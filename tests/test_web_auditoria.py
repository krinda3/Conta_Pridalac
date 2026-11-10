"""Pantalla de la auditoría de integridad."""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.auditoria import auditar
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.auditoria import CATALOGO, nombre_de
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/auditoria"


@pytest.fixture(autouse=True)
def a_principios_de_ano(monkeypatch):
    """Los plazos de los modelos dependen del reloj (su vigilancia se prueba en test_vigilancia.py): aquí, un día sin plazos a la vista (5 de enero de 2021, antes de todos los ejercicios que usan estas pruebas)."""
    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.hoy", lambda: date(2021, 1, 5))


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
    for codigo, nombre in (("57200001", "BANCO"), ("10000000", "CAPITAL"), ("40000001", "PROVEEDOR"), ("62900000", "GASTOS"), ("47200021", "IVA SOPORTADO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    prov = Tercero(empresa_id=e.id, clase="P", nombre="Proveedor", cuenta_id=ids["40000001"])
    s.add(prov)
    s.flush()
    grabar_asiento(s, ej, tipo=4, numero=1, fecha=date(2026, 1, 2), concepto="CAPITAL", lineas=[LineaAsiento("57200001", D(5000)), LineaAsiento("10000000", D(-5000))])
    s.commit()
    s.close()
    cl = TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))
    cl.ids, cl.prov = ids, prov.id
    return cl


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _con_una_factura(cliente):
    s = _sesion(cliente)
    ej = s.scalar(select(Ejercicio))
    f = Factura(ejercicio_id=ej.id, sentido="R", numero=1, fecha_contable=date(2026, 2, 10), fecha_factura=date(2026, 2, 10), numero_factura="F1", total=D("121.00"), tercero_id=cliente.prov,
                cuenta_tercero_id=cliente.ids["40000001"], cuenta_contrapartida_id=cliente.ids["62900000"], ivas=[FacturaIva(base=D("100.00"), pct_iva=D("21.00"), cuota_iva=D("21.00"), cuenta_iva_id=cliente.ids["47200021"])])
    grabar_asiento_de = grabar_factura(s, ej, f)
    s.commit()
    s.close()
    return grabar_asiento_de


# ---------------------------------------------------------------------------- el catálogo


def test_el_catalogo_cubre_todas_las_comprobaciones():
    fuente = (Path(__file__).resolve().parents[1] / "src" / "conta_pridalac" / "auditoria.py").read_text(encoding="utf-8")
    codigos = set(re.findall(r'Hallazgo\(\s*(?:\n\s*)?"([a-z_]+)"', fuente))
    assert len(codigos) >= 25
    assert codigos <= set(CATALOGO), codigos - set(CATALOGO)
    for codigo, (nombre, que, como, pantalla) in CATALOGO.items():
        assert nombre and que and como, codigo
    assert nombre_de("inventada_nueva") == "Inventada nueva"


# ---------------------------------------------------------------------------- listado y ficha


def test_una_contabilidad_limpia(cliente):
    assert cliente.get(BASE).status_code == 200 and "Auditoría de integridad" in cliente.get("/e/prueba/2026").text
    html = cliente.get(f"{BASE}/tabla").text
    assert "Sin hallazgos" in html and "No hay filas" in html


def test_errores_y_avisos(cliente):
    _con_una_factura(cliente)
    s = _sesion(cliente)
    s.execute(delete(Asiento).where(Asiento.tipo == 2))  # la factura se queda sin su asiento
    s.commit()
    s.close()
    html = cliente.get(f"{BASE}/tabla").text
    assert "1 error(es) y 1 aviso(s)" in html and "hay que corregir los errores antes de cerrar" in html
    assert "Factura sin asiento" in html and "Gasto sin justificante" in html and 'class="fila-error"' in html
    assert html.index("Factura sin asiento") < html.index("Gasto sin justificante")  # los errores primero
    solo_errores = cliente.get(f"{BASE}/tabla", params={"gravedad": "ERROR"}).text
    assert "Factura sin asiento" in solo_errores and "Gasto sin justificante" not in solo_errores and "1 error(es) y 0 aviso(s)" in solo_errores
    assert "Gasto sin justificante" in cliente.get(f"{BASE}/tabla", params={"comprobacion": "gasto_sin_justificante"}).text
    assert "No hay filas" in cliente.get(f"{BASE}/tabla", params={"comprobacion": "saldo_de_banco"}).text


