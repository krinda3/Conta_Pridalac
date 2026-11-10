"""Facturación por cliente o proveedor en un rango de fechas: lo facturado a cada cliente (facturas emitidas) y por cada proveedor (facturas recibidas).

Se suma por la **fecha contable** de la factura, la misma que decide el trimestre del 303 y del 347. «Total con IVA» es base más IVA y recargo (el importe que se declara en el 347, sin descontar retenciones);
«neto» es el total de la factura (con sus retenciones y demás ajustes). Los terceros se agrupan por su ficha; las facturas sin ficha se agrupan por la cuenta contable del tercero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio, Factura

CERO = Decimal("0.00")


@dataclass
class LineaFacturada:
    factura_id: int
    documento: str  # «R 63»
    fecha_contable: date
    fecha_factura: date | None
    numero_factura: str | None
    base: Decimal
    iva: Decimal  # cuota de IVA y recargo
    total_con_iva: Decimal
    neto: Decimal


@dataclass
class FacturadoA:
    clave: str  # identifica al tercero dentro del listado (sentido + ficha o cuenta)
    sentido: str  # E clientes · R proveedores
    nombre: str
    nif: str | None
    facturas: list[LineaFacturada] = field(default_factory=list)

    @property
    def base(self) -> Decimal:
        return sum((l.base for l in self.facturas), CERO)

    @property
    def iva(self) -> Decimal:
        return sum((l.iva for l in self.facturas), CERO)

    @property
    def total_con_iva(self) -> Decimal:
        return sum((l.total_con_iva for l in self.facturas), CERO)

    @property
    def neto(self) -> Decimal:
        return sum((l.neto for l in self.facturas), CERO)


def facturacion_por_tercero(
    sesion: Session, ejercicio: Ejercicio, *, desde: date | None = None, hasta: date | None = None, sentido: str | None = None, texto: str | None = None, minimo: Decimal | None = None,
) -> list[FacturadoA]:
    """Un renglón por tercero (y sentido), ordenado por importe de mayor a menor. `texto` filtra por nombre o NIF; `minimo`, por el total con IVA (se queda quien lo supera)."""
    consulta = select(Factura).where(Factura.ejercicio_id == ejercicio.id).order_by(Factura.fecha_contable, Factura.numero)
    if desde is not None:
        consulta = consulta.where(Factura.fecha_contable >= desde)
    if hasta is not None:
        consulta = consulta.where(Factura.fecha_contable <= hasta)
    if sentido in ("E", "R"):
        consulta = consulta.where(Factura.sentido == sentido)
    grupos: dict[str, FacturadoA] = {}
    for f in sesion.scalars(consulta):
        t = f.tercero
        if t is not None:
            clave, nombre, nif = f"{f.sentido}:t{t.id}", t.nombre, t.nif
        elif f.cuenta_tercero is not None:
            clave, nombre, nif = f"{f.sentido}:c{f.cuenta_tercero_id}", f.cuenta_tercero.nombre, None
        else:
            clave, nombre, nif = f"{f.sentido}:-", "(sin tercero)", None
        base = sum((i.base for i in f.ivas), CERO)
        iva = sum((i.cuota_iva + i.cuota_recargo for i in f.ivas), CERO)
        g = grupos.setdefault(clave, FacturadoA(clave, f.sentido, nombre, nif))
        g.facturas.append(LineaFacturada(f.id, f"{f.sentido} {f.numero}", f.fecha_contable, f.fecha_factura, f.numero_factura, base, iva, base + iva, f.total))
    resultado = list(grupos.values())
    if texto and texto.strip():
        buscado = texto.strip().lower()
        resultado = [g for g in resultado if buscado in g.nombre.lower() or buscado in (g.nif or "").lower()]
    if minimo is not None:
        resultado = [g for g in resultado if g.total_con_iva > minimo]
    return sorted(resultado, key=lambda g: (-g.total_con_iva, g.nombre))
