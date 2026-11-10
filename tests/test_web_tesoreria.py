"""Tesorería en la web: bancos, movimientos, vencimientos (cobrar, pagar, compensar) y transferencias."""
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import (
    Adjunto, Asiento, Banco, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, MovimientoBanco, Pago, Parametro, Tercero, Vencimiento,
)
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.tesoreria import crear_banco
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, definir_vencimientos
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


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
    for codigo, nombre in (("57200001", "BANCO UNO"), ("57200002", "BANCO DOS"), ("40000001", "PROVEEDOR UNO"), ("43000001", "CLIENTE UNO"), ("62900000", "OTROS SERVICIOS"),
                           ("70000000", "VENTAS"), ("55500000", "PARTIDAS PENDIENTES"), ("47200021", "IVA SOPORTADO"), ("47700021", "IVA REPERCUTIDO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.add(Parametro(empresa_id=e.id, clave="PTE_APLIC", valor="55500000"))
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    crear_banco(s, e.id, "Banco Uno", "57200001", iban="ES00 1111", saldo_inicial=D("1000"))
    crear_banco(s, e.id, "Banco Dos", "57200002")
    prov = Tercero(empresa_id=e.id, clase="P", nombre="Iberdrola", cuenta_id=ids["40000001"])
    cli = Tercero(empresa_id=e.id, clase="C", nombre="Cliente Uno", cuenta_id=ids["43000001"])
    s.add_all([prov, cli])
    s.flush()
    for sentido, numero, tercero, cta_t, cta_c, iva, total, base in (("R", 1, prov, "40000001", "62900000", "47200021", D("121.00"), D("100.00")), ("E", 1, cli, "43000001", "70000000", "47700021", D("242.00"), D("200.00"))):
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=date(2026, 2, 1), fecha_factura=date(2026, 2, 1), numero_factura=f"F-{sentido}", total=total,
                    tercero_id=tercero.id, cuenta_tercero_id=ids[cta_t], cuenta_contrapartida_id=ids[cta_c],
                    ivas=[FacturaIva(base=base, pct_iva=D("21.00"), cuota_iva=total - base, cuenta_iva_id=ids[iva])])
        grabar_factura(s, ej, f)
        definir_vencimientos(s, ej, f, [PlazoVencimiento(importe=total, fecha=date(2026, 3, 1))])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _banco(cliente, nombre="Banco Uno"):
    s = _sesion(cliente)
    try:
        return s.scalar(select(Banco.id).where(Banco.nombre == nombre))
    finally:
        s.close()


def _venc(cliente, tipo):
    s = _sesion(cliente)
    try:
        return s.scalar(select(Vencimiento.id).where(Vencimiento.origen_tipo == tipo))
    finally:
        s.close()


def _movimientos(cliente):
    s = _sesion(cliente)
    try:
        return [(m.id, m.numero, m.banco.nombre, m.texto, [p.importe for p in m.pagos], {ap.cuenta.codigo: ap.debe - ap.haber for a in s.scalars(select(Asiento).where(Asiento.tipo == 3, Asiento.numero == m.numero)) for ap in a.apuntes})
                for m in s.scalars(select(MovimientoBanco).order_by(MovimientoBanco.numero))]
    finally:
        s.close()


def _pendiente(cliente, vid):
    s = _sesion(cliente)
    try:
        v = s.get(Vencimiento, vid)
        return v.importe - (s.scalar(select(func.sum(Pago.importe)).where(Pago.vencimiento_id == vid)) or D("0.00"))
    finally:
        s.close()


def _disparo(r):
    return json.loads(r.headers["HX-Trigger"])


# ---------------------------------------------------------------------------- páginas


def test_paginas_y_menu(cliente):
    for n in ("movimientos", "vencimientos", "bancos"):
        assert cliente.get(f"{BASE}/{n}").status_code == 200 and "<table" in cliente.get(f"{BASE}/{n}/tabla").text
    panel = cliente.get(BASE).text
    assert "Movimientos de banco" in panel and "Vencimientos pendientes" in panel and "Bancos" in panel
    assert "Transferencia" in cliente.get(f"{BASE}/movimientos").text


# ---------------------------------------------------------------------------- bancos


def test_listado_de_bancos(cliente):
    html = cliente.get(f"{BASE}/bancos/tabla").text
    assert "Banco Uno" in html and "ES001111" in html and "57200001" in html and "1.000,00" in html and "2 filas" in html
    assert 'class="aviso-fila"' in html  # el saldo inicial de 1.000 no está en el asiento de apertura: la cuenta no lo refleja


def test_alta_edicion_y_baja_de_un_banco(cliente):
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    s.add(Cuenta(empresa_id=e.id, codigo="57200003", nombre="BANCO TRES"))
    s.commit()
    s.close()
    assert cliente.get(f"{BASE}/bancos/nuevo").status_code == 200
    r = cliente.post(f"{BASE}/bancos/guardar", data={"nombre": "Banco Tres", "cuenta": "57200003", "iban": "es12 3456", "saldo_inicial": "250,50"})
    assert r.text == ""
    b = _banco(cliente, "Banco Tres")
    html = cliente.get(f"{BASE}/bancos/f/{b}").text
    assert 'value="Banco Tres"' in html and 'value="ES123456"' in html and 'value="250,50"' in html
    assert cliente.post(f"{BASE}/bancos/guardar", data={"id": b, "nombre": "Banco 3", "cuenta": "57200003", "saldo_inicial": "0"}).text == ""
    assert _banco(cliente, "Banco 3") == b
    assert _disparo(cliente.post(f"{BASE}/bancos/borrar", data={"ids": [b]}))["mensaje"]["tipo"] == "ok" and _banco(cliente, "Banco 3") is None


@pytest.mark.parametrize(
    "datos, texto",
    [({"nombre": "", "cuenta": "57200001"}, "Falta «Banco»"), ({"nombre": "X", "cuenta": ""}, "Falta «Cuenta contable»"), ({"nombre": "X", "cuenta": "99999999"}, "No existe la cuenta"),
     ({"nombre": "X", "cuenta": "57200001"}, "ya es la de otro banco")],
)
def test_bancos_incorrectos(cliente, datos, texto):
    r = cliente.post(f"{BASE}/bancos/guardar", data=datos)
    assert texto in r.text and 'role="alert"' in r.text


def test_un_banco_con_movimientos_no_se_borra(cliente):
    cliente.post(f"{BASE}/vencimientos/guardar", data={"id": _venc(cliente, "R"), "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "010326", "importe": "-121,00"})
    r = cliente.post(f"{BASE}/bancos/borrar", data={"ids": [_banco(cliente)]})
    assert _disparo(r)["mensaje"]["tipo"] == "error" and "tiene 1 movimientos" in _disparo(r)["mensaje"]["texto"]


# ---------------------------------------------------------------------------- vencimientos


def test_cartera_de_vencimientos(cliente):
    html = cliente.get(f"{BASE}/vencimientos/tabla").text
    assert "Iberdrola" in html and "Cliente Uno" in html and "-121,00" in html and "242,00" in html and "2 filas" in html
    assert "1 fila" in cliente.get(f"{BASE}/vencimientos/tabla", params={"origen": "R"}).text
    assert "No hay filas" in cliente.get(f"{BASE}/vencimientos/tabla", params={"estado": "pagados"}).text
    assert 'class="aviso-fila"' not in html or "Vencido" in html  # sólo se resaltan los vencidos


def test_pagar_un_vencimiento_desde_su_ficha(cliente):
    vid = _venc(cliente, "R")
    f = cliente.get(f"{BASE}/vencimientos/f/{vid}")
    assert f.status_code == 200 and "Iberdrola" in f.text and 'value="-121,00"' in f.text and "Registrar pago" in f.text and "Compensar" in f.text
    r = cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "050326", "importe": "-121,00", "texto": ""})
    assert r.text == "" and _disparo(r)["cerrarModal"]
    m = _movimientos(cliente)[0]
    assert m[2] == "Banco Uno" and m[4] == [D("-121.00")] and m[5] == {"40000001": D("121.00"), "57200001": D("-121.00")} and "PAGO" in m[3]
    assert _pendiente(cliente, vid) == 0
    assert "1 fila" in cliente.get(f"{BASE}/vencimientos/tabla").text  # sólo queda el de cobro
    assert "Saldado" in cliente.get(f"{BASE}/vencimientos/tabla", params={"estado": "todos"}).text
    assert "Este vencimiento está saldado" in cliente.get(f"{BASE}/vencimientos/f/{vid}").text


def test_cobro_parcial_deja_el_resto(cliente):
    vid = _venc(cliente, "E")
    cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "050326", "importe": "100,00"})
    assert _pendiente(cliente, vid) == D("142.00")
    assert "142,00" in cliente.get(f"{BASE}/vencimientos/f/{vid}").text


