"""Modelo 180 en la web: ejercicio, ficha, borrador, fichero, copia para presentar, registro con el PDF, borrado, ficha del proveedor y aviso de plazos."""
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
from conta_pridalac.ficheros_aeat.fichero180 import leer
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from test_justificante_aeat import pdf_de_la_sede

D = Decimal
BASE = "/e/prueba/2025/modelo-180"


@pytest.fixture(autouse=True)
def despues_del_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion180.hoy", lambda: date(2026, 1, 20))


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678", telefono="600111222", representante_nombre="PEREZ GOMEZ ANA")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("47510000", "H.P. RETENCIONES"), ("41000001", "CASERO UNO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    cuenta = s.scalars(select(Cuenta).where(Cuenta.codigo == "41000001")).one()
    s.add(Tercero(empresa_id=e.id, clase="P", nombre="CASERO UNO", nif="12345678Z", cuenta_id=cuenta.id, provincia_190="13", inmueble_situacion="1", inmueble_catastro="1234567VK1234S0001AB",
                  inmueble_tipo_via="CL", inmueble_via="MAYOR", inmueble_numero="12", inmueble_municipio="CIUDAD REAL", inmueble_codigo_municipio="13034", inmueble_provincia="13",
                  inmueble_codigo_postal="13001"))
    grabar_asiento(s, ej, tipo=2, numero=1, sub=0, fecha=date(2025, 2, 3), concepto="alquiler del local", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62100000", "1000.00"), ("47510000", "-190.00"), ("41000001", "-810.00"))])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _presentaciones(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return list(s.scalars(select(PresentacionAeat).order_by(PresentacionAeat.id)))
    finally:
        s.close()


def _generar(cliente, **extra):
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "generar", "tipo_presentacion": "normal", **extra})
    assert "Fichero generado" in r.headers["HX-Trigger"], r.text[:400]
    return r


def test_el_menu_y_el_listado_del_ejercicio(cliente):
    assert "/modelo-180" in cliente.get("/e/prueba/2025").text and cliente.get(BASE).status_code == 200
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Sin presentar" in tabla and "2025" in tabla


def test_la_ficha_calcula_los_arrendadores_y_su_inmueble(cliente):
    ficha = cliente.get(f"{BASE}/f/0").text
    assert "Modelo 180 · ejercicio 2025" in ficha and "CASERO UNO" in ficha and "12345678Z" in ficha and "1234567VK1234S0001AB" in ficha and "1.000,00" in ficha and "190,00" in ficha
    assert "CL MAYOR 12" in ficha and "CIUDAD REAL" in ficha and "19,00" in ficha
    assert "disabled" not in re.findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]


def test_guardar_generar_descargar_y_copiar(cliente, monkeypatch):
    assert "Borrador guardado" in cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "normal"}).headers["HX-Trigger"]
    r = _generar(cliente)
    p = _presentaciones(cliente)[0]
    assert p.estado == "generada" and p.modelo == "180" and p.periodo == "0A" and "Ver lo que lleva el fichero" in r.text and p.fichero_nombre in r.text
    d = cliente.get(f"{BASE}/{p.id}/fichero")
    assert d.status_code == 200 and len(d.content) == 1004 and d.content.startswith(b"11802025B12345678")
    copia = json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    esperado = cliente.app.state.config.descargas / "EMPRESA_DE_PRUEBA_AEAT_180_2025_0A.180"
    assert copia == f"Copiado a {esperado}" and esperado.read_bytes() == d.content
    abiertas = []
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: abiertas.append(args))
    assert cliente.post(f"{BASE}/{p.id}/carpeta-copia").status_code == 200 and len(abiertas) == 1


def test_registrar_la_presentacion_con_el_pdf_y_pasar_a_sustitutiva(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ident = leer((cliente.app.state.config.almacen / p.fichero_ruta).read_bytes().decode("latin-1")).identificativo
    assert ident in cliente.get(f"{BASE}/f/0").text
    pdf = pdf_de_la_sede(modelo="180", registro="2025180009950902801851", justificante=ident, resultado="", nrc_importe=None, fecha="20-01-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "leído del PDF" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], r.text[:300]
    p = _presentaciones(cliente)[0]
    assert p.estado == "presentada" and p.justificante == ident and "Presentación registrada" in r.text
    assert cliente.get(f"{BASE}/{p.id}/justificante").content == pdf
    assert "Presentado" in cliente.get(f"{BASE}/tabla").text
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "normal"})
    assert "ya está presentado" in r.text and len(_presentaciones(cliente)) == 1
    assert cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "sustitutiva"}).headers["HX-Trigger"]


def test_un_pdf_con_otro_justificante_no_se_registra(cliente):
    _generar(cliente)
    pdf = pdf_de_la_sede(modelo="180", registro="2025180009950902801851", justificante="1800000000001", resultado="", nrc_importe=None, fecha="20-01-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "lleva el 180" in r.text and _presentaciones(cliente)[0].estado == "generada"


def test_se_borra_lo_pendiente(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ruta = cliente.app.state.config.almacen / p.fichero_ruta
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "eliminar_sin_presentar"})
    assert "Eliminado lo que no se presentó" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"] and not ruta.exists() and _presentaciones(cliente) == []


def test_sin_los_datos_del_inmueble_no_se_genera(cliente):
    s = cliente.app.state.config.sesion("prueba")
    s.scalars(select(Tercero)).one().inmueble_catastro = None
    s.commit()
    s.close()
    ficha = cliente.get(f"{BASE}/f/0").text
    assert "referencia catastral" in ficha and "disabled" in re.findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "generar", "tipo_presentacion": "normal"})
    assert "No se puede generar el fichero" in r.text and _presentaciones(cliente)[0].estado == "borrador"


def test_la_ficha_del_proveedor_pide_los_datos_del_inmueble_y_los_guarda(cliente):
    formulario = cliente.get("/e/prueba/2025/proveedores/f/1").text
    assert "Inmueble que alquila (modelo 180)" in formulario and 'name="inmueble_catastro"' in formulario and 'name="inmueble_codigo_postal"' in formulario
    assert "Inmueble que alquila" not in cliente.get("/e/prueba/2025/clientes/nuevo").text


def test_el_panel_avisa_del_180_y_del_115_que_no_estan_presentados_y_vencidos(cliente, monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.hoy", lambda: date(2026, 2, 10))
    panel = cliente.get("/e/prueba/2025").text
    assert "modelo-180" in panel and "Abrir el modelo 180" in panel and "Abrir el modelo 115" in panel
    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.hoy", lambda: date(2025, 1, 5))
    assert "alertas-plazos" not in cliente.get("/e/prueba/2025").text
