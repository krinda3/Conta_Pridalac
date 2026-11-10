"""Modelo 111 (retenciones e ingresos a cuenta del IRPF): cálculo del trimestre desde los libros.

Regla seguida (la de las declaraciones presentadas hasta ahora, comprobada con `tools/comparar_111.py`):

- **Retención practicada** = abono neto a las cuentas 4751 (Hacienda Pública acreedora por retenciones practicadas) en los asientos **del trimestre** que no son de apertura, cierre,
  regularización ni de liquidación de IVA, ni movimientos de banco (los pagos a Hacienda cargan la 4751 y no cuentan).
- **Percepción** = lo devengado a favor del perceptor en ese mismo asiento antes de retener: abono neto a sus cuentas de acreedores (40 y 41) más la retención. Es lo que figura en la casilla
  de importe de percepciones: el importe total de la factura, con su IVA (así se ha presentado hasta ahora).
- **Perceptores** = cuentas de acreedor distintas en esos asientos.
- Todo se declara como **actividades económicas, rendimientos dinerarios** (casillas 07, 08 y 09): hoy sólo hay retenciones de ese tipo (compras a agricultores al 2 %). Si aparecen nóminas, premios
  u otras claves habrá que distinguirlas (casillas 01-03, 13-15…): el cálculo lo avisa cuando el porcentaje de retención no es el habitual.
- **28** = suma de retenciones · **29** = resultado de anteriores declaraciones (sólo en una complementaria) · **30** = resultado a ingresar = 28 − 29. Sin retenciones, el trimestre se presenta
  **negativa / sin actividad** (tipo N), que es lo habitual.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.modelo303 import periodo_de_fechas

CERO = Decimal("0.00")
SUBTIPOS_QUE_NO_SON_OPERACIONES = ("A", "P", "R", "Z")
TIPO_TESORERIA = 3
PORCENTAJES_HABITUALES = (Decimal("2"),)  # compras a agricultores y ganaderos
CUENTA_DE_ALQUILERES = "621"  # arrendamientos y cánones: sus retenciones van al modelo 115 (`servicios/modelo115.py`), no al 111


def es_de_alquiler(asiento) -> bool:
    return any(ap.cuenta.codigo.startswith(CUENTA_DE_ALQUILERES) and ap.debe > ap.haber for ap in asiento.apuntes)


@dataclass
class Linea111:
    """Una retención practicada: de dónde sale cada importe."""

    asiento: str
    fecha: date
    cuenta: str
    perceptor: str
    nif: str | None
    percepcion: Decimal
    retencion: Decimal

    @property
    def porcentaje(self) -> Decimal:
        return (self.retencion / self.percepcion * 100).quantize(Decimal("0.01")) if self.percepcion else CERO


@dataclass
class Calculo111:
    anio: int
    periodo: int
    desde: date
    hasta: date
    casillas: dict[int, Decimal] = field(default_factory=dict)
    lineas: list[Linea111] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def __getitem__(self, casilla: int) -> Decimal:
        return self.casillas.get(casilla, CERO)


def _dec(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_111(sesion: Session, ejercicio: Ejercicio, periodo: int, *, anterior_30: Decimal | None = None) -> Calculo111:
    """Casillas del 111 del trimestre. Con `anterior_30` (resultado a ingresar de la declaración que se complementa) se rellena la casilla 29 con su signo cambiado."""
    desde, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    c = Calculo111(ejercicio.anio, periodo, desde, hasta)
    asientos = sesion.scalars(
        select(Asiento).where(
            Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta, Asiento.tipo != TIPO_TESORERIA,
            Asiento.subtipo.is_(None) | Asiento.subtipo.not_in(SUBTIPOS_QUE_NO_SON_OPERACIONES),
        ).order_by(Asiento.fecha, Asiento.tipo, Asiento.numero)
    ).all()
    for a in asientos:
        retencion = sum((ap.haber - ap.debe for ap in a.apuntes if ap.cuenta.codigo.startswith("4751")), CERO)
        if retencion <= 0:
            continue
        if es_de_alquiler(a):  # retención de un alquiler: va al 115
            continue
        acreedores: dict[str, Decimal] = defaultdict(lambda: CERO)
        for ap in a.apuntes:
            if ap.cuenta.codigo.startswith(("40", "41")):
                acreedores[ap.cuenta.codigo] += ap.haber - ap.debe
        if not acreedores:
            c.avisos.append(f"El asiento {a.identificador} retiene {retencion} pero no tiene ninguna cuenta de acreedor (40 o 41): no se sabe quién es el perceptor")
            continue
        total_acreedores = sum(acreedores.values(), CERO)
        for cuenta, neto in acreedores.items():
            parte = (retencion * neto / total_acreedores) if total_acreedores else retencion / len(acreedores)  # reparto si hay varios perceptores en el asiento
            cuenta_db = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == cuenta))
            tercero = sesion.scalar(select(Tercero).where(Tercero.cuenta_id == cuenta_db.id)) if cuenta_db else None
            c.lineas.append(Linea111(a.identificador, a.fecha, cuenta, (tercero.nombre if tercero else cuenta_db.nombre if cuenta_db else cuenta), tercero.nif if tercero else None,
                                     _dec(neto + parte), _dec(parte)))
    retenciones = sum((l.retencion for l in c.lineas), CERO)
    if retenciones:
        c.casillas[7] = Decimal(len({l.cuenta for l in c.lineas}))
        c.casillas[8] = sum((l.percepcion for l in c.lineas), CERO)
        c.casillas[9] = retenciones
    c.casillas[28] = retenciones
    if anterior_30 is not None and anterior_30:
        c.casillas[29] = -_dec(anterior_30)
    c.casillas[30] = _dec(retenciones + c[29])
    for l in c.lineas:
        if l.porcentaje not in PORCENTAJES_HABITUALES:
            c.avisos.append(f"{l.perceptor} ({l.asiento}): la retención es el {l.porcentaje} % y lo habitual aquí es el 2 %: ¿es otro tipo de rendimiento (nómina, profesional, premio…) que va a otras casillas?")
    if any(not l.nif for l in c.lineas):
        c.avisos.append("Hay perceptores sin NIF en su ficha: hará falta para el modelo 190 (resumen anual)")
    return c
