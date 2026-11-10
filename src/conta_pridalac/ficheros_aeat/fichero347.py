"""Fichero del modelo 347 (declaración anual de operaciones con terceras personas) según el diseño de registro oficial (`347.pdf` de la sede, vigente para 2025 y siguientes).

Registros de 500 posiciones terminados en CR LF, ISO-8859-1: uno de declarante (tipo 1) y uno por cada declarado (tipo 2, hoja «D»). Los registros de inmueble (hoja «I») no están implementados.
De cada declarado se rellenan: NIF, nombre, provincia, clave de operación (A adquisiciones, B entregas) y el importe de cada trimestre; el anual es su suma. Los demás campos (cobros en metálico, seguros,
arrendamientos de local, operaciones de transmisión de inmuebles, NIF de operador comunitario, criterio de caja, inversión del sujeto pasivo, BDNS) van a ceros o blancos, igual que en lo presentado hasta ahora.
Si se leyera un fichero que sí los lleva, se avisa en vez de perderlos.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from conta_pridalac.domain.errores import ErrorContable

DISENO_VERSION = "347_2025"
CODIFICACION = "latin-1"
LONGITUD = 500
CERO = Decimal("0")
CLAVES = {"A": "Adquisiciones de bienes y servicios", "B": "Entregas de bienes y servicios"}


@dataclass
class Declarado347:
    nif: str
    nombre: str
    provincia: str  # dos cifras
    clave: str  # A o B
    trimestres: list[Decimal] = field(default_factory=lambda: [CERO] * 4)  # importes con IVA de cada trimestre (con signo)

    @property
    def anual(self) -> Decimal:
        return sum(self.trimestres, CERO)


@dataclass
class Declaracion347:
    nif: str
    nombre: str
    ejercicio: int
    contacto_telefono: str
    contacto_nombre: str
    identificativo: str  # 13 cifras
    declarados: list[Declarado347] = field(default_factory=list)
    sustitutiva: bool = False
    complementaria: bool = False
    identificativo_anterior: str = ""

    @property
    def total(self) -> Decimal:
        return sum((d.anual for d in self.declarados), CERO)


def limpiar(texto: str) -> str:
    """Mayúsculas y sin vocales acentuadas (la eñe se conserva)."""
    salida = []
    for c in texto.upper():
        salida.append(c if c == "Ñ" else "".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn"))
    return "".join(salida)


def _texto(valor: str, lon: int, nombre: str) -> str:
    t = limpiar(valor)
    if len(t) > lon:
        raise ErrorContable(f"{nombre} no cabe en {lon} posiciones: {valor!r}")
    return t.ljust(lon)


def _cifras(valor: str, lon: int, nombre: str) -> str:
    if not valor.isdigit() or len(valor) > lon:
        raise ErrorContable(f"{nombre} debe ser numérico de hasta {lon} cifras: {valor!r}")
    return valor.rjust(lon, "0")


def _importe(valor: Decimal, lon: int = 16) -> str:
    """Signo («N» si es negativo, blanco si no) y el resto en céntimos, a la derecha y con ceros a la izquierda."""
    centimos = int((abs(Decimal(valor)) * 100).to_integral_value())
    return ("N" if valor < 0 else " ") + str(centimos).rjust(lon - 1, "0")


def _leer_importe(campo: str) -> Decimal:
    return (Decimal(int(campo[1:])) / 100) * (-1 if campo[0] == "N" else 1)


def _nif(valor: str) -> str:
    """NIF ajustado a la derecha y con ceros a la izquierda, como pide el diseño."""
    n = limpiar(valor).strip()
    if not 5 <= len(n) <= 9:
        raise ErrorContable(f"NIF no válido: {valor!r}")
    return n.rjust(9, "0")


def registro_declarante(d: Declaracion347) -> str:
    if d.complementaria and d.sustitutiva:
        raise ErrorContable("Una declaración no puede ser a la vez complementaria y sustitutiva")
    if (d.complementaria or d.sustitutiva) and not d.identificativo_anterior:
        raise ErrorContable("Una declaración complementaria o sustitutiva necesita el número identificativo de la anterior")
    r = (
        "1" + "347" + str(d.ejercicio) + _texto(d.nif, 9, "El NIF del declarante") + _texto(d.nombre, 40, "El nombre del declarante") + "T"
        + _cifras(d.contacto_telefono, 9, "El teléfono de contacto") + _texto(d.contacto_nombre, 40, "El nombre de contacto") + _cifras(d.identificativo, 13, "El número identificativo")
        + ("C" if d.complementaria else " ") + ("S" if d.sustitutiva else " ") + _cifras(d.identificativo_anterior or "0", 13, "El identificativo anterior")
        + _cifras(str(len(d.declarados)), 9, "El número de declarados") + _importe(d.total) + "0" * 9 + _importe(CERO)
    )
    return r.ljust(LONGITUD)


def registro_declarado(d: Declaracion347, p: Declarado347) -> str:
    if p.clave not in CLAVES:
        raise ErrorContable(f"Clave de operación {p.clave!r} no admitida (A o B)")
    r = (
        "2" + "347" + str(d.ejercicio) + _texto(d.nif, 9, "El NIF del declarante") + _nif(p.nif) + " " * 9
        + _texto(p.nombre, 40, "El nombre del declarado") + "D" + _cifras(p.provincia, 2, "La provincia") + "  " + " " + p.clave + _importe(p.anual) + "  " + "0" * 15
        + _importe(CERO) + "0000"
    )
    for t in p.trimestres:
        r += _importe(t) + _importe(CERO)  # importe del trimestre e importe percibido por transmisiones de inmuebles
    r += " " * 17 + "   " + _importe(CERO) + "0" * (6 if d.ejercicio >= 2025 else 0)
    return r.ljust(LONGITUD)


def generar(d: Declaracion347) -> str:
    registros = [registro_declarante(d)] + [registro_declarado(d, p) for p in d.declarados]
    assert all(len(r) == LONGITUD for r in registros)
    return "".join(r + "\r\n" for r in registros)


def leer(texto: str) -> Declaracion347:
    """Interpreta un fichero 347 (para ver lo ya presentado y para comprobar lo generado). Avisa si trae datos que este programa no sabe escribir."""
    lineas = [x for x in texto.split("\r\n") if x]
    if not lineas or any(len(x) != LONGITUD for x in lineas) or not lineas[0].startswith("1347"):
        raise ErrorContable("No es un fichero del modelo 347: faltan registros o no tienen 500 posiciones")
    c = lineas[0]
    d = Declaracion347(nif=c[8:17].strip(), nombre=c[17:57].strip(), ejercicio=int(c[4:8]), contacto_telefono=c[58:67], contacto_nombre=c[67:107].strip(), identificativo=c[107:120],
                       complementaria=c[120] == "C", sustitutiva=c[121] == "S", identificativo_anterior=c[122:135] if int(c[122:135]) else "")
    for r in lineas[1:]:
        if not r.startswith("2347") or r[75] != "D":
            raise ErrorContable("Registro que no es de declarado (tipo 2, hoja D): los de inmuebles no están implementados")
        trimestres = [_leer_importe(r[135 + 32 * i: 151 + 32 * i]) for i in range(4)]
        p = Declarado347(nif=r[17:26].strip(), nombre=r[35:75].strip(), provincia=r[76:78], clave=r[81], trimestres=trimestres)
        if _leer_importe(r[82:98]) != p.anual:
            raise ErrorContable(f"{p.nombre}: el importe anual no es la suma de los trimestres")
        d.declarados.append(p)
        if registro_declarado(d, p) != r:
            raise ErrorContable(f"{p.nombre}: el registro lleva datos que este programa no sabe escribir (metálico, inmuebles, criterio de caja…)")
    if int(c[135:144]) != len(d.declarados):
        raise ErrorContable(f"El fichero dice {int(c[135:144])} declarados y lleva {len(d.declarados)}")
    return d
