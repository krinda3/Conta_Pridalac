"""Arranque cómodo: lanzador, cierre del programa desde su pantalla y creación del icono."""
import os
import shutil
import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conta_pridalac import lanzador
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import crear_acceso_directo  # noqa: E402


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sin_programa_en_marcha_el_lanzador_lo_sabe():
    assert lanzador.en_marcha(_puerto_libre()) is False
    assert lanzador.parar(_puerto_libre()) is False


class _Servidor:
    should_exit = False


@pytest.fixture
def cliente(tmp_path):
    app = crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "a", copias=tmp_path / "c"))
    return TestClient(app)


def test_cerrar_el_programa_exige_la_cabecera_propia_y_un_servidor_propio(cliente):
    assert cliente.post("/_apagar").status_code == 403  # lo que haría una web cualquiera
    assert cliente.post("/_apagar", headers={"X-Conta": "otra"}).status_code == 403
    assert cliente.post("/_apagar", headers=lanzador.CABECERA_APAGAR).status_code == 409  # sin `app.state.servidor` (p. ej. en las pruebas)
    cliente.app.state.servidor = _Servidor()
    assert cliente.post("/_apagar", headers=lanzador.CABECERA_APAGAR).status_code == 204 and cliente.app.state.servidor.should_exit is True


def test_la_pantalla_tiene_el_boton_de_cerrar_y_los_iconos_existen(cliente):
    assert 'id="salir"' in cliente.get("/").text
    static = Path(__file__).resolve().parents[1] / "src" / "conta_pridalac" / "web" / "static"
    assert (static / "icono.ico").stat().st_size > 1000 and (static / "icono.png").stat().st_size > 1000


def test_el_lanzador_de_linux_apunta_al_lanzador_y_al_icono(tmp_path):
    texto = crear_acceso_directo.contenido_desktop(Path("/usr/bin/python3"), Path("/x/icono.png"), "--sin-navegador")
    assert "Exec=\"/usr/bin/python3\" -m conta_pridalac.lanzador --sin-navegador" in texto and "Icon=/x/icono.png" in texto and "Terminal=false" in texto
    ruta = crear_acceso_directo.crear_en_linux(tmp_path)
    assert ruta.name == "conta-pridalac.desktop" and "[Desktop Entry]" in ruta.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt" or shutil.which("powershell") is None, reason="El acceso directo .lnk sólo se crea en Windows")
def test_el_acceso_directo_de_windows_se_crea_y_apunta_al_lanzador(tmp_path):
    ruta = crear_acceso_directo.crear_en_windows(tmp_path / "escritorio")
    assert ruta.name == "Conta Pridalac.lnk" and ruta.stat().st_size > 100
    leido = __import__("subprocess").run(
        ["powershell", "-NoProfile", "-Command", f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{ruta}'); $s.TargetPath; $s.Arguments; $s.IconLocation"], capture_output=True, text=True
    ).stdout.splitlines()
    assert leido[0].lower().endswith(("pythonw.exe", "python.exe")) and leido[1] == "-m conta_pridalac.lanzador" and leido[2].endswith("icono.ico,0")


def test_el_escritorio_en_linux_se_busca_con_xdg_user_dir_y_cae_a_desktop(tmp_path, monkeypatch):
    """En un Linux en español el escritorio es «Escritorio»; sin xdg-user-dir (o si devuelve la carpeta personal) se usa «Desktop»."""
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": f"{tmp_path}/Escritorio\n"})())
    assert crear_acceso_directo._carpeta_linux("Desktop", tmp_path) == tmp_path / "Escritorio"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": f"{tmp_path}\n"})())   # sin carpeta de escritorio configurada, devuelve la personal
    assert crear_acceso_directo._carpeta_linux("Desktop", tmp_path) == tmp_path / "Desktop"

    def sin_xdg(*a, **k):
        raise FileNotFoundError("xdg-user-dir")

    monkeypatch.setattr(subprocess, "run", sin_xdg)
    assert crear_acceso_directo._carpeta_linux("Desktop", tmp_path) == tmp_path / "Desktop"
    assert crear_acceso_directo._carpeta_linux("Programs", tmp_path) == tmp_path / ".local" / "share" / "applications"
    assert crear_acceso_directo._carpeta_linux("Startup", tmp_path) == tmp_path / ".config" / "autostart"


def test_el_instalador_de_linux_es_un_script_con_fin_de_linea_lf():
    script = (Path(__file__).resolve().parents[1] / "instalar.sh").read_bytes()
    assert script.startswith(b"#!/usr/bin/env bash\n") and b"\r\n" not in script                        # con CRLF, bash falla
    assert b"crear_acceso_directo.py --menu" in script and b"pip install -e ." in script
