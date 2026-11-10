"""Modelo 190: cálculo anual por perceptor (suma de los cuatro 111) y datos fiscales de la ficha."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.cuentas import modificar_tercero
from conta_pridalac.servicios.modelo190 import calcular_190
from test_modelo111 import compra_a_agricultor, ej  # noqa: F401  (el montaje de empresa y cuentas es el mismo)

D = Decimal


def test_sin_retenciones_no_hay_perceptores(sesion, ej):  # noqa: F811
    c = calcular_190(sesion, ej)
    assert c.perceptores == [] and c.percepciones == c.retenciones == D("0.00") and c.avisos == []


def test_suma_los_trimestres_por_perceptor_y_avisa_de_lo_que_falta(sesion, ej):  # noqa: F811
    compra_a_agricultor(sesion, ej, date(2026, 2, 2), "41000132", "100.00", "12.00", "2.24", 1)
    compra_a_agricultor(sesion, ej, date(2026, 11, 20), "41000132", "200.00", "24.00", "4.48", 2)
    compra_a_agricultor(sesion, ej, date(2026, 11, 22), "41000133", "576.00", "69.12", "12.90", 3)
    c = calcular_190(sesion, ej)
    assert [(p.nombre, p.nif, p.percepcion, p.retencion) for p in c.perceptores] == [
        ("AGRICULTOR DOS", None, D("645.12"), D("12.90")), ("AGRICULTOR UNO", "12345678Z", D("336.00"), D("6.72"))]
    assert c.percepciones == D("981.12") and c.retenciones == D("19.62")
    assert any("AGRICULTOR UNO: faltan en su ficha provincia, clave, subclave" in a for a in c.avisos)
    assert any("AGRICULTOR DOS: faltan en su ficha NIF, provincia, clave, subclave" in a for a in c.avisos)


def test_con_la_ficha_completa_no_hay_avisos(sesion, ej):  # noqa: F811
    compra_a_agricultor(sesion, ej, date(2026, 2, 2), "41000132", "100.00", "12.00", "2.24", 1)
    t = sesion.scalars(select(Tercero).where(Tercero.nif == "12345678Z")).one()
    modificar_tercero(sesion, t, "P", t.nombre, nif=t.nif, cuenta="41000132", provincia_190="13", clave_190="h", subclave_190="03")
    p = calcular_190(sesion, ej).perceptores[0]
    assert (p.provincia, p.clave, p.subclave, p.completo, p.faltan) == ("13", "H", "03", True, [])


@pytest.mark.parametrize("campo,valor,mensaje", [("provincia_190", "1", "dos cifras"), ("provincia_190", "ab", "dos cifras"), ("clave_190", "7", "una letra"), ("subclave_190", "3", "dos cifras")])
def test_la_ficha_valida_los_datos_del_190(sesion, ej, campo, valor, mensaje):  # noqa: F811
    t = sesion.scalars(select(Tercero)).first()
    with pytest.raises(ErrorContable, match=mensaje):
        modificar_tercero(sesion, t, "P", t.nombre, nif=t.nif, cuenta="41000132", **{campo: valor})
