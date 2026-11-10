"""Preferencias de pantalla (tema, disposición del menú, última caja abierta, cómo se muestran las explicaciones).

Se guardan en un fichero junto a las bases de datos, no en el navegador: así no se pierden si el navegador borra los datos de los sitios al cerrarse
ni dependen de qué navegador o perfil se use para abrir el programa.
"""
from __future__ import annotations

import json
from pathlib import Path

from conta_pridalac.web.config import Configuracion
from conta_pridalac.web.definiciones import CAJAS

DEFECTO = {"tema": "auto", "menu": "horizontal", "caja": "", "ayudas": "tooltip"}
VALORES = {"tema": {"auto", "light", "dark"}, "menu": {"horizontal", "vertical"}, "caja": {""} | {c[0] for c in CAJAS}, "ayudas": {"tooltip", "visibles"}}


def _ruta(config: Configuracion) -> Path:
    return config.datos / "_preferencias.json"


def leer(config: Configuracion) -> dict[str, str]:
    """Las preferencias guardadas; lo que falta o no es válido vale el valor por defecto."""
    try:
        guardadas = json.loads(_ruta(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guardadas = {}
    return {k: (guardadas.get(k) if guardadas.get(k) in VALORES[k] else v) for k, v in DEFECTO.items()}


def guardar(config: Configuracion, clave: str, valor: str) -> dict[str, str]:
    if clave not in VALORES or valor not in VALORES[clave]:
        raise ValueError(f"Preferencia no válida: {clave} = {valor!r}")
    actuales = leer(config)
    actuales[clave] = valor
    ruta = _ruta(config)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(actuales, ensure_ascii=False, indent=2), encoding="utf-8")
    return actuales
