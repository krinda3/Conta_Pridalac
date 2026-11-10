"""Liquidación del IVA en la web."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, Parametro, Tercero, Vencimiento
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.tesoreria import crear_banco, pagar_vencimiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/liquidacion-iva"
T1, T2, T3 = "2026-03-31", "2026-06-30", "2026-09-30"


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("47200021", "IVA SOPORTADO 21"), ("47700021", "IVA REPERCUTIDO 21"), ("47000000", "HP DEUDORA IVA"), ("47500000", "HP ACREEDORA IVA"), ("40000001", "PROVEEDOR"),
                           ("43000001", "CLIENTE"), ("62900000", "GASTOS"), ("70000000", "VENTAS"), ("57200001", "BANCO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.add_all([Parametro(empresa_id=e.id, clave="IVA_DEBE", valor="47000000"), Parametro(empresa_id=e.id, clave="IVA_HABER", valor="47500000")])
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    prov, cli = Tercero(empresa_id=e.id, clase="P", nombre="Proveedor", cuenta_id=ids["40000001"]), Tercero(empresa_id=e.id, clase="C", nombre="Cliente", cuenta_id=ids["43000001"])
    s.add_all([prov, cli])
    s.flush()
    s.commit()
    s.close()
    cl = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))
    _factura(cl, "R", 1, date(2026, 2, 10), D("1000"))  # soportado 210 en el 1T
    _factura(cl, "E", 1, date(2026, 2, 20), D("500"))  # repercutido 105 en el 1T
    _factura(cl, "E", 2, date(2026, 5, 20), D("2000"))  # repercutido 420 en el 2T
    return cl


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _factura(cliente, sentido, numero, fecha, base):
    s = _sesion(cliente)
    try:
        ej = s.scalar(select(Ejercicio))
        ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
        recibida = sentido == "R"
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"{sentido}{numero}", total=base * D("1.21"),
                    tercero_id=s.scalar(select(Tercero.id).where(Tercero.clase == ("P" if recibida else "C"))), cuenta_tercero_id=ids["40000001" if recibida else "43000001"],
                    cuenta_contrapartida_id=ids["62900000" if recibida else "70000000"],
                    ivas=[FacturaIva(base=base, pct_iva=D("21.00"), cuota_iva=base * D("0.21"), cuenta_iva_id=ids["47200021" if recibida else "47700021"])])
        grabar_factura(s, ej, f)
        s.commit()
    finally:
        s.close()


def _liquidaciones(cliente):
    s = _sesion(cliente)
    try:
        return [(a.identificador, a.fecha, a.concepto, {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}) for a in s.scalars(select(Asiento).where(Asiento.subtipo == "P").order_by(Asiento.fecha))]
    finally:
        s.close()


def _vencimientos(cliente):
    s = _sesion(cliente)
    try:
        return [(v.fecha, v.importe) for v in s.scalars(select(Vencimiento).where(Vencimiento.origen_tipo == "X"))]
    finally:
        s.close()


def _disparo(r):
    assert "HX-Trigger" in r.headers, re.findall(r'role="alert">([^<]*)', r.text) or r.text[:300]
    return json.loads(r.headers["HX-Trigger"])


def _liquidar(cliente, periodo, **extra):
    return cliente.post(f"{BASE}/guardar", data={"id": periodo, "accion": "liquidar", **extra})


# ---------------------------------------------------------------------------- listado y ficha


def test_listado_de_periodos(cliente):
    assert cliente.get(BASE).status_code == 200 and "Liquidación del IVA" in cliente.get("/e/prueba/2026").text
    html = cliente.get(f"{BASE}/tabla").text
    assert "1 TRIM/2026" in html and "4 TRIM/2026" in html and "4 filas" in html
    assert html.count("Sin liquidar") == 2 and html.count("Sin IVA") == 2
    assert "210,00" in html and "105,00" in html and "420,00" in html
    assert 'data-clave="sentido">compensar<' in html and 'data-clave="sentido">pagar<' in html


def test_ficha_del_periodo_sin_liquidar(cliente):
    f = cliente.get(f"{BASE}/f/{T1}")
    assert f.status_code == 200 and "1 TRIM/2026" in f.text and "Sin liquidar" in f.text and "A compensar en periodos siguientes" in f.text and "Liquidar el periodo" in f.text
    assert "47200021" in f.text and "IVA SOPORTADO 21" in f.text and "Deshacer la liquidación" not in f.text
    sin = cliente.get(f"{BASE}/f/{T3}")
    assert "Sin IVA en el periodo" in sin.text and "Liquidar el periodo" not in sin.text


@pytest.mark.parametrize("id", ["2026-05-15", "basura", "2025-12-31"])
def test_periodos_no_validos(cliente, id):
    assert cliente.get(f"{BASE}/f/{id}").status_code == 404


# ---------------------------------------------------------------------------- liquidar, rehacer y deshacer


def test_liquidar_un_periodo_a_compensar(cliente):
    r = _liquidar(cliente, T1, compensar="on")
    assert "Liquidado" in r.text and "105,00 a compensar" in _disparo(r)["mensaje"]["texto"] and _disparo(r)["refrescar"]
    assert _liquidaciones(cliente) == [("9.1", date(2026, 3, 31), "REGUL. IVA 1 TRIM/2026", {"47200021": D("-210.00"), "47700021": D("105.00"), "47000000": D("105.00")})]
    assert _vencimientos(cliente) == []
    assert "Deshacer la liquidación" in r.text and "Volver a liquidar" in r.text
    tabla = cliente.get(f"{BASE}/tabla").text
    assert 'data-clave="estado">Liquidado<' in tabla and 'data-clave="asiento">9.1<' in tabla


def test_liquidar_a_pagar_compensa_y_crea_el_vencimiento(cliente):
    _liquidar(cliente, T1, compensar="on")
    vista = cliente.get(f"{BASE}/f/{T2}")
    assert "A pagar el 25/07/2026" in vista.text and "315,00" in vista.text and "Compensado de periodos anteriores" in vista.text
    r = _liquidar(cliente, T2, compensar="on")
    assert "a pagar 315,00 el 25/07/2026" in _disparo(r)["mensaje"]["texto"]
    asiento = _liquidaciones(cliente)[1]
    assert asiento[3] == {"47700021": D("420.00"), "47000000": D("-105.00"), "47500000": D("-315.00")}
    assert _vencimientos(cliente) == [(date(2026, 7, 25), D("-315.00"))]
    assert 'data-clave="pago">25/07/2026<' in cliente.get(f"{BASE}/tabla").text


def test_sin_compensar_se_paga_todo(cliente):
    _liquidar(cliente, T1, compensar="on")
    r = _liquidar(cliente, T2)  # la casilla sin marcar
    assert "a pagar 420,00" in _disparo(r)["mensaje"]["texto"] and _vencimientos(cliente) == [(date(2026, 7, 25), D("-420.00"))]


def test_recalcular_la_vista_no_graba_nada(cliente):
    _liquidar(cliente, T1, compensar="on")
    r = cliente.post(f"{BASE}/guardar", data={"id": T2, "accion": "ver"})
    assert "420,00" in r.text and "Compensado de periodos anteriores" not in r.text and len(_liquidaciones(cliente)) == 1


def test_una_liquidacion_se_queda_desactualizada_y_se_rehace(cliente):
    _liquidar(cliente, T1, compensar="on")
    _factura(cliente, "R", 2, date(2026, 3, 10), D("300"))  # 63 de IVA soportado más en el 1T, ya liquidado
    tabla = cliente.get(f"{BASE}/tabla").text
    assert 'data-clave="estado">Desactualizado<' in tabla and 'class="aviso-fila"' in tabla
    f = cliente.get(f"{BASE}/f/{T1}").text
    assert "ya no coincide" in f and "Grabado" in f and 'class="periodo-pendiente"' in f
    r = _liquidar(cliente, T1, compensar="on")
    assert "168,00 a compensar" in _disparo(r)["mensaje"]["texto"]  # 273 − 105
    liq = _liquidaciones(cliente)
    assert len(liq) == 1 and liq[0][0] == "9.1" and liq[0][3]["47000000"] == D("168.00")  # el mismo asiento, rehecho
    assert 'data-clave="estado">Liquidado<' in cliente.get(f"{BASE}/tabla").text


def test_deshacer_la_liquidacion(cliente):
    _liquidar(cliente, T1, compensar="on")
    _liquidar(cliente, T2, compensar="on")
    r = cliente.post(f"{BASE}/guardar", data={"id": T2, "accion": "deshacer"})
    assert "Liquidación deshecha" in _disparo(r)["mensaje"]["texto"] and len(_liquidaciones(cliente)) == 1 and _vencimientos(cliente) == []
    assert "no está liquidado" in cliente.post(f"{BASE}/guardar", data={"id": T2, "accion": "deshacer"}).text


def test_no_se_deshace_si_el_vencimiento_ya_esta_pagado(cliente):
    _liquidar(cliente, T1, compensar="on")
    _liquidar(cliente, T2, compensar="on")
    s = _sesion(cliente)
    ej = s.scalar(select(Ejercicio))
    banco = crear_banco(s, ej.empresa_id, "Banco", "57200001")
    pagar_vencimiento(s, ej, s.scalar(select(Vencimiento).where(Vencimiento.origen_tipo == "X")), banco, date(2026, 7, 25))
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": T2, "accion": "deshacer"})
    assert "cobros o pagos" in r.text and len(_liquidaciones(cliente)) == 2


def test_errores_al_liquidar(cliente):
    assert "No hay datos de IVA" in _liquidar(cliente, T3).text
    assert "Acción desconocida" in cliente.post(f"{BASE}/guardar", data={"id": T1, "accion": "inventada"}).text
    s = _sesion(cliente)
    s.scalar(select(Ejercicio)).cerrado = True
    s.commit()
    s.close()
    assert "cerrado" in _liquidar(cliente, T1).text and _liquidaciones(cliente) == []
    assert "disabled" in cliente.get(f"{BASE}/f/{T1}").text


# ---------------------------------------------------------------------------- parámetros


def test_parametros_del_iva(cliente):
    f = cliente.get(f"{BASE}/accion/parametros")
    assert f.status_code == 200 and 'value="47000000"' in f.text and "Trimestral" in f.text
    r = cliente.post(f"{BASE}/accion/parametros", data={"IVA_PERIODICIDAD": "12", "IVA_DIAS_PAGO": "20", "IVA_DEBE": "47000000", "IVA_HABER": "47500000"})
    assert r.text == "" and _disparo(r)["mensaje"]["texto"] == "Parámetros del IVA guardados"
    assert "12 filas" in cliente.get(f"{BASE}/tabla").text and "01/2026" in cliente.get(f"{BASE}/tabla").text
    r = _liquidar(cliente, "2026-02-28")  # febrero: sólo la factura recibida de 1000 € (210 de IVA soportado) y la emitida de 500 € (105)
    assert "105,00 a compensar" in _disparo(r)["mensaje"]["texto"] and _vencimientos(cliente) == []
    s = _sesion(cliente)
    assert s.scalar(select(Parametro.valor).where(Parametro.clave == "IVA_DIAS_PAGO")) == "20"
    s.close()


@pytest.mark.parametrize(
    "cambios, texto",
    [({"IVA_PERIODICIDAD": "5"}, "trimestral"), ({"IVA_DIAS_PAGO": "20,45"}, "números del 1 al 31"), ({"IVA_DIAS_PAGO": "a,b"}, "números del 1 al 31"),
     ({"IVA_DEBE": "99999999"}, "No existe la cuenta 99999999"), ({"IVA_HABER": ""}, "Falta la cuenta")],
)
def test_parametros_incorrectos(cliente, cambios, texto):
    datos = {"IVA_PERIODICIDAD": "4", "IVA_DIAS_PAGO": "", "IVA_DEBE": "47000000", "IVA_HABER": "47500000", **cambios}
    r = cliente.post(f"{BASE}/accion/parametros", data=datos)
    assert 'role="alert"' in r.text and texto in r.text


def test_sin_parametros_el_listado_avisa(cliente):
    s = _sesion(cliente)
    for p in s.scalars(select(Parametro)):
        s.delete(p)
    s.commit()
    s.close()
    html = cliente.get(f"{BASE}/tabla").text
    assert 'role="alert"' in html and "Faltan los parámetros IVA_DEBE e IVA_HABER" in html
    r = cliente.post(f"{BASE}/accion/parametros", data={"IVA_PERIODICIDAD": "4", "IVA_DEBE": "47000000", "IVA_HABER": "47500000"})
    assert r.text == "" and "Faltan" not in cliente.get(f"{BASE}/tabla").text


def test_el_listado_se_exporta(cliente):
    assert cliente.get(f"{BASE}/exportar.xlsx").status_code == 200
    assert cliente.get(f"{BASE}/exportar.pdf").headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_liquidaciones_reales(tmp_path):
    """Empresa A: 1T liquidado y 2T desactualizado; Empresa B: 1T desactualizado, 2T y 3T liquidados (lo que ya señalaba la auditoría)."""
    from conftest import EMPRESAS_MGD_2021, _carpeta_empresa

    from conta_pridalac.db.sesion import crear_motor
    from conta_pridalac.migracion.mgd import cargar_mgd

    (tmp_path / "bd").mkdir()
    for clave in ("empresa_a", "empresa_b"):
        origen = _carpeta_empresa(clave)
        if not (origen / "Diario.dbf").exists():
            pytest.skip(f"No hay datos MGD de {clave}")
        motor = crear_motor(tmp_path / "bd" / f"{clave}.sqlite")
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        d = EMPRESAS_MGD_2021[clave]
        cargar_mgd(sesion, origen, codigo_empresa=d["codigo"], nombre_empresa=d["nombre"], anio=2021)
        sesion.commit()
        sesion.close()
        motor.dispose()
    cliente = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "alm")))
    esperado = {"empresa_a": ["Liquidado", "Desactualizado"], "empresa_b": ["Desactualizado", "Liquidado", "Liquidado"]}
    for clave, estados in esperado.items():
        base = f"/e/{clave}/2021/liquidacion-iva"
        html = cliente.get(f"{base}/tabla").text
        assert 'role="alert"' not in html, clave
        assert re.findall(r'data-clave="estado">([^<]+)<', html)[: len(estados)] == estados, clave
        for periodo in ("2021-03-31", "2021-06-30", "2021-09-30", "2021-12-31"):
            assert cliente.get(f"{base}/f/{periodo}").status_code == 200
        assert "Periodicidad" in cliente.get(f"{base}/accion/parametros").text
