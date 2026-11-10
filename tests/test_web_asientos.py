"""Asientos manuales y plantillas en la web."""
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Adjunto, Apunte, Asiento, Cuenta, Ejercicio, Empresa, Plantilla, PlantillaLinea, Vencimiento
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/asientos"
PL = "/e/prueba/2026/plantillas"
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
    for codigo, nombre in (("64000000", "SUELDOS"), ("47510000", "HP RETENCIONES"), ("47600000", "SEGURIDAD SOCIAL"), ("57200001", "BANCO"), ("10000000", "CAPITAL"), ("17000001", "PRESTAMO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    p = Plantilla(empresa_id=e.id, titulo="NOMINA {mes}/{año}")
    p.lineas = [
        PlantillaLinea(orden=1, cuenta="64000000", dhc="D", ayuda="Sueldo bruto"),
        PlantillaLinea(orden=2, cuenta="47510000", dhc="H", ayuda="Retención", vencimientos="D=20 M+1 A="),
        PlantillaLinea(orden=3, cuenta="57200001", dhc="C", ayuda="Líquido"),
    ]
    s.add(p)
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def formulario(**cambios):
    datos = {
        "fecha": "150326", "concepto": "Aportación de socios", "plantilla": "",
        "ln-0-cuenta": "57200001", "ln-0-dh": "D", "ln-0-importe": "1000,00", "ln-0-ayuda": "", "ln-0-cuadre": "0", "ln-0-reglas": "", "ln-0-plauto": "1",
        "ln-1-cuenta": "10000000", "ln-1-dh": "H", "ln-1-importe": "1000,00", "ln-1-ayuda": "", "ln-1-cuadre": "0", "ln-1-reglas": "", "ln-1-plauto": "1",
    }
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def _asientos(cliente):
    s = _sesion(cliente)
    try:
        return [(a.id, a.numero, a.concepto, {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}) for a in s.scalars(select(Asiento).where(Asiento.tipo == 4).order_by(Asiento.numero))]
    finally:
        s.close()


def _disparo(r):
    return json.loads(r.headers["HX-Trigger"])


# ---------------------------------------------------------------------------- páginas


def test_las_paginas_y_el_menu(cliente):
    for ruta in (BASE, PL):
        assert cliente.get(ruta).status_code == 200
    panel = cliente.get("/e/prueba/2026").text
    assert "Asientos manuales" in panel and "Plantillas de asientos" in panel
    assert "Desde plantilla" in cliente.get(BASE).text
    f = cliente.get(f"{BASE}/nuevo")
    assert f.status_code == 200 and 'name="ln-0-cuenta"' in f.text and "Guardar asiento" in f.text and "Línea de cuadre" in f.text


# ---------------------------------------------------------------------------- alta, edición y borrado


def test_alta_de_un_asiento_manual(cliente):
    r = cliente.post(f"{BASE}/guardar", data=formulario())
    assert r.status_code == 200 and r.text == ""
    d = _disparo(r)
    assert d["refrescar"] and d["cerrarModal"]
    assert _asientos(cliente) == [(1, 1, "Aportación de socios", {"57200001": D("1000.00"), "10000000": D("-1000.00")})]
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Aportación de socios" in tabla and "1.000,00" in tabla and "57200001, 10000000" in tabla


@pytest.mark.parametrize(
    "cambios, texto",
    [
        ({"ln-1-importe": "900,00"}, "no cuadra"),
        ({"ln-1-cuenta": "99999999"}, "No existe la cuenta 99999999"),
        ({"ln-1-cuenta": ""}, "Falta la cuenta"),
        ({"ln-1-importe": ""}, "Falta el importe"),
        ({"ln-1-importe": "-5"}, "importe negativo"),
        ({"ln-1-importe": "xx"}, "no es un importe válido"),
        ({"fecha": "050327"}, "fuera del ejercicio"),
        ({"fecha": ""}, "Fecha"),
    ],
)
def test_los_errores_no_guardan_nada(cliente, cambios, texto):
    r = cliente.post(f"{BASE}/guardar", data=formulario(**cambios))
    assert r.status_code == 200 and "HX-Trigger" not in r.headers and 'role="alert"' in r.text and "Guardar asiento" in r.text
    assert texto.lower() in r.text.lower(), r.text[:800]
    assert _asientos(cliente) == []


def test_un_asiento_sin_lineas_no_se_graba(cliente):
    r = cliente.post(f"{BASE}/guardar", data={"fecha": "150326", "concepto": "x"})
    assert "al menos dos líneas" in r.text and _asientos(cliente) == []


def test_edicion_conserva_el_numero_y_regenera(cliente):
    cliente.post(f"{BASE}/guardar", data=formulario())
    ident = _asientos(cliente)[0][0]
    f = cliente.get(f"{BASE}/f/{ident}")
    assert f.status_code == 200 and 'value="Aportación de socios"' in f.text and 'value="1000,00"' in f.text and f'name="id" value="{ident}"' in f.text
    r = cliente.post(f"{BASE}/guardar", data=formulario(id=str(ident), concepto="Aportación revisada", **{"ln-0-importe": "1500,00", "ln-1-importe": "1500,00"}))
    assert r.text == ""
    assert _asientos(cliente) == [(ident, 1, "Aportación revisada", {"57200001": D("1500.00"), "10000000": D("-1500.00")})]


def test_borrar_un_asiento(cliente):
    cliente.post(f"{BASE}/guardar", data=formulario())
    r = cliente.post(f"{BASE}/borrar", data={"ids": [_asientos(cliente)[0][0]]})
    assert _disparo(r)["mensaje"]["tipo"] == "ok" and _asientos(cliente) == []


def test_un_ejercicio_cerrado_no_admite_asientos(cliente):
    s = _sesion(cliente)
    s.scalar(select(Ejercicio)).cerrado = True
    s.commit()
    s.close()
    assert "cerrado" in cliente.post(f"{BASE}/guardar", data=formulario()).text and _asientos(cliente) == []


# ---------------------------------------------------------------------------- línea de cuadre y recálculo


def test_la_linea_de_cuadre_se_calcula(cliente):
    datos = formulario(**{"ln-1-importe": "", "ln-1-cuadre": "1", "ln-1-cuenta": "10000000", "ln-0-importe": "250,75"})
    r = cliente.post(f"{BASE}/recalcular", data=datos)
    assert 'name="ln-1-importe" value="250,75"' in r.text and "Cuadrado" in r.text
    assert re.search(r'<option value="H" selected>', r.text)
    assert cliente.post(f"{BASE}/guardar", data=datos).text == ""
    assert _asientos(cliente)[0][3] == {"57200001": D("250.75"), "10000000": D("-250.75")}


def test_acciones_de_lineas(cliente):
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(), "accion": "add-ln"})
    assert 'name="ln-2-cuenta"' in r.text
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(), "accion": "del-ln-0"})
    assert 'name="ln-1-cuenta"' not in r.text
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(), "accion": "cuadrar"})
    assert 'name="ln-2-cuadre" value="1"' in r.text
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(**{"ln-1-importe": "900"}), })
    assert "Descuadre" in r.text and "100,00" in r.text


