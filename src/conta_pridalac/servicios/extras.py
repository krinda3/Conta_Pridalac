"""Asientos manuales («extras» de MGD) y plantillas (docs/pseudocodigo/06_extras_y_plantillas.md).

Un asiento manual es un `Asiento` de tipo 4 (general) cuyas líneas se teclean —o salen de una plantilla— en vez de derivarse
de un documento. Cada línea puede llevar **vencimientos** (p. ej. la cuota de un préstamo o la retención de una nómina):
cuelgan del apunte de esa línea y se saldan con movimientos de banco como los de una factura.

En MGD los extras también se agrupan por cuenta en el Diario (14 de 14 extras reales lo confirman), igual que el resto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    TIPO_GENERAL,
    Apunte,
    Asiento,
    Cuenta,
    Ejercicio,
    Pago,
    Plantilla,
    Vencimiento,
)
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import DocumentoConPagos, ErrorContable
from conta_pridalac.domain.fechas import validar_en_ejercicio
from conta_pridalac.domain.plantillas import (
    LineaPlantilla,
    aplicar_plantilla,
    evaluar_texto,
    fecha_de_vencimiento,
)
from conta_pridalac.servicios.asientos import LineaAsiento, buscar_asiento, grabar_asiento
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, repartir_en_plazos

CERO = Decimal("0.00")


@dataclass
class LineaManual:
    """Línea de un asiento manual. `importe` positivo; `dh` = "D" o "H".

    `vencimientos`: `None` = no tocar los que ya tenga el apunte; `[]` = quitarlos; lista = establecerlos. Los importes de
    los plazos van **con signo** (positivo a cobrar, negativo a pagar): en un apunte que agrupa líneas del debe y del haber
    de la misma cuenta (el asiento de apertura) el signo del vencimiento no se deduce del apunte neto.
    """

    cuenta: str  # código de 8 dígitos
    dh: str
    importe: Decimal
    ayuda: str = ""
    vencimientos: list[PlazoVencimiento] | None = None


@dataclass
class ResultadoExtra:
    asiento: Asiento
    vencimientos: list[Vencimiento] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def siguiente_numero(sesion: Session, ejercicio: Ejercicio, tipo: int = TIPO_GENERAL) -> int:
    maximo = sesion.scalar(select(func.max(Asiento.numero)).where(Asiento.ejercicio_id == ejercicio.id, Asiento.tipo == tipo))
    return (maximo or 0) + 1


def _con_pagos(sesion: Session, v: Vencimiento) -> bool:
    return bool(sesion.scalar(select(func.count()).select_from(Pago).where(Pago.vencimiento_id == v.id)))


def _vencimientos_del_apunte(sesion: Session, apunte: Apunte) -> list[Vencimiento]:
    return sorted(sesion.scalars(select(Vencimiento).where(Vencimiento.apunte_id == apunte.id)), key=lambda v: v.id)


def _establecer_vencimientos(
    sesion: Session, ejercicio: Ejercicio, asiento: Asiento, apunte: Apunte, plazos: list[PlazoVencimiento]
) -> tuple[list[Vencimiento], list[str]]:
    existentes = _vencimientos_del_apunte(sesion, apunte)
    for sobrante in existentes[len(plazos):]:
        if _con_pagos(sesion, sobrante):
            raise DocumentoConPagos(f"El vencimiento del {sobrante.fecha} de la cuenta {apunte.cuenta.codigo} ya tiene cobros o pagos; no se puede quitar")
        sesion.delete(sobrante)

    resultado, avisos = [], []
    for i, p in enumerate(plazos):
        v = existentes[i] if i < len(existentes) else Vencimiento(ejercicio_id=ejercicio.id)
        v.origen_tipo, v.origen_numero, v.apunte_id = "X", asiento.numero, apunte.id
        v.fecha = p.fecha
        v.importe = dinero(p.importe)  # con signo: positivo a cobrar, negativo a pagar
        v.cuenta_id = None
        v.cuenta_defecto_id = v.cuenta_origen_id = apunte.cuenta_id
        v.banco_previsto, v.forma_pago = p.banco, p.forma_pago
        sesion.add(v)
        resultado.append(v)
    neto = apunte.debe - apunte.haber
    suma = sum((dinero(p.importe) for p in plazos), CERO)
    if plazos and suma != neto:
        avisos.append(f"Los vencimientos de la cuenta {apunte.cuenta.codigo} suman {suma} y el apunte es de {neto}")
    return resultado, avisos


def grabar_extra(
    sesion: Session,
    ejercicio: Ejercicio,
    *,
    fecha: date,
    texto: str,
    lineas: list[LineaManual],
    numero: int | None = None,
    tipo: int = TIPO_GENERAL,
    subtipo: str = "M",
) -> ResultadoExtra:
    """Crea o regraba un asiento manual con sus líneas y vencimientos. Debe cuadrar; si no, no se graba."""
    validar_en_ejercicio(fecha, ejercicio)
    if not lineas:
        raise ErrorContable("Un asiento necesita al menos una línea")
    for l in lineas:
        if l.dh not in ("D", "H"):
            raise ErrorContable(f"La línea de la cuenta {l.cuenta} tiene un lado {l.dh!r}; debe ser D o H")
        if l.importe < 0:
            raise ErrorContable(f"La línea de la cuenta {l.cuenta} tiene importe negativo; use el otro lado")
    numero = numero or siguiente_numero(sesion, ejercicio, tipo)

    # Las líneas que desaparecen al regrabar arrastran sus vencimientos (si no tienen pagos)
    previo = buscar_asiento(sesion, ejercicio, tipo, numero)
    if previo is not None:
        cuentas_nuevas = {l.cuenta for l in lineas if l.importe != 0}
        for ap in previo.apuntes:
            if ap.cuenta.codigo not in cuentas_nuevas:
                for v in _vencimientos_del_apunte(sesion, ap):
                    if _con_pagos(sesion, v):
                        raise DocumentoConPagos(
                            f"La cuenta {ap.cuenta.codigo} desaparece del asiento {previo.identificador} pero tiene un vencimiento con cobros o pagos"
                        )
                    sesion.delete(v)
        sesion.flush()

    asiento = grabar_asiento(
        sesion, ejercicio, tipo=tipo, numero=numero, fecha=fecha, concepto=texto, subtipo=subtipo,
        lineas=[LineaAsiento(l.cuenta, dinero(l.importe) * (1 if l.dh == "D" else -1), l.ayuda or None) for l in lineas],
    )
    if asiento is None:
        raise ErrorContable("Todas las líneas tienen importe 0: no hay asiento que grabar")

    por_cuenta = {ap.cuenta.codigo: ap for ap in asiento.apuntes}
    vencimientos: list[Vencimiento] = []
    advertencias: list[str] = []
    plazos_por_cuenta: dict[str, list[PlazoVencimiento]] = {}
    for l in lineas:
        if l.vencimientos is not None:
            plazos_por_cuenta.setdefault(l.cuenta, []).extend(l.vencimientos)
    for cuenta, plazos in plazos_por_cuenta.items():
        vs, avisos = _establecer_vencimientos(sesion, ejercicio, asiento, por_cuenta[cuenta], plazos)
        vencimientos += vs
        advertencias += avisos
    sesion.flush()
    return ResultadoExtra(asiento, vencimientos, advertencias)


def lineas_de_plantilla(plantilla: Plantilla) -> list[LineaPlantilla]:
    return [
        LineaPlantilla(l.cuenta, l.ayuda, l.dhc, l.importe, [v.strip() for v in l.vencimientos.split(",") if v.strip()])
        for l in plantilla.lineas
    ]


def crear_desde_plantilla(
    sesion: Session, ejercicio: Ejercicio, plantilla: Plantilla, fecha: date, importes: list[Decimal], *, texto: str | None = None
) -> ResultadoExtra:
    """Asiento a partir de una plantilla (`vNuevoExtra`): título con {año}/{mes}…, línea de cuadre calculada y vencimientos
    automáticos según las reglas de cada línea."""
    lineas_extra = aplicar_plantilla(lineas_de_plantilla(plantilla), importes)
    existentes = {
        c.codigo for c in sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo.in_({l.cuenta for l in lineas_extra})))
    }
    for l in lineas_extra:
        if l.cuenta not in existentes:
            raise ErrorContable(
                f"La plantilla «{plantilla.titulo}» no se puede usar: la cuenta {l.cuenta} no está creada. "
                "Cree la cuenta o modifique la plantilla."
            )
    manuales = []
    for l in lineas_extra:
        plazos = None
        if l.vencimientos:
            fechas = [fecha_de_vencimiento(r, fecha) for r in l.vencimientos]
            plazos = []
            signo = 1 if l.dh == "D" else -1  # a cobrar si va al debe; a pagar si va al haber
            for p, f in zip(repartir_en_plazos(l.importe, len(fechas), None), fechas):
                p.fecha, p.importe = f, signo * p.importe
                plazos.append(p)
        manuales.append(LineaManual(l.cuenta, l.dh, l.importe, l.ayuda, plazos))
    return grabar_extra(sesion, ejercicio, fecha=fecha, texto=texto or evaluar_texto(plantilla.titulo, fecha), lineas=manuales)


def eliminar_extra(sesion: Session, ejercicio: Ejercicio, asiento: Asiento) -> None:
    """Borra un asiento manual con sus vencimientos. No si algún vencimiento ya tiene cobros o pagos."""
    validar_en_ejercicio(ejercicio.fecha_inicio, ejercicio)  # solo comprueba que el ejercicio admite cambios
    vencimientos = [v for ap in asiento.apuntes for v in _vencimientos_del_apunte(sesion, ap)]
    if any(_con_pagos(sesion, v) for v in vencimientos):
        raise DocumentoConPagos(f"El asiento {asiento.identificador} tiene vencimientos con cobros o pagos aplicados; deshaga primero esos movimientos")
    for v in vencimientos:
        sesion.delete(v)
    sesion.flush()
    sesion.delete(asiento)
    sesion.flush()


def buscar_extra(sesion: Session, ejercicio: Ejercicio, numero: int, tipo: int = TIPO_GENERAL) -> Asiento | None:
    return buscar_asiento(sesion, ejercicio, tipo, numero)
