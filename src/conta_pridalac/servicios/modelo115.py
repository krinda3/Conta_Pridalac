"""Modelo 115 (retenciones e ingresos a cuenta por arrendamientos de inmuebles urbanos): cálculo del trimestre desde los libros.

Regla seguida (la misma idea que el 111, `servicios/modelo111.py`):

- Un asiento es **de alquiler** si carga la cuenta 621 (arrendamientos y cánones). Su retención es el abono neto a las cuentas 4751 de ese asiento, y va al 115 (el 111 la salta).
- **Base** (casilla 02) = lo cargado a la 621 en esos asientos: la renta **sin IVA**. **Retención** (03) = abono neto a la 4751. Lo habitual es el 19 %.
- **Perceptores** (01) = arrendadores distintos (cuentas de acreedor 40 y 41 del asiento).
- **04** = resultado de la declaración que se complementa (sólo en una complementaria) · **05** = resultado a ingresar = 03 − 04. Sin retenciones el trimestre se presenta **negativa / sin actividad** (tipo N).
- Asientos de alquiler **sin retención** (arrendador exento, renta anual de hasta 900 €…) no entran, pero se avisa por si se olvidó retener.
- Los asientos de apertura, cierre, regularización, liquidación de IVA y los movimientos de banco no cuentan, igual que en el 111.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Tercero
from conta_pridalac.servicios.modelo111 import CUENTA_DE_ALQUILERES, SUBTIPOS_QUE_NO_SON_OPERACIONES, TIPO_TESORERIA, _dec, es_de_alquiler
from conta_pridalac.servicios.modelo303 import periodo_de_fechas

CERO = Decimal("0.00")
PORCENTAJES_HABITUALES = (Decimal("19"),)


@dataclass
class Linea115:
    """Una retención practicada: de dónde sale cada importe."""

    asiento: str
    fecha: date
    cuenta: str
    perceptor: str
    nif: str | None
    base: Decimal
    retencion: Decimal

    @property
    def porcentaje(self) -> Decimal:
        return (self.retencion / self.base * 100).quantize(Decimal("0.01")) if self.base else CERO


@dataclass
class Calculo115:
    anio: int
    periodo: int
    desde: date
    hasta: date
    casillas: dict[int, Decimal] = field(default_factory=dict)
    lineas: list[Linea115] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def __getitem__(self, casilla: int) -> Decimal:
        return self.casillas.get(casilla, CERO)


def calcular_115(sesion: Session, ejercicio: Ejercicio, periodo: int, *, anterior_5: Decimal | None = None) -> Calculo115:
    """Casillas del 115 del trimestre. Con `anterior_5` (resultado a ingresar de la declaración que se complementa) se rellena la casilla 04."""
    desde, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    c = Calculo115(ejercicio.anio, periodo, desde, hasta)
    asientos = sesion.scalars(
        select(Asiento).where(
            Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta, Asiento.tipo != TIPO_TESORERIA,
            Asiento.subtipo.is_(None) | Asiento.subtipo.not_in(SUBTIPOS_QUE_NO_SON_OPERACIONES),
        ).order_by(Asiento.fecha, Asiento.tipo, Asiento.numero)
    ).all()
    for a in asientos:
        if not es_de_alquiler(a):
            continue
        retencion = sum((ap.haber - ap.debe for ap in a.apuntes if ap.cuenta.codigo.startswith("4751")), CERO)
        base = sum((ap.debe - ap.haber for ap in a.apuntes if ap.cuenta.codigo.startswith(CUENTA_DE_ALQUILERES)), CERO)
        if retencion <= 0:
            c.avisos.append(f"El asiento {a.identificador} es un alquiler ({base}) sin retención: ¿arrendador exento (renta anual de hasta 900 €) o se olvidó retener?")
            continue
        acreedores: dict[str, Decimal] = defaultdict(lambda: CERO)
        for ap in a.apuntes:
            if ap.cuenta.codigo.startswith(("40", "41")):
                acreedores[ap.cuenta.codigo] += ap.haber - ap.debe
        if not acreedores:
            c.avisos.append(f"El asiento {a.identificador} retiene {retencion} de un alquiler pero no tiene ninguna cuenta de acreedor (40 o 41): no se sabe quién es el arrendador")
            continue
        total = sum(acreedores.values(), CERO)
        for cuenta, neto in acreedores.items():
            peso = (neto / total) if total else Decimal(1) / len(acreedores)  # reparto si hay varios arrendadores en el asiento
            cuenta_db = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == cuenta))
            tercero = sesion.scalar(select(Tercero).where(Tercero.cuenta_id == cuenta_db.id)) if cuenta_db else None
            c.lineas.append(Linea115(a.identificador, a.fecha, cuenta, (tercero.nombre if tercero else cuenta_db.nombre if cuenta_db else cuenta), tercero.nif if tercero else None,
                                     _dec(base * peso), _dec(retencion * peso)))
    retenciones = sum((l.retencion for l in c.lineas), CERO)
    if retenciones:
        c.casillas[1] = Decimal(len({l.cuenta for l in c.lineas}))
        c.casillas[2] = sum((l.base for l in c.lineas), CERO)
    c.casillas[3] = retenciones
    if anterior_5:
        c.casillas[4] = _dec(anterior_5)
    c.casillas[5] = _dec(retenciones - c[4])
    for l in c.lineas:
        if l.porcentaje not in PORCENTAJES_HABITUALES:
            c.avisos.append(f"{l.perceptor} ({l.asiento}): la retención es el {l.porcentaje} % de la renta y lo habitual es el 19 %: revise el asiento")
    if any(not l.nif for l in c.lineas):
        c.avisos.append("Hay arrendadores sin NIF en su ficha: hará falta para el modelo 180 (resumen anual)")
    return c
