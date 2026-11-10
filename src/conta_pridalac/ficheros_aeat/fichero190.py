"""Fichero del modelo 190 (resumen anual de retenciones e ingresos a cuenta del IRPF) según el diseño de registro oficial (`DISENOS_LOGICOS_190_2025.pdf`).

Registros de 500 posiciones terminados en CR LF, ISO-8859-1: uno de declarante (tipo 1) y uno por cada percepción (tipo 2: un perceptor puede aparecer con varias claves/subclaves).
Los campos de los perceptores que no se usan van a ceros (numéricos) o blancos (alfanuméricos), igual que en lo presentado hasta ahora; la zona numérica del final del registro 2 crece con los años (2024: hasta la posición 388; 2025: hasta la 394).

De los registros de perceptor sólo se rellenan los campos de las claves de actividades económicas (G, H, I…), que son las que tiene el programa: provincia, clave, subclave, percepción íntegra y retención.
Las claves del trabajo (A, B, C, D…) llevan más datos (situación familiar, reducciones…) y no están implementadas.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from conta_pridalac.domain.errores import ErrorContable

DISENO_VERSION = "DISENOS_LOGICOS_190_2025"
CODIFICACION = "latin-1"
LONGITUD = 500
CERO = Decimal("0")
CLAVES_ADMITIDAS = ("G", "H", "I")  # actividades económicas: sólo llevan percepción dineraria íntegra y retención

# Campos del registro de tipo 2 con su valor por defecto («N» numérico a ceros, «A» alfanumérico a blancos); los que se rellenan se dan por nombre.
_PERCEPTOR = [
    ("tipo", 1, 1, "A"), ("modelo", 2, 4, "A"), ("ejercicio", 5, 8, "A"), ("nif_declarante", 9, 17, "A"), ("nif", 18, 26, "A"), ("nif_representante", 27, 35, "A"),
    ("nombre", 36, 75, "A"), ("provincia", 76, 77, "N"), ("clave", 78, 78, "A"), ("subclave", 79, 80, "N"), ("signo", 81, 81, "A"), ("percepcion", 82, 94, "N"), ("retencion", 95, 107, "N"),
    ("signo_especie", 108, 108, "A"), ("especie", 109, 121, "N"), ("ingreso_a_cuenta", 122, 134, "N"), ("especie_repercutido", 135, 147, "N"),
    ("devengo", 148, 151, "N"), ("ceuta_melilla", 152, 152, "N"), ("nacimiento", 153, 156, "N"), ("situacion_familiar", 157, 157, "N"), ("nif_conyuge", 158, 166, "A"),
    ("discapacidad", 167, 167, "N"), ("contrato", 168, 168, "N"), ("unidad_convivencia", 169, 169, "N"), ("movilidad", 170, 170, "N"),
    ("reducciones", 171, 183, "N"), ("gastos", 184, 196, "N"), ("pensiones_compensatorias", 197, 209, "N"), ("alimentos", 210, 222, "N"),
    ("hijos", 223, 228, "N"), ("hijos_discapacidad", 229, 240, "N"), ("ascendientes", 241, 244, "N"), ("ascendientes_discapacidad", 245, 250, "N"), ("computo_hijos", 251, 253, "N"), ("prestamos", 254, 254, "N"),
    ("signo_incapacidad", 255, 255, "A"), ("incapacidad", 256, 268, "N"), ("retencion_incapacidad", 269, 281, "N"),
    ("signo_especie_incapacidad", 282, 282, "A"), ("especie_incapacidad", 283, 295, "N"), ("ingreso_incapacidad", 296, 308, "N"), ("especie_repercutido_incapacidad", 309, 321, "N"),
    ("ayuda_infancia", 322, 322, "N"),
]


def _fin_zona_numerica(ejercicio: int) -> int:
    """Última posición numérica (a ceros) de la parte final del registro 2, que cada año el diseño amplía con campos nuevos."""
    return 387 if ejercicio <= 2023 else 388 if ejercicio == 2024 else 394


@dataclass
class Percepcion190:
    nif: str  # NIF del perceptor
    nombre: str  # apellidos y nombre, o razón social
    provincia: str  # código de provincia de dos cifras (28 Madrid, 13 Ciudad Real…)
    clave: str  # clave de percepción (G, H, I…)
    subclave: str  # dos cifras
    percepcion: Decimal  # percepción dineraria íntegra
    retencion: Decimal  # retenciones practicadas


@dataclass
class Declaracion190:
    nif: str
    nombre: str
    ejercicio: int
    contacto_telefono: str
    contacto_nombre: str
    identificativo: str  # 13 cifras
    percepciones: list[Percepcion190] = field(default_factory=list)
    email: str = ""
    sustitutiva: bool = False
    complementaria: bool = False
    identificativo_anterior: str = ""  # de la declaración que se complementa o sustituye


def limpiar(texto: str) -> str:
    """Mayúsculas y sin vocales acentuadas (la eñe se conserva: el diseño sólo prohíbe los caracteres especiales)."""
    salida = []
    for c in texto.upper():
        if c == "Ñ":
            salida.append(c)
        else:
            salida.append("".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn"))
    return "".join(salida)


def _importe(valor: Decimal, lon: int) -> str:
    if valor < 0:
        raise ErrorContable(f"Los importes del 190 se consignan sin signo: {valor}")
    return str(int((Decimal(valor) * 100).to_integral_value())).rjust(lon, "0")


def _texto(valor: str, lon: int, nombre: str) -> str:
    t = limpiar(valor)
    if len(t) > lon:
        raise ErrorContable(f"{nombre} no cabe en {lon} posiciones: {valor!r}")
    return t.ljust(lon)


def _cifras(valor: str, lon: int, nombre: str) -> str:
    if not valor.isdigit() or len(valor) > lon:
        raise ErrorContable(f"{nombre} debe ser numérico de hasta {lon} cifras: {valor!r}")
    return valor.rjust(lon, "0")


def registro_declarante(d: Declaracion190) -> str:
    if d.complementaria and d.sustitutiva:
        raise ErrorContable("Una declaración no puede ser a la vez complementaria y sustitutiva")
    if (d.complementaria or d.sustitutiva) and not d.identificativo_anterior:
        raise ErrorContable("Una declaración complementaria o sustitutiva necesita el número identificativo de la anterior")
    total = sum((p.percepcion for p in d.percepciones), CERO)
    retenido = sum((p.retencion for p in d.percepciones), CERO)
    r = (
        "1" + "190" + str(d.ejercicio) + _texto(d.nif, 9, "El NIF del declarante") + _texto(d.nombre, 40, "El nombre del declarante") + "T"
        + _cifras(d.contacto_telefono, 9, "El teléfono de contacto") + _texto(d.contacto_nombre, 40, "El nombre de contacto") + _cifras(d.identificativo, 13, "El número identificativo")
        + ("C" if d.complementaria else " ") + ("S" if d.sustitutiva else " ") + _cifras(d.identificativo_anterior or "0", 13, "El identificativo anterior")
        + _cifras(str(len(d.percepciones)), 9, "El número de percepciones") + " " + _importe(total, 15) + _importe(retenido, 15) + _texto(d.email, 50, "El correo electrónico")
    )
    return r.ljust(LONGITUD)


def registro_perceptor(d: Declaracion190, p: Percepcion190) -> str:
    if p.clave not in CLAVES_ADMITIDAS:
        raise ErrorContable(f"La clave de percepción {p.clave!r} todavía no está implementada (sólo {', '.join(CLAVES_ADMITIDAS)})")
    valores = {
        "tipo": "2", "modelo": "190", "ejercicio": str(d.ejercicio), "nif_declarante": _texto(d.nif, 9, "El NIF del declarante"), "nif": _texto(p.nif, 9, "El NIF del perceptor"),
        "nombre": _texto(p.nombre, 40, "El nombre del perceptor"), "provincia": _cifras(p.provincia, 2, "La provincia"), "clave": p.clave, "subclave": _cifras(p.subclave, 2, "La subclave"),
        "percepcion": _importe(p.percepcion, 13), "retencion": _importe(p.retencion, 13),
    }
    partes = []
    for nombre, ini, fin, tipo in _PERCEPTOR:
        lon = fin - ini + 1
        partes.append(valores[nombre] if nombre in valores else ("0" * lon if tipo == "N" else " " * lon))
    r = "".join(partes) + "0" * (_fin_zona_numerica(d.ejercicio) - 322)
    return r.ljust(LONGITUD)


def generar(d: Declaracion190) -> str:
    registros = [registro_declarante(d)] + [registro_perceptor(d, p) for p in d.percepciones]
    assert all(len(r) == LONGITUD for r in registros)
    return "".join(r + "\r\n" for r in registros)


def leer(texto: str) -> Declaracion190:
    """Interpreta un fichero 190 (para ver lo ya presentado y para comprobar lo generado)."""
    lineas = [x for x in texto.split("\r\n") if x]
    if not lineas or any(len(x) != LONGITUD for x in lineas) or not lineas[0].startswith("1190"):
        raise ErrorContable("No es un fichero del modelo 190: faltan registros o no tienen 500 posiciones")

    def num(s: str) -> Decimal:
        return Decimal(int(s)) / 100

    c = lineas[0]
    d = Declaracion190(nif=c[8:17].strip(), nombre=c[17:57].strip(), ejercicio=int(c[4:8]), contacto_telefono=c[58:67], contacto_nombre=c[67:107].strip(), identificativo=c[107:120],
                       complementaria=c[120] == "C", sustitutiva=c[121] == "S", identificativo_anterior=c[122:135] if int(c[122:135]) else "", email=c[175:225].strip())
    for r in lineas[1:]:
        if not r.startswith("2190"):
            raise ErrorContable("Registro que no es de perceptor (tipo 2) después del de declarante")
        d.percepciones.append(Percepcion190(nif=r[17:26].strip(), nombre=r[35:75].strip(), provincia=r[75:77], clave=r[77], subclave=r[78:80], percepcion=num(r[81:94]), retencion=num(r[94:107])))
    if int(c[135:144]) != len(d.percepciones):
        raise ErrorContable(f"El fichero dice {int(c[135:144])} percepciones y lleva {len(d.percepciones)}")
    return d
