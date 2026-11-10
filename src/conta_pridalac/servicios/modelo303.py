"""Modelo 303 (autoliquidación trimestral del IVA, régimen general): cálculo de las casillas desde los libros.

Reglas, deducidas y verificadas con las 42 declaraciones presentadas desde 2021 (ver `docs/00_plan_de_trabajo.md`, Hito 3, y `tools/comparar_303.py`):

- **Periodo** = trimestre de la **fecha contable** de la factura (la fecha de introducción).
- **Devengado**: facturas emitidas, por tipo: 4 % (casillas 1, 2, 3), 10 % (4, 5, 6) y 21 % (7, 8, 9); casilla 27 = suma de las cuotas. Desde 2026 las líneas al 0 %
  (los alquileres exentos de Empresa B) van a la base de la casilla 150, como se presentaron los trimestres de 2026.
- **Deducible, operaciones interiores corrientes** (casillas 28 base y 29 cuota): facturas recibidas con IVA deducible, de cualquier tipo. Las líneas
  al 0 % no van a ninguna casilla y las de bienes de inversión van a la 30 y 31. Una línea negativa (factura rectificativa) **resta** de la 28 y 29, salvo que rectifique
  deducciones de periodos anteriores: entonces va a las casillas 40 y 41. Eso no se sabe sólo con los importes, así que lo decide quien graba la rectificativa
  (parámetro `rectifican`; más adelante, una marca en la factura).
- **44**: regularización por prorrata. No se calcula: se introduce a mano (es lo que se hace hoy con la hoja de prorrata).
- **45** total a deducir = 29 + 31 + 41 + 44 · **46** resultado = 27 − 45 · **64** = 46 · **65** = 100 % · **66** = 64 × 65 % · 69 y 71 = resultado de la liquidación.
- **Compensación** (siempre se presenta con compensación): se lleva una **bolsa** de cuotas a compensar dentro del año, con lo ya **presentado** en los
  trimestres anteriores. En el 1T al 3T, un resultado negativo se presenta tal cual y entra en la bolsa; uno positivo se compensa con ella hasta donde llegue.
  En el 4T el resultado de la liquidación (69 y 71) es el del trimestre menos toda la bolsa. La casilla 87 es la bolsa pendiente al terminar el periodo sin contar
  el resultado negativo del propio periodo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import PRESENTADA, DeclaracionPresentada, Ejercicio, Factura, FacturaIva, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable

CERO = Decimal("0.00")
CIEN = Decimal("100")
# tipo de IVA → (casilla de la base, casilla del tipo, casilla de la cuota)
CASILLAS_DEVENGADO = {Decimal("4"): (1, 2, 3), Decimal("10"): (4, 5, 6), Decimal("21"): (7, 8, 9)}
TIPOS_FIJOS = {2: Decimal("4"), 5: Decimal("10"), 8: Decimal("21"), 20: Decimal("1.4"), 23: Decimal("5.2")}  # los que el formulario trae impresos


@dataclass
class Linea303:
    """Una línea de IVA que entra en una casilla (para ver de dónde sale cada importe)."""

    casilla: int
    sentido: str
    numero: int
    numero_factura: str | None
    base: Decimal
    cuota: Decimal
    factura_id: int = 0


@dataclass
class Calculo303:
    anio: int
    periodo: int
    desde: date
    hasta: date
    casillas: dict[int, Decimal] = field(default_factory=dict)
    lineas: list[Linea303] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def __getitem__(self, casilla: int) -> Decimal:
        return self.casillas.get(casilla, CERO)


def periodo_de_fechas(anio: int, periodo: int) -> tuple[date, date]:
    if periodo not in (1, 2, 3, 4):
        raise ErrorContable("El periodo del 303 es un trimestre: 1 a 4")
    fin_mes = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[periodo]
    return date(anio, 3 * periodo - 2, 1), date(anio, *fin_mes)


def _dec(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bolsa_de_periodos_anteriores(sesion: Session, empresa_id: int, anio: int, periodo: int) -> Decimal:
    """Cuotas a compensar acumuladas al empezar el periodo, según lo **presentado** en el trimestre anterior del año (0 en el 1T)."""
    if periodo == 1:
        return CERO
    nuestra = sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == anio, PresentacionAeat.periodo == f"{periodo - 1}T",
               PresentacionAeat.estado == PRESENTADA)
        .order_by(PresentacionAeat.id.desc())
    ).first()
    if nuestra is not None:  # lo presentado con este programa manda sobre lo importado del programa anterior
        c = json.loads(nuestra.casillas or "{}")
        return Decimal(str(c.get("87", 0))) + max(CERO, -Decimal(str(c.get("46", 0))))
    previa = sesion.scalars(
        select(DeclaracionPresentada).where(
            DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == "303", DeclaracionPresentada.anio == anio,
            DeclaracionPresentada.periodo == periodo - 1, DeclaracionPresentada.tipo == 1,
        )
    ).first()
    if previa is None:
        return CERO
    return previa.a_compensar + max(CERO, -previa.resultado_liquidacion)


def compensar(resultado: Decimal, periodo: int, bolsa: Decimal) -> tuple[Decimal, Decimal]:
    """Aplica la bolsa de compensación. Devuelve (resultado de la liquidación, casilla 87)."""
    if periodo == 4:
        if resultado < 0:
            return resultado - bolsa, CERO
        aplicada = min(bolsa, resultado)
        return resultado - aplicada, bolsa - aplicada
    if resultado < 0:
        return resultado, bolsa
    aplicada = min(bolsa, resultado)
    return resultado - aplicada, bolsa - aplicada


def calcular_303(
    sesion: Session, ejercicio: Ejercicio, periodo: int, *, regularizacion_prorrata: Decimal | None = None, bolsa: Decimal | None = None,
    facturas: set[int] | None = None, rectifican: set[int] | None = None, anterior_69: Decimal | None = None,
) -> Calculo303:
    """Casillas del 303 del trimestre `periodo` desde las facturas con fecha contable en él.

    `regularizacion_prorrata`: casilla 44 (con signo; negativa si se deduce menos). `bolsa`: cuotas a compensar al empezar el periodo; si no se da, sale de lo presentado.
    `facturas`: ids de las facturas a incluir en lugar de las del trimestre (sirve para reproducir una declaración ya presentada cuyas facturas no coinciden con las fechas).
    `rectifican`: ids de las rectificativas que rectifican deducciones de periodos anteriores (casillas 40 y 41).
    `anterior_69`: resultado (casilla 69) de la autoliquidación que se rectifica; con él, esta es una **rectificativa**: la casilla 70 lleva el resultado a ingresar de la anterior (esté ingresado o no), la 71 es
    69 − 70 y, si sale negativa por haberse ingresado de más, la 111 recoge esa parte. No se piden devoluciones, así que la 109 queda en blanco.
    """
    desde, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    c = Calculo303(ejercicio.anio, periodo, desde, hasta)
    devengado: dict[Decimal, list[Decimal]] = {t: [CERO, CERO] for t in CASILLAS_DEVENGADO}
    consulta = select(FacturaIva, Factura).join(Factura, Factura.id == FacturaIva.factura_id).order_by(Factura.sentido, Factura.numero, FacturaIva.id)
    if facturas is None:
        consulta = consulta.where(Factura.ejercicio_id == ejercicio.id, Factura.fecha_contable >= desde, Factura.fecha_contable <= hasta)
    else:
        consulta = consulta.where(Factura.id.in_(facturas))
    rectifican = rectifican or set()
    base_cero = CERO
    ded = {28: CERO, 29: CERO, 30: CERO, 31: CERO, 40: CERO, 41: CERO}

    def sumar(casilla_base: int, casilla_cuota: int, f: Factura, i: FacturaIva) -> None:
        ded[casilla_base] += i.base
        ded[casilla_cuota] += i.cuota_iva
        c.lineas.append(Linea303(casilla_cuota, f.sentido, f.numero, f.numero_factura, i.base, i.cuota_iva, f.id))

    for i, f in sesion.execute(consulta):
        if i.pct_iva == 0 and i.cuota_iva == 0:
            if f.sentido == "E" and ejercicio.anio >= 2026 and i.base:  # el formulario de 2026 tiene la fila del 0 %: así se presentaron los alquileres exentos de Empresa B
                base_cero += i.base
                c.lineas.append(Linea303(152, f.sentido, f.numero, f.numero_factura, i.base, i.cuota_iva, f.id))
            continue  # exento o no sujeto: no va a ninguna otra casilla del régimen general
        if f.sentido == "E":
            tipo = Decimal(int(i.pct_iva)) if i.pct_iva == i.pct_iva.to_integral_value() else None
            casillas = CASILLAS_DEVENGADO.get(tipo)
            if casillas is None:
                c.avisos.append(f"Emitida {f.numero}: el tipo {i.pct_iva} % no tiene casilla en el régimen general del 303")
                continue
            devengado[tipo][0] += i.base
            devengado[tipo][1] += i.cuota_iva
            c.lineas.append(Linea303(casillas[2], f.sentido, f.numero, f.numero_factura, i.base, i.cuota_iva, f.id))
        elif i.deducible:
            if (i.cuota_iva < 0 or i.base < 0) and f.id in rectifican:
                sumar(40, 41, f, i)
            elif i.bien_inversion:
                sumar(30, 31, f, i)
            else:
                sumar(28, 29, f, i)
    cas: dict[int, Decimal] = {}
    for tipo, (cb, ct, cq) in CASILLAS_DEVENGADO.items():
        base, cuota = devengado[tipo]
        if base or cuota:
            cas[cb], cas[cq] = _dec(base), _dec(cuota)
    if base_cero:
        cas[150] = _dec(base_cero)
    cas[27] = sum((_dec(devengado[t][1]) for t in devengado), CERO)
    for k, v in ded.items():
        if v:
            cas[k] = _dec(v)
    cas[44] = _dec(regularizacion_prorrata) if regularizacion_prorrata else CERO
    cas[45] = _dec(cas.get(29, CERO) + cas.get(31, CERO) + cas.get(41, CERO) + cas[44])
    cas[46] = _dec(cas[27] - cas[45])
    cas[64], cas[65] = cas[46], CIEN
    cas[66] = _dec(cas[64] * cas[65] / CIEN)
    bolsa_inicial = bolsa_de_periodos_anteriores(sesion, ejercicio.empresa_id, ejercicio.anio, periodo) if bolsa is None else bolsa
    liquidacion, pendiente = compensar(cas[66], periodo, bolsa_inicial)
    cas[69] = cas[71] = liquidacion
    if anterior_69 is not None:
        cas[70] = max(anterior_69, CERO)
        cas[71] = liquidacion - cas[70]
        cas[111] = min(-cas[71], cas[70]) if cas[71] < 0 < cas[70] else CERO
    cas[110], cas[87] = bolsa_inicial, pendiente
    cas[78] = bolsa_inicial - pendiente  # 87 = 110 − 78
    c.casillas = {k: v for k, v in cas.items() if v != 0 or k in (27, 45, 46, 64, 65, 66, 69, 71)}
    return c
