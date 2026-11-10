"""Arranque cómodo del programa: si no está en marcha lo arranca **sin ventana** y abre el navegador; con `--parar` lo cierra.

    pythonw -m conta_pridalac.lanzador              # (lo que hace el icono del escritorio)
    pythonw -m conta_pridalac.lanzador --parar

El servidor sigue siendo el de siempre (`python -m conta_pridalac.web`, sólo accesible desde este equipo); esto sólo evita tener que escribir el comando y mantener una ventana abierta.
Su salida se guarda en `web.log`, junto a la carpeta de datos.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from conta_pridalac.web.config import RAIZ_PROYECTO, Configuracion

PUERTO = 8000
CABECERA_APAGAR = {"X-Conta": "apagar"}  # un navegador no puede enviarla desde otra página sin permiso: evita que una web cualquiera apague el programa


def url(puerto: int) -> str:
    return f"http://127.0.0.1:{puerto}"


def en_marcha(puerto: int = PUERTO) -> bool:
    """¿Responde nuestro programa en ese puerto?"""
    try:
        with urllib.request.urlopen(f"{url(puerto)}/tema.css", timeout=1.5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _ejecutable() -> str:
    """En Windows, `pythonw.exe` (no abre ventana de consola) si está junto al intérprete actual."""
    if os.name == "nt":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return sys.executable


def arrancar(puerto: int = PUERTO) -> None:
    """Lanza el servidor como proceso independiente (sigue vivo aunque se cierre quien lo lanzó)."""
    registro = Configuracion().datos.parent / "web.log"
    registro.parent.mkdir(parents=True, exist_ok=True)
    salida = open(registro, "ab")
    opciones = {"creationflags": 0x08000000 | 0x00000008} if os.name == "nt" else {"start_new_session": True}  # sin consola y desligado
    subprocess.Popen([_ejecutable(), "-m", "conta_pridalac.web", "--puerto", str(puerto), "--autoapagar"], cwd=RAIZ_PROYECTO, stdin=subprocess.DEVNULL, stdout=salida, stderr=salida, **opciones)


def esperar(puerto: int = PUERTO, segundos: float = 25) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if en_marcha(puerto):
            return True
        time.sleep(0.4)
    return False


def parar(puerto: int = PUERTO) -> bool:
    """Pide al programa que se cierre. Devuelve si estaba en marcha."""
    if not en_marcha(puerto):
        return False
    peticion = urllib.request.Request(f"{url(puerto)}/_apagar", method="POST", headers=CABECERA_APAGAR, data=b"")
    try:
        urllib.request.urlopen(peticion, timeout=5).close()
    except (urllib.error.URLError, OSError):
        pass
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=PUERTO)
    ap.add_argument("--parar", action="store_true", help="cierra el programa si está en marcha")
    ap.add_argument("--sin-navegador", action="store_true", help="sólo arranca el servidor (para el arranque automático al iniciar sesión)")
    a = ap.parse_args(argv)
    if a.parar:
        print("Programa cerrado." if parar(a.puerto) else "El programa no estaba en marcha.")
        return 0
    if not en_marcha(a.puerto):
        arrancar(a.puerto)
        if not esperar(a.puerto):
            print(f"No se pudo arrancar el programa. Mire el registro: {Configuracion().datos.parent / 'web.log'}", file=sys.stderr)
            return 1
    if not a.sin_navegador:
        webbrowser.open(url(a.puerto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
