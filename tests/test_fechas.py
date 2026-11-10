from datetime import date
from types import SimpleNamespace

import pytest

from conta_pridalac.domain.errores import EjercicioCerrado, FechaFueraDePeriodo, FechaInvalida
from conta_pridalac.domain.fechas import introducir_fecha, parsear_fecha, validar_en_ejercicio

REF = date(2026, 5, 17)


def ejercicio(anio=2026, cerrado=False):
    return SimpleNamespace(anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, 31), cerrado=cerrado)


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("150826", date(2026, 8, 15)),  # DDMMAA
        ("15082026", date(2026, 8, 15)),  # DDMMAAAA
        ("1508", date(2026, 8, 15)),  # DDMM: año de la referencia
        ("15", date(2026, 5, 15)),  # día: mes y año de la referencia
        ("5", date(2026, 5, 5)),
        ("15/8", date(2026, 8, 15)),
        ("15/08/26", date(2026, 8, 15)),
        ("15-8-2026", date(2026, 8, 15)),
        ("15.08.26", date(2026, 8, 15)),
        (" 29/02/24 ", date(2024, 2, 29)),
        ("010121", date(2021, 1, 1)),
    ],
)
def test_formatos_admitidos(texto, esperado):
    assert parsear_fecha(texto, referencia=REF) == esperado


def test_hoy():
    assert parsear_fecha("hoy") == date.today()


@pytest.mark.parametrize("texto", ["", "  ", "310226", "29/02/25", "32/1", "1/13", "abc", "1234567", "15/08/2026/1", "00/01/26"])
def test_fechas_invalidas(texto):
    with pytest.raises(FechaInvalida):
        parsear_fecha(texto, referencia=REF)


def test_el_mensaje_dice_que_no_existe_en_el_calendario():
    with pytest.raises(FechaInvalida, match="no existe en el calendario"):
        parsear_fecha("310226")


def test_dentro_del_ejercicio():
    assert validar_en_ejercicio(date(2026, 12, 31), ejercicio()) == date(2026, 12, 31)


@pytest.mark.parametrize("fecha", [date(2025, 12, 31), date(2027, 1, 1)])
def test_fuera_del_ejercicio(fecha):
    with pytest.raises(FechaFueraDePeriodo):
        validar_en_ejercicio(fecha, ejercicio())


def test_ejercicio_cerrado_no_admite_movimientos_salvo_que_se_pida():
    with pytest.raises(EjercicioCerrado):
        validar_en_ejercicio(date(2026, 3, 1), ejercicio(cerrado=True))
    assert validar_en_ejercicio(date(2026, 3, 1), ejercicio(cerrado=True), permitir_cerrado=True)


def test_introducir_fecha_no_cambia_de_ejercicio_en_silencio():
    """Trabajando en 2021, `3112` es el 31/12/2021 aunque el reloj diga otro año; un año explícito distinto se rechaza."""
    e = ejercicio(2021)
    assert introducir_fecha("3112", e) == date(2021, 12, 31)
    assert introducir_fecha("010121", e) == date(2021, 1, 1)
    with pytest.raises(FechaFueraDePeriodo):
        introducir_fecha("010122", e)
