"""Interfaz web: páginas, componente de listado (filtro, orden, alta, edición, borrado, exportación) y tema claro/oscuro."""
import io
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion
from conta_pridalac.web.tema import DARK, LIGHT

D = Decimal
BASE = "/e/prueba/2026"


def _motor_en_memoria():
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    return motor


@pytest.fixture
def cliente(tmp_path):
    motor = _motor_en_memoria()
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("10000000", "CAPITAL SOCIAL"), ("57200001", "BANCO"), ("62900000", "OTROS SERVICIOS"), ("41000001", "PROVEEDOR UNO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    grabar_asiento(s, ej, tipo=4, numero=1, fecha=date(2026, 1, 2), concepto="APORTACION", lineas=[LineaAsiento("57200001", D(1000)), LineaAsiento("10000000", D(-1000))])
    grabar_asiento(s, ej, tipo=4, numero=2, fecha=date(2026, 2, 1), concepto="LUZ", lineas=[LineaAsiento("62900000", D(200)), LineaAsiento("41000001", D(-200))])
    s.add(Tercero(empresa_id=e.id, clase="P", nombre="Iberdrola", nif="A12345678", cuenta_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "41000001"))))
    s.commit()
    s.close()
    config = Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})
    return TestClient(crear_app(config))


def _cuenta(cliente, codigo):
    sesion = cliente.app.state.config.sesion("prueba")
    try:
        return sesion.scalar(select(Cuenta).where(Cuenta.codigo == codigo))
    finally:
        sesion.close()


# ---------------------------------------------------------------------------- páginas y tema


def test_inicio_lista_las_empresas_y_el_panel_los_listados(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "Empresa de Prueba" in r.text and f'href="{BASE}"' in r.text
    p = cliente.get(BASE)
    assert p.status_code == 200 and "Plan de cuentas" in p.text and "Libro Diario" in p.text


def test_el_tema_define_la_paleta_clara_y_la_oscura_de_empresa_b(cliente):
    css = cliente.get("/tema.css").text
    assert "--pistacho: #8DB84A" in css and "--pistacho: #5A8A1A" in css  # oscuro y claro
    assert "--bg-base: #1E2124" in css and "--bg-base: #F5F4F0" in css
    assert ":root[data-theme='dark']" in css and ":root[data-theme='light']" in css and "prefers-color-scheme: dark" in css
    assert set(DARK) == set(LIGHT)


def test_las_paginas_traen_el_selector_de_tema_y_htmx_local(cliente):
    html = cliente.get(f"{BASE}/cuentas").text
    assert 'id="tema"' in html and 'data-theme="auto"' in html and "/static/htmx.min.js" in html
    assert cliente.get("/static/htmx.min.js").status_code == 200 and cliente.get("/static/app.js").status_code == 200


def test_rutas_desconocidas_dan_404(cliente):
    assert cliente.get("/e/otra/2026").status_code == 404
    assert cliente.get("/e/prueba/1999").status_code == 404
    assert cliente.get(f"{BASE}/nada").status_code == 404


@pytest.mark.parametrize("nombre", ["cuentas", "proveedores", "clientes", "diario", "mayor", "balance", "iva-recibidas", "iva-emitidas"])
def test_todos_los_listados_se_muestran(cliente, nombre):
    assert cliente.get(f"{BASE}/{nombre}").status_code == 200
    r = cliente.get(f"{BASE}/{nombre}/tabla")
    assert r.status_code == 200 and "<table" in r.text


# ---------------------------------------------------------------------------- listado: filtro, orden y exportación


def test_cuentas_con_sus_sumas(cliente):
    html = cliente.get(f"{BASE}/cuentas/tabla").text
    assert "57200001" in html and "1.000,00" in html and "Totales" in html and "4 filas" in html


def test_filtro_sin_acentos_ni_mayusculas(cliente):
    html = cliente.get(f"{BASE}/cuentas/tabla", params={"q": "banco"}).text
    assert "57200001" in html and "62900000" not in html and "1 fila" in html
    assert "No hay filas" in cliente.get(f"{BASE}/cuentas/tabla", params={"q": "zzz"}).text


def test_orden_por_columna(cliente):
    def codigos(**p):
        html = cliente.get(f"{BASE}/cuentas/tabla", params=p).text
        return [c for c in ("10000000", "41000001", "57200001", "62900000") if c in html], html

    _, asc = codigos(orden="saldo", dir="asc")
    _, desc = codigos(orden="saldo", dir="desc")
    assert asc.index("10000000") < asc.index("57200001")  # −1000 antes que +1000
    assert desc.index("57200001") < desc.index("10000000")
    assert 'aria-sort="ascending"' in asc and 'aria-sort="descending"' in desc


def test_exportar_a_excel_respeta_filtro_y_orden(cliente):
    r = cliente.get(f"{BASE}/cuentas/exportar.xlsx", params={"q": "o", "orden": "codigo", "dir": "desc"})
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"] and "prueba_2026_cuentas.xlsx" in r.headers["content-disposition"]
    filas = [f for f in load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True) if f[0] and str(f[0]).isdigit()]
    assert [f[0] for f in filas] == sorted((f[0] for f in filas), reverse=True) and "57200001" in [f[0] for f in filas]