@pytest.mark.parametrize(
    "cambios, texto",
    [({"banco": ""}, "Elija el banco"), ({"fecha_pago": "050327"}, "fuera del ejercicio"), ({"importe": "xx"}, "no es un importe válido"), ({"fecha_pago": "zz"}, "no es una fecha")],
)
def test_errores_al_pagar(cliente, cambios, texto):
    vid = _venc(cliente, "R")
    datos = {"id": vid, "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "050326", "importe": "-121,00"}
    datos.update(cambios)
    r = cliente.post(f"{BASE}/vencimientos/guardar", data=datos)
    assert 'role="alert"' in r.text and texto in r.text and "HX-Trigger" not in r.headers and _movimientos(cliente) == []


def test_pagar_de_mas_o_con_el_signo_contrario_avisa(cliente):
    vid = _venc(cliente, "R")
    r = cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "050326", "importe": "-500,00"})
    assert r.text == "" and _disparo(r)["mensaje"]["tipo"] == "aviso" and "solo tiene" in _disparo(r)["mensaje"]["texto"]


def test_compensar_un_vencimiento(cliente):
    vid = _venc(cliente, "R")
    r = cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "compensar", "cuenta": "43000001", "fecha_pago": "050326"})
    assert r.text == "", r.text[:300]
    assert _pendiente(cliente, vid) == 0
    assert _movimientos(cliente)[0][2] == "COMPENSACION DE VENCIMIENTOS"
    assert "No existe la cuenta" in cliente.post(f"{BASE}/vencimientos/guardar", data={"id": _venc(cliente, "E"), "accion": "compensar", "cuenta": "99999999", "fecha_pago": "050326"}).text


