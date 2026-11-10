"""Bienes de inversión en la web: ficha, cuadro, amortización, baja y libro de bienes (IVA)."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import AmortizacionPeriodo, Asiento, BienInversion, Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
B26 = "/e/prueba/2026"
B27 = "/e/prueba/2027"


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba")
    s.add(e)
    s.add_all([Ejercicio(anio=a, fecha_inicio=date(a, 1, 1), fecha_fin=date(a, 12, 31), empresa=e) for a in (2026, 2027)])
    s.flush()
    for codigo, nombre in (("21800000", "ELEMENTOS DE TRANSPORTE"), ("28180000", "AMORT. ACUM. TRANSPORTE"), ("68100000", "AMORTIZACION"), ("67100000", "PERDIDAS INMOVILIZADO"),
                           ("77100000", "BENEFICIOS INMOVILIZADO"), ("57200001", "BANCO"), ("21100000", "CONSTRUCCIONES")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def ficha(**cambios):
    datos = {"descripcion": "FURGONETA", "tipo_elemento": "Vehículo", "numero_factura_compra": "F-1", "fecha_adquisicion": "010126", "fecha_funcionamiento": "010126",
             "precio_compra": "5000,00", "valor_residual": "", "periodos_vida": "5", "coeficiente_pct": "", "meses_periodo": "12", "iva_soportado": "",
             "cuenta_inmovilizado": "21800000", "cuenta_amortizacion": "28180000", "cuenta_dotacion": "68100000", "notas": "", "accion": "guardar"}
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def _bien(cliente, descripcion="FURGONETA"):
    s = _sesion(cliente)
    try:
        b = s.scalar(select(BienInversion).where(BienInversion.descripcion == descripcion))
        if b is None:
            return None
        return dict(id=b.id, periodos=[(a.id, a.anio, a.desde, a.hasta, a.importe_previsto, a.importe_contable, a.asiento_id) for a in b.amortizaciones], baja=b.fecha_baja,
                    asiento_baja=b.asiento_baja_id, precio=b.precio_compra)
    finally:
        s.close()


def _crear(cliente, **cambios):
    r = cliente.post(f"{B26}/bienes/guardar", data=ficha(**cambios))
    assert 'role="alert"' not in r.text, r.text[:500]
    return _bien(cliente, cambios.get("descripcion", "FURGONETA"))


def _disparo(r):
    assert "HX-Trigger" in r.headers, re.findall(r'role="alert">([^<]*)', r.text) or r.text[:300]  # si falla, se ve el aviso de error del formulario
    return json.loads(r.headers["HX-Trigger"])


def _asientos_q(cliente):
    s = _sesion(cliente)
    try:
        return [(a.identificador, a.fecha, a.subtipo, {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}) for a in s.scalars(select(Asiento).order_by(Asiento.fecha, Asiento.numero))]
    finally:
        s.close()


# ---------------------------------------------------------------------------- páginas y alta


def test_paginas_y_menu(cliente):
    for n in ("bienes", "bienes-iva"):
        assert cliente.get(f"{B26}/{n}").status_code == 200 and "<table" in cliente.get(f"{B26}/{n}/tabla").text
    panel = cliente.get(B26).text
    assert "Bienes de inversión" in panel and "Libro de bienes de inversión" in panel
    f = cliente.get(f"{B26}/bienes/nuevo")
    assert f.status_code == 200 and "Crear el bien" in f.text and 'name="cuenta_dotacion"' in f.text and "Cuadro de amortización" not in f.text
    assert "Amortizar el ejercicio" in cliente.get(f"{B26}/bienes").text


def test_alta_de_un_bien_genera_el_cuadro_y_deja_el_formulario_abierto(cliente):
    r = cliente.post(f"{B26}/bienes/guardar", data=ficha())
    assert r.status_code == 200 and "Cuadro de amortización" in r.text and "Bien creado" in _disparo(r)["mensaje"]["texto"] and _disparo(r)["refrescar"]
    b = _bien(cliente)
    assert [p[1] for p in b["periodos"]] == [2026, 2027, 2028, 2029, 2030] and all(p[4] == D("1000.00") and p[5] is None for p in b["periodos"])
    tabla = cliente.get(f"{B26}/bienes/tabla").text
    assert "FURGONETA" in tabla and "5.000,00" in tabla and "Sin amortizar" in tabla and "21800000" in tabla


@pytest.mark.parametrize(
    "cambios, texto",
    [
        ({"descripcion": ""}, "Falta la descripción"),
        ({"precio_compra": ""}, "Falta el precio"),
        ({"precio_compra": "abc"}, "no es un importe válido"),
        ({"fecha_funcionamiento": ""}, "Falta «Puesta en funcionamiento»"),
        ({"fecha_funcionamiento": "320126"}, "no existe en el calendario"),
        ({"periodos_vida": "", "coeficiente_pct": ""}, "vida útil"),
        ({"periodos_vida": "cinco"}, "no es un número entero"),
        ({"cuenta_dotacion": "99999999"}, "No existe la cuenta 99999999"),
        ({"cuenta_amortizacion": ""}, "Falta la cuenta"),
        ({"valor_residual": "5000,00"}, "mayor que cero"),
    ],
)
def test_alta_incorrecta_no_guarda_nada(cliente, cambios, texto):
    r = cliente.post(f"{B26}/bienes/guardar", data=ficha(**cambios))
    assert 'role="alert"' in r.text and texto in r.text and "HX-Trigger" not in r.headers
    assert _bien(cliente) is None


def test_porcentaje_en_lugar_de_vida_util(cliente):
    b = _crear(cliente, periodos_vida="", coeficiente_pct="20,00")
    assert len(b["periodos"]) == 5 and b["periodos"][0][4] == D("1000.00")


# ---------------------------------------------------------------------------- edición


def test_editar_la_ficha_rehace_el_cuadro_y_cierra(cliente):
    b = _crear(cliente)
    r = cliente.post(f"{B26}/bienes/guardar", data={**ficha(descripcion="FURGONETA BLANCA", periodos_vida="10"), "id": str(b["id"])})
    assert r.text == "" and _disparo(r)["cerrarModal"]
    nuevo = _bien(cliente, "FURGONETA BLANCA")
    assert nuevo["id"] == b["id"] and len(nuevo["periodos"]) == 10 and nuevo["periodos"][0][4] == D("500.00")
    f = cliente.get(f"{B26}/bienes/f/{b['id']}")
    assert 'value="FURGONETA BLANCA"' in f.text and 'name="periodos_vida" type="text" value="10"' in f.text and "Cuadro de amortización" in f.text


# ---------------------------------------------------------------------------- amortización


def _accion(cliente, base, bien_id, accion, **extra):
    return cliente.post(f"{base}/bienes/guardar", data={**ficha(), "id": str(bien_id), "accion": accion, **extra})


def test_amortizar_y_deshacer_un_periodo(cliente):
    b = _crear(cliente)
    pid = b["periodos"][0][0]
    r = _accion(cliente, B26, b["id"], f"amortizar-{pid}")
    assert "Contabilizado" in r.text and "Amortizado el periodo 2026" in _disparo(r)["mensaje"]["texto"] and "1000,00" in _disparo(r)["mensaje"]["texto"]
    assert _asientos_q(cliente) == [("9.1", date(2026, 12, 31), "Q", {"68100000": D("1000.00"), "28180000": D("-1000.00")})]
    assert re.search(r'value="deshacer-%d"' % pid, r.text)
    assert "En amortización" in cliente.get(f"{B26}/bienes/tabla").text
    r = _accion(cliente, B26, b["id"], f"deshacer-{pid}")
    assert "Deshecha" in _disparo(r)["mensaje"]["texto"] and _asientos_q(cliente) == [] and _bien(cliente)["periodos"][0][5] is None


def test_editar_a_mano_los_importes_del_cuadro(cliente):
    b = _crear(cliente)
    p0, p1 = b["periodos"][0][0], b["periodos"][1][0]
    f = cliente.get(f"{B26}/bienes/f/{b['id']}").text
    assert f'name="prev-{p0}"' in f and f'name="cont-{p0}"' in f and "Guardar los importes del cuadro" in f
    r = cliente.post(f"{B26}/bienes/guardar", data={"id": str(b["id"]), "accion": "periodos", f"prev-{p0}": "1.200,50", f"cont-{p0}": "1.200,50", f"prev-{p1}": "900,00", f"cont-{p1}": ""})
    assert "2 periodo(s) modificado(s)" in _disparo(r)["mensaje"]["texto"]
    per = {x[0]: x for x in _bien(cliente)["periodos"]}
    assert per[p0][4] == D("1200.50") and per[p0][5] == D("1200.50") and per[p0][6] is None  # fijado a mano: sin asiento
    assert per[p1][4] == D("900.00") and per[p1][5] is None
    assert _asientos_q(cliente) == []
    r = cliente.post(f"{B26}/bienes/guardar", data={"id": str(b["id"]), "accion": "periodos", f"prev-{p1}": "900,00", f"cont-{p1}": ""})
    assert "No había cambios" in _disparo(r)["mensaje"]["texto"]
    # los importes negativos se rechazan
    r = cliente.post(f"{B26}/bienes/guardar", data={"id": str(b["id"]), "accion": "periodos", f"prev-{p1}": "-5,00", f"cont-{p1}": ""})
    assert "negativos" in r.text or "negativos" in str(r.headers)


def test_un_periodo_de_otro_ejercicio_no_se_amortiza_desde_este(cliente):
    b = _crear(cliente)
    pid_2027 = b["periodos"][1][0]
    r = _accion(cliente, B26, b["id"], f"amortizar-{pid_2027}")
    assert "en otro ejercicio" in r.text and _asientos_q(cliente) == []
    assert "otro ejercicio" in cliente.get(f"{B26}/bienes/f/{b['id']}").text
    assert 'value="amortizar-%d"' % pid_2027 in cliente.get(f"{B27}/bienes/f/{b['id']}").text  # en 2027 sí


def test_amortizar_todo_el_ejercicio(cliente):
    _crear(cliente)
    _crear(cliente, descripcion="ORDENADOR", precio_compra="1200,00", periodos_vida="4")
    vista = cliente.get(f"{B26}/bienes/accion/amortizar")
    assert vista.status_code == 200 and "FURGONETA" in vista.text and "ORDENADOR" in vista.text and "1.300,00" in vista.text and "Amortizar 2 periodo(s)" in vista.text
    r = cliente.post(f"{B26}/bienes/accion/amortizar", data={})
    assert r.text == "" and "Amortizados 2 periodo(s) por 1300,00" in _disparo(r)["mensaje"]["texto"]
    assert len(_asientos_q(cliente)) == 2
    assert "No hay periodos pendientes" in cliente.get(f"{B26}/bienes/accion/amortizar").text
    assert "fecha" in cliente.post(f"{B26}/bienes/accion/amortizar", data={"hasta": "zz"}).text.lower()
    assert cliente.get(f"{B26}/bienes/accion/otra").status_code == 404


def test_un_ejercicio_cerrado_no_amortiza(cliente):
    b = _crear(cliente)
    s = _sesion(cliente)
    s.scalar(select(Ejercicio).where(Ejercicio.anio == 2026)).cerrado = True
    s.commit()
    s.close()
    r = _accion(cliente, B26, b["id"], f"amortizar-{b['periodos'][0][0]}")
    assert "cerrado" in r.text and _asientos_q(cliente) == []


# ---------------------------------------------------------------------------- baja


def test_baja_con_venta_y_su_asiento(cliente):
    b = _crear(cliente)
    r = _accion(cliente, B26, b["id"], "baja", fecha_baja="300627", causa_baja="VENTA")
    assert "Baja el 30/06/2027" in _disparo(r)["mensaje"]["texto"] and "Asiento de baja" in r.text
    assert [p[1] for p in _bien(cliente)["periodos"]] == [2026, 2027] and _bien(cliente)["baja"] == date(2027, 6, 30)
    # antes de amortizar no se puede contabilizar la baja
    assert "Faltan por amortizar" in _accion(cliente, B27, b["id"], "asiento-baja", fecha_asiento_baja="300627").text
    pid26, pid27 = [p[0] for p in _bien(cliente)["periodos"]]
    _accion(cliente, B26, b["id"], f"amortizar-{pid26}")
    _accion(cliente, B27, b["id"], f"amortizar-{pid27}")
    assert "cobro" in _accion(cliente, B27, b["id"], "asiento-baja", fecha_asiento_baja="300627", precio_venta="4000,00", cuenta_cobro="").text
    r = _accion(cliente, B27, b["id"], "asiento-baja", fecha_asiento_baja="300627", precio_venta="4000,00", cuenta_cobro="57200001", cuenta_perdidas="67100000", cuenta_beneficios="77100000")
    assert "Asiento de baja 9.2: beneficio de 495,89" in _disparo(r)["mensaje"]["texto"] and "Deshacer el asiento de baja" in r.text
    baja = _asientos_q(cliente)[-1]
    assert baja[2] == "B" and baja[3] == {"21800000": D("-5000.00"), "28180000": D("1495.89"), "57200001": D("4000.00"), "77100000": D("-495.89")}
    assert "Anular la baja" not in r.text
    assert "Dado de baja" in cliente.get(f"{B27}/bienes/tabla").text
    r = _accion(cliente, B27, b["id"], "deshacer-asiento-baja")
    assert "Asiento de baja deshecho" in _disparo(r)["mensaje"]["texto"] and _bien(cliente)["asiento_baja"] is None
    r = _accion(cliente, B27, b["id"], "anular-baja")
    assert "Baja anulada" in _disparo(r)["mensaje"]["texto"] and len(_bien(cliente)["periodos"]) == 5 and _bien(cliente)["baja"] is None


def test_errores_de_la_baja(cliente):
    b = _crear(cliente)
    assert "Falta la fecha de baja" in _accion(cliente, B26, b["id"], "baja", fecha_baja="").text
    assert "no es una fecha" in _accion(cliente, B26, b["id"], "baja", fecha_baja="zz").text
    assert "anterior a la puesta en funcionamiento" in _accion(cliente, B26, b["id"], "baja", fecha_baja="010125").text
    assert "Guarde primero" in cliente.post(f"{B26}/bienes/guardar", data={**ficha(), "accion": "baja", "fecha_baja": "010126"}).text
    assert "Acción desconocida" in _accion(cliente, B26, b["id"], "inventada").text


# ---------------------------------------------------------------------------- borrar


def test_borrar_bienes(cliente):
    libre = _crear(cliente, descripcion="LIBRE")
    amortizado = _crear(cliente, descripcion="AMORTIZADO")
    _accion(cliente, B26, amortizado["id"], f"amortizar-{amortizado['periodos'][0][0]}")
    assert _disparo(cliente.post(f"{B26}/bienes/borrar", data={"ids": [libre["id"]]}))["mensaje"]["tipo"] == "ok" and _bien(cliente, "LIBRE") is None
    d = _disparo(cliente.post(f"{B26}/bienes/borrar", data={"ids": [amortizado["id"]]}))["mensaje"]
    assert d["tipo"] == "error" and "amortizado" in d["texto"] and _bien(cliente, "AMORTIZADO") is not None
    s = _sesion(cliente)
    assert s.scalar(select(func.count()).select_from(AmortizacionPeriodo)) == 5  # los del bien que queda
    s.close()


# ---------------------------------------------------------------------------- libro de bienes de inversión (IVA)


def test_libro_de_bienes_de_inversion(cliente):
    _crear(cliente, iva_soportado="1050,00")
    _crear(cliente, descripcion="CON IVA ABSURDO", iva_soportado="361217,00")
    _crear(cliente, descripcion="PEQUENO", precio_compra="500,00", iva_soportado="105,00")
    html = cliente.get(f"{B26}/bienes-iva/tabla").text
    assert "FURGONETA" in html and "1.050,00" in html and "CON IVA ABSURDO" in html and "supera el precio de compra" in html and "PEQUENO" not in html
    assert cliente.get(f"{B26}/bienes-iva/exportar.xlsx").status_code == 200


def test_estado_del_bien_y_filtros(cliente):
    b = _crear(cliente)
    _crear(cliente, descripcion="VENDIDO")
    _accion(cliente, B26, _bien(cliente, "VENDIDO")["id"], "baja", fecha_baja="300627")
    assert "FURGONETA" in cliente.get(f"{B26}/bienes/tabla", params={"estado": "uso"}).text and "VENDIDO" not in cliente.get(f"{B26}/bienes/tabla", params={"estado": "uso"}).text
    assert "VENDIDO" in cliente.get(f"{B26}/bienes/tabla", params={"estado": "baja"}).text
    assert "No hay filas" in cliente.get(f"{B26}/bienes/tabla", params={"estado": "amortizados"}).text
    assert b["id"]


def test_los_listados_de_bienes_se_exportan(cliente):
    _crear(cliente)
    assert cliente.get(f"{B26}/bienes/exportar.xlsx").status_code == 200
    assert cliente.get(f"{B26}/bienes/exportar.pdf").headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_los_bienes_reales_se_abren_y_se_regraban_sin_cambios(tmp_path):
    """Empresa A y Empresa B: cada bien de MGD se abre, se guarda tal cual (ficha) y su cuadro queda idéntico."""
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
    for clave, esperados in (("empresa_a", 22), ("empresa_b", 1)):
        base = f"/e/{clave}/2021"
        ids = sorted(set(re.findall(r'data-id="(\d+)"', cliente.get(f"{base}/bienes/tabla").text)), key=int)
        assert len(ids) == esperados
        sesion = cliente.app.state.config.sesion(clave)
        antes = [(a.bien_id, a.desde, a.hasta, a.importe_previsto, a.importe_contable, a.origen if a.importe_contable is not None else None) for a in sesion.scalars(select(AmortizacionPeriodo).order_by(AmortizacionPeriodo.bien_id, AmortizacionPeriodo.desde))]
        sesion.close()
        for i in ids:
            f = cliente.get(f"{base}/bienes/f/{i}")
            assert f.status_code == 200 and "Cuadro de amortización" in f.text
            # se envía la ficha tal como la muestra el formulario
            campos = dict(re.findall(r'<input[^>]*name="(\w+)"[^>]*value="([^"]*)"', f.text))
            campos = {k: v.replace("&#39;", "'").replace("&amp;", "&") for k, v in campos.items()}
            r = cliente.post(f"{base}/bienes/guardar", data={**campos, "id": i, "accion": "guardar"})
            assert r.text == "", (clave, i, r.text[:600])
        sesion = cliente.app.state.config.sesion(clave)
        despues = [(a.bien_id, a.desde, a.hasta, a.importe_previsto, a.importe_contable, a.origen if a.importe_contable is not None else None) for a in sesion.scalars(select(AmortizacionPeriodo).order_by(AmortizacionPeriodo.bien_id, AmortizacionPeriodo.desde))]
        sesion.close()
        assert despues == antes, clave
        assert cliente.get(f"{base}/bienes-iva/tabla").status_code == 200
        assert "Amortizar" in cliente.get(f"{base}/bienes/accion/amortizar").text
