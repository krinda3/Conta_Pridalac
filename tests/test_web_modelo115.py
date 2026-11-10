"""Modelo 115 en la web: trimestres, ficha, fichero, copia, registro con el PDF y el paso del asistente del trimestre."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, PresentacionAeat, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from test_justificante_aeat import pdf_de_la_sede

D = Decimal
BASE = "/e/prueba/2026/modelo-115"


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))
    monkeypatch.setattr("conta_pridalac.servicios.presentacion115.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Asociación de Prueba", nif="G12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. RETENCIONES"), ("41000001", "CASERO UNO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    cuenta = s.scalars(select(Cuenta).where(Cuenta.codigo == "41000001")).one()
    s.add(Tercero(empresa_id=e.id, clase="P", nombre="CASERO UNO", nif="12345678Z", cuenta_id=cuenta.id))
    grabar_asiento(s, ej, tipo=2, numero=1, sub=0, fecha=date(2026, 2, 3), concepto="alquiler del local", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62100000", "1000.00"), ("47200000", "210.00"), ("47510000", "-190.00"), ("41000001", "-1020.00"))])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _presentaciones(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return list(s.scalars(select(PresentacionAeat).order_by(PresentacionAeat.id)))
    finally:
        s.close()


def _generar(cliente, periodo="1"):
    r = cliente.post(f"{BASE}/guardar", data={"id": periodo, "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"})
    assert "Fichero generado" in r.headers["HX-Trigger"], r.text[:300]
    return r


def test_el_menu_y_el_listado_de_trimestres(cliente):
    assert "/modelo-115" in cliente.get("/e/prueba/2026").text and cliente.get(BASE).status_code == 200
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "1T 2026" in tabla and "4T 2026" in tabla and tabla.count("Sin presentar") == 4


def test_la_ficha_calcula_la_retencion_del_alquiler(cliente):
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "Modelo 115 · 1T 2026" in ficha and "190,00" in ficha and "CASERO UNO" in ficha and "12345678Z" in ficha
    assert "disabled" not in re.findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]
    assert "No hay retenciones de alquileres" in cliente.get(f"{BASE}/f/2").text
    assert cliente.get(f"{BASE}/f/5").status_code == 404 and cliente.get(f"{BASE}/f/x").status_code == 404


def test_generar_descargar_y_copiar(cliente):
    r = _generar(cliente)
    p = _presentaciones(cliente)[0]
    assert p.estado == "generada" and p.modelo == "115" and p.tipo_declaracion == "U" and f"/modelo-115/{p.id}/fichero" in r.text
    d = cliente.get(f"{BASE}/{p.id}/fichero")
    assert d.status_code == 200 and len(d.content) == 846 and d.content.startswith(b"<T115020261T0000>")
    copia = json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    esperado = cliente.app.state.config.descargas / "ASOCIACION_DE_PRUEBA_AEAT_115_2026_1T.115"
    assert copia == f"Copiado a {esperado}" and esperado.read_bytes() == d.content


def test_registrar_la_presentacion_con_el_pdf_y_bloquear_el_trimestre(cliente):
    _generar(cliente)
    pdf = pdf_de_la_sede(modelo="115", registro="202611500790771G", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="14-01-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "leído del PDF" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], r.text[:300]
    p = _presentaciones(cliente)[0]
    assert p.estado == "presentada" and cliente.get(f"{BASE}/{p.id}/justificante").content == pdf
    assert "Presentado" in cliente.get(f"{BASE}/tabla").text


def test_el_asistente_del_trimestre_sigue_funcionando_con_el_115(cliente):
    assert cliente.get("/e/prueba/2026/trimestre/tabla").status_code == 200