def test_cambiar_datos_del_vencimiento(cliente):
    vid = _venc(cliente, "E")
    r = cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "guardar", "fecha": "150426", "forma": "", "banco_previsto": str(_banco(cliente, "Banco Dos"))})
    assert r.text == ""
    s = _sesion(cliente)
    v = s.get(Vencimiento, vid)
    assert v.fecha == date(2026, 4, 15) and v.banco_previsto.nombre == "Banco Dos"
    s.close()
    assert "Banco Dos" in cliente.get(f"{BASE}/vencimientos/tabla", params={"origen": "E"}).text
    assert "no es una fecha" in cliente.post(f"{BASE}/vencimientos/guardar", data={"id": vid, "accion": "guardar", "fecha": "zz"}).text


def test_un_ejercicio_cerrado_no_admite_cobros(cliente):
    s = _sesion(cliente)
    s.scalar(select(Ejercicio)).cerrado = True
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/vencimientos/guardar", data={"id": _venc(cliente, "R"), "accion": "pagar", "banco": _banco(cliente), "fecha_pago": "050326", "importe": "-121,00"})
    assert "cerrado" in r.text and _movimientos(cliente) == []


# ---------------------------------------------------------------------------- movimientos


def _mov(cliente, **cambios):
    datos = {"banco": str(_banco(cliente)), "fecha": "050326", "texto": "", "ln-0-tipo": "V", "ln-0-venc": str(_venc(cliente, "R")), "ln-0-cuenta": "", "ln-0-importe": "-121,00", "ln-0-auto": "0"}
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def test_el_formulario_de_movimiento_propone_el_pendiente_y_el_asiento(cliente):
    f = cliente.get(f"{BASE}/movimientos/nuevo")
    assert f.status_code == 200 and "Un vencimiento" in f.text and "Guardar movimiento" in f.text
    assert '<option value="C" selected>Una cuenta directa' in f.text  # la primera línea de un movimiento nuevo va a una cuenta directa
    r = cliente.post(f"{BASE}/movimientos/recalcular", data=_mov(cliente, **{"ln-0-importe": "", "ln-0-auto": "1"}))
    assert 'name="ln-0-importe" value="-121,00"' in r.text and "Sale del banco" in r.text
    assert "Asiento que se generará" in r.text and "PROVEEDOR UNO" in r.text and "BANCO UNO" in r.text
    r = cliente.post(f"{BASE}/movimientos/recalcular", data={**_mov(cliente), "accion": "add-ln"})
    assert 'name="ln-1-tipo"' in r.text


