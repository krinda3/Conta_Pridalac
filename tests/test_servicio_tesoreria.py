"""Servicios de vencimientos y de movimientos de banco, sobre los datos reales de Empresa A y Empresa B."""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.auditoria import auditar
from conta_pridalac.db.modelos import Asiento, Banco, Cuenta, Ejercicio, Factura, MovimientoBanco, Pago, Vencimiento
from conta_pridalac.domain.errores import DocumentoConPagos, EjercicioCerrado, ErrorContable
from conta_pridalac.domain.errores import FechaFueraDePeriodo
from conta_pridalac.domain.tesoreria import cuenta_efectiva, pendiente, saldos_corridos
from conta_pridalac.servicios.tesoreria import (
    LineaPago,
    compensar_vencimiento,
    eliminar_movimiento,
    pagar_vencimiento,
    regenerar_asiento,
    registrar_movimiento,
    transferir,
)
from conta_pridalac.servicios.vencimientos import (
    PlazoVencimiento,
    definir_vencimientos,
    importe_a_vencer,
    plazos_por_defecto,
    repartir_en_plazos,
    signo,
)

D = Decimal
pytestmark = pytest.mark.datos_reales


def _foto(sesion):
    estado = {}
    for a in sesion.scalars(select(Asiento)):
        lineas: Counter = Counter()
        for ap in a.apuntes:
            lineas[ap.cuenta.codigo] += ap.debe - ap.haber
        estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, dict(lineas))
    return estado


def _bancos(sesion):
    return sesion.scalars(select(Banco).where(Banco.clase == "B").order_by(Banco.numero)).all()


def _pendientes(sesion):
    return [v for v in sesion.scalars(select(Vencimiento).order_by(Vencimiento.id)) if v.fecha and pendiente(sesion, v) != 0]


def _hallazgos(sesion, ej):
    return Counter(h.codigo for h in auditar(sesion, ej))


# --------------------------------------------------------------------------- vencimientos (puros)


def test_repartir_en_plazos_el_primero_absorbe_la_diferencia():
    plazos = repartir_en_plazos(D("100.00"), 3, date(2026, 1, 31), meses_entre=1)
    assert [p.importe for p in plazos] == [D("33.34"), D("33.33"), D("33.33")]
    assert [p.fecha for p in plazos] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert sum(p.importe for p in plazos) == D("100.00")
    assert repartir_en_plazos(D("10"), 1, None)[0].fecha is None
    with pytest.raises(ErrorContable):
        repartir_en_plazos(D("10"), 0, None)


# --------------------------------------------------------------------------- vencimientos (datos reales)


def test_los_vencimientos_de_cada_factura_suman_total_mas_retenciones(sesion, carga_mgd):
    """268 facturas reales: Σ vencimientos = ±(total − ajustes) en todas, incluida la que lleva retención de IRPF."""
    comprobadas = 0
    for f in sesion.scalars(select(Factura)):
        vs = sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)).all()
        assert sum((v.importe for v in vs), D(0)) == signo(f) * importe_a_vencer(f), f"{f.sentido} {f.numero}"
        comprobadas += 1
    assert comprobadas == carga_mgd.facturas


def test_redefinir_los_vencimientos_actuales_no_cambia_nada(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes = {v.id: (v.fecha, v.importe, v.cuenta_id) for v in sesion.scalars(select(Vencimiento))}
    for f in sesion.scalars(select(Factura)).all():
        vs = sorted(sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)), key=lambda v: v.id)
        plazos = [PlazoVencimiento(importe=signo(f) * v.importe, fecha=v.fecha, cuenta=v.cuenta.codigo if v.cuenta else None, banco=v.banco_previsto, forma_pago=v.forma_pago) for v in vs]
        definir_vencimientos(sesion, ej, f, plazos)
    assert {v.id: (v.fecha, v.importe, v.cuenta_id) for v in sesion.scalars(select(Vencimiento))} == antes


