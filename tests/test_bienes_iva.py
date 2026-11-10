"""Libro de bienes de inversión (IVA) y regularización anual de deducciones."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa
from conta_pridalac.servicios.bienes import alta_bien, dar_de_baja
from conta_pridalac.servicios.bienes_iva import (
    es_bien_de_inversion,
    libro_bienes_inversion,
    plazo_de_regularizacion,
    regularizacion_del_anio,
)
from conta_pridalac.servicios.tablas_informes import tabla_libro_bienes_inversion

D = Decimal


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ejs = {a: Ejercicio(anio=a, fecha_inicio=date(a, 1, 1), fecha_fin=date(a, 12, 31), empresa=e) for a in (2026, 2027, 2028, 2031)}
    sesion.add_all([e, *ejs.values()])
    sesion.flush()
    for c in ("21300000", "28130000", "21100000", "28110000", "68100000"):
        sesion.add(Cuenta(empresa_id=e.id, codigo=c, nombre=c))
    sesion.flush()
    return e, ejs


def _maquina(sesion, e, **kw):
    datos = dict(descripcion="MAQUINA", precio_compra=D("12000"), fecha_funcionamiento=date(2026, 3, 1), cuenta_inmovilizado="21300000",
                 cuenta_amortizacion="28130000", cuenta_dotacion="68100000", periodos_vida=10, iva_soportado=D("2520"))
    datos.update(kw)
    return alta_bien(sesion, e.id, **datos)


def test_umbral_y_plazos(sesion, emp):
    e, _ = emp
    assert es_bien_de_inversion(_maquina(sesion, e))
    assert not es_bien_de_inversion(_maquina(sesion, e, precio_compra=D("3005.06"), iva_soportado=D("631.06")))
    assert not es_bien_de_inversion(_maquina(sesion, e, iva_soportado=D("0")))
    assert plazo_de_regularizacion(_maquina(sesion, e)) == 5
    edificio = _maquina(sesion, e, cuenta_inmovilizado="21100000", cuenta_amortizacion="28110000")
    assert plazo_de_regularizacion(edificio) == 10


def test_con_deduccion_total_no_hay_regularizacion(sesion, emp):
    e, ejs = emp
    b = _maquina(sesion, e)
    assert all(regularizacion_del_anio(b, a) == 0 for a in range(2025, 2040))
    assert libro_bienes_inversion(sesion, ejs[2027])[0].regularizacion == 0


def test_regularizacion_por_cambio_de_prorrata(sesion, emp):
    e, ejs = emp
    b = _maquina(sesion, e)
    deduccion = {2026: D("100"), 2027: D("80"), 2028: D("100"), 2030: D("50"), 2031: D("50")}
    assert regularizacion_del_anio(b, 2026, deduccion) == 0  # el primer año no se regulariza
    assert regularizacion_del_anio(b, 2027, deduccion) == D("-100.80")  # 2520 / 5 × (80 − 100) %
    assert regularizacion_del_anio(b, 2028, deduccion) == 0
    assert regularizacion_del_anio(b, 2030, deduccion) == D("-252.00")  # último año del periodo (2026 + 4)
    assert regularizacion_del_anio(b, 2031, deduccion) == 0  # ya fuera del periodo
    linea = libro_bienes_inversion(sesion, ejs[2027], deduccion)[0]
    assert (linea.primer_anio, linea.ultimo_anio, linea.plazo) == (2026, 2030, 5)
    assert (linea.pct_deducible_inicial, linea.pct_deducible_ejercicio, linea.regularizacion) == (D("100"), D("80"), D("-100.80"))


def test_el_primer_anio_fija_el_porcentaje_de_referencia(sesion, emp):
    e, _ = emp
    b = _maquina(sesion, e)
    # se empezó deduciendo el 60 % y en 2027 se pasa al 100 %: se deduce más
    assert regularizacion_del_anio(b, 2027, {2026: D("60"), 2027: D("100")}) == D("201.60")


def test_avisos_de_datos_dudosos_y_baja(sesion, emp):
    e, ejs = emp
    _maquina(sesion, e, iva_soportado=D("361217"))
    linea = libro_bienes_inversion(sesion, ejs[2027])[0]
    assert "supera el precio de compra" in linea.avisos[0]
    b = _maquina(sesion, e, descripcion="VENDIDA")
    dar_de_baja(sesion, b, date(2027, 6, 30), "VENTA")
    vendida = next(l for l in libro_bienes_inversion(sesion, ejs[2027]) if l.bien.descripcion == "VENDIDA")
    assert "art. 110" in vendida.avisos[0]


def test_el_libro_no_incluye_bienes_posteriores_y_se_exporta(sesion, emp, tmp_path):
    from conta_pridalac.exportacion import a_excel, a_pdf

    e, ejs = emp
    _maquina(sesion, e, fecha_funcionamiento=date(2028, 5, 1))
    assert libro_bienes_inversion(sesion, ejs[2027]) == []
    lineas = libro_bienes_inversion(sesion, ejs[2028])
    t = tabla_libro_bienes_inversion(lineas, ejs[2028])
    assert t.totales[6] == D("2520.00")
    a_excel(t, tmp_path / "bi.xlsx")
    a_pdf(t, tmp_path / "bi.pdf")


@pytest.mark.datos_reales
def test_libro_con_los_bienes_reales_de_2021(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    lineas = libro_bienes_inversion(sesion, ej)
    # con deducción del 100 % nada se regulariza
    assert all(l.regularizacion == 0 for l in lineas)
    if carga_mgd.clave == "empresa_a":
        assert any("supera el precio de compra" in a for l in lineas for a in l.avisos)  # el Mazda trae un IVA absurdo (361.217 €)
