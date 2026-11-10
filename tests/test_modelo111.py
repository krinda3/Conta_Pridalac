"""Cálculo del 111 desde los libros: retenciones de la 4751 por trimestre, perceptores y percepciones."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.modelo111 import calcular_111

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000132", "AGRICULTOR UNO"), ("41000133", "AGRICULTOR DOS"),
                           ("57200001", "BANCO"), ("62900000", "OTROS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    for codigo, nif in (("41000132", "12345678Z"), ("41000133", None)):
        cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()
        sesion.add(Tercero(empresa_id=e.id, clase="P", nombre=cuenta.nombre, nif=nif, cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def asiento(sesion, ej, fecha, lineas, *, tipo=4, numero=None, subtipo=None):
    return grabar_asiento(sesion, ej, tipo=tipo, numero=numero or len(sesion.scalars(select(Cuenta)).all()) * 100 + int(fecha.strftime("%m%d")), sub=0, fecha=fecha, concepto="prueba",
                          subtipo=subtipo, lineas=[LineaAsiento(c, D(i)) for c, i in lineas])


def compra_a_agricultor(sesion, ej, fecha, cuenta, base, iva, retencion, numero):
    """Como se contabiliza en la empresa: el proveedor se abona por el total y se le carga la retención."""
    total = D(base) + D(iva)
    return asiento(sesion, ej, fecha, [("62300000", base), ("47200000", iva), ("47510000", f"-{retencion}"), (cuenta, retencion), (cuenta, f"-{total}")], tipo=2, numero=numero)


def test_un_trimestre_sin_retenciones_es_sin_actividad(sesion, ej):
    c = calcular_111(sesion, ej, 1)
    assert c.casillas == {28: D("0.00"), 30: D("0.00")} and c.lineas == [] and c.avisos == []


def test_las_retenciones_del_trimestre_van_a_actividades_economicas(sesion, ej):
    compra_a_agricultor(sesion, ej, date(2026, 11, 2), "41000132", "865.22", "103.83", "19.38", 78)
    compra_a_agricultor(sesion, ej, date(2026, 12, 10), "41000133", "576.00", "69.12", "12.90", 94)
    c = calcular_111(sesion, ej, 4)
    assert (c[7], c[8], c[9], c[28], c[30]) == (D("2"), D("1614.17"), D("32.28"), D("32.28"), D("32.28"))  # dos perceptores; 969,05 + 645,12 de percepciones
    assert [(l.perceptor, l.percepcion, l.retencion, l.porcentaje) for l in c.lineas] == [("AGRICULTOR UNO", D("969.05"), D("19.38"), D("2.00")), ("AGRICULTOR DOS", D("645.12"), D("12.90"), D("2.00"))]
    assert c.avisos == ["Hay perceptores sin NIF en su ficha: hará falta para el modelo 190 (resumen anual)"]
    assert calcular_111(sesion, ej, 3).casillas == {28: D("0.00"), 30: D("0.00")}  # en otro trimestre no cuentan


def test_un_mismo_perceptor_cuenta_una_vez(sesion, ej):
    compra_a_agricultor(sesion, ej, date(2026, 11, 2), "41000132", "100.00", "12.00", "2.24", 1)
    compra_a_agricultor(sesion, ej, date(2026, 11, 20), "41000132", "200.00", "24.00", "4.48", 2)
    c = calcular_111(sesion, ej, 4)
    assert (c[7], c[8], c[9]) == (D("1"), D("336.00"), D("6.72"))


def test_el_pago_a_hacienda_la_apertura_y_el_cierre_no_cuentan_como_retencion(sesion, ej):
    compra_a_agricultor(sesion, ej, date(2026, 11, 2), "41000132", "100.00", "12.00", "2.24", 1)
    asiento(sesion, ej, date(2026, 12, 20), [("47510000", "2.24"), ("57200001", "-2.24")], tipo=3, numero=5)  # el ingreso: carga la 4751
    asiento(sesion, ej, date(2026, 10, 1), [("47510000", "-50.00"), ("62900000", "50.00")], numero=6, subtipo="A")  # apertura con saldo de la 4751
    asiento(sesion, ej, date(2026, 12, 31), [("47510000", "-9.00"), ("62900000", "9.00")], numero=7, subtipo="Z")
    c = calcular_111(sesion, ej, 4)
    assert (c[9], c[28]) == (D("2.24"), D("2.24")) and len(c.lineas) == 1


def test_avisa_si_la_retencion_no_es_la_habitual(sesion, ej):
    compra_a_agricultor(sesion, ej, date(2026, 11, 2), "41000132", "1000.00", "0.00", "150.00", 1)  # un 15 %: parece un profesional
    assert any("15.00 %" in a and "2 %" in a for a in calcular_111(sesion, ej, 4).avisos)


def test_una_retencion_sin_acreedor_no_se_inventa_perceptor(sesion, ej):
    asiento(sesion, ej, date(2026, 11, 2), [("62900000", "10.00"), ("47510000", "-10.00")], numero=1)
    c = calcular_111(sesion, ej, 4)
    assert c[28] == D("0.00") and any("no tiene ninguna cuenta de acreedor" in a for a in c.avisos)


def test_complementaria_resta_lo_ingresado_en_la_anterior(sesion, ej):
    compra_a_agricultor(sesion, ej, date(2026, 11, 2), "41000132", "100.00", "12.00", "2.24", 1)
    c = calcular_111(sesion, ej, 4, anterior_30=D("1.00"))
    assert (c[28], c[29], c[30]) == (D("2.24"), D("-1.00"), D("1.24"))
