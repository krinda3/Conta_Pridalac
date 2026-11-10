"""Pasar a movimientos de banco, como cobro o pago de una operación, la parte del banco de los asientos manuales."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.auditoria import auditar
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, MovimientoBanco, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.pasar_asientos import asientos_a_pasar, pasar_todos
from test_extractos import banco_de, ej, movimiento  # noqa: F401 - `ej` es una fixture

D = Decimal


def _cuentas(sesion, ej, *codigos):
    for codigo in codigos:
        sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=codigo, nombre=f"CUENTA {codigo}"))
    sesion.flush()


def _saldos(sesion, ej):
    filas = sesion.execute(select(Cuenta.codigo, Apunte.debe, Apunte.haber).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id).where(Asiento.ejercicio_id == ej.id)).all()
    saldos: dict[str, Decimal] = {}
    for codigo, debe, haber in filas:
        saldos[codigo] = saldos.get(codigo, D(0)) + debe - haber
    return saldos


def _avisos_de_saldo(sesion, ej):
    return [h for h in auditar(sesion, ej) if h.codigo == "saldo_de_banco"]


def _concesion_y_cobro(sesion, ej, numero=2, importe="1477.62", dia=13):
    """Asiento de cuatro líneas: la concesión (4708 al debe, 740 al haber) y el cobro (banco al debe, 4708 al haber)."""
    grabar_asiento(sesion, ej, tipo=4, numero=numero, fecha=date(2026, 5, dia), concepto="Concesion ayuda", subtipo="M", agrupar=False, lineas=[
        LineaAsiento("47080000", D(importe)), LineaAsiento("74000000", -D(importe)), LineaAsiento("57200001", D(importe)), LineaAsiento("47080000", -D(importe))])


def test_el_cobro_de_una_subvencion_pasa_a_movimiento_y_salda_un_vencimiento_de_la_operacion(sesion, ej):
    banco = banco_de(sesion)
    _cuentas(sesion, ej, "47080000", "74000000")
    _concesion_y_cobro(sesion, ej)
    assert len(_avisos_de_saldo(sesion, ej)) == 1
    antes = _saldos(sesion, ej)
    (c,) = pasar_todos(sesion, ej, banco)
    assert c.hecha and c.contrapartida == "47080000" and sorted(c.resto) == [("47080000", D("1477.62")), ("74000000", D("-1477.62"))] and c.movimiento is not None
    assert _saldos(sesion, ej) == antes  # ninguna cuenta cambia de saldo
    assert _avisos_de_saldo(sesion, ej) == []
    manual = sesion.scalars(select(Asiento).where(Asiento.tipo == 4, Asiento.numero == 2)).one()
    assert sorted((a.cuenta.codigo, a.debe - a.haber) for a in manual.apuntes) == [("47080000", D("1477.62")), ("74000000", D("-1477.62"))]  # queda la concesión
    v = sesion.scalars(select(Vencimiento)).one()  # y la operación lleva su vencimiento, a cobrar, saldado por el movimiento
    assert (v.origen_tipo, v.importe, v.apunte.cuenta.codigo, v.fecha) == ("X", D("1477.62"), "47080000", date(2026, 5, 13)) and pendiente(sesion, v) == 0
    m = sesion.scalars(select(MovimientoBanco)).one()
    assert (m.fecha, m.pagos[0].importe, m.pagos[0].vencimiento_id, m.pagos[0].cuenta_directa_id) == (date(2026, 5, 13), D("1477.62"), v.id, None)  # el cobro salda el vencimiento: no es un apunte suelto
    assert asientos_a_pasar(sesion, ej, banco) == []  # volver a pasarlo no encuentra nada


def test_la_devolucion_de_un_proveedor_pasa_igual_y_un_pago_sale_con_vencimiento_a_pagar(sesion, ej):
    banco = banco_de(sesion)
    _cuentas(sesion, ej, "41008192")
    # una corrección (proveedor al debe, gasto al haber) y su devolución (banco al debe, proveedor al haber)
    grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 1), concepto="Correccion", subtipo="M", agrupar=False, lineas=[
        LineaAsiento("41008192", D("2.70")), LineaAsiento("62900000", D("-2.70")), LineaAsiento("57200001", D("2.70")), LineaAsiento("41008192", D("-2.70"))])
    # y un pago: una provisión que se paga (gasto al debe, proveedor al haber) y el pago (proveedor al debe, banco al haber)
    grabar_asiento(sesion, ej, tipo=4, numero=5, fecha=date(2026, 2, 1), concepto="Pago", subtipo="M", agrupar=False, lineas=[
        LineaAsiento("62900000", D("50.00")), LineaAsiento("41008192", D("-50.00")), LineaAsiento("41008192", D("50.00")), LineaAsiento("57200001", D("-50.00"))])
    antes = _saldos(sesion, ej)
    hechas = pasar_todos(sesion, ej, banco)
    assert [c.hecha for c in hechas] == [True, True]
    assert _saldos(sesion, ej) == antes and _avisos_de_saldo(sesion, ej) == []
    importes = sorted(v.importe for v in sesion.scalars(select(Vencimiento)))
    assert importes == [D("-50.00"), D("2.70")]  # a pagar el que sale del banco, a cobrar el que entra
    assert all(pendiente(sesion, v) == 0 for v in sesion.scalars(select(Vencimiento)))


def test_un_asiento_que_no_recoge_la_operacion_no_se_toca(sesion, ej):
    """Un simple «banco contra ingresos» no sale de ninguna operación: pasarlo a movimiento sería inventarlo."""
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    antes = _saldos(sesion, ej)
    (c,) = pasar_todos(sesion, ej, banco)
    assert not c.hecha and "no recoge la operación" in c.problema
    assert _saldos(sesion, ej) == antes and sesion.scalar(select(func.count()).select_from(MovimientoBanco)) == 0 and sesion.scalar(select(func.count()).select_from(Vencimiento)) == 0


def test_si_hay_dudas_sobre_la_cuenta_no_se_toca_nada(sesion, ej):
    banco = banco_de(sesion)
    _cuentas(sesion, ej, "47080000")
    grabar_asiento(sesion, ej, tipo=4, numero=3, fecha=date(2026, 5, 13), concepto="Raro", subtipo="M", agrupar=False, lineas=[
        LineaAsiento("57200001", D("100.00")), LineaAsiento("62900000", D("-100.00")), LineaAsiento("70000000", D("-100.00")), LineaAsiento("47080000", D("100.00")), LineaAsiento("47080000", D("-100.00")), LineaAsiento("62900000", D("100.00"))])
    antes = _saldos(sesion, ej)
    (c,) = pasar_todos(sesion, ej, banco)
    assert not c.hecha and "no se puede decidir" in c.problema
    assert _saldos(sesion, ej) == antes and sesion.scalar(select(func.count()).select_from(MovimientoBanco)) == 0


def test_se_puede_limitar_a_unos_asientos_y_un_ejercicio_cerrado_no_se_toca(sesion, ej):
    banco = banco_de(sesion)
    _cuentas(sesion, ej, "47080000", "74000000")
    _concesion_y_cobro(sesion, ej, numero=11, importe="10.00", dia=10)
    _concesion_y_cobro(sesion, ej, numero=12, importe="20.00", dia=11)
    hechas = pasar_todos(sesion, ej, banco, {"4.12"})
    assert [c.asiento for c in hechas] == ["4.12"] and [a.numero for a in asientos_a_pasar(sesion, ej, banco)] == [11]
    ej.cerrado = True
    with pytest.raises(ErrorContable, match="cerrado"):
        pasar_todos(sesion, ej, banco)
