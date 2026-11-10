"""Cuadro de amortización lineal de Gestión MGD (`vELbiCuadro.Generar`, E_Edicion.prg:26126).

Es la regla de MGD, que **no** coincide con la del programa anterior (ver docs/00_plan_de_trabajo.md §8): MGD prorratea el primer
periodo por días entre los días reales del periodo y redondea con "mitad hacia arriba"; el programa anterior da otros céntimos.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PeriodoAmortizacion:
    ejercicio: int
    desde: date
    hasta: date
    previsto: Decimal


def suma_meses(d: date, meses: int) -> date:
    """Suma `meses` a una fecha; si el día no existe en el mes de destino, el último día del mes."""
    total = d.year * 12 + (d.month - 1) + meses
    anio, mes = divmod(total, 12)
    mes += 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def ultimo_dia_mes(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def primer_dia_mes(d: date) -> date:
    return d.replace(day=1)


def generar_cuadro(
    fecha_inicio: date,
    coste: Decimal,
    residual: Decimal = Decimal("0"),
    periodos: int = 0,
    meses_periodo: int = 12,
    coeficiente_pct: Decimal = Decimal("0"),
    fecha_baja: date | None = None,
    decimales: int = 2,
) -> list[PeriodoAmortizacion]:
    """Cuadro de amortización previsto. `periodos` = vida útil en periodos; si se da `coeficiente_pct`, manda el porcentaje."""
    importe = Decimal(coste) - Decimal(residual)
    if importe <= Decimal("0.001"):
        raise ValueError("El importe neto a amortizar ha de ser mayor que cero")
    if periodos <= 0 and coeficiente_pct <= 0:
        raise ValueError("Falta el porcentaje a amortizar por periodo o el número de periodos")
    meses = meses_periodo if meses_periodo >= 1 else 12

    # Porcentaje en centésimas de punto (MGD: Integer(coef*100)), como entero
    porc = int(Decimal(coeficiente_pct) * 100)
    if porc <= 0:
        porc = int(Decimal(10000) / periodos)
    elif porc > 10000:
        raise ValueError("El porcentaje a amortizar por periodo es como máximo 100%")
    if periodos <= 0:
        periodos = int(Decimal(10000) / porc)

    baja_teorica = suma_meses(fecha_inicio, meses * periodos) - timedelta(days=1)
    baja = baja_teorica if fecha_baja is None or fecha_baja > baja_teorica else fecha_baja

    # Fechas de los periodos
    tramos: list[tuple[date, date]] = []
    desde = fecha_inicio
    n = ((desde.month - 1) // meses) * meses + meses
    hasta = min(ultimo_dia_mes(desde.year, n), baja)
    tramos.append((desde, hasta))
    desde = hasta + timedelta(days=1)
    for _ in range(2, periodos * 2 + 1):
        if hasta == baja:
            break
        hasta = min(suma_meses(desde, meses) - timedelta(days=1), baja)
        tramos.append((desde, hasta))
        if hasta == baja:
            break
        desde = hasta + timedelta(days=1)

    # Importes
    por_periodo = importe * porc / 10000
    cuantum = Decimal(1).scaleb(-decimales)
    cuadro: list[PeriodoAmortizacion] = []
    for desde, hasta in tramos:
        inicio_teorico = primer_dia_mes(suma_meses(hasta, -meses + 1))
        if desde == inicio_teorico:
            previsto = por_periodo
        else:
            previsto = Decimal((hasta - desde).days + 1) * por_periodo / Decimal((hasta - inicio_teorico).days + 1)
        cuadro.append(PeriodoAmortizacion(desde.year, desde, hasta, previsto.quantize(cuantum, rounding=ROUND_HALF_UP)))

    if baja == baja_teorica:  # el último periodo absorbe el resto
        total = sum((p.previsto for p in cuadro), Decimal("0"))
        ultimo = cuadro[-1]
        cuadro[-1] = PeriodoAmortizacion(ultimo.ejercicio, ultimo.desde, ultimo.hasta, ultimo.previsto + (importe - total))
    return cuadro