def _factura_nueva(sesion, ej, modelo, numero, total="100.00"):
    f = Factura(
        ejercicio_id=ej.id, sentido="R", fecha_contable=date(2021, 12, 1), numero=numero,
        cuenta_tercero_id=modelo.cuenta_tercero_id, cuenta_contrapartida_id=modelo.cuenta_contrapartida_id, total=D(total),
    )
    sesion.add(f)
    sesion.flush()
    return f


def test_los_plazos_deben_sumar_lo_que_exige_la_factura(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    modelo = sesion.scalars(select(Factura).where(Factura.sentido == "R")).first()
    with pytest.raises(ErrorContable, match="suman"):
        definir_vencimientos(sesion, ej, modelo, [PlazoVencimiento(importe=modelo.total - D("1"), fecha=date(2021, 5, 1))])

    nueva = _factura_nueva(sesion, ej, modelo, 9001)
    vs = definir_vencimientos(sesion, ej, nueva, repartir_en_plazos(D("100.00"), 3, date(2021, 12, 31)))
    assert [v.importe for v in vs] == [D("-33.34"), D("-33.33"), D("-33.33")]  # a pagar: negativo
    assert all(v.cuenta_defecto_id == nueva.cuenta_tercero_id for v in vs)
    # volver a un solo plazo, sin fecha, quita los otros dos (no tienen pagos)
    definir_vencimientos(sesion, ej, nueva, [PlazoVencimiento(importe=D("100.00"), fecha=None)])
    quedan = sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == nueva.id)).all()
    assert len(quedan) == 1 and quedan[0].fecha is None and quedan[0].importe == D("-100.00")


