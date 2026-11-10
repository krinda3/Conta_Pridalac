"""Facturas recibidas cuyo asiento lleva la retención de IRPF (cuenta 4751) pero cuya ficha no tiene el ajuste de retención.

En las facturas que vienen de la contabilidad anterior, la retención está en el asiento (la línea de la 4751 y el total ya neto) pero la factura no la anota como ajuste, así que el asiento que
se regeneraría de la factura sale distinto y la auditoría da error. Esto añade a la factura el ajuste que falta (cuenta de la retención, importe con signo, «contra el gasto») sin tocar ningún
asiento, ni importe, ni fecha, y sólo si con él el asiento regenerado queda **idéntico** al que hay; si no, no hace nada con esa factura. Vale para ejercicios cerrados: no cambia ninguna cifra.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.auditoria import _lineas
from conta_pridalac.db.modelos import Asiento, Ejercicio, Factura, FacturaAjuste
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.facturas import asientos_de_factura

RETENCION = "4751"


@dataclass
class Reparacion:
    anio: int
    factura: str  # «R 127»
    numero_factura: str
    cuenta: str
    importe: Decimal
    resultado: str  # «añadido» o el motivo por el que no se toca


def reparar(sesion: Session, ejercicio: Ejercicio) -> list[Reparacion]:
    """Añade el ajuste de retención que falta a las facturas recibidas del ejercicio que lo necesitan. No hace commit."""
    hechas: list[Reparacion] = []
    for f in sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == "R").order_by(Factura.numero)):
        try:
            esperados = asientos_de_factura(f)
        except ErrorContable:
            continue
        if len(esperados) != 1:
            continue
        real = sesion.scalar(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id, Asiento.tipo == 2, Asiento.numero == f.numero, Asiento.sub == 0))
        if real is None or _lineas(real) == esperados[0]:
            continue
        retenciones = [(ap.cuenta, importe) for ap in real.apuntes for importe in [_lineas(real).get(ap.cuenta.codigo, Decimal("0"))] if ap.cuenta.codigo.startswith(RETENCION) and esperados[0].get(ap.cuenta.codigo) is None]
        vistas = set()
        retenciones = [(c, i) for c, i in retenciones if not (c.codigo in vistas or vistas.add(c.codigo))]
        ref = f"R {f.numero}"
        if len(retenciones) != 1:
            hechas.append(Reparacion(ejercicio.anio, ref, f.numero_factura or "", "", Decimal("0"), "no es sólo la retención lo que difiere"))
            continue
        cuenta, importe = retenciones[0]
        ajuste = FacturaAjuste(factura_id=f.id, orden=len(f.ajustes), cuenta_id=cuenta.id, importe=importe, contra="G")
        f.ajustes.append(ajuste)
        sesion.flush()
        if asientos_de_factura(f) == [_lineas(real)]:
            hechas.append(Reparacion(ejercicio.anio, ref, f.numero_factura or "", cuenta.codigo, importe, "añadido"))
        else:
            f.ajustes.remove(ajuste)
            sesion.delete(ajuste)
            sesion.flush()
            hechas.append(Reparacion(ejercicio.anio, ref, f.numero_factura or "", cuenta.codigo, importe, "con el ajuste el asiento sigue sin coincidir"))
    return hechas
