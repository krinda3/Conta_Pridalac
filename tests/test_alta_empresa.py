"""Alta de una empresa: vacía con el plan del PGC, o desde una copia de MGD (servicio y pantalla)."""
import io
import os
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Parametro, TipoIva
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import alta_empresa as svc
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cuentas import crear_tercero
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal


@pytest.fixture
def config(tmp_path):
    return Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "justificantes", copias=tmp_path / "copias", descargas=tmp_path / "descargas")


def abrir(config, slug):
    return nueva_sesion(crear_motor(config.datos / f"{slug}.sqlite"))


def test_el_plan_basico_tiene_las_cuentas_del_pgc_con_los_digitos_pedidos():
    for n in (6, 7, 8, 10):
        plan = svc.plan_basico(n)
        assert all(len(c) == n for c in plan) and len(plan) > 300
        assert plan["572".ljust(n, "0")] and plan["4751".ljust(n, "0")] == "Hacienda Pública, acreedora por retenciones practicadas"


@pytest.mark.parametrize("digitos", [6, 7, 8, 9])
def test_una_empresa_nueva_nace_con_lo_que_necesita_el_programa(config, digitos):
    alta = svc.crear_empresa_nueva(config, nombre="Fundación Ñandú, ONG", nif="g-123.456.78", anio=2026, digitos=digitos)
    assert alta.slug == "fundacion-nandu-ong" and alta.anio == 2026 and alta.cuentas > 300
    s = abrir(config, alta.slug)
    e = s.scalars(select(Empresa)).one()
    assert (e.nombre, e.nif, e.digitos_cuenta) == ("Fundación Ñandú, ONG", "G12345678", digitos)
    assert set(s.scalars(select(func.length(Cuenta.codigo)))) == {digitos}
    ej = s.scalars(select(Ejercicio)).one()
    assert (ej.anio, ej.fecha_inicio, ej.fecha_fin, ej.cerrado) == (2026, date(2026, 1, 1), date(2026, 12, 31), False)
    parametros = {p.clave: p.valor for p in s.scalars(select(Parametro))}
    assert parametros == {"PYG": "129".ljust(digitos, "0"), "IVA_DEBE": "4700".ljust(digitos, "0"), "IVA_HABER": "4750".ljust(digitos, "0"), "PTE_APLIC": "555".ljust(digitos, "0")}
    assert all(s.scalar(select(Cuenta.id).where(Cuenta.codigo == v)) for v in parametros.values())  # las cuentas que nombran existen
    tipos = list(s.scalars(select(TipoIva).order_by(TipoIva.sentido, TipoIva.numero)))
    assert len(tipos) == 8 and [t.pct_iva for t in tipos[:4]] == [D("21"), D("10"), D("4"), D("0")]
    assert {t.cuenta_iva.codigo for t in tipos if t.sentido == "R"} == {"472".ljust(digitos, "0")} and {t.cuenta_iva.codigo for t in tipos if t.sentido == "E"} == {"477".ljust(digitos, "0")}
    assert sum(t.por_defecto for t in tipos) == 2


def test_se_puede_trabajar_en_una_empresa_recien_creada(config):
    alta = svc.crear_empresa_nueva(config, nombre="Recién Creada", nif="B12345678", anio=2026, digitos=7)
    s = abrir(config, alta.slug)
    ej = s.scalars(select(Ejercicio)).one()
    proveedor = crear_tercero(s, ej.empresa_id, "P", "Proveedor Uno")
    assert s.get(Cuenta, proveedor.cuenta_id).codigo == "4000001"
    grabar_asiento(s, ej, tipo=4, numero=1, sub=0, fecha=date(2026, 2, 1), concepto="compra", subtipo=None,
                   lineas=[LineaAsiento("6290000", D("100.00")), LineaAsiento("4720000", D("21.00")), LineaAsiento("5720000", D("-121.00"))])
    s.commit()
    s.close()
    cliente = TestClient(crear_app(config))
    assert alta.slug in cliente.get("/").text
    for nombre in sorted(crear_app(config).state.listados):
        for sufijo in ("", "/tabla"):
            r = cliente.get(f"/e/{alta.slug}/2026/{nombre}{sufijo}")
            assert r.status_code == 200 and "Traceback" not in r.text, (nombre, sufijo)
            assert not (sufijo and "aviso error" in r.text), (nombre, r.text[:300])


