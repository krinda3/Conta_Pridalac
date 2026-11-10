"""Datos fijos de la ficha de empresa que pide el modelo 390: actividades (IAE) y representantes con poder."""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import ActividadEmpresa, Empresa, RepresentanteEmpresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha

MAX_ACTIVIDADES = 6  # la principal y cinco más
MAX_REPRESENTANTES = 3


def _nif(valor: str | None) -> str:
    return re.sub(r"[\s.-]", "", valor or "").upper()


def guardar_actividades(sesion: Session, empresa: Empresa, filas: Iterable[tuple[str, str, str]]) -> None:
    """Sustituye las actividades por `(descripcion, codigo, epigrafe)`; las líneas del todo vacías se ignoran. La primera es la principal."""
    nuevas = []
    for descripcion, codigo, epigrafe in filas:
        descripcion, codigo, epigrafe = (descripcion or "").strip(), (codigo or "").strip().upper(), (epigrafe or "").strip().upper()
        if not (descripcion or codigo or epigrafe):
            continue
        if not descripcion:
            raise ErrorContable("Actividades: cada línea necesita su descripción")
        if codigo and not re.fullmatch(r"[A-Z0-9]{1,3}", codigo):
            raise ErrorContable(f"Actividades: el código de actividad «{codigo}» son hasta 3 letras o cifras (por ejemplo A03)")
        if epigrafe and not re.fullmatch(r"[A-Z0-9]{1,4}", epigrafe):
            raise ErrorContable(f"Actividades: el epígrafe del IAE «{epigrafe}» son hasta 4 letras o cifras (por ejemplo 8431)")
        nuevas.append(ActividadEmpresa(descripcion=descripcion[:40], codigo=codigo or None, epigrafe=epigrafe or None))
    if len(nuevas) > MAX_ACTIVIDADES:
        raise ErrorContable(f"El 390 admite {MAX_ACTIVIDADES} actividades como máximo (la principal y {MAX_ACTIVIDADES - 1} más)")
    empresa.actividades = [setattr(a, "orden", i) or a for i, a in enumerate(nuevas)]
    sesion.flush()


def guardar_representantes(sesion: Session, empresa: Empresa, filas: Iterable[tuple[str, str, str, str]]) -> None:
    """Sustituye los representantes por `(nombre, nif, fecha_poder, notaria)`; las líneas del todo vacías se ignoran."""
    nuevos = []
    for nombre, nif, fecha_poder, notaria in filas:
        nombre, nif, fecha_poder, notaria = (nombre or "").strip(), _nif(nif), (fecha_poder or "").strip(), (notaria or "").strip()
        if not (nombre or nif or fecha_poder or notaria):
            continue
        if not nombre:
            raise ErrorContable("Representantes: cada línea necesita el nombre y apellidos")
        if not re.fullmatch(r"[A-Z0-9]{9}", nif):
            raise ErrorContable(f"Representantes: el NIF de {nombre} debe tener 9 caracteres")
        try:
            fecha: date | None = parsear_fecha(fecha_poder) if fecha_poder else None
        except ErrorContable as ex:
            raise ErrorContable(f"Representantes: fecha del poder de {nombre}: {ex}") from ex
        nuevos.append(RepresentanteEmpresa(nombre=nombre[:80], nif=nif, fecha_poder=fecha, notaria=notaria[:12] or None))
    if len(nuevos) > MAX_REPRESENTANTES:
        raise ErrorContable(f"El 390 admite {MAX_REPRESENTANTES} representantes como máximo")
    empresa.representantes = [setattr(r, "orden", i) or r for i, r in enumerate(nuevos)]
    sesion.flush()