def test_no_se_quita_un_vencimiento_con_pagos(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    modelo = sesion.scalars(select(Factura).where(Factura.sentido == "R")).first()
    nueva = _factura_nueva(sesion, ej, modelo, 9002)
    v1, v2 = definir_vencimientos(sesion, ej, nueva, repartir_en_plazos(D("100.00"), 2, date(2021, 12, 1)))
    pagar_vencimiento(sesion, ej, v2, _bancos(sesion)[0], date(2021, 12, 31))  # se paga el 2.º plazo
    with pytest.raises(DocumentoConPagos):
        definir_vencimientos(sesion, ej, nueva, [PlazoVencimiento(importe=D("100.00"), fecha=date(2021, 12, 1))])
    # el 1.º, sin pagos, se puede modificar libremente; el 2.º conserva su pago
    definir_vencimientos(sesion, ej, nueva, [PlazoVencimiento(importe=D("60.00"), fecha=date(2021, 12, 5)), PlazoVencimiento(importe=D("40.00"), fecha=date(2021, 12, 31))])
    assert v1.importe == D("-60.00") and pendiente(sesion, v2) == D("-40.00") - D("-50.00")  # pagado 50 de un plazo que ahora es 40

# --------------------------------------------------------------------------- movimientos


def _fuera_del_ejercicio(ej, m):
    """Movimientos que la auditoría ya marca como error (fechados en 2020 dentro de la empresa 2021 de Empresa B)."""
    return not (ej.fecha_inicio <= m.fecha <= ej.fecha_fin)


def test_regenerar_el_asiento_de_todos_los_movimientos_no_cambia_el_diario(sesion, carga_mgd):
    """El servicio se niega a tocar un movimiento fechado fuera del ejercicio (3 en Empresa B) y regenera el resto igual."""
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes = _foto(sesion)
    rechazados = 0
    for m in sesion.scalars(select(MovimientoBanco)).all():
        if _fuera_del_ejercicio(ej, m):
            with pytest.raises(FechaFueraDePeriodo):
                regenerar_asiento(sesion, ej, m)
            rechazados += 1
        else:
            regenerar_asiento(sesion, ej, m)
    assert rechazados == (3 if carga_mgd.clave == "empresa_b" else 0)
    assert _foto(sesion) == antes


def test_regrabar_cada_movimiento_con_sus_mismas_lineas_no_cambia_nada(sesion, carga_mgd):
    """Reemplaza los pagos de los movimientos por ellos mismos y compara el Diario y los saldos."""
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes, saldos = _foto(sesion), {b.id: [(m.numero, s) for m, s in saldos_corridos(sesion, b)] for b in sesion.scalars(select(Banco))}
    # primero se recoge todo (las lineas dependen de relaciones que se reemplazan al regrabar)
    plan = []
    for m in sesion.scalars(select(MovimientoBanco)).all():
        if _fuera_del_ejercicio(ej, m):
            continue
        plan.append((m, m.banco, m.fecha, [LineaPago(p.importe, p.vencimiento, p.cuenta_directa.codigo if p.cuenta_directa else None) for p in m.pagos],
                     m.texto, m.clave, [p.movimiento_contraparte for p in m.pagos]))
    for m, banco, fecha, lineas, texto, clave, contrapartes in plan:
        registrar_movimiento(sesion, ej, banco, fecha, lineas, texto=texto, clave=clave, movimiento=m, contrapartes=contrapartes)
    assert _foto(sesion) == antes
    assert {b.id: [(m.numero, s) for m, s in saldos_corridos(sesion, b)] for b in sesion.scalars(select(Banco))} == saldos


def test_pago_directo_de_un_vencimiento_y_su_borrado(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    base = _hallazgos(sesion, ej)
    v = next(x for x in _pendientes(sesion) if x.origen_tipo in ("R", "E"))
    banco, pte = _bancos(sesion)[0], pendiente(sesion, v)
    ultimo_diario = sesion.scalar(select(func.max(Asiento.numero_diario)))
    ultimo_mov = sesion.scalar(select(func.max(MovimientoBanco.numero)))

    r = pagar_vencimiento(sesion, ej, v, banco, date(2021, 12, 31))
    m = r.movimiento
    assert m.numero == ultimo_mov + 1 and r.asiento.numero_diario == ultimo_diario + 1
    assert pendiente(sesion, v) == 0 and r.advertencias == []
    assert m.pagos[0].importe == pte and m.clave == "ZZZ" and m.texto.startswith(("PAGO", "COBRO"))
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in r.asiento.apuntes}
    assert lineas[banco.cuenta.codigo] == pte  # el banco recibe lo que cobra (o entrega lo que paga, negativo)
    assert _hallazgos(sesion, ej) == base  # no se ha creado ningún problema nuevo

    assert eliminar_movimiento(sesion, ej, m) == 1
    assert pendiente(sesion, v) == pte
    assert _hallazgos(sesion, ej) == base


def test_pagar_dos_veces_avisa_pero_graba(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    v = next(x for x in _pendientes(sesion) if x.origen_tipo in ("R", "E"))
    banco = _bancos(sesion)[0]
    pagar_vencimiento(sesion, ej, v, banco, date(2021, 12, 30))
    with pytest.raises(ErrorContable, match="ya está saldado"):  # el atajo se niega a pagar lo que ya está saldado
        pagar_vencimiento(sesion, ej, v, banco, date(2021, 12, 31))
    # el movimiento manual sí se puede grabar (como en MGD), pero avisa; el vencimiento queda pagado de más
    r = registrar_movimiento(sesion, ej, banco, date(2021, 12, 31), [LineaPago(v.importe, v)])
    assert any("ya está pagado" in a for a in r.advertencias)
    assert r.asiento is not None
    assert pendiente(sesion, v) == -v.importe
    assert "vencimiento_pagado_de_mas" in _hallazgos(sesion, ej)  # y la auditoría lo detecta


def test_compensar_un_vencimiento_contra_otra_cuenta(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    base = _hallazgos(sesion, ej)
    v = next(x for x in _pendientes(sesion) if x.origen_tipo == "R")
    pte = pendiente(sesion, v)
    otra = sesion.scalars(select(Cuenta).where(Cuenta.codigo.like("4%"), Cuenta.id != cuenta_efectiva(v).id)).first()
    r = compensar_vencimiento(sesion, ej, v, otra.codigo, date(2021, 12, 31))
    assert r.movimiento.banco.clase == "C" and sum((p.importe for p in r.movimiento.pagos), D(0)) == 0
    assert pendiente(sesion, v) == 0
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in r.asiento.apuntes}
    # la deuda sale de la cuenta en que se devenga el vencimiento (la del proveedor o, en una retención, la de Hacienda)
    assert lineas == {cuenta_efectiva(v).codigo: -pte, otra.codigo: pte}
    assert _hallazgos(sesion, ej) == base


def test_transferencia_entre_bancos(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    base = _hallazgos(sesion, ej)
    origen, destino = _bancos(sesion)[:2]
    antes = {b.id: sum((p.importe for m in sesion.scalars(select(MovimientoBanco).where(MovimientoBanco.banco_id == b.id)) for p in m.pagos), D(0)) for b in (origen, destino)}

    salida, entrada = transferir(sesion, ej, origen, destino, date(2021, 12, 20), D("250.00"))
    assert salida.asiento is not None and entrada.asiento is None  # solo el lado de salida genera asiento
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in salida.asiento.apuntes}
    assert lineas == {destino.cuenta.codigo: D("250.00"), origen.cuenta.codigo: D("-250.00")}
    assert salida.movimiento.pagos[0].movimiento_contraparte_id == entrada.movimiento.id
    assert entrada.movimiento.pagos[0].movimiento_contraparte_id == salida.movimiento.id
    assert _hallazgos(sesion, ej) == base  # saldos de bancos y espejos siguen cuadrando

    assert eliminar_movimiento(sesion, ej, salida.movimiento) == 2  # se borra la pareja
    assert sesion.scalar(select(func.count()).select_from(MovimientoBanco)) == carga_mgd.movimientos
    assert _hallazgos(sesion, ej) == base
    with pytest.raises(ErrorContable):
        transferir(sesion, ej, origen, origen, date(2021, 12, 20), D("1"))
    with pytest.raises(ErrorContable):
        transferir(sesion, ej, origen, destino, date(2021, 12, 20), D("-1"))


def test_un_cobro_sin_vencimiento_queda_pendiente_de_aplicar(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    base = _hallazgos(sesion, ej)
    banco = _bancos(sesion)[0]
    r = registrar_movimiento(sesion, ej, banco, date(2021, 11, 5), [LineaPago(D("77.00"))], texto="INGRESO NO IDENTIFICADO")
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in r.asiento.apuntes}
    assert lineas[banco.cuenta.codigo] == D("77.00") and -D("77.00") in lineas.values()
    assert any(c.startswith("555") for c in lineas)  # cuenta de partidas pendientes de aplicar
    assert _hallazgos(sesion, ej) == base


def test_fecha_fuera_del_ejercicio_y_ejercicio_cerrado(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    banco = _bancos(sesion)[0]
    antes = sesion.scalar(select(func.count()).select_from(MovimientoBanco))
    with pytest.raises(ErrorContable):
        registrar_movimiento(sesion, ej, banco, date(2022, 1, 3), [LineaPago(D("1"))])
    ej.cerrado = True
    with pytest.raises(EjercicioCerrado):
        registrar_movimiento(sesion, ej, banco, date(2021, 6, 3), [LineaPago(D("1"))])
    with pytest.raises(ErrorContable, match="al menos una línea"):
        ej.cerrado = False
        registrar_movimiento(sesion, ej, banco, date(2021, 6, 3), [])
    sesion.rollback()
    assert sesion.scalar(select(func.count()).select_from(MovimientoBanco)) == antes