def test_las_altas_no_validas_se_rechazan_sin_dejar_nada(config):
    svc.crear_empresa_nueva(config, nombre="Una", nif=None, anio=2026)
    for kw in (dict(nombre="Una"), dict(nombre=" "), dict(nombre="Otra", anio=1800), dict(nombre="Otra", digitos=3), dict(nombre="Otra", digitos=40)):
        with pytest.raises(ErrorContable):
            svc.crear_empresa_nueva(config, **{"nif": None, "anio": 2026, "digitos": 8, **kw})
    assert [p.stem for p in config.datos.glob("*.sqlite")] == ["una"]


def test_si_el_alta_falla_a_medias_no_queda_un_fichero(config, monkeypatch):
    def rompe(*a, **k):
        raise RuntimeError("fallo de prueba")

    monkeypatch.setattr(svc, "plan_basico", rompe)
    with pytest.raises(RuntimeError):
        svc.crear_empresa_nueva(config, nombre="Rota", nif=None, anio=2026)
    assert list(config.datos.glob("*.sqlite")) == []


# ---------------------------------------------------------------- la pantalla


@pytest.fixture
def web(config):
    return TestClient(crear_app(config), follow_redirects=False)


def test_el_inicio_ofrece_añadir_empresa_y_la_pantalla_enseña_los_dos_caminos(web):
    assert "Añadir empresa" in web.get("/").text and "/empresa-nueva" in web.get("/").text
    pagina = web.get("/empresa-nueva").text
    assert "Empresa nueva" in pagina and "Desde una copia de Gestión MGD" in pagina and 'name="digitos"' in pagina and 'type="file"' in pagina


def test_crear_una_empresa_nueva_desde_la_pantalla(web, config):
    r = web.post("/empresa-nueva/vacia", data={"nombre": "ONG de Prueba", "nif": "G12345678", "anio": "2026", "digitos": "7"})
    assert r.status_code == 303 and r.headers["location"] == "/e/ong-de-prueba/2026"
    assert web.get("/e/ong-de-prueba/2026").status_code == 200
    repetida = web.post("/empresa-nueva/vacia", data={"nombre": "ONG de Prueba", "anio": "2026", "digitos": "7"})
    assert repetida.status_code == 200 and "Ya existe una empresa" in repetida.text and 'value="ONG de Prueba"' in repetida.text
    mala = web.post("/empresa-nueva/vacia", data={"nombre": "", "anio": "2026", "digitos": "7"})
    assert mala.status_code == 200 and "Falta el nombre" in mala.text


def test_con_certificado_obligatorio_se_lleva_a_la_ficha(config):
    config.exigir_certificado = True
    web = TestClient(crear_app(config), follow_redirects=False)
    r = web.post("/empresa-nueva/vacia", data={"nombre": "Con Certificado", "anio": "2026", "digitos": "8"})
    assert r.status_code == 303 and r.headers["location"] == "/empresa/con-certificado?sin_certificado=1"
    ficha = web.get(r.headers["location"])
    assert ficha.status_code == 200 and "protección de acceso" in ficha.text


@pytest.fixture(scope="module")
def zip_de_copia(tmp_path_factory, carpeta_mgd_2021):
    ruta = tmp_path_factory.mktemp("copia") / "copia mgd.zip"
    with zipfile.ZipFile(ruta, "w") as z:
        for f in carpeta_mgd_2021.iterdir():
            if f.is_file():
                z.write(f, f.name)
    return ruta


