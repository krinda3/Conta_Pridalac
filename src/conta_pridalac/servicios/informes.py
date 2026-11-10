"""Informes contables: libro Diario, Mayor, balance de sumas y saldos y libros de registro de IVA.

Sólo leen: ninguna función modifica la base de datos. Los importes de saldo se calculan en Python (restar en SQL
perdería el tipo `Dinero`).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Factura
from conta_pridalac.domain.pgc import nombre_pgc

CERO = Decimal("0.00")


def _orden_diario():
    return (Asiento.fecha, func.coalesce(Asiento.numero_diario, 0), Asiento.tipo, Asiento.numero, Asiento.sub)


# ------------------------------------------------------------------------------------------------ libro Diario


@dataclass
class LibroDiario:
    asientos: list[Asiento]
    total_debe: Decimal
    total_haber: Decimal


def libro_diario(
    sesion: Session, ejercicio: Ejercicio, *, desde: date | None = None, hasta: date | None = None, subtipos: tuple[str, ...] | None = None
) -> LibroDiario:
    """Asientos del ejercicio por orden de fecha y de número, con sus apuntes (`subtipos`: M, A, P, R, Z… para filtrar)."""
    consulta = select(Asiento).where(Asiento.ejercicio_id == ejercicio.id).options(selectinload(Asiento.apuntes).selectinload(Apunte.cuenta))
    if desde:
        consulta = consulta.where(Asiento.fecha >= desde)
    if hasta:
        consulta = consulta.where(Asiento.fecha <= hasta)
    if subtipos:
        consulta = consulta.where(func.coalesce(Asiento.subtipo, "").in_(subtipos))
    asientos = list(sesion.scalars(consulta.order_by(*_orden_diario())))
    debe = sum((ap.debe for a in asientos for ap in a.apuntes), CERO)
    haber = sum((ap.haber for a in asientos for ap in a.apuntes), CERO)
    return LibroDiario(asientos, debe, haber)


# ------------------------------------------------------------------------------------------------ Mayor


@dataclass
class LineaMayor:
    fecha: date
    asiento: str  # identificador "tipo.número[/sub]"
    concepto: str
    debe: Decimal
    haber: Decimal
    saldo: Decimal  # acumulado (debe − haber), incluido el saldo anterior


@dataclass
class Mayor:
    cuenta: str
    nombre: str
    saldo_anterior: Decimal
    lineas: list[LineaMayor] = field(default_factory=list)

    @property
    def total_debe(self) -> Decimal:
        return sum((l.debe for l in self.lineas), CERO)

    @property
    def total_haber(self) -> Decimal:
        return sum((l.haber for l in self.lineas), CERO)

    @property
    def saldo_final(self) -> Decimal:
        return self.saldo_anterior + self.total_debe - self.total_haber


def mayor(
    sesion: Session, ejercicio: Ejercicio, codigo: str, *, desde: date | None = None, hasta: date | None = None
) -> Mayor:
    """Mayor de una cuenta (8 dígitos) o de un grupo si `codigo` es más corto (todas las cuentas que empiezan por él)."""
    nombre = sesion.scalar(select(Cuenta.nombre).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == codigo)) or ""
    base = (
        select(Apunte, Asiento)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .where(Asiento.ejercicio_id == ejercicio.id, Cuenta.codigo.like(f"{codigo}%"))
    )
    anterior = CERO
    if desde:
        for ap, _ in sesion.execute(base.where(Asiento.fecha < desde)):
            anterior += ap.debe - ap.haber
        base = base.where(Asiento.fecha >= desde)
    if hasta:
        base = base.where(Asiento.fecha <= hasta)
    resultado = Mayor(codigo, nombre, anterior)
    saldo = anterior
    for ap, a in sesion.execute(base.order_by(*_orden_diario(), Apunte.orden)):
        saldo += ap.debe - ap.haber
        resultado.lineas.append(LineaMayor(a.fecha, a.identificador, ap.concepto or a.concepto, ap.debe, ap.haber, saldo))
    return resultado


def mayor_general(
    sesion: Session, ejercicio: Ejercicio, prefijo: str = "", *, desde: date | None = None, hasta: date | None = None
) -> list[Mayor]:
    """El Mayor de todas las cuentas con movimientos (o con saldo anterior) que empiezan por `prefijo`, ordenadas por código.

    Cada cuenta lleva su propio saldo acumulado. Una sola consulta: no se pregunta cuenta por cuenta.
    """
    consulta = (
        select(Apunte, Asiento, Cuenta)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .where(Asiento.ejercicio_id == ejercicio.id, Cuenta.codigo.like(f"{prefijo}%"))
        .order_by(Cuenta.codigo, *_orden_diario(), Apunte.orden)
    )
    cuentas: dict[str, Mayor] = {}
    saldos: dict[str, Decimal] = {}
    for ap, a, cuenta in sesion.execute(consulta):
        m = cuentas.get(cuenta.codigo)
        if m is None:
            m = cuentas[cuenta.codigo] = Mayor(cuenta.codigo, cuenta.nombre, CERO)
            saldos[cuenta.codigo] = CERO
        if desde and a.fecha < desde:
            m.saldo_anterior += ap.debe - ap.haber
            saldos[cuenta.codigo] += ap.debe - ap.haber
            continue
        if hasta and a.fecha > hasta:
            continue
        saldos[cuenta.codigo] += ap.debe - ap.haber
        m.lineas.append(LineaMayor(a.fecha, a.identificador, ap.concepto or a.concepto, ap.debe, ap.haber, saldos[cuenta.codigo]))
    return [m for m in cuentas.values() if m.lineas or m.saldo_anterior != 0]


# ------------------------------------------------------------------------------------------------ balance de sumas y saldos


@dataclass
class FilaBalance:
    cuenta: str
    nombre: str
    debe: Decimal
    haber: Decimal

    @property
    def saldo_deudor(self) -> Decimal:
        return self.debe - self.haber if self.debe > self.haber else CERO

    @property
    def saldo_acreedor(self) -> Decimal:
        return self.haber - self.debe if self.haber > self.debe else CERO


@dataclass
class Balance:
    filas: list[FilaBalance]

    @property
    def total_debe(self) -> Decimal:
        return sum((f.debe for f in self.filas), CERO)

    @property
    def total_haber(self) -> Decimal:
        return sum((f.haber for f in self.filas), CERO)


NIVEL_SUBCUENTA = 12  # «todos los dígitos»: agrupar a más dígitos de los que tiene cualquier subcuenta las deja tal cual


def balance_sumas_y_saldos(
    sesion: Session, ejercicio: Ejercicio, *, nivel: int = NIVEL_SUBCUENTA, desde: date | None = None, hasta: date | None = None,
    excluir_subtipos: tuple[str, ...] = (), solo_subtipos: tuple[str, ...] | None = None,
) -> Balance:
    """Sumas y saldos por cuenta agrupadas a `nivel` dígitos (`NIVEL_SUBCUENTA` o más que sus dígitos = subcuentas, 3 = cuentas, 2 = subgrupos, 1 = grupos).

    Incluye apertura, regularización y cierre salvo que se pasen en `excluir_subtipos` (p. ej. ("R", "Z") para ver
    el balance previo al cierre).
    """
    if not 1 <= nivel <= NIVEL_SUBCUENTA:
        raise ValueError(f"El nivel debe estar entre 1 y {NIVEL_SUBCUENTA} dígitos")
    consulta = (
        select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Apunte, Apunte.cuenta_id == Cuenta.id)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ejercicio.id)
        .group_by(Cuenta.codigo)
    )
    if desde:
        consulta = consulta.where(Asiento.fecha >= desde)
    if hasta:
        consulta = consulta.where(Asiento.fecha <= hasta)
    if excluir_subtipos:
        consulta = consulta.where(func.coalesce(Asiento.subtipo, "").not_in(excluir_subtipos))
    if solo_subtipos:
        consulta = consulta.where(func.coalesce(Asiento.subtipo, "").in_(solo_subtipos))
    sumas: dict[str, list[Decimal]] = defaultdict(lambda: [CERO, CERO])
    for codigo, debe, haber in sesion.execute(consulta):
        s = sumas[codigo[:nivel]]
        s[0] += debe or CERO
        s[1] += haber or CERO
    nombres = {
        c: n
        for c, n in sesion.execute(
            select(Cuenta.codigo, Cuenta.nombre).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo.in_(list(sumas)))
        )
    }
    return Balance([FilaBalance(c, nombres.get(c) or nombre_pgc(c, ejercicio.empresa.tipo_plan), d, h) for c, (d, h) in sorted(sumas.items())])


# ------------------------------------------------------------------------------------------------ libros de IVA


@dataclass
class LineaLibroIva:
    fecha: date
    numero: int
    numero_factura: str
    tercero: str
    nif: str
    base: Decimal
    pct_iva: Decimal
    cuota: Decimal
    cuota_recargo: Decimal
    deducible: bool
    bien_inversion: bool
    factura_id: int = 0


@dataclass
class LibroIva:
    sentido: str
    lineas: list[LineaLibroIva]

    @property
    def total_base(self) -> Decimal:
        return sum((l.base for l in self.lineas), CERO)

    @property
    def total_cuota(self) -> Decimal:
        return sum((l.cuota + l.cuota_recargo for l in self.lineas), CERO)

    @property
    def total_cuota_deducible(self) -> Decimal:
        return sum((l.cuota + l.cuota_recargo for l in self.lineas if l.deducible), CERO)

    def por_tipo(self) -> dict[Decimal, tuple[Decimal, Decimal]]:
        """{% de IVA: (base, cuota)}."""
        r: dict[Decimal, list[Decimal]] = defaultdict(lambda: [CERO, CERO])
        for l in self.lineas:
            r[l.pct_iva][0] += l.base
            r[l.pct_iva][1] += l.cuota + l.cuota_recargo
        return {k: (v[0], v[1]) for k, v in sorted(r.items())}


def libro_iva(
    sesion: Session, ejercicio: Ejercicio, sentido: str, *, desde: date | None = None, hasta: date | None = None
) -> LibroIva:
    """Libro registro de IVA de facturas emitidas (`E`) o recibidas (`R`): una línea por tipo de IVA de cada factura."""
    if sentido not in ("E", "R"):
        raise ValueError("El sentido debe ser 'E' (emitidas) o 'R' (recibidas)")
    consulta = (
        select(Factura)
        .where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == sentido)
        .options(selectinload(Factura.ivas), selectinload(Factura.tercero))
    )
    if desde:
        consulta = consulta.where(Factura.fecha_contable >= desde)
    if hasta:
        consulta = consulta.where(Factura.fecha_contable <= hasta)
    lineas = []
    for f in sesion.scalars(consulta.order_by(Factura.fecha_contable, Factura.numero)):
        for iva in f.ivas:
            lineas.append(
                LineaLibroIva(
                    f.fecha_contable, f.numero, f.numero_factura or "", f.tercero.nombre if f.tercero else "",
                    (f.tercero.nif or "") if f.tercero else "", iva.base, iva.pct_iva, iva.cuota_iva, iva.cuota_recargo,
                    iva.deducible, iva.bien_inversion, f.id,
                )
            )
    return LibroIva(sentido, lineas)