# ---------------------------------------------------------------------------- vencimientos


def test_vencimientos_de_una_linea_con_signo(cliente):
    datos = formulario(**{"ln-0-cuenta": "17000001", "ln-0-dh": "H", "ln-0-importe": "600,00", "ln-1-cuenta": "57200001", "ln-1-dh": "D", "ln-1-importe": "600,00",
                          "ln-0-plauto": "0", "ln-0-pl-0-fecha": "300426", "ln-0-pl-0-importe": "-300,00", "ln-0-pl-1-fecha": "300526", "ln-0-pl-1-importe": "-300,00"})
    assert cliente.post(f"{BASE}/guardar", data=datos).text == ""
    s = _sesion(cliente)
    v = sorted((x.fecha, x.importe) for x in s.scalars(select(Vencimiento)))
    s.close()
    assert v == [(date(2026, 4, 30), D("-300.00")), (date(2026, 5, 30), D("-300.00"))]
    assert re.search(r'data-clave="vencimientos">2<', cliente.get(f"{BASE}/tabla").text)
    # al editar, quitar un vencimiento lo borra
    ident = _asientos(cliente)[0][0]
    sin_segundo = {k: v for k, v in datos.items() if not k.startswith("ln-0-pl-1-")}
    r = cliente.post(f"{BASE}/guardar", data={**sin_segundo, "id": str(ident)})
    assert r.text == ""
    s = _sesion(cliente)
    assert s.scalar(select(func.count()).select_from(Vencimiento)) == 1
    s.close()


