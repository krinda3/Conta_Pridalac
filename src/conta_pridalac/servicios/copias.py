"""Copias de seguridad de una empresa y su restauración.

Una copia es un `.zip` con la base de datos de la empresa (copia coherente hecha con la API de copias de SQLite, aunque la aplicación esté abierta), los justificantes del almacén y un
`manifest.json` con el contenido y la huella SHA-256 de cada fichero. Toda copia se **verifica** al hacerla (huellas, integridad de SQLite y recuento de las tablas principales) y volverá a
verificarse antes de restaurarla. Restaurar sustituye la base y los justificantes de la empresa por los de la copia, y **antes** hace una copia automática del estado actual
(`…_antes_de_restaurar.zip`), de modo que siempre se puede deshacer.

**Copia ligera y copia completa (versión 2).** Los PDF de las facturas (carpetas `R` y `E` del almacén) son casi todo el peso —y no cambian nunca—, y cada uno ya está en las carpetas de
trimestre del usuario. Por eso la copia normal es **ligera**: lleva la base y todo lo demás (declaraciones y acuses de la sede, libros, depósito, ficheros de los modelos, justificantes de bancos y
asientos) y, de los PDF de facturas, solo su lista con la huella (`excluidos` en el manifiesto). Con `completa=True` van también los PDF. Después de restaurar, `recuperar_justificantes` trae los
que falten desde las carpetas que se indiquen, **por su contenido** (la base guarda la huella de cada adjunto), sin importar cómo se llamen o dónde estén. Restaurar **nunca borra** PDF de facturas.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import huellas

VERSION = 2
TABLAS_PRINCIPALES = ("factura", "asiento", "apunte", "movimiento_banco", "adjunto", "declaracion_presentada", "presentacion_aeat", "cuenta", "tercero")
PREFIJO_BASE, PREFIJO_JUSTIFICANTES = "base/", "justificantes/"
DE_FACTURA = re.compile(r"^\d{4}/[RE]/")  # «2025/R/000123_x.pdf»: el documento de una factura recibida (R) o emitida (E), relativo a la carpeta de la empresa en el almacén
EXTENSIONES_DE_JUSTIFICANTE = (".pdf", ".jpg", ".jpeg")


@dataclass
class Copia:
    ruta: Path
    momento: datetime
    slug: str
    empresa: str
    nif: str
    tamano: int
    tablas: dict[str, int] = field(default_factory=dict)
    justificantes: int = 0
    etiqueta: str = ""
    completa: bool = True  # lleva también los PDF de las facturas (las copias de la versión 1 siempre)
    fuera: int = 0  # PDF de facturas que no lleva (solo su huella)
    fuera_bytes: int = 0

    @property
    def nombre(self) -> str:
        return self.ruta.name


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _recuento(ruta_bd: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{ruta_bd.as_posix()}?mode=ro", uri=True)
    try:
        existentes = {r[0] for r in con.execute("select name from sqlite_master where type = 'table'")}
        return {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in TABLAS_PRINCIPALES if t in existentes}
    finally:
        con.close()


def _integridad(ruta_bd: Path) -> str:
    con = sqlite3.connect(f"file:{ruta_bd.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute("pragma integrity_check").fetchone()[0]
    finally:
        con.close()


def _datos_de_la_empresa(ruta_bd: Path) -> tuple[int, str, str]:
    con = sqlite3.connect(f"file:{ruta_bd.as_posix()}?mode=ro", uri=True)
    try:
        fila = con.execute("select codigo, nombre, coalesce(nif, '') from empresa order by id limit 1").fetchone()
    finally:
        con.close()
    if fila is None:
        raise ErrorContable("La base de datos no tiene ninguna empresa")
    return fila


def _nombre_libre(carpeta: Path, slug: str, etiqueta: str) -> Path:
    base = f"copia_{slug}_{datetime.now():%Y%m%d_%H%M%S}" + (f"_{etiqueta}" if etiqueta else "")
    ruta, n = carpeta / f"{base}.zip", 1
    while ruta.exists():
        n += 1
        ruta = carpeta / f"{base}_{n}.zip"
    return ruta


def hacer_copia(slug: str, ruta_bd: Path, almacen: Path, carpeta_copias: Path, *, etiqueta: str = "", completa: bool = False) -> Path:
    """Crea y **verifica** la copia de la empresa `slug`. Devuelve la ruta del `.zip`; si la copia no verifica, la borra y falla.
    Por defecto es ligera (sin los PDF de las facturas, solo su huella); con `completa=True` los lleva."""
    try:
        return _hacer_copia(slug, ruta_bd, almacen, carpeta_copias, etiqueta, completa)
    except PermissionError as e:  # un fichero que otro programa tiene bloqueado (Windows)
        raise ErrorContable(f"No se puede copiar «{Path(e.filename).name if e.filename else 'un fichero'}» porque está abierto en otro programa; ciérrelo y vuelva a intentarlo") from None


def _hacer_copia(slug: str, ruta_bd: Path, almacen: Path, carpeta_copias: Path, etiqueta: str, completa: bool) -> Path:
    ruta_bd, almacen, carpeta_copias = Path(ruta_bd), Path(almacen), Path(carpeta_copias)
    if not ruta_bd.is_file():
        raise ErrorContable(f"No existe la base de datos de la empresa {slug}")
    codigo, nombre, nif = _datos_de_la_empresa(ruta_bd)
    carpeta_copias.mkdir(parents=True, exist_ok=True)
    destino = _nombre_libre(carpeta_copias, slug, etiqueta)
    with tempfile.TemporaryDirectory(dir=carpeta_copias) as temporal:
        copia_bd = Path(temporal) / f"{slug}.sqlite"
        origen, destino_bd = sqlite3.connect(ruta_bd), sqlite3.connect(copia_bd)
        try:
            origen.backup(destino_bd)  # copia coherente aunque haya otra conexión abierta
        finally:
            destino_bd.close()
            origen.close()
        huellas.anotar_de_archivo(almacen, codigo, copia_bd, f"copia de seguridad {destino.name}")  # la última huella del registro de cambios, fuera de la base
        carpeta_just = almacen / f"{codigo:03d}"
        archivos = [(copia_bd, PREFIJO_BASE + copia_bd.name)]
        fuera: list[tuple[Path, str]] = []
        if carpeta_just.is_dir():
            for f in sorted(carpeta_just.rglob("*")):
                if not f.is_file():
                    continue
                relativa = f.relative_to(carpeta_just).as_posix()
                (fuera if (not completa and DE_FACTURA.match(relativa)) else archivos).append((f, PREFIJO_JUSTIFICANTES + relativa))
        manifiesto = {
            "version": VERSION, "slug": slug, "empresa": {"codigo": codigo, "nombre": nombre, "nif": nif}, "creada": datetime.now().isoformat(timespec="seconds"), "etiqueta": etiqueta,
            "completa": completa, "tablas": _recuento(copia_bd), "archivos": [{"ruta": arc, "sha256": _sha256(f), "bytes": f.stat().st_size} for f, arc in archivos],
            "excluidos": [{"ruta": arc, "sha256": _sha256(f), "bytes": f.stat().st_size} for f, arc in fuera],  # los PDF de facturas que no van en la copia ligera
        }
        parcial = destino.with_suffix(".zip.parcial")
        try:
            with zipfile.ZipFile(parcial, "w") as z:
                z.writestr("manifest.json", json.dumps(manifiesto, ensure_ascii=False, indent=1))
                for f, arc in archivos:
                    z.write(f, arc, compress_type=zipfile.ZIP_DEFLATED if f.suffix == ".sqlite" else zipfile.ZIP_STORED)
            problemas = verificar_copia(parcial)
            if problemas:
                raise ErrorContable("La copia no ha pasado la verificación y se ha descartado: " + "; ".join(problemas))
            os.replace(parcial, destino)
        finally:
            parcial.unlink(missing_ok=True)
    return destino


def leer_manifiesto(ruta: Path) -> dict:
    try:
        with zipfile.ZipFile(ruta) as z:
            return json.loads(z.read("manifest.json"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        raise ErrorContable(f"«{Path(ruta).name}» no es una copia de seguridad válida ({e})") from None


def verificar_copia(ruta: Path) -> list[str]:
    """Problemas de una copia (lista vacía = correcta): zip íntegro, huella de cada fichero, integridad de SQLite y recuento de tablas."""
    ruta = Path(ruta)
    try:
        manifiesto = leer_manifiesto(ruta)
    except ErrorContable as e:
        return [str(e)]
    problemas: list[str] = []
    with zipfile.ZipFile(ruta) as z:
        malo = z.testzip()
        if malo:
            return [f"El fichero «{malo}» de la copia está dañado"]
        presentes = set(z.namelist())
        for a in manifiesto.get("archivos", []):
            if a["ruta"] not in presentes:
                problemas.append(f"Falta «{a['ruta']}» en la copia")
                continue
            h = hashlib.sha256()
            with z.open(a["ruta"]) as f:
                for bloque in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(bloque)
            if h.hexdigest() != a["sha256"]:
                problemas.append(f"«{a['ruta']}» no coincide con la huella guardada")
        bases = [a["ruta"] for a in manifiesto.get("archivos", []) if a["ruta"].startswith(PREFIJO_BASE)]
        if len(bases) != 1:
            problemas.append("La copia debe llevar exactamente una base de datos")
        elif not problemas:
            with tempfile.TemporaryDirectory() as temporal:
                bd = Path(temporal) / "copia.sqlite"
                bd.write_bytes(z.read(bases[0]))
                try:
                    if (resultado := _integridad(bd)) != "ok":
                        problemas.append(f"La base de datos de la copia no pasa la comprobación de integridad: {resultado}")
                    elif _recuento(bd) != manifiesto.get("tablas"):
                        problemas.append("El recuento de registros de la base de datos no coincide con el anotado al hacer la copia")
                except sqlite3.Error as e:
                    problemas.append(f"La base de datos de la copia no se puede abrir: {e}")
    return problemas


def listar_copias(carpeta_copias: Path, slug: str) -> list[Copia]:
    """Las copias de la empresa, la más reciente primero (sin verificarlas: sólo se lee su manifiesto)."""
    copias = []
    for ruta in Path(carpeta_copias).glob(f"copia_{slug}_*.zip"):
        try:
            m = leer_manifiesto(ruta)
        except ErrorContable:
            continue
        copias.append(Copia(
            ruta=ruta, momento=datetime.fromisoformat(m["creada"]), slug=m["slug"], empresa=m["empresa"]["nombre"], nif=m["empresa"]["nif"], tamano=ruta.stat().st_size, tablas=m.get("tablas", {}),
            justificantes=sum(a["ruta"].startswith(PREFIJO_JUSTIFICANTES) for a in m["archivos"]), etiqueta=m.get("etiqueta", ""), completa=m.get("completa", True),
            fuera=len(m.get("excluidos", [])), fuera_bytes=sum(a["bytes"] for a in m.get("excluidos", [])),
        ))
    return sorted(copias, key=lambda c: c.momento, reverse=True)


def _extraer(z: zipfile.ZipFile, miembros: list[str], quitar: str, destino: Path) -> None:
    """Extrae `miembros` quitando el prefijo `quitar`; rechaza rutas que se salgan del destino."""
    raiz = destino.resolve()
    for m in miembros:
        objetivo = (raiz / m[len(quitar):]).resolve()
        if raiz not in objetivo.parents:
            raise ErrorContable(f"La copia lleva una ruta no válida: {m}")
        objetivo.parent.mkdir(parents=True, exist_ok=True)
        with z.open(m) as origen, open(objetivo, "wb") as f:
            shutil.copyfileobj(origen, f)


def restaurar_copia(
    ruta_copia: Path, slug: str, ruta_bd: Path, almacen: Path, carpeta_copias: Path, *, liberar: Callable[[], None] = lambda: None,
) -> Path:
    """Sustituye la base y los justificantes de la empresa por los de la copia. Devuelve la copia de seguridad del estado anterior.

    Orden: verifica la copia → comprueba que es de esta misma empresa → hace una copia del estado actual → `liberar()` (cierra las conexiones a la base) → extrae a una carpeta temporal →
    sincroniza los justificantes y cambia la base. Si algo falla, se deja todo como estaba y se explica por qué (típicamente un fichero abierto en otro programa); si no se llegó a tocar
    nada, la copia previa se borra porque no hace falta.
    """
    ruta_copia, ruta_bd, almacen, carpeta_copias = Path(ruta_copia), Path(ruta_bd), Path(almacen), Path(carpeta_copias)
    problemas = verificar_copia(ruta_copia)
    if problemas:
        raise ErrorContable("La copia no está en buen estado y no se puede restaurar: " + "; ".join(problemas))
    manifiesto = leer_manifiesto(ruta_copia)
    codigo, _, nif = _datos_de_la_empresa(ruta_bd)
    de_la_copia = manifiesto["empresa"]
    if de_la_copia["codigo"] != codigo or (nif and de_la_copia["nif"] and de_la_copia["nif"] != nif):
        raise ErrorContable(f"La copia es de otra empresa ({de_la_copia['nombre']}, {de_la_copia['nif']}) y no se puede restaurar sobre ésta")
    previa = hacer_copia(slug, ruta_bd, almacen, carpeta_copias, etiqueta="antes_de_restaurar")
    liberar()
    carpeta_just = almacen / f"{codigo:03d}"
    cambiado = False
    try:
        with tempfile.TemporaryDirectory(dir=ruta_bd.parent) as temporal, zipfile.ZipFile(ruta_copia) as z:
            nueva_bd, nuevos_just = Path(temporal) / "nueva.sqlite", Path(temporal) / "justificantes"
            miembros = [a["ruta"] for a in manifiesto["archivos"]]
            _extraer(z, [m for m in miembros if m.startswith(PREFIJO_BASE)], PREFIJO_BASE, Path(temporal) / "base")
            shutil.move(str(next((Path(temporal) / "base").iterdir())), nueva_bd)
            nuevos_just.mkdir()
            _extraer(z, [m for m in miembros if m.startswith(PREFIJO_JUSTIFICANTES)], PREFIJO_JUSTIFICANTES, nuevos_just)
            cambiado = True  # a partir de aquí se toca lo que hay en el disco
            _sincronizar(nuevos_just, carpeta_just, conservar=DE_FACTURA.match)  # restaurar nunca borra un PDF de factura: como mucho añade o repone
            try:
                os.replace(nueva_bd, ruta_bd)
            except OSError as e:
                raise ErrorContable(f"No se puede sustituir la base de datos ({e.strerror or e}): ¿está abierta en otro programa?") from None
    except (ErrorContable, OSError) as e:
        mensaje = str(e) if isinstance(e, ErrorContable) else f"{e.strerror or e}"
        if not cambiado:  # no se llegó a tocar nada: la copia previa no hace falta
            previa.unlink(missing_ok=True)
            raise ErrorContable(f"No se pudo restaurar: {mensaje}. No se ha cambiado nada.") from None
        try:  # se vuelve a dejar como estaba, con la copia previa
            _devolver_justificantes(previa, almacen, codigo)
        except (ErrorContable, OSError) as e2:
            raise ErrorContable(f"No se pudo restaurar ({mensaje}) y tampoco se pudo devolver todo a su sitio ({e2}). El estado anterior completo está en {previa.name}: restáurelo desde ahí.") from None
        previa.unlink(missing_ok=True)
        raise ErrorContable(f"No se pudo restaurar: {mensaje}. Todo sigue como estaba.") from None
    huellas.anotar_de_archivo(almacen, codigo, ruta_bd, f"{huellas.RESTAURACION} de {ruta_copia.name}")
    return previa


def _sincronizar(origen: Path, destino: Path, conservar: Callable[[str], object] = lambda rel: None) -> None:
    """Deja `destino` con exactamente los ficheros de `origen`, sin renombrar carpetas (en Windows no se puede renombrar una carpeta que otro programa tiene abierta, p. ej. el Explorador).
    Los ficheros de `destino` que no están en `origen` se borran, salvo los que cumplan `conservar(ruta relativa)`."""
    destino.mkdir(parents=True, exist_ok=True)
    nuevos = {f.relative_to(origen) for f in origen.rglob("*") if f.is_file()}
    for rel in sorted(nuevos):
        fuente, objetivo = origen / rel, destino / rel
        try:
            if objetivo.is_file() and objetivo.stat().st_size == fuente.stat().st_size and _sha256(objetivo) == _sha256(fuente):
                continue  # ya es igual: no se toca (así tampoco molesta que esté abierto)
            objetivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fuente, objetivo)
        except PermissionError:
            raise ErrorContable(f"No se puede sustituir «{rel.as_posix()}» porque está abierto en otro programa; ciérrelo y vuelva a intentarlo") from None
    for f in sorted(destino.rglob("*"), reverse=True):
        try:
            if f.is_file() and f.relative_to(destino) not in nuevos and not conservar(f.relative_to(destino).as_posix()):
                f.unlink()
            elif f.is_dir() and not any(f.iterdir()):
                f.rmdir()
        except PermissionError:
            if f.is_file():
                raise ErrorContable(f"No se puede quitar «{f.relative_to(destino).as_posix()}» porque está abierto en otro programa; ciérrelo y vuelva a intentarlo") from None


def _devolver_justificantes(copia_previa: Path, almacen: Path, codigo: int) -> None:
    """Vuelve a dejar los justificantes de la empresa como estaban en la copia previa (por si falla una restauración a medias)."""
    with tempfile.TemporaryDirectory() as temporal, zipfile.ZipFile(copia_previa) as z:
        miembros = [a["ruta"] for a in leer_manifiesto(copia_previa)["archivos"] if a["ruta"].startswith(PREFIJO_JUSTIFICANTES)]
        _extraer(z, miembros, PREFIJO_JUSTIFICANTES, Path(temporal))
        _sincronizar(Path(temporal), almacen / f"{codigo:03d}", conservar=DE_FACTURA.match)


# ------------------------------------------------------------------------------------------------ justificantes que faltan y su recuperación

@dataclass
class Falta:
    ruta: str  # relativa al almacén: «001/2025/R/000123_x.pdf»
    sha256: str
    tamano: int


@dataclass
class Recuperacion:
    recuperados: int = 0
    revisados: int = 0  # ficheros de las carpetas que se han mirado
    faltan: list[Falta] = field(default_factory=list)  # los que siguen sin aparecer


def _adjuntos_con_huella(ruta_bd: Path) -> list[Falta]:
    con = sqlite3.connect(f"file:{Path(ruta_bd).as_posix()}?mode=ro", uri=True)
    try:
        existe = con.execute("select 1 from sqlite_master where type = 'table' and name = 'adjunto'").fetchone()
        filas = con.execute("select ruta_relativa, sha256, coalesce(tamano, 0) from adjunto where sha256 is not null").fetchall() if existe else []
    finally:
        con.close()
    return [Falta(r, h, int(tam)) for r, h, tam in filas]


def _dentro(almacen: Path, relativa: str) -> Path:
    raiz = almacen.resolve()
    ruta = (raiz / relativa).resolve()
    if raiz not in ruta.parents:
        raise ErrorContable(f"La base de datos lleva una ruta de justificante no válida: {relativa}")
    return ruta


def justificantes_que_faltan(ruta_bd: Path, almacen: Path) -> list[Falta]:
    """Los documentos que la base de datos dice tener (con su huella) y que no están en el almacén o tienen otro tamaño."""
    almacen = Path(almacen)
    faltan = []
    for a in _adjuntos_con_huella(ruta_bd):
        ruta = _dentro(almacen, a.ruta)
        if not ruta.is_file() or (a.tamano and ruta.stat().st_size != a.tamano):
            faltan.append(a)
    return faltan


def recuperar_justificantes(ruta_bd: Path, almacen: Path, carpetas: list[Path]) -> Recuperacion:
    """Repone en el almacén los justificantes que faltan buscándolos **por su contenido** (huella SHA-256) en `carpetas` y todas sus subcarpetas. No importa cómo se llamen ni dónde estén:
    si hay un fichero con la misma huella, se copia a la ruta que la base de datos espera. No toca nada de las carpetas ni sobrescribe ningún fichero del almacén que ya sea correcto."""
    almacen = Path(almacen)
    pendientes: dict[str, list[Falta]] = {}
    for f in justificantes_que_faltan(ruta_bd, almacen):
        pendientes.setdefault(f.sha256, []).append(f)
    resultado = Recuperacion()
    if not pendientes:
        return resultado
    tamanos = {f.tamano for lista in pendientes.values() for f in lista if f.tamano}
    for carpeta in map(Path, carpetas):
        if not carpeta.is_dir():
            raise ErrorContable(f"No existe la carpeta «{carpeta}»")
        for raiz, _, nombres in os.walk(carpeta):
            for nombre in nombres:
                if not nombre.lower().endswith(EXTENSIONES_DE_JUSTIFICANTE):
                    continue
                origen = Path(raiz) / nombre
                try:
                    if tamanos and origen.stat().st_size not in tamanos:
                        continue
                    resultado.revisados += 1
                    huella = _sha256(origen)
                except OSError:
                    continue  # un fichero que no se puede leer (bloqueado, sin permiso): se sigue con los demás
                for falta in pendientes.pop(huella, []):
                    destino = _dentro(almacen, falta.ruta)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origen, destino)
                    resultado.recuperados += 1
        if not pendientes:
            break
    resultado.faltan = [f for lista in pendientes.values() for f in lista]
    return resultado
