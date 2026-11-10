"""Plazos del 303: presentación y domiciliación."""
from datetime import date

import pytest

from conta_pridalac.servicios.plazos import DOMICILIACION_PUBLICADA, _fin_domiciliacion, plazo_303


@pytest.mark.parametrize(
    "anio, periodo, fin, domiciliacion",
    [(2026, 1, date(2026, 4, 20), date(2026, 4, 15)), (2026, 2, date(2026, 7, 20), date(2026, 7, 15)), (2026, 3, date(2026, 10, 20), date(2026, 10, 15)), (2025, 4, date(2026, 1, 30), date(2026, 1, 27))],
)
def test_plazos_publicados_por_la_aeat(anio, periodo, fin, domiciliacion):
    p = plazo_303(anio, periodo)
    assert (p.fin, p.fin_domiciliacion, p.confirmado) == (fin, domiciliacion, True)


def test_la_regla_de_estimacion_reproduce_todos_los_plazos_publicados():
    for (anio, periodo), publicada in DOMICILIACION_PUBLICADA.items():
        fin = plazo_303(anio, periodo).fin
        assert _fin_domiciliacion(fin) == publicada


def test_periodo_sin_plazo_publicado_es_una_estimacion_y_el_fin_inhabil_se_prorroga():
    p = plazo_303(2026, 4)  # el 30 de enero de 2027 es sábado
    assert p.inicio == date(2027, 1, 1) and p.fin == date(2027, 2, 1) and not p.confirmado
    assert plazo_303(2027, 1).fin == date(2027, 4, 20) and plazo_303(2027, 1).fin_domiciliacion < plazo_303(2027, 1).fin


def test_periodo_no_valido():
    with pytest.raises(ValueError):
        plazo_303(2026, 5)


# ---------------------------------------------------------------------------------------------- calendario 2026 contrastado con la sede (28/10/2026)

from conta_pridalac.servicios.plazos import plazo  # noqa: E402


@pytest.mark.parametrize(
    "modelo, anio, periodo, fin, domiciliacion",
    [
        ("111", 2025, 4, date(2026, 1, 20), date(2026, 1, 15)),  # el 111 del 4T es hasta el 20 de enero, no el 30 como el 303
        ("111", 2026, 1, date(2026, 4, 20), date(2026, 4, 15)),
        ("111", 2026, 3, date(2026, 10, 20), date(2026, 10, 15)),
        ("115", 2025, 4, date(2026, 1, 20), date(2026, 1, 15)),
        ("303", 2025, 4, date(2026, 1, 30), date(2026, 1, 27)),
        ("202", 2026, 1, date(2026, 4, 20), date(2026, 4, 15)),
        ("202", 2026, 2, date(2026, 10, 20), date(2026, 10, 15)),
        ("202", 2026, 3, date(2026, 12, 21), date(2026, 12, 16)),  # el 20 de diciembre de 2026 es domingo
    ],
)
def test_plazos_publicados_de_otros_modelos(modelo, anio, periodo, fin, domiciliacion):
    p = plazo(modelo, anio, periodo)
    assert (p.fin, p.fin_domiciliacion, p.confirmado) == (fin, domiciliacion, True)


@pytest.mark.parametrize(
    "modelo, anio, fin",
    [("390", 2025, date(2026, 1, 30)), ("190", 2025, date(2026, 2, 2)), ("347", 2025, date(2026, 3, 2)), ("347", 2026, date(2027, 3, 1)), ("190", 2026, date(2027, 2, 1))],
)
def test_plazos_de_los_modelos_anuales(modelo, anio, fin):
    assert plazo(modelo, anio).fin == fin  # los fines de semana pasan al lunes


def test_el_347_no_tiene_domiciliacion_y_el_111_del_4t_de_2026_es_estimado():
    assert plazo("347", 2025).fin_domiciliacion is None
    p = plazo("111", 2026, 4)
    assert p.fin == date(2027, 1, 20) and p.fin_domiciliacion == date(2027, 1, 15) and not p.confirmado


def test_modelos_o_periodos_no_cargados():
    with pytest.raises(ValueError):
        plazo("999", 2026, 1)
    with pytest.raises(ValueError):
        plazo("111", 2026, 5)
    with pytest.raises(ValueError):
        plazo("202", 2026, 4)
