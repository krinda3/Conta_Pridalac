"""Fichero del modelo 390 (declaración-resumen anual del IVA) para su presentación a la AEAT, según el diseño de registro oficial
(`dr390_2026.json`, salido de `dr390e2026.xlsx`, «390 - Ejercicio 2026 y siguientes»).

Como el 303: páginas de posiciones fijas, cada una entre `<T390PPPPP>…</T390PPPPP>`, dentro de `<T3900EEEE0A0000>…</T3900EEEE0A0000>` y con la cabecera `<AUX>`.
Siempre van la 1 (identificación), 2, 2 bis, 3, 4, 6 y 7 (operaciones específicas); la 5 (régimen simplificado) y la 8 (deducciones diferenciadas) sólo si traen alguna
casilla, como hace el programa anterior. Los importes se rellenan por el número de casilla del diseño; los datos de identificación, por su posición.
Codificación ISO-8859-1, sin saltos de línea.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero303 import _campo, _constante, _numero

RUTA_DISENO = Path(__file__).with_name("dr390_2026.json")
DISENO = json.loads(RUTA_DISENO.read_text(encoding="utf-8"))
CODIFICACION = "latin-1"
DISENO_VERSION = "dr390e2026"
DISENO_SHA256 = hashlib.sha256(RUTA_DISENO.read_bytes()).hexdigest()
PAGINAS = {"01000": "Pág. 1", "02000": "Pág. 2", "02B00": "Pág. 2 bis", "03000": "Pág. 3", "04000": "Pág. 4", "05000": "Pág. 5", "06000": "Pág. 6", "07000": "Pág. 7", "08000": "Pág. 8"}
SIEMPRE = ("01000", "02000", "02B00", "03000", "04000", "06000", "07000")
CERO = Decimal("0")
MAX_ACTIVIDADES = 6
MAX_REPRESENTANTES = 3

# Indicadores de la página 1 (posición → valor) en una empresa corriente: sin devolución mensual, sin grupo, sin criterio de caja, sin concurso.
INDICADORES = {
    109: "0",  # registro de devolución mensual
    110: "0",  # régimen especial del grupo de entidades
    118: "0",  # dominante
    119: "0",  # dependiente
    120: "0",  # tipo de régimen especial del art. 163 sexies.cinco: sin marcar, como en los 390 de 2025
    130: "2",  # concurso de acreedores en el ejercicio
    131: "2",  # opción por el criterio de caja
    132: "2",  # destinatario del criterio de caja
    133: "2",  # pago a cuenta de gasolinas, gasóleos y biocarburantes (novedad de 2026): NO
    134: "0",  # declaración sustitutiva
    135: "0",  # sustitutiva por rectificación de cuotas
}
POS_OPERACIONES_TERCEROS = 431  # «D»: marca de haber presentado el 347

# páginas con la casilla de la actividad (descripción, código, epígrafe), la posición de la primera y el paso entre actividades
POS_ACTIVIDADES = (149, 196, 243, 290, 337, 384)
# representantes (nombre, NIF, fecha del poder, notaría): posiciones de cada uno
POS_REPRESENTANTES = ((646, 726, 735, 743), (755, 835, 844, 852), (864, 944, 953, 961))
POS_REPRESENTANTES_LECTURA = tuple((n, i, f) for n, i, f, _ in POS_REPRESENTANTES)  # nombre, NIF y fecha del poder, para enseñar lo que lleva un fichero


@dataclass
class Actividad390:
    descripcion: str
    codigo: str = ""
    epigrafe: str = ""


@dataclass
class Representante390:
    nombre: str
    nif: str
    fecha_poder: date | None = None
    notaria: str = ""


@dataclass
class Declaracion390:
    nif: str
    nombre: str
    ejercicio: int
    casillas: dict[int, Decimal] = field(default_factory=dict)
    actividades: list[Actividad390] = field(default_factory=list)
    representantes: list[Representante390] = field(default_factory=list)
    declara_347: bool = False  # «D»: marca de tener obligación de presentar el 347; los 390 de 2025 de Empresa A y Empresa B no la llevan
    sustitutiva: bool = False
    justificante_anterior: str = ""  # nº de justificante (13 dígitos) de la declaración que se sustituye
    indicadores: dict[int, str] = field(default_factory=dict)  # sobre INDICADORES
    version_programa: str = ""  # AUX: versión del programa y NIF de quien lo desarrolló (se dejan en blanco)
    nif_desarrollador: str = ""


def _texto_aeat(valor: str, largo: int) -> str:
    """Campo alfanumérico de la AEAT: mayúsculas y sin acentos (la Ñ y la Ç se conservan)."""
    resultado = []
    for caracter in unicodedata.normalize("NFC", (valor or "").upper()):
        if caracter in "ÑÇ":
            resultado.append(caracter)
            continue
        base = "".join(c for c in unicodedata.normalize("NFD", caracter) if unicodedata.category(c) != "Mn")
        resultado.append(base)
    return "".join(resultado)[:largo]


def _fecha(d: date | None) -> str:
    return d.strftime("%d%m%Y") if d else ""


def _pagina(clave: str, valores_posicion: dict[int, str], casillas: dict[int, Decimal], usadas: set[int]) -> str:
    partes = []
    for c in DISENO[PAGINAS[clave]]:
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


def _casillas_de(clave: str) -> set[int]:
    return {c["casilla"] for c in DISENO[PAGINAS[clave]] if c["casilla"] is not None and c["tipo"].upper() in ("NUM", "N")}


def _identificacion(d: Declaracion390) -> dict[int, str]:
    if len(d.actividades) > MAX_ACTIVIDADES:
        raise ErrorContable(f"El 390 admite {MAX_ACTIVIDADES} actividades como máximo")
    if len(d.representantes) > MAX_REPRESENTANTES:
        raise ErrorContable(f"El 390 admite {MAX_REPRESENTANTES} representantes como máximo")
    if d.sustitutiva and not re.fullmatch(r"\d{13}", d.justificante_anterior or ""):
        raise ErrorContable("Una declaración sustitutiva necesita el nº de justificante (13 dígitos) de la que sustituye")
    v = {14: d.nif, 23: _texto_aeat(d.nombre, 60), 103: str(d.ejercicio), **INDICADORES, **d.indicadores}
    v[POS_OPERACIONES_TERCEROS] = "1" if d.declara_347 else "0"
    if d.sustitutiva:
        v[134], v[136] = "1", d.justificante_anterior
    for pos, a in zip(POS_ACTIVIDADES, d.actividades):
        v[pos], v[pos + 40], v[pos + 43] = _texto_aeat(a.descripcion, 40), _texto_aeat(a.codigo, 3), _texto_aeat(a.epigrafe, 4)
    for (p_nombre, p_nif, p_fecha, p_notaria), r in zip(POS_REPRESENTANTES, d.representantes):
        v[p_nombre], v[p_nif], v[p_fecha], v[p_notaria] = _texto_aeat(r.nombre, 80), r.nif, _fecha(r.fecha_poder), _texto_aeat(r.notaria, 12)
    return v


def generar(d: Declaracion390) -> str:
    """Fichero completo (texto) de la declaración."""
    if not d.actividades:
        raise ErrorContable("Falta la actividad principal: se escribe en la ficha de la empresa")
    if not d.representantes:
        raise ErrorContable("Falta al menos un representante con poder: se escribe en la ficha de la empresa")
    casillas = dict(d.casillas)
    usadas: set[int] = set()
    claves = [c for c in PAGINAS if c in SIEMPRE or any(casillas.get(k, CERO) != 0 for k in _casillas_de(c) - set().union(*(_casillas_de(s) for s in SIEMPRE)))]
    cuerpo = ""
    for clave in claves:
        cuerpo += _pagina(clave, _identificacion(d) if clave == "01000" else {}, casillas, usadas)
    sobrantes = sorted(k for k in casillas if k not in usadas and casillas[k] != 0)
    if sobrantes:
        raise ErrorContable(f"Casillas que no caben en las páginas del fichero: {sobrantes}")
    cabecera = f"<T3900{d.ejercicio}0A0000>"
    aux = "<AUX>" + " " * 70 + d.version_programa.ljust(4) + " " * 4 + d.nif_desarrollador.ljust(9) + " " * 213 + "</AUX>"
    return cabecera + aux + cuerpo + f"</T3900{d.ejercicio}0A0000>"


def leer(texto: str) -> dict[str, dict[int, str]]:
    """Descompone un fichero en páginas {posición: texto del campo} según el diseño (para comprobar y para depurar)."""
    paginas = {}
    for clave, hoja in PAGINAS.items():
        inicio = texto.find(f"<T390{clave}>")
        if inicio < 0:
            continue
        paginas[clave] = {c["pos"]: texto[inicio + c["pos"] - 1 : inicio + c["pos"] - 1 + c["lon"]] for c in DISENO[hoja]}
    return paginas


def casillas_del_fichero(texto: str) -> dict[int, Decimal]:
    """Las casillas distintas de cero que lleva un fichero (con la primera aparición si una casilla sale en dos sitios)."""
    casillas: dict[int, Decimal] = {}
    for clave, valores in leer(texto).items():
        for c in DISENO[PAGINAS[clave]]:
            if c["casilla"] and c["tipo"].upper() in ("NUM", "N") and c["casilla"] not in casillas:
                bruto = valores[c["pos"]]
                importe = Decimal(bruto.replace("N", "0")) / 100
                if importe:
                    casillas[c["casilla"]] = -importe if bruto.startswith("N") else importe
    return dict(sorted(casillas.items()))


def desde_calculo(empresa, calculo, *, declara_347: bool = False, **resto) -> Declaracion390:
    """Declaración lista para `generar` a partir del cálculo (`servicios.modelo390.calcular_390`) y la ficha de la empresa (actividades y representantes)."""
    casillas = {k: v for k, v in calculo.casillas.items() if v != 0}
    # tributación toda en territorio común: casilla 87 = 100 % y el resultado atribuible es el de la liquidación anual
    casillas.update({87: Decimal("100"), 92: calculo.casillas.get(84, CERO), 93: calculo.casillas.get(85, CERO), 94: calculo.casillas.get(86, CERO)})
    return Declaracion390(
        nif=empresa.nif, nombre=empresa.nombre, ejercicio=calculo.anio, casillas=casillas, declara_347=declara_347,
        actividades=[Actividad390(a.descripcion, a.codigo or "", a.epigrafe or "") for a in empresa.actividades],
        representantes=[Representante390(r.nombre, r.nif or "", r.fecha_poder, r.notaria or "") for r in empresa.representantes], **resto,
    )
