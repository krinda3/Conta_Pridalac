"""Dónde están los datos de Conta y cómo cambiarlos de sitio.

Los datos viven en una **carpeta de datos** (la «raíz») con esta forma:

    <raíz>/bd/<empresa>.sqlite      una base por empresa (y `_preferencias.json`, `_normativa.json`…)
    <raíz>/justificantes/           los PDF y demás documentos adjuntos
    <raíz>/copias/                  las copias de seguridad

Por defecto es `datos_locales` junto al programa. Para poder tenerla en otra parte (un disco externo, una carpeta sincronizada, una unidad de red), la ubicación se guarda **fuera** de la
carpeta de datos, en un fichero de configuración del usuario (`%APPDATA%\\ContaPridalac\\ubicacion.json` en Windows, `~/.config/conta-pridalac/ubicacion.json` en Linux). Orden de preferencia:

1. la variable de entorno `CONTA_DATOS` (la carpeta `bd` directamente; la usan las pruebas y quien arranca el programa a mano);
2. la ubicación guardada;
3. `datos_locales` junto al programa.

**Mover** los datos es **copiar, verificar y cambiar**: nunca se borra la carpeta de origen (queda con una nota de que se movió) para que, si algo sale mal, no se pierda nada.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from conta_pridalac.domain.errores import ErrorContable

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
NOTA_DE_TRASLADO = "MOVIDO_A.txt"
MARCA = ".conta_datos"  # fichero que dice «esta carpeta es de Conta»: distingue una carpeta de datos nueva elegida a propósito de una unidad que no está montada
SUBCARPETAS = ("bd", "justificantes", "copias")


# ------------------------------------------------------------------------------------------------ dónde se guarda la ubicación

def carpeta_de_configuracion() -> Path:
    """Dónde guarda el programa sus ajustes de usuario (fuera de la carpeta de datos). `CONTA_CONFIG` la cambia (pruebas)."""
    if os.environ.get("CONTA_CONFIG"):
        return Path(os.environ["CONTA_CONFIG"])
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "ContaPridalac"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "conta-pridalac"


def _fichero() -> Path:
    return carpeta_de_configuracion() / "ubicacion.json"


def raiz_por_defecto() -> Path:
    return RAIZ_PROYECTO / "datos_locales"


def ubicacion_guardada() -> Path | None:
    try:
        ruta = json.loads(_fichero().read_text(encoding="utf-8")).get("raiz")
    except (OSError, ValueError, AttributeError):
        return None
    return Path(ruta) if ruta else None


def guardar_ubicacion(raiz: Path | None) -> None:
    """Fija la carpeta de datos (o, con `None`, vuelve a la de por defecto)."""
    fichero = _fichero()
    if raiz is None:
        fichero.unlink(missing_ok=True)
        return
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(json.dumps({"raiz": str(Path(raiz).resolve()), "desde": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")


def resolver() -> tuple[Path, str]:
    """(carpeta `bd`, de dónde sale: «variable», «guardada» o «por defecto»)."""
    if os.environ.get("CONTA_DATOS"):
        return Path(os.environ["CONTA_DATOS"]), "variable"
    guardada = ubicacion_guardada()
    if guardada is not None:
        return guardada / "bd", "guardada"
    return raiz_por_defecto() / "bd", "por defecto"


def raiz_de(bd: Path) -> Path:
    return Path(bd).parent


def marcar(raiz: Path) -> None:
    """Deja en la carpeta la marca de que es de Conta (la crea si hace falta)."""
    raiz = Path(raiz)
    (raiz / "bd").mkdir(parents=True, exist_ok=True)
    (raiz / MARCA).write_text(f"Carpeta de datos de Conta Pridalac · {datetime.now():%d/%m/%Y %H:%M}\n", encoding="utf-8")


def tiene_marca(raiz: Path) -> bool:
    try:
        return (Path(raiz) / MARCA).is_file()
    except OSError:
        return False


def pide_guia(raiz: Path, origen: str) -> bool:
    """¿Hay que preguntar «¿dónde están sus datos?» en vez de ofrecer crear una empresa? Sólo si la ubicación se eligió a mano (guardada), no hay empresas y la carpeta no se marcó como nueva:
    es lo que pasa con un disco desconectado o una carpeta movida, donde crear empresas dejaría los datos en un sitio equivocado."""
    return origen == "guardada" and not inspeccionar(raiz).tiene_datos and not tiene_marca(raiz)


# ------------------------------------------------------------------------------------------------ qué hay en una carpeta

@dataclass
class Inspeccion:
    raiz: Path
    existe: bool = False
    accesible: bool = True
    empresas: list[str] = field(default_factory=list)
    bytes_bd: int = 0
    bytes_justificantes: int = 0
    bytes_copias: int = 0
    problema: str = ""

    @property
    def tiene_datos(self) -> bool:
        return bool(self.empresas)

    @property
    def total(self) -> int:
        return self.bytes_bd + self.bytes_justificantes + self.bytes_copias


def _tamano(carpeta: Path) -> int:
    total = 0
    for dirpath, _, ficheros in os.walk(carpeta):
        for f in ficheros:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    return total


def inspeccionar(raiz: Path) -> Inspeccion:
    """Qué hay en una carpeta de datos: empresas, tamaños y si se puede leer. Nunca lanza: lo que falla se cuenta en `problema`."""
    raiz = Path(raiz)
    r = Inspeccion(raiz)
    try:
        r.existe = raiz.is_dir()
        if not r.existe:
            r.problema = "La carpeta no existe o no está disponible (¿disco o unidad de red desconectada?)"
            return r
        bd = raiz / "bd"
        if bd.is_dir():
            r.empresas = sorted(p.stem for p in bd.glob("*.sqlite"))
            r.bytes_bd = _tamano(bd)
        r.bytes_justificantes = _tamano(raiz / "justificantes") if (raiz / "justificantes").is_dir() else 0
        r.bytes_copias = _tamano(raiz / "copias") if (raiz / "copias").is_dir() else 0
        if not r.empresas:
            r.problema = "No hay empresas en esta carpeta (se esperan ficheros «.sqlite» dentro de una subcarpeta «bd»)"
    except OSError as e:
        r.accesible = False
        r.problema = f"No se puede leer la carpeta: {e.strerror or e}"
    return r


def normalizar_eleccion(ruta: str | Path) -> Path:
    """Quien elige la carpeta `bd` (o una de dentro) en vez de la raíz: se sube a la raíz."""
    p = Path(str(ruta).strip().strip('"')).expanduser()
    if p.name == "bd" and p.is_dir():
        return p.parent
    return p


def comprobar_destino_para_usar(raiz: Path) -> Inspeccion:
    """Para «usar otra carpeta que ya tiene datos»: tiene que existir y tener empresas."""
    i = inspeccionar(raiz)
    if not i.existe or not i.accesible or not i.tiene_datos:
        raise ErrorContable(i.problema or "No hay datos en esa carpeta")
    return i


# ------------------------------------------------------------------------------------------------ mover los datos

Progreso = Callable[[str, int, int], None]  # (qué se está haciendo, bytes hechos, bytes totales)


def _dentro(a: Path, b: Path) -> bool:
    try:
        a.resolve().relative_to(b.resolve())
        return True
    except ValueError:
        return False


def comprobar_traslado(origen: Path, destino: Path) -> Inspeccion:
    """Todo lo que se puede comprobar antes de empezar. Devuelve la inspección del origen; lanza `ErrorContable` con el motivo si no se puede."""
    origen, destino = Path(origen), Path(destino)
    i = inspeccionar(origen)
    if not i.tiene_datos:
        raise ErrorContable(f"En el origen no hay datos que mover: {i.problema}")
    if origen.resolve() == destino.resolve():
        raise ErrorContable("El destino es la misma carpeta que el origen")
    if _dentro(destino, origen) or _dentro(origen, destino):
        raise ErrorContable("El destino no puede estar dentro del origen ni el origen dentro del destino")
    if destino.exists():
        if not destino.is_dir():
            raise ErrorContable("El destino existe y no es una carpeta")
        if any(destino.iterdir()):
            raise ErrorContable("La carpeta de destino no está vacía: elija una vacía (o una que no exista; se crea). Para usar una carpeta que ya tiene datos, use «Usar otra carpeta con datos»")
    else:
        try:
            destino.mkdir(parents=True)
            destino.rmdir()  # sólo era para comprobar que se puede crear
        except OSError as e:
            raise ErrorContable(f"No se puede crear la carpeta de destino: {e.strerror or e}") from None
    libre = shutil.disk_usage(destino if destino.exists() else destino.parent if destino.parent.exists() else Path(destino.anchor)).free
    if libre < int(i.total * 1.1) + 50 * 1024 * 1024:
        raise ErrorContable(f"No hay sitio suficiente en el destino: hacen falta unos {i.total / 1024 / 1024:,.0f} MB y hay {libre / 1024 / 1024:,.0f} MB libres".replace(",", "."))
    return i


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _copiar_base(origen: Path, destino: Path) -> None:
    """Copia coherente de una base SQLite (aunque esté abierta)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(origen), sqlite3.connect(destino)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def _filas_de_las_tablas(base: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True)
    try:
        tablas = [t for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        return {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tablas}
    finally:
        con.close()


def _integridad(base: Path) -> str:
    con = sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("pragma integrity_check").fetchone()[0]
    finally:
        con.close()


@dataclass
class InformeTraslado:
    origen: Path
    destino: Path
    bases: list[str] = field(default_factory=list)
    ficheros: int = 0
    bytes: int = 0


def trasladar(origen: Path, destino: Path, progreso: Progreso | None = None) -> InformeTraslado:
    """Copia la carpeta de datos entera al destino y comprueba que la copia es idéntica: cada base con `integrity_check` y el mismo número de filas por tabla, y cada fichero con su tamaño y su
    huella SHA-256. Si algo no coincide, borra lo copiado y lanza `ErrorContable`: el origen no se toca nunca. Al terminar deja una nota en el origen (`MOVIDO_A.txt`)."""
    origen, destino = Path(origen), Path(destino)
    i = comprobar_traslado(origen, destino)
    avisar = progreso or (lambda *_: None)
    hecho = 0
    informe = InformeTraslado(origen, destino)
    ficheros = [(p, p.relative_to(origen)) for p in origen.rglob("*") if p.is_file() and not p.name.endswith((".parcial", ".lock", ".tmp"))]
    bases = [(p, r) for p, r in ficheros if r.parts[:1] == ("bd",) and p.suffix == ".sqlite"]
    resto = [(p, r) for p, r in ficheros if (p, r) not in bases]
    destino_creado = not destino.exists()
    try:
        destino.mkdir(parents=True, exist_ok=True)
        marcar(destino)
        for p, r in bases:
            avisar(f"Copiando la base «{p.stem}»", hecho, i.total)
            _copiar_base(p, destino / r)
            hecho += p.stat().st_size
            informe.bases.append(p.stem)
        for p, r in resto:
            avisar(f"Copiando {r.as_posix()}", hecho, i.total)
            (destino / r).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, destino / r)
            hecho += p.stat().st_size
            informe.ficheros += 1
        for sub in SUBCARPETAS:  # las carpetas vacías también cuentan
            (destino / sub).mkdir(exist_ok=True)
        avisar("Verificando la copia", hecho, i.total)
        for p, r in bases:
            copia = destino / r
            if _integridad(copia) != "ok":
                raise ErrorContable(f"La copia de la base «{p.stem}» no pasa la comprobación de integridad")
            if _filas_de_las_tablas(p) != _filas_de_las_tablas(copia):
                raise ErrorContable(f"La copia de la base «{p.stem}» no tiene los mismos datos que el origen")
        for n, (p, r) in enumerate(resto, start=1):
            copia = destino / r
            if not copia.is_file() or copia.stat().st_size != p.stat().st_size or _sha256(copia) != _sha256(p):
                raise ErrorContable(f"El fichero «{r.as_posix()}» no se copió bien")
            avisar("Verificando la copia", hecho, i.total)
        informe.bytes = hecho
    except BaseException:
        if destino_creado:  # no deja una copia a medias que alguien pudiera tomar por buena
            shutil.rmtree(destino, ignore_errors=True)
        raise
    try:
        (origen / NOTA_DE_TRASLADO).write_text(
            f"Estos datos se copiaron a\n{destino}\nel {datetime.now():%d/%m/%Y %H:%M}. Conta usa desde entonces la carpeta nueva: no trabaje con esta.\n"
            "Cuando compruebe que todo está bien en la nueva, puede borrar esta carpeta (o déjela como copia de seguridad).\n", encoding="utf-8")
    except OSError:
        pass  # sólo es un recordatorio
    avisar("Listo", informe.bytes, i.total)
    return informe
