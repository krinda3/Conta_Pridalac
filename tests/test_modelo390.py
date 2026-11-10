"""Cálculo del modelo 390 desde los libros: casillas por tipo, totales, resultado y controles contra los cuatro 303."""
import json
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaIva
from conta_pridalac.servicios.modelo390 import calcular_390

D = Decimal


@pytest.fixture
def libro(sesion):
    emp = Empresa(codigo=1, nombre="E")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=emp)
    sesion.add_all([emp, ej])
    sesion.flush()
    cuenta = Cuenta(empresa_id=emp.id, codigo="62800000", nombre="G")
    sesion.add(cuenta)
    sesion.flush()

    def factura(sentido, numero, fecha, *lineas, deducible=True, bien=False):
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"F{numero}", total=D("0"),
                    cuenta_tercero_id=cuenta.id, cuenta_contrapartida_id=cuenta.id)
        for base, pct, cuota in lineas:
            f.ivas.append(FacturaIva(base=D(base), pct_iva=D(pct), cuota_iva=D(cuota), deducible=deducible, bien_inversion=bien))
        sesion.add(f)
        sesion.flush()
        return f

    return sesion, ej, factura


def _con_todo(factura):
    factura("E", 1, date(2026, 7, 5), ("1000.00", "21", "210.00"), ("500.00", "10", "50.00"))
    factura("E", 2, date(2026, 8, 5), ("100.00", "4", "4.00"), ("300.00", "0", "0.00"))  # el 0 % va a la 700 en el 390
    factura("E", 3, date(2026, 10, 1), ("999.00", "21", "209.79"))  # otro trimestre del mismo año: el 390 es anual
    factura("R", 1, date(2026, 7, 9), ("200.00", "21", "42.00"), ("100.00", "10", "10.00"))
    factura("R", 2, date(2026, 9, 30), ("50.00", "21", "10.50"), deducible=False)  # IVA no deducible: sólo la base, a la 232
    factura("R", 3, date(2026, 9, 1), ("1000.00", "21", "210.00"), bien=True)  # bien de inversión: sus filas y los totales 50/51
    factura("R", 4, date(2026, 9, 2), ("-20.00", "21", "-4.20"))  # rectificativa: resta en su tipo
    factura("R", 5, date(2026, 5, 2), ("1700.00", "12", "204.00"))  # compra a un agricultor en régimen especial: casillas 60/61
    factura("R", 6, date(2026, 5, 3), ("100.00", "0", "0.00"))  # exenta: a ninguna fila
    factura("R", 7, date(2026, 5, 4), ("150.50", "22", "33.11"))  # un tipo que el formulario no tiene: entra en el total y avisa


def test_las_casillas_del_año_por_tipo_y_los_totales(libro):
    sesion, ej, factura = libro
    _con_todo(factura)
    c = calcular_390(sesion, ej)
    assert (c[700], c[701], c[1], c[2], c[3], c[4], c[5], c[6]) == (D("300.00"), D("0.00"), D("100.00"), D("4.00"), D("500.00"), D("50.00"), D("1999.00"), D("419.79"))
    assert (c[33], c[34], c[47]) == (D("2899.00"), D("473.79"), D("473.79"))
    assert (c[603], c[604], c[605], c[606]) == (D("100.00"), D("10.00"), D("180.00"), D("37.80"))  # 10 % y 21 % (con la rectificativa restando)
    assert (c[48], c[49]) == (D("430.50"), D("80.91"))  # los totales incluyen el 22 %, que no tiene fila
    assert (c[613], c[614], c[50], c[51]) == (D("1000.00"), D("210.00"), D("1000.00"), D("210.00"))
    assert (c[60], c[61]) == (D("1700.00"), D("204.00"))
    assert (c[64], c[65], c[84], c[85], c[86], c[97]) == (D("494.91"), D("-21.12"), D("-21.12"), D("0.00"), D("-21.12"), D("21.12"))
    assert (c[99], c[108], c[232]) == (D("2899.00"), D("2899.00"), D("50.00"))
    assert any("22.00 %" in a for a in c.avisos)


def test_con_los_303_sin_presentar_se_contrasta_con_los_calculados(libro):
    sesion, ej, factura = libro
    _con_todo(factura)
    c = calcular_390(sesion, ej)
    assert c.origen_303 == {1: "calculada", 2: "calculada", 3: "calculada", 4: "calculada"}
    assert [k.gravedad for k in c.controles if "cuotas devengadas" in k.texto] == ["ok"]
    assert [k.gravedad for k in c.controles if "cuotas deducibles" in k.texto] == ["ok"]
    assert any("no está presentado" in k.texto for k in c.controles)


def _presentar(sesion, ej, periodo, **casillas):
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=ej.anio, periodo=periodo, tipo=1, casillas=json.dumps({str(k): str(v) for k, v in casillas.items()})))
    sesion.flush()


def test_una_diferencia_con_lo_presentado_se_senala_con_su_importe(libro):
    sesion, ej, factura = libro
    factura("E", 1, date(2026, 2, 5), ("1000.00", "21", "210.00"))
    factura("R", 1, date(2026, 2, 9), ("500.00", "21", "105.00"))
    _presentar(sesion, ej, 1, **{"27": "210.00", "45": "91.65", "46": "118.35", "71": "118.35"})  # en el 303 del 1T se dedujeron 13,35 € menos que en las facturas
    for p in (2, 3, 4):
        _presentar(sesion, ej, p, **{"27": "0", "45": "0", "46": "0", "71": "0"})
    c = calcular_390(sesion, ej)
    assert c.origen_303 == {1: "presentada", 2: "presentada", 3: "presentada", 4: "presentada"}
    assert c[95] == D("118.35")  # los resultados a ingresar salen de lo presentado
    assert [k.gravedad for k in c.controles if "cuotas devengadas" in k.texto] == ["ok"]
    deducibles = [k for k in c.controles if "cuotas deducibles" in k.texto]
    assert [k.gravedad for k in deducibles] == ["aviso"] and "diferencia de 13,35 €" in deducibles[0].texto


def test_si_un_303_presentado_no_trae_casillas_no_se_compara_con_trimestres_sueltos(libro):
    sesion, ej, factura = libro
    factura("E", 1, date(2026, 2, 5), ("1000.00", "21", "210.00"))
    _presentar(sesion, ej, 1, **{"27": "210.00", "45": "0", "46": "210.00", "71": "210.00"})
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=ej.anio, periodo=4, tipo=1, casillas="{}"))  # importado sin casillas
    sesion.flush()
    c = calcular_390(sesion, ej)
    assert c.origen_303[4] == "presentada sin casillas"
    assert any("sin sus casillas" in k.texto for k in c.controles) and not any("coincide" in k.texto for k in c.controles)


def test_la_compensacion_del_ejercicio_anterior_se_aplica_hasta_donde_llega(libro):
    sesion, ej, factura = libro
    factura("E", 1, date(2026, 2, 5), ("1000.00", "21", "210.00"))
    _presentar(sesion, ej, 1, **{"27": "210.00", "45": "0", "46": "210.00", "71": "0.00", "110": "150.00"})  # el 1T traía 150 € pendientes de compensar del año anterior
    c = calcular_390(sesion, ej)
    assert (c[84], c[85], c[86]) == (D("210.00"), D("150.00"), D("60.00"))
    assert c[97] == D("0.00")
