"""Copias de seguridad: hacer, verificar, listar y restaurar (con copia previa)."""
import hashlib
import json
import os
import shutil
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.copias import hacer_copia, leer_manifiesto, listar_copias, restaurar_copia, verificar_copia


@pytest.fixture
def entorno(tmp_path):
    bd = tmp_path / "bd" / "prueba.sqlite"
    bd.parent.mkdir()
    motor = crear_motor(bd)
    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)])
    s.flush()
    s.add(Cuenta(empresa_id=e.id, codigo="62900000", nombre="SERVICIOS"))
    s.commit()
    s.close()
    motor.dispose()
    almacen = tmp_path / "almacen"
    (almacen / "001" / "2026" / "F").mkdir(parents=True)
    (almacen / "001" / "2026" / "F" / "1_factura.pdf").write_bytes(b"%PDF-1.4 uno")
    (almacen / "001" / "2026" / "aeat").mkdir()
    (almacen / "001" / "2026" / "aeat" / "fichero.303").write_bytes(b"<T303>")
    (almacen / "002" / "2026").mkdir(parents=True)
    (almacen / "002" / "2026" / "otra_empresa.pdf").write_bytes(b"%PDF-1.4 de otra empresa")
    return bd, almacen, tmp_path / "copias"


def cuentas(bd):
    motor = crear_motor(bd)
    s = nueva_sesion(motor)
    try:
        return s.scalar(select(func.count()).select_from(Cuenta))
    finally:
        s.close()
        motor.dispose()


def test_la_copia_lleva_base_y_justificantes_de_su_empresa_y_se_verifica(entorno):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    assert ruta.parent == copias and ruta.name.startswith("copia_prueba_") and ruta.suffix == ".zip"
    m = leer_manifiesto(ruta)
    rutas = {a["ruta"] for a in m["archivos"]}
    assert rutas == {"base/prueba.sqlite", "justificantes/2026/F/1_factura.pdf", "justificantes/2026/aeat/fichero.303"}  # nada de la empresa 002
    assert m["empresa"] == {"codigo": 1, "nombre": "Empresa de Prueba", "nif": "B12345678"} and m["tablas"]["cuenta"] == 1
    assert verificar_copia(ruta) == [] and not list(copias.glob("*.parcial")) and not list(copias.glob("tmp*"))
    (c,) = listar_copias(copias, "prueba")
    assert c.nombre == ruta.name and c.justificantes == 2 and c.tablas["cuenta"] == 1 and c.empresa == "Empresa de Prueba"


def test_dos_copias_en_el_mismo_segundo_no_se_pisan(entorno):
    bd, almacen, copias = entorno
    a, b = hacer_copia("prueba", bd, almacen, copias), hacer_copia("prueba", bd, almacen, copias, etiqueta="prueba_a_mano")
    assert a != b and len(listar_copias(copias, "prueba")) == 2 and listar_copias(copias, "otra") == []


def _alterar(ruta, miembro, contenido):
    """Reescribe el zip cambiando el contenido de un miembro (sin tocar el manifiesto)."""
    nuevo = ruta.with_suffix(".nuevo")
    with zipfile.ZipFile(ruta) as origen, zipfile.ZipFile(nuevo, "w") as destino:
        for i in origen.infolist():
            destino.writestr(i.filename, contenido if i.filename == miembro else origen.read(i.filename))
    nuevo.replace(ruta)


def test_la_verificacion_detecta_ficheros_alterados_o_ausentes_y_zips_que_no_lo_son(entorno, tmp_path):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    _alterar(ruta, "justificantes/2026/F/1_factura.pdf", b"%PDF-1.4 cambiado")
    assert any("no coincide con la huella" in p for p in verificar_copia(ruta))
    otra = hacer_copia("prueba", bd, almacen, copias)
    _alterar(otra, "base/prueba.sqlite", b"esto no es sqlite")
    assert verificar_copia(otra)
    falsa = tmp_path / "falsa.zip"
    falsa.write_bytes(b"no es un zip")
    assert "no es una copia de seguridad válida" in verificar_copia(falsa)[0]
    sin_manifiesto = tmp_path / "vacia.zip"
    with zipfile.ZipFile(sin_manifiesto, "w") as z:
        z.writestr("otra_cosa.txt", "x")
    assert verificar_copia(sin_manifiesto)


