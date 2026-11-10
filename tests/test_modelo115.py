"""Cálculo del 115 desde los libros: retenciones de alquileres (621 + 4751), arrendadores y base; y que el 111 no las cuenta."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.modelo111 import calcular_111
from conta_pridalac.servicios.modelo115 import calcular_115

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Asociación S.L.", nif="G12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000001", "CASERO UNO"),
                           ("41000002", "CASERO DOS"), ("41000132", "AGRICULTOR"), ("57200001", "BANCO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    for codigo, nif in (("41000001", "12345678Z"), ("41000002", None)):
        cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()
        sesion.add(Tercero(empresa_id=e.id, clase="P", nombre=cuenta.nombre, nif=nif, cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def asiento(sesion, ej, fecha, lineas, numero, *, tipo=2, subtipo=None):
    return grabar_asiento(sesion, ej, tipo=tipo, numero=numero, sub=0, fecha=fecha, concepto="prueba", subtipo=subtipo, lineas=[LineaAsiento(c, D(i)) for c, i in lineas])


def alquiler(sesion, ej, fecha, cuenta, renta, iva, retencion, numero):
    """El arrendador se abona por renta + IVA − retención; la retención se abona a la 4751."""
    total = D(renta) + D(iva) - D(retencion)
    return asiento(sesion, ej, fecha, [("62100000", renta), ("47200000", iva), ("47510000", f"-{retencion}"), (cuenta, f"-{total}")], numero)


def test_un_trimestre_sin_alquileres_es_sin_actividad(sesion, ej):
    c = calcular_115(sesion, ej, 1)
    assert c.casillas == {3: D("0.00"), 5: D("0.00")} and c.lineas == [] and c.avisos == []


def test_la_base_es_la_renta_sin_iva_y_la_retencion_el_19(sesion, ej):
    alquiler(sesion, ej, date(2026, 11, 2), "41000001", "1000.00", "210.00", "190.00", 1)
    alquiler(sesion, ej, date(2026, 12, 2), "41000002", "500.00", "105.00", "95.00", 2)
    c = calcular_115(sesion, ej, 4)
    assert (c[1], c[2], c[3], c[5]) == (D("2"), D("1500.00"), D("285.00"), D("285.00"))
    assert [(l.perceptor, l.base, l.retencion, l.porcentaje) for l in c.lineas] == [("CASERO UNO", D("1000.00"), D("190.00"), D("19.00")), ("CASERO DOS", D("500.00"), D("95.00"), D("19.00"))]
    assert c.avisos == ["Hay arrendadores sin NIF en su ficha: hará falta para el modelo 180 (resumen anual)"]
    assert calcular_115(sesion, ej, 3).casillas == {3: D("0.00"), 5: D("0.00")}


def test_el_mismo_arrendador_cuenta_una_vez(sesion, ej):
    alquiler(sesion, ej, date(2026, 10, 2), "41000001", "1000.00", "0.00", "190.00", 1)
    alquiler(sesion, ej, date(2026, 11, 2), "41000001", "1000.00", "0.00", "190.00", 2)
    c = calcular_115(sesion, ej, 4)
    assert (c[1], c[2], c[3]) == (D("1"), D("2000.00"), D("380.00"))


def test_el_111_no_cuenta_las_retenciones_de_alquileres_y_el_115_no_cuenta_las_del_111(sesion, ej):
    alquiler(sesion, ej, date(2026, 11, 2), "41000001", "1000.00", "210.00", "190.00", 1)
    asiento(sesion, ej, date(2026, 11, 5), [("62300000", "100.00"), ("47510000", "-2.00"), ("41000132", "-98.00")], 2)  # compra a un agricultor con el 2 %
    assert calcular_111(sesion, ej, 4)[28] == D("2.00")
    assert calcular_115(sesion, ej, 4)[3] == D("190.00")


def test_el_pago_a_hacienda_y_la_apertura_no_cuentan(sesion, ej):
    alquiler(sesion, ej, date(2026, 11, 2), "41000001", "1000.00", "0.00", "190.00", 1)
    asiento(sesion, ej, date(2026, 12, 20), [("47510000", "190.00"), ("57200001", "-190.00")], 5, tipo=3)
    asiento(sesion, ej, date(2026, 10, 1), [("47510000", "-50.00"), ("62100000", "50.00")], 6, subtipo="A")
    c = calcular_115(sesion, ej, 4)
    assert c[3] == D("190.00") and len(c.lineas) == 1


def test_avisa_de_un_alquiler_sin_retencion_y_de_un_porcentaje_raro(sesion, ej):
    asiento(sesion, ej, date(2026, 11, 2), [("62100000", "300.00"), ("41000001", "-300.00")], 1)
    alquiler(sesion, ej, date(2026, 12, 2), "41000001", "1000.00", "0.00", "100.00", 2)
    c = calcular_115(sesion, ej, 4)
    assert any("sin retención" in a for a in c.avisos) and any("10.00 %" in a and "19 %" in a for a in c.avisos)
    assert c[3] == D("100.00")


def test_complementaria_resta_lo_ingresado_en_la_anterior(sesion, ej):
    alquiler(sesion, ej, date(2026, 11, 2), "41000001", "1000.00", "0.00", "190.00", 1)
    c = calcular_115(sesion, ej, 4, anterior_5=D("100.00"))
    assert (c[3], c[4], c[5]) == (D("190.00"), D("100.00"), D("90.00"))