def test_importar_una_copia_de_mgd_desde_la_pantalla(web, config, zip_de_copia):
    with open(zip_de_copia, "rb") as f:
        vista = web.post("/empresa-nueva/mgd", files={"archivo": ("copia mgd.zip", f, "application/zip")})
    assert vista.status_code == 200 and "7 dígitos" in vista.text and "103 asientos" in vista.text and "copia mgd.zip" in vista.text
    token = vista.text.split('name="token" value="')[1].split('"')[0]
    assert list(config.datos.glob("*.sqlite")) == []  # examinar no crea nada
    r = web.post("/empresa-nueva/mgd/crear", data={"token": token, "nombre": "Amigo ONG", "nif": "G12345678", "anio": "2021"})
    assert r.status_code == 303 and r.headers["location"] == "/e/amigo-ong/2021"
    s = abrir(config, "amigo-ong")
    assert s.scalars(select(Empresa)).one().digitos_cuenta == 7
    assert web.get("/e/amigo-ong/2021/balance-oficial").status_code == 200
    # el token se gasta
    otra = web.post("/empresa-nueva/mgd/crear", data={"token": token, "nombre": "Otra", "anio": "2021"})
    assert otra.status_code == 200 and "ya no está disponible" in otra.text


def test_cancelar_la_importacion_borra_la_copia_subida(web, config, zip_de_copia):
    with open(zip_de_copia, "rb") as f:
        vista = web.post("/empresa-nueva/mgd", files={"archivo": ("copia.zip", f, "application/zip")})
    token = vista.text.split('name="token" value="')[1].split('"')[0]
    guardada = web.app.state.altas_pendientes[token]["zip"]
    assert os.path.exists(guardada)
    r = web.post("/empresa-nueva/mgd/cancelar", data={"token": token})
    assert r.status_code == 303 and not os.path.exists(guardada) and token not in web.app.state.altas_pendientes


def test_un_fichero_que_no_es_una_copia_se_rechaza(web, config):
    r = web.post("/empresa-nueva/mgd", files={"archivo": ("notas.zip", b"esto no es un zip", "application/zip")})
    assert r.status_code == 200 and "No se puede usar" in r.text
    assert not config.datos.exists() or list(config.datos.glob("*.sqlite")) == []
    vacio = io.BytesIO()
    with zipfile.ZipFile(vacio, "w") as z:
        z.writestr("hola.txt", "no es MGD")
    r2 = web.post("/empresa-nueva/mgd", files={"archivo": ("otro.zip", vacio.getvalue(), "application/zip")})
    assert r2.status_code == 200 and "No parece una copia de MGD" in r2.text


# ---------------------------------------------------------------- plan de entidades sin fines lucrativos (ONG)

ESTADOS_DE_PYMES = ("estado-cambios-pn",)  # el único modelo de PYMES que una ONG no tiene aparte


def test_el_plan_de_una_ong_tiene_sus_propias_cuentas():
    plan = svc.plan_basico(8, "esfl")
    assert all(len(c) == 8 for c in plan) and len(plan) > 340
    assert plan["10000000"] == "Dotación fundacional" and plan["72000000"] == "Cuotas de asociados y afiliados" and plan["12900000"] == "Excedente del ejercicio"
    assert "10200000" not in plan and "11200000" not in plan  # el capital y la reserva legal son de las sociedades
    assert plan["47510000"] == "Hacienda Pública, acreedora por retenciones practicadas" and plan["47300000"]
    assert plan != svc.plan_basico(8, "pymes")


def test_los_nombres_del_plan_dependen_del_tipo():
    from conta_pridalac.domain.pgc import nombre_pgc

    assert nombre_pgc("129") == "Resultado del ejercicio" and nombre_pgc("129", "esfl") == "Excedente del ejercicio"
    assert nombre_pgc("1", "esfl") == "Financiación básica" and nombre_pgc("72", "esfl") and nombre_pgc("1030", "esfl") == "Fundadores por desembolsos no exigidos"
    assert nombre_pgc("1030") == ""  # el plan de PYMES sólo tiene nombres hasta tres dígitos
    assert nombre_pgc("369", "esfl") == "Materiales recuperados B" and nombre_pgc("446", "esfl") == "Deudores de dudoso cobro"  # erratas del Excel corregidas con el BOE


def test_un_tipo_de_plan_desconocido_se_rechaza(config):
    with pytest.raises(ErrorContable, match="tipo de plan"):
        svc.crear_empresa_nueva(config, nombre="X", nif=None, anio=2026, tipo_plan="otro")
    assert not list(config.datos.glob("*.sqlite"))


