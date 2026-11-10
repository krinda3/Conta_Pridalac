"""Liquidación del IVA: periodos, días de pago y reproducción de las liquidaciones reales de MGD 2021."""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.iva import calcular_liquidacion, fecha_de_pago, liquidar_iva, periodo_de, texto_periodo

D = Decimal


# --------------------------------------------------------------------------- periodos y fechas (puros)


@pytest.mark.parametrize(
    "hasta, periodicidad, esperado",
    [
        (date(2026, 3, 31), 4, (date(2026, 1, 1), date(2026, 3, 31))),
        (date(2026, 5, 10), 4, (date(2026, 4, 1), date(2026, 6, 30))),
        (date(2026, 12, 31), 4, (date(2026, 10, 1), date(2026, 12, 31))),
        (date(2026, 4, 30), 6, (date(2026, 3, 1), date(2026, 4, 30))),
        (date(2026, 2, 10), 12, (date(2026, 2, 1), date(2026, 2, 28))),
    ],
)
def test_periodo_de(hasta, periodicidad, esperado):
    assert periodo_de(hasta, periodicidad) == esperado


@pytest.mark.parametrize(
    "hasta, periodicidad, dias, esperado",
    [
        (date(2021, 6, 30), 4, None, date(2021, 7, 25)),  # el 25 del mes siguiente (valor por defecto de MGD)
        (date(2021, 9, 30), 4, None, date(2021, 10, 25)),
        (date(2021, 12, 31), 4, None, date(2022, 1, 25)),  # cruza de año
        (date(2021, 12, 31), 4, [20, 20, 20, 30], date(2022, 1, 30)),  # configurable por periodo
        (date(2021, 3, 31), 4, [20, 20, 20, 30], date(2021, 4, 20)),
        (date(2021, 1, 31), 12, None, date(2021, 2, 25)),
        (date(2021, 1, 31), 12, [31] * 12, date(2021, 2, 28)),  # día inexistente → fin de mes
    ],
)
def test_fecha_de_pago(hasta, periodicidad, dias, esperado):
    assert fecha_de_pago(hasta, periodicidad, dias) == esperado


def test_texto_del_periodo():
    assert texto_periodo(date(2021, 4, 1), date(2021, 6, 30), 4) == "REGUL. IVA 2 TRIM/2021"
    assert texto_periodo(date(2021, 3, 1), date(2021, 4, 30), 6) == "REGUL. IVA 2 BIMESTRE/2021"
    assert texto_periodo(date(2021, 2, 1), date(2021, 2, 28), 12) == "REGUL. IVA 02/2021"


