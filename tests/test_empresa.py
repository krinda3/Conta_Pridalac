"""Ficha de la empresa y acceso con la contraseña de su certificado digital (los certificados de prueba se generan aquí, no hay ninguno real)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import empresa as svc
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion


def _pfx(ruta, contrasena="clave", dias=365, atributos=None):
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name(atributos or [x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA DE PRUEBA SL"), x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-B12345678")])
    ahora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ahora - timedelta(days=30)).not_valid_after(ahora + timedelta(days=dias)).sign(clave, hashes.SHA256()))
    ruta.write_bytes(pkcs12.serialize_key_and_certificates(b"prueba", clave, cert, None, serialization.BestAvailableEncryption(contrasena.encode())))
    return ruta


@pytest.fixture
def pfx(tmp_path):
    return _pfx(tmp_path / "prueba.pfx")


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)])
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})), follow_redirects=False)


def _empresa(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return s.scalars(select(Empresa)).first(), s
    except Exception:
        s.close()
        raise


# ---------------------------------------------------------------------------- servicio


def test_el_certificado_se_abre_con_su_contrasena(pfx):
    info = svc.leer_certificado(pfx, "clave")
    assert info.titular == "EMPRESA DE PRUEBA SL" and info.nif == "B12345678" and not info.caducado and info.caduca > date.today()
    with pytest.raises(ErrorContable, match="contraseña"):
        svc.leer_certificado(pfx, "otra")
    with pytest.raises(ErrorContable, match="No se encuentra"):
        svc.leer_certificado(pfx.parent / "no-existe.pfx", "clave")


def test_un_certificado_caducado_se_detecta(tmp_path):
    assert svc.leer_certificado(_pfx(tmp_path / "viejo.pfx", dias=-2), "clave").caducado


def test_la_ficha_se_valida_y_se_guarda(cliente):
    empresa, s = _empresa(cliente)
    svc.modificar_empresa(s, empresa, " Empresa A SL ", nif="b-12.345.678", domicilio="C/ Mayor 1", codigo_postal="04001", email="a@b.es", cnae="0125",
                          representante_nif="12345678z", fecha_constitucion=date(2001, 3, 4))
    assert (empresa.nombre, empresa.nif, empresa.representante_nif, empresa.fecha_constitucion) == ("Empresa A SL", "B12345678", "12345678Z", date(2001, 3, 4))
    for mal, texto in (({"email": "sin-arroba"}, "correo"), ({"cnae": "ab"}, "CNAE"), ({"codigo_postal": "ABC"}, "postal"), ({"inventado": "x"}, "desconocidos")):
        with pytest.raises(ErrorContable, match=texto):
            svc.modificar_empresa(s, empresa, "X", **mal)
    with pytest.raises(ErrorContable, match="obligatoria"):
        svc.modificar_empresa(s, empresa, "  ")
    s.close()


# ---------------------------------------------------------------------------- web


def test_la_ficha_se_edita_desde_la_pantalla(cliente):
    assert "Ficha de la empresa" in cliente.get("/").text
    r = cliente.get("/empresa/prueba")
    assert r.status_code == 200 and 'name="nombre"' in r.text and 'name="registro_tomo"' in r.text and "Empresa de Prueba" in r.text
    datos = {"nombre": "Empresa Nueva SL", "nif": "b99999999", "fecha_constitucion": "040301", "domicilio": "C/ Mayor 1", "poblacion": "Almería", "email": "info@x.es", "registro_tomo": "12"}
    r = cliente.post("/empresa/prueba", data=datos)
    assert r.status_code == 303 and r.headers["location"].endswith("guardada=1")
    empresa, s = _empresa(cliente)
    assert (empresa.nombre, empresa.nif, empresa.poblacion, empresa.registro_tomo, empresa.fecha_constitucion) == ("Empresa Nueva SL", "B99999999", "Almería", "12", date(2001, 3, 4))
    s.close()
    assert "Ficha guardada" in cliente.get("/empresa/prueba?guardada=1").text
    malo = cliente.post("/empresa/prueba", data={**datos, "email": "mal"})
    assert malo.status_code == 200 and "correo" in malo.text
    assert "Fecha de constitución" in cliente.post("/empresa/prueba", data={**datos, "fecha_constitucion": "99999"}).text


def test_sin_certificado_la_empresa_se_abre_sin_contrasena(cliente):
    assert cliente.get("/e/prueba/2026").status_code == 200


def test_con_certificado_hay_que_dar_la_contrasena(cliente, pfx):
    # asociar el certificado exige acertar la contraseña; quien lo asocia queda dentro
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "certificado_ruta": str(pfx), "certificado_contrasena": "mala"})
    assert r.status_code == 200 and "contraseña" in r.text
    assert cliente.get("/e/prueba/2026").status_code == 200  # no se asoció nada
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    assert r.status_code == 303
    assert cliente.get("/e/prueba/2026").status_code == 200
    assert "EMPRESA DE PRUEBA SL" in cliente.get("/empresa/prueba").text and "🔒" in cliente.get("/").text
    # otro navegador (sin cookie) no entra
    otro = TestClient(cliente.app, follow_redirects=False)
    r = otro.get("/e/prueba/2026/facturas-recibidas")
    assert r.status_code == 303 and r.headers["location"].startswith("/empresa/prueba/entrar?volver=")
    assert otro.get("/empresa/prueba").status_code == 303
    # y con HTMX recibe una redirección que el navegador sigue
    h = otro.get("/e/prueba/2026/facturas-recibidas/tabla", headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/e/prueba/2026/facturas-recibidas"})
    assert h.status_code == 401 and h.headers["HX-Redirect"].startswith("/empresa/prueba/entrar")
    # contraseña mala y buena
    assert "contraseña" in otro.post("/empresa/prueba/entrar", data={"contrasena": "mala", "volver": "/e/prueba/2026"}).text
    assert otro.get("/e/prueba/2026").status_code == 303
    r = otro.post("/empresa/prueba/entrar", data={"contrasena": "clave", "volver": "/e/prueba/2026"})
    assert r.status_code == 303 and r.headers["location"] == "/e/prueba/2026"
    assert otro.get("/e/prueba/2026").status_code == 200
    # la contraseña no se guarda en la base de datos
    empresa, s = _empresa(cliente)
    assert empresa.certificado_ruta == str(pfx.resolve()) and "clave" not in repr([getattr(empresa, c.name) for c in Empresa.__table__.columns])
    s.close()
    # cerrar la empresa la vuelve a bloquear
    assert otro.post("/empresa/prueba/salir").status_code == 303
    assert otro.get("/e/prueba/2026").status_code == 303


def test_si_se_exige_certificado_sin_el_solo_se_abre_la_ficha(cliente, pfx):
    cliente.app.state.config.exigir_certificado = True
    r = cliente.get("/e/prueba/2026/facturas-recibidas")
    assert r.status_code == 303 and r.headers["location"] == "/empresa/prueba?sin_certificado=1"
    h = cliente.get("/e/prueba/2026/facturas-recibidas/tabla", headers={"HX-Request": "true"})
    assert h.status_code == 401 and h.headers["HX-Redirect"] == "/empresa/prueba?sin_certificado=1"
    ficha = cliente.get("/empresa/prueba?sin_certificado=1")
    assert ficha.status_code == 200 and "protección de acceso" in ficha.text
    # con el certificado validado ya se entra (quien lo asocia queda dentro)
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    assert r.status_code == 303
    assert cliente.get("/e/prueba/2026/facturas-recibidas").status_code == 200


def test_el_destino_de_vuelta_no_puede_salir_de_la_aplicacion(cliente, pfx):
    cliente.post("/empresa/prueba", data={"nombre": "X", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    otro = TestClient(cliente.app, follow_redirects=False)
    for malo in ("https://evil.example/", "//evil.example/", "/otra"):
        r = otro.post("/empresa/prueba/entrar", data={"contrasena": "clave", "volver": malo})
        assert r.headers["location"] == "/"


def test_quitar_el_certificado_elimina_la_contrasena(cliente, pfx):
    cliente.post("/empresa/prueba", data={"nombre": "X", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    assert cliente.post("/empresa/prueba", data={"nombre": "X", "certificado_ruta": ""}).status_code == 303
    otro = TestClient(cliente.app, follow_redirects=False)
    assert otro.get("/e/prueba/2026").status_code == 200


def test_las_bases_antiguas_ganan_las_columnas_de_la_ficha(tmp_path):
    from sqlalchemy import text

    from conta_pridalac.db.sesion import actualizar_esquema

    motor = create_engine(f"sqlite:///{tmp_path / 'vieja.sqlite'}")
    with motor.begin() as c:
        c.execute(text("CREATE TABLE empresa (id INTEGER PRIMARY KEY, codigo INTEGER, nombre VARCHAR(128), nif VARCHAR(20))"))
        c.execute(text("INSERT INTO empresa VALUES (1, 11, 'Vieja', 'B1')"))
    anadidas = actualizar_esquema(motor)
    assert "empresa.certificado_ruta" in anadidas and "empresa.registro_tomo" in anadidas and "empresa.fecha_constitucion" in anadidas


# ---------------------------------------------------------------------------- datos que trae el certificado


def _representante(ruta):
    """Un certificado de representante de persona jurídica, con los atributos habituales de la FNMT."""
    return _pfx(ruta, atributos=[
        x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EMPRESA A SL"),
        x509.NameAttribute(x509.ObjectIdentifier("2.5.4.97"), "VATES-B04123456"), x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-12345678Z"),
        x509.NameAttribute(NameOID.SURNAME, "GARCIA LOPEZ"), x509.NameAttribute(NameOID.GIVEN_NAME, "JAVIER"),
        x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA A SL - CIF B04123456 - JAVIER GARCIA - NIF 12345678Z")])


def test_se_deducen_los_datos_de_la_ficha_del_certificado(tmp_path, pfx):
    info = svc.leer_certificado(_representante(tmp_path / "rep.pfx"), "clave")
    assert (info.razon_social, info.nif_empresa, info.representante_nombre, info.representante_nif) == ("EMPRESA A SL", "B04123456", "JAVIER GARCIA LOPEZ", "12345678Z")
    propio = svc.leer_certificado(pfx, "clave")  # el de la propia sociedad: el nombre común es la razón social
    assert (propio.razon_social, propio.nif_empresa, propio.representante_nif) == ("EMPRESA DE PRUEBA SL", "B12345678", None)
    fisica = svc.leer_certificado(_pfx(tmp_path / "fisica.pfx", atributos=[x509.NameAttribute(NameOID.COMMON_NAME, "JUAN PEREZ"), x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-12345678Z")]), "clave")
    assert (fisica.nif_empresa, fisica.representante_nif) == (None, "12345678Z")


def test_completar_no_pisa_lo_ya_escrito(cliente, tmp_path):
    empresa, s = _empresa(cliente)
    info = svc.leer_certificado(_representante(tmp_path / "rep.pfx"), "clave")
    empresa.nif = None
    assert svc.completar_desde_certificado(empresa, info) == ["nif", "representante_nombre", "representante_nif"]
    assert empresa.nombre == "Empresa de Prueba" and empresa.nif == "B04123456"
    s.close()


def test_al_asociar_el_certificado_la_ficha_se_rellena_sola(cliente, tmp_path):
    ruta = _representante(tmp_path / "rep.pfx")
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "nif": "", "certificado_ruta": str(ruta), "certificado_contrasena": "clave"})
    assert r.status_code == 303
    empresa, s = _empresa(cliente)
    assert (empresa.nif, empresa.representante_nombre, empresa.representante_nif) == ("B04123456", "JAVIER GARCIA LOPEZ", "12345678Z")
    s.close()


def test_leer_los_datos_del_certificado_desde_la_ficha(cliente, tmp_path):
    ruta = _representante(tmp_path / "rep.pfx")
    r = cliente.post("/empresa/prueba/certificado", data={"ruta": str(ruta), "contrasena": "clave"}).json()
    assert r["nombre"] == "EMPRESA A SL" and r["nif"] == "B04123456" and r["representante_nif"] == "12345678Z" and r["caducado"] is False
    assert "contraseña" in cliente.post("/empresa/prueba/certificado", data={"ruta": str(ruta), "contrasena": "mala"}).json()["error"]
    assert "No se encuentra" in cliente.post("/empresa/prueba/certificado", data={"ruta": str(tmp_path / "no.pfx"), "contrasena": "x"}).json()["error"]


def test_examinar_devuelve_la_ruta_elegida(cliente, monkeypatch):
    from conta_pridalac.web import empresa as web_empresa

    monkeypatch.setattr(web_empresa, "elegir_fichero", lambda: "C:/certificados/empresa_a.pfx")
    assert cliente.post("/empresa/prueba/examinar").json() == {"ruta": "C:/certificados/empresa_a.pfx"}

    def falla():
        raise ErrorContable("sin selector")

    monkeypatch.setattr(web_empresa, "elegir_fichero", falla)
    assert cliente.post("/empresa/prueba/examinar").json() == {"error": "sin selector"}
    assert 'id="examinar"' in cliente.get("/empresa/prueba").text and 'id="leer-certificado"' in cliente.get("/empresa/prueba").text


# ------------------------------------------------------------------------------------------------ protección de acceso (certificado opcional)

def test_la_ficha_ofrece_la_proteccion_de_acceso_y_la_empresa_sin_certificado_se_abre(cliente):
    ficha = cliente.get("/empresa/prueba").text
    assert 'name="proteccion"' in ficha and 'value="ninguna" checked' in ficha and "Sin protección" in ficha and "barrera de pantalla" in ficha


def test_una_empresa_anterior_sin_certificado_bloqueada_se_desbloquea_eligiendo_sin_proteccion(cliente):
    """El caso de quien creó una empresa con la exigencia de certificado y no lo tiene: antes no podía trabajar."""
    cliente.app.state.config.exigir_certificado = True
    assert cliente.get("/e/prueba/2026/facturas-recibidas").status_code == 303                    # bloqueada: sólo la ficha
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "proteccion": "ninguna"})
    assert r.status_code == 303 and cliente.get("/e/prueba/2026/facturas-recibidas").status_code == 200
    empresa, s = _empresa(cliente)
    assert empresa.proteccion == "ninguna" and empresa.certificado_ruta is None
    s.close()


def test_proteger_con_certificado_sin_indicarlo_no_deja_trabajar_hasta_configurarlo(cliente, pfx):
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "proteccion": "certificado"})
    assert r.status_code == 200 and "indique su ruta" in r.text                                    # error: falta el certificado
    empresa, s = _empresa(cliente)
    assert empresa.proteccion is None                                                               # no se cambió nada
    s.close()
    ok = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "proteccion": "certificado", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    assert ok.status_code == 303
    otro = TestClient(cliente.app, follow_redirects=False)
    assert otro.get("/e/prueba/2026").status_code == 303                                           # ahora pide la contraseña
    empresa, s = _empresa(cliente)
    assert empresa.proteccion == "certificado" and empresa.certificado_ruta == str(pfx.resolve())
    s.close()


def test_pasar_de_certificado_a_sin_proteccion_quita_la_contrasena(cliente, pfx):
    cliente.post("/empresa/prueba", data={"nombre": "X", "proteccion": "certificado", "certificado_ruta": str(pfx), "certificado_contrasena": "clave"})
    otro = TestClient(cliente.app, follow_redirects=False)
    assert otro.get("/e/prueba/2026").status_code == 303
    assert cliente.post("/empresa/prueba", data={"nombre": "X", "proteccion": "ninguna", "certificado_ruta": str(pfx)}).status_code == 303   # quien está dentro puede quitarla
    assert otro.get("/e/prueba/2026").status_code == 200
    empresa, s = _empresa(cliente)
    assert empresa.proteccion == "ninguna" and empresa.certificado_ruta is None
    s.close()


def test_con_proteccion_ninguna_la_exigencia_general_no_bloquea(cliente):
    cliente.post("/empresa/prueba", data={"nombre": "X", "proteccion": "ninguna"})
    cliente.app.state.config.exigir_certificado = True
    assert cliente.get("/e/prueba/2026/facturas-recibidas").status_code == 200


def test_una_proteccion_que_no_existe_se_rechaza(cliente):
    r = cliente.post("/empresa/prueba", data={"nombre": "X", "proteccion": "magica"})
    assert r.status_code == 200 and "no es válida" in r.text