def test_un_vencimiento_sin_importe_da_error(cliente):
    datos = formulario(**{"ln-0-plauto": "0", "ln-0-pl-0-fecha": "300426", "ln-0-pl-0-importe": ""})
    assert "Falta el importe del vencimiento" in cliente.post(f"{BASE}/guardar", data=datos).text and _asientos(cliente) == []


# ---------------------------------------------------------------------------- justificantes


def test_justificante_de_un_asiento(cliente):
    r = cliente.post(f"{BASE}/guardar", data=formulario(), files=[("ficheros", ("recibo.pdf", PDF, "application/pdf"))])
    assert r.text == ""
    s = _sesion(cliente)
    a = s.scalar(select(Adjunto))
    asiento_id = a.asiento_id
    ruta = cliente.app.state.config.almacen_de_adjuntos().ruta(a)
    s.close()
    assert ruta.read_bytes() == PDF and cliente.get(f"/e/prueba/2026/adjuntos/{a.id}").content == PDF
    assert "<iframe" in cliente.get(f"{BASE}/f/{asiento_id}").text
    assert re.search(r'data-clave="justificantes">1<', cliente.get(f"{BASE}/tabla").text)
    cliente.post(f"{BASE}/borrar", data={"ids": [asiento_id]})
    assert not ruta.exists() and _asientos(cliente) == []


def test_un_fichero_no_valido_no_guarda_el_asiento(cliente):
    r = cliente.post(f"{BASE}/guardar", data=formulario(), files=[("ficheros", ("a.txt", b"hola", "text/plain"))])
    assert "sólo se admiten ficheros PDF y JPG" in r.text and _asientos(cliente) == []


# ---------------------------------------------------------------------------- plantillas


def test_asiento_desde_plantilla(cliente):
    form = cliente.get(f"{BASE}/accion/plantilla")
    assert form.status_code == 200 and "NOMINA {mes}/{año}" in form.text
    pid = re.search(r'<option value="(\d+)"', form.text).group(1)
    r = cliente.post(f"{BASE}/accion/plantilla", data={"plantilla": pid, "fecha": "050326"})
    assert 'value="NOMINA 3/2026"' in r.text and 'name="ln-0-cuenta" value="64000000"' in r.text and 'name="ln-2-cuadre" value="1"' in r.text
    # se teclean los importes: el cuadre y el vencimiento de la retención salen solos
    datos = formulario(plantilla=pid, concepto="NOMINA 3/2026", fecha="050326", **{
        "ln-0-cuenta": "64000000", "ln-0-dh": "D", "ln-0-importe": "2000,00", "ln-0-ayuda": "Sueldo bruto",
        "ln-1-cuenta": "47510000", "ln-1-dh": "H", "ln-1-importe": "300,00", "ln-1-ayuda": "Retención", "ln-1-reglas": "D=20 M+1 A=",
        "ln-2-cuenta": "57200001", "ln-2-dh": "H", "ln-2-importe": "", "ln-2-ayuda": "Líquido", "ln-2-cuadre": "1", "ln-2-reglas": "", "ln-2-plauto": "1"})
    c = cliente.post(f"{BASE}/recalcular", data=datos)
    assert 'name="ln-2-importe" value="1700,00"' in c.text and 'name="ln-1-pl-0-fecha" value="20/04/2026"' in c.text and 'name="ln-1-pl-0-importe" value="-300,00"' in c.text
    assert cliente.post(f"{BASE}/guardar", data=datos).text == ""
    a = _asientos(cliente)[0]
    assert a[2] == "NOMINA 3/2026" and a[3] == {"64000000": D("2000.00"), "47510000": D("-300.00"), "57200001": D("-1700.00")}
    s = _sesion(cliente)
    assert [(v.fecha, v.importe) for v in s.scalars(select(Vencimiento))] == [(date(2026, 4, 20), D("-300.00"))]
    s.close()


