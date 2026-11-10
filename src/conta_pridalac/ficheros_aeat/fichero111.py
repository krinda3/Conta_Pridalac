"""Fichero del modelo 111 (retenciones e ingresos a cuenta del IRPF: trabajo, actividades económicas, premios…) según el diseño de registro oficial (`dr111_v18.json`, de `dr111e16v18.xls`, vigente para 2019 y siguientes).

Una sola página entre `<T11101000>…</T11101000>`, dentro de `<T1110AAAAPP0000>…</T1110AAAAPP0000>`, con la cabecera `<AUX>…</AUX>` de siempre: 328 + 1000 + 18 = 1346 posiciones. ISO-8859-1.
Los campos se identifican por su casilla oficial (01-30): 01-03 trabajo dinerario, 04-06 trabajo en especie, 07-09 actividades económicas dinerarias, 10-12 en especie, 13-15 premios dinerarios, 16-18 premios en especie,
19-21 ganancias por aprovechamientos forestales dinerarias, 22-24 en especie, 25-27 cesión de derechos de imagen, 28 suma de retenciones, 29 resultado de anteriores declaraciones y 30 resultado a ingresar.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable

_RUTA = Path(__file__).with_name("dr111_v18.json")
DISENO = json.loads(_RUTA.read_text(encoding="utf-8"))
DISENO_VERSION = "DR111e16v18"
DISENO_SHA256 = hashlib.sha256(_RUTA.read_bytes()).hexdigest()
CODIFICACION = "latin-1"
CERO = Decimal("0")
NUMERO_DE_PERCEPTORES = {1, 4, 7, 10, 13, 16, 19, 22, 25}  # el resto de casillas son importes
TIPOS = {"I": "Ingreso", "U": "Domiciliación", "G": "Cuenta corriente tributaria (ingreso)", "N": "Negativa / sin actividad"}


@dataclass
class Declaracion111:
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


def _numero(valor: Decimal, lon: int, con_signo: bool, entero: bool) -> str:
    if entero:
        n = int(valor)
        if n < 0:
            raise ErrorContable(f"El número de perceptores no puede ser negativo: {valor}")
        return str(n).rjust(lon, "0")
    centimos = int((abs(Decimal(valor)) * 100).to_integral_value())
    if valor < 0:
        if not con_signo:
            raise ErrorContable(f"Esta casilla no admite negativos: {valor}")
        return "N" + str(centimos).rjust(lon - 1, "0")
    return str(centimos).rjust(lon, "0")


def generar(d: Declaracion111) -> str:
    if d.tipo not in TIPOS:
        raise ErrorContable(f"Tipo de declaración desconocido: {d.tipo!r}")
    if d.tipo == "U" and not d.iban.strip():
        raise ErrorContable("Para domiciliar el pago hace falta el IBAN")
    if d.complementaria and (len(d.justificante_anterior) != 13 or not d.justificante_anterior.isdigit()):
        raise ErrorContable("Una declaración complementaria necesita el nº de justificante (13 dígitos) de la que complementa")
    casillas = {k: v for k, v in d.casillas.items() if v}
    valores = {
        6: d.tipo, 7: d.nif, 8: d.nombre, 10: str(d.ejercicio), 11: d.periodo, 42: "X" if d.complementaria else " ", 43: d.justificante_anterior if d.complementaria else "",
        45: d.iban if d.tipo == "U" else "",
    }
    constantes = {1: "<T", 2: "111", 3: "01", 4: "000>", 48: "</T11101000>"}
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
            partes.append(_numero(casillas.get(c["casilla"], CERO), lon, tipo == "N", c["casilla"] in NUMERO_DE_PERCEPTORES))
        else:
            partes.append(" " * lon)
    sobrantes = sorted(set(casillas) - usadas)
    if sobrantes:
        raise ErrorContable(f"Casillas del 111 que no existen: {sobrantes}")
    aux = "<AUX>" + " " * 70 + d.version_programa.ljust(4) + " " * 4 + d.nif_desarrollador.ljust(9) + " " * 213 + "</AUX>"
    return f"<T1110{d.ejercicio}{d.periodo}0000>" + aux + "".join(partes) + f"</T1110{d.ejercicio}{d.periodo}0000>"


def leer(texto: str) -> dict[int, str]:
    """Campos de la página 01 de un fichero, por número de orden del diseño (para comprobar y depurar)."""
    inicio = texto.find("<T11101000>")
    if inicio < 0:
        raise ErrorContable("El fichero no tiene la página 01 del modelo 111")
    return {c["orden"]: texto[inicio + c["pos"] - 1 : inicio + c["pos"] - 1 + c["lon"]] for c in DISENO}


def casillas_de(texto: str) -> dict[int, Decimal]:
    """Casillas con importe (o número de perceptores) distinto de cero."""
    campos, casillas = leer(texto), {}
    for c in DISENO:
        if c["casilla"] is None:
            continue
        bruto = campos[c["orden"]]
        valor = Decimal(int(bruto)) if c["casilla"] in NUMERO_DE_PERCEPTORES else Decimal(bruto.replace("N", "0")) / 100 * (-1 if bruto.startswith("N") else 1)
        if valor:
            casillas[c["casilla"]] = valor
    return casillas


def contenido_legible(texto: str) -> tuple[list[tuple[str, str]], dict[int, Decimal]]:
    """Lo que lleva un fichero, para enseñarlo: (datos de identificación, casillas con importe)."""
    c = leer(texto)
    datos = [("Tipo de declaración", c[6].strip()), ("NIF", c[7].strip()), ("Razón social", c[8].strip()), ("Ejercicio y periodo", f"{c[10].strip()} {c[11].strip()}")]
    if c[42].strip():
        datos += [("Declaración complementaria", "sí"), ("Justificante de la anterior", c[43].strip())]
    if c[45].strip():
        datos.append(("IBAN", c[45].strip()))
    return datos, dict(sorted(casillas_de(texto).items()))
