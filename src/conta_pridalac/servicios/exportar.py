"""Copia de los ficheros generados a una carpeta fácil de encontrar, con un nombre que se entienda, para subirlos a la sede de la AEAT (o al Registro Mercantil).

Internamente cada fichero vive en el almacén (`<empresa>/<año>/aeat/<id>_C000X_[R]303_<año>_<n>T.303`); desde aquí se **copia** a la carpeta de copias para presentar (por defecto `Descargas\\Conta Pridalac`)
como `<EMPRESA>_AEAT_<modelo>_<año>_<periodo>[_rectificativa].<extensión>`, por ejemplo `EMPRESA_A_AEAT_303_2026_1T_rectificativa.303`. La extensión se conserva (la sede la espera). Es la misma norma
para todos los modelos y para lo que se prepare para el Registro Mercantil.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from conta_pridalac.db.modelos import Empresa, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable

FORMAS_JURIDICAS = re.compile(r"[\s,]+(S\.?\s?L\.?\s?U\.?|S\.?\s?L\.?\s?L\.?|S\.?\s?L\.?|S\.?\s?A\.?\s?U\.?|S\.?\s?A\.?|S\.?\s?COOP\.?|C\.?\s?B\.?|S\.?\s?C\.?)\s*$", re.IGNORECASE)
CARPETA = "Conta Pridalac"


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()


def nombre_corto(empresa: Empresa) -> str:
    """El prefijo de los nombres de fichero: el «nombre corto» de la ficha o, si no hay, la razón social sin la forma jurídica (S.L., S.A.…), en mayúsculas y sin caracteres raros."""
    texto = (empresa.nombre_corto or "").strip() or FORMAS_JURIDICAS.sub("", empresa.nombre or "").strip()
    limpio = re.sub(r"[^A-Z0-9]+", "_", _sin_acentos(texto).upper()).strip("_")
    return limpio or "EMPRESA"


def nombre_para_presentar(empresa: Empresa, modelo: str, anio: int, periodo: str, tipo_presentacion: str, extension: str) -> str:
    """`EMPRESA_A_AEAT_303_2026_1T_rectificativa.303`."""
    sufijo = "" if tipo_presentacion == "normal" else f"_{tipo_presentacion}"
    return f"{nombre_corto(empresa)}_AEAT_{modelo}_{anio}_{periodo}{sufijo}.{extension.lstrip('.')}"


def carpeta_de_descargas() -> Path:
    """La carpeta Descargas del usuario según el sistema (en Windows puede estar redirigida, p. ej. a OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            guid = ctypes.c_buffer(16)
            ctypes.windll.ole32.CLSIDFromString("{374DE290-123F-4565-9164-39C4925E467B}", guid)  # FOLDERID_Downloads
            ruta = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, wintypes.HANDLE(0), ctypes.byref(ruta)) == 0 and ruta.value:
                return Path(ruta.value)
        except Exception:  # sin acceso a la API: se usa la ruta de siempre
            pass
    else:
        try:
            salida = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=3).stdout.strip()
            if salida:
                return Path(salida)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Downloads"


def carpeta_para_presentar() -> Path:
    return Path(os.environ["CONTA_DESCARGAS"]) if os.environ.get("CONTA_DESCARGAS") else carpeta_de_descargas() / CARPETA


def copiar_para_presentar(origen: Path, carpeta: Path, nombre: str) -> tuple[Path, bool]:
    """Copia `origen` a `carpeta/nombre`. Si ya hay un fichero con ese nombre y el mismo contenido no hace nada; si es distinto, no lo pisa y guarda la copia como `nombre_2`, `_3`…
    Devuelve (ruta final, si se ha copiado)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    base, extension = Path(nombre).stem, Path(nombre).suffix
    destino, n = carpeta / nombre, 1
    while destino.exists():
        if origen.read_bytes() == destino.read_bytes():  # no filecmp: su caché por tamaño y fecha daba «igual» a dos ficheros distintos escritos casi a la vez
            return destino, False
        n += 1
        destino = carpeta / f"{base}_{n}{extension}"
    shutil.copyfile(origen, destino)
    return destino, True


def exportar_presentacion(presentacion: PresentacionAeat, empresa: Empresa, raiz_almacen: Path, carpeta: Path) -> tuple[Path, bool]:
    """Copia el fichero generado de una presentación (de cualquier modelo) a la carpeta de copias para presentar, tras comprobar que sigue sin alterar."""
    from conta_pridalac.servicios.presentacion303 import ruta_del_fichero

    if not presentacion.fichero_ruta:
        raise ErrorContable("Esta presentación todavía no tiene fichero generado")
    ruta = ruta_del_fichero(raiz_almacen, presentacion)
    if ruta is None:
        raise ErrorContable("El fichero no está en el almacén o ha cambiado desde que se generó: genérelo de nuevo")
    nombre = nombre_para_presentar(empresa, presentacion.modelo, presentacion.anio, presentacion.periodo, presentacion.tipo_presentacion, Path(presentacion.fichero_nombre or ruta.name).suffix)
    return copiar_para_presentar(ruta, carpeta, nombre)


def abrir_en_el_explorador(ruta: Path) -> None:
    """Abre la carpeta del fichero (seleccionándolo en Windows). Sólo tiene sentido con la aplicación en el mismo equipo."""
    try:
        if os.name == "nt":
            # Como cadena y no como lista: con espacios en la ruta, Python entrecomillaría «/select,ruta» entero y el explorador abriría «Documentos»
            subprocess.Popen(f'explorer /select,"{ruta}"')
        else:
            subprocess.Popen(["xdg-open", str(ruta.parent)])
    except OSError as e:
        raise ErrorContable(f"No se pudo abrir la carpeta: {e}") from None