def test_restaurar_devuelve_la_base_y_los_justificantes_y_deja_copia_del_estado_anterior(entorno):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    # después de la copia: una cuenta más, un justificante nuevo, otro borrado y otro cambiado
    motor = crear_motor(bd)
    s = nueva_sesion(motor)
    s.add(Cuenta(empresa_id=s.scalar(select(Empresa.id)), codigo="62900001", nombre="MÁS"))
    s.commit()
    s.close()
    motor.dispose()
    (almacen / "001" / "2026" / "F" / "2_nueva.pdf").write_bytes(b"%PDF-1.4 dos")
    (almacen / "001" / "2026" / "aeat" / "fichero.303").unlink()
    (almacen / "001" / "2026" / "F" / "1_factura.pdf").write_bytes(b"%PDF-1.4 modificado")
    assert cuentas(bd) == 2
    llamadas = []
    previa = restaurar_copia(ruta, "prueba", bd, almacen, copias, liberar=lambda: llamadas.append(1))
    assert llamadas == [1] and cuentas(bd) == 1
    assert (almacen / "001" / "2026" / "F" / "1_factura.pdf").read_bytes() == b"%PDF-1.4 uno" and (almacen / "001" / "2026" / "aeat" / "fichero.303").read_bytes() == b"<T303>"
    assert not (almacen / "001" / "2026" / "F" / "2_nueva.pdf").exists()
    assert (almacen / "002" / "2026" / "otra_empresa.pdf").read_bytes() == b"%PDF-1.4 de otra empresa"  # no se toca otra empresa
    assert "antes_de_restaurar" in previa.name and verificar_copia(previa) == [] and leer_manifiesto(previa)["tablas"]["cuenta"] == 2
    assert not [p for p in almacen.iterdir() if p.name.startswith(".antes")]
    restaurar_copia(previa, "prueba", bd, almacen, copias)  # y se puede deshacer
    assert cuentas(bd) == 2 and (almacen / "001" / "2026" / "F" / "2_nueva.pdf").exists()


def test_no_se_restaura_una_copia_dañada_ni_de_otra_empresa(entorno):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    _alterar(ruta, "justificantes/2026/F/1_factura.pdf", b"%PDF-1.4 cambiado")
    antes = cuentas(bd)
    with pytest.raises(ErrorContable, match="no está en buen estado"):
        restaurar_copia(ruta, "prueba", bd, almacen, copias)
    assert cuentas(bd) == antes and not list(copias.glob("*antes_de_restaurar*"))  # ni siquiera se llegó a hacer la copia previa

    otra_bd = bd.parent / "otra.sqlite"
    shutil.copy(bd, otra_bd)
    motor = crear_motor(otra_bd)
    s = nueva_sesion(motor)
    s.scalars(select(Empresa)).first().codigo = 2
    s.commit()
    s.close()
    motor.dispose()
    buena = hacer_copia("prueba", bd, almacen, copias)
    with pytest.raises(ErrorContable, match="otra empresa"):
        restaurar_copia(buena, "otra", otra_bd, almacen, copias)


