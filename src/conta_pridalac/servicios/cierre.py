"""Cierre del ejercicio: regularización, asiento de cierre y apertura del siguiente (docs/pseudocodigo/07_cierre_e_iva.md §2).

Sigue `CierreContable` y `RegulIngresosGastos` de MGD:
1. **Regularización de ingresos y gastos**: salda las cuentas de los grupos de gastos (6) e ingresos (7) contra Pérdidas y
   Ganancias, que queda con el resultado. No cuenta regularizaciones ni cierres anteriores, así que se puede repetir.
2. **Asiento de cierre**: salda todas las cuentas con saldo. Exige que el Diario cuadre y que ingresos y gastos estén a cero.
3. **Apertura del ejercicio siguiente**: abre cada cuenta con el saldo que tenía **antes del cierre** y arrastra los
   vencimientos pendientes (cada uno en una línea de su cuenta, con su texto) para que sigan siendo exigibles.

`cerrar_ejercicio` lo encadena y exige una auditoría sin errores. Todo es idempotente: repetirlo sustituye los asientos.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    TIPO_AUTOMATICO,
    Apunte,
    Asiento,
    Cuenta,
    Ejercicio,
    Parametro,
    Vencimiento,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.tesoreria import cuenta_efectiva, pendiente
from conta_pridalac.servicios.extras import LineaManual, ResultadoExtra, eliminar_extra, grabar_extra
from conta_pridalac.servicios.vencimientos import PlazoVencimiento

CERO = Decimal("0.00")
SUBTIPO_APERTURA, SUBTIPO_REGULARIZACION, SUBTIPO_CIERRE = "A", "R", "Z"


# ------------------------------------------------------------------------------------------------ saldos


def _parametro(sesion: Session, ejercicio: Ejercicio, clave: str, defecto: str = "") -> str:
    valor = sesion.scalar(select(Parametro.valor).where(Parametro.empresa_id == ejercicio.empresa_id, Parametro.clave == clave))
    return valor.strip() if valor and valor.strip() else defecto


def prefijos_ingresos_y_gastos(sesion: Session, ejercicio: Ejercicio) -> tuple[str, ...]:
    """Grupos de ingresos y de gastos (`G_INGRESOS`, `G_GASTOS`; por defecto 7 y 6), como prefijos de cuenta."""
    texto = f"{_parametro(sesion, ejercicio, 'G_GASTOS', '6')},{_parametro(sesion, ejercicio, 'G_INGRESOS', '7')}"
    return tuple(p.strip() for p in texto.split(",") if p.strip())


def saldos_del_ejercicio(
    sesion: Session, ejercicio: Ejercicio, *, hasta: date | None = None, excluir: tuple[str, ...] = ()
) -> dict[str, Decimal]:
    """Saldo (debe − haber) de cada cuenta con movimientos del ejercicio, sin los asientos de los subtipos `excluir`."""
    consulta = (
        select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Apunte, Apunte.cuenta_id == Cuenta.id)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ejercicio.id)
        .group_by(Cuenta.codigo)
    )
    if hasta is not None:
        consulta = consulta.where(Asiento.fecha <= hasta)
    if excluir:
        consulta = consulta.where(func.coalesce(Asiento.subtipo, "").not_in(excluir))
    saldos = {}
    for codigo, debe, haber in sesion.execute(consulta):
        neto = (debe or CERO) - (haber or CERO)
        if neto != 0:
            saldos[codigo] = neto
    return saldos


def _buscar(sesion: Session, ejercicio: Ejercicio, subtipo: str, fecha: date | None = None) -> Asiento | None:
    consulta = select(Asiento).where(
        Asiento.ejercicio_id == ejercicio.id, Asiento.tipo == TIPO_AUTOMATICO, Asiento.subtipo == subtipo
    )
    if fecha is not None:
        consulta = consulta.where(Asiento.fecha == fecha)
    return sesion.scalars(consulta.order_by(Asiento.numero)).first()


def _nombre(sesion: Session, ejercicio: Ejercicio, codigo: str) -> str:
    return sesion.scalars(select(Cuenta.nombre).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == codigo)).first() or ""


def _lineas_de(sesion: Session, ejercicio: Ejercicio, importes: dict[str, Decimal]) -> list[LineaManual]:
    """Debe primero y haber después; los importes con signo (debe +)."""
    ordenadas = sorted(importes.items(), key=lambda kv: (kv[1] < 0, kv[0]))
    return [LineaManual(c, "D" if i > 0 else "H", abs(i), _nombre(sesion, ejercicio, c)) for c, i in ordenadas if i != 0]


# ------------------------------------------------------------------------------------------------ regularización


def regularizar_ingresos_gastos(sesion: Session, ejercicio: Ejercicio, fecha: date | None = None) -> ResultadoExtra:
    """Asiento de regularización (tipo 9, subtipo R). Solo cuentan los movimientos que no son regularizaciones ni cierres."""
    fecha = fecha or ejercicio.fecha_fin
    pyg = _parametro(sesion, ejercicio, "PYG")
    if not pyg or sesion.scalar(select(func.count()).select_from(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == pyg)) == 0:
        raise ErrorContable(f"No existe la cuenta de Pérdidas y Ganancias ({pyg or 'parámetro PYG sin definir'})")
    prefijos = prefijos_ingresos_y_gastos(sesion, ejercicio)
    saldos = {
        c: s
        for c, s in saldos_del_ejercicio(sesion, ejercicio, hasta=fecha, excluir=(SUBTIPO_REGULARIZACION, SUBTIPO_CIERRE)).items()
        if c.startswith(prefijos)
    }
    existente = _buscar(sesion, ejercicio, SUBTIPO_REGULARIZACION, fecha)
    if not saldos:
        if existente is not None:  # ya no hay nada que regularizar: se quita la antigua
            eliminar_extra(sesion, ejercicio, existente)
        raise ErrorContable("No hay ingresos ni gastos que regularizar")
    importes = {c: -s for c, s in saldos.items()}  # cada cuenta se salda
    importes[pyg] = importes.get(pyg, CERO) + sum(saldos.values(), CERO)  # y P y G recoge el resultado
    return grabar_extra(
        sesion, ejercicio, fecha=fecha, texto="REGUL. DE INGRESOS Y GASTOS", lineas=_lineas_de(sesion, ejercicio, importes),
        numero=existente.numero if existente else None, tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_REGULARIZACION,
    )


# ------------------------------------------------------------------------------------------------ cierre


def asiento_de_cierre(sesion: Session, ejercicio: Ejercicio, fecha: date | None = None) -> ResultadoExtra:
    """Asiento de cierre (tipo 9, subtipo Z): salda todas las cuentas con saldo."""
    fecha = fecha or ejercicio.fecha_fin
    saldos = saldos_del_ejercicio(sesion, ejercicio, hasta=fecha, excluir=(SUBTIPO_CIERRE,))
    descuadre = sum(saldos.values(), CERO)
    if descuadre != 0:
        raise ErrorContable(f"El Diario está descuadrado ({descuadre}); no se puede cerrar. Ejecute la auditoría de integridad.")
    prefijos = prefijos_ingresos_y_gastos(sesion, ejercicio)
    for cuenta, saldo in sorted(saldos.items()):
        if cuenta.startswith(prefijos):
            raise ErrorContable(
                f"La cuenta {cuenta} de ingresos y gastos tiene saldo ({saldo}): probablemente está pendiente la regularización de ingresos y gastos"
            )
    if not saldos:
        raise ErrorContable("No hay saldos que cerrar")
    existente = _buscar(sesion, ejercicio, SUBTIPO_CIERRE)
    return grabar_extra(
        sesion, ejercicio, fecha=fecha, texto="ASIENTO DE CIERRE",
        lineas=_lineas_de(sesion, ejercicio, {c: -s for c, s in saldos.items()}),
        numero=existente.numero if existente else None, tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_CIERRE,
    )


# ------------------------------------------------------------------------------------------------ apertura


def _texto_de_vencimiento(v: Vencimiento) -> str:
    if v.factura is not None and v.factura.tercero is not None:
        tercero = v.factura.tercero.nombre
    elif v.apunte is not None:
        tercero = v.apunte.asiento.concepto
    else:
        tercero = ""
    return f"{v.origen_tipo} {v.origen_numero} {tercero}".strip().upper()[:64]


@dataclass
class ResultadoApertura:
    ejercicio: Ejercicio
    extra: ResultadoExtra
    vencimientos_arrastrados: int = 0
    advertencias: list[str] = field(default_factory=list)


def ejercicio_siguiente(sesion: Session, ejercicio: Ejercicio) -> Ejercicio:
    """El ejercicio que empieza el día siguiente al fin de éste; se crea si no existe."""
    inicio = date.fromordinal(ejercicio.fecha_fin.toordinal() + 1)
    existente = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ejercicio.empresa_id, Ejercicio.anio == inicio.year)).first()
    if existente is not None:
        return existente
    fin = date(inicio.year, 12, 31) if inicio.month == 1 else date(inicio.year + 1, inicio.month - 1, calendar.monthrange(inicio.year + 1, inicio.month - 1)[1])
    nuevo = Ejercicio(empresa_id=ejercicio.empresa_id, anio=inicio.year, fecha_inicio=inicio, fecha_fin=fin, cerrado=False)
    sesion.add(nuevo)
    sesion.flush()
    return nuevo


def abrir_ejercicio(sesion: Session, ejercicio: Ejercicio) -> ResultadoApertura:
    """Asiento de apertura del ejercicio siguiente (tipo 9, subtipo A, nº 1) con los vencimientos pendientes (`AsientoAperturaOtra`).

    Cada cuenta se abre con el saldo que tenía antes del cierre. Cada vencimiento pendiente va en una línea de su cuenta
    con su texto y su fecha, y la línea base de la cuenta baja en ese importe; si la cuenta no tiene saldo se compensa con
    una línea «COMPENSACION». Los vencimientos de una cuenta que acaba con saldo 0 no se pueden colgar de ningún apunte:
    se avisa.
    """
    saldos = saldos_del_ejercicio(sesion, ejercicio, excluir=(SUBTIPO_CIERRE,))
    if not saldos:
        raise ErrorContable("No hay saldos que abrir en el ejercicio siguiente")
    nuevo = ejercicio_siguiente(sesion, ejercicio)

    base: dict[str, Decimal] = dict(saldos)
    detalle: list[tuple[str, Decimal, str, Vencimiento | None]] = []  # cuenta, importe, texto, vencimiento
    for v in sesion.scalars(select(Vencimiento).where(Vencimiento.ejercicio_id == ejercicio.id).order_by(Vencimiento.id)):
        pte = pendiente(sesion, v)
        if pte == 0:
            continue
        cuenta = cuenta_efectiva(v)
        if cuenta is None:
            raise ErrorContable(f"El vencimiento {v.origen_tipo} {v.origen_numero} no tiene cuenta")
        texto = _texto_de_vencimiento(v)
        detalle.append((cuenta.codigo, pte, texto, v))
        if cuenta.codigo in saldos:
            base[cuenta.codigo] -= pte
        else:
            detalle.append((cuenta.codigo, -pte, "COMPENSACION " + texto, None))

    lineas: list[LineaManual] = []
    for cuenta, importe in base.items():
        if importe != 0:
            lineas.append(LineaManual(cuenta, "D" if importe > 0 else "H", abs(importe), _nombre(sesion, ejercicio, cuenta)))
    advertencias = []
    arrastrados = 0
    for cuenta, importe, texto, v in detalle:
        plazos = None
        if v is not None:
            plazos = [PlazoVencimiento(importe=pendiente(sesion, v), fecha=v.fecha, banco=v.banco_previsto, forma_pago=v.forma_pago)]
            arrastrados += 1
        lineas.append(LineaManual(cuenta, "D" if importe > 0 else "H", abs(importe), texto, plazos))

    # Cuentas que acaban en saldo 0 tras agrupar: sus vencimientos no tienen apunte al que colgarse
    neto = {c: CERO for c in {l.cuenta for l in lineas}}
    for l in lineas:
        neto[l.cuenta] += l.importe if l.dh == "D" else -l.importe
    for cuenta, n in neto.items():
        if n == 0:
            for l in lineas:
                if l.cuenta == cuenta and l.vencimientos:
                    advertencias.append(f"La cuenta {cuenta} tiene vencimientos pendientes pero su saldo de apertura es 0: no se arrastran ({l.ayuda})")
                    l.vencimientos = None
                    arrastrados -= 1

    existente = _buscar(sesion, nuevo, SUBTIPO_APERTURA)
    ordenadas = sorted(lineas, key=lambda l: (l.dh == "H", l.cuenta))
    extra = grabar_extra(
        sesion, nuevo, fecha=nuevo.fecha_inicio, texto="ASIENTO DE APERTURA", lineas=ordenadas,
        numero=existente.numero if existente else 1, tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_APERTURA,
    )
    # No se propagan los avisos de «los vencimientos no suman el apunte»: en una apertura es normal, porque el apunte
    # agrupa la línea base de la cuenta y las de sus vencimientos (incluso de signo contrario).
    return ResultadoApertura(nuevo, extra, arrastrados, advertencias)


# ------------------------------------------------------------------------------------------------ orquestación


@dataclass
class ResultadoCierre:
    regularizacion: ResultadoExtra | None
    cierre: ResultadoExtra
    apertura: ResultadoApertura | None
    resultado: Decimal  # beneficio (positivo) o pérdida (negativo) del ejercicio
    advertencias: list[str] = field(default_factory=list)


def cerrar_ejercicio(
    sesion: Session, ejercicio: Ejercicio, *, abrir_siguiente: bool = True, exigir_auditoria: bool = True
) -> ResultadoCierre:
    """Regulariza (si hace falta), cierra, abre el siguiente y marca el ejercicio como cerrado.

    La auditoría de integridad debe estar **sin errores**: el cierre no se hace sobre una contabilidad incoherente.
    """
    if ejercicio.cerrado:
        raise ErrorContable(f"El ejercicio {ejercicio.anio} ya está cerrado")
    if exigir_auditoria:
        from conta_pridalac.auditoria import ERROR, auditar

        errores = [h for h in auditar(sesion, ejercicio) if h.gravedad == ERROR]
        if errores:
            resumen = "; ".join(f"{h.referencia}: {h.mensaje}" for h in errores[:5])
            raise ErrorContable(f"La auditoría tiene {len(errores)} error(es); corríjalos antes de cerrar. {resumen}")

    prefijos = prefijos_ingresos_y_gastos(sesion, ejercicio)
    # Los movimientos de ingresos y gastos *sin contar la regularización anterior*: si queda alguno hay que (re)regularizar, y la
    # regularización es idempotente, así que una antigua —de antes de reabrir y añadir algo— se sustituye en vez de quedarse desfasada.
    sin_regularizar = {
        c: s
        for c, s in saldos_del_ejercicio(sesion, ejercicio, excluir=(SUBTIPO_REGULARIZACION, SUBTIPO_CIERRE)).items()
        if c.startswith(prefijos)
    }
    regularizacion = None
    if sin_regularizar:
        regularizacion = regularizar_ingresos_gastos(sesion, ejercicio)
    cierre = asiento_de_cierre(sesion, ejercicio)
    pyg = _parametro(sesion, ejercicio, "PYG")
    regul = regularizacion.asiento if regularizacion else _buscar(sesion, ejercicio, SUBTIPO_REGULARIZACION)
    # El resultado del año es lo que la regularización lleva a P y G (el saldo de P y G puede arrastrar el del año anterior)
    resultado = -sum((ap.debe - ap.haber for ap in (regul.apuntes if regul else []) if ap.cuenta.codigo == pyg), CERO)
    apertura = abrir_ejercicio(sesion, ejercicio) if abrir_siguiente else None
    ejercicio.cerrado = True
    sesion.flush()
    avisos = list(apertura.advertencias) if apertura else []
    return ResultadoCierre(regularizacion, cierre, apertura, resultado, avisos)


def reabrir_ejercicio(sesion: Session, ejercicio: Ejercicio) -> None:
    """Deshace el cierre completo: borra el asiento de cierre, la regularización de ingresos y gastos y la apertura del siguiente
    ejercicio (solo si éste no tiene más movimientos que su apertura). Al volver a cerrar se regulariza de nuevo con lo que haya."""
    if not ejercicio.cerrado:
        raise ErrorContable(f"El ejercicio {ejercicio.anio} no está cerrado")
    siguiente = sesion.scalars(
        select(Ejercicio).where(Ejercicio.empresa_id == ejercicio.empresa_id, Ejercicio.fecha_inicio == date.fromordinal(ejercicio.fecha_fin.toordinal() + 1))
    ).first()
    ejercicio.cerrado = False
    sesion.flush()
    if siguiente is not None:
        otros = sesion.scalar(
            select(func.count()).select_from(Asiento).where(Asiento.ejercicio_id == siguiente.id, func.coalesce(Asiento.subtipo, "") != SUBTIPO_APERTURA)
        )
        if otros:
            ejercicio.cerrado = True
            raise ErrorContable(f"El ejercicio {siguiente.anio} ya tiene movimientos además de la apertura; no se puede reabrir {ejercicio.anio}")
        apertura = _buscar(sesion, siguiente, SUBTIPO_APERTURA)
        if apertura is not None:
            eliminar_extra(sesion, siguiente, apertura)
        sesion.delete(siguiente)
        sesion.flush()
    for subtipo in (SUBTIPO_CIERRE, SUBTIPO_REGULARIZACION):  # primero el cierre y luego la regularización
        asiento = _buscar(sesion, ejercicio, subtipo)
        if asiento is not None:
            eliminar_extra(sesion, ejercicio, asiento)
