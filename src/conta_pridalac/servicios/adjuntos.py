"""Justificantes (PDF y JPG) de facturas, movimientos de banco y asientos, con un almacén de ficheros en disco.

Disposición del almacén: `<raíz>/<empresa 3 dígitos>/<año>/<R|E|B|X>/<id del adjunto>_<nombre saneado>`; `Adjunto.ruta_relativa`
es la ruta bajo `<raíz>` y `Adjunto.nombre` el nombre original que se enseña al usuario. Se guarda la huella SHA-256: un
fichero cambiado o borrado a mano se detecta con `verificar_almacen`.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Adjunto, Asiento, DeclaracionPresentada, Ejercicio, Factura, MovimientoBanco
from conta_pridalac.domain.errores import EjercicioCerrado, ErrorContable

MAXIMO_BYTES = 25 * 1024 * 1024
TIPOS = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
Destino = Factura | MovimientoBanco | Asiento


class AdjuntoInvalido(ErrorContable):
    """El fichero no es un PDF/JPG válido o no se puede adjuntar."""


@dataclass
class ResultadoAdjuntar:
    adjunto: Adjunto
    advertencias: list[str] = field(default_factory=list)


@dataclass
class InformeAlmacen:
    ausentes: list[Adjunto] = field(default_factory=list)  # referenciados pero sin fichero
    alterados: list[Adjunto] = field(default_factory=list)  # el fichero ya no tiene la huella guardada
    huerfanos: list[Path] = field(default_factory=list)  # ficheros del almacén sin adjunto

    @property
    def correcto(self) -> bool:
        return not (self.ausentes or self.alterados or self.huerfanos)


class AlmacenAdjuntos:
    def __init__(self, raiz: str | Path):
        self.raiz = Path(raiz)

    def ruta(self, adjunto: Adjunto) -> Path:
        destino = (self.raiz / adjunto.ruta_relativa).resolve()
        if self.raiz.resolve() not in destino.parents:  # nunca fuera del almacén, aunque la ruta guardada sea rara
            raise AdjuntoInvalido(f"Ruta fuera del almacén: {adjunto.ruta_relativa}")
        return destino


# ------------------------------------------------------------------------------------------------ utilidades


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _tipo_mime(nombre: str) -> str:
    mime = TIPOS.get(Path(nombre).suffix.lower())
    if mime is None:
        raise AdjuntoInvalido(f"«{nombre}»: sólo se admiten ficheros PDF y JPG")
    return mime


def _validar_contenido(mime: str, cabecera: bytes, nombre: str) -> None:
    # Los lectores de PDF aceptan basura antes de la cabecera (dentro del primer KB): los PDF descargados de sedes electrónicas
    # llegan a veces envueltos en una parte MIME.
    if mime == "application/pdf" and b"%PDF-" not in cabecera[:1024]:
        raise AdjuntoInvalido(f"«{nombre}» no es un PDF válido")
    if mime == "image/jpeg" and not cabecera.startswith(b"\xff\xd8\xff"):
        raise AdjuntoInvalido(f"«{nombre}» no es una imagen JPG válida")


def nombre_seguro(nombre: str) -> str:
    """Nombre apto para disco: sin rutas ni caracteres raros, extensión en minúsculas, máximo 100 caracteres."""
    base = Path(nombre.replace("\\", "/")).name
    tronco, ext = Path(base).stem, Path(base).suffix.lower()
    tronco = re.sub(r"[^\w .()\-]", "_", tronco, flags=re.UNICODE).strip(" .") or "adjunto"
    return tronco[: 100 - len(ext)] + ext


def _columna(destino: Destino) -> str:
    if isinstance(destino, Factura):
        return "factura_id"
    if isinstance(destino, MovimientoBanco):
        return "movimiento_banco_id"
    if isinstance(destino, Asiento):
        return "asiento_id"
    raise TypeError(f"No se puede adjuntar a {type(destino).__name__}")


def _destino_de(sesion: Session, adjunto: Adjunto) -> Destino:
    if adjunto.factura_id is not None:
        return sesion.get(Factura, adjunto.factura_id)
    if adjunto.movimiento_banco_id is not None:
        return sesion.get(MovimientoBanco, adjunto.movimiento_banco_id)
    return sesion.get(Asiento, adjunto.asiento_id)


def _prefijo(destino: Destino) -> str:
    if isinstance(destino, Factura):
        return destino.sentido
    return "B" if isinstance(destino, MovimientoBanco) else "X"


def _comprobar(ejercicio: Ejercicio, destino: Destino) -> None:
    if destino.ejercicio_id != ejercicio.id:
        raise ErrorContable("El documento no pertenece a este ejercicio")
    if ejercicio.cerrado:
        raise EjercicioCerrado(f"El ejercicio {ejercicio.anio} está cerrado: no se pueden cambiar sus justificantes")


def _ruta_destino(ejercicio: Ejercicio, destino: Destino, adjunto_id: int, nombre: str) -> str:
    return f"{ejercicio.empresa.codigo:03d}/{ejercicio.anio}/{_prefijo(destino)}/{adjunto_id:06d}_{nombre_seguro(nombre)}"


# ------------------------------------------------------------------------------------------------ altas y bajas


def listar(sesion: Session, destino: Destino) -> list[Adjunto]:
    columna = getattr(Adjunto, _columna(destino))
    return list(sesion.scalars(select(Adjunto).where(columna == destino.id).order_by(Adjunto.orden, Adjunto.id)))


def adjuntar(
    sesion: Session, almacen: AlmacenAdjuntos, ejercicio: Ejercicio, destino: Destino, origen: str | Path, *, nombre: str | None = None,
    ignorar_cierre: bool = False,
) -> ResultadoAdjuntar:
    """Copia un PDF/JPG al almacén y lo asocia al documento. Un duplicado idéntico no se vuelve a guardar (se avisa).

    `ignorar_cierre` es sólo para las migraciones: los justificantes de ejercicios ya cerrados se cargan igualmente.
    """
    if ignorar_cierre and destino.ejercicio_id != ejercicio.id:
        raise ErrorContable("El documento no pertenece a este ejercicio")
    if not ignorar_cierre:
        _comprobar(ejercicio, destino)
    origen = Path(origen)
    nombre = nombre or origen.name
    mime = _tipo_mime(nombre)
    if not origen.is_file():
        raise AdjuntoInvalido(f"No existe el fichero {origen}")
    tamano = origen.stat().st_size
    if tamano == 0:
        raise AdjuntoInvalido(f"«{nombre}» está vacío")
    if tamano > MAXIMO_BYTES:
        raise AdjuntoInvalido(f"«{nombre}» pesa {tamano / 1048576:.1f} MB; el máximo es {MAXIMO_BYTES // 1048576} MB")
    with open(origen, "rb") as f:
        _validar_contenido(mime, f.read(1024), nombre)
    huella = sha256_de(origen)
    existentes = listar(sesion, destino)
    for a in existentes:
        if a.sha256 == huella:
            return ResultadoAdjuntar(a, [f"«{nombre}» ya estaba adjunto como «{a.nombre}»; no se ha duplicado"])
    adjunto = Adjunto(
        **{_columna(destino): destino.id}, orden=max((a.orden for a in existentes), default=0) + 1, nombre=nombre,
        ruta_relativa="", tipo_mime=mime, sha256=huella, tamano=tamano,
    )
    sesion.add(adjunto)
    sesion.flush()
    adjunto.ruta_relativa = _ruta_destino(ejercicio, destino, adjunto.id, nombre)
    final = almacen.ruta(adjunto)
    try:
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, final)
    except OSError as e:
        sesion.delete(adjunto)
        sesion.flush()
        raise AdjuntoInvalido(f"No se pudo guardar «{nombre}»: {e}") from e
    return ResultadoAdjuntar(adjunto)


def quitar(sesion: Session, almacen: AlmacenAdjuntos, ejercicio: Ejercicio, adjunto: Adjunto, *, borrar_fichero: bool = True) -> None:
    """Quita el justificante del documento y, por defecto, borra su fichero del almacén."""
    destino = _destino_de(sesion, adjunto)
    _comprobar(ejercicio, destino)
    ruta = almacen.ruta(adjunto) if adjunto.ruta_relativa else None
    sesion.delete(adjunto)
    sesion.flush()
    if borrar_fichero and ruta is not None and ruta.is_file():
        ruta.unlink()


def sustituir(
    sesion: Session, almacen: AlmacenAdjuntos, ejercicio: Ejercicio, adjunto: Adjunto, origen: str | Path, *, nombre: str | None = None
) -> ResultadoAdjuntar:
    """Cambia el fichero de un justificante conservando su posición. Si el nuevo no es válido, no se toca el antiguo."""
    destino = _destino_de(sesion, adjunto)
    orden = adjunto.orden
    nuevo = adjuntar(sesion, almacen, ejercicio, destino, origen, nombre=nombre)
    if nuevo.adjunto.id == adjunto.id:  # mismo contenido: no hay nada que sustituir
        return nuevo
    quitar(sesion, almacen, ejercicio, adjunto)
    nuevo.adjunto.orden = orden
    sesion.flush()
    return nuevo


# ------------------------------------------------------------------------------------------------ comprobaciones y traslado


def verificar_almacen(sesion: Session, almacen: AlmacenAdjuntos, *, empresa_codigo: int | None = None) -> InformeAlmacen:
    """Cruza los adjuntos con el disco: ficheros ausentes, alterados (huella distinta) y huérfanos (sin adjunto)."""
    informe = InformeAlmacen()
    referenciadas: set[Path] = set()
    for a in sesion.scalars(select(Adjunto)):
        ruta = almacen.ruta(a) if a.ruta_relativa else None
        if ruta is None or not ruta.is_file():
            informe.ausentes.append(a)
            continue
        referenciadas.add(ruta)
        if a.sha256 and sha256_de(ruta) != a.sha256:
            informe.alterados.append(a)
    for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.pdf_ruta.is_not(None))):  # el PDF de una declaración presentada también está referenciado
        ruta = almacen.raiz / d.pdf_ruta
        if ruta.is_file():
            referenciadas.add(ruta)
    base = almacen.raiz / f"{empresa_codigo:03d}" if empresa_codigo is not None else almacen.raiz
    if base.is_dir():
        resueltas = {r.resolve() for r in referenciadas}  # una sola vez: recalcularlo por fichero tardaba minutos con miles de justificantes
        informe.huerfanos = sorted(p for p in base.rglob("*") if p.is_file() and p.resolve() not in resueltas)
    return informe


def facturas_sin_justificante(sesion: Session, ejercicio: Ejercicio, sentido: str = "R") -> list[Factura]:
    """Facturas del ejercicio (por defecto recibidas) que no tienen ningún justificante presente."""
    con_fichero = select(Adjunto.factura_id).where(Adjunto.factura_id.is_not(None), Adjunto.sha256.is_not(None))
    return list(
        sesion.scalars(
            select(Factura)
            .where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == sentido, Factura.id.not_in(con_fichero))
            .order_by(Factura.fecha_contable, Factura.numero)
        )
    )


def trasladar_a_almacen(sesion: Session, almacen: AlmacenAdjuntos, ejercicio: Ejercicio, carpeta_origen: str | Path) -> int:
    """Copia al almacén los justificantes importados de MGD (ruta relativa a `carpeta_origen`) y deja su ruta definitiva.

    Los ausentes se dejan como están. Devuelve cuántos ficheros se copiaron.
    """
    carpeta = Path(carpeta_origen)
    copiados = 0
    consulta = (
        select(Adjunto)
        .outerjoin(Factura, Factura.id == Adjunto.factura_id)
        .outerjoin(MovimientoBanco, MovimientoBanco.id == Adjunto.movimiento_banco_id)
        .outerjoin(Asiento, Asiento.id == Adjunto.asiento_id)
        .where(ejercicio.id == func.coalesce(Factura.ejercicio_id, MovimientoBanco.ejercicio_id, Asiento.ejercicio_id))
    )
    for a in sesion.scalars(consulta):
        origen = carpeta / a.ruta_relativa
        if a.ruta_relativa.startswith(f"{ejercicio.empresa.codigo:03d}/") or not origen.is_file():
            continue
        destino = _destino_de(sesion, a)
        a.ruta_relativa = _ruta_destino(ejercicio, destino, a.id, a.nombre)
        final = almacen.ruta(a)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, final)
        copiados += 1
    sesion.flush()
    return copiados
