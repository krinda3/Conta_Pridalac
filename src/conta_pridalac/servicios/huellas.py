"""La última huella del registro de cambios, guardada **fuera de la base** (`db/registro.py`).

Quien tenga el archivo de la base podría reescribir toda la cadena de huellas. Para que eso se note, en cada copia de seguridad, restauración, presentación registrada y cierre o reapertura de un ejercicio se añade una línea
a `huellas_registro_<empresa>.txt`, en la raíz del almacén de justificantes (fuera de la base y de las copias, que no lo sobrescriben al restaurar), y la copia que se lleva a la carpeta de la empresa en OneDrive la acompaña.
Cada línea dice la fecha, el motivo, el número de anotación y su huella, y lleva el SHA-256 de la línea anterior, de modo que el propio fichero tampoco se puede retocar sin que se note.

La auditoría (`comprobar`) exige que la anotación que cita cada línea siga existiendo en la base con la misma huella. Una restauración de una copia antigua deja constancia con su propia línea: lo que se anotó después de esa
anotación deja de exigirse (sigue a la vista en el fichero).
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from conta_pridalac.db.registro import RegistroCambio, ultima_huella

RESTAURACION = "RESTAURACIÓN"
SEPARADOR = " | "


def ruta_del_fichero(almacen: Path, codigo: int) -> Path:
    return Path(almacen) / f"huellas_registro_{codigo:03d}.txt"


def _sha(linea: str) -> str:
    return hashlib.sha256(linea.encode("utf-8")).hexdigest()


def _lineas(ruta: Path) -> list[str]:
    return [l for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()] if ruta.is_file() else []


def anotar(almacen: Path, codigo: int, motivo: str, numero: int, huella: str) -> None:
    """Añade la línea al fichero de la empresa. No hace nada si la base aún no tiene anotaciones (nada que guardar)."""
    if not numero:
        return
    ruta = ruta_del_fichero(almacen, codigo)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    previas = _lineas(ruta)
    linea = SEPARADOR.join([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), motivo.replace("|", "/"), str(numero), huella, _sha(previas[-1]) if previas else ""])
    with open(ruta, "a", encoding="utf-8", newline="\n") as f:
        f.write(linea + "\n")


def ultima_de_archivo(ruta_bd: Path) -> tuple[int, str]:
    """(número, huella) de la última anotación de una base que está en un archivo (una copia, una base recién restaurada)."""
    conexion = sqlite3.connect(ruta_bd)
    try:
        fila = conexion.execute("SELECT id, huella FROM registro_cambios ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.OperationalError:  # una base anterior al registro
        fila = None
    finally:
        conexion.close()
    return (fila[0], fila[1]) if fila else (0, "")


def anotar_de_archivo(almacen: Path, codigo: int, ruta_bd: Path, motivo: str) -> None:
    numero, huella = ultima_de_archivo(ruta_bd)
    anotar(almacen, codigo, motivo, numero, huella)


def anotar_al_confirmar(sesion: Session, almacen: Path, codigo: int, motivo: str) -> None:
    """Pide anotar la huella cuando la transacción de la sesión se confirme: si se deshace, no se escribe nada (la línea citaría anotaciones que ya no existen)."""
    sesion.info.setdefault("huellas_pendientes", []).append((Path(almacen), codigo, motivo))


@event.listens_for(Session, "after_commit")
def _al_confirmar(sesion: Session) -> None:
    pendientes = sesion.info.pop("huellas_pendientes", None)
    if not pendientes:
        return
    with sesion.get_bind().connect() as conexion:
        fila = conexion.execute(select(RegistroCambio.id, RegistroCambio.huella).order_by(RegistroCambio.id.desc()).limit(1)).first()
    for almacen, codigo, motivo in pendientes:
        if fila:
            anotar(almacen, codigo, motivo, fila[0], fila[1])


@event.listens_for(Session, "after_rollback")
def _al_deshacer(sesion: Session) -> None:
    sesion.info.pop("huellas_pendientes", None)


def comprobar(sesion: Session, almacen: Path, codigo: int) -> list[str]:
    """Lo que no cuadra entre el fichero de huellas y la base (vacío = todo en orden). Sin fichero no hay nada que comprobar."""
    lineas = _lineas(ruta_del_fichero(almacen, codigo))
    problemas: list[str] = []
    esperadas: list[tuple[int, str, str]] = []  # (número, huella, fecha)
    anterior = ""
    for i, linea in enumerate(lineas, 1):
        partes = linea.split(SEPARADOR)
        if len(partes) != 5 or not partes[2].isdigit() or partes[4] != (_sha(anterior) if anterior else ""):
            return [f"El fichero de huellas (línea {i}) ha sido modificado: no continúa la línea anterior"]
        anterior = linea
        fecha, motivo, numero, huella = partes[0], partes[1], int(partes[2]), partes[3]
        if motivo.startswith(RESTAURACION):
            esperadas = [e for e in esperadas if e[0] <= numero]
        esperadas.append((numero, huella, fecha))
    ultima, _ = ultima_huella(sesion)
    for numero, huella, fecha in esperadas:
        if numero > ultima:
            problemas.append(f"Constaba fuera de la base la anotación {numero} ({fecha}) y la base sólo llega a la {ultima}: faltan anotaciones")
            break
        en_la_base = sesion.execute(text("SELECT huella FROM registro_cambios WHERE id = :n"), {"n": numero}).scalar()
        if en_la_base != huella:
            problemas.append(f"La anotación {numero} no coincide con la huella que constaba fuera de la base el {fecha}: se ha reescrito el registro")
            break
    return problemas
