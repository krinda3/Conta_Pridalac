"""Crea el icono para abrir el programa con un doble clic (Windows: acceso directo `.lnk`; Linux: lanzador `.desktop`).

    python tools/crear_acceso_directo.py                  # icono en el escritorio
    python tools/crear_acceso_directo.py --menu           # además, en el menú de inicio / de aplicaciones
    python tools/crear_acceso_directo.py --arranque       # además, que el programa se arranque solo al iniciar sesión (sin abrir el navegador)
    python tools/crear_acceso_directo.py --carpeta X      # sólo en esa carpeta (para probar)

El icono ejecuta `conta_pridalac.lanzador` con el Python de este entorno, así que hay que repetir esta orden si se mueve la carpeta del proyecto o se recrea el `.venv`.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESTATICOS = RAIZ / "src" / "conta_pridalac" / "web" / "static"
NOMBRE = "Conta Pridalac"
DESCRIPCION = "Contabilidad para pequeñas empresas"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    return exe.with_name("pythonw.exe") if os.name == "nt" and exe.with_name("pythonw.exe").is_file() else exe


def contenido_desktop(python: Path, icono: Path, argumentos: str = "") -> str:
    """Texto de un lanzador de escritorio de Linux."""
    return (
        "[Desktop Entry]\nType=Application\nVersion=1.0\n"
        f"Name={NOMBRE}\nComment={DESCRIPCION}\nExec=\"{python.as_posix()}\" -m conta_pridalac.lanzador{(' ' + argumentos) if argumentos else ''}\n"
        f"Path={RAIZ.as_posix()}\nIcon={icono.as_posix()}\nTerminal=false\nCategories=Office;Finance;\n"
    )


def crear_en_linux(carpeta: Path, argumentos: str = "") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "conta-pridalac.desktop"
    ruta.write_text(contenido_desktop(Path(sys.executable), ESTATICOS / "icono.png", argumentos), encoding="utf-8")
    ruta.chmod(0o755)
    _marcar_de_confianza(ruta)
    return ruta


def _marcar_de_confianza(ruta: Path) -> None:
    """En GNOME un lanzador del escritorio no se abre con doble clic hasta que se «permite ejecutar»; así ya sale permitido. Sin `gio` (otros escritorios) no hace nada."""
    if shutil.which("gio"):
        subprocess.run(["gio", "set", str(ruta), "metadata::trusted", "true"], capture_output=True)


def crear_en_windows(carpeta: Path, argumentos: str = "") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{NOMBRE}.lnk"
    arg = f"-m conta_pridalac.lanzador{(' ' + argumentos) if argumentos else ''}"
    guion = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$a = $w.CreateShortcut('{ruta}'); $a.TargetPath = '{_pythonw()}'; $a.Arguments = '{arg}'; $a.WorkingDirectory = '{RAIZ}'; "
        f"$a.IconLocation = '{ESTATICOS / 'icono.ico'}'; $a.Description = '{DESCRIPCION}'; $a.Save()"
    )
    resultado = subprocess.run(["powershell", "-NoProfile", "-Command", guion], capture_output=True, text=True)
    if resultado.returncode != 0 or not ruta.is_file():
        raise SystemExit(f"No se pudo crear el acceso directo: {resultado.stderr.strip() or resultado.stdout.strip()}")
    return ruta


def _carpeta_especial(nombre: str) -> Path:
    """Escritorio, menú de inicio o carpeta de arranque del usuario (respeta las redirecciones, p. ej. a OneDrive)."""
    if os.name == "nt":
        salida = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetFolderPath('{nombre}')"], capture_output=True, text=True).stdout.strip()
        return Path(salida)
    return _carpeta_linux(nombre, Path.home())


def _carpeta_linux(nombre: str, inicio: Path) -> Path:
    if nombre == "Desktop":  # en un Linux en español es «Escritorio», no «Desktop»
        try:
            salida = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=3).stdout.strip()
            if salida and Path(salida) != inicio:
                return Path(salida)
        except (OSError, subprocess.SubprocessError):
            pass
    return {
        "Desktop": inicio / "Desktop", "Programs": inicio / ".local" / "share" / "applications", "Startup": inicio / ".config" / "autostart",
    }[nombre]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--menu", action="store_true", help="también en el menú de inicio (Windows) o de aplicaciones (Linux)")
    ap.add_argument("--arranque", action="store_true", help="también en el arranque de la sesión, sin abrir el navegador")
    ap.add_argument("--carpeta", type=Path, help="crear sólo en esta carpeta")
    a = ap.parse_args(argv)
    crear = crear_en_windows if os.name == "nt" else crear_en_linux
    hecho = []
    if a.carpeta:
        hecho.append(crear(a.carpeta))
    else:
        hecho.append(crear(_carpeta_especial("Desktop")))
        if a.menu:
            hecho.append(crear(_carpeta_especial("Programs")))
        if a.arranque:
            hecho.append(crear(_carpeta_especial("Startup"), "--sin-navegador"))
    for r in hecho:
        print("Creado:", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
