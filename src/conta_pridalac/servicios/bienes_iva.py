"""Libro de bienes de inversión a efectos de IVA y regularización anual de las deducciones (arts. 107 a 110 LIVA).

MGD sólo guardaba la marca «bien de inversión» y el IVA soportado en la ficha (informativo: no generaba ningún asiento).
Aquí se obtiene el registro que pide el art. 40 del Reglamento del IVA y la regularización del ejercicio.

Reglas aplicadas:
- Es bien de inversión el de valor de adquisición **superior a 3.005,06 €**.
- Periodo de regularización: **5 años naturales** (el de puesta en funcionamiento y los 4 siguientes); **10** para terrenos y
  edificaciones (cuentas 210, 211, 220 y 221).
- Cada año posterior al primero: `IVA soportado / plazo × (% deducible del año − % deducible del primer año) / 100`
  (positivo = se deduce más; negativo = hay que devolver). Con deducción del 100 % todos los años la regularización es cero.
- La regularización por transmisión o baja anticipada (art. 110) no se calcula: se avisa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import BienInversion, Ejercicio

CERO = Decimal("0.00")
UMBRAL_BIEN_DE_INVERSION = Decimal("3005.06")
CUENTAS_DE_10_ANIOS = ("210", "211", "220", "221")


@dataclass
class LineaLibroBienes:
    bien: BienInversion
    base: Decimal
    iva_soportado: Decimal
    plazo: int
    primer_anio: int
    ultimo_anio: int
    pct_deducible_inicial: Decimal
    pct_deducible_ejercicio: Decimal
    regularizacion: Decimal
    avisos: list[str] = field(default_factory=list)


def plazo_de_regularizacion(bien: BienInversion) -> int:
    codigo = bien.cuenta_inmovilizado.codigo if bien.cuenta_inmovilizado else ""
    return 10 if codigo.startswith(CUENTAS_DE_10_ANIOS) else 5


def es_bien_de_inversion(bien: BienInversion) -> bool:
    return bien.precio_compra > UMBRAL_BIEN_DE_INVERSION and bien.iva_soportado > 0 and bien.fecha_funcionamiento is not None


def regularizacion_del_anio(bien: BienInversion, anio: int, deduccion: dict[int, Decimal] | None = None) -> Decimal:
    """Importe a regularizar en `anio` (0 fuera del periodo y en el primer año). `deduccion`: {año: % deducible definitivo}, 100 por defecto."""
    deduccion = deduccion or {}
    inicio = bien.fecha_funcionamiento.year
    plazo = plazo_de_regularizacion(bien)
    if not (inicio < anio < inicio + plazo):
        return CERO
    pct0, pct = Decimal(deduccion.get(inicio, 100)), Decimal(deduccion.get(anio, 100))
    return (bien.iva_soportado / plazo * (pct - pct0) / 100).quantize(CERO, rounding=ROUND_HALF_UP)


def libro_bienes_inversion(
    sesion: Session, ejercicio: Ejercicio, deduccion: dict[int, Decimal] | None = None
) -> list[LineaLibroBienes]:
    """Bienes de inversión de la empresa puestos en funcionamiento hasta el ejercicio, con su regularización del año."""
    deduccion = deduccion or {}
    lineas = []
    bienes = sesion.scalars(
        select(BienInversion).where(BienInversion.empresa_id == ejercicio.empresa_id).order_by(BienInversion.codigo)
    )
    for bien in bienes:
        if not es_bien_de_inversion(bien):
            continue
        inicio, plazo = bien.fecha_funcionamiento.year, plazo_de_regularizacion(bien)
        if inicio > ejercicio.anio:
            continue
        avisos = []
        if bien.iva_soportado > bien.precio_compra:
            avisos.append("El IVA soportado de la ficha supera el precio de compra: revise el dato")
        if bien.fecha_baja and inicio <= bien.fecha_baja.year < inicio + plazo:
            avisos.append(
                f"Baja el {bien.fecha_baja:%d/%m/%Y} dentro del periodo de regularización: la regularización por transmisión (art. 110) no se calcula"
            )
        lineas.append(
            LineaLibroBienes(
                bien, bien.precio_compra, bien.iva_soportado, plazo, inicio, inicio + plazo - 1,
                Decimal(deduccion.get(inicio, 100)), Decimal(deduccion.get(ejercicio.anio, 100)),
                regularizacion_del_anio(bien, ejercicio.anio, deduccion), avisos,
            )
        )
    return lineas


def en_periodo(linea: LineaLibroBienes, ejercicio: Ejercicio) -> bool:
    """¿Sigue abierto el periodo de regularización en este ejercicio?"""
    return linea.primer_anio <= ejercicio.anio <= linea.ultimo_anio
