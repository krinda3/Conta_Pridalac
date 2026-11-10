"""Regularización, cierre y apertura del ejercicio siguiente."""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.auditoria import ERROR, auditar
from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Parametro, Vencimiento
from conta_pridalac.domain.errores import EjercicioCerrado, ErrorContable
from conta_pridalac.domain.tesoreria import cuenta_efectiva, pendiente
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cierre import (
    abrir_ejercicio,
    asiento_de_cierre,
    cerrar_ejercicio,
    ejercicio_siguiente,
    reabrir_ejercicio,
    regularizar_ingresos_gastos,
    saldos_del_ejercicio,
)
from conta_pridalac.servicios.extras import LineaManual, grabar_extra
from conta_pridalac.servicios.vencimientos import PlazoVencimiento

D = Decimal


# ---------------------------------------------------------------------------- sintético


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("10000000", "CAPITAL"), ("12900000", "PERDIDAS Y GANANCIAS"), ("57200001", "BANCO"), ("62900000", "GASTOS"),
                           ("70000000", "VENTAS"), ("41000001", "PROVEEDOR"), ("43000001", "CLIENTE")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.add(Parametro(empresa_id=e.id, clave="PYG", valor="12900000"))
    sesion.flush()
    return ej


def _mov(sesion, ej, n, fecha, *lineas, tipo=4):
    grabar_asiento(sesion, ej, tipo=tipo, numero=n, fecha=fecha, lineas=[LineaAsiento(c, D(i)) for c, i in lineas])


def _saldo(sesion, ej, codigo, **kw):
    return saldos_del_ejercicio(sesion, ej, **kw).get(codigo, D("0.00"))


def test_regulariza_con_beneficio(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 1, 2), ("57200001", "1000"), ("10000000", "-1000"))
    _mov(sesion, emp, 2, date(2026, 3, 1), ("43000001", "500"), ("70000000", "-500"))
    _mov(sesion, emp, 3, date(2026, 4, 1), ("62900000", "200"), ("41000001", "-200"))
    r = regularizar_ingresos_gastos(sesion, emp)
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in r.asiento.apuntes}
    assert lineas == {"70000000": D("500.00"), "62900000": D("-200.00"), "12900000": D("-300.00")}  # P y G al haber: beneficio
    assert (r.asiento.tipo, r.asiento.subtipo, r.asiento.fecha) == (9, "R", date(2026, 12, 31))
    assert _saldo(sesion, emp, "70000000") == 0 and _saldo(sesion, emp, "62900000") == 0
    assert _saldo(sesion, emp, "12900000") == D("-300.00")


def test_regulariza_con_perdida_y_es_idempotente(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 3, 1), ("62900000", "800"), ("41000001", "-800"))
    _mov(sesion, emp, 2, date(2026, 4, 1), ("43000001", "300"), ("70000000", "-300"))
    a = regularizar_ingresos_gastos(sesion, emp)
    assert {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.asiento.apuntes}["12900000"] == D("500.00")  # P y G al debe: pérdida
    b = regularizar_ingresos_gastos(sesion, emp)
    assert a.asiento.id == b.asiento.id
    assert len(sesion.scalars(select(Asiento).where(Asiento.subtipo == "R")).all()) == 1  # no se acumulan
    # un gasto nuevo posterior: la regularización se rehace incluyéndolo
    _mov(sesion, emp, 3, date(2026, 5, 1), ("62900000", "100"), ("41000001", "-100"))
    c = regularizar_ingresos_gastos(sesion, emp)
    assert c.asiento.id == a.asiento.id and {ap.cuenta.codigo: ap.debe - ap.haber for ap in c.asiento.apuntes}["12900000"] == D("600.00")


def test_errores_de_la_regularizacion(sesion, emp):
    with pytest.raises(ErrorContable, match="No hay ingresos ni gastos"):
        regularizar_ingresos_gastos(sesion, emp)
    sesion.scalars(select(Parametro).where(Parametro.clave == "PYG")).one().valor = "99999999"
    _mov(sesion, emp, 1, date(2026, 3, 1), ("62900000", "800"), ("41000001", "-800"))
    with pytest.raises(ErrorContable, match="Pérdidas y Ganancias"):
        regularizar_ingresos_gastos(sesion, emp)


def test_el_cierre_exige_regularizar_antes(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 3, 1), ("62900000", "800"), ("41000001", "-800"))
    with pytest.raises(ErrorContable, match="pendiente la regularización"):
        asiento_de_cierre(sesion, emp)
    regularizar_ingresos_gastos(sesion, emp)
    r = asiento_de_cierre(sesion, emp)
    assert r.asiento.subtipo == "Z" and r.asiento.concepto == "ASIENTO DE CIERRE"
    assert saldos_del_ejercicio(sesion, emp) == {}  # todas las cuentas a cero con el cierre