def test_alta_de_un_movimiento_que_salda_un_vencimiento(cliente):
    r = cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente))
    assert r.text == "" and _disparo(r)["refrescar"]
    m = _movimientos(cliente)[0]
    assert m[1] == 1 and m[4] == [D("-121.00")] and m[5] == {"40000001": D("121.00"), "57200001": D("-121.00")}
    tabla = cliente.get(f"{BASE}/movimientos/tabla").text
    assert "Banco Uno" in tabla and "-121,00" in tabla and "879,00" in tabla  # saldo: 1.000 − 121
    assert _pendiente(cliente, _venc(cliente, "R")) == 0


def test_movimiento_con_varias_lineas_y_cuenta_directa(cliente):
    datos = _mov(cliente, **{"ln-1-tipo": "C", "ln-1-venc": "", "ln-1-cuenta": "62900000", "ln-1-importe": "-30,00", "ln-1-auto": "0", "texto": "Pago y gasto"})
    assert cliente.post(f"{BASE}/movimientos/guardar", data=datos).text == ""
    m = _movimientos(cliente)[0]
    assert m[3] == "Pago y gasto" and m[5] == {"40000001": D("121.00"), "62900000": D("30.00"), "57200001": D("-151.00")}


def test_linea_pendiente_de_aplicar(cliente):
    datos = _mov(cliente, **{"ln-0-tipo": "P", "ln-0-venc": "", "ln-0-importe": "75,00"})
    assert cliente.post(f"{BASE}/movimientos/guardar", data=datos).text == ""
    assert _movimientos(cliente)[0][5] == {"57200001": D("75.00"), "55500000": D("-75.00")}


@pytest.mark.parametrize(
    "cambios, texto",
    [({"banco": ""}, "Elija el banco"), ({"fecha": "050327"}, "fuera del ejercicio"), ({"ln-0-venc": ""}, "elija el vencimiento"), ({"ln-0-tipo": "C", "ln-0-venc": "", "ln-0-cuenta": "62900000", "ln-0-importe": ""}, "Falta el importe"),
     ({"ln-0-importe": "xx"}, "no es un importe válido"), ({"ln-0-tipo": "C", "ln-0-venc": "", "ln-0-cuenta": "99999999"}, "No existe la cuenta 99999999")],
)
def test_errores_en_un_movimiento(cliente, cambios, texto):
    r = cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente, **cambios))
    assert 'role="alert"' in r.text and texto in r.text and "Guardar movimiento" in r.text and _movimientos(cliente) == []


def test_editar_y_borrar_un_movimiento(cliente):
    cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente))
    mid = _movimientos(cliente)[0][0]
    f = cliente.get(f"{BASE}/movimientos/f/{mid}")
    assert f.status_code == 200 and 'value="-121,00"' in f.text and f'name="id" value="{mid}"' in f.text and "<fieldset class=\"sin-marco\" >" in f.text.replace("\n", "")
    # pagar sólo 100 en lugar de 121: el vencimiento vuelve a tener pendiente
    assert cliente.post(f"{BASE}/movimientos/guardar", data={**_mov(cliente, **{"ln-0-importe": "-100,00"}), "id": str(mid)}).text == ""
    assert _movimientos(cliente)[0][4] == [D("-100.00")] and _pendiente(cliente, _venc(cliente, "R")) == D("-21.00")
    assert _disparo(cliente.post(f"{BASE}/movimientos/borrar", data={"ids": [mid]}))["mensaje"]["tipo"] == "ok"
    assert _movimientos(cliente) == [] and _pendiente(cliente, _venc(cliente, "R")) == D("-121.00")