def test_una_copia_con_rutas_peligrosas_no_se_extrae_fuera(entorno, tmp_path):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    contenido = b"malicioso"
    m = leer_manifiesto(ruta)
    m["archivos"].append({"ruta": "justificantes/../../../fuera.txt", "sha256": hashlib.sha256(contenido).hexdigest(), "bytes": len(contenido)})
    nuevo = ruta.with_suffix(".nuevo")
    with zipfile.ZipFile(ruta) as origen, zipfile.ZipFile(nuevo, "w") as destino:
        for i in origen.infolist():
            destino.writestr(i.filename, json.dumps(m) if i.filename == "manifest.json" else origen.read(i.filename))
        destino.writestr("justificantes/../../../fuera.txt", contenido)
    nuevo.replace(ruta)
    with pytest.raises(ErrorContable, match="ruta no válida.*No se ha cambiado nada"):
        restaurar_copia(ruta, "prueba", bd, almacen, copias)
    assert not list(copias.glob("*antes_de_restaurar*"))  # no se tocó nada: la copia previa no se deja de recuerdo
    assert not (tmp_path / "fuera.txt").exists() and not list(tmp_path.rglob("fuera.txt"))


def test_restaurar_con_el_explorador_abierto_en_la_carpeta_de_justificantes(entorno):
    """Windows no deja renombrar una carpeta que otro programa tiene abierta (el Explorador, un visor…): restaurar no debe depender de eso."""
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    (almacen / "001" / "2026" / "F" / "2_nueva.pdf").write_bytes(b"%PDF-1.4 dos")
    antes = Path.cwd()
    os.chdir(almacen / "001" / "2026" / "F")  # un proceso con esa carpeta abierta
    try:
        restaurar_copia(ruta, "prueba", bd, almacen, copias)
    finally:
        os.chdir(antes)
    assert not (almacen / "001" / "2026" / "F" / "2_nueva.pdf").exists() and (almacen / "001" / "2026" / "F" / "1_factura.pdf").read_bytes() == b"%PDF-1.4 uno"


def test_restaurar_la_misma_copia_sobre_un_estado_identico_funciona_y_deja_su_copia_previa(entorno):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    previa = restaurar_copia(ruta, "prueba", bd, almacen, copias)
    assert previa.exists() and cuentas(bd) == 1


class _abierto_en_exclusiva:
    """Abre un fichero bloqueándolo para los demás (Windows), como hace un visor de PDF o un antivirus mientras trabajan."""

    def __init__(self, ruta, compartir=1):
        import ctypes

        self.ctypes = ctypes
        self.ruta = str(ruta)
        self.compartir = compartir  # 1 = otros pueden leerlo pero no escribirlo (un visor de PDF); 0 = nadie

    def __enter__(self):
        k = self.ctypes.windll.kernel32
        k.CreateFileW.restype = self.ctypes.c_void_p
        self.manejador = k.CreateFileW(self.ruta, 0x80000000, self.compartir, None, 3, 0, None)  # GENERIC_READ, OPEN_EXISTING
        assert self.manejador not in (None, self.ctypes.c_void_p(-1).value)
        return self

    def __exit__(self, *a):
        self.ctypes.windll.kernel32.CloseHandle(self.ctypes.c_void_p(self.manejador))


@pytest.mark.skipif(os.name != "nt", reason="En Linux un fichero abierto no impide sustituirlo")
def test_un_justificante_abierto_en_otro_programa_no_deja_la_restauracion_a_medias(entorno):
    bd, almacen, copias = entorno
    ruta = hacer_copia("prueba", bd, almacen, copias)
    motor = crear_motor(bd)
    s = nueva_sesion(motor)
    s.add(Cuenta(empresa_id=s.scalar(select(Empresa.id)), codigo="62900001", nombre="MÁS"))
    s.commit()
    s.close()
    motor.dispose()
    (almacen / "001" / "2026" / "aeat" / "fichero.303").write_bytes(b"<T303>cambiado despues")  # cambia después de la copia...
    (almacen / "001" / "2026" / "F" / "2_nueva.pdf").write_bytes(b"%PDF-1.4 dos")
    with _abierto_en_exclusiva(almacen / "001" / "2026" / "aeat" / "fichero.303"):  # ...y otro programa lo tiene abierto (como un visor de PDF)
        with pytest.raises(ErrorContable, match="fichero.303.*abierto en otro programa.*Todo sigue como estaba"):
            restaurar_copia(ruta, "prueba", bd, almacen, copias)
    assert cuentas(bd) == 2 and (almacen / "001" / "2026" / "F" / "2_nueva.pdf").read_bytes() == b"%PDF-1.4 dos"
    assert (almacen / "001" / "2026" / "aeat" / "fichero.303").read_bytes() == b"<T303>cambiado despues"
    assert [p.name for p in copias.glob("*.zip")] == [ruta.name]  # sin copias previas inútiles


