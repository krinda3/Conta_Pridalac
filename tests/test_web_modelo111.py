"""Modelo 111 en la web: trimestres, ficha, borrador, fichero, copia para presentar, registro con el PDF y borrado."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, PresentacionAeat, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from test_justificante_aeat import pdf_de_la_sede

D = Decimal
BASE = "/e/prueba/2026/modelo-111"


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. RETENCIONES"), ("41000132", "AGRICULTOR UNO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    cuenta = s.scalars(select(Cuenta).where(Cuenta.codigo == "41000132")).one()
    s.add(Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", cuenta_id=cuenta.id))
    grabar_asiento(s, ej, tipo=2, numero=1, sub=0, fecha=date(2026, 2, 3), concepto="compra a agricultor", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62300000", "1000.00"), ("47200000", "120.00"), ("47510000", "-22.40"), ("41000132", "22.40"), ("41000132", "-1120.00"))])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _presentaciones(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return list(s.scalars(select(PresentacionAeat).order_by(PresentacionAeat.id)))
    finally:
        s.close()


def _generar(cliente, periodo="1", **extra):
    r = cliente.post(f"{BASE}/guardar", data={"id": periodo, "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion", **extra})
    assert "Fichero generado" in r.headers["HX-Trigger"], r.text[:300]
    return r


def test_el_menu_y_el_listado_de_trimestres(cliente):
    assert "/modelo-111" in cliente.get("/e/prueba/2026").text and cliente.get(BASE).status_code == 200
    pagina = cliente.get(BASE).text
    assert "Declaraciones presentadas" in pagina and "/e/prueba/2026/declaraciones-111/tabla" in pagina
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "1T 2026" in tabla and "4T 2026" in tabla and tabla.count("Sin presentar") == 4


def test_la_ficha_calcula_las_retenciones_y_ofrece_generar(cliente):
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "Modelo 111 · 1T 2026" in ficha and "22,40" in ficha and "AGRICULTOR UNO" in ficha and "12345678Z" in ficha
    assert "disabled" not in re.findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]
    sin = cliente.get(f"{BASE}/f/2").text
    assert "No hay retenciones que ingresar" in sin and "Sin errores ni avisos" in sin
    assert cliente.get(f"{BASE}/f/5").status_code == 404 and cliente.get(f"{BASE}/f/x").status_code == 404


def test_guardar_generar_descargar_y_copiar(cliente, monkeypatch):
    assert "Borrador guardado" in cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"}).headers["HX-Trigger"]
    r = _generar(cliente)
    p = _presentaciones(cliente)[0]
    assert p.estado == "generada" and p.modelo == "111" and p.tipo_declaracion == "U" and f"/modelo-111/{p.id}/fichero" in r.text and "Ver lo que lleva el fichero" in r.text
    d = cliente.get(f"{BASE}/{p.id}/fichero")
    assert d.status_code == 200 and len(d.content) == 1346 and d.content.startswith(b"<T111020261T0000>")
    copia = json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    esperado = cliente.app.state.config.descargas / "EMPRESA_DE_PRUEBA_AEAT_111_2026_1T.111"
    assert copia == f"Copiado a {esperado}" and esperado.read_bytes() == d.content
    abiertas = []
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: abiertas.append(args))
    assert cliente.post(f"{BASE}/{p.id}/carpeta-copia").status_code == 200 and len(abiertas) == 1
    assert "Copiar fichero para presentar" in cliente.get(BASE).text
    dialogo = cliente.get(f"{BASE}/accion/copiar").text
    assert "EMPRESA_DE_PRUEBA_AEAT_111_2026_1T.111" in dialogo


def test_un_trimestre_sin_retenciones_genera_un_fichero_sin_actividad(cliente):
    _generar(cliente, "2")
    p = _presentaciones(cliente)[0]
    assert p.tipo_declaracion == "N" and p.resultado == D("0.00")


def test_registrar_la_presentacion_con_el_pdf_y_bloquear_el_trimestre(cliente):
    _generar(cliente)
    pdf = pdf_de_la_sede(modelo="111", registro="202611100790771G", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="14-01-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "leído del PDF" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], r.text[:300]
    p = _presentaciones(cliente)[0]
    assert p.estado == "presentada" and p.justificante == "3036479211552" and "Presentación registrada" in r.text
    assert cliente.get(f"{BASE}/{p.id}/justificante").content == pdf
    assert "Presentado" in cliente.get(f"{BASE}/tabla").text and 'class="sel"' not in cliente.get(f"{BASE}/tabla").text
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal"})
    assert "ya está presentado" in r.text and len(_presentaciones(cliente)) == 1


def test_un_pdf_de_otro_modelo_no_se_registra(cliente):
    _generar(cliente)
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf_de_la_sede(modelo="303"), "application/pdf")})
    assert "del modelo 303" in r.text and _presentaciones(cliente)[0].estado == "generada"


def test_lo_importado_de_programa_anterior_cuenta_como_presentado_y_sale_en_el_bloque_inferior(cliente):
    s = cliente.app.state.config.sesion("prueba")
    s.add(DeclaracionPresentada(empresa_id=s.scalars(select(Empresa)).first().id, modelo="111", anio=2026, periodo=1, tipo=1, justificante="1116996603852", resultado=D("22.40"), resultado_liquidacion=D("22.40"),
                                casillas=json.dumps({"7": 1, "8": 1120.0, "9": 22.4, "28": 22.4, "30": 22.4})))
    s.add(DeclaracionPresentada(empresa_id=s.scalars(select(Empresa)).first().id, modelo="303", anio=2026, periodo=1, tipo=1, casillas="{}"))
    s.commit()
    s.close()
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Presentado (importado)" in tabla and "1116996603852" in tabla
    inferior = cliente.get("/e/prueba/2026/declaraciones-111/tabla").text
    assert "1116996603852" in inferior and "1 fila" in inferior  # sólo el 111, no el 303
    assert "Casilla 28" in cliente.get("/e/prueba/2026/declaraciones-111/f/1").text
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal"})
    assert "ya está presentado" in r.text
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "complementaria" in ficha.lower() and "Ver la declaración" in ficha
    assert cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "complementaria", "forma_pago": "domiciliacion"}).headers["HX-Trigger"]


def test_se_borra_lo_pendiente_y_no_se_ofrece_lo_presentado(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ruta = cliente.app.state.config.almacen / p.fichero_ruta
    assert 'class="sel"' in cliente.get(f"{BASE}/tabla").text and "Eliminar lo no presentado (1)" in cliente.get(f"{BASE}/f/1").text
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "eliminar_sin_presentar"})
    assert "Eliminado lo que no se presentó" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"] and not ruta.exists() and _presentaciones(cliente) == []
    assert "No hay borradores ni ficheros sin presentar" in cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "eliminar_sin_presentar"}).text