def test_justificante_de_un_movimiento(cliente):
    r = cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente), files=[("ficheros", ("extracto.pdf", PDF, "application/pdf"))])
    assert r.text == ""
    s = _sesion(cliente)
    a = s.scalar(select(Adjunto))
    ruta = cliente.app.state.config.almacen_de_adjuntos().ruta(a)
    mid = a.movimiento_banco_id
    s.close()
    assert ruta.read_bytes() == PDF and cliente.get(f"{BASE}/adjuntos/{a.id}").content == PDF
    assert "<iframe" in cliente.get(f"{BASE}/movimientos/f/{mid}").text
    assert re.search(r'data-clave="justificantes">1<', cliente.get(f"{BASE}/movimientos/tabla").text)
    cliente.post(f"{BASE}/movimientos/borrar", data={"ids": [mid]})
    assert not ruta.exists()


def test_filtro_por_banco(cliente):
    cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente))
    uno, dos = _banco(cliente), _banco(cliente, "Banco Dos")
    assert "1 fila" in cliente.get(f"{BASE}/movimientos/tabla", params={"banco": uno}).text
    assert "Este banco no tiene movimientos" in cliente.get(f"{BASE}/movimientos/tabla", params={"banco": dos}).text
    assert "1 fila" in cliente.get(f"{BASE}/movimientos/tabla").text  # sin elegir, trabaja con el primer banco
    pagina = cliente.get(f"{BASE}/movimientos").text
    assert "Todos los bancos" not in pagina and f'<option value="{uno}"' in pagina and f'<option value="{dos}"' in pagina


# ---------------------------------------------------------------------------- transferencias


def test_transferencia_entre_bancos(cliente):
    f = cliente.get(f"{BASE}/movimientos/accion/transferencia")
    assert f.status_code == 200 and "Banco de origen" in f.text and "Banco Dos" in f.text
    uno, dos = _banco(cliente), _banco(cliente, "Banco Dos")
    r = cliente.post(f"{BASE}/movimientos/accion/transferencia", data={"origen": uno, "destino": dos, "fecha": "100326", "importe": "300,00", "texto": ""})
    assert r.text == "" and _disparo(r)["mensaje"]["texto"] == "Transferencia registrada" and _disparo(r)["cerrarModal"]
    movs = _movimientos(cliente)
    assert [m[4] for m in movs] == [[D("-300.00")], [D("300.00")]]
    asientos = [m[5] for m in movs if m[5]]
    assert asientos == [{"57200002": D("300.00"), "57200001": D("-300.00")}]  # un solo asiento
    assert cliente.get(f"{BASE}/movimientos/tabla", params={"banco": uno}).text.count("Transferencia") == 1  # cada banco ve su mitad
    assert cliente.get(f"{BASE}/movimientos/tabla", params={"banco": dos}).text.count("Transferencia") == 1
    # sus mitades no se editan, y borrar una borra las dos
    mid = movs[0][0]
    assert "mitades de una transferencia" in cliente.get(f"{BASE}/movimientos/f/{mid}").text
    assert "mitades de una transferencia" in cliente.post(f"{BASE}/movimientos/guardar", data={**_mov(cliente), "id": str(mid)}).text
    cliente.post(f"{BASE}/movimientos/borrar", data={"ids": [mid]})
    assert _movimientos(cliente) == []


@pytest.mark.parametrize(
    "cambios, texto",
    [({"destino": "SAME"}, "son el mismo"), ({"origen": ""}, "Elija el banco"), ({"importe": ""}, "Falta el importe"), ({"importe": "-5"}, "positivo"), ({"fecha": "050327"}, "fuera del ejercicio")],
)
def test_errores_en_una_transferencia(cliente, cambios, texto):
    uno, dos = _banco(cliente), _banco(cliente, "Banco Dos")
    datos = {"origen": uno, "destino": dos, "fecha": "100326", "importe": "300,00"}
    datos.update(cambios)
    if datos["destino"] == "SAME":
        datos["destino"] = uno
    r = cliente.post(f"{BASE}/movimientos/accion/transferencia", data=datos)
    assert 'role="alert"' in r.text and texto in r.text and _movimientos(cliente) == []


