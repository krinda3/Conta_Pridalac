"""Fichero del modelo 200 (Impuesto sobre Sociedades) según el diseño de registro oficial (`dr200_2025.json`, salido de `DR200e25.xls`, v1.02).

El fichero es una sola cadena (sin saltos de línea) en ISO-8859-1: la cabecera `<T200…><AUX>…</AUX>` (328 posiciones), las páginas en el orden del diseño y el cierre `</T200…>`.
Cada página es `<T200ppppp>` + campos de posición fija + `</T200ppppp>`; todas miden siempre lo mismo (la lista de campos del diseño las cubre sin huecos).

Aquí está sólo el **formato**: leer y escribir páginas y campos. Qué páginas lleva cada declaración y con qué valores se decide en `servicios/impuesto_sociedades_200.py`.
Un fichero de otro ejercicio no se lee con este diseño (las páginas miden otra cosa): cada año tiene su `dr200_AAAA.json`.

Tipos de campo: `N` importe de 17 posiciones en céntimos, con una `N` en la primera si es negativo; `Num` dígitos con ceros a la izquierda (si son 17 y llevan casilla, un importe sin signo);
`A` y `An` texto alineado a la izquierda con blancos a la derecha.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero303 import _campo, _numero

RUTA_DISENO = Path(__file__).with_name("dr200_2025.json")
DISENO = json.loads(RUTA_DISENO.read_text(encoding="utf-8"))
DISENO_VERSION = "DR200e25v102"
DISENO_SHA256 = hashlib.sha256(RUTA_DISENO.read_bytes()).hexdigest()
CODIFICACION = "latin-1"
EJERCICIO = 2025
LONGITUD_CABECERA = 328
POS_COMPLEMENTARIA = 12  # «Indicador de página complementaria» (campo 5): en blanco, o marca de que la página repite la anterior
ORDEN = {codigo: i for i, (codigo, _) in enumerate(sorted(DISENO["paginas"].items(), key=lambda kv: kv[1]["hoja"]))}  # el orden de las hojas es el de las páginas en el fichero

_CAMPOS: dict[str, dict[int, dict]] = {cod: {c["n"]: c for c in p["campos"]} for cod, p in DISENO["paginas"].items()}
_LONGITUD = {cod: max(c["pos"] + c["lon"] for c in campos.values()) - 1 for cod, campos in _CAMPOS.items()}
_CASILLAS: dict[str, dict[str, list[int]]] = {}
for _cod, _campos in _CAMPOS.items():
    _CASILLAS[_cod] = {}
    for _n, _c in _campos.items():
        if _c["casilla"]:
            _CASILLAS[_cod].setdefault(_c["casilla"], []).append(_n)


def _constante(campo: dict) -> str | None:
    """El valor fijo de un campo (`Constante "<T"`), si lo tiene y cabe exactamente en su longitud."""
    cont = campo.get("contenido") or ""
    if not cont.startswith("Constante"):
        return None
    valor = cont[len("Constante"):].strip().strip('"')
    return valor if len(valor) == campo["lon"] else None


def paginas_del_diseno() -> list[str]:
    return sorted(DISENO["paginas"], key=ORDEN.__getitem__)


def longitud_de_pagina(codigo: str) -> int:
    return _LONGITUD[codigo]


@dataclass
class Pagina:
    codigo: str
    valores: dict[int, str] = field(default_factory=dict)  # nº de campo → texto de su longitud exacta

    @classmethod
    def nueva(cls, codigo: str, complementaria: bool = False) -> Pagina:
        """Una página en blanco: las constantes puestas, los textos en blanco y los importes y números a cero."""
        if codigo not in _CAMPOS:
            raise ErrorContable(f"La página {codigo} no está en el diseño del modelo 200 de {EJERCICIO}")
        valores = {}
        for n, c in _CAMPOS[codigo].items():
            fijo = _constante(c)
            if fijo is not None:
                valores[n] = fijo
            elif c["tipo"] in ("N", "Num"):
                valores[n] = "0" * c["lon"]
            else:
                valores[n] = " " * c["lon"]
        ultimo = max(_CAMPOS[codigo].items(), key=lambda kv: kv[1]["pos"])  # el último campo de toda página es su etiqueta de cierre (en algunas hojas no figura como constante)
        if ultimo[1]["lon"] == len(f"</T200{codigo}>"):
            valores[ultimo[0]] = f"</T200{codigo}>"
        pagina = cls(codigo, valores)
        if complementaria:
            pagina.valores[5] = "C"[: _CAMPOS[codigo][5]["lon"]]
        return pagina

    @property
    def complementaria(self) -> bool:
        return self.valores[5].strip() != ""

    def _campo(self, n: int) -> dict:
        try:
            return _CAMPOS[self.codigo][n]
        except KeyError:
            raise ErrorContable(f"La página {self.codigo} no tiene el campo {n}") from None

    def n_de_casilla(self, casilla: int | str) -> int:
        """El número de campo de una casilla (`562` → el campo de la cuota íntegra). Si la casilla está repetida en la página (tablas de filas), da error: usar el nº de campo."""
        nombre = f"{int(casilla):05d}"
        ns = _CASILLAS[self.codigo].get(nombre, [])
        if len(ns) != 1:
            raise ErrorContable(f"La casilla {nombre} {'no está' if not ns else 'está repetida'} en la página {self.codigo}")
        return ns[0]

    def texto(self, n: int) -> str:
        return self.valores[n].rstrip()

    def poner_texto(self, n: int, valor: str) -> None:
        c = self._campo(n)
        if c["tipo"] not in ("A", "An"):
            raise ErrorContable(f"El campo {n} de la página {self.codigo} no es de texto ({c['tipo']})")
        try:
            valor.encode(CODIFICACION)
        except UnicodeEncodeError:
            raise ErrorContable(f"El campo {n} de la página {self.codigo} lleva caracteres que el fichero no admite: {valor!r}") from None
        self.valores[n] = _campo(valor, c["lon"], c["tipo"])

    def importe(self, n: int) -> Decimal:
        c, v = self._campo(n), self.valores[n]
        if c["tipo"] == "N":
            return (-Decimal(v[1:]) if v.startswith("N") else Decimal(v)) / 100
        if c["tipo"] == "Num":
            return Decimal(v) / 100
        raise ErrorContable(f"El campo {n} de la página {self.codigo} no es un importe ({c['tipo']})")

    def poner_importe(self, n: int, valor: Decimal | int | str) -> None:
        """Un importe en euros (con céntimos). Los `Num` no admiten negativos."""
        c = self._campo(n)
        if c["tipo"] not in ("N", "Num"):
            raise ErrorContable(f"El campo {n} de la página {self.codigo} no es numérico ({c['tipo']})")
        self.valores[n] = _numero(Decimal(valor), c["lon"], c["tipo"] == "N")

    def numero(self, n: int) -> int:
        return int(self.valores[n])

    def poner_numero(self, n: int, valor: int) -> None:
        """Un número entero (año, mes, código, 0/1/2 de las casillas marcables…) con ceros a la izquierda."""
        c = self._campo(n)
        if c["tipo"] not in ("N", "Num") or valor < 0:
            raise ErrorContable(f"El campo {n} de la página {self.codigo} no admite el número {valor}")
        self.valores[n] = _campo(str(valor), c["lon"], "Num")

    def escribir(self) -> str:
        salida = "".join(self.valores[n] for n, _ in sorted(_CAMPOS[self.codigo].items(), key=lambda kv: kv[1]["pos"]))
        if len(salida) != _LONGITUD[self.codigo]:
            raise ErrorContable(f"La página {self.codigo} mide {len(salida)} y debe medir {_LONGITUD[self.codigo]}")
        return salida

    @classmethod
    def leer(cls, codigo: str, texto: str) -> Pagina:
        if codigo not in _CAMPOS:
            raise ErrorContable(f"La página {codigo} no está en el diseño del modelo 200 de {EJERCICIO}")
        if len(texto) != _LONGITUD[codigo]:
            raise ErrorContable(f"La página {codigo} mide {len(texto)} y el diseño del modelo 200 de {EJERCICIO} dice {_LONGITUD[codigo]}: no es de este ejercicio")
        return cls(codigo, {n: texto[c["pos"] - 1: c["pos"] - 1 + c["lon"]] for n, c in _CAMPOS[codigo].items()})


@dataclass
class Fichero200:
    ejercicio: int = EJERCICIO
    periodo: str = "0A"
    discriminante: str = "0"  # «0» normal, abreviado y PYMES; «A» aseguradoras…
    version_programa: str = ""  # AUX: versión del programa y NIF de quien lo desarrolla (se dejan en blanco)
    nif_desarrollador: str = ""
    paginas: list[Pagina] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list, compare=False)  # lo que el generador quiere que se sepa (no se escribe en el fichero)

    @property
    def etiqueta(self) -> str:
        return f"T200{self.discriminante}{self.ejercicio:04d}{self.periodo}0000"

    def cabecera(self) -> str:
        texto = f"<{self.etiqueta}>" + "<AUX>" + " " * 70 + _campo(self.version_programa, 4, "An") + " " * 4 + _campo(self.nif_desarrollador, 9, "An") + " " * 213 + "</AUX>"
        if len(texto) != LONGITUD_CABECERA:
            raise ErrorContable(f"La cabecera mide {len(texto)} y debe medir {LONGITUD_CABECERA}")
        return texto

    def escribir(self) -> str:
        if self.ejercicio != EJERCICIO:
            raise ErrorContable(f"Este diseño es el del ejercicio {EJERCICIO}, no el {self.ejercicio}")
        previa = -1
        for p in self.paginas:
            orden = ORDEN.get(p.codigo)
            if orden is None or orden < previa:
                raise ErrorContable(f"La página {p.codigo} está fuera del orden del diseño")
            previa = orden
        return self.cabecera() + "".join(p.escribir() for p in self.paginas) + f"</{self.etiqueta}>"

    @classmethod
    def leer(cls, texto: str) -> Fichero200:
        m = re.match(r"<T200(.)(\d{4})(\w\w)0000><AUX>", texto)
        if not m or len(texto) < LONGITUD_CABECERA or texto[LONGITUD_CABECERA - 6: LONGITUD_CABECERA] != "</AUX>":
            raise ErrorContable("No es un fichero del modelo 200: falta la cabecera")
        fichero = cls(ejercicio=int(m.group(2)), periodo=m.group(3), discriminante=m.group(1), version_programa=texto[92:96].rstrip(), nif_desarrollador=texto[100:109].rstrip())
        if fichero.ejercicio != EJERCICIO:
            raise ErrorContable(f"El fichero es del ejercicio {fichero.ejercicio} y este diseño es el del {EJERCICIO}")
        cierre = f"</{fichero.etiqueta}>"
        if not texto.endswith(cierre):
            raise ErrorContable("Al fichero le falta el cierre " + cierre)
        pos, fin = LONGITUD_CABECERA, len(texto) - len(cierre)
        while pos < fin:
            etiqueta = re.match(r"<T200(\w{5})>", texto[pos:pos + 11])
            if not etiqueta:
                raise ErrorContable(f"Se esperaba una página en la posición {pos + 1} del fichero")
            codigo = etiqueta.group(1)
            if codigo not in _LONGITUD:
                raise ErrorContable(f"La página {codigo} no está en el diseño del modelo 200 de {EJERCICIO}")
            pagina = texto[pos: pos + _LONGITUD[codigo]]
            if len(pagina) != _LONGITUD[codigo] or not pagina.endswith(f"</T200{codigo}>"):
                raise ErrorContable(f"La página {codigo} no mide lo que dice el diseño ({_LONGITUD[codigo]}): no es de este ejercicio")
            fichero.paginas.append(Pagina.leer(codigo, pagina))
            pos += _LONGITUD[codigo]
        return fichero