@pytest.mark.skipif(os.name != "nt", reason="En Linux un fichero abierto no impide leerlo")
def test_hacer_una_copia_con_un_fichero_bloqueado_lo_explica_en_vez_de_romper(entorno):
    bd, almacen, copias = entorno
    with _abierto_en_exclusiva(almacen / "001" / "2026" / "F" / "1_factura.pdf", compartir=0):
        with pytest.raises(ErrorContable, match="1_factura.pdf.*abierto en otro programa"):
            hacer_copia("prueba", bd, almacen, copias)
    assert not list(copias.glob("*.zip")) and not list(copias.glob("*.parcial"))


# ------------------------------------------------------------------------------------------------ copia ligera y recuperación de justificantes

import sqlite3  # noqa: E402

from conta_pridalac.servicios.copias import justificantes_que_faltan, recuperar_justificantes  # noqa: E402


def _con_pdfs_de_facturas(entorno):
    """Añade al almacén dos PDF de facturas (carpetas R y E) y los anota en la tabla `adjunto` con su huella, como hace el programa."""
    bd, almacen, copias = entorno
    pdfs = {"001/2026/R/000001_proveedor.pdf": b"%PDF-1.4 recibida uno" * 50, "001/2026/E/000002_cliente.pdf": b"%PDF-1.4 emitida dos" * 50}
    con = sqlite3.connect(bd)
    for i, (ruta, contenido) in enumerate(pdfs.items(), 1):
        destino = almacen / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        con.execute("insert into adjunto (factura_id, orden, nombre, ruta_relativa, tipo_mime, sha256, tamano) values (?, 0, ?, ?, 'application/pdf', ?, ?)",
                    (i, Path(ruta).name, ruta, hashlib.sha256(contenido).hexdigest(), len(contenido)))
    con.commit()
    con.close()
    return pdfs


def test_la_copia_ligera_no_lleva_los_pdf_de_las_facturas_pero_si_su_huella(entorno):
    bd, almacen, copias = entorno
    pdfs = _con_pdfs_de_facturas(entorno)
    ligera = hacer_copia("prueba", bd, almacen, copias)
    completa = hacer_copia("prueba", bd, almacen, copias, completa=True)
    m = leer_manifiesto(ligera)
    rutas = {a["ruta"] for a in m["archivos"]}
    assert m["version"] == 2 and m["completa"] is False and not any("/R/" in r or "/E/" in r for r in rutas) and "justificantes/2026/F/1_factura.pdf" in rutas
    assert {e["ruta"] for e in m["excluidos"]} == {"justificantes/" + r.split("/", 1)[1] for r in pdfs} and all(len(e["sha256"]) == 64 for e in m["excluidos"])
    assert verificar_copia(ligera) == [] and verificar_copia(completa) == []
    assert ligera.stat().st_size < completa.stat().st_size and not any("/R/" in n for n in zipfile.ZipFile(ligera).namelist())
    assert any("/R/" in n for n in zipfile.ZipFile(completa).namelist()) and leer_manifiesto(completa)["completa"] is True and leer_manifiesto(completa)["excluidos"] == []
    por_nombre = {c.nombre: c for c in listar_copias(copias, "prueba")}
    assert (por_nombre[ligera.name].completa, por_nombre[ligera.name].fuera) == (False, 2) and por_nombre[completa.name].completa and por_nombre[completa.name].fuera == 0