def test_la_apertura_arrastra_saldos_y_vencimientos(sesion, emp):
    # Apertura previa con un capital, una factura pendiente de pago (vencimiento) y otra ya pagada
    grabar_extra(sesion, emp, fecha=date(2026, 1, 1), texto="X", numero=1, tipo=9, subtipo="A", lineas=[
        LineaManual("57200001", "D", D("1000")), LineaManual("10000000", "H", D("1000"))])
    r = grabar_extra(sesion, emp, fecha=date(2026, 6, 1), texto="COMPRA", lineas=[
        LineaManual("62900000", "D", D("300")),
        LineaManual("41000001", "H", D("300"), vencimientos=[PlazoVencimiento(D("-100"), date(2026, 11, 30)), PlazoVencimiento(D("-200"), date(2027, 2, 15))])])
    cierre = cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    assert cierre.resultado == D("-300.00")  # pérdida de 300
    nuevo = cierre.apertura.ejercicio
    assert (nuevo.anio, nuevo.fecha_inicio, nuevo.fecha_fin, nuevo.cerrado) == (2027, date(2027, 1, 1), date(2027, 12, 31), False)
    assert emp.cerrado
    ap = cierre.apertura.extra.asiento
    assert (ap.tipo, ap.numero, ap.subtipo, ap.fecha, ap.concepto) == (9, 1, "A", date(2027, 1, 1), "ASIENTO DE APERTURA")
    lineas = {a.cuenta.codigo: a.debe - a.haber for a in ap.apuntes}
    assert lineas == {"57200001": D("1000.00"), "10000000": D("-1000.00"), "12900000": D("300.00"), "41000001": D("-300.00")}
    vs = sorted(sesion.scalars(select(Vencimiento).where(Vencimiento.ejercicio_id == nuevo.id)), key=lambda v: v.fecha)
    assert [(v.fecha, v.importe, v.origen_tipo) for v in vs] == [(date(2026, 11, 30), D("-100.00"), "X"), (date(2027, 2, 15), D("-200.00"), "X")]
    assert all(v.apunte.cuenta.codigo == "41000001" and v.apunte.asiento_id == ap.id for v in vs)
    assert cierre.apertura.vencimientos_arrastrados == 2 and cierre.advertencias == []


def test_un_ejercicio_cerrado_no_admite_movimientos_y_no_se_cierra_dos_veces(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 3, 1), ("57200001", "100"), ("10000000", "-100"))
    cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    with pytest.raises(EjercicioCerrado):
        _mov(sesion, emp, 2, date(2026, 4, 1), ("57200001", "1"), ("10000000", "-1"))
    with pytest.raises(ErrorContable, match="ya está cerrado"):
        cerrar_ejercicio(sesion, emp, exigir_auditoria=False)


def test_reabrir_deshace_el_cierre_y_la_apertura(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 3, 1), ("62900000", "50"), ("41000001", "-50"))
    antes = sesion.scalar(select(Asiento.id).order_by(Asiento.id.desc()).limit(1))
    cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    assert sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2027)).first() is not None
    reabrir_ejercicio(sesion, emp)
    assert not emp.cerrado and sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2027)).first() is None
    assert {a.subtipo for a in sesion.scalars(select(Asiento))} <= {None, "M"}  # no queda ni cierre, ni regularización, ni apertura
    # se puede volver a cerrar
    assert cerrar_ejercicio(sesion, emp, exigir_auditoria=False).apertura is not None
    # y no se reabre si el nuevo ya tiene movimientos
    nuevo = ejercicio_siguiente(sesion, emp)
    _mov(sesion, nuevo, 7, date(2027, 2, 1), ("57200001", "10"), ("10000000", "-10"))
    with pytest.raises(ErrorContable, match="ya tiene movimientos"):
        reabrir_ejercicio(sesion, emp)


