"""Fichero del modelo 180 (resumen anual de retenciones e ingresos a cuenta por arrendamientos de inmuebles urbanos) según el diseño de registro oficial (`DR_Mod_180_2023.pdf`).

Registros de 500 posiciones terminados en CR LF, ISO-8859-1: uno de declarante (tipo 1) y uno por cada arrendador e inmueble (tipo 2).
El diseño es el del ejercicio 2023 (el último que tenemos); si la AEAT publica uno nuevo se compara con éste y se ajusta (ver `servicios/normativa.py`).

El registro de perceptor lleva, además de la renta y la retención, los datos del **inmueble** arrendado (situación, referencia catastral y dirección), que salen de la ficha del proveedor.
Sólo se implementa la modalidad dineraria («1») y el ejercicio de devengo a cero (rentas del propio ejercicio): no hay rentas en especie ni reintegros de ejercicios anteriores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero190 import _cifras, _importe, _texto, limpiar

DISENO_VERSION = "DR_Mod_180_2023"
CODIFICACION = "latin-1"
LONGITUD = 500
CERO = Decimal("0")


@dataclass
class Inmueble180:
    """Datos del inmueble arrendado (posiciones 114-327 del registro de perceptor)."""

    situacion: str = ""  # 1 con referencia catastral (resto de España) · 2 País Vasco · 3 Navarra · 4 sin referencia catastral
    catastro: str = ""
    tipo_via: str = ""
    via: str = ""
    tipo_numeracion: str = ""
    numero: str = ""
    calificador: str = ""
    bloque: str = ""
    portal: str = ""
    escalera: str = ""
    planta: str = ""
    puerta: str = ""
    complemento: str = ""
    localidad: str = ""
    municipio: str = ""
    codigo_municipio: str = ""
    provincia: str = ""
    codigo_postal: str = ""


# (campo, longitud) de las posiciones 114 a 327, en su orden
_CAMPOS_DEL_INMUEBLE = (
    ("situacion", 1), ("catastro", 20), ("tipo_via", 5), ("via", 50), ("tipo_numeracion", 3), ("numero", 5), ("calificador", 3), ("bloque", 3), ("portal", 3), ("escalera", 3),
    ("planta", 3), ("puerta", 3), ("complemento", 40), ("localidad", 30), ("municipio", 30), ("codigo_municipio", 5), ("provincia", 2), ("codigo_postal", 5),
)
_NUMERICOS = {"codigo_municipio", "provincia", "codigo_postal"}


@dataclass
class Percepcion180:
    nif: str  # NIF del arrendador
    nombre: str  # apellidos y nombre, o razón social
    provincia: str  # código de provincia del domicilio del arrendador (dos cifras)
    base: Decimal  # renta anual satisfecha sin IVA
    porcentaje: Decimal  # % de retención (el último del año)
    retencion: Decimal
    inmueble: Inmueble180 = field(default_factory=Inmueble180)


@dataclass
class Declaracion180:
    nif: str
    nombre: str
    ejercicio: int
    contacto_telefono: str
    contacto_nombre: str
    identificativo: str  # 13 cifras, empiezan por 180
    percepciones: list[Percepcion180] = field(default_factory=list)
    sustitutiva: bool = False
    complementaria: bool = False
    identificativo_anterior: str = ""  # de la declaración que se complementa o sustituye


def _nif(valor: str, nombre: str) -> str:
    t = limpiar(valor).strip()
    if not t or len(t) > 9:
        raise ErrorContable(f"{nombre} debe tener de 1 a 9 caracteres: {valor!r}")
    return t.rjust(9, "0")  # ajustado a la derecha y con ceros a la izquierda, según el diseño


def _porcentaje(valor: Decimal) -> str:
    if valor < 0 or valor >= 100:
        raise ErrorContable(f"El porcentaje de retención debe estar entre 0 y 99,99: {valor}")
    return str(int((Decimal(valor) * 100).to_integral_value())).rjust(4, "0")


def registro_declarante(d: Declaracion180) -> str:
    if d.complementaria and d.sustitutiva:
        raise ErrorContable("Una declaración no puede ser a la vez complementaria y sustitutiva")
    if (d.complementaria or d.sustitutiva) and not d.identificativo_anterior:
        raise ErrorContable("Una declaración complementaria o sustitutiva necesita el número identificativo de la anterior")
    if not d.identificativo.startswith("180"):
        raise ErrorContable("El número identificativo de un 180 empieza por 180")
    base = sum((p.base for p in d.percepciones), CERO)
    retenido = sum((p.retencion for p in d.percepciones), CERO)
    r = (
        "1" + "180" + str(d.ejercicio) + _nif(d.nif, "El NIF del declarante") + _texto(d.nombre, 40, "El nombre del declarante") + "T"
        + _cifras(d.contacto_telefono, 9, "El teléfono de contacto") + _texto(d.contacto_nombre, 40, "El nombre de contacto") + _cifras(d.identificativo, 13, "El número identificativo")
        + ("C" if d.complementaria else " ") + ("S" if d.sustitutiva else " ") + _cifras(d.identificativo_anterior or "0", 13, "El identificativo anterior")
        + _cifras(str(len(d.percepciones)), 9, "El número de percepciones") + " " + _importe(base, 15) + _importe(retenido, 15)
    )
    return r.ljust(LONGITUD)


def registro_perceptor(d: Declaracion180, p: Percepcion180) -> str:
    i = p.inmueble
    if i.situacion not in ("1", "2", "3", "4"):
        raise ErrorContable(f"La situación del inmueble de {p.nombre} debe ser 1, 2, 3 o 4: {i.situacion!r}")
    partes = [
        "2", "180", str(d.ejercicio), _nif(d.nif, "El NIF del declarante"), _nif(p.nif, "El NIF del arrendador"), " " * 9, _texto(p.nombre, 40, "El nombre del arrendador"),
        _cifras(p.provincia, 2, "La provincia del arrendador"), "1", " ", _importe(p.base, 13), _porcentaje(p.porcentaje), _importe(p.retencion, 13), "0000",
    ]
    for campo, lon in _CAMPOS_DEL_INMUEBLE:
        valor = getattr(i, campo) or ""
        partes.append(_cifras(valor or "0", lon, f"El campo «{campo}» del inmueble") if campo in _NUMERICOS else _texto(valor, lon, f"El campo «{campo}» del inmueble"))
    return "".join(partes).ljust(LONGITUD)


def generar(d: Declaracion180) -> str:
    registros = [registro_declarante(d)] + [registro_perceptor(d, p) for p in d.percepciones]
    assert all(len(r) == LONGITUD for r in registros)
    return "".join(r + "\r\n" for r in registros)


def leer(texto: str) -> Declaracion180:
    """Interpreta un fichero 180 (para ver lo ya generado y para comprobarlo)."""
    lineas = [x for x in texto.split("\r\n") if x]
    if not lineas or any(len(x) != LONGITUD for x in lineas) or not lineas[0].startswith("1180"):
        raise ErrorContable("No es un fichero del modelo 180: faltan registros o no tienen 500 posiciones")

    def num(s: str) -> Decimal:
        return Decimal(int(s)) / 100

    c = lineas[0]
    d = Declaracion180(nif=c[8:17].strip(), nombre=c[17:57].strip(), ejercicio=int(c[4:8]), contacto_telefono=c[58:67], contacto_nombre=c[67:107].strip(), identificativo=c[107:120],
                       complementaria=c[120] == "C", sustitutiva=c[121] == "S", identificativo_anterior=c[122:135] if int(c[122:135]) else "")
    for r in lineas[1:]:
        if not r.startswith("2180"):
            raise ErrorContable("Registro que no es de perceptor (tipo 2) después del de declarante")
        inmueble, pos = Inmueble180(), 113
        for campo, lon in _CAMPOS_DEL_INMUEBLE:
            setattr(inmueble, campo, r[pos:pos + lon].strip())
            pos += lon
        d.percepciones.append(Percepcion180(nif=r[17:26].strip(), nombre=r[35:75].strip(), provincia=r[75:77], base=num(r[79:92]), porcentaje=num(r[92:96]),
                                            retencion=num(r[96:109]), inmueble=inmueble))
    if int(c[135:144]) != len(d.percepciones):
        raise ErrorContable(f"El fichero dice {int(c[135:144])} percepciones y lleva {len(d.percepciones)}")
    return d
