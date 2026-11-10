"""Configuración de la aplicación web: dónde están las bases de datos (una SQLite por empresa) y el almacén de justificantes."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.servicios import ubicacion_datos
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos

RAIZ_PROYECTO = Path(__file__).resolve().parents[3]


@dataclass
class Configuracion:
    """`datos`: carpeta con una base `<empresa>.sqlite` por empresa. `motores`: bases ya abiertas (tests), por nombre."""

    datos: Path = field(default_factory=lambda: ubicacion_datos.resolver()[0])  # la variable CONTA_DATOS, la ubicación guardada o `datos_locales/bd` (véase `servicios/ubicacion_datos.py`)
    almacen: Path | None = None
    copias: Path | None = None  # carpeta de las copias de seguridad (por defecto `datos_locales/copias`)
    descargas: Path | None = None  # carpeta a la que se copian los ficheros para presentar (por defecto `Descargas\\Conta Pridalac`)
    motores: dict[str, Engine] = field(default_factory=dict)
    exigir_certificado: bool = False  # True (lo activa `python -m conta_pridalac.web`): las empresas anteriores sin protección elegida y sin certificado sólo abren su ficha
    usar_candado: bool = False  # True (lo activa `python -m conta_pridalac.web`): la carpeta de datos lleva un candado para no abrirla desde dos equipos a la vez (`servicios/candado.py`)

    def __post_init__(self):
        self.datos = Path(self.datos)
        if self.almacen is None:
            self.almacen = Path(os.environ.get("CONTA_ALMACEN", self.datos.parent / "justificantes"))
        if self.copias is None:
            self.copias = Path(os.environ.get("CONTA_COPIAS", self.datos.parent / "copias"))
        self.copias = Path(self.copias)
        if self.descargas is None:
            from conta_pridalac.servicios.exportar import carpeta_para_presentar

            self.descargas = carpeta_para_presentar()
        self.descargas = Path(self.descargas)

    @property
    def raiz(self) -> Path:
        """La carpeta de datos: la que contiene `bd`, `justificantes` y `copias`."""
        return self.datos.parent

    def cambiar_raiz(self, raiz: Path) -> None:
        """Pasa a usar otra carpeta de datos sin reiniciar: cierra las bases abiertas y apunta a `bd`, `justificantes` y `copias` de la nueva."""
        for motor in list(self.motores.values()):
            motor.dispose()
        self.motores.clear()
        raiz = Path(raiz)
        self.datos, self.almacen, self.copias = raiz / "bd", raiz / "justificantes", raiz / "copias"

    def empresas(self) -> list[str]:
        """Nombres (sin extensión) de las empresas disponibles."""
        en_disco = {p.stem for p in self.datos.glob("*.sqlite")} if self.datos.is_dir() else set()
        return sorted(en_disco | set(self.motores))

    def motor(self, slug: str) -> Engine:
        if slug not in self.motores:
            ruta = self.datos / f"{slug}.sqlite"
            if not ruta.is_file():
                raise KeyError(slug)
            self.motores[slug] = crear_motor(ruta)
            crear_esquema(self.motores[slug])  # añade tablas nuevas si la base es anterior; no toca las existentes
        return self.motores[slug]

    def sesion(self, slug: str) -> Session:
        return nueva_sesion(self.motor(slug))

    def almacen_de_adjuntos(self) -> AlmacenAdjuntos:
        return AlmacenAdjuntos(self.almacen)