# ---------------------------------------------------------------------------- exportación


def test_los_listados_de_tesoreria_se_exportan(cliente):
    cliente.post(f"{BASE}/movimientos/guardar", data=_mov(cliente))
    for n in ("movimientos", "vencimientos", "bancos"):
        assert cliente.get(f"{BASE}/{n}/exportar.xlsx").status_code == 200
        assert cliente.get(f"{BASE}/{n}/exportar.pdf").headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
@pytest.mark.parametrize("clave", ["empresa_a", "empresa_b"])
def test_tesoreria_con_los_datos_reales(clave, tmp_path):
    """Las pantallas salen con los datos de MGD y cada movimiento normal se reconstruye en el formulario y se regraba igual."""
    from conftest import EMPRESAS_MGD_2021, _carpeta_empresa

    from conta_pridalac.db.sesion import crear_motor
    from conta_pridalac.migracion.mgd import cargar_mgd
    from conta_pridalac.web.listados import Contexto
    from conta_pridalac.web.tesoreria import construir_y_grabar, estado_de_movimiento

    origen = _carpeta_empresa(clave)
    if not (origen / "Diario.dbf").exists():
        pytest.skip(f"No hay datos MGD de {clave}")
    (tmp_path / "bd").mkdir()
    motor = crear_motor(tmp_path / "bd" / f"{clave}.sqlite")
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    datos = EMPRESAS_MGD_2021[clave]
    res = cargar_mgd(sesion, origen, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
    sesion.commit()
    ej = sesion.get(Ejercicio, res.ejercicio_id)
    ctx = Contexto(sesion, sesion.get(Empresa, ej.empresa_id), ej, clave, Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "alm"))

    def foto():
        estado = {}
        for a in sesion.scalars(select(Asiento)):
            lineas: Counter = Counter()
            for ap in a.apuntes:
                lineas[ap.cuenta.codigo] += ap.debe - ap.haber
            estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, a.concepto, dict(lineas))
        pagos = sorted((p.movimiento.numero, p.orden, p.importe, p.vencimiento_id or 0) for p in sesion.scalars(select(Pago)))
        return estado, pagos, sorted((m.numero, m.fecha, m.texto) for m in sesion.scalars(select(MovimientoBanco)))

    antes = foto()
    regrabados = 0
    for m in list(sesion.scalars(select(MovimientoBanco))):
        e = estado_de_movimiento(ctx, m)
        if e.solo_lectura or not (ej.fecha_inicio <= m.fecha <= ej.fecha_fin):
            continue
        movimiento, errores, _ = construir_y_grabar(ctx, e, [])
        assert errores == [] and movimiento is not None, (m.numero, errores)
        regrabados += 1
    sesion.flush()
    assert regrabados >= 1
    assert foto() == antes
    sesion.close()
    motor.dispose()

    cliente = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "alm2")))
    base = f"/e/{clave}/2021"
    for n in ("movimientos", "vencimientos", "bancos"):
        r = cliente.get(f"{base}/{n}/tabla")
        assert r.status_code == 200 and 'role="alert"' not in r.text, n
    bancos = re.findall(r'<option value="(\d+)"', cliente.get(f"{base}/movimientos").text)
    assert bancos
    ids = sorted({i for b in bancos for i in re.findall(r'data-id="(\d+)"', cliente.get(f"{base}/movimientos/tabla", params={"banco": b}).text)}, key=int)
    assert ids
    for i in ids:
        assert cliente.get(f"{base}/movimientos/f/{i}").status_code == 200
    ids = sorted(set(re.findall(r'data-id="(\d+)"', cliente.get(f"{base}/vencimientos/tabla", params={"estado": "todos"}).text)), key=int)
    assert ids
    for i in ids:
        assert cliente.get(f"{base}/vencimientos/f/{i}").status_code == 200
    assert "aviso-fila" not in cliente.get(f"{base}/bancos/tabla").text  # el saldo de cada banco cuadra con su cuenta
