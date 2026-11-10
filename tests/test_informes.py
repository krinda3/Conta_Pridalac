"""Libro Diario, Mayor, balance de sumas y saldos y libros de IVA."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Factura
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, libro_diario, libro_iva, mayor, mayor_general

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    x = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, x])
    sesion.flush()
    for codigo, nombre in (("10000000", "CAPITAL"), ("57200001", "BANCO"), ("57200002", "CAJA"), ("62900000", "GASTOS"), ("41000001", "PROVEEDOR")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    grabar_asiento(sesion, x, tipo=4, numero=1, fecha=date(2026, 1, 2), lineas=[LineaAsiento("57200001", D(1000)), LineaAsiento("10000000", D(-1000))])
    grabar_asiento(sesion, x, tipo=4, numero=2, fecha=date(2026, 2, 1), lineas=[LineaAsiento("62900000", D(200)), LineaAsiento("41000001", D(-200))])
    grabar_asiento(sesion, x, tipo=4, numero=3, fecha=date(2026, 3, 1), lineas=[LineaAsiento("41000001", D(200)), LineaAsiento("57200001", D(-200))])
    grabar_asiento(sesion, x, tipo=4, numero=4, fecha=date(2026, 3, 5), lineas=[LineaAsiento("57200002", D(50)), LineaAsiento("57200001", D(-50))])
    return x


def test_libro_diario_en_orden_y_cuadrado(sesion, ej):
    d = libro_diario(sesion, ej)
    assert [a.numero for a in d.asientos] == [1, 2, 3, 4]
    assert d.total_debe == d.total_haber == D("1450.00")
    marzo = libro_diario(sesion, ej, desde=date(2026, 3, 1), hasta=date(2026, 3, 31))
    assert [a.numero for a in marzo.asientos] == [3, 4]


def test_mayor_con_saldo_corrido(sesion, ej):
    m = mayor(sesion, ej, "57200001")
    assert [l.saldo for l in m.lineas] == [D("1000.00"), D("800.00"), D("750.00")]
    assert (m.saldo_anterior, m.total_debe, m.total_haber, m.saldo_final) == (D("0.00"), D("1000.00"), D("250.00"), D("750.00"))
    assert m.nombre == "BANCO"


def test_mayor_desde_una_fecha_arrastra_el_saldo_anterior(sesion, ej):
    m = mayor(sesion, ej, "57200001", desde=date(2026, 3, 1))
    assert m.saldo_anterior == D("1000.00")
    assert [l.saldo for l in m.lineas] == [D("800.00"), D("750.00")]
    assert m.saldo_final == D("750.00")


def test_mayor_de_un_grupo_junta_sus_cuentas(sesion, ej):
    m = mayor(sesion, ej, "572")
    assert m.saldo_final == D("800.00")  # banco 750 + caja 50


def test_mayor_general_de_todas_las_cuentas(sesion, ej):
    todas = mayor_general(sesion, ej)
    assert [m.cuenta for m in todas] == ["10000000", "41000001", "57200001", "57200002", "62900000"]
    banco = next(m for m in todas if m.cuenta == "57200001")
    assert [l.saldo for l in banco.lineas] == [D("1000.00"), D("800.00"), D("750.00")] and banco.saldo_final == D("750.00")
    assert [m.cuenta for m in mayor_general(sesion, ej, "572")] == ["57200001", "57200002"]
    # con «desde» cada cuenta arrastra lo anterior; una cuenta sin movimientos en el periodo pero con saldo anterior sigue apareciendo
    marzo = {m.cuenta: m for m in mayor_general(sesion, ej, desde=date(2026, 3, 1))}
    assert marzo["57200001"].saldo_anterior == D("1000.00") and [l.saldo for l in marzo["57200001"].lineas] == [D("800.00"), D("750.00")]
    assert marzo["10000000"].saldo_anterior == D("-1000.00") and marzo["10000000"].lineas == []
    assert "62900000" in marzo and marzo["62900000"].saldo_anterior == D("200.00")
    assert {m.cuenta for m in mayor_general(sesion, ej, hasta=date(2026, 1, 31))} == {"10000000", "57200001"}


def test_mayor_general_coincide_con_el_mayor_de_cada_cuenta(sesion, ej):
    for m in mayor_general(sesion, ej):
        solo = mayor(sesion, ej, m.cuenta)
        assert [(l.asiento, l.debe, l.haber, l.saldo) for l in m.lineas] == [(l.asiento, l.debe, l.haber, l.saldo) for l in solo.lineas]


def test_balance_por_subcuenta_y_por_grupo(sesion, ej):
    b = balance_sumas_y_saldos(sesion, ej)
    assert b.total_debe == b.total_haber == D("1450.00")
    banco = next(f for f in b.filas if f.cuenta == "57200001")
    assert (banco.debe, banco.haber, banco.saldo_deudor, banco.saldo_acreedor, banco.nombre) == (D("1000.00"), D("250.00"), D("750.00"), D("0.00"), "BANCO")
    por_grupo = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ej, nivel=3).filas}
    assert set(por_grupo) == {"100", "410", "572", "629"}
    assert por_grupo["572"].debe == D("1050.00") and por_grupo["572"].saldo_deudor == D("800.00")
    assert {f.cuenta for f in balance_sumas_y_saldos(sesion, ej, nivel=1).filas} == {"1", "4", "5", "6"}


def test_balance_hasta_una_fecha(sesion, ej):
    b = balance_sumas_y_saldos(sesion, ej, hasta=date(2026, 2, 28), nivel=3)
    assert b.total_debe == b.total_haber == D("1200.00")


def test_balance_rechaza_niveles_invalidos(sesion, ej):
    with pytest.raises(ValueError):
        balance_sumas_y_saldos(sesion, ej, nivel=13)


def test_libro_iva_rechaza_sentido_invalido(sesion, ej):
    with pytest.raises(ValueError):
        libro_iva(sesion, ej, "X")


# ---------------------------------------------------------------------------- datos reales (MGD 2021)


@pytest.mark.datos_reales
def test_informes_con_datos_reales(sesion, carga_mgd):
    e = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    d = libro_diario(sesion, e)
    assert d.total_debe == d.total_haber and len(d.asientos) == carga_mgd.asientos
    b = balance_sumas_y_saldos(sesion, e)
    assert b.total_debe == b.total_haber == d.total_debe
    # el saldo final del Mayor de cada cuenta es el saldo del balance
    for fila in b.filas[:40]:
        m = mayor(sesion, e, fila.cuenta)
        assert m.saldo_final == fila.debe - fila.haber
    # el balance agrupado cuadra con el de subcuentas
    por_3 = balance_sumas_y_saldos(sesion, e, nivel=3)
    assert por_3.total_debe == b.total_debe


@pytest.mark.datos_reales
def test_libro_iva_recibidas_cuadra_con_los_asientos_de_las_facturas(sesion, carga_mgd):
    e = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    r = libro_iva(sesion, e, "R")
    emitidas = libro_iva(sesion, e, "E")
    assert len(r.lineas) + len(emitidas.lineas) >= 1
    assert sum((b for b, _ in r.por_tipo().values()), D("0.00")) == r.total_base
    # La cuota del libro = saldo, en los asientos de facturas recibidas (tipo 2), de las cuentas de IVA que usan las facturas
    # (casi siempre 472…; en Empresa A dos facturas de 2021 llevan el IVA a una cuenta 4711…, por eso no se filtra por 472).
    cuentas_iva = {iva.cuenta_iva_id for f in sesion.scalars(select(Factura).where(Factura.ejercicio_id == e.id, Factura.sentido == "R")) for iva in f.ivas}
    cuentas_iva.discard(None)
    apuntes = sesion.execute(
        select(Apunte.debe, Apunte.haber).join(Asiento).where(Asiento.ejercicio_id == e.id, Asiento.tipo == 2, Apunte.cuenta_id.in_(cuentas_iva))
    )
    assert r.total_cuota == sum((debe - haber for debe, haber in apuntes), D("0.00"))
