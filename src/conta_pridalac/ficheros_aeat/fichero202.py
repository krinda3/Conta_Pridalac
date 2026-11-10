"""Fichero del modelo 202 (pago fraccionado del Impuesto sobre Sociedades, modalidad del art. 40.2 LIS) según el diseño de registro oficial
(`dr202_2025.json`, salido de `DR202e25.xlsx`, «202 - Ejercicio 2025 y siguientes», v1.3).

Dos páginas de posiciones fijas, `<T20201000>…</T20201000>` (identificación y liquidación: 700 posiciones) y `<T20202000>…</T20202000>` (complementaria y domiciliación: 900), dentro de
`<T2020AAAAPP0000>…</T2020AAAAPP0000>` y con la cabecera `<AUX>`. Codificación ISO-8859-1, sin saltos de línea. Sólo se rellena la liquidación de la modalidad A (art. 40.2 LIS): base [01],
resultado de la declaración anterior [02] (sólo en una complementaria) y a ingresar [03]; la modalidad B (art. 40.3, empresas de más de 10 millones de cifra de negocios) no se genera.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero303 import _campo, _constante, _numero

RUTA_DISENO = Path(__file__).with_name("dr202_2025.json")
DISENO = json.loads(RUTA_DISENO.read_text(encoding="utf-8"))
CODIFICACION = "latin-1"
DISENO_VERSION = "dr202e25"
DISENO_SHA256 = hashlib.sha256(RUTA_DISENO.read_bytes()).hexdigest()
PAGINAS = {"01000": "dr M202 (1)", "02000": "dr M202 (2)"}
CERO = Decimal("0")
TIPOS_DECLARACION = {"I": "ingreso", "U": "domiciliación", "G": "ingreso en CCT", "N": "negativa o resultado cero"}
PORCENTAJE = Decimal("0.18")  # 5/7 del tipo general del 25 %, redondeado por exceso (art. 40.2 LIS)

# posiciones de la página 1
POS_TIPO, POS_NIF, POS_NOMBRE, POS_EJERCICIO, POS_PERIODO, POS_INICIO, POS_CNAE = 13, 14, 23, 104, 108, 110, 118
POS_CIFRA_MENOR_1M, POS_TIPO_GRAVAMEN, POS_MODALIDAD = 130, 132, 148
CASILLA_BASE, CASILLA_ANTERIOR, CASILLA_A_INGRESAR = 1, 2, 3
# posiciones de la página 2
POS_COMPLEMENTARIA, POS_JUSTIFICANTE_ANTERIOR, POS_IBAN = 712, 713, 726


@dataclass
class Declaracion202:
    nif: str
    nombre: str
    ejercicio: int
    periodo: int  # 1, 2 o 3
    inicio: date  # primer día del periodo impositivo (el 1 de enero en un ejercicio natural)
    base: Decimal  # casilla [01]
    a_ingresar: Decimal  # casilla [03]
    tipo: str = "N"  # I, U, G o N
    tipo_gravamen: str = "25"
    cifra_menor_1m: bool = True  # importe neto de la cifra de negocios del periodo anterior inferior a un millón de euros
    cnae: str = ""
    iban: str = ""
    complementaria: bool = False
    justificante_anterior: str = ""
    resultado_anterior: Decimal = CERO  # casilla [02]: lo ingresado en la declaración que se complementa
    version_programa: str = ""  # AUX: versión del programa y NIF de quien lo desarrolló (se dejan en blanco)
    nif_desarrollador: str = ""


def _texto_aeat(valor: str, largo: int) -> str:
    """Campo alfanumérico de la AEAT: mayúsculas y sin acentos (la Ñ y la Ç se conservan)."""
    resultado = []
    for caracter in unicodedata.normalize("NFC", (valor or "").upper()):
        if caracter in "ÑÇ":
            resultado.append(caracter)
            continue
        resultado.append("".join(c for c in unicodedata.normalize("NFD", caracter) if unicodedata.category(c) != "Mn"))
    return "".join(resultado)[:largo]


def pago(base: Decimal) -> Decimal:
    """El pago fraccionado: el 18 % de la base, al céntimo."""
    return (max(base, CERO) * PORCENTAJE).quantize(Decimal("0.01"))


def _pagina(clave: str, valores_posicion: dict[int, str], casillas: dict[int, Decimal]) -> str:
    partes = []
    for c in DISENO[PAGINAS[clave]]:
        pos, lon, tipo = c["pos"], c["lon"], c["tipo"]
        constante = _constante(c["contenido"])
        if pos in valores_posicion:
            partes.append(_campo(valores_posicion[pos], lon, tipo))
        elif constante is not None and lon == len(constante):
            partes.append(constante)
        elif c["casilla"] is not None and tipo.upper() in ("NUM", "N") and c["casilla"] in casillas:
            partes.append(_numero(casillas[c["casilla"]], lon, tipo.upper() == "N"))
        elif tipo.upper() in ("A", "AN"):
            partes.append(" " * lon)
        else:
            partes.append("0" * lon)
    return "".join(partes)


def _validar(d: Declaracion202) -> None:
    if d.periodo not in (1, 2, 3):
        raise ErrorContable("El 202 tiene tres pagos fraccionados: periodo 1 a 3")
    if d.tipo not in TIPOS_DECLARACION:
        raise ErrorContable(f"Tipo de declaración desconocido: {d.tipo}")
    if d.tipo == "N" and d.a_ingresar != 0:
        raise ErrorContable("Una declaración negativa (tipo N) no puede tener importe a ingresar")
    if d.tipo != "N" and d.a_ingresar == 0:
        raise ErrorContable("Con importe cero la declaración es de tipo N (negativa o resultado cero)")
    if d.tipo in ("U", "G") and not re.fullmatch(r"ES\d{22}", d.iban or ""):
        raise ErrorContable("Para domiciliar el pago hace falta un IBAN español (ES y 22 dígitos)")
    if d.complementaria and not re.fullmatch(r"\d{13}", d.justificante_anterior or ""):
        raise ErrorContable("Una declaración complementaria necesita el nº de justificante (13 dígitos) de la que complementa")
    if d.cnae and not re.fullmatch(r"\d{4}", d.cnae):
        raise ErrorContable("El CNAE son cuatro dígitos")


def generar(d: Declaracion202) -> str:
    """Fichero completo (texto) de la declaración."""
    _validar(d)
    p1 = {
        POS_TIPO: d.tipo, POS_NIF: d.nif, POS_NOMBRE: _texto_aeat(d.nombre, 60), POS_EJERCICIO: str(d.ejercicio), POS_PERIODO: f"{d.periodo}P", POS_INICIO: d.inicio.strftime("%d%m%Y"),
        POS_TIPO_GRAVAMEN: _texto_aeat(d.tipo_gravamen, 15), POS_MODALIDAD: "A",
    }
    if d.cnae:
        p1[POS_CNAE] = d.cnae
    if d.cifra_menor_1m:
        p1[POS_CIFRA_MENOR_1M] = "X"
    p2 = {}
    if d.tipo in ("U", "G"):
        p2[POS_IBAN] = d.iban
    if d.complementaria:
        p2[POS_COMPLEMENTARIA], p2[POS_JUSTIFICANTE_ANTERIOR] = "X", d.justificante_anterior
    casillas = {CASILLA_BASE: d.base, CASILLA_ANTERIOR: d.resultado_anterior, CASILLA_A_INGRESAR: d.a_ingresar}
    cuerpo = _pagina("01000", p1, casillas) + _pagina("02000", p2, {})
    cabecera = f"<T2020{d.ejercicio}{d.periodo}P0000>"
    aux = "<AUX>" + " " * 70 + d.version_programa.ljust(4) + " " * 4 + d.nif_desarrollador.ljust(9) + " " * 213 + "</AUX>"
    return cabecera + aux + cuerpo + f"</T2020{d.ejercicio}{d.periodo}P0000>"


def leer(texto: str) -> dict[str, dict[int, str]]:
    """Descompone un fichero en páginas {posición: texto del campo} según el diseño (para comprobar y para depurar)."""
    paginas = {}
    for clave, hoja in PAGINAS.items():
        inicio = texto.find(f"<T202{clave}>")
        if inicio < 0:
            continue
        paginas[clave] = {c["pos"]: texto[inicio + c["pos"] - 1 : inicio + c["pos"] - 1 + c["lon"]] for c in DISENO[hoja]}
    return paginas


def datos_del_fichero(texto: str) -> dict:
    """Lo que lleva un fichero `.202`, para importar lo ya presentado y para comprobar lo que se ha generado."""
    cabecera = re.match(r"<T2020(\d{4})(\dP)0000>", texto)
    if cabecera is None:
        raise ErrorContable("No es un fichero del modelo 202")
    p1, p2 = leer(texto)["01000"], leer(texto).get("02000", {})
    importe = lambda s: (Decimal(s) / 100).quantize(Decimal("0.01"))  # noqa: E731
    return {
        "ejercicio": int(cabecera.group(1)), "periodo": int(cabecera.group(2)[0]), "tipo": p1[POS_TIPO], "nif": p1[POS_NIF].strip(), "nombre": p1[POS_NOMBRE].strip(),
        "inicio": date(int(p1[POS_INICIO][4:]), int(p1[POS_INICIO][2:4]), int(p1[POS_INICIO][:2])) if int(p1[POS_INICIO]) else None, "tipo_gravamen": p1[POS_TIPO_GRAVAMEN].strip(), "modalidad": p1[POS_MODALIDAD],
        "base": importe(p1[149]), "resultado_anterior": importe(p1[166]), "a_ingresar": importe(p1[183]), "iban": p2.get(POS_IBAN, "").strip(), "complementaria": p2.get(POS_COMPLEMENTARIA) == "X",
    }
