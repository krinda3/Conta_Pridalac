"""Copia de los justificantes de Hacienda a una carpeta de la empresa (la de OneDrive, por ejemplo).

Cada modelo presentado deja su PDF en el almacén de Conta; esta copia es un segundo ejemplar, con el nombre que se usa en la carpeta de Hacienda de cada año («EMPRESA B AEAT Mod 303 3T 2026.pdf»). La carpeta
se configura por empresa, con `{año}` donde va el año. Nunca se pisa un fichero distinto: si ya existe uno con otro contenido, el nuevo lleva un sufijo.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa, PresentacionAeat, PRESENTADA, SUSTITUIDA
from conta_pridalac.servicios.exportar import nombre_corto

COPIADO, IGUAL, CON_SUFIJO, FALLO, SIN_CARPETA = "copiado", "igual", "con_sufijo", "fallo", "sin_carpeta"
MODELOS_ANUALES = ("190", "180", "347", "390", "200")


@dataclass
class Justificante:
    nombre: str  # el nombre con el que se copia
    ruta: Path  # el PDF en el almacén


@dataclass
class Copia:
    nombre: str
    estado: str
    destino: Path | None = None
    mensaje: str = ""


@dataclass
class ResultadoCopias:
    copias: list[Copia] = field(default_factory=list)

    def cuantos(self, estado: str) -> int:
        return sum(1 for c in self.copias if c.estado == estado)


def carpeta_de(empresa: Empresa, anio: int) -> Path | None:
    """La carpeta de destino de ese año, o `None` si la empresa no la tiene configurada."""
    plantilla = (empresa.carpeta_justificantes or "").strip().strip('"')
    return Path(plantilla.replace("{año}", str(anio)).replace("{anio}", str(anio))) if plantilla else None


def nombre_de(empresa: Empresa, modelo: str, anio: int, periodo: str | int, tipo_presentacion: str = "normal") -> str:
    """`EMPRESA B AEAT Mod 303 3T 2026.pdf`; los anuales (190, 347, 390, 200) llevan sólo el año, y una rectificativa o complementaria lo dice al final."""
    corto = nombre_corto(empresa).replace("_", " ")
    texto = str(periodo)
    trimestral = (f"{texto}T" if texto.isdigit() else texto) if modelo not in MODELOS_ANUALES and texto else ""
    partes = [corto, "AEAT", "Mod", modelo] + ([trimestral] if trimestral else []) + [str(anio)] + ([] if tipo_presentacion in ("normal", "", None) else [tipo_presentacion])
    return re.sub(r'[<>:"/\\|?*]+', "", " ".join(partes)) + ".pdf"


def justificantes_del_anio(sesion: Session, empresa: Empresa, anio: int, raiz_almacen: Path, trimestre: int | None = None) -> list[Justificante]:
    """Los PDF de los modelos presentados ese año: los registrados aquí (también los que una rectificativa ha sustituido) y los importados del programa anterior.

    Con `trimestre`, sólo los modelos de ese trimestre (303, 111…): los anuales y los de otros trimestres no entran.
    """
    resultado: list[Justificante] = []
    for p in sesion.scalars(select(PresentacionAeat).where(PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.anio == anio, PresentacionAeat.estado.in_((PRESENTADA, SUSTITUIDA))).order_by(PresentacionAeat.id)):
        if trimestre is not None and p.periodo != f"{trimestre}T":
            continue
        ruta = Path(raiz_almacen) / p.respuesta_ruta if p.respuesta_ruta else None
        if ruta is not None and ruta.is_file():
            resultado.append(Justificante(nombre_de(empresa, p.modelo, anio, p.periodo, p.tipo_presentacion), ruta))
    for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.anio == anio).order_by(DeclaracionPresentada.id)):
        if trimestre is not None and (d.periodo != trimestre or d.modelo in MODELOS_ANUALES):
            continue
        ruta = Path(raiz_almacen) / d.pdf_ruta if d.pdf_ruta else None
        if ruta is not None and ruta.is_file():
            resultado.append(Justificante(nombre_de(empresa, d.modelo, anio, d.periodo, "normal" if d.tipo == 1 else ("rectificativa" if d.tipo == 2 else f"tipo {d.tipo}")), ruta))
    vistos: set[str] = set()
    unicos = []
    for j in resultado:  # lo registrado aquí manda sobre lo importado, si hay dos con el mismo nombre
        if j.nombre not in vistos:
            vistos.add(j.nombre)
            unicos.append(j)
    return unicos


def _huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def estado_de(empresa: Empresa, anio: int, nombre: str, contenido: bytes) -> tuple[str, Path | None]:
    """Qué pasaría al copiar: «copiado» (no está), «igual» (ya está idéntico) o «con_sufijo» (hay otro distinto con ese nombre). Sin carpeta: «sin_carpeta»."""
    carpeta = carpeta_de(empresa, anio)
    if carpeta is None:
        return SIN_CARPETA, None
    destino = carpeta / nombre
    if not destino.exists():
        return COPIADO, destino
    try:
        if _huella(destino.read_bytes()) == _huella(contenido):
            return IGUAL, destino
    except OSError:
        return FALLO, destino
    n = 2
    while True:
        alterno = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not alterno.exists():
            return CON_SUFIJO, alterno
        if _huella(alterno.read_bytes()) == _huella(contenido):
            return IGUAL, alterno
        n += 1


def copiar_pdf(empresa: Empresa, anio: int, nombre: str, contenido: bytes) -> Copia:
    """Copia un PDF a la carpeta de la empresa. Nunca lanza: si no se puede, lo dice en el resultado (la presentación no debe fallar por la copia)."""
    try:
        estado, destino = estado_de(empresa, anio, nombre, contenido)
        if estado == SIN_CARPETA:
            return Copia(nombre, SIN_CARPETA, None, "La empresa no tiene configurada la carpeta de copia de los justificantes")
        if estado in (COPIADO, CON_SUFIJO):
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
        return Copia(nombre, estado, destino, "")
    except OSError as e:
        return Copia(nombre, FALLO, None, f"No se pudo copiar a la carpeta: {e}")


def revisar_copias(sesion: Session, empresa: Empresa, anio: int, raiz_almacen: Path, trimestre: int | None = None) -> ResultadoCopias:
    """Qué haría «copiar todo» sin escribir nada: el estado de cada justificante del año respecto a la carpeta."""
    resultado = ResultadoCopias()
    for j in justificantes_del_anio(sesion, empresa, anio, raiz_almacen, trimestre):
        estado, destino = estado_de(empresa, anio, j.nombre, j.ruta.read_bytes())
        resultado.copias.append(Copia(j.nombre, estado, destino))
    return resultado


def copiar_todos(sesion: Session, empresa: Empresa, anio: int, raiz_almacen: Path, trimestre: int | None = None) -> ResultadoCopias:
    resultado = ResultadoCopias()
    for j in justificantes_del_anio(sesion, empresa, anio, raiz_almacen, trimestre):
        resultado.copias.append(copiar_pdf(empresa, anio, j.nombre, j.ruta.read_bytes()))
    return resultado


def aviso_de_copia(copia: Copia) -> str:
    """El texto que acompaña al «Presentación registrada» según lo que pasó con la copia."""
    if copia.estado == SIN_CARPETA:
        return ""  # sin carpeta configurada no hay copia ni aviso: es una función opcional
    if copia.estado == FALLO:
        return f" · AVISO: {copia.mensaje}"
    if copia.estado == IGUAL:
        return f" · ya estaba copiado en {copia.destino.parent}"
    return f" · copiado a {copia.destino}"
