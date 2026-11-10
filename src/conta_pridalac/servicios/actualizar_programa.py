"""Actualizar Conta desde GitHub: buscar si hay versión nueva y actualizar.

Requiere que la carpeta del programa sea un clon de git (`git clone`) con su origen configurado y que git esté instalado; si el repositorio es privado, el equipo ya tiene que tener las credenciales de GitHub
(es lo que ocurre con el Git Credential Manager). Los datos no se tocan: están en `datos_locales`, que no está en git.

Por seguridad, antes de actualizar:
- se negará si hay ficheros del programa modificados a mano (un `git pull` los pisaría o fallaría a medias);
- hace una copia de seguridad ligera de cada empresa (si falla alguna, no se actualiza);
- sólo avanza si es un avance limpio (`--ff-only`): nunca mezcla ni reescribe nada.
Si cambió `pyproject.toml` (dependencias), vuelve a instalarlas con pip. Después hay que cerrar y volver a abrir el programa; las bases añaden solas las columnas nuevas al abrirse.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from conta_pridalac.domain.errores import ErrorContable

RAIZ = Path(__file__).resolve().parents[3]  # carpeta del programa (la que tiene .git y pyproject.toml)


def _git(raiz: Path, *args: str, timeout: int = 60) -> tuple[int, str]:
    entorno = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # sin credenciales no se queda esperando a que se teclee algo: falla
    try:
        r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, timeout=timeout, env=entorno, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return 1, f"git tardó más de {timeout} s en responder"
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace").strip()


def disponible(raiz: Path = RAIZ) -> str | None:
    """`None` si se puede actualizar; si no, el motivo."""
    if not (raiz / ".git").exists():
        return "Esta carpeta no es un clon de GitHub (se copió a mano): para poder actualizar hay que instalar el programa con «git clone»."
    if not shutil.which("git"):
        return "Falta git en este ordenador (winget install Git.Git)."
    cod, _ = _git(raiz, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if cod != 0:
        return "La carpeta no tiene una rama enlazada con GitHub (falta el «upstream»)."
    return None


@dataclass
class Version:
    hash: str = ""
    fecha: str = ""
    resumen: str = ""

    def __str__(self) -> str:
        return f"{self.hash} · {self.fecha} · {self.resumen}" if self.hash else "desconocida"


def version(raiz: Path = RAIZ) -> Version:
    if not (raiz / ".git").exists() or not shutil.which("git"):
        return Version()
    cod, txt = _git(raiz, "log", "-1", "--format=%h\t%cd\t%s", "--date=format:%d/%m/%Y")
    partes = txt.split("\t", 2)
    return Version(*partes) if cod == 0 and len(partes) == 3 else Version()


def origen(raiz: Path = RAIZ) -> str:
    """La dirección del repositorio, sin usuario ni clave por si los llevara."""
    cod, txt = _git(raiz, "remote", "get-url", "origin")
    if cod != 0:
        return ""
    if "@" in txt and "://" in txt:
        esquema, resto = txt.split("://", 1)
        txt = f"{esquema}://{resto.split('@', 1)[1]}"
    return txt


@dataclass
class Comprobacion:
    pendientes: int = -1               # -1: no se pudo comprobar
    cambios: list[str] = field(default_factory=list)
    adelantados: int = 0               # cambios locales que GitHub no tiene (el equipo de quien desarrolla)
    mensaje: str = ""

    @property
    def al_dia(self) -> bool:
        return self.pendientes == 0


def comprobar(raiz: Path = RAIZ) -> Comprobacion:
    """Pregunta a GitHub (`git fetch`) cuántos cambios nuevos hay. No cambia nada del programa."""
    if (motivo := disponible(raiz)):
        return Comprobacion(mensaje=motivo)
    cod, txt = _git(raiz, "fetch", "--quiet", timeout=90)
    if cod != 0:
        return Comprobacion(mensaje=f"No se pudo conectar con GitHub: {txt[:300]}")
    cod, n = _git(raiz, "rev-list", "--count", "HEAD..@{u}")
    if cod != 0 or not n.strip().isdigit():
        return Comprobacion(mensaje=n[:300] or "No se pudo comparar con GitHub")
    _, adelante = _git(raiz, "rev-list", "--count", "@{u}..HEAD")
    pendientes = int(n)
    cambios = []
    if pendientes:
        _, lista = _git(raiz, "log", "--format=%h · %cd · %s", "--date=format:%d/%m/%Y", "HEAD..@{u}")
        cambios = [l for l in lista.splitlines() if l.strip()]
    mensaje = "El programa está al día." if not pendientes else f"Hay {pendientes} cambio(s) nuevo(s) en GitHub."
    return Comprobacion(pendientes, cambios, int(adelante) if adelante.strip().isdigit() else 0, mensaje)


FICHERO_COMPROBACION = "_programa.json"  # en la carpeta de datos: lo último que se supo de GitHub, para enseñarlo sin volver a consultar


def guardar_comprobacion(carpeta_datos: Path, c: Comprobacion) -> None:
    try:
        (Path(carpeta_datos) / FICHERO_COMPROBACION).write_text(
            json.dumps({"fecha": datetime.now().isoformat(timespec="seconds"), "pendientes": c.pendientes, "cambios": c.cambios, "mensaje": c.mensaje}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # sin poder guardar, sólo se pierde el recuerdo de la última comprobación


def ultima_comprobacion(carpeta_datos: Path) -> dict:
    """`{"fecha", "pendientes", "cambios", "mensaje"}` de la última vez que se buscó, o `{}` si nunca."""
    try:
        d = json.loads((Path(carpeta_datos) / FICHERO_COMPROBACION).read_text(encoding="utf-8"))
        datetime.fromisoformat(d["fecha"])
        return d
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def modificados(raiz: Path = RAIZ) -> list[str]:
    """Ficheros del programa (los que git sigue) con cambios sin guardar en este equipo."""
    cod, txt = _git(raiz, "status", "--porcelain", "--untracked-files=no")
    return [l.split(None, 1)[1] for l in txt.splitlines() if len(l.split(None, 1)) == 2] if cod == 0 else []  # «_M fichero»: git rellena con un espacio y `_git` recorta el primero


def _python_consola() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def instalar_dependencias(raiz: Path = RAIZ) -> tuple[bool, str]:
    r = subprocess.run([_python_consola(), "-m", "pip", "install", "--quiet", "-e", str(raiz)], capture_output=True, timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0, r.stderr.decode("utf-8", "replace")[-500:]


@dataclass
class Resultado:
    ok: bool
    informe: list[str] = field(default_factory=list)
    actualizado: bool = False          # el programa ha cambiado: hay que cerrarlo y volver a abrirlo


def actualizar(raiz: Path = RAIZ, *, antes: Callable[[], list[str]] | None = None, instalar: Callable[[Path], tuple[bool, str]] = instalar_dependencias) -> Resultado:
    """`git pull --ff-only` y, si cambiaron las dependencias, `pip install`. `antes` se llama justo antes de tocar nada (la copia de seguridad) y devuelve lo que ha hecho;
    si lanza `ErrorContable`, no se actualiza."""
    if (motivo := disponible(raiz)):
        return Resultado(False, [motivo])
    c = comprobar(raiz)
    if c.pendientes < 0:
        return Resultado(False, [c.mensaje])
    if c.pendientes == 0:
        return Resultado(True, ["El programa ya estaba al día."])
    if propios := modificados(raiz):
        return Resultado(False, ["Hay ficheros del programa modificados en este equipo, y actualizar los pisaría o fallaría a medias:", *[f"   {f}" for f in propios[:10]],
                                 "Avise a quien mantiene el programa para resolverlo (git)."])
    informe: list[str] = []
    if antes is not None:
        try:
            informe += antes()
        except ErrorContable as e:
            return Resultado(False, [f"No se actualiza porque no se pudo hacer la copia de seguridad: {e}"])
    _, antes_id = _git(raiz, "rev-parse", "HEAD")
    cod, txt = _git(raiz, "pull", "--ff-only", timeout=180)
    if cod != 0:
        return Resultado(False, informe + [f"No se pudo actualizar (no se ha cambiado nada): {txt[:400]}"])
    _, despues_id = _git(raiz, "rev-parse", "HEAD")
    if antes_id == despues_id:
        return Resultado(True, informe + ["El programa ya estaba al día."])
    _, cambiados = _git(raiz, "diff", "--name-only", antes_id, despues_id)
    informe.append(f"Actualizado a {version(raiz)}.")
    if "pyproject.toml" in cambiados.split():
        ok, error = instalar(raiz)
        if not ok:
            return Resultado(False, informe + ["Falló la instalación de las dependencias nuevas: ejecute `instalar.bat` en la carpeta del programa.", error], actualizado=True)
        informe.append("Dependencias actualizadas.")
    informe.append("Cierre el programa y vuelva a abrirlo para usar la versión nueva.")
    return Resultado(True, informe, actualizado=True)
