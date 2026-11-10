"""Modelo 347 en la web: ejercicio, ficha, borrador, fichero, copia para presentar, registro con el PDF y borrado."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaIva, PresentacionAeat, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero347 import leer
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from test_justificante_aeat import pdf_de_la_sede

D = Decimal
BASE = "/e/prueba/2025/modelo-347"


@pytest.fixture(autouse=True)
def despues_del_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion347.hoy", lambda: date(2026, 3, 10))


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
    t = Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", codigo_postal="13001")
    s.add(t)
    s.flush()
    for numero, fecha, base in ((1, date(2025, 2, 3), "2000.00"), (2, date(2025, 11, 3), "1000.00")):
        cuota = (D(base) * D("0.21")).quantize(D("0.01"))
        f = Factura(ejercicio_id=ej.id, sentido="R", numero=numero, fecha_contable=fecha, fecha_factura=fecha, tercero_id=t.id, total=D(base) + cuota)
        f.ivas.append(FacturaIva(base=D(base), pct_iva=D("21"), cuota_iva=cuota))
        s.add(f)
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
    assert "/modelo-347" in cliente.get("/e/prueba/2025").text and cliente.get(BASE).status_code == 200
    assert "Declaraciones presentadas" in cliente.get(BASE).text
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Sin presentar" in tabla and "2025" in tabla


def test_la_ficha_calcula_los_declarados(cliente):
    ficha = cliente.get(f"{BASE}/f/0").text
    assert "Modelo 347 · ejercicio 2025" in ficha and "AGRICULTOR UNO" in ficha and "12345678Z" in ficha and "3.630,00" in ficha
    assert "disabled" not in re.findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]


def test_guardar_generar_descargar_y_copiar(cliente, monkeypatch):
    assert "Borrador guardado" in cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "normal"}).headers["HX-Trigger"]
    r = _generar(cliente)
    p = _presentaciones(cliente)[0]
    assert p.estado == "generada" and p.modelo == "347" and p.periodo == "0A" and "Ver lo que lleva el fichero" in r.text and p.fichero_nombre in r.text
    d = cliente.get(f"{BASE}/{p.id}/fichero")
    assert d.status_code == 200 and len(d.content) == 1004 and d.content.startswith(b"13472025B12345678")
    copia = json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    esperado = cliente.app.state.config.descargas / "EMPRESA_DE_PRUEBA_AEAT_347_2025_0A.347"
    assert copia == f"Copiado a {esperado}" and esperado.read_bytes() == d.content
    abiertas = []
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: abiertas.append(args))
    assert cliente.post(f"{BASE}/{p.id}/carpeta-copia").status_code == 200 and len(abiertas) == 1


def test_registrar_la_presentacion_con_el_pdf_y_pasar_a_sustitutiva(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ident = leer((cliente.app.state.config.almacen / p.fichero_ruta).read_bytes().decode("latin-1")).identificativo
    assert ident in cliente.get(f"{BASE}/f/0").text
    pdf = pdf_de_la_sede(modelo="347", registro="2025347009790900508614", justificante=ident, resultado="", nrc_importe=None, fecha="02-03-2026 a las 17:24:37")
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
    pdf = pdf_de_la_sede(modelo="347", registro="2025347009790900508614", justificante="3470000000001", resultado="", nrc_importe=None, fecha="02-03-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "lleva el 347" in r.text and _presentaciones(cliente)[0].estado == "generada"


def test_lo_importado_cuenta_como_presentado_y_sale_en_el_bloque_inferior(cliente):
    s = cliente.app.state.config.sesion("prueba")
    s.add(DeclaracionPresentada(empresa_id=s.scalars(select(Empresa)).first().id, modelo="347", anio=2025, periodo=0, tipo=1, justificante="3470224754049", resultado=D("3630.00"),
                                casillas=json.dumps({"declarados": 1, "total": 3630.0, "lista": [{"clave": "A", "nif": "12345678Z", "nombre": "AGRICULTOR UNO", "provincia": "13", "trimestres": [2420.0, 0, 0, 1210.0], "anual": 3630.0}]})))
    s.commit()
    s.close()
    assert "Presentado (importado)" in cliente.get(f"{BASE}/tabla").text
    inferior = cliente.get("/e/prueba/2025/declaraciones-347/tabla").text
    assert "3470224754049" in inferior and "1 fila" in inferior
    assert "AGRICULTOR UNO" in cliente.get("/e/prueba/2025/declaraciones-347/f/1").text
    assert "ya está presentado" in cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "normal"}).text


def test_se_borra_lo_pendiente(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ruta = cliente.app.state.config.almacen / p.fichero_ruta
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "eliminar_sin_presentar"})
    assert "Eliminado lo que no se presentó" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"] and not ruta.exists() and _presentaciones(cliente) == []
