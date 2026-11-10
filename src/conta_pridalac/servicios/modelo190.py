"""Modelo 190 (resumen anual de retenciones e ingresos a cuenta del IRPF): cálculo del ejercicio desde los libros.

Es la suma de los cuatro 111 del año (`modelo111.calcular_111`, con la misma regla de percepciones y retenciones), agrupada por perceptor: una percepción por perceptor, con su NIF, nombre, provincia, clave y subclave.
Comprobado contra lo presentado con `tools/comparar_190.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Tercero
from conta_pridalac.servicios.modelo111 import CERO, calcular_111


@dataclass
class Perceptor190:
    cuenta: str
    nombre: str
    nif: str | None
    provincia: str | None
    clave: str | None
    subclave: str | None
    percepcion: Decimal = CERO
    retencion: Decimal = CERO
    asientos: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return bool(self.nif and self.provincia and self.clave and self.subclave)

    @property
    def faltan(self) -> list[str]:
        return [n for n, v in (("NIF", self.nif), ("provincia", self.provincia), ("clave", self.clave), ("subclave", self.subclave)) if not v]


@dataclass
class Calculo190:
    anio: int
    perceptores: list[Perceptor190] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def percepciones(self) -> Decimal:
        return sum((p.percepcion for p in self.perceptores), CERO)

    @property
    def retenciones(self) -> Decimal:
        return sum((p.retencion for p in self.perceptores), CERO)


def calcular_190(sesion: Session, ejercicio: Ejercicio) -> Calculo190:
    """Perceptores del año con lo percibido y retenido; los datos fiscales que falten en su ficha se señalan en `faltan`."""
    c = Calculo190(ejercicio.anio)
    por_cuenta: dict[str, Perceptor190] = {}
    for trimestre in (1, 2, 3, 4):
        t = calcular_111(sesion, ejercicio, trimestre)
        c.avisos += [a for a in t.avisos if "sin NIF" not in a]
        for l in t.lineas:
            p = por_cuenta.get(l.cuenta)
            if p is None:
                cuenta = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == l.cuenta))
                ficha = sesion.scalar(select(Tercero).where(Tercero.cuenta_id == cuenta.id)) if cuenta else None
                p = por_cuenta[l.cuenta] = Perceptor190(l.cuenta, l.perceptor, l.nif, getattr(ficha, "provincia_190", None), getattr(ficha, "clave_190", None), getattr(ficha, "subclave_190", None))
            p.percepcion += l.percepcion
            p.retencion += l.retencion
            p.asientos.append(l.asiento)
    c.perceptores = sorted(por_cuenta.values(), key=lambda p: (p.nif or "", p.cuenta))
    for p in c.perceptores:
        if p.faltan:
            c.avisos.append(f"{p.nombre}: faltan en su ficha {', '.join(p.faltan)} (hacen falta para el 190)")
    return c