def test_restaurar_no_borra_los_pdf_de_las_facturas_aunque_no_esten_en_la_copia(entorno):
    bd, almacen, copias = entorno
    pdfs = _con_pdfs_de_facturas(entorno)
    ligera = hacer_copia("prueba", bd, almacen, copias)
    nuevo = almacen / "001" / "2026" / "R" / "000009_posterior.pdf"
    nuevo.write_bytes(b"%PDF-1.4 hecha despues")
    (almacen / "001" / "2026" / "F" / "2_nueva.pdf").write_bytes(b"%PDF-1.4 otra cosa")  # esto SÍ se limpia: no es de factura
    restaurar_copia(ligera, "prueba", bd, almacen, copias)
    assert nuevo.read_bytes() == b"%PDF-1.4 hecha despues" and all((almacen / r).is_file() for r in pdfs) and not (almacen / "001" / "2026" / "F" / "2_nueva.pdf").exists()


def test_los_justificantes_que_faltan_se_recuperan_por_su_contenido_desde_cualquier_carpeta(entorno, tmp_path):
    bd, almacen, copias = entorno
    pdfs = _con_pdfs_de_facturas(entorno)
    assert justificantes_que_faltan(bd, almacen) == []
    recibida, emitida = (almacen / r for r in pdfs)
    contenido_recibida = recibida.read_bytes()
    recibida.unlink()
    emitida.write_bytes(b"cambiado")  # un fichero con otro tamaño también cuenta como falta
    assert {f.ruta for f in justificantes_que_faltan(bd, almacen)} == set(pdfs)
    # las carpetas de trimestre del usuario: otros nombres, otras subcarpetas, ficheros que no son y una copia de la recibida
    trimestre = tmp_path / "OneDrive" / "Facturas 3T" / "julio"
    trimestre.mkdir(parents=True)
    (trimestre / "Factura proveedor 119-2026.pdf").write_bytes(contenido_recibida)
    (trimestre / "otra.pdf").write_bytes(b"%PDF-1.4 sin relacion")
    (trimestre / "notas.txt").write_text("nada")
    r = recuperar_justificantes(bd, almacen, [tmp_path / "OneDrive"])
    assert r.recuperados == 1 and [f.ruta for f in r.faltan] == ["001/2026/E/000002_cliente.pdf"] and recibida.read_bytes() == contenido_recibida
    assert emitida.read_bytes() == b"cambiado"  # lo que no se encuentra no se toca
    contenido_emitida = b"%PDF-1.4 emitida dos" * 50
    (trimestre / "Emitida 2026-15.pdf").write_bytes(contenido_emitida)
    r2 = recuperar_justificantes(bd, almacen, [tmp_path / "OneDrive"])
    assert r2.recuperados == 1 and r2.faltan == [] and emitida.read_bytes() == contenido_emitida and justificantes_que_faltan(bd, almacen) == []
    assert recuperar_justificantes(bd, almacen, [tmp_path / "no existe"]).recuperados == 0  # no hay nada que buscar: no se mira ni la carpeta
    recibida.unlink()
    with pytest.raises(ErrorContable, match="No existe la carpeta"):
        recuperar_justificantes(bd, almacen, [tmp_path / "no existe"])


def test_la_recuperacion_rechaza_una_ruta_que_se_sale_del_almacen(entorno, tmp_path):
    bd, almacen, copias = entorno
    con = sqlite3.connect(bd)
    con.execute("insert into adjunto (factura_id, orden, nombre, ruta_relativa, tipo_mime, sha256, tamano) values (1, 0, 'x.pdf', '../../fuera.pdf', 'application/pdf', ?, 5)", ("a" * 64,))
    con.commit()
    con.close()
    with pytest.raises(ErrorContable, match="ruta de justificante no válida"):
        justificantes_que_faltan(bd, almacen)
