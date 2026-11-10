"""Copias de seguridad en la web: hacer, ver, descargar, verificar, restaurar y borrar."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

BASE = "/e/prueba/2026/copias"


@pytest.fixture
def cliente(tmp_path):
    bd = tmp_path / "bd"
    bd.mkdir()
    motor = crear_motor(bd / "prueba.sqlite")
    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)])
    s.flush()
    s.add(Cuenta(empresa_id=e.id, codigo="62900000", nombre="SERVICIOS"))
    s.commit()
    s.close()
    motor.dispose()
    (tmp_path / "almacen" / "001" / "2026").mkdir(parents=True)
    (tmp_path / "almacen" / "001" / "2026" / "f.pdf").write_bytes(b"%PDF-1.4 prueba")
    return TestClient(crear_app(Configuracion(datos=bd, almacen=tmp_path / "almacen", copias=tmp_path / "copias")))


def _cuentas(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return s.scalar(select(func.count()).select_from(Cuenta))
    finally:
        s.close()


def _añadir_cuenta(cliente, codigo):
    s = cliente.app.state.config.sesion("prueba")
    s.add(Cuenta(empresa_id=s.scalar(select(Empresa.id)), codigo=codigo, nombre="MÁS"))
    s.commit()
    s.close()


def _mensaje(r):
    return json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]


def _hacer(cliente):
    r = cliente.post(f"{BASE}/accion/hacer")
    assert "Copia ligera hecha y verificada" in _mensaje(r), r.text[:300]
    return sorted(cliente.app.state.config.copias.glob("copia_prueba_*.zip"))[-1]


def test_la_pantalla_vacia_ofrece_hacer_una_copia(cliente):
    assert "Copias de seguridad" in cliente.get("/e/prueba/2026").text and cliente.get(BASE).status_code == 200
    assert "No hay copias de seguridad" in cliente.get(f"{BASE}/tabla").text
    dialogo = cliente.get(f"{BASE}/accion/hacer").text
    assert "Hacer la copia" in dialogo and "no protege de un fallo del disco" in dialogo


def test_hacer_la_copia_la_lista_y_la_detalla_y_se_descarga(cliente):
    ruta = _hacer(cliente)
    tabla = cliente.get(f"{BASE}/tabla").text
    assert ruta.name in tabla and "1 fila" in tabla and ">Ligera<" in tabla
    detalle = cliente.get(f"{BASE}/f/{ruta.name}").text
    assert "Correcta: huellas, integridad de la base y recuento de registros" in detalle and "Empresa de Prueba (B12345678)" in detalle and "cuenta" in detalle
    d = cliente.get(f"{BASE}/{ruta.name}/descargar")
    assert d.status_code == 200 and d.content == ruta.read_bytes() and d.headers["content-type"] == "application/zip"
    assert cliente.get(f"{BASE}/copia_prueba_inexistente.zip/descargar").status_code == 404
    assert cliente.get(f"{BASE}/..%2F..%2Fbd%2Fprueba.sqlite/descargar").status_code == 404


def test_verificar_dice_si_esta_bien_o_que_falla(cliente):
    ruta = _hacer(cliente)
    r = cliente.post(f"{BASE}/accion/verificar", data={"copia": ruta.name})
    assert "está en buen estado" in r.text
    contenido = bytearray(ruta.read_bytes())
    contenido[len(contenido) // 2] ^= 0xFF  # un byte dañado en medio del fichero
    ruta.write_bytes(bytes(contenido))
    r = cliente.post(f"{BASE}/accion/verificar", data={"copia": ruta.name})
    assert "tiene problemas" in r.text and "en buen estado" not in r.text
    assert "CON PROBLEMAS" in cliente.get(f"{BASE}/f/{ruta.name}").text
    assert "no existe" in cliente.post(f"{BASE}/accion/verificar", data={"copia": "copia_prueba_xx.zip"}).text


def test_restaurar_pide_confirmacion_y_devuelve_el_estado_de_la_copia(cliente):
    ruta = _hacer(cliente)
    _añadir_cuenta(cliente, "62900001")
    (cliente.app.state.config.almacen / "001" / "2026" / "f.pdf").write_bytes(b"%PDF-1.4 cambiado")
    assert _cuentas(cliente) == 2
    r = cliente.post(f"{BASE}/accion/restaurar", data={"copia": ruta.name, "confirmacion": "si"})
    assert "escriba RESTAURAR" in r.text and _cuentas(cliente) == 2  # sin la palabra no se toca nada
    r = cliente.post(f"{BASE}/accion/restaurar", data={"copia": ruta.name, "confirmacion": "RESTAURAR"})
    assert "Copia restaurada" in r.text and "antes_de_restaurar" in r.text and "refrescar" in r.text  # el resultado se queda a la vista en el diálogo
    assert _cuentas(cliente) == 1  # la aplicación sigue funcionando con la base restaurada
    assert (cliente.app.state.config.almacen / "001" / "2026" / "f.pdf").read_bytes() == b"%PDF-1.4 prueba"
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Antes de restaurar" in tabla and "2 filas" in tabla
    previa = next(p for p in cliente.app.state.config.copias.glob("*antes_de_restaurar*.zip"))
    cliente.post(f"{BASE}/accion/restaurar", data={"copia": previa.name, "confirmacion": "RESTAURAR"})  # y se deshace
    assert _cuentas(cliente) == 2


def test_no_se_restaura_una_copia_dañada(cliente):
    ruta = _hacer(cliente)
    contenido = bytearray(ruta.read_bytes())
    contenido[len(contenido) // 2] ^= 0xFF
    ruta.write_bytes(bytes(contenido))
    _añadir_cuenta(cliente, "62900001")
    r = cliente.post(f"{BASE}/accion/restaurar", data={"copia": ruta.name, "confirmacion": "RESTAURAR"})
    assert "no está en buen estado" in r.text and _cuentas(cliente) == 2


def test_borrar_una_copia_quita_su_fichero(cliente):
    ruta = _hacer(cliente)
    r = cliente.post(f"{BASE}/borrar", data={"ids": [ruta.name]})
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "ok" and not ruta.exists()
    r = cliente.post(f"{BASE}/borrar", data={"ids": ["../../bd/prueba.sqlite"]})
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "error" and (cliente.app.state.config.datos / "prueba.sqlite").exists()


def test_los_dialogos_avisan_de_que_estan_trabajando_y_desactivan_el_boton(cliente):
    """Hacer, verificar y restaurar pueden tardar: el aviso de espera está en el diálogo (oculto hasta que se pulsa) y el botón se desactiva al pulsarlo."""
    _hacer(cliente)
    esperado = {"hacer": "Haciendo la copia de seguridad", "verificar": "Verificando la copia", "restaurar": "Restaurando la copia"}
    for modo, texto in esperado.items():
        dialogo = cliente.get(f"{BASE}/accion/{modo}").text
        assert texto in dialogo and 'id="espera-copias"' in dialogo and "find button[type=submit]" in dialogo, modo


# ------------------------------------------------------------------------------------------------ copia ligera y recuperación de justificantes

import hashlib  # noqa: E402
import sqlite3  # noqa: E402
from pathlib import Path  # noqa: E402


def _adjuntar_pdf_de_factura(cliente, nombre="000001_proveedor.pdf", contenido=b"%PDF-1.4 una factura recibida" * 40):
    almacen = cliente.app.state.config.almacen
    ruta = f"001/2026/R/{nombre}"
    (almacen / ruta).parent.mkdir(parents=True, exist_ok=True)
    (almacen / ruta).write_bytes(contenido)
    con = sqlite3.connect(cliente.app.state.config.datos / "prueba.sqlite")
    con.execute("insert into adjunto (factura_id, orden, nombre, ruta_relativa, tipo_mime, sha256, tamano) values (1, 0, ?, ?, 'application/pdf', ?, ?)",
                (nombre, ruta, hashlib.sha256(contenido).hexdigest(), len(contenido)))
    con.commit()
    con.close()
    return almacen / ruta, contenido


def test_el_dialogo_de_hacer_la_copia_explica_que_es_ligera_y_ofrece_la_completa(cliente):
    dialogo = cliente.get(f"{BASE}/accion/hacer").text
    assert "ligera" in dialogo and "solo su huella" in dialogo and 'name="completa"' in dialogo


def test_la_copia_ligera_deja_fuera_los_pdf_de_facturas_y_la_completa_los_lleva(cliente):
    _adjuntar_pdf_de_factura(cliente)
    ligera = _hacer(cliente)
    r = cliente.post(f"{BASE}/accion/hacer", data={"completa": "on"})
    assert "Copia completa hecha y verificada" in _mensaje(r)
    completa = [c for c in sorted(cliente.app.state.config.copias.glob("copia_prueba_*.zip")) if c != ligera][-1]
    assert ligera.stat().st_size < completa.stat().st_size
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Ligera" in tabla and "Completa" in tabla
    ficha = cliente.get(f"{BASE}/f/{ligera.name}").text
    assert "no lleva 1 PDF de facturas" in ficha
    r = cliente.post(f"{BASE}/accion/verificar", data={"copia": ligera.name})
    assert "copia <strong>ligera</strong>" in r.text and "no lleva 1 PDF" in r.text


def test_recuperar_justificantes_busca_por_contenido_en_las_carpetas_indicadas(cliente, tmp_path):
    pdf, contenido = _adjuntar_pdf_de_factura(cliente)
    assert "No falta ningún justificante" in cliente.get(f"{BASE}/accion/recuperar").text
    pdf.unlink()
    assert "Faltan 1 justificante" in cliente.get(f"{BASE}/accion/recuperar").text
    onedrive = tmp_path / "OneDrive" / "Facturas 3T"
    onedrive.mkdir(parents=True)
    (onedrive / "otro nombre cualquiera.pdf").write_bytes(contenido)
    r = cliente.post(f"{BASE}/accion/recuperar", data={"carpetas": ""})
    assert "Indique al menos una carpeta" in r.text
    r = cliente.post(f"{BASE}/accion/recuperar", data={"carpetas": str(tmp_path / "no existe")})
    assert "No existe la carpeta" in r.text
    r = cliente.post(f"{BASE}/accion/recuperar", data={"carpetas": str(tmp_path / "OneDrive")})
    assert "Recuperados: 1" in r.text and pdf.read_bytes() == contenido
    assert "No falta ningún justificante" in r.text


def test_tras_restaurar_una_copia_ligera_avisa_de_los_pdf_que_faltan(cliente):
    pdf, _ = _adjuntar_pdf_de_factura(cliente)
    ligera = _hacer(cliente)
    pdf.unlink()  # el almacén se perdió pero la base (restaurada) sigue sabiendo que el PDF existía
    r = cliente.post(f"{BASE}/accion/restaurar", data={"copia": ligera.name, "confirmacion": "RESTAURAR"})
    assert "Copia restaurada" in r.text and "Faltan 1 PDF de facturas" in r.text and "Recuperar justificantes" in r.text
