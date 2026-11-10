"""Menú en cajas: la banda de pestañas, la caja que se abre según la pantalla y las opciones que aún no están."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from conta_pridalac.web.definiciones import CAJAS, caja_de, construir_menu, todos_los_listados


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def test_todas_las_opciones_del_menu_son_pantallas_que_existen():
    listados = todos_los_listados()
    for _, _, entradas in CAJAS:
        for e in entradas:
            if isinstance(e, str) and e.startswith("~"):
                continue
            nombre = e if isinstance(e, str) else e[0]
            assert nombre in listados, nombre
            if not isinstance(e, str):
                assert len(e) == 4 and all(a in listados for a in e[2]), e


def test_cada_pantalla_con_menu_esta_en_una_sola_caja():
    nombres = [o.nombre for c in construir_menu(todos_los_listados()) for o in c.opciones if o.nombre]
    assert len(nombres) == len(set(nombres))


def test_caja_de_una_pantalla_y_de_sus_alias():
    menu = construir_menu(todos_los_listados())
    assert caja_de(menu, "balance-oficial") == "listados" and caja_de(menu, "modelo-303") == "liquidaciones" and caja_de(menu, "declaraciones-190") == "liquidaciones"
    assert caja_de(menu, "bancos") == "tesoreria" and caja_de(menu, "no-existe") is None and caja_de(menu, None) is None


def test_la_banda_sale_en_todas_las_pantallas_con_su_caja_abierta(cliente):
    inicio = cliente.get("/e/prueba/2025").text
    assert inicio.count('role="tab"') == len(CAJAS) and 'data-inicio="1"' in inicio and "Impuesto sobre Sociedades" in inicio and "Registro Mercantil" in inicio
    balance = cliente.get("/e/prueba/2025/balance-oficial").text
    assert 'data-inicio=""' in balance and 'aria-expanded="true"' in balance and 'class="opcion actual"' in balance
    assert re.search(r'id="pestana-listados"[^>]*aria-expanded="true"', balance) and re.search(r'class="pestana activa" id="pestana-listados"', balance)
    assert re.search(r'id="pestana-tesoreria"[^>]*aria-expanded="false"', balance)
    assert not re.search(r'id="caja-listados"[^>]*hidden', balance) and re.search(r'id="caja-tesoreria"[^>]*hidden', balance)


def test_las_declaraciones_presentadas_dejan_abierta_la_caja_de_su_modelo(cliente):
    pagina = cliente.get("/e/prueba/2025/declaraciones-111").text
    assert not re.search(r'id="caja-liquidaciones"[^>]*hidden', pagina) and re.search(r'id="caja-listados"[^>]*hidden', pagina)


def test_lo_que_aun_no_esta_sale_marcado_y_sin_enlace(cliente):
    pagina = cliente.get("/e/prueba/2025").text
    assert 'href="/e/prueba/2025/modelo-200"' in pagina and "200 · Impuesto sobre Sociedades" in pagina  # el 200 ya existe: con enlace (ya no queda nada «próximamente»)
    assert 'class="opcion proximamente"' not in pagina
    assert 'href="/e/prueba/2025/modelo-347"' in pagina and "347 · Operaciones con terceros" in pagina
    assert 'href="/e/prueba/2025/modelo-390"' in pagina and "390 · Resumen anual del IVA" in pagina  # el 390 ya existe: con enlace
    assert 'href="/e/prueba/2025/modelo-202"' in pagina and "202 · Pago fraccionado" in pagina  # y el 202 también
    assert 'href="/e/prueba/2025/legalizacion-libros"' in pagina and "Legalización de libros" in pagina  # y la legalización de libros
    assert 'href="/e/prueba/2025/deposito-cuentas"' in pagina and "Depósito de cuentas" in pagina  # y el depósito de cuentas


def test_el_inicio_ya_no_repite_las_tarjetas(cliente):
    assert 'class="tarjetas"' not in cliente.get("/e/prueba/2025").text


def test_cada_opcion_enseña_su_explicacion_debajo(cliente):
    pagina = cliente.get("/e/prueba/2025").text
    # las de los modelos de la AEAT y las de los listados (la descripción completa de cada uno, no sólo un título)
    assert "Autoliquidación trimestral: cálculo, controles, fichero para la sede, justificantes y declaraciones presentadas." in pagina
    assert "Clientes y proveedores con más de 3.005,06 € en el año" in pagina and "Lo facturado a cada cliente (facturas emitidas)" in pagina
    assert re.search(r'<strong>Facturas recibidas</strong><span class="explicacion">[^<]+', pagina)
    assert re.search(r'<strong>200 · Impuesto sobre Sociedades</strong><span class="explicacion">Liquidación anual del Impuesto sobre Sociedades[^<]+', pagina)
    assert re.search(r'<strong>202 · Pago fraccionado</strong><span class="explicacion">Pago fraccionado del Impuesto sobre Sociedades[^<]+', pagina)
    sin_explicacion = re.findall(r'<strong>([^<]+)</strong><span class="explicacion">\s*</span>', pagina)
    assert sin_explicacion == [], sin_explicacion  # ninguna opción se queda sin su explicación


def test_la_disposicion_del_menu_se_elige_con_un_boton_y_se_recuerda(cliente):
    pagina = cliente.get("/e/prueba/2025").text
    # el botón sale con menú, el marco envuelve la banda y el cuerpo, y la disposición se fija antes de pintar
    assert 'id="disposicion"' in pagina and '<div class="marco">' in pagina and 'data-menu="horizontal"' in pagina
    assert pagina.index('class="cajas"') < pagina.index('class="cuerpo"')
    # sin empresa (pantalla de inicio general) no hay menú que colocar
    assert 'id="disposicion"' not in cliente.get("/").text
    js = cliente.get("/static/app.js").text
    assert "guardarPreferencia('menu'" in js and "data-menu" in js
    assert "html[data-menu='vertical'] .caja " in cliente.get("/static/app.css").text


CABECERA = {"X-Conta": "preferencia"}


def test_las_preferencias_de_pantalla_las_guarda_el_programa_y_vuelven_en_la_pagina(cliente):
    assert cliente.post("/_preferencias", json={"clave": "menu", "valor": "vertical"}, headers=CABECERA).status_code == 204
    assert cliente.post("/_preferencias", json={"clave": "tema", "valor": "dark"}, headers=CABECERA).status_code == 204
    assert cliente.post("/_preferencias", json={"clave": "caja", "valor": "listados"}, headers=CABECERA).status_code == 204
    pagina = cliente.get("/e/prueba/2025").text
    assert 'data-menu="vertical"' in pagina and 'data-theme="dark"' in pagina and 'data-guardada="listados"' in pagina
    assert 'data-menu="vertical"' in cliente.get("/").text  # también en las pantallas sin empresa


def test_las_preferencias_no_se_aceptan_sin_la_cabecera_ni_con_valores_raros(cliente):
    assert cliente.post("/_preferencias", json={"clave": "menu", "valor": "vertical"}).status_code == 403
    assert cliente.post("/_preferencias", json={"clave": "menu", "valor": "diagonal"}, headers=CABECERA).status_code == 422
    assert cliente.post("/_preferencias", json={"clave": "otra", "valor": "x"}, headers=CABECERA).status_code == 422
    assert 'data-menu="horizontal"' in cliente.get("/e/prueba/2025").text


def test_las_explicaciones_salen_como_tooltip_y_se_pueden_dejar_fijas(cliente):
    """Preferencia «ayudas»: por defecto las explicaciones de las opciones no ocupan sitio (tooltip); con «visibles» se quedan a la vista."""
    pagina = cliente.get("/e/prueba/2025").text
    assert 'data-ayudas="tooltip"' in pagina and 'id="ayudas"' in pagina
    assert 'id="ayudas"' not in cliente.get("/").text                                                   # sin empresa no hay menú ni explicaciones que cambiar
    assert re.search(r'<a class="opcion[^"]*" title="[^"]{20,}" href="/e/prueba/2025/', pagina)          # cada opción lleva su explicación como tooltip…
    assert 'class="explicacion"' in pagina                                                              # …y el texto sigue en la página (lectores de pantalla)
    css = cliente.get("/static/app.css").text
    assert "html[data-ayudas='tooltip'] .opcion .explicacion" in css and "(hover: none)" in css           # sin ratón, las explicaciones se quedan visibles
    assert "guardarPreferencia('ayudas'" in cliente.get("/static/app.js").text
    assert cliente.post("/_preferencias", json={"clave": "ayudas", "valor": "visibles"}, headers=CABECERA).status_code == 204
    assert 'data-ayudas="visibles"' in cliente.get("/e/prueba/2025").text and 'data-ayudas="visibles"' in cliente.get("/").text
    assert cliente.post("/_preferencias", json={"clave": "ayudas", "valor": "nunca"}, headers=CABECERA).status_code == 422
    assert 'data-ayudas="visibles"' in cliente.get("/e/prueba/2025").text                               # un valor raro no cambia nada


def test_la_descripcion_de_cada_pantalla_es_fija_o_plegable_segun_la_preferencia(cliente):
    pagina = cliente.get("/e/prueba/2025/facturas-recibidas").text
    assert 'class="suave descripcion-fija"' in pagina and '<details class="descripcion-plegable suave">' in pagina and "Qué hace esta pantalla" in pagina