@pytest.mark.parametrize("digitos", [7, 8])
def test_una_ong_nace_con_su_plan_y_funciona(config, digitos):
    alta = svc.crear_empresa_nueva(config, nombre="Asociación Amiga", nif="G12345678", anio=2026, digitos=digitos, tipo_plan="esfl")
    s = abrir(config, alta.slug)
    e = s.scalars(select(Empresa)).one()
    assert (e.tipo_plan, e.digitos_cuenta) == ("esfl", digitos)
    assert s.scalar(select(Cuenta.nombre).where(Cuenta.codigo == "100".ljust(digitos, "0"))) == "Dotación fundacional"
    parametros = {p.clave: p.valor for p in s.scalars(select(Parametro))}
    assert all(s.scalar(select(Cuenta.id).where(Cuenta.codigo == v)) for v in parametros.values())
    assert len(list(s.scalars(select(TipoIva)))) == 8 and all(t.cuenta_iva_id for t in s.scalars(select(TipoIva)))
    ej = s.scalars(select(Ejercicio)).one()
    crear_tercero(s, ej.empresa_id, "P", "Proveedor Uno")
    grabar_asiento(s, ej, tipo=4, numero=1, sub=0, fecha=date(2026, 2, 1), concepto="cuota", subtipo=None,
                   lineas=[LineaAsiento("5720000".ljust(digitos, "0"), D("50.00")), LineaAsiento("7200000".ljust(digitos, "0"), D("-50.00"))])
    s.commit()
    s.close()
    web = TestClient(crear_app(config))
    for nombre in sorted(crear_app(config).state.listados):
        for sufijo in ("", "/tabla"):
            r = web.get(f"/e/{alta.slug}/2026/{nombre}{sufijo}")
            assert r.status_code == 200 and "Traceback" not in r.text, (nombre, sufijo)
            if sufijo and nombre not in ESTADOS_DE_PYMES:
                assert "aviso error" not in r.text, (nombre, r.text[:300])
    for nombre in ESTADOS_DE_PYMES:  # el estado de cambios del PGC de PYMES no vale para una ONG: avisa en lugar de dar números equivocados
        r = web.get(f"/e/{alta.slug}/2026/{nombre}/tabla")
        assert "no corresponde al plan de cuentas de esta empresa" in r.text and "entidad sin fines lucrativos" in r.text
    balance = web.get(f"/e/{alta.slug}/2026/balance-oficial/tabla").text  # el balance y la cuenta de resultados sí son los de las entidades sin fines lucrativos
    assert "Dotación fundacional/Fondo social" in balance and "Usuarios y otros deudores de la actividad propia" in balance and "Capital escriturado" not in balance
    resultados = web.get(f"/e/{alta.slug}/2026/pyg-oficial/tabla").text
    assert "Ingresos de la actividad propia" in resultados and "Cuotas de asociados y afiliados" in resultados and "Gastos por ayudas y otros" in resultados
    sumas = web.get(f"/e/{alta.slug}/2026/balance/tabla", params={"nivel": "3"}).text
    assert "Cuotas de asociados y afiliados" in sumas  # el balance de sumas y saldos agrupa con los nombres del plan de la ONG


def test_el_alta_de_una_ong_desde_la_pantalla(web):
    pagina = web.get("/empresa-nueva").text
    assert 'name="tipo_plan"' in pagina and "Entidad sin fines lucrativos" in pagina
    r = web.post("/empresa-nueva/vacia", data={"nombre": "Fundación Ejemplo", "nif": "G12345678", "anio": "2026", "digitos": "8", "tipo_plan": "esfl"})
    assert r.status_code == 303
    malo = web.post("/empresa-nueva/vacia", data={"nombre": "Otra", "anio": "2026", "digitos": "8", "tipo_plan": "inventado"})
    assert malo.status_code == 200 and "tipo de plan" in malo.text


