"""Conciliar vencimientos pendientes con líneas del extracto: varias facturas en un cargo, un pago en dos veces, diferencias."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Banco, Cuenta, Extracto, ExtractoLinea, MovimientoBanco, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.pagos_extracto import CON_DIFERENCIA, PARCIAL, conciliar_pagos, sugerir, vencimientos_a_pagar
from conta_pridalac.servicios.trimestre import aplicar, fijar_proveedor, preparar_pendientes, proponer
from test_trimestre import _cargar, _saldo, contab, excel, fila  # noqa: F401 - contab es una fixture

D = Decimal


def pendiente_de_pago(sesion, ej, almacen, nombre, total, dia, numero, nif="B77777777"):
    """Una factura recibida contabilizada sin pago: su vencimiento queda pendiente."""
    f = _cargar(sesion, ej, fila(nombre, total, dia, numero, nif=nif, base=round(total / 1.21, 2)))[numero]
    fijar_proveedor(sesion, f, crear=True)
    aplicar(sesion, almacen, ej, preparar_pendientes(sesion, ej, proponer(sesion, ej.empresa_id)).aplicables)
    return next(v for v in sesion.scalars(select(Vencimiento)) if v.factura.numero_factura == numero)


def linea(sesion, ej, texto, importe, dia, valor=None):
    banco = sesion.scalars(select(Banco)).one()
    extracto = sesion.scalar(select(Extracto)) or Extracto(empresa_id=ej.empresa_id, banco_id=banco.id, fichero="x.xlsx", huella="h", formato="bbva")
    sesion.add(extracto)
    sesion.flush()
    n = len(list(sesion.scalars(select(ExtractoLinea)))) + 1
    l = ExtractoLinea(extracto_id=extracto.id, empresa_id=ej.empresa_id, banco_id=banco.id, orden=n, fecha=date(2026, 9, dia), fecha_valor=date(2026, 9, valor) if valor else None,
                      texto=texto, importe=D(str(importe)), clave=f"k{n}")
    sesion.add(l)
    sesion.flush()
    return l


def test_una_linea_paga_un_vencimiento_con_su_fecha_valor(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 57, 3, "H-1")
    assert [(x.id, p) for x, p in vencimientos_a_pagar(sesion, ej)] == [(v.id, D("57.00"))]
    l = linea(sesion, ej, "HOTEL PALACE", -57, 8, valor=7)
    r = conciliar_pagos(sesion, ej, [v], [l])
    assert (r.movimientos, r.saldados, r.parciales) == (1, 1, 0)
    m = sesion.scalars(select(MovimientoBanco)).one()
    assert (m.fecha, m.texto, l.movimiento_id) == (date(2026, 9, 7), "HOTEL PALACE", m.id) and pendiente(sesion, v) == 0
    assert _saldo(sesion, "57200001") == D("-57.00") and vencimientos_a_pagar(sesion, ej) == []


def test_un_cargo_paga_varias_facturas(contab):
    sesion, ej, almacen = contab
    a = pendiente_de_pago(sesion, ej, almacen, "Renfe Viajeros", 66.10, 7, "R-1")
    b = pendiente_de_pago(sesion, ej, almacen, "Renfe Viajeros", 36.95, 7, "R-2")
    l = linea(sesion, ej, "RENFE VIRTUAL INTERNET", -103.05, 8)
    r = conciliar_pagos(sesion, ej, [a, b], [l])
    assert (r.movimientos, r.saldados) == (1, 2)
    m = sesion.scalars(select(MovimientoBanco)).one()
    assert sorted(p.importe for p in m.pagos) == [D("-66.10"), D("-36.95")] and _saldo(sesion, "57200001") == D("-103.05")


def test_una_factura_pagada_en_dos_veces(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Golf Valdecañas", 713.08, 3, "G-1")
    l1, l2 = linea(sesion, ej, "HOTELES Y ALOJAMIENTO", -580.48, 25), linea(sesion, ej, "HOTELES Y ALOJAMIENTO", -132.60, 28)
    r = conciliar_pagos(sesion, ej, [v], [l1, l2])
    assert (r.movimientos, r.saldados) == (2, 1) and pendiente(sesion, v) == 0 and len(list(sesion.scalars(select(MovimientoBanco)))) == 2


def test_pago_parcial_deja_el_resto_pendiente(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 100, 3, "H-1")
    r = conciliar_pagos(sesion, ej, [v], [linea(sesion, ej, "HOTEL", -60, 8)], modo=PARCIAL)
    assert (r.saldados, r.parciales) == (0, 1) and pendiente(sesion, v) == D("-40.00")
    assert [(x.id, p) for x, p in vencimientos_a_pagar(sesion, ej)] == [(v.id, D("40.00"))]


def test_saldar_con_una_diferencia_a_una_cuenta_si_se_pago_menos(contab):
    sesion, ej, almacen = contab
    sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo="77800000", nombre="OTROS INGRESOS"))
    v = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 121, 3, "H-1")
    r = conciliar_pagos(sesion, ej, [v], [linea(sesion, ej, "HOTEL", -120.60, 8)], modo=CON_DIFERENCIA, cuenta_diferencia="77800000")
    assert (r.saldados, r.diferencia) == (1, D("0.40")) and pendiente(sesion, v) == 0
    assert (_saldo(sesion, "57200001"), _saldo(sesion, "77800000")) == (D("-120.60"), D("-0.40")) and _saldo(sesion, v.factura.cuenta_tercero.codigo) == 0


def test_saldar_con_una_diferencia_a_una_cuenta_si_se_pago_de_mas(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Restaurante", 51.60, 3, "RE-1")
    l = linea(sesion, ej, "RESTAURANTES", -52, 8)
    with pytest.raises(ErrorContable, match="más de lo pendiente"):
        conciliar_pagos(sesion, ej, [v], [l], modo=PARCIAL)
    antes = _saldo(sesion, "62900000")
    conciliar_pagos(sesion, ej, [v], [l], modo=CON_DIFERENCIA, cuenta_diferencia="62900000")
    assert pendiente(sesion, v) == 0 and _saldo(sesion, "57200001") == D("-52.00") and _saldo(sesion, "62900000") - antes == D("0.40")


def test_con_diferencia_hay_que_decir_una_cuenta_que_exista(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 100, 3, "H-1")
    l = linea(sesion, ej, "HOTEL", -99, 8)
    with pytest.raises(ErrorContable, match="Elija la subcuenta"):
        conciliar_pagos(sesion, ej, [v], [l], modo=CON_DIFERENCIA, cuenta_diferencia="99999999")
    assert l.movimiento_id is None and not list(sesion.scalars(select(MovimientoBanco)))


def test_lo_que_no_se_puede_conciliar_se_rechaza_sin_hacer_nada(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 57, 3, "H-1")
    ingreso = linea(sesion, ej, "DEVOLUCION", 57, 8)
    with pytest.raises(ErrorContable, match="es un ingreso"):
        conciliar_pagos(sesion, ej, [v], [ingreso])
    ok = linea(sesion, ej, "HOTEL", -57, 9)
    conciliar_pagos(sesion, ej, [v], [ok])
    otra = linea(sesion, ej, "HOTEL OTRA VEZ", -57, 10)
    with pytest.raises(ErrorContable, match="ya están saldados"):
        conciliar_pagos(sesion, ej, [v], [otra])
    with pytest.raises(ErrorContable, match="ya está conciliado"):
        conciliar_pagos(sesion, ej, [pendiente_de_pago(sesion, ej, almacen, "Otro", 10, 4, "O-1", nif="B66666666")], [ok])
    with pytest.raises(ErrorContable, match="al menos un vencimiento"):
        conciliar_pagos(sesion, ej, [], [otra])


def test_sugerencias_para_varias_facturas_en_un_cargo_y_pagos_en_dos_veces(contab):
    sesion, ej, almacen = contab
    a = pendiente_de_pago(sesion, ej, almacen, "Renfe Viajeros", 66.10, 7, "R-1", nif="B11111111")
    b = pendiente_de_pago(sesion, ej, almacen, "Renfe Viajeros", 36.95, 7, "R-2", nif="B11111111")
    g = pendiente_de_pago(sesion, ej, almacen, "Belmo Muebles y Hogar", 3442.75, 1, "B-1", nif="B22222222")
    linea(sesion, ej, "RENFE VIRTUAL INTERNET", -103.05, 8)
    linea(sesion, ej, "TRANSFERENCIAS BELMO Muebles pago 2", -2000, 2)
    linea(sesion, ej, "TRANSFERENCIAS BELMO Muebles pago 3", -1442.75, 20)
    por_regla = {s.regla: s for s in sugerir(sesion, ej)}
    assert {v.id for v in por_regla["varias_facturas_un_cargo"].vencimientos} == {a.id, b.id}
    assert [v.id for v in por_regla["dos_pagos"].vencimientos] == [g.id] and len(por_regla["dos_pagos"].lineas) == 2
    s = por_regla["dos_pagos"]
    r = conciliar_pagos(sesion, ej, s.vencimientos, s.lineas)  # aceptar una sugerencia
    assert (r.movimientos, r.saldados) == (2, 1) and s.clave.startswith("v") and "_l" in s.clave


def test_pagar_vencimientos_con_un_banco_de_socio_sin_linea_de_extracto(contab):
    from conta_pridalac.servicios.pagos_extracto import pagar_con_banco
    sesion, ej, almacen = contab
    a = pendiente_de_pago(sesion, ej, almacen, "Plenoil", 155.58, 30, "P-1", nif="B11111111")
    b = pendiente_de_pago(sesion, ej, almacen, "Hotel Palace", 57, 3, "H-1")
    cuenta = Cuenta(empresa_id=ej.empresa_id, codigo="55100002", nombre="BANCO JAVIER")
    sesion.add(cuenta)
    sesion.flush()
    javier = Banco(empresa_id=ej.empresa_id, numero=9, clase="B", nombre="BANCO JAVIER", cuenta_id=cuenta.id)
    sesion.add(javier)
    sesion.flush()
    r = pagar_con_banco(sesion, ej, [a, b], javier, date(2026, 9, 28))
    assert (r.movimientos, r.saldados) == (2, 2) and pendiente(sesion, a) == 0 and pendiente(sesion, b) == 0
    assert _saldo(sesion, "55100002") == D("-212.58") and {m.fecha for m in sesion.scalars(select(MovimientoBanco))} == {date(2026, 9, 28)}
    with pytest.raises(ErrorContable, match="ya está saldado"):
        pagar_con_banco(sesion, ej, [a], javier)
    otro = Banco(empresa_id=ej.empresa_id, numero=10, clase="B", nombre="SIN CUENTA")
    sesion.add(otro)
    sesion.flush()
    with pytest.raises(ErrorContable, match="tenga subcuenta"):
        pagar_con_banco(sesion, ej, [a], otro)


def test_un_descuento_del_extracto_se_junta_con_los_pagos_y_se_resta(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Solred", 222.41, 28, "S-1")
    l1, l2 = linea(sesion, ej, "SOLRED 1", -116.45, 1), linea(sesion, ej, "SOLRED 2", -110.50, 11)
    descuento = linea(sesion, ej, "DESCUENTO EXTRA SOLRED", 4.54, 21)
    r = conciliar_pagos(sesion, ej, [v], [l1, l2, descuento])
    assert (r.movimientos, r.saldados) == (3, 1) and pendiente(sesion, v) == 0
    assert _saldo(sesion, "57200001") == D("-222.41") and all(l.movimiento_id is not None for l in (l1, l2, descuento))
    importes = sorted(p.importe for m in sesion.scalars(select(MovimientoBanco)) for p in m.pagos)
    assert importes == [D("-116.45"), D("-110.50"), D("4.54")]


def test_un_abono_solo_no_es_un_pago(contab):
    sesion, ej, almacen = contab
    v = pendiente_de_pago(sesion, ej, almacen, "Solred", 50, 28, "S-1")
    with pytest.raises(ErrorContable, match="es un ingreso, no un pago"):
        conciliar_pagos(sesion, ej, [v], [linea(sesion, ej, "DESCUENTO", 4.54, 21)])


def test_los_abonos_solo_salen_en_las_lineas_libres_si_se_piden(contab):
    from conta_pridalac.servicios.pagos_extracto import lineas_libres
    sesion, ej, almacen = contab
    linea(sesion, ej, "PAGO", -10, 3)
    linea(sesion, ej, "DESCUENTO", 1, 4)
    assert [l.texto for l in lineas_libres(sesion, ej.empresa_id)] == ["PAGO"]
    assert [l.texto for l in lineas_libres(sesion, ej.empresa_id, con_abonos=True)] == ["PAGO", "DESCUENTO"]


# ---------------------------------------------------------------------------- Solred: cargos de la tarjeta que suman exactamente la factura


def _tarjeta(sesion, ej):
    cuenta = Cuenta(empresa_id=ej.empresa_id, codigo="52100001", nombre="TARJETA PTE PAGO")
    sesion.add(cuenta)
    sesion.flush()
    banco = Banco(empresa_id=ej.empresa_id, numero=7, clase="B", nombre="TARJETA", cuenta_id=cuenta.id)
    sesion.add(banco)
    sesion.flush()
    sesion.add(Extracto(empresa_id=ej.empresa_id, banco_id=banco.id, fichero="t.xlsx", huella="t", formato="tarjeta"))
    sesion.flush()
    return banco


def linea_de(sesion, ej, banco, texto, importe, dia):
    extracto = sesion.scalars(select(Extracto).where(Extracto.banco_id == banco.id)).first()
    n = len(list(sesion.scalars(select(ExtractoLinea)))) + 1
    l = ExtractoLinea(extracto_id=extracto.id, empresa_id=ej.empresa_id, banco_id=banco.id, orden=n, fecha=date(2026, 9, dia), texto=texto, importe=D(str(importe)), clave=f"t{n}")
    sesion.add(l)
    sesion.flush()
    return l


def test_los_cargos_de_la_tarjeta_que_suman_justo_una_factura_de_solred_se_sugieren(contab):
    sesion, ej, almacen = contab
    tarjeta = _tarjeta(sesion, ej)
    v = pendiente_de_pago(sesion, ej, almacen, "SOLRED, S.A.", 222.41, 28, "S-1", nif="A79707345")
    a, b = linea_de(sesion, ej, tarjeta, "E.S. AREA LA TORRETA, S.L", -114.12, 1), linea_de(sesion, ej, tarjeta, "E.S. AREA LA TORRETA, S.L", -108.29, 11)
    for texto, imp, dia in (("HOTEL PALACE", -50, 5), ("LA ATALAYA M.I.", -70, 6), ("OTRO ABONO", 4.54, 7)):  # ruido: líneas que no son de esta factura
        linea_de(sesion, ej, tarjeta, texto, imp, dia)
    s, = [x for x in sugerir(sesion, ej) if x.regla == "acumulado"]
    assert [x.id for x in s.vencimientos] == [v.id] and [l.id for l in s.lineas] == [a.id, b.id] and "suman exactamente 222.41" in s.motivo
    r = conciliar_pagos(sesion, ej, s.vencimientos, s.lineas)
    assert (r.movimientos, r.saldados) == (2, 1) and pendiente(sesion, v) == 0


def test_los_descuentos_de_solred_entran_en_la_suma_pero_solo_si_llevan_su_nombre(contab):
    sesion, ej, almacen = contab
    tarjeta = _tarjeta(sesion, ej)
    v = pendiente_de_pago(sesion, ej, almacen, "SOLRED, S.A.", 314.94, 30, "S-2", nif="A79707345")
    cargos = [linea_de(sesion, ej, tarjeta, t, -i, d) for t, i, d in (("LA ATALAYA M.I.", 133.92, 29), ("E.S.MACE S.L.", 69.77, 29), ("LA ATALAYA M.I.", 122.09, 30))]
    descuentos = [linea_de(sesion, ej, tarjeta, "DESCUENTO EXTRA SOLRED", i, d) for i, d in ((4.11, 21), (2.04, 29), (4.69, 30))]
    linea_de(sesion, ej, tarjeta, "DEVOLUCION TIENDA", 3.00, 28)  # un abono ajeno: no se usa
    s, = [x for x in sugerir(sesion, ej) if x.regla == "acumulado"]
    assert {l.id for l in s.lineas} == {l.id for l in cargos + descuentos} and "3 cargo(s) de la tarjeta y 3 descuento(s)" in s.motivo
    r = conciliar_pagos(sesion, ej, s.vencimientos, s.lineas)
    assert (r.movimientos, r.saldados) == (6, 1) and pendiente(sesion, v) == 0 and _saldo(sesion, "52100001") == D("-314.94")


def test_solo_los_proveedores_acumulados_y_solo_con_lineas_de_tarjeta(contab):
    sesion, ej, almacen = contab
    tarjeta = _tarjeta(sesion, ej)
    otro = pendiente_de_pago(sesion, ej, almacen, "Gasolinera Cualquiera", 100, 28, "G-1", nif="B33333333")
    linea_de(sesion, ej, tarjeta, "ALGO", -60, 1)
    linea_de(sesion, ej, tarjeta, "ALGO MAS", -40, 2)  # suman 100 justo, pero el proveedor no es de los acumulados
    assert [x for x in sugerir(sesion, ej) if x.regla == "acumulado"] == []
    solred = pendiente_de_pago(sesion, ej, almacen, "SOLRED, S.A.", 90, 28, "S-3", nif="A79707345")
    normal = sesion.scalars(select(Banco).where(Banco.nombre == "BANCO")).one()
    sesion.add(Extracto(empresa_id=ej.empresa_id, banco_id=normal.id, fichero="b.xlsx", huella="b", formato="bbva"))
    sesion.flush()
    linea_de(sesion, ej, normal, "UN CARGO DEL BANCO", -50, 3)  # el banco normal no es una tarjeta
    linea_de(sesion, ej, normal, "OTRO CARGO DEL BANCO", -40, 4)
    assert [x for x in sugerir(sesion, ej) if x.regla == "acumulado"] == []
    assert otro.id != solred.id
