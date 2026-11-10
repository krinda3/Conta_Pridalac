"""Candado de la carpeta de datos: que Conta no se abra a la vez desde dos equipos sobre los mismos datos.

Si la carpeta de datos está en un sitio que se sincroniza (Drive, OneDrive, Dropbox) o en red, abrir las mismas bases desde dos ordenadores a la vez las puede corromper o crear «copias en conflicto».
El candado es un fichero `conta.lock` en la raíz de la carpeta de datos con quién la tiene (equipo, usuario, proceso, desde cuándo y su última señal). Mientras el programa está abierto renueva su **señal** cada pocos segundos.

- Si no hay candado, o es de este mismo programa, se toma sin más.
- Si es de **este equipo** y su proceso ya no existe, el programa que lo tenía se cerró mal: se toma solo.
- Si es de **otro equipo**, no se abre: se enseña quién lo tiene y desde cuándo. Si de verdad quedó pillado (se apagó el otro equipo, se fue la luz…), se puede **forzar**: se toma el control a sabiendas.
  El programa que lo tenía, si aún estuviera vivo, se entera al renovar su señal y se bloquea él.

Límites que hay que conocer: un fichero sincronizado tarda en llegar al otro equipo (segundos o minutos), así que el candado **no es perfecto**: conviene cerrar Conta y esperar a que
termine la sincronización antes de abrirlo en otro ordenador. Por eso una señal reciente cuenta como «en uso» y una antigua como «posiblemente pillado», pero en ningún caso se toma sin que alguien lo pida.
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

NOMBRE = "conta.lock"
SENAL_CADA = timedelta(seconds=20)            # cada cuánto renueva su señal el programa que tiene el candado
SENAL_RECIENTE = timedelta(minutes=3)         # una señal más reciente que esto = «en uso»
SENAL_ANTIGUA = timedelta(minutes=15)         # una señal más vieja que esto = «posiblemente pillado» (sólo cambia el mensaje: tomarlo siempre lo pide una persona)

LIBRE, MIO, OTRO_EQUIPO, HUERFANO = "libre", "mio", "otro_equipo", "huerfano"


@dataclass
class Titular:
    equipo: str
    usuario: str
    pid: int
    instancia: str
    desde: str
    senal: str

    def hace(self, ahora: datetime) -> timedelta:
        try:
            return ahora - datetime.fromisoformat(self.senal)
        except ValueError:
            return timedelta.max

    def describir(self, ahora: datetime) -> str:
        minutos = self.hace(ahora).total_seconds() / 60
        cuando = "hace un momento" if minutos < 1 else (f"hace {minutos:.0f} min" if minutos < 120 else f"hace {minutos / 60:.0f} h")
        return f"{self.usuario}@{self.equipo} (desde el {datetime.fromisoformat(self.desde):%d/%m/%Y %H:%M}; última señal {cuando})"


def proceso_vivo(pid: int) -> bool:
    """¿Existe ese proceso en este equipo?"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        gestor = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not gestor:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(ctypes.windll.kernel32.GetExitCodeProcess(gestor, ctypes.byref(codigo))) and codigo.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(gestor)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Candado:
    def __init__(self, raiz: Path, *, equipo: str | None = None, usuario: str | None = None, pid: int | None = None, instancia: str | None = None,
                 ahora: Callable[[], datetime] = datetime.now, vivo: Callable[[int], bool] = proceso_vivo):
        self.ruta = Path(raiz) / NOMBRE
        self.equipo = equipo or socket.gethostname()
        try:
            self.usuario = usuario or getpass.getuser()
        except Exception:  # noqa: BLE001 - sin usuario del sistema no se debe impedir abrir
            self.usuario = usuario or "desconocido"
        self.pid = pid if pid is not None else os.getpid()
        self.instancia = instancia or uuid.uuid4().hex
        self.ahora, self.vivo = ahora, vivo

    # ------------------------------------------------------------------ lectura
    def titular(self) -> Titular | None:
        try:
            return Titular(**json.loads(self.ruta.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def estado(self) -> tuple[str, Titular | None]:
        """(LIBRE | MIO | OTRO_EQUIPO | HUERFANO, titular). HUERFANO: es de este equipo y su proceso ya no existe."""
        t = self.titular()
        if t is None:
            return LIBRE, None
        if t.instancia == self.instancia:
            return MIO, t
        if t.equipo == self.equipo and not self.vivo(t.pid):
            return HUERFANO, t
        return OTRO_EQUIPO, t

    def posiblemente_pillado(self, t: Titular) -> bool:
        return t.hace(self.ahora()) > SENAL_ANTIGUA

    def en_uso_reciente(self, t: Titular) -> bool:
        return t.hace(self.ahora()) < SENAL_RECIENTE

    # ------------------------------------------------------------------ escritura
    def _escribir(self, desde: str | None = None) -> None:
        ahora = self.ahora().isoformat(timespec="seconds")
        actual = self.titular()
        t = Titular(self.equipo, self.usuario, self.pid, self.instancia, desde or (actual.desde if actual and actual.instancia == self.instancia else ahora), ahora)
        temporal = self.ruta.with_name(self.ruta.name + f".{self.instancia[:6]}.tmp")
        temporal.write_text(json.dumps(asdict(t), ensure_ascii=False), encoding="utf-8")
        os.replace(temporal, self.ruta)  # el fichero nunca se ve a medias

    def adquirir(self) -> tuple[bool, Titular | None]:
        """Toma el candado si está libre, es mío o quedó huérfano en este equipo. Devuelve (conseguido, titular actual si no)."""
        estado, t = self.estado()
        if estado in (LIBRE, MIO, HUERFANO):
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self._escribir()
            return True, None
        return False, t

    def forzar(self) -> None:
        """Toma el candado aunque lo tenga otro equipo (quien lo tuviera se bloqueará al renovar su señal). Lo decide una persona, a sabiendas."""
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.unlink(missing_ok=True)
        self._escribir()

    def renovar(self) -> bool:
        """Renueva la señal. Si el candado ya no es mío (alguien lo forzó), no lo toca y devuelve False."""
        estado, _ = self.estado()
        if estado != MIO:
            return False
        try:
            self._escribir()
        except OSError:
            return False
        return True

    def liberar(self) -> None:
        """Al cerrar el programa: quita el candado si es mío (si lo forzó otro, no se toca)."""
        if self.estado()[0] == MIO:
            self.ruta.unlink(missing_ok=True)

    def tengo(self) -> bool:
        return self.estado()[0] == MIO
