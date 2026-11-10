"""Pantalla del registro de cambios: lo anotado, los filtros, la ficha de cada anotación y el aviso de cadena rota."""
import re

from sqlalchemy import select, text

from conta_pridalac.db.registro import RegistroCambio
from test_web_auditoria import _con_una_factura, _sesion, cliente  # noqa: F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/registro-cambios"


def test_la_pantalla_enseña_lo_anotado_y_la_cadena_integra(cliente):
    _con_una_factura(cliente)
    assert cliente.get(BASE).status_code == 200 and "Registro de cambios" in cliente.get("/e/prueba/2026").text
    html = cliente.get(f"{BASE}/tabla").text
    assert "Cadena íntegra" in html and "Situación de partida" in html and "factura_iva" in html and "Alta" in html


def test_se_filtra_por_operacion_y_por_tabla(cliente):
    _con_una_factura(cliente)
    solo_cambios = cliente.get(f"{BASE}/tabla", params={"operacion": "cambio"}).text
    assert "Situación de partida" not in solo_cambios
    solo_facturas = cliente.get(f"{BASE}/tabla", params={"tabla": "factura_iva"}).text
    assert "factura_iva" in solo_facturas and "asiento" not in solo_facturas.replace("Situación", "")


def test_la_ficha_de_una_anotacion_enseña_sus_datos(cliente):
    _con_una_factura(cliente)
    s = _sesion(cliente)
    alta = s.scalars(select(RegistroCambio).where(RegistroCambio.tabla == "factura", RegistroCambio.operacion == "alta")).first()
    inicio = s.scalars(select(RegistroCambio).order_by(RegistroCambio.id)).first()
    s.close()
    ficha = cliente.get(f"{BASE}/f/{alta.id}")
    assert ficha.status_code == 200 and "Fila creada" in ficha.text and "numero_factura" in ficha.text and alta.huella in ficha.text
    assert "Filas de cada tabla" in cliente.get(f"{BASE}/f/{inicio.id}").text
    assert cliente.get(f"{BASE}/f/9999999").status_code == 404


def test_si_la_cadena_se_rompe_la_pantalla_lo_dice(cliente):
    _con_una_factura(cliente)
    s = _sesion(cliente)
    s.execute(text("DROP TRIGGER registro_cambios_sin_update"))
    s.execute(text("UPDATE registro_cambios SET usuario = 'otro' WHERE id = 2"))
    s.commit()
    s.close()
    html = cliente.get(f"{BASE}/tabla").text
    assert "CADENA ROTA" in html and "ha sido modificada" in html and "Cadena íntegra" not in html
