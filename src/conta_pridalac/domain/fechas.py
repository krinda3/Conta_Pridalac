"""Entrada y validación de fechas (Hito 1, punto 12 del plan).

Se admite `DDMMAA`, `DDMMAAAA`, `DDMM`, `D/M`, `D/M/AA`, `D-M-AAAA`, `D.M.AA`, solo el día (`15`) y `hoy`.
La fecha se valida **al introducirla** contra el calendario, el ejercicio y su estado; nunca se cambia el año en silencio.
"""
from __future__ import annotations

import re
from datetime import date

from conta_pridalac.domain.errores import EjercicioCerrado, FechaFueraDePeriodo, FechaInvalida

_SEPARADORES = re.compile(r"^(\d{1,2})[/\-. ](\d{1,2})(?:[/\-. ](\d{2}|\d{4}))?$")
_SOLO_DIGITOS = re.compile(r"^\d+$")


def parsear_fecha(texto: str, *, referencia: date | None = None) -> date:
    """Convierte lo que teclea el usuario en una `date`.

    `referencia` aporta el mes y el año que faltan (día solo, `DDMM`, `D/M`): normalmente la fecha de hoy o la del
    documento anterior. Los años de dos cifras se interpretan como 20AA.
    """
    referencia = referencia or date.today()
    t = (texto or "").strip().lower()
    if not t:
        raise FechaInvalida("La fecha está vacía")
    if t in ("hoy", "h"):
        return date.today()

    if _SOLO_DIGITOS.match(t):
        if len(t) <= 2:
            dia, mes, anio = int(t), referencia.month, referencia.year
        elif len(t) == 4:
            dia, mes, anio = int(t[:2]), int(t[2:]), referencia.year
        elif len(t) == 6:
            dia, mes, anio = int(t[:2]), int(t[2:4]), 2000 + int(t[4:])
        elif len(t) == 8:
            dia, mes, anio = int(t[:2]), int(t[2:4]), int(t[4:])
        else:
            raise FechaInvalida(f"«{texto}» no es una fecha: use DDMMAA, DDMMAAAA o D/M/AA")
    else:
        m = _SEPARADORES.match(t)
        if not m:
            raise FechaInvalida(f"«{texto}» no es una fecha: use DDMMAA, DDMMAAAA o D/M/AA")
        dia, mes = int(m.group(1)), int(m.group(2))
        a = m.group(3)
        anio = referencia.year if a is None else (2000 + int(a) if len(a) == 2 else int(a))

    try:
        return date(anio, mes, dia)
    except ValueError:
        raise FechaInvalida(f"«{texto}» no existe en el calendario ({dia:02d}/{mes:02d}/{anio})") from None


def validar_en_ejercicio(fecha: date, ejercicio, *, permitir_cerrado: bool = False) -> date:
    """Comprueba que la fecha está dentro del ejercicio y que éste admite movimientos. Devuelve la fecha."""
    if not (ejercicio.fecha_inicio <= fecha <= ejercicio.fecha_fin):
        raise FechaFueraDePeriodo(
            f"La fecha {fecha:%d/%m/%Y} está fuera del ejercicio {ejercicio.anio} "
            f"({ejercicio.fecha_inicio:%d/%m/%Y} – {ejercicio.fecha_fin:%d/%m/%Y})"
        )
    if ejercicio.cerrado and not permitir_cerrado:
        raise EjercicioCerrado(f"El ejercicio {ejercicio.anio} está cerrado; reábralo para grabar movimientos")
    return fecha


def introducir_fecha(texto: str, ejercicio, *, referencia: date | None = None) -> date:
    """Atajo para las pantallas: interpreta el texto y lo valida contra el ejercicio de trabajo.

    Por defecto, las fechas incompletas toman el año del ejercicio (no el del reloj) y, si hoy cae dentro del ejercicio,
    el mes de hoy; en un ejercicio distinto del actual, el primer mes. Nunca se salta de ejercicio en silencio.
    """
    if referencia is None:
        hoy = date.today()
        referencia = hoy if ejercicio.fecha_inicio <= hoy <= ejercicio.fecha_fin else ejercicio.fecha_inicio
    return validar_en_ejercicio(parsear_fecha(texto, referencia=referencia), ejercicio)
