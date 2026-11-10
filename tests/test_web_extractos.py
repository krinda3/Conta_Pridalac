"""Pantallas de extractos: importar un fichero, ver las líneas, borrarlas y cuadrar cada banco con su Mayor."""
import re
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Empresa, Extracto, ExtractoLinea
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from test_extractos import CAIXA, TARJETA, excel

D = Decimal
BASE = "/e/prueba/2026/extractos"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)])
    s.flush()
    for codigo, nombre in (("57200001", "BANCO"), ("52100001", "TARJETA"), ("62900000", "SERVICIOS"), ("70000000", "VENTAS"), ("10000000", "CAPITAL")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    s.add_all([Banco(empresa_id=e.id, numero=1, nombre="CAIXABANK", cuenta_id=ids["57200001"]), Banco(empresa_id=e.id, numero=2, nombre="TARJETA LA CAIXA", cuenta_id=ids["52100001"])])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _banco(cliente, nombre="CAIXABANK") -> int:
    s = _sesion(cliente)
    try:
        return s.scalar(select(Banco.id).where(Banco.nombre == nombre))
    finally:
        s.close()


def importar(cliente, contenido=CAIXA, nombre="caixa.xlsx", banco="CAIXABANK", **datos):
    return cliente.post(f"{BASE}/accion/importar", data={"banco": str(_banco(cliente, banco)), "signo": "", **datos}, files={"fichero": (nombre, contenido, XLSX)})


def test_el_menu_ofrece_extractos_y_cuadre_en_tesoreria(cliente):
    pagina = cliente.get("/e/prueba/2026").text
    assert f'href="{BASE}"' in pagina and 'href="/e/prueba/2026/cuadre-bancos"' in pagina
    assert cliente.get(BASE).status_code == 200 and cliente.get("/e/prueba/2026/cuadre-bancos").status_code == 200


def test_el_formulario_de_importar_ofrece_los_bancos(cliente):
    f = cliente.get(f"{BASE}/accion/importar")
    assert f.status_code == 200 and "CAIXABANK" in f.text and "TARJETA LA CAIXA" in f.text and 'type="file"' in f.text


def test_importar_un_extracto_enseña_el_resultado_y_deja_las_lineas(cliente):
    r = importar(cliente)
    assert r.status_code == 200 and "Extracto importado" in r.text and "formato CaixaBank" in r.text
    assert re.search(r"Líneas del fichero</span><strong>3<", r.text) and re.search(r"Nuevas</span><strong>3<", r.text) and "Faltan líneas" not in r.text
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "V.NEGOCIOS CRED." in tabla and "IBERDROLA CLIENT." in tabla and "-100,50" in tabla and "900,00" in tabla
    repetido = importar(cliente)  # el mismo fichero otra vez: no se añade nada
    assert re.search(r"Nuevas</span><strong>0<", repetido.text) and re.search(r"Ya estaban</span><strong>3<", repetido.text) and "ya se había importado" in repetido.text
    assert tabla.count("V.NEGOCIOS CRED.") == cliente.get(f"{BASE}/tabla").text.count("V.NEGOCIOS CRED.") == 1


def test_importar_avisa_cuando_el_saldo_no_encaja(cliente):
    falta = excel([["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"], [datetime(2026, 3, 10), None, "A", "", -100.5, 900.0], [datetime(2026, 3, 1), None, "C", "", 300.5, 1200.5]])
    r = importar(cliente, falta)
    assert "Faltan líneas en el extracto" in r.text and "-200,00" in r.text


def test_la_tarjeta_se_importa_con_los_gastos_como_cargos(cliente):
    r = importar(cliente, TARJETA, "tarjeta.xlsx", banco="TARJETA LA CAIXA")
    assert "gastos venían en positivo" in r.text
    s = _sesion(cliente)
    assert sorted(l.importe for l in s.scalars(select(ExtractoLinea))) == [D("-1041.10"), D("-29.70"), D("8.25")]
    s.close()


def test_los_errores_de_importar_se_dicen_en_el_dialogo(cliente):
    sin_banco = cliente.post(f"{BASE}/accion/importar", data={"banco": ""}, files={"fichero": ("c.xlsx", CAIXA, XLSX)})
    assert "Elija el banco o la tarjeta" in sin_banco.text
    sin_fichero = cliente.post(f"{BASE}/accion/importar", data={"banco": str(_banco(cliente))})
    assert "Elija el fichero Excel" in sin_fichero.text
    assert "No se puede abrir el Excel" in importar(cliente, b"esto no es un excel", "malo.xlsx").text
    assert "No reconozco el formato" in importar(cliente, excel([["a", "b"], [1, 2]]), "otro.xlsx").text


def test_se_pueden_borrar_lineas_y_el_extracto_vacio_desaparece(cliente):
    importar(cliente)
    s = _sesion(cliente)
    ids = [str(i) for i in s.scalars(select(ExtractoLinea.id))]
    s.close()
    assert cliente.post(f"{BASE}/borrar", data={"ids": ids[:2]}).status_code == 200
    s = _sesion(cliente)
    assert len(list(s.scalars(select(ExtractoLinea)))) == 1 and len(list(s.scalars(select(Extracto)))) == 1
    s.close()
    cliente.post(f"{BASE}/borrar", data={"ids": ids[2:]})
    s = _sesion(cliente)
    assert not list(s.scalars(select(Extracto)))
    s.close()


def _mayor(cliente, movimientos):
    s = _sesion(cliente)
    ej = s.scalar(select(Ejercicio))
    for n, (fecha, importe, subtipo, contra) in enumerate(movimientos, start=1):
        grabar_asiento(s, ej, tipo=4, numero=n, sub=0, fecha=fecha, concepto="prueba", subtipo=subtipo, lineas=[LineaAsiento("57200001", D(importe)), LineaAsiento(contra, -D(importe))])
    s.commit()
    s.close()


def test_el_cuadre_dice_que_cuadra(cliente):
    importar(cliente)
    _mayor(cliente, [(date(2026, 1, 1), "900.00", "A", "10000000"), (date(2026, 3, 1), "300.50", None, "70000000"), (date(2026, 3, 5), "-200.00", None, "62900000"), (date(2026, 3, 10), "-100.50", None, "62900000")])
    r = cliente.get(f"/e/prueba/2026/cuadre-bancos/tabla", params={"banco": str(_banco(cliente))}).text
    assert "CUADRA · CAIXABANK" in r and "NO CUADRA" not in r and "3 emparejadas" in r and "Sólo en el" not in r


def test_el_cuadre_enseña_lo_que_sobra_en_cada_lado(cliente):
    importar(cliente)
    _mayor(cliente, [(date(2026, 1, 1), "900.00", "A", "10000000"), (date(2026, 3, 1), "300.50", None, "70000000"), (date(2026, 3, 10), "-100.50", None, "62900000"), (date(2026, 3, 8), "-77.00", None, "62900000")])
    r = cliente.get("/e/prueba/2026/cuadre-bancos/tabla", params={"banco": str(_banco(cliente))}).text
    assert "NO CUADRA · CAIXABANK" in r and "Sólo en el extracto" in r and "Sólo en el Mayor" in r and "V.NEGOCIOS CRED." in r and "-200,00" in r and "-77,00" in r and "Diferencia" in r


def test_el_cuadre_sin_extractos_lo_explica(cliente):
    r = cliente.get("/e/prueba/2026/cuadre-bancos/tabla", params={"banco": str(_banco(cliente))}).text
    assert "no tiene extractos importados" in r