def test_importar_mgd_como_entidad_sin_fines_lucrativos(web, config, zip_de_copia):
    with open(zip_de_copia, "rb") as f:
        vista = web.post("/empresa-nueva/mgd", files={"archivo": ("copia.zip", f, "application/zip")})
    assert 'name="tipo_plan"' in vista.text
    token = vista.text.split('name="token" value="')[1].split('"')[0]
    r = web.post("/empresa-nueva/mgd/crear", data={"token": token, "nombre": "ONG desde MGD", "nif": "G12345678", "anio": "2021", "tipo_plan": "esfl"})
    assert r.status_code == 303
    s = abrir(config, "ong-desde-mgd")
    assert s.scalars(select(Empresa)).one().tipo_plan == "esfl"
    assert "Dotación fundacional/Fondo social" in web.get("/e/ong-desde-mgd/2021/balance-oficial/tabla").text
    assert "no corresponde al plan de cuentas" in web.get("/e/ong-desde-mgd/2021/estado-cambios-pn/tabla").text


def test_una_base_anterior_gana_el_tipo_de_plan_pymes(tmp_path):
    from sqlalchemy import text

    from conta_pridalac.db.sesion import actualizar_esquema, crear_esquema

    motor = crear_motor(tmp_path / "vieja.sqlite")
    crear_esquema(motor)
    with motor.begin() as c:
        c.execute(text("INSERT INTO empresa (id, codigo, nombre) VALUES (1, 1, 'Antigua')"))
        c.execute(text("ALTER TABLE empresa DROP COLUMN tipo_plan"))
    assert "empresa.tipo_plan" in actualizar_esquema(motor)
    assert nueva_sesion(motor).get(Empresa, 1).tipo_plan == "pymes"


# ---------------------------------------------------------------- balance y cuenta de resultados de una entidad sin fines lucrativos


def _ong_con_movimientos(config):
    """Una ONG con: fondo social 10.000, cuotas 5.000, subvención a la actividad 3.000, ayudas 1.200, personal 2.000, compra de mobiliario 1.000,
    gasto a un proveedor 300 y una subvención de capital de 1.000 de la que se traspasan 100 al excedente."""
    alta = svc.crear_empresa_nueva(config, nombre="ONG de Cuentas", nif="G12345678", anio=2026, digitos=8, tipo_plan="esfl")
    s = abrir(config, alta.slug)
    ej = s.scalars(select(Ejercicio)).one()
    banco, proveedor = "57200000", "40000001"
    s.add(Cuenta(empresa_id=ej.empresa_id, codigo=proveedor, nombre="PROVEEDOR UNO"))
    s.flush()
    movimientos = [
        ([(banco, "10000"), ("10000000", "-10000")]),
        ([(banco, "5000"), ("72000000", "-5000")]),
        ([(banco, "3000"), ("74000000", "-3000")]),
        ([("65000000", "1200"), (banco, "-1200")]),
        ([("64000000", "2000"), (banco, "-2000")]),
        ([("21600000", "1000"), (banco, "-1000")]),
        ([("62900000", "300"), (proveedor, "-300")]),
        ([(banco, "1000"), ("13000000", "-1000")]),
        ([("13000000", "100"), ("74500000", "-100")]),
    ]
    for n, lineas in enumerate(movimientos, start=1):
        grabar_asiento(s, ej, tipo=4, numero=n, sub=0, fecha=date(2026, 3, n), concepto="prueba", subtipo=None, lineas=[LineaAsiento(c, D(i)) for c, i in lineas])
    s.commit()
    return s, ej


def test_el_balance_de_una_ong_cuadra_y_usa_las_lineas_del_boe(config):
    from conta_pridalac.servicios.cuentas_anuales_esfl import balance_esfl

    s, ej = _ong_con_movimientos(config)
    b = balance_esfl(s, ej)
    assert b.sin_asignar == [] and b.avisos == []
    esperado = {"A.III": "1000", "B.VII": "14800", "A": "1000", "B": "14800", "TA": "15800", "PN.1.I.1": "10000", "PN.1.IV": "4600", "PN.1": "14600", "PN.2": "900", "PN": "15500", "PC.V.1": "300", "PC": "300", "TP": "15800"}
    assert {k: b.importe(k) for k in esperado} == {k: D(v) for k, v in esperado.items()}  # el excedente 4.600 es el de los grupos 6 y 7 aún sin regularizar