def test_reabrir_deshace_tambien_la_regularizacion_y_al_volver_a_cerrar_se_recalcula(sesion, emp):
    _mov(sesion, emp, 1, date(2026, 3, 1), ("62900000", "50"), ("41000001", "-50"))
    _mov(sesion, emp, 2, date(2026, 4, 1), ("43000001", "300"), ("70000000", "-300"))
    primero = cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    assert primero.resultado == D("250.00") and primero.regularizacion is not None
    assert _saldo(sesion, emp, "62900000", excluir=("Z",)) == 0 and _saldo(sesion, emp, "12900000", excluir=("Z",)) == D("-250.00")
    reabrir_ejercicio(sesion, emp)
    # las cuentas de gastos e ingresos vuelven a tener sus saldos y P y G a cero: la regularización ya no está
    assert _saldo(sesion, emp, "62900000") == D("50.00") and _saldo(sesion, emp, "70000000") == D("-300.00") and _saldo(sesion, emp, "12900000") == 0
    # se añade un gasto después de reabrir: al cerrar de nuevo la regularización recoge todo (no queda desfasada)
    _mov(sesion, emp, 3, date(2026, 5, 1), ("62900000", "70"), ("41000001", "-70"))
    segundo = cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    assert segundo.resultado == D("180.00") and _saldo(sesion, emp, "62900000", excluir=("Z",)) == 0
    assert sesion.scalar(select(func.count()).select_from(Asiento).where(Asiento.subtipo == "R")) == 1


def test_no_se_cierra_con_errores_de_auditoria(sesion, emp):
    from conta_pridalac.db.modelos import Apunte

    a = Asiento(ejercicio_id=emp.id, tipo=4, numero=1, fecha=date(2026, 1, 5), numero_diario=1)
    a.apuntes.append(Apunte(orden=1, cuenta_id=sesion.scalars(select(Cuenta).where(Cuenta.codigo == "57200001")).one().id, debe=D("10")))
    sesion.add(a)
    sesion.flush()
    with pytest.raises(ErrorContable, match="auditoría tiene 1 error"):
        cerrar_ejercicio(sesion, emp)
    assert not emp.cerrado