def test_desde_plantilla_pide_plantilla_y_fecha_validas(cliente):
    r = cliente.post(f"{BASE}/accion/plantilla", data={"plantilla": "", "fecha": "050326"})
    assert "Elija una plantilla" in r.text
    pid = re.search(r'<option value="(\d+)"', cliente.get(f"{BASE}/accion/plantilla").text).group(1)
    assert "fuera del ejercicio" in cliente.post(f"{BASE}/accion/plantilla", data={"plantilla": pid, "fecha": "050327"}).text
    assert cliente.get(f"{BASE}/accion/otra").status_code == 404


def _plantilla_form(**cambios):
    datos = {"titulo": "CUOTA PRESTAMO {mes}/{año}", "ln-0-cuenta": "17000001", "ln-0-dhc": "D", "ln-0-ayuda": "Capital", "ln-0-importe": "", "ln-0-reglas": "",
             "ln-1-cuenta": "57200001", "ln-1-dhc": "C", "ln-1-ayuda": "", "ln-1-importe": "", "ln-1-reglas": ""}
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def test_alta_edicion_y_borrado_de_plantillas(cliente):
    f = cliente.get(f"{PL}/nuevo")
    assert f.status_code == 200 and "Reglas de vencimiento" in f.text and 'name="titulo"' in f.text
    assert cliente.post(f"{PL}/guardar", data=_plantilla_form()).text == ""
    tabla = cliente.get(f"{PL}/tabla").text
    assert "CUOTA PRESTAMO" in tabla and "NOMINA" in tabla
    s = _sesion(cliente)
    p = s.scalar(select(Plantilla).where(Plantilla.titulo.like("CUOTA%")))
    pid, lineas = p.id, [(l.cuenta, l.dhc) for l in p.lineas]
    s.close()
    assert lineas == [("17000001", "D"), ("57200001", "C")]
    assert 'value="CUOTA PRESTAMO {mes}/{año}"' in cliente.get(f"{PL}/f/{pid}").text
    assert cliente.post(f"{PL}/guardar", data=_plantilla_form(id=str(pid), titulo="CUOTA PRESTAMO BANCO", **{"ln-1-reglas": "D=30 M+1 A="})).text == ""
    s = _sesion(cliente)
    p = s.get(Plantilla, pid)
    assert p.titulo == "CUOTA PRESTAMO BANCO" and p.lineas[1].vencimientos == "D=30 M+1 A=" and s.scalar(select(func.count()).select_from(PlantillaLinea)) == 5
    s.close()
    assert _disparo(cliente.post(f"{PL}/borrar", data={"ids": [pid]}))["mensaje"]["tipo"] == "ok"
    s = _sesion(cliente)
    assert s.get(Plantilla, pid) is None and s.scalar(select(func.count()).select_from(PlantillaLinea)) == 3
    s.close()


@pytest.mark.parametrize(
    "cambios, texto",
    [
        ({"titulo": ""}, "Falta el título"),
        ({"titulo": "NOMINA {mes}/{año}"}, "Ya existe una plantilla"),
        ({"ln-0-cuenta": "123"}, "no tiene 8 dígitos"),
        ({"ln-0-dhc": "C"}, "apuntes de cuadre"),
        ({"ln-0-reglas": "mañana"}, "no es válida"),
        ({"ln-0-importe": "abc"}, "no es un importe válido"),
    ],
)
def test_plantillas_incorrectas(cliente, cambios, texto):
    r = cliente.post(f"{PL}/guardar", data=_plantilla_form(**cambios))
    assert 'role="alert"' in r.text and texto in r.text and "HX-Trigger" not in r.headers
    s = _sesion(cliente)
    assert s.scalar(select(func.count()).select_from(Plantilla)) == 1
    s.close()