def test_la_cuenta_de_resultados_de_una_ong_y_sus_variaciones_del_patrimonio_neto(config):
    from conta_pridalac.servicios.cuentas_anuales_esfl import cuenta_resultados_esfl

    s, ej = _ong_con_movimientos(config)
    r = cuenta_resultados_esfl(s, ej)
    assert r.sin_asignar == []
    esperado = {
        "1a": "5000", "1d": "3000", "1": "8000", "3a": "-1200", "3": "-1200", "8": "-2000", "9": "-300", "11": "100", "A1": "4600", "A2": "0", "A3": "4600", "A4": "4600",
        "B1": "1000", "BT": "1000", "C1": "-100", "CT": "-100", "D": "900", "G": "10000", "H": "0", "I": "15500",
    }
    assert {k: r.importe(k) for k in esperado} == {k: D(v) for k, v in esperado.items()}
    assert any("secciones B a H" in a for a in r.avisos) and any("No hay ejercicio 2025" in a for a in r.avisos)
    sin_valor = {l.id for l in r.lineas if l.importe is None}
    assert {"A", "B", "C", "E", "F"} <= sin_valor and "A1" not in sin_valor  # las cabeceras y los ajustes que no se calculan salen en blanco


def test_las_variaciones_del_patrimonio_neto_parten_del_balance_del_año_anterior(config):
    from conta_pridalac.servicios.cuentas_anuales_esfl import cuenta_resultados_esfl

    alta = svc.crear_empresa_nueva(config, nombre="ONG Dos Años", nif=None, anio=2026, digitos=8, tipo_plan="esfl")
    s = abrir(config, alta.slug)
    nuevo = s.scalars(select(Ejercicio)).one()
    anterior = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa_id=nuevo.empresa_id)
    s.add(anterior)
    s.flush()
    grabar_asiento(s, anterior, tipo=4, numero=1, sub=0, fecha=date(2025, 5, 1), concepto="fondo social", subtipo=None, lineas=[LineaAsiento("57200000", D("10000")), LineaAsiento("10000000", D("-10000"))])
    grabar_asiento(s, nuevo, tipo=4, numero=1, sub=0, fecha=date(2026, 1, 1), concepto="apertura", subtipo=None, lineas=[LineaAsiento("57200000", D("10000")), LineaAsiento("10000000", D("-10000"))])
    grabar_asiento(s, nuevo, tipo=4, numero=2, sub=0, fecha=date(2026, 2, 1), concepto="cuotas", subtipo=None, lineas=[LineaAsiento("57200000", D("5000")), LineaAsiento("72000000", D("-5000"))])
    s.commit()
    r = cuenta_resultados_esfl(s, nuevo)
    assert not any("No hay ejercicio" in a for a in r.avisos)
    assert (r.importe("A4"), r.importe("G"), r.importe("H"), r.importe("I")) == (D("5000"), D("0"), D("0"), D("5000"))  # la dotación no varía y todo el cambio del patrimonio es el excedente


def test_al_crear_la_empresa_se_elige_si_se_protege_con_certificado(config):
    web = TestClient(crear_app(config), follow_redirects=False)
    pantalla = web.get("/empresa-nueva").text
    assert 'name="proteccion"' in pantalla and "Sin protección" in pantalla and "Con certificado digital" in pantalla
    config.exigir_certificado = True
    assert 'value="certificado" checked' in web.get("/empresa-nueva").text                          # con la exigencia general, el valor propuesto es el certificado
    libre = web.post("/empresa-nueva/vacia", data={"nombre": "Sin Proteger", "anio": "2026", "digitos": "8", "proteccion": "ninguna"})
    assert libre.status_code == 303 and libre.headers["location"] == "/e/sin-proteger/2026"       # no hace falta pasar por la ficha
    assert web.get("/e/sin-proteger/2026").status_code == 200
    con = web.post("/empresa-nueva/vacia", data={"nombre": "Con Cert", "anio": "2026", "digitos": "8", "proteccion": "certificado"})
    assert con.status_code == 303 and con.headers["location"] == "/empresa/con-cert?sin_certificado=1"
    assert web.get("/e/con-cert/2026").status_code == 303                                         # y hasta que no se indique el certificado, sólo la ficha
    mala = web.post("/empresa-nueva/vacia", data={"nombre": "Rara", "anio": "2026", "digitos": "8", "proteccion": "magica"})
    assert mala.status_code == 200 and "no es válida" in mala.text