def test_vencimientos_en_una_cuenta_con_saldo_cero_se_avisan(sesion, emp):
    """Factura pendiente (-100) y un anticipo (+100) en la misma cuenta: saldo 0 pero vencimiento pendiente."""
    grabar_extra(sesion, emp, fecha=date(2026, 2, 1), texto="FACTURA", lineas=[
        LineaManual("62900000", "D", D("100")),
        LineaManual("41000001", "H", D("100"), vencimientos=[PlazoVencimiento(D("-100"), date(2026, 3, 1))])])
    grabar_extra(sesion, emp, fecha=date(2026, 2, 5), texto="ANTICIPO", lineas=[
        LineaManual("41000001", "D", D("100")), LineaManual("57200001", "H", D("100"))])
    cierre = cerrar_ejercicio(sesion, emp, exigir_auditoria=False)
    assert any("saldo de apertura es 0" in a for a in cierre.advertencias)
    assert cierre.apertura.vencimientos_arrastrados == 0


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_regularizar_los_ingresos_y_gastos_reales(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    prefijos = ("6", "7")
    antes = {c: s for c, s in saldos_del_ejercicio(sesion, ej).items() if c.startswith(prefijos)}
    resultado = -sum(antes.values())  # beneficio si los ingresos superan a los gastos
    r = regularizar_ingresos_gastos(sesion, ej, date(2021, 12, 31))
    assert sum((ap.debe - ap.haber for ap in r.asiento.apuntes), D(0)) == 0
    assert not {c for c in saldos_del_ejercicio(sesion, ej) if c.startswith(prefijos)}  # ingresos y gastos a cero
    pyg_linea = next(ap for ap in r.asiento.apuntes if ap.cuenta.codigo == "12900000")
    assert pyg_linea.haber - pyg_linea.debe == resultado
    # idempotente
    r2 = regularizar_ingresos_gastos(sesion, ej, date(2021, 12, 31))
    assert (r2.asiento.id, r2.asiento.numero_diario) == (r.asiento.id, r.asiento.numero_diario)


@pytest.mark.datos_reales
def test_cierre_y_apertura_de_los_ejercicios_reales(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    regularizar_ingresos_gastos(sesion, ej, date(2021, 12, 31))
    saldos = saldos_del_ejercicio(sesion, ej)
    assert sum(saldos.values(), D(0)) == 0  # el Diario cuadra

    cierre = asiento_de_cierre(sesion, ej, date(2021, 12, 31))
    assert saldos_del_ejercicio(sesion, ej) == {}  # todas las cuentas quedan a cero
    assert {ap.cuenta.codigo: ap.debe - ap.haber for ap in cierre.asiento.apuntes} == {c: -s for c, s in saldos.items()}

    ap = abrir_ejercicio(sesion, ej)
    nuevo = ap.ejercicio
    assert (nuevo.anio, nuevo.fecha_inicio) == (2022, date(2022, 1, 1))
    # la apertura reproduce los saldos previos al cierre
    assert saldos_del_ejercicio(sesion, nuevo) == saldos
    assert sum((a.debe - a.haber for a in ap.extra.asiento.apuntes), D(0)) == 0
    # y arrastra todos los vencimientos pendientes cuya cuenta tiene saldo
    pendientes = [v for v in sesion.scalars(select(Vencimiento).where(Vencimiento.ejercicio_id == ej.id)) if pendiente(sesion, v) != 0]
    carry = sesion.scalars(select(Vencimiento).where(Vencimiento.ejercicio_id == nuevo.id)).all()
    assert ap.advertencias == []
    assert len(carry) == ap.vencimientos_arrastrados == len(pendientes) == {"empresa_a": 22, "empresa_b": 9}[carga_mgd.clave]
    for v in carry:
        assert v.origen_tipo == "X" and v.apunte is not None and v.apunte.asiento_id == ap.extra.asiento.id
    assert sum(v.importe for v in carry) == sum(pendiente(sesion, v) for v in pendientes)
    orden = lambda t: (t[0] or date.max, t[1])  # hay vencimientos sin fecha
    assert sorted(((v.fecha, v.importe) for v in carry), key=orden) == sorted(((v.fecha, pendiente(sesion, v)) for v in pendientes), key=orden)
    # la contabilidad del nuevo ejercicio no tiene errores de integridad
    assert [h for h in auditar(sesion, nuevo) if h.gravedad == ERROR] == []


@pytest.mark.datos_reales
def test_cerrar_el_ejercicio_exige_auditoria_sin_errores(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    if carga_mgd.clave == "empresa_b":
        with pytest.raises(ErrorContable, match="6 error"):  # los 6 asientos de 2020 dentro de la empresa 2021
            cerrar_ejercicio(sesion, ej)
        assert not ej.cerrado
        return
    r = cerrar_ejercicio(sesion, ej)
    assert ej.cerrado and r.apertura.ejercicio.anio == 2022
    with pytest.raises(EjercicioCerrado):
        grabar_asiento(sesion, ej, tipo=4, numero=999, fecha=date(2021, 6, 1), lineas=[LineaAsiento("57200001", D("1")), LineaAsiento("10000000", D("-1"))])
    # reabrir devuelve la contabilidad a como estaba y se puede volver a cerrar con el mismo resultado
    reabrir_ejercicio(sesion, ej)
    assert not ej.cerrado
    assert cerrar_ejercicio(sesion, ej).resultado == r.resultado


@pytest.mark.datos_reales
def test_los_movimientos_de_banco_del_ejercicio_nuevo_no_rompen_la_auditoria_del_anterior(sesion, carga_mgd):
    """Con dos ejercicios, el saldo de cada banco se comprueba por separado (apertura + movimientos del propio ejercicio)."""
    from datetime import date as d

    from conta_pridalac.db.modelos import Banco
    from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento

    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    regularizar_ingresos_gastos(sesion, ej, d(2021, 12, 31))
    asiento_de_cierre(sesion, ej, d(2021, 12, 31))
    nuevo = abrir_ejercicio(sesion, ej).ejercicio
    banco = sesion.scalars(select(Banco).where(Banco.clase == "B").order_by(Banco.numero)).first()
    registrar_movimiento(sesion, nuevo, banco, d(2022, 2, 1), [LineaPago(D("123.45"))], texto="INGRESO 2022")
    assert [h for h in auditar(sesion, nuevo) if h.codigo == "saldo_de_banco"] == []
    assert [h for h in auditar(sesion, ej) if h.codigo == "saldo_de_banco"] == []


@pytest.mark.datos_reales
def test_saldos_bancarios_de_apertura_coinciden_con_el_cierre(sesion, carga_mgd):
    """El saldo inicial de cada banco en el ejercicio nuevo es el saldo contable de su cuenta al cerrar el anterior."""
    from conta_pridalac.db.modelos import Banco

    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    regularizar_ingresos_gastos(sesion, ej, date(2021, 12, 31))
    saldos = saldos_del_ejercicio(sesion, ej)
    asiento_de_cierre(sesion, ej, date(2021, 12, 31))
    ap = abrir_ejercicio(sesion, ej)
    lineas = {a.cuenta.codigo: a.debe - a.haber for a in ap.extra.asiento.apuntes}
    for banco in sesion.scalars(select(Banco).where(Banco.clase == "B")):
        assert lineas.get(banco.cuenta.codigo, D(0)) == saldos.get(banco.cuenta.codigo, D(0))
