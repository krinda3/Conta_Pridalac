"""Plazos de presentación y de domiciliación de los modelos de la AEAT que usa el programa (303, 111, 115, 202, 390, 190 y 347).

Los plazos de **presentación** se calculan con sus reglas fijas: el último día del plazo, y si es inhábil (sábado, domingo; los festivos locales no se conocen) el primer día hábil siguiente.
Los de **domiciliación** son los que publica la AEAT («Calendario del contribuyente 2026 · Plazos de presentación de autoliquidaciones con domiciliación bancaria»); donde no están
publicados (otros años) se estiman con su regla general —entre el fin de la domiciliación y el del plazo tiene que haber «un mínimo de tres días hábiles o cinco naturales»— y quedan marcados
como no confirmados hasta cargar la tabla oficial. Esta tabla se revisa cada año con el calendario nuevo (sale en diciembre).

Calendario 2026 contrastado con la sede (28/10/2026): 303 trimestral hasta el 20 de abril, julio y octubre y el 30 de enero; 111 y 115 trimestral hasta el 20 de abril, julio, octubre y **20 de enero**;
202 hasta el 20 de abril, octubre y diciembre; 390 hasta el 30 de enero; 190 y 180 hasta el 31 de enero (2 de febrero en 2026 por ser sábado); 347 hasta el último día de febrero (2 de marzo en 2026).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

# (modelo, ejercicio del periodo, periodo) → último día para presentar domiciliando el pago, según la AEAT
PUBLICADAS = {
    **{("303", 2025, 4): date(2026, 1, 27), ("303", 2026, 1): date(2026, 4, 15), ("303", 2026, 2): date(2026, 7, 15), ("303", 2026, 3): date(2026, 10, 15)},
    **{(m, a, p): d for m in ("111", "115") for (a, p), d in {(2025, 4): date(2026, 1, 15), (2026, 1): date(2026, 4, 15), (2026, 2): date(2026, 7, 15), (2026, 3): date(2026, 10, 15)}.items()},
    ("202", 2026, 1): date(2026, 4, 15), ("202", 2026, 2): date(2026, 10, 15), ("202", 2026, 3): date(2026, 12, 16),
}
DOMICILIACION_PUBLICADA = {(a, p): d for (m, a, p), d in PUBLICADAS.items() if m == "303"}  # sólo el 303 (lo usan las pruebas y el modelo 303)
MODELOS_TRIMESTRALES = {"303", "111", "115"}
MODELOS_ANUALES = {"390", "190", "180", "347"}  # periodo único («0A»): se declara el ejercicio anterior


@dataclass(frozen=True)
class Plazo:
    inicio: date
    fin: date  # último día para presentar
    fin_domiciliacion: date | None  # último día para presentar domiciliando el pago (None si el modelo no admite pago: 347)
    confirmado: bool  # la fecha de domiciliación es la publicada por la AEAT (no una estimación)


def _habil(dia: date) -> bool:
    return dia.weekday() < 5


def _siguiente_habil(dia: date) -> date:
    while not _habil(dia):
        dia += timedelta(days=1)
    return dia


def _fin_domiciliacion(fin: date) -> date:
    """El último día hábil D con al menos tres días hábiles o cinco naturales hasta `fin` (D < fin)."""
    d = fin - timedelta(days=1)
    while True:
        habiles = sum(_habil(fin - timedelta(days=i)) for i in range(0, (fin - d).days))
        if habiles >= 3 or (fin - d).days >= 5:
            while not _habil(d):  # el último día para domiciliar es siempre un día hábil
                d -= timedelta(days=1)
            return d
        d -= timedelta(days=1)


def _nominal(modelo: str, anio: int, periodo: int) -> tuple[date, date]:
    """(inicio, último día nominal del plazo) antes de trasladarlo por inhábil."""
    if modelo in MODELOS_TRIMESTRALES:
        if periodo not in (1, 2, 3, 4):
            raise ValueError(f"El {modelo} es trimestral: periodo 1 a 4")
        if periodo == 4:
            ultimo = 30 if modelo == "303" else 20  # el 303 del 4T es hasta el 30 de enero; el 111 y el 115, hasta el 20
            return date(anio + 1, 1, 1), date(anio + 1, 1, ultimo)
        mes = 3 * periodo + 1
        return date(anio, mes, 1), date(anio, mes, 20)
    if modelo == "202":
        if periodo not in (1, 2, 3):
            raise ValueError("El 202 tiene tres pagos fraccionados: periodo 1 a 3")
        mes = {1: 4, 2: 10, 3: 12}[periodo]
        return date(anio, mes, 1), date(anio, mes, 20)
    if modelo in ("390", "190", "180"):
        return date(anio + 1, 1, 1), date(anio + 1, 1, 30 if modelo == "390" else 31)
    if modelo == "347":
        return date(anio + 1, 2, 1), date(anio + 1, 2, calendar.monthrange(anio + 1, 2)[1])
    if modelo == "LIBROS":  # legalización de libros en el Registro Mercantil: cuatro meses desde el cierre del ejercicio
        return date(anio + 1, 1, 1), date(anio + 1, 4, 30)
    if modelo == "DEPOSITO":  # depósito de cuentas: un mes desde la aprobación, que es antes del 30 de junio
        return date(anio + 1, 1, 1), date(anio + 1, 7, 30)
    raise ValueError(f"No hay plazos cargados para el modelo {modelo}")


def plazo(modelo: str, anio: int, periodo: int = 0) -> Plazo:
    """Plazo del modelo para el periodo `periodo` del ejercicio `anio` (en los anuales, `anio` es el ejercicio que se declara y el periodo se ignora)."""
    inicio, nominal = _nominal(modelo, anio, periodo)
    fin = _siguiente_habil(nominal)
    if modelo in ("347", "LIBROS", "DEPOSITO"):
        return Plazo(inicio, fin, None, True)  # sin ingreso que domiciliar
    publicada = PUBLICADAS.get((modelo, anio, periodo))
    estimada = _fin_domiciliacion(nominal) + (fin - nominal)  # si el plazo se prorroga, la domiciliación se amplía los mismos días
    return Plazo(inicio, fin, publicada or estimada, publicada is not None)


def un_mes_despues(dia: date) -> date:
    """El mismo día del mes siguiente (o el último de ese mes si no existe)."""
    mes, anio = dia.month % 12 + 1, dia.year + (dia.month == 12)
    return date(anio, mes, min(dia.day, calendar.monthrange(anio, mes)[1]))


def fin_del_deposito(anio: int, aprobacion: date | None) -> date:
    """Último día para depositar las cuentas del ejercicio `anio`: un mes desde que la junta las aprobó; si aún no se sabe, el plazo general (30 de julio, o el primer día hábil siguiente)."""
    return _siguiente_habil(un_mes_despues(aprobacion)) if aprobacion else plazo("DEPOSITO", anio).fin


def plazo_303(anio: int, periodo: int) -> Plazo:
    return plazo("303", anio, periodo)
