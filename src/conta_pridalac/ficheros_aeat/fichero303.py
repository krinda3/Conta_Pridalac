"""Fichero del modelo 303 para su presentación a la AEAT, según el diseño de registro oficial (`dr303_2026.json`, salido de `DR303e26v101.xlsx`).

El fichero son páginas de posiciones fijas, cada una entre etiquetas `<T303PPPPP>…</T303PPPPP>`, dentro de `<T303EEEEPP0000>…</T303EEEEPP0000>`:
cabecera con `<AUX>`, página 01000 (identificación y liquidación), 03000 (información adicional y resultado), 04000 (sólo en el 4T), y DID00 (IBAN).
Los campos se rellenan por el número de casilla que lleva la descripción del diseño (`[29]`); los demás (identificación, indicadores, IBAN) por su posición.
Codificación ISO-8859-1, sin saltos de línea.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable

DISENO = json.loads((Path(__file__).with_name("dr303_2026.json")).read_text(encoding="utf-8"))
CODIFICACION = "latin-1"
DISENO_VERSION = "DR303e26v101"  # diseño de registro oficial del que sale `dr303_2026.json`
DISENO_SHA256 = hashlib.sha256((Path(__file__).with_name("dr303_2026.json")).read_bytes()).hexdigest()
PAGINAS = {"01000": "DP30301", "02000": "DP30302", "03000": "DP30303", "04000": "DP30304", "05000": "DP30305", "DID00": "DP303DID"}
CERO = Decimal("0")

# Indicadores de la página 01000 (posición → valor) en una autoliquidación corriente de régimen general, como los presenta el programa anterior y acepta la AEAT.
INDICADORES = {
    109: "2",  # tributación exclusivamente foral con IVA a la importación pendiente de ingreso
    110: "2",  # registro de devolución mensual
    111: "3",  # tributa exclusivamente en régimen simplificado: "3" NO (sólo régimen general)
    112: "2",  # autoliquidación conjunta
    113: "2",  # criterio de caja
    114: "2",  # destinatario de operaciones en criterio de caja
    115: "2",  # opción por la prorrata especial
    116: "2",  # revocación de la opción por la prorrata especial
    117: "2",  # concurso de acreedores
    118: "00000000",  # fecha del auto de concurso
    126: " ",  # tipo de autoliquidación si hay concurso
    127: "2",  # SII
    128: "0",  # exonerado del 390 (0 salvo en el 4T)
    129: "0",  # volumen anual de operaciones distinto de cero (0 salvo en el 4T)
    130: "0",  # pago a cuenta de gasolinas…
}


@dataclass
class Declaracion303:
    nif: str
    nombre: str
    ejercicio: int
    periodo: str  # "1T".."4T" (o "01".."12" si fuera mensual)
    tipo: str  # C compensación · I ingreso · U domiciliación · D devolución · N sin actividad / resultado cero
    casillas: dict[int, Decimal] = field(default_factory=dict)
    iban: str = ""
    sin_actividad: bool = False
    rectificativa: bool = False
    justificante_anterior: str = ""  # nº de justificante de la autoliquidación que se rectifica (13 dígitos)
    importe_rectificacion: Decimal = CERO  # casilla 111 (si no viene ya en `casillas`)
    baja_domiciliacion: bool = False  # rectificativa favorable: modificar o dar de baja la domiciliación de la anterior
    indicadores: dict[int, str] = field(default_factory=dict)  # sobre INDICADORES: exonerado del 390 y volumen de operaciones en el 4T
    sepa: str = "0"
    version_programa: str = ""  # AUX: versión del programa y NIF de quien lo desarrolló (se dejan en blanco)
    nif_desarrollador: str = ""


def _campo(valor: str, lon: int, tipo: str) -> str:
    if len(valor) > lon:
        raise ErrorContable(f"Valor demasiado largo para un campo de {lon} posiciones: {valor!r}")
    return valor.ljust(lon) if tipo.upper() in ("A", "AN") else valor.rjust(lon, "0")


def _numero(valor: Decimal, lon: int, con_signo: bool) -> str:
    centimos = int((abs(Decimal(valor)) * 100).to_integral_value())
    if valor < 0:
        if not con_signo:
            raise ErrorContable(f"El campo no admite negativos: {valor}")
        return "N" + str(centimos).rjust(lon - 1, "0")
    return str(centimos).rjust(lon, "0")


def _constante(contenido: str) -> str | None:
    m = re.search(r'Constante\s+"([^"]*)"', contenido) or re.fullmatch(r'\s*"(\d{5})"[ .\w]*', contenido)  # el tipo del recargo del 0,5 % viene sin la palabra "Constante"
    return m.group(1) if m else None


def _pagina(clave: str, valores_posicion: dict[int, str], casillas: dict[int, Decimal], usadas: set[int]) -> str:
    campos = DISENO[PAGINAS[clave]]
    partes = []
    for c in campos:
        pos, lon, tipo = c["pos"], c["lon"], c["tipo"]
        constante = _constante(c["contenido"])
        if pos in valores_posicion:
            partes.append(_campo(valores_posicion[pos], lon, tipo))
        elif constante is not None and lon == len(constante):
            partes.append(constante)
        elif c["casilla"] is not None and tipo.upper() in ("NUM", "N") and c["casilla"] in casillas:
            usadas.add(c["casilla"])
            partes.append(_numero(casillas[c["casilla"]], lon, tipo.upper() == "N"))
        elif tipo.upper() in ("A", "AN"):
            partes.append(" " * lon)
        else:
            partes.append("0" * lon)
    return "".join(partes)


def generar(d: Declaracion303) -> str:
    """Fichero completo (texto) de la autoliquidación."""
    if d.tipo not in ("C", "I", "U", "D", "N", "G", "V", "X"):
        raise ErrorContable(f"Tipo de declaración desconocido: {d.tipo!r}")
    ultimo = d.periodo in ("4T", "12")
    usadas: set[int] = set()
    casillas = dict(d.casillas)
    if d.importe_rectificacion:
        casillas[111] = d.importe_rectificacion
    if d.rectificativa and not re.fullmatch(r"\d{13}", d.justificante_anterior or ""):
        raise ErrorContable("Una autoliquidación rectificativa necesita el nº de justificante (13 dígitos) de la que rectifica")
    identificacion = {13: d.tipo, 14: d.nif, 23: d.nombre, 103: str(d.ejercicio), 107: d.periodo, **INDICADORES, **d.indicadores}
    resultado = {
        425: "X" if d.sin_actividad else " ",
        426: "X" if d.rectificativa else " ",
        427: d.justificante_anterior if d.rectificativa else "",
        440: "X" if d.rectificativa and d.baja_domiciliacion else " ",
        458: "X" if d.rectificativa else " ",  # motivo: «Rectificaciones» (el otro, discrepancia de criterio administrativo, habilita la casilla 108)
    }
    did = {23: d.iban, 194: d.sepa}
    cuerpo = _pagina("01000", identificacion, casillas, usadas) + _pagina("03000", resultado, casillas, usadas)
    if ultimo:
        cuerpo += _pagina("04000", {}, casillas, usadas)
    cuerpo += _pagina("DID00", did, casillas, usadas)
    sobrantes = sorted(k for k in d.casillas if k not in usadas and d.casillas[k] != 0)
    if sobrantes:
        raise ErrorContable(f"Casillas que no caben en las páginas del fichero: {sobrantes}")
    cabecera = f"<T3030{d.ejercicio}{d.periodo}0000>"
    aux = "<AUX>" + " " * 70 + d.version_programa.ljust(4) + " " * 4 + d.nif_desarrollador.ljust(9) + " " * 213 + "</AUX>"
    texto = cabecera + aux + cuerpo + f"</T3030{d.ejercicio}{d.periodo}0000>"
    return texto


def leer(texto: str) -> dict[str, dict[int, str]]:
    """Descompone un fichero en páginas {posición: texto del campo} según el diseño (para comprobar y para depurar)."""
    paginas = {}
    for pagina, hoja in PAGINAS.items():
        inicio = texto.find(f"<T303{pagina}>")
        if inicio < 0:
            continue
        paginas[pagina] = {c["pos"]: texto[inicio + c["pos"] - 1 : inicio + c["pos"] - 1 + c["lon"]] for c in DISENO[hoja]}
    return paginas


def tipo_de_declaracion(resultado: Decimal, *, domiciliar: bool, rectificacion: Decimal = CERO) -> str:
    """Tipo según el resultado (casilla 71): negativo → C (se presenta siempre con compensación); cero → N; positivo → U (domiciliación) o I (ingreso, p. ej. con NRC).

    En una rectificativa con casilla 111 el tipo corresponde al resultado sin la parte de la 111 (la AEAT lo pide así)."""
    if resultado < 0:
        resultado = min(resultado + rectificacion, CERO)
    if resultado < 0:
        return "C"
    if resultado == 0:
        return "N"
    return "U" if domiciliar else "I"


def desde_calculo(empresa, calculo, *, domiciliar: bool = True, iban: str = "", justificante_anterior: str | None = None, baja_domiciliacion: bool = False) -> Declaracion303:
    """Declaración lista para `generar` a partir del cálculo del 303 (`servicios.modelo303.calcular_303`) y los datos de la empresa.

    Con `justificante_anterior` es una autoliquidación rectificativa de la que tiene ese justificante."""
    resultado = calculo[71]
    tipo = tipo_de_declaracion(resultado, domiciliar=domiciliar, rectificacion=calculo[111])
    if tipo == "U" and not iban:
        raise ErrorContable("Para domiciliar el pago hace falta el IBAN de la empresa")
    return Declaracion303(
        nif=empresa.nif, nombre=empresa.nombre, ejercicio=calculo.anio, periodo=f"{calculo.periodo}T", tipo=tipo,
        casillas={k: v for k, v in calculo.casillas.items() if v != 0 or k in (27, 45, 46, 64, 65, 66, 69, 71)}, iban=iban if tipo == "U" else "",
        rectificativa=justificante_anterior is not None, justificante_anterior=justificante_anterior or "", baja_domiciliacion=baja_domiciliacion,
    )


def contenido_legible(texto: str) -> tuple[list[tuple[str, str]], dict[int, Decimal]]:
    """Lo que lleva un fichero, para enseñarlo: (datos de identificación y de la rectificativa, casillas distintas de cero con su importe)."""
    paginas = leer(texto)
    p1, p3, did = paginas.get("01000", {}), paginas.get("03000", {}), paginas.get("DID00", {})
    datos = [
        ("Tipo de declaración", p1.get(13, "").strip()), ("NIF", p1.get(14, "").strip()), ("Razón social", p1.get(23, "").strip()),
        ("Ejercicio y periodo", f"{p1.get(103, '').strip()} {p1.get(107, '').strip()}"),
    ]
    if p3.get(426, " ").strip():
        datos += [("Autoliquidación rectificativa", "sí"), ("Justificante de la anterior", p3.get(427, "").strip())]
        if p3.get(440, " ").strip():
            datos.append(("Modificar o dar de baja la domiciliación", "sí"))
    if did.get(23, "").strip():
        datos.append(("IBAN", did[23].strip()))
    casillas: dict[int, Decimal] = {}
    for pagina, valores in paginas.items():
        for c in DISENO[PAGINAS[pagina]]:
            if c["casilla"] and c["tipo"].upper() in ("NUM", "N") and "Tipo %" not in c["desc"]:
                bruto = valores[c["pos"]]
                importe = Decimal(bruto.replace("N", "0")) / 100
                if importe:
                    casillas[c["casilla"]] = -importe if bruto.startswith("N") else importe
    return datos, dict(sorted(casillas.items()))
