"""Motor de conciliación: qué línea del extracto pagó cada factura."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.servicios.conciliacion import FacturaPorConciliar, LineaPorConciliar, coincide_el_texto, conciliar

D = Decimal


def f(id, nombre, total, dia, nif="B12345678"):
    return FacturaPorConciliar(id, nombre, nif, date(2026, 9, dia), D(str(total)))


def l(id, texto, importe, dia, valor=None):
    return LineaPorConciliar(id, date(2026, 9, dia), texto, D(str(importe)), date(2026, 9, valor) if valor else None)


def pares(resultado):
    return sorted((tuple(x.id for x in e.facturas), tuple(x.id for x in e.lineas), e.regla) for e in resultado.emparejadas)


@pytest.mark.parametrize("nombre, concepto, esperado", [
    ("PLENERGY GRUPO, S.L.", "PAGO CON TARJETA EN GASOLINERAS PLENERGY US305 MADRID", True),  # una palabra entera en común
    ("Amazon EU S.a.r.L.", "Compra AMAZON.ES", True),
    ("Hotel Palace S.L.", "HOTEL PALACE", True),
    ("Villalta Sativum S.L.", "TRANSFERENCIAS · VILLALTAsativum Pago Factura", True),  # una dentro de la otra
    ("Zentral Industrial S.A.", "ADEUDO ZENTRA IND", True),  # el banco trunca
    ("Brico Depot (MAJADAHONDA)", "BRICO DEPOT MAJADAHONDA", True),
    ("Comercial Agrocor SL", "PAGO CON TARJETA EN HOGAR, MUEBLES VILLALTA SA", False),
    ("Naturgy Iberia", "RECIBO ENDESA CLIENTES", False),
])
def test_el_nombre_se_parece_al_concepto_del_banco(nombre, concepto, esperado):
    assert coincide_el_texto(nombre, concepto) is esperado


def test_un_alias_del_usuario_junta_nombres_que_no_se_parecen():
    assert not coincide_el_texto("Comercial Agrocor SL", "VILLALTA SA")
    assert coincide_el_texto("Comercial Agrocor SL", "VILLALTA SA", [("agrocor", "villalta")])


def test_misma_cantidad_y_nombre_empareja():
    r = conciliar([f("1", "Iberdrola Clientes", 162.33, 5)], [l("a", "IBERDROLA CLIENT. Recibo de suministros", -162.33, 7), l("b", "OTRO", -50, 7)])
    assert pares(r) == [(("1",), ("a",), "importe_y_texto")] and [x.id for x in r.libres] == ["b"] and r.sin_conciliar == [] and r.dudosas == []


def test_dos_facturas_iguales_se_reparten_las_lineas_por_cercania_de_fecha():
    facturas = [f("viejo", "Securitas Direct", 165.66, 1), f("cerca", "Securitas Direct", 165.66, 6)]
    r = conciliar(facturas, [l("pago", "SECURITAS DIRECT Recibo", -165.66, 6)])
    assert pares(r) == [(("cerca",), ("pago",), "importe_y_texto")]  # la línea es para la factura de ese día, no para la primera que se mire
    assert [d.factura.id for d in r.dudosas] == ["viejo"] and "repetida" in r.dudosas[0].motivo  # y la otra, con la misma cantidad, se señala como posible repetida


def test_se_usa_la_fecha_valor_cuando_el_banco_la_da():
    r = conciliar([f("1", "Brico Depot", 116.40, 19), f("2", "Brico Depot", 116.40, 3)], [l("a", "BRICO DEPOT", -116.40, 21, valor=19), l("b", "BRICO DEPOT", -116.40, 4)])
    assert pares(r) == [(("1",), ("a",), "importe_y_texto"), (("2",), ("b",), "importe_y_texto")]


def test_lineas_identicas_del_mismo_dia_son_intercambiables():
    r = conciliar([f("1", "SEITT", 5.95, 2), f("2", "SEITT", 5.95, 2)], [l("a", "SEITT AP41", -5.95, 2), l("b", "SEITT AP41", -5.95, 2)])
    assert len(r.emparejadas) == 2 and r.dudosas == [] and r.libres == []


def test_importe_con_centimos_unico_empareja_aunque_el_nombre_no_se_parezca():
    r = conciliar([f("1", "Eurofins Analisis", 68.37, 25)], [l("a", "TRANSFERENCIAS · LABORATORIO CSR", -68.37, 25), l("b", "OTRO", -10, 3)])
    assert pares(r) == [(("1",), ("a",), "importe_unico")]


def test_misma_cantidad_redonda_el_mismo_dia_empareja_aunque_el_nombre_no_se_parezca():
    facturas = [f("1", "Ecollim Holdings", 17, 24), f("2", "Momentos Zhou", 17, 8)]
    r = conciliar(facturas, [l("x", "COMERCIO XABIA", -17, 8), l("y", "SP NATULIM", -17, 24)])
    assert pares(r) == [(("1",), ("y",), "importe_y_fecha"), (("2",), ("x",), "importe_y_fecha")]


def test_una_cantidad_redonda_en_otro_dia_con_otro_nombre_no_se_empareja_sola():
    r = conciliar([f("1", "Ecollim Holdings", 17, 10)], [l("x", "COMERCIO XABIA", -17, 8)])
    assert r.emparejadas == [] and [x.id for x in r.sin_conciliar] == ["1"]


def test_varias_facturas_un_solo_cargo():
    r = conciliar([f("1", "RENFE VIAJEROS S.A.", 66.10, 7), f("2", "RENFE VIAJEROS S.A.", 36.95, 7)], [l("a", "RENFE VIRTUAL INTERNET", -103.05, 8)])
    assert pares(r) == [(("1", "2"), ("a",), "varias_facturas_un_cargo")]


def test_una_factura_pagada_en_dos_veces():
    r = conciliar([f("1", "Belmo Muebles y Hogar", 3442.75, 1)], [l("a", "TRANSFERENCIAS · BELMO Muebles pago 2", -2000, 2), l("b", "TRANSFERENCIAS · BELMO Muebles pago 3", -1442.75, 20)])
    assert pares(r) == [(("1",), ("a", "b"), "dos_pagos")]


def test_otro_importe_con_el_mismo_nombre_y_fecha_cercana_queda_dudoso():
    r = conciliar([f("1", "HIPER HU", 158.07, 21)], [l("a", "HIPER HU", -158.10, 21)])
    assert r.emparejadas == [] and r.dudosas[0].factura.id == "1" and r.dudosas[0].candidatas[0].id == "a" and "otro importe" in r.dudosas[0].motivo


def test_una_factura_sin_nada_parecido_queda_sin_conciliar_y_se_listan_las_lineas_libres():
    r = conciliar([f("1", "Proveedor Raro", 99.99, 3)], [l("a", "COMISION MANTENIMIENTO", -6, 30)])
    assert [x.id for x in r.sin_conciliar] == ["1"] and [x.id for x in r.libres] == ["a"]


def test_las_emitidas_se_cobran_con_importes_positivos():
    r = conciliar([f("1", "CEMPRON S.A.", 1331, 28)], [l("a", "TRANSFERENCIA CEMPRON", 1331, 30), l("b", "CEMPRON devolucion", -1331, 30)], sentido="E")
    assert pares(r) == [(("1",), ("a",), "importe_y_texto")]


def test_un_abono_se_empareja_con_un_ingreso():
    r = conciliar([f("1", "Proveedor Uno", -50.25, 3)], [l("a", "ABONO PROVEEDOR UNO", 50.25, 4)])
    assert pares(r) == [(("1",), ("a",), "importe_y_texto")]


def test_una_linea_se_usa_una_sola_vez():
    r = conciliar([f("1", "Naturgy", 40.55, 3), f("2", "Naturgy Iberia", 40.55, 5)], [l("a", "NATURGY", -40.55, 4)])
    assert len(r.emparejadas) == 1 and len(r.dudosas) == 1 and r.dudosas[0].candidatas[0].id == "a"