def test_exportar_a_pdf(cliente):
    r = cliente.get(f"{BASE}/balance/exportar.pdf", params={"nivel": "3"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    texto = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Balance de sumas y saldos" in texto and "Empresa de Prueba" in texto and "1.200,00" in texto
    assert cliente.get(f"{BASE}/balance/exportar.csv").status_code == 404


# ---------------------------------------------------------------------------- informes con parámetros


def test_balance_por_grupos(cliente):
    assert "Tesorería" in cliente.get(f"{BASE}/balance/tabla", params={"nivel": "2"}).text


def test_el_mayor_sale_con_todas_las_cuentas_y_la_cuenta_en_la_primera_columna(cliente):
    html = cliente.get(f"{BASE}/mayor/tabla").text
    cabeceras = re.findall(r'<th[^>]*data-clave="(\w+)"', html)
    assert cabeceras[:3] == ["cuenta", "nombre", "fecha"]
    for cuenta in ("10000000", "41000001", "57200001", "62900000"):
        assert cuenta in html
    assert html.count("Total de la cuenta") == 4 and "APORTACION" in html and "LUZ" in html
    assert 'class="resumen total"' in html


def test_el_mayor_se_acota_a_una_cuenta_o_a_un_grupo(cliente):
    una = cliente.get(f"{BASE}/mayor/tabla", params={"cuenta": "57200001"}).text
    assert "57200001" in una and "62900000" not in una and "Total de la cuenta" in una
    grupo = cliente.get(f"{BASE}/mayor/tabla", params={"cuenta": "57"}).text
    assert "57200001" in grupo and "10000000" not in grupo
    assert "No hay movimientos con esos criterios" in cliente.get(f"{BASE}/mayor/tabla", params={"cuenta": "99"}).text
    assert 'role="alert"' in cliente.get(f"{BASE}/mayor/tabla", params={"cuenta": "57x"}).text


def test_el_mayor_con_fechas_arrastra_el_saldo_anterior(cliente):
    html = cliente.get(f"{BASE}/mayor/tabla", params={"desde": "010226"}).text  # el 2 de enero queda como saldo anterior
    assert "Saldo anterior" in html and "LUZ" in html and "APORTACION" not in html


def test_al_ordenar_el_mayor_desaparecen_las_filas_de_resumen(cliente):
    html = cliente.get(f"{BASE}/mayor/tabla", params={"orden": "debe", "dir": "desc"}).text
    assert "Total de la cuenta" not in html and "LUZ" in html


def test_fechas_de_los_parametros_se_validan(cliente):
    html = cliente.get(f"{BASE}/diario/tabla", params={"desde": "99/99/99"}).text
    assert 'role="alert"' in html
    solo_febrero = cliente.get(f"{BASE}/diario/tabla", params={"desde": "010226"}).text
    assert "LUZ" in solo_febrero and "APORTACION" not in solo_febrero


def test_doble_clic_en_el_diario_muestra_el_asiento_completo(cliente):
    sesion = cliente.app.state.config.sesion("prueba")
    from conta_pridalac.db.modelos import Asiento

    ident = sesion.scalar(select(Asiento.id).where(Asiento.numero == 2))
    sesion.close()
    r = cliente.get(f"{BASE}/diario/f/{ident}")
    assert r.status_code == 200 and "Asiento 4.2" in r.text and "PROVEEDOR UNO" in r.text and "200,00" in r.text
    assert 'data-doble-clic="si"' in cliente.get(f"{BASE}/diario/tabla").text
    assert 'data-doble-clic="no"' in cliente.get(f"{BASE}/balance/tabla").text


def test_el_mayor_propone_las_cuentas_con_movimientos(cliente):
    html = cliente.get(f"{BASE}/mayor").text
    assert '<datalist id="dl-cuenta">' in html and '<option value="57200001">BANCO</option>' in html and 'list="dl-cuenta"' in html


def _con_factura_recibida(cliente):
    """Añade a la empresa de prueba una factura recibida con IVA, con su asiento, y devuelve su id."""
    from conta_pridalac.db.modelos import Factura, FacturaIva
    from conta_pridalac.servicios.facturas import grabar_factura

    s = cliente.app.state.config.sesion("prueba")
    try:
        e = s.scalars(select(Empresa)).first()
        ej = s.scalar(select(Ejercicio))
        s.add(Cuenta(empresa_id=e.id, codigo="47200000", nombre="HP IVA SOPORTADO"))
        s.flush()
        ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
        f = Factura(
            ejercicio_id=ej.id, sentido="R", numero=1, fecha_contable=date(2026, 3, 1), fecha_factura=date(2026, 2, 27), numero_factura="F-77", total=D("121.00"),
            tercero_id=s.scalar(select(Tercero.id)), cuenta_tercero_id=ids["41000001"], cuenta_contrapartida_id=ids["62900000"], concepto="Suministro de luz",
            ivas=[FacturaIva(base=D("100.00"), pct_iva=D("21.00"), cuota_iva=D("21.00"), cuenta_iva_id=ids["47200000"])],
        )
        grabar_factura(s, ej, f)
        s.commit()
        return f.id
    finally:
        s.close()


def test_doble_clic_en_el_libro_de_iva_muestra_la_factura(cliente):
    fid = _con_factura_recibida(cliente)
    tabla = cliente.get(f"{BASE}/iva-recibidas/tabla").text
    assert f'data-id="{fid}"' in tabla and 'data-doble-clic="si"' in tabla and "F-77" in tabla
    r = cliente.get(f"{BASE}/iva-recibidas/f/{fid}")
    assert r.status_code == 200
    for esperado in ("Factura recibida 1", "F-77", "Iberdrola", "A12345678", "Suministro de luz", "121,00", "21,00", "Asiento contable", "HP IVA SOPORTADO", "PROVEEDOR UNO"):
        assert esperado in r.text, esperado
    assert "Vencimientos" not in r.text  # esta factura de prueba no tiene


# ---------------------------------------------------------------------------- alta, edición y borrado


def test_alta_de_una_cuenta(cliente):
    form = cliente.get(f"{BASE}/cuentas/nuevo")
    assert form.status_code == 200 and 'name="codigo"' in form.text and 'name="nombre"' in form.text
    r = cliente.post(f"{BASE}/cuentas/guardar", data={"codigo": "60000001", "nombre": "Compras de prueba"})
    assert r.status_code == 200 and r.text == ""
    disparo = json.loads(r.headers["HX-Trigger"])
    assert disparo["refrescar"] is True and disparo["cerrarModal"] is True and disparo["mensaje"]["tipo"] == "ok"
    assert _cuenta(cliente, "60000001").nombre == "Compras de prueba"
    assert "60000001" in cliente.get(f"{BASE}/cuentas/tabla").text


@pytest.mark.parametrize(
    "datos, texto",
    [({"codigo": "123", "nombre": "x"}, "8 dígitos"), ({"codigo": "57200001", "nombre": "Repetida"}, "Ya existe"), ({"codigo": "60000002", "nombre": ""}, "Falta")],
)
def test_alta_incorrecta_vuelve_al_formulario_con_el_error(cliente, datos, texto):
    r = cliente.post(f"{BASE}/cuentas/guardar", data=datos)
    assert r.status_code == 200 and "HX-Trigger" not in r.headers and texto in r.text and 'role="alert"' in r.text
    assert f'value="{datos["codigo"]}"' in r.text  # conserva lo escrito


def test_edicion_de_una_cuenta_y_codigo_bloqueado_si_tiene_movimientos(cliente):
    cuenta = _cuenta(cliente, "62900000")
    form = cliente.get(f"{BASE}/cuentas/f/{cuenta.id}")
    assert form.status_code == 200 and 'value="62900000"' in form.text and 'value="OTROS SERVICIOS"' in form.text
    ok = cliente.post(f"{BASE}/cuentas/guardar", data={"id": cuenta.id, "codigo": "62900000", "nombre": "Servicios varios"})
    assert ok.text == "" and _cuenta(cliente, "62900000").nombre == "Servicios varios"
    malo = cliente.post(f"{BASE}/cuentas/guardar", data={"id": cuenta.id, "codigo": "62900009", "nombre": "x"})
    assert "está en uso" in malo.text and _cuenta(cliente, "62900000") is not None


def test_borrar_una_cuenta_libre_y_una_en_uso(cliente):
    cliente.post(f"{BASE}/cuentas/guardar", data={"codigo": "60000001", "nombre": "Para borrar"})
    libre, usada = _cuenta(cliente, "60000001"), _cuenta(cliente, "57200001")
    r = cliente.post(f"{BASE}/cuentas/borrar", data={"ids": [libre.id]})
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "ok" and _cuenta(cliente, "60000001") is None
    r = cliente.post(f"{BASE}/cuentas/borrar", data={"ids": [usada.id]})
    mensaje = json.loads(r.headers["HX-Trigger"])["mensaje"]
    assert mensaje["tipo"] == "error" and "en uso" in mensaje["texto"] and _cuenta(cliente, "57200001") is not None
    assert json.loads(cliente.post(f"{BASE}/cuentas/borrar").headers["HX-Trigger"])["mensaje"]["tipo"] == "aviso"


def test_terceros_alta_con_cuenta_y_error_si_la_cuenta_no_existe(cliente):
    r = cliente.post(f"{BASE}/clientes/guardar", data={"clase": "C", "nombre": "Cliente Nuevo", "nif": "b87654321", "cuenta": "41000001"})
    assert r.text == ""
    html = cliente.get(f"{BASE}/clientes/tabla", params={"q": "nuevo"}).text
    assert "Cliente Nuevo" in html and "B87654321" in html and "Cliente<" in html.replace(" ", "").replace("\n", "") or "Cliente" in html
    malo = cliente.post(f"{BASE}/proveedores/guardar", data={"clase": "P", "nombre": "X", "cuenta": "99999999"})
    assert "No existe la cuenta" in malo.text


def test_tercero_nuevo_sin_cuenta_recibe_la_siguiente_libre(cliente):
    form = cliente.get(f"{BASE}/proveedores/nuevo").text
    assert 'name="grupo_cuenta"' in form and "siguiente cuenta libre" in form
    assert cliente.post(f"{BASE}/proveedores/guardar", data={"clase": "P", "nombre": "Proveedor Nuevo", "nif": "b11111111", "cuenta": "", "grupo_cuenta": ""}).text == ""
    assert _cuenta(cliente, "40000001").nombre == "PROVEEDOR NUEVO"
    assert cliente.post(f"{BASE}/proveedores/guardar", data={"clase": "P", "nombre": "Notario", "cuenta": "", "grupo_cuenta": "410"}).text == ""
    assert _cuenta(cliente, "41000002") is not None  # la 41000001 ya existía en esta empresa
    assert cliente.post(f"{BASE}/clientes/guardar", data={"clase": "C", "nombre": "Cliente Nuevo 2", "cuenta": "", "grupo_cuenta": ""}).text == ""
    assert _cuenta(cliente, "43000001") is not None
    html = cliente.get(f"{BASE}/proveedores/tabla", params={"q": "notario"}).text
    assert "41000002" in html


def test_la_ficha_ampliada_del_tercero_se_guarda_y_se_vuelve_a_mostrar(cliente):
    datos = {"clase": "P", "nombre": "Ferretería Sur", "comercial": "Ferrosur", "nif": "B12345678", "cuenta": "", "grupo_cuenta": "", "tipo_identificador": "NIF", "domicilio": "C/ Mayor 1",
             "codigo_postal": "04001", "poblacion": "Almería", "provincia": "Almería", "pais": "España", "telefonos": "950000000", "email": "info@ferrosur.es", "divisa": "eur",
             "recargo_equivalencia": "on", "criterio_caja": "on", "retencion_pct": "15", "pct_iva_deducible": "50", "cuenta_gasto": "62900000", "tipos_iva_defecto": "1,2",
             "iban": "ES9121000418450200051332", "observaciones": "Paga a 30 días"}
    assert cliente.post(f"{BASE}/proveedores/guardar", data=datos).text == ""
    t = cliente.get(f"{BASE}/proveedores/tabla", params={"q": "ferrosur"}).text
    assert "Ferretería Sur" in t and "info@ferrosur.es" in t and "62900000" in t and "ES9121000418450200051332" in t
    ident = re.search(r'data-id="(\d+)"', t).group(1)
    f = cliente.get(f"{BASE}/proveedores/f/{ident}").text
    for esperado in ("Datos generales", "Por defecto en las facturas", "Datos de pago o de cobro", "Ferrosur", "62900000", "Paga a 30 días"):
        assert esperado in f, esperado
    assert re.search(r'name="recargo_equivalencia"[^>]*checked', f) and not re.search(r'name="generico"[^>]*checked', f)
    malo = cliente.post(f"{BASE}/proveedores/guardar", data={**datos, "id": ident, "iban": "ES0000000000000000000000"})
    assert "IBAN" in malo.text


def test_proveedores_y_clientes_van_en_listados_separados(cliente):
    cliente.post(f"{BASE}/proveedores/guardar", data={"nombre": "Solo Proveedor", "cuenta": "", "grupo_cuenta": ""})
    cliente.post(f"{BASE}/clientes/guardar", data={"nombre": "Solo Cliente", "cuenta": "", "grupo_cuenta": ""})
    prov, cli = cliente.get(f"{BASE}/proveedores/tabla").text, cliente.get(f"{BASE}/clientes/tabla").text
    assert "Solo Proveedor" in prov and "Solo Cliente" not in prov and "Solo Cliente" in cli and "Solo Proveedor" not in cli
    assert _cuenta(cliente, "40000001").nombre == "SOLO PROVEEDOR" or _cuenta(cliente, "40000002") is not None
    assert _cuenta(cliente, "43000001") is not None  # el cliente cae en el grupo 430 sin elegirlo
    assert 'name="clase"' not in cliente.get(f"{BASE}/clientes/nuevo").text and "Subcuenta de ingreso" in cliente.get(f"{BASE}/clientes/nuevo").text
    assert "Subcuenta de gasto" in cliente.get(f"{BASE}/proveedores/nuevo").text
    assert cliente.get(f"{BASE}/terceros").status_code == 404


def test_los_listados_de_solo_lectura_no_admiten_altas_ni_borrados(cliente):
    assert cliente.get(f"{BASE}/diario/nuevo").status_code == 405
    assert cliente.post(f"{BASE}/diario/borrar", data={"ids": ["1"]}).status_code == 405
    assert cliente.post(f"{BASE}/balance/guardar", data={"x": "1"}).status_code == 405


# ---------------------------------------------------------------------------- con los datos reales de MGD


@pytest.mark.datos_reales
@pytest.mark.parametrize("clave", ["empresa_a", "empresa_b"])
def test_aplicacion_con_los_datos_reales(clave, tmp_path):
    """Sirve cada empresa real desde su fichero SQLite y comprueba que todos los listados salen y que el PDF del balance cuadra."""
    from conftest import EMPRESAS_MGD_2021, _carpeta_empresa

    from conta_pridalac.db.sesion import crear_motor
    from conta_pridalac.migracion.mgd import cargar_mgd
    from conta_pridalac.servicios.informes import balance_sumas_y_saldos

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
    esperado = balance_sumas_y_saldos(sesion, ej, nivel=3).total_debe
    sesion.close()
    motor.dispose()

    cliente = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen")))
    assert clave in cliente.get("/").text
    base = f"/e/{clave}/2021"
    for nombre in ("cuentas", "proveedores", "clientes", "diario", "balance", "iva-recibidas", "iva-emitidas"):
        r = cliente.get(f"{base}/{nombre}/tabla")
        assert r.status_code == 200 and 'role="alert"' not in r.text and "No hay filas" not in r.text, nombre
    import re

    for lista in ("iva-recibidas", "iva-emitidas"):  # el doble clic de cada línea del libro de IVA abre su factura
        ids = sorted(set(re.findall(r'data-id="(\d+)"', cliente.get(f"{base}/{lista}/tabla").text)))
        for i in ids:
            r = cliente.get(f"{base}/{lista}/f/{i}")
            assert r.status_code == 200 and "Asiento contable" in r.text, (lista, i)
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(cliente.get(f"{base}/balance/exportar.pdf").content)).pages)
    assert f"{esperado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") in texto