def test_ficha_de_un_hallazgo(cliente):
    _con_una_factura(cliente)
    s = _sesion(cliente)
    s.execute(delete(Asiento).where(Asiento.tipo == 2))
    s.commit()
    s.close()
    html = cliente.get(f"{BASE}/tabla").text
    ident = re.search(r'data-id="(factura_sin_asiento~[0-9a-f]+)"', html).group(1)
    f = cliente.get(f"{BASE}/f/{ident}")
    assert f.status_code == 200
    for esperado in ("Error: Factura sin asiento", "impide cerrar el ejercicio", "Qué significa", "Cómo se corrige", "guárdela de nuevo", "Pantalla «Facturas recibidas»", f"/e/prueba/2026/facturas-recibidas"):
        assert esperado in f.text, esperado
    assert "Abrir la factura recibida nº 1" in f.text  # enlace a la factura concreta, no al listado
    s = _sesion(cliente)
    fid = s.scalar(select(Factura.id).where(Factura.numero == 1))
    s.close()
    assert f"/e/prueba/2026/facturas-recibidas?abrir={fid}" in f.text
    pagina = cliente.get(f"/e/prueba/2026/facturas-recibidas?abrir={fid}")  # la página del listado abre ese registro en el diálogo, con el tema de la aplicación
    assert pagina.status_code == 200 and "get('abrir')" in pagina.text and "/tema.css" in pagina.text
    assert cliente.get(f"/e/prueba/2026/facturas-recibidas/f/{fid}").status_code == 200
    assert cliente.get("/favicon.ico").headers["content-type"].startswith("image/svg")
    assert cliente.get(f"{BASE}/f/no-existe~0000000000").status_code == 404


def test_si_la_referencia_es_un_asiento_se_enseña(cliente):
    s = _sesion(cliente)
    ej = s.scalar(select(Ejercicio))
    a = Asiento(ejercicio_id=ej.id, tipo=4, numero=7, sub=0, fecha=date(2025, 12, 31), concepto="FUERA DE FECHA", subtipo="M")
    a.apuntes = [Apunte(orden=1, cuenta_id=cliente.ids["57200001"], debe=D("10.00")), Apunte(orden=2, cuenta_id=cliente.ids["10000000"], haber=D("10.00"))]
    s.add(a)
    s.commit()
    s.close()
    ident = re.search(r'data-id="(asiento_fuera_del_ejercicio~[0-9a-f]+)"', cliente.get(f"{BASE}/tabla").text).group(1)
    f = cliente.get(f"{BASE}/f/{ident}").text
    assert "Asiento 4.7 · 31/12/2025 · FUERA DE FECHA" in f and "57200001" in f and "10,00" in f and "Pantalla «Asientos manuales»" in f


def test_la_pantalla_sugerida_depende_del_tipo_de_asiento(cliente):
    s = _sesion(cliente)
    ej = s.scalar(select(Ejercicio))
    a = Asiento(ejercicio_id=ej.id, tipo=3, numero=5, sub=0, fecha=date(2025, 12, 31), concepto="PAGO FUERA", subtipo="M")
    a.apuntes = [Apunte(orden=1, cuenta_id=cliente.ids["57200001"], debe=D("10.00")), Apunte(orden=2, cuenta_id=cliente.ids["10000000"], haber=D("10.00"))]
    s.add(a)
    s.commit()
    s.close()
    ident = re.search(r'data-id="(asiento_fuera_del_ejercicio~[0-9a-f]+)"', cliente.get(f"{BASE}/tabla").text).group(1)
    f = cliente.get(f"{BASE}/f/{ident}").text
    assert "Pantalla «Movimientos de banco»" in f and "/e/prueba/2026/movimientos" in f


def test_la_auditoria_se_exporta(cliente):
    _con_una_factura(cliente)
    assert cliente.get(f"{BASE}/exportar.xlsx").status_code == 200
    assert cliente.get(f"{BASE}/exportar.pdf").headers["content-type"] == "application/pdf"


def test_el_cierre_enlaza_con_la_auditoria(cliente):
    assert f"{BASE}" in cliente.get("/e/prueba/2026/ejercicios/f/2026").text


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
def test_auditoria_con_los_datos_reales(tmp_path):
    """La pantalla muestra exactamente los hallazgos de `auditar` en las dos empresas y cada uno se puede abrir."""
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
    for clave, errores in (("empresa_a", 0), ("empresa_b", 6)):
        base = f"/e/{clave}/2021/auditoria"
        html = cliente.get(f"{base}/tabla").text
        sesion = cliente.app.state.config.sesion(clave)
        esperados = auditar(sesion, sesion.scalar(select(Ejercicio)), almacen=cliente.app.state.config.almacen_de_adjuntos(), con_plazos=True)
        sesion.close()
        assert len(re.findall(r'data-id="', html)) == len(esperados), clave
        assert f"{errores} error(es)" in html, clave
        sin_catalogo = {h.codigo for h in esperados} - set(CATALOGO)
        assert not sin_catalogo, sin_catalogo
        ids = re.findall(r'data-id="([^"]+)"', html)
        for i in ids[:5] + ids[-2:]:
            assert cliente.get(f"{base}/f/{i}").status_code == 200, (clave, i)


def test_el_nombre_de_la_empresa_lleva_a_su_ficha_y_la_casita_a_las_opciones(cliente):
    html = cliente.get("/e/prueba/2026/auditoria").text
    assert 'href="/empresa/prueba" class="empresa"' in html and 'class="inicio boton plano"' in html and 'href="/e/prueba/2026"' in html
