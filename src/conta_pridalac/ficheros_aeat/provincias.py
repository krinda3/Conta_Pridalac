"""Códigos de provincia de la AEAT (los de los modelos 190 y 347) y su nombre: de un código postal, de un nombre escrito a mano o de un código ya presentado."""
from __future__ import annotations

import re
import unicodedata

# código → nombre con el que se guarda en la ficha del tercero
PROVINCIAS = {
    "01": "ÁLAVA", "02": "ALBACETE", "03": "ALICANTE", "04": "ALMERÍA", "05": "ÁVILA", "06": "BADAJOZ", "07": "ILLES BALEARS", "08": "BARCELONA", "09": "BURGOS", "10": "CÁCERES", "11": "CÁDIZ",
    "12": "CASTELLÓN", "13": "CIUDAD REAL", "14": "CÓRDOBA", "15": "A CORUÑA", "16": "CUENCA", "17": "GIRONA", "18": "GRANADA", "19": "GUADALAJARA", "20": "GUIPÚZCOA", "21": "HUELVA", "22": "HUESCA",
    "23": "JAÉN", "24": "LEÓN", "25": "LLEIDA", "26": "LA RIOJA", "27": "LUGO", "28": "MADRID", "29": "MÁLAGA", "30": "MURCIA", "31": "NAVARRA", "32": "OURENSE", "33": "ASTURIAS", "34": "PALENCIA",
    "35": "LAS PALMAS", "36": "PONTEVEDRA", "37": "SALAMANCA", "38": "SANTA CRUZ DE TENERIFE", "39": "CANTABRIA", "40": "SEGOVIA", "41": "SEVILLA", "42": "SORIA", "43": "TARRAGONA", "44": "TERUEL",
    "45": "TOLEDO", "46": "VALENCIA", "47": "VALLADOLID", "48": "VIZCAYA", "49": "ZAMORA", "50": "ZARAGOZA", "51": "CEUTA", "52": "MELILLA", "53": "ISLA DE LA PALMA",
}
ALIAS = {
    "ARABA": "01", "ALAVA": "01", "ALACANT": "03", "BALEARES": "07", "ISLAS BALEARES": "07", "CASTELLO": "12", "CASTELLON DE LA PLANA": "12", "CORUNA": "15", "LA CORUNA": "15", "CORUNA A": "15",
    "GIPUZKOA": "20", "RIOJA": "26", "RIOJA LA": "26", "PALMAS": "35", "PALMAS LAS": "35", "GRAN CANARIA": "35", "TENERIFE": "38", "S C TENERIFE": "38", "SC TENERIFE": "38", "BIZKAIA": "48",
    "PRINCIPADO DE ASTURIAS": "33", "OVIEDO": "33", "GERONA": "17", "LERIDA": "25", "ORENSE": "32", "LA PALMA": "53",
}


def _normal(texto: str) -> str:
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", sin_acentos)).strip()


_POR_NOMBRE = {_normal(nombre): codigo for codigo, nombre in PROVINCIAS.items()} | {_normal(a): c for a, c in ALIAS.items()}


def codigo_de_provincia(codigo_postal: str | None = None, nombre: str | None = None) -> str | None:
    """El código de dos cifras: de los dos primeros dígitos del código postal si es de 5 cifras y de una provincia real; si no, del nombre (con o sin acentos, «Alicante/Alacant»…)."""
    cp = (codigo_postal or "").strip()
    if len(cp) == 5 and cp.isdigit() and cp[:2] in PROVINCIAS:
        return cp[:2]
    texto = _normal(nombre or "")
    if not texto:
        return None
    if texto in _POR_NOMBRE:
        return _POR_NOMBRE[texto]
    for parte in re.split(r"\s*/\s*", (nombre or "").upper()):  # «Alicante/Alacant», «Vizcaya/Bizkaia»
        if _normal(parte) in _POR_NOMBRE:
            return _POR_NOMBRE[_normal(parte)]
    return None