def test_acciones_del_formulario_de_plantilla(cliente):
    r = cliente.post(f"{PL}/recalcular", data={**_plantilla_form(), "accion": "add-ln"})
    assert 'name="ln-2-cuenta"' in r.text
    r = cliente.post(f"{PL}/recalcular", data={**_plantilla_form(), "accion": "del-ln-0"})
    assert 'name="ln-1-cuenta"' not in r.text


# ---------------------------------------------------------------------------- exportación


def test_el_listado_de_asientos_se_exporta(cliente):
    cliente.post(f"{BASE}/guardar", data=formulario())
    assert cliente.get(f"{BASE}/exportar.xlsx").status_code == 200
    assert cliente.get(f"{PL}/exportar.pdf").headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
@pytest.mark.parametrize("clave", ["empresa_a", "empresa_b"])
def test_regrabar_cada_asiento_manual_real_desde_el_formulario_no_cambia_el_diario(clave, tmp_path):
    from conftest import EMPRESAS_MGD_2021, _carpeta_empresa

    from conta_pridalac.db.sesion import crear_motor
    from conta_pridalac.migracion.mgd import cargar_mgd
    from conta_pridalac.web.asientos import construir_y_grabar, estado_de_asiento
    from conta_pridalac.web.listados import Contexto

    origen = _carpeta_empresa(clave)
    if not (origen / "Diario.dbf").exists():
        pytest.skip(f"No hay datos MGD de {clave}")
    motor = crear_motor(None)
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    datos = EMPRESAS_MGD_2021[clave]
    res = cargar_mgd(sesion, origen, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
    sesion.commit()
    ej = sesion.get(Ejercicio, res.ejercicio_id)
    ctx = Contexto(sesion, sesion.get(Empresa, ej.empresa_id), ej, clave, Configuracion(datos=tmp_path, almacen=tmp_path / "alm"))

    def foto():
        estado = {}
        for a in sesion.scalars(select(Asiento)):
            lineas: Counter = Counter()
            for ap in a.apuntes:
                lineas[ap.cuenta.codigo] += ap.debe - ap.haber
            estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, a.concepto, dict(lineas))
        venc = sorted((v.origen_numero, v.importe, v.fecha) for v in sesion.scalars(select(Vencimiento)))
        return estado, venc

    antes = foto()
    manuales = list(sesion.scalars(select(Asiento).where(Asiento.tipo == 4)))  # Empresa A no tiene ninguno en 2021
    regrabables = [a for a in manuales if ej.fecha_inicio <= a.fecha <= ej.fecha_fin]  # los fechados en 2020 el formulario se niega a grabarlos
    for a in regrabables:
        e = estado_de_asiento(ctx, a)
        asiento, errores, _ = construir_y_grabar(ctx, e, [])
        assert errores == [] and asiento is not None, (a.identificador, errores)
    sesion.flush()
    assert foto() == antes
    # y el listado y el formulario de cada uno salen
    motor_archivo = crear_motor(tmp_path / "bd" / f"{clave}.sqlite") if (tmp_path / "bd").mkdir() is None else None
    crear_esquema(motor_archivo)
    otra = nueva_sesion(motor_archivo)
    cargar_mgd(otra, origen, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
    otra.commit()
    otra.close()
    motor_archivo.dispose()
    cliente = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "alm2")))
    tabla = cliente.get(f"/e/{clave}/2021/asientos/tabla").text
    ids = sorted(set(re.findall(r'data-id="(\d+)"', tabla)), key=int)
    assert len(ids) == len(manuales)
    if clave == "empresa_b":
        assert manuales and len(regrabables) < len(manuales)  # hay asientos manuales de 2020 dentro del ejercicio 2021 (dato conocido de MGD)
    for i in ids:
        assert cliente.get(f"/e/{clave}/2021/asientos/f/{i}").status_code == 200
    assert cliente.get(f"/e/{clave}/2021/plantillas/tabla").status_code == 200