# --------------------------------------------------------------------------- caso sintético


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    from conta_pridalac.db.modelos import Parametro

    for codigo, nombre in (("47000000", "HP DEUDORA IVA"), ("47500000", "HP ACREEDORA IVA"), ("47200000", "IVA SOPORTADO"),
                           ("47700000", "IVA REPERCUTIDO"), ("62900000", "GASTOS"), ("41000001", "PROVEEDOR"), ("43000001", "CLIENTE"), ("70000000", "VENTAS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.add_all([Parametro(empresa_id=e.id, clave="IVA_DEBE", valor="47000000"), Parametro(empresa_id=e.id, clave="IVA_HABER", valor="47500000")])
    sesion.flush()
    return ej


def _gasto(sesion, ej, n, fecha, base, iva):
    grabar_asiento(sesion, ej, tipo=2, numero=n, fecha=fecha, lineas=[
        LineaAsiento("62900000", D(base)), LineaAsiento("47200000", D(iva)), LineaAsiento("41000001", -(D(base) + D(iva)))])


def _venta(sesion, ej, n, fecha, base, iva):
    grabar_asiento(sesion, ej, tipo=1, numero=n, fecha=fecha, lineas=[
        LineaAsiento("43000001", D(base) + D(iva)), LineaAsiento("70000000", -D(base)), LineaAsiento("47700000", -D(iva))])


def test_iva_a_pagar_crea_el_vencimiento_el_25_del_mes_siguiente(sesion, emp):
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")
    _gasto(sesion, emp, 1, date(2026, 5, 12), "300", "63")
    liq, res = liquidar_iva(sesion, emp, date(2026, 6, 30))
    assert (liq.soportado, liq.repercutido, liq.a_pagar, liq.a_compensar) == (D("63.00"), D("210.00"), D("147.00"), D("0.00"))
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in res.asiento.apuntes}
    assert lineas == {"47700000": D("210.00"), "47200000": D("-63.00"), "47500000": D("-147.00")}
    assert res.asiento.tipo == 9 and res.asiento.subtipo == "P" and res.asiento.concepto == "REGUL. IVA 2 TRIM/2026"
    (v,) = res.vencimientos
    assert (v.fecha, v.importe, v.apunte.cuenta.codigo) == (date(2026, 7, 25), D("-147.00"), "47500000")


def test_iva_a_favor_va_a_hacienda_deudora_y_no_crea_vencimiento(sesion, emp):
    _gasto(sesion, emp, 1, date(2026, 2, 10), "1000", "210")
    _venta(sesion, emp, 1, date(2026, 2, 11), "200", "42")
    liq, res = liquidar_iva(sesion, emp, date(2026, 3, 31))
    assert liq.a_compensar == D("168.00") and liq.a_pagar == 0
    assert {ap.cuenta.codigo: ap.debe - ap.haber for ap in res.asiento.apuntes} == {"47000000": D("168.00"), "47200000": D("-210.00"), "47700000": D("42.00")}
    assert res.vencimientos == []


def test_se_compensa_el_saldo_a_favor_del_periodo_anterior(sesion, emp):
    _gasto(sesion, emp, 1, date(2026, 2, 10), "1000", "210")  # 1T: a favor 210
    liquidar_iva(sesion, emp, date(2026, 3, 31))
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")  # 2T: 210 − 42 = 168 a pagar, se compensa todo con los 210 a favor
    _gasto(sesion, emp, 2, date(2026, 5, 12), "200", "42")
    liq, res = liquidar_iva(sesion, emp, date(2026, 6, 30))
    assert (liq.compensado, liq.a_pagar) == (D("168.00"), D("0.00"))
    assert {ap.cuenta.codigo: ap.debe - ap.haber for ap in res.asiento.apuntes} == {"47700000": D("210.00"), "47200000": D("-42.00"), "47000000": D("-168.00")}
    assert res.vencimientos == []


def test_compensacion_parcial_y_sin_compensar(sesion, emp):
    _gasto(sesion, emp, 1, date(2026, 2, 10), "100", "21")  # 1T: a favor 21
    liquidar_iva(sesion, emp, date(2026, 3, 31))
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")  # 2T: 210 a pagar, 21 compensados
    liq, res = liquidar_iva(sesion, emp, date(2026, 6, 30))
    assert (liq.compensado, liq.a_pagar) == (D("21.00"), D("189.00"))
    assert res.vencimientos[0].importe == D("-189.00")
    liq2, res2 = liquidar_iva(sesion, emp, date(2026, 6, 30), compensar=False)  # regrabar sin compensar
    assert (liq2.compensado, liq2.a_pagar) == (D("0.00"), D("210.00"))
    assert res2.asiento.id == res.asiento.id and res2.vencimientos[0].id == res.vencimientos[0].id  # mismo asiento y vencimiento
    assert res2.vencimientos[0].importe == D("-210.00")


def test_regrabar_es_idempotente_y_no_cuenta_su_propia_liquidacion(sesion, emp):
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")
    _, a = liquidar_iva(sesion, emp, date(2026, 6, 30))
    _, b = liquidar_iva(sesion, emp, date(2026, 6, 30))
    assert a.asiento.id == b.asiento.id
    assert len(sesion.scalars(select(Asiento).where(Asiento.subtipo == "P")).all()) == 1
    assert len(sesion.scalars(select(Vencimiento)).all()) == 1


def test_si_ya_no_hay_iva_a_pagar_se_quita_el_vencimiento(sesion, emp):
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")
    liquidar_iva(sesion, emp, date(2026, 6, 30))
    _gasto(sesion, emp, 1, date(2026, 5, 12), "2000", "420")  # ahora el soportado supera al repercutido
    _, res = liquidar_iva(sesion, emp, date(2026, 6, 30))
    assert res.vencimientos == [] and sesion.scalars(select(Vencimiento)).first() is None
    assert "47500000" not in {ap.cuenta.codigo for ap in res.asiento.apuntes}


def test_errores(sesion, emp):
    with pytest.raises(ErrorContable, match="No hay datos de IVA"):
        liquidar_iva(sesion, emp, date(2026, 6, 30))
    _venta(sesion, emp, 1, date(2026, 5, 10), "1000", "210")
    with pytest.raises(ErrorContable, match="acaba el 30/06/2026"):
        liquidar_iva(sesion, emp, date(2026, 5, 31))
    assert calcular_liquidacion(sesion, emp, date(2026, 7, 1), date(2026, 9, 30)).lineas == {}


# --------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_las_cuentas_de_iva_del_catalogo_incluyen_las_que_se_liquidan(sesion, carga_mgd):
    from conta_pridalac.db.modelos import TipoIva

    assert carga_mgd.tipos_iva == (21 if carga_mgd.clave == "empresa_a" else 14)
    cuentas = {c.codigo for t in sesion.scalars(select(TipoIva)) for c in (t.cuenta_iva, t.cuenta_recargo) if c}
    liquidadas = set()
    for a in sesion.scalars(select(Asiento).where(Asiento.subtipo == "P")):
        liquidadas |= {ap.cuenta.codigo for ap in a.apuntes if ap.cuenta.codigo.startswith(("472", "477"))}
    assert liquidadas and liquidadas <= cuentas


# Liquidaciones reales: (trimestre, ¿MGD las hizo con todas las facturas del trimestre ya contabilizadas?)
REALES = {
    "empresa_a": {3: True, 6: False},  # la del 2.º trimestre quedó 18,87 € por debajo del saldo
    "empresa_b": {3: False, 6: True, 9: True},  # la del 1.er trimestre quedó 337,90 € por debajo
}


@pytest.mark.datos_reales
def test_regenerar_las_liquidaciones_reales(sesion, carga_mgd):
    """Reproduce al céntimo las que se hicieron con el trimestre completo y detecta las que quedaron desactualizadas."""
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    reales = {}
    for a in sesion.scalars(select(Asiento).where(Asiento.subtipo == "P")):
        reales[a.fecha.month] = ({ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}, [(v.fecha, v.importe) for ap in a.apuntes for v in sesion.scalars(select(Vencimiento).where(Vencimiento.apunte_id == ap.id))])
    assert set(reales) == set(REALES[carga_mgd.clave])
    for mes, completa in REALES[carga_mgd.clave].items():
        hasta = date(2021, mes, 31 if mes in (3, 12) else 30)
        liq, res = liquidar_iva(sesion, ej, hasta)
        lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in res.asiento.apuntes}
        venc = [(v.fecha, v.importe) for v in res.vencimientos]
        if completa:
            assert (lineas, venc) == reales[mes], f"periodo que acaba en el mes {mes}"
        else:
            assert (lineas, venc) != reales[mes], f"el mes {mes} debería salir distinto (liquidación desactualizada)"
