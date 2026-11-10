"""Fichero del modelo 115 (retenciones e ingresos a cuenta del IRPF/IS por arrendamientos de inmuebles urbanos) según el diseño de registro oficial (`dr115_v13.json`, de `DR115e15v13.xls`, vigente para 2019 y siguientes).

Una sola página entre `<T11501000>…</T11501000>`, dentro de `<T1150AAAAPP0000>…</T1150AAAAPP0000>`, con la cabecera `<AUX>…</AUX>` de siempre: 328 + 500 + 18 = 846 posiciones. ISO-8859-1.
Casillas oficiales: 01 número de perceptores (arrendadores) · 02 base de las retenciones e ingresos a cuenta · 03 retenciones e ingresos a cuenta · 04 resultado de anteriores declaraciones · 05 resultado a ingresar (03 − 04).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable

_RUTA = Path(__file__).with_name("dr115_v13.json")
DISENO = json.loads(_RUTA.read_text(encoding="utf-8"))
DISENO_VERSION = "DR115e15v13"
DISENO_SHA256 = hashlib.sha256(_RUTA.read_bytes()).hexdigest()
CODIFICACION = "latin-1"
CERO = Decimal("0")
NUMERO_DE_PERCEPTORES = {1}  # el resto de casillas son importes
TIPOS = {"I": "Ingreso", "U": "Domiciliación", "G": "Cuenta corriente tributaria (ingreso)", "N": "Negativa / sin actividad"}


@dataclass
class Declaracion115:
    nif: str
    nombre: str
    ejercicio: int
    periodo: str  # "1T".."4T" (o "01".."12" si fuera mensual)
    tipo: str  # I ingreso · U domiciliación · G cuenta corriente tributaria · N negativa / sin actividad
    casillas: dict[int, Decimal] = field(default_factory=dict)
    iban: str = ""
    complementaria: bool = False
    justificante_anterior: str = ""  # nº de justificante (13) de la declaración que se complementa
    version_programa: str = ""  # AUX: versión del programa y NIF de quien lo desarrolla (en blanco)
    nif_desarrollador: str = ""


def _numero(valor: Decimal, lon: int, entero: bool) -> str:
    if valor < 0:
        raise ErrorContable(f"Esta casilla no admite negativos: {valor}")
    if entero:
        return str(int(valor)).rjust(lon, "0")
    return str(int((Decimal(valor) * 100).to_integral_value())).rjust(lon, "0")


def generar(d: Declaracion115) -> str:
    if d.tipo not in TIPOS:
        raise ErrorContable(f"Tipo de declaración desconocido: {d.tipo!r}")
    if d.tipo == "U" and not d.iban.strip():
        raise ErrorContable("Para domiciliar el pago hace falta el IBAN")
    if d.complementaria and (len(d.justificante_anterior) != 13 or not d.justificante_anterior.isdigit()):
        raise ErrorContable("Una declaración complementaria necesita el nº de justificante (13 dígitos) de la que complementa")
    casillas = {k: v for k, v in d.casillas.items() if v}
    valores = {6: d.tipo, 7: d.nif, 8: d.nombre, 10: str(d.ejercicio), 11: d.periodo, 17: "X" if d.complementaria else " ", 18: d.justificante_anterior if d.complementaria else "", 19: d.iban if d.tipo == "U" else ""}
    constantes = {1: "<T", 2: "115", 3: "01", 4: "000>", 22: "</T11501000>"}
    usadas: set[int] = set()
    partes = []
    for c in DISENO:
        n, lon, tipo = c["orden"], c["lon"], c["tipo"]
        if n in constantes:
            partes.append(constantes[n])
        elif n in valores:
            v = valores[n]
            if len(v) > lon:
                raise ErrorContable(f"Valor demasiado largo para un campo de {lon} posiciones: {v!r}")
            partes.append(v.rjust(lon, "0") if tipo == "Num" else v.ljust(lon))
        elif c["casilla"] is not None:
            if c["casilla"] in casillas:
                usadas.add(c["casilla"])
            partes.append(_numero(casillas.get(c["casilla"], CERO), lon, c["casilla"] in NUMERO_DE_PERCEPTORES))
        else:
            partes.append(" " * lon)
    sobrantes = sorted(set(casillas) - usadas)
    if sobrantes:
        raise ErrorContable(f"Casillas del 115 que no existen: {sobrantes}")
    aux = "<AUX>" + " " * 70 + d.version_programa.ljust(4) + " " * 4 + d.nif_desarrollador.ljust(9) + " " * 213 + "</AUX>"
    return f"<T1150{d.ejercicio}{d.periodo}0000>" + aux + "".join(partes) + f"</T1150{d.ejercicio}{d.periodo}0000>"


def leer(texto: str) -> dict[int, str]:
    """Campos de la página 01 de un fichero, por número de orden del diseño (para comprobar y depurar)."""
    inicio = texto.find("<T11501000>")
    if inicio < 0:
        raise ErrorContable("El fichero no tiene la página 01 del modelo 115")
    return {c["orden"]: texto[inicio + c["pos"] - 1 : inicio + c["pos"] - 1 + c["lon"]] for c in DISENO}


def casillas_de(texto: str) -> dict[int, Decimal]:
    """Casillas con importe (o número de perceptores) distinto de cero."""
    campos, casillas = leer(texto), {}
    for c in DISENO:
        if c["casilla"] is None:
            continue
        bruto = campos[c["orden"]]
        valor = Decimal(int(bruto)) if c["casilla"] in NUMERO_DE_PERCEPTORES else Decimal(int(bruto)) / 100
        if valor:
            casillas[c["casilla"]] = valor
    return casillas


def contenido_legible(texto: str) -> tuple[list[tuple[str, str]], dict[int, Decimal]]:
    """Lo que lleva un fichero, para enseñarlo: (datos de identificación, casillas con importe)."""
    c = leer(texto)
    datos = [("Tipo de declaración", c[6].strip()), ("NIF", c[7].strip()), ("Razón social", c[8].strip()), ("Ejercicio y periodo", f"{c[10].strip()} {c[11].strip()}")]
    if c[17].strip():
        datos += [("Declaración complementaria", "sí"), ("Justificante de la anterior", c[18].strip())]
    if c[19].strip():
        datos.append(("IBAN", c[19].strip()))
    return datos, dict(sorted(casillas_de(texto).items()))
