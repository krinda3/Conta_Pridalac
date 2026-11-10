"""Copia de seguridad llevada a la carpeta de la empresa (OneDrive): el respaldo del final del trimestre.

Se hace la copia (`servicios/copias.py`: ligera —la base y los documentos irrecuperables, de los PDF de facturas solo su huella—, en un `.zip` verificado de unos pocos MB) en la carpeta local de copias y se lleva a la carpeta elegida por empresa. La copia que llega se
verifica otra vez, ya en su sitio: si no pasa, se borra y se avisa. Una copia está «al día» si es posterior al último cambio de la base de datos.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import copias, huellas


@dataclass
class EstadoCopiaExterna:
    carpeta: Path | None
    ultima: copias.Copia | None = None
    ultimo_cambio: datetime | None = None

    @property
    def al_dia(self) -> bool:
        # la copia anota su hora sin fracciones de segundo: se compara a segundos
        return self.ultima is not None and (self.ultimo_cambio is None or self.ultima.momento >= self.ultimo_cambio.replace(microsecond=0))


def carpeta_de(empresa: Empresa) -> Path | None:
    texto = (empresa.carpeta_copias or "").strip().strip('"')
    return Path(texto) if texto else None


def ultimo_cambio(ruta_bd: Path) -> datetime | None:
    """Cuándo se escribió por última vez en la base de datos (su fichero y, si lo hay, el de su diario)."""
    momentos = [Path(f"{ruta_bd}{sufijo}").stat().st_mtime for sufijo in ("", "-wal") if Path(f"{ruta_bd}{sufijo}").exists()]
    return datetime.fromtimestamp(max(momentos)) if momentos else None


def estado(empresa: Empresa, slug: str, ruta_bd: Path) -> EstadoCopiaExterna:
    """Cuál es la última copia en la carpeta de la empresa y si es posterior al último cambio."""
    carpeta = carpeta_de(empresa)
    if carpeta is None:
        return EstadoCopiaExterna(None)
    try:
        todas = copias.listar_copias(carpeta, slug) if carpeta.is_dir() else []
    except OSError:
        todas = []
    return EstadoCopiaExterna(carpeta, todas[0] if todas else None, ultimo_cambio(Path(ruta_bd)))


def hacer_y_llevar(empresa: Empresa, slug: str, ruta_bd: Path, almacen: Path, carpeta_local: Path) -> tuple[Path, Path]:
    """Hace la copia (verificada) en la carpeta local y la lleva a la carpeta de la empresa, donde se vuelve a verificar. Devuelve (copia local, copia en la carpeta de la empresa)."""
    carpeta = carpeta_de(empresa)
    if carpeta is None:
        raise ErrorContable("La empresa no tiene configurada la carpeta de las copias de seguridad: indíquela en los datos de la empresa")
    local = copias.hacer_copia(slug, ruta_bd, almacen, carpeta_local)
    destino = carpeta / local.name
    parcial = destino.with_suffix(".zip.parcial")
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, parcial)
        os.replace(parcial, destino)
    except OSError as e:
        try:
            parcial.unlink(missing_ok=True)
        except OSError:  # en Linux, si la «carpeta» es en realidad un fichero, ni siquiera se puede intentar borrar dentro de ella
            pass
        raise ErrorContable(f"La copia está hecha en {local}, pero no se pudo llevar a {carpeta}: {e.strerror or e}") from None
    problemas = copias.verificar_copia(destino)
    if problemas:
        destino.unlink(missing_ok=True)
        raise ErrorContable(f"La copia no llegó bien a {carpeta} y se ha borrado (queda la de {local}): " + "; ".join(problemas))
    huellas_de_la_empresa = huellas.ruta_del_fichero(almacen, empresa.codigo)  # las huellas del registro de cambios viajan con la copia, pero aparte de ella
    if huellas_de_la_empresa.is_file():
        try:
            shutil.copyfile(huellas_de_la_empresa, carpeta / huellas_de_la_empresa.name)
        except OSError:
            pass  # es un segundo ejemplar: no impide dar la copia por buena
    return local, destino
