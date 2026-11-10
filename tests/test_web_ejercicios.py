"""Cierre y apertura del ejercicio en la web."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, Parametro, Tercero, Vencimiento
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, definir_vencimientos
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/ejercicios"


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
    for codigo, nombre in (("10000000", "CAPITAL"), ("57200001", "BANCO"), ("12900000", "PERDIDAS Y GANANCIAS"), ("47200021", "IVA SOPORTADO"), ("47700021", "IVA REPERCUTIDO"),
                           ("47000000", "HP DEUDORA IVA"), ("47500000", "HP ACREEDORA IVA"), ("40000001", "PROVEEDOR"), ("43000001", "CLIENTE"), ("62900000", "GASTOS"), ("70000000", "VENTAS")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.add_all([Parametro(empresa_id=e.id, clave=c, valor=v) for c, v in (("PYG", "12900000"), ("IVA_DEBE", "47000000"), ("IVA_HABER", "47500000"))])
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    prov, cli = Tercero(empresa_id=e.id, clase="P", nombre="Proveedor", cuenta_id=ids["40000001"]), Tercero(empresa_id=e.id, clase="C", nombre="Cliente", cuenta_id=ids["43000001"])
    s.add_all([prov, cli])
    s.flush()
    grabar_asiento(s, ej, tipo=4, numero=1, fecha=date(2026, 1, 2), concepto="CAPITAL", lineas=[LineaAsiento("57200001", D(5000)), LineaAsiento("10000000", D(-5000))])
    for sentido, numero, tercero, base, fecha in (("R", 1, prov, D("1000"), date(2026, 2, 10)), ("E", 1, cli, D("3000"), date(2026, 2, 20))):
        recibida = sentido == "R"
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"{sentido}1", total=base * D("1.21"), tercero_id=tercero.id,
                    cuenta_tercero_id=ids["40000001" if recibida else "43000001"], cuenta_contrapartida_id=ids["62900000" if recibida else "70000000"],
                    ivas=[FacturaIva(base=base, pct_iva=D("21.00"), cuota_iva=base * D("0.21"), cuenta_iva_id=ids["47200021" if recibida else "47700021"])])
        grabar_factura(s, ej, f)
        definir_vencimientos(s, ej, f, [PlazoVencimiento(importe=f.total, fecha=date(2026, 3, 15))])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _estado(cliente):
    s = _sesion(cliente)
    try:
        return {
            "ejercicios": {e.anio: e.cerrado for e in s.scalars(select(Ejercicio))},
            "subtipos": sorted((anio, subtipo) for anio, subtipo in s.execute(select(Ejercicio.anio, Asiento.subtipo).join(Asiento, Asiento.ejercicio_id == Ejercicio.id)) if subtipo in ("R", "Z", "A")),
        }
    finally:
        s.close()


def _disparo(r):
    assert "HX-Trigger" in r.headers, re.findall(r'role="alert">([^<]*)', r.text) or r.text[:300]
    return json.loads(r.headers["HX-Trigger"])


def _cerrar(cliente, anio=2026, **extra):
    return cliente.post(f"{BASE}/guardar", data={"id": str(anio), "accion": "cerrar", "abrir_siguiente": "on", **extra})


# ---------------------------------------------------------------------------- listado y ficha


def test_listado_de_ejercicios(cliente):
    assert cliente.get(BASE).status_code == 200 and "Cierre del ejercicio" in cliente.get("/e/prueba/2026").text
    html = cliente.get(f"{BASE}/tabla").text
    assert "1 fila" in html and "Abierto" in html and "2.000,00" in html and 'data-id="2026"' in html


def test_ficha_con_la_lista_de_comprobacion(cliente):
    f = cliente.get(f"{BASE}/f/2026")
    assert f.status_code == 200
    for esperado in ("Ejercicio 2026", "Abierto", "Resultado provisional (beneficio)", "2.000,00", "Auditoría de integridad", "Sin errores", "Liquidaciones del IVA", "sin liquidar",
                     "Amortización de los bienes", "Todo amortizado", "2 cuenta(s) de los grupos 6 y 7", "2 por 4.840,00 pendientes", "Cerrar el ejercicio", "Abrir el ejercicio siguiente"):
        assert esperado in f.text, esperado
    assert "disabled" not in f.text.split("Cerrar el ejercicio")[0].rsplit("<button", 1)[-1]  # el botón de cerrar está activo


@pytest.mark.parametrize("id", ["1999", "abc"])
def test_ejercicios_inexistentes(cliente, id):
    assert cliente.get(f"{BASE}/f/{id}").status_code == 404


# ---------------------------------------------------------------------------- cerrar y reabrir


def test_cerrar_el_ejercicio_y_abrir_el_siguiente(cliente):
    r = _cerrar(cliente)
    texto = _disparo(r)["mensaje"]["texto"]
    assert "Ejercicio 2026 cerrado. Beneficio del ejercicio: 2000,00" in texto and "Abierto el 2027 con 2 vencimiento(s) arrastrado(s)" in texto
    assert "Cerrado" in r.text and "Reabrir el ejercicio" in r.text and "Cerrar el ejercicio" not in r.text
    assert _estado(cliente) == {"ejercicios": {2026: True, 2027: False}, "subtipos": [(2026, "R"), (2026, "Z"), (2027, "A")]}
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "2 filas" in tabla and "Cerrado" in tabla and "9.2" in tabla and "9.1 (2027)" in tabla
    assert "ya está cerrado" in _cerrar(cliente).text


def test_cerrar_sin_abrir_el_siguiente(cliente):
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "cerrar"})
    assert "cerrado" in _disparo(r)["mensaje"]["texto"] and "Abierto el" not in _disparo(r)["mensaje"]["texto"]
    assert _estado(cliente)["ejercicios"] == {2026: True}


def test_el_ejercicio_cerrado_ya_no_admite_movimientos(cliente):
    _cerrar(cliente)
    r = cliente.post("/e/prueba/2026/asientos/guardar", data={"fecha": "150326", "concepto": "x", "ln-0-cuenta": "57200001", "ln-0-dh": "D", "ln-0-importe": "10", "ln-1-cuenta": "10000000", "ln-1-dh": "H", "ln-1-importe": "10"})
    assert "cerrado" in r.text


def test_reabrir_el_ejercicio(cliente):
    _cerrar(cliente)
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "reabrir"})
    assert "Ejercicio 2026 reabierto" in _disparo(r)["mensaje"]["texto"] and "Cerrar el ejercicio" in r.text
    est = _estado(cliente)
    assert est["ejercicios"] == {2026: False} and est["subtipos"] == []  # ni cierre, ni regularización, ni apertura
    assert "no está cerrado" in cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "reabrir"}).text
    assert "cerrado" in _disparo(_cerrar(cliente))["mensaje"]["texto"]  # se puede volver a cerrar


def test_no_se_reabre_si_el_siguiente_ya_tiene_movimientos(cliente):
    _cerrar(cliente)
    s = _sesion(cliente)
    ej27 = s.scalar(select(Ejercicio).where(Ejercicio.anio == 2027))
    grabar_asiento(s, ej27, tipo=4, numero=1, fecha=date(2027, 1, 5), lineas=[LineaAsiento("57200001", D(10)), LineaAsiento("10000000", D(-10))])
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "reabrir"})
    assert "ya tiene movimientos además de la apertura" in r.text and _estado(cliente)["ejercicios"][2026] is True


def test_la_auditoria_con_errores_bloquea_el_cierre(cliente):
    s = _sesion(cliente)
    s.execute(delete(Asiento).where(Asiento.tipo == 2))  # una factura recibida sin su asiento: error de integridad
    s.commit()
    s.close()
    f = cliente.get(f"{BASE}/f/2026")
    assert "bloquean el cierre" in f.text and "lista-errores" in f.text and 'disabled title="La auditoría tiene errores"' in f.text
    r = _cerrar(cliente)
    assert "La auditoría tiene" in r.text and _estado(cliente)["ejercicios"] == {2026: False} and _estado(cliente)["subtipos"] == []  # no se creó nada a medias


def test_accion_desconocida(cliente):
    assert "Acción desconocida" in cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "inventada"}).text
    assert "no existe" in cliente.post(f"{BASE}/guardar", data={"id": "1999", "accion": "cerrar"}).text


# ---------------------------------------------------------------------------- nuevo ejercicio


def test_nuevo_ejercicio(cliente):
    f = cliente.get(f"{BASE}/accion/nuevo")
    assert f.status_code == 200 and 'value="2027"' in f.text
    r = cliente.post(f"{BASE}/accion/nuevo", data={"anio": "2028"})
    assert r.text == "" and "Ejercicio 2028 creado" in _disparo(r)["mensaje"]["texto"]
    assert _estado(cliente)["ejercicios"] == {2026: False, 2028: False}
    assert "2028" in cliente.get("/e/prueba/2028/ejercicios").text  # ya se puede elegir arriba
    assert "2 filas" in cliente.get(f"{BASE}/tabla").text


@pytest.mark.parametrize("anio, texto", [("2026", "Ya existe"), ("abc", "entre 1990 y 2100"), ("1800", "entre 1990 y 2100"), ("", "entre 1990 y 2100")])
def test_nuevo_ejercicio_incorrecto(cliente, anio, texto):
    r = cliente.post(f"{BASE}/accion/nuevo", data={"anio": anio})
    assert 'role="alert"' in r.text and texto in r.text


def test_el_listado_se_exporta(cliente):
    assert cliente.get(f"{BASE}/exportar.xlsx").status_code == 200


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_cierre_con_los_datos_reales(tmp_path):
    """Empresa A se cierra y abre 2022; Empresa B no se puede cerrar mientras haya asientos fechados en 2020 (error de la auditoría) y no queda nada a medias."""
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

    def subtipos(clave):
        s = cliente.app.state.config.sesion(clave)
        try:
            return sorted((anio, subtipo) for anio, subtipo in s.execute(select(Ejercicio.anio, Asiento.subtipo).join(Asiento, Asiento.ejercicio_id == Ejercicio.id)) if subtipo in ("R", "Z"))
        finally:
            s.close()

    # Empresa A
    base = "/e/empresa_a/2021/ejercicios"
    f = cliente.get(f"{base}/f/2021")
    assert f.status_code == 200 and "Sin errores" in f.text
    r = cliente.post(f"{base}/guardar", data={"id": "2021", "accion": "cerrar", "abrir_siguiente": "on"})
    assert "cerrado" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], re.findall(r'role="alert">([^<]*)', r.text)
    assert subtipos("empresa_a") == [(2021, "R"), (2021, "Z")]
    assert "2022" in cliente.get(f"{base}/tabla").text and "Cerrado" in cliente.get(f"{base}/tabla").text
    # Empresa B
    base = "/e/empresa_b/2021/ejercicios"
    f = cliente.get(f"{base}/f/2021")
    assert "bloquean el cierre" in f.text
    r = cliente.post(f"{base}/guardar", data={"id": "2021", "accion": "cerrar", "abrir_siguiente": "on"})
    assert "La auditoría tiene" in r.text and "HX-Trigger" not in r.headers and subtipos("empresa_b") == []
