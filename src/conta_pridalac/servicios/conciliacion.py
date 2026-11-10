"""Conciliación de facturas con las líneas de un extracto: qué movimiento del banco o de la tarjeta pagó (o cobró) cada factura.

Es el motor de la conciliación de Verifactu llevado a Conta, con los casos que ya se han visto en los datos reales: una factura pagada en dos veces, y varias facturas (o tickets) pagadas con un único cargo.
No toca la base de datos: recibe facturas y líneas sencillas y devuelve qué se empareja con qué y por qué regla; quien llama decide qué aplicar. Lo dudoso nunca se empareja solo.

Pasadas, de más a menos segura (una línea sólo se usa una vez):
1. **importe y texto**: la misma cantidad y el nombre o el NIF del tercero en el concepto del movimiento (con las palabras de conciliación del usuario como alias);
2. **importe único**: la misma cantidad, con céntimos, y una sola línea posible; o la misma cantidad y el mismo día, aunque el nombre no se parezca;
3. **varias facturas, un cargo**: facturas del mismo tercero cuyo total suma lo que cargó el banco;
4. **dos pagos**: una factura cuyo total suman dos líneas del mismo tercero;
5. lo que queda sale como *dudoso*, para decidirlo a mano, si tiene el nombre y una fecha próxima pero **otro importe** (una divisa, un descuento) o si otra factura con la misma cantidad **ya ocupa esa línea** (¿factura repetida?).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import combinations

CERO = Decimal("0.00")
DIAS_PARA_DESEMPATAR = 10  # entre varias líneas posibles, vale la más cercana a la fecha de la factura si está a menos de estos días
DIAS_ENTRE_DOS_PAGOS = 60
DIAS_PARA_DUDAR = 7
MARGEN_DE_IMPORTE = Decimal("0.20")  # un importe distinto hasta un 20 % se propone como dudoso
MAX_FACTURAS_POR_CARGO = 4
NIF_REAL = re.compile(r"^([A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z]|[XYZ]\d{7}[A-Z])$")  # «VARIOSTAXI» o «MANUTENCION» no son NIF

# palabras sin valor para comparar nombres: formas jurídicas, artículos y las propias del banco
RUIDO = {
    "sl", "sa", "slu", "sll", "slp", "sau", "sociedad", "limitada", "anonima", "civil", "profesional", "cooperativa", "coop", "the", "and", "los", "las", "del", "de", "la", "el", "en", "con",
    "por", "para", "una", "uno", "que", "sus", "como", "transferencia", "transf", "bizum", "pago", "recibo", "cobro", "sepa", "iban", "comision", "cargo", "abono", "ingreso",
}


def normalizar(texto) -> str:
    """Minúsculas, sin tildes y sin signos."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFD", str(texto))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def palabras(texto_normalizado: str) -> list[str]:
    return [p for p in texto_normalizado.split() if len(p) >= 2 and p not in RUIDO]


def coincide_el_texto(nombre: str, descripcion: str, alias: list[tuple[str, str]] = ()) -> bool:
    """¿Se parece el nombre del tercero al concepto del movimiento? Las mismas estrategias que Verifactu, de la más estricta a la más laxa."""
    emp, mov = normalizar(nombre), normalizar(descripcion)
    if not emp or not mov:
        return False
    p_emp, p_mov = palabras(emp), palabras(mov)
    if not p_emp:
        return False
    comunes = set(p_emp) & set(p_mov)
    if comunes:  # una palabra entera en común (también las siglas de 2 y 3 letras)
        return True
    if any(len(p) >= 4 and p in mov for p in p_emp) or any(len(p) >= 4 and p in emp for p in p_mov):  # una dentro de la otra
        return True
    if any(2 <= len(pe) <= 3 and pm.startswith(pe) for pe in p_emp for pm in p_mov) or any(2 <= len(pm) <= 3 and pe.startswith(pm) for pm in p_mov for pe in p_emp):  # siglas
        return True
    for pe in p_emp:  # prefijo común de 4 letras
        for pm in p_mov:
            if len(pe) >= 4 and len(pm) >= 4 and pe[:4] == pm[:4]:
                return True
    for pe in p_emp:  # el banco trunca los nombres largos
        for pm in p_mov:
            if len(pe) >= 6 and len(pm) >= 4 and ((pe.startswith(pm) and len(pm) >= 6) or (pm.startswith(pe[:8]) and len(pe[:8]) >= 6)):
                return True
    if SequenceMatcher(None, emp, mov).ratio() >= 0.60:
        return True
    return any(normalizar(a) in emp and normalizar(b) in mov for a, b in alias if normalizar(a) and normalizar(b))


@dataclass(frozen=True)
class FacturaPorConciliar:
    id: str
    nombre: str
    nif: str
    fecha: date | None
    total: Decimal  # en euros; negativo si es un abono


@dataclass(frozen=True)
class LineaPorConciliar:
    id: str
    fecha: date
    texto: str  # concepto y más datos del movimiento
    importe: Decimal  # con el signo del Mayor: negativo = sale dinero
    fecha_valor: date | None = None  # la de la operación: en una compra con tarjeta, la del día de la compra; es la que se usa como fecha de pago

    @property
    def dia_del_pago(self) -> date:
        return self.fecha_valor or self.fecha


@dataclass
class Emparejamiento:
    facturas: tuple[FacturaPorConciliar, ...]
    lineas: tuple[LineaPorConciliar, ...]
    regla: str  # importe_y_texto, importe_unico, varias_facturas_un_cargo, dos_pagos


@dataclass
class Dudosa:
    factura: FacturaPorConciliar
    motivo: str
    candidatas: tuple[LineaPorConciliar, ...]


@dataclass
class ResultadoConciliacion:
    emparejadas: list[Emparejamiento] = field(default_factory=list)
    dudosas: list[Dudosa] = field(default_factory=list)
    sin_conciliar: list[FacturaPorConciliar] = field(default_factory=list)  # ninguna línea: se pagaron de otra forma (el socio) o no aparecen en este extracto
    libres: list[LineaPorConciliar] = field(default_factory=list)  # líneas sin factura: comisiones, recibos, pagos sin justificante


def _esperado(f: FacturaPorConciliar, sentido: str) -> Decimal:
    """Lo que ha de mover el banco por la factura: una recibida sale (negativo) y una emitida entra."""
    return -f.total if sentido == "R" else f.total


def _clave_de_tercero(f: FacturaPorConciliar) -> str:
    nif = re.sub(r"[\s.\-]", "", f.nif or "").upper()
    return nif if NIF_REAL.match(nif) else normalizar(f.nombre)


def _con_centimos(importe: Decimal) -> bool:
    return abs(importe) % 1 != 0


def _distancia(f: FacturaPorConciliar, l: LineaPorConciliar) -> int:
    """Días entre la factura y el movimiento (el más cercano de sus dos fechas)."""
    if not f.fecha:
        return 10**6
    return min(abs((f.fecha - l.fecha).days), abs((f.fecha - l.dia_del_pago).days))


def conciliar(facturas: list[FacturaPorConciliar], lineas: list[LineaPorConciliar], sentido: str = "R", alias: list[tuple[str, str]] = ()) -> ResultadoConciliacion:
    """Empareja facturas con líneas de extracto. `sentido`: R recibidas (el dinero sale) o E emitidas (entra). `alias`: pares (nombre del tercero, palabra del banco) del usuario."""
    resultado = ResultadoConciliacion()
    libres = {l.id: l for l in lineas}
    pendientes = sorted(facturas, key=lambda f: (not _con_centimos(f.total), f.fecha or date.min, f.id))  # primero las de importe más específico: son las menos ambiguas

    def candidatas(f: FacturaPorConciliar) -> list[LineaPorConciliar]:
        return [l for l in libres.values() if l.importe == _esperado(f, sentido)]

    def texto_de(f: FacturaPorConciliar, l: LineaPorConciliar) -> bool:
        nif = re.sub(r"[\s.\-]", "", f.nif or "").upper()
        return coincide_el_texto(f.nombre, l.texto, alias) or (len(nif) >= 8 and nif in l.texto.upper().replace(" ", ""))

    usadas: dict[str, LineaPorConciliar] = {}

    def emparejar(facturas_: tuple, lineas_: tuple, regla: str) -> None:
        for l in lineas_:
            usadas[l.id] = libres.pop(l.id, l)
        resultado.emparejadas.append(Emparejamiento(tuple(facturas_), tuple(lineas_), regla))

    # 1. importe y texto. Si varias facturas piden la misma línea (dos facturas iguales, la repetida), se la queda la de fecha más cercana: se reparte de menor a mayor distancia
    pares = sorted(((_distancia(f, l), f.id, l.id, f, l) for f in pendientes for l in candidatas(f) if texto_de(f, l)), key=lambda p: p[:3])
    hechas: set[str] = set()
    for distancia, _, _, f, l in pares:
        if f.id in hechas or l.id not in libres:
            continue
        iguales = [l2 for d2, _, _, f2, l2 in pares if f2.id == f.id and l2.id in libres and l2.id != l.id and d2 == distancia
                   and (l2.dia_del_pago, l2.texto) != (l.dia_del_pago, l.texto)]  # dos líneas idénticas son intercambiables: no hay nada que decidir
        if iguales:
            hechas.add(f.id)
            resultado.dudosas.append(Dudosa(f, "Varios movimientos posibles con el mismo importe, nombre y fecha", (l, *iguales)))
            continue
        hechas.add(f.id)
        emparejar((f,), (l,), "importe_y_texto")
    dudosas_ya = {d.factura.id for d in resultado.dudosas}
    pendientes = [f for f in pendientes if f.id not in hechas and f.id not in dudosas_ya]

    # 2. importe único con céntimos: una sola línea con esa cantidad; si la piden varias facturas, la más cercana
    pares = sorted(((_distancia(f, candidatas(f)[0]), f.id, f) for f in pendientes if _con_centimos(f.total) and len(candidatas(f)) == 1), key=lambda p: p[:2])
    resto_ids = set()
    for _, _, f in pares:
        posibles = candidatas(f)
        if len(posibles) == 1:
            emparejar((f,), (posibles[0],), "importe_unico")
            resto_ids.add(f.id)
    pendientes = [f for f in pendientes if f.id not in resto_ids]
    for f in list(pendientes):  # la misma cantidad y el mismo día, aunque el nombre del banco no se parezca (un comercio con otro nombre comercial)
        mismo_dia = [l for l in candidatas(f) if _distancia(f, l) == 0]
        competidoras = [g for g in pendientes if g.id != f.id and _esperado(g, sentido) == _esperado(f, sentido) and g.fecha == f.fecha]
        if len(mismo_dia) == 1 and not competidoras:
            emparejar((f,), (mismo_dia[0],), "importe_y_fecha")
            pendientes = [g for g in pendientes if g.id != f.id]

    # 3. varias facturas del mismo tercero, un solo cargo
    por_tercero: dict[str, list[FacturaPorConciliar]] = {}
    for f in pendientes:
        por_tercero.setdefault(_clave_de_tercero(f), []).append(f)
    for grupo in por_tercero.values():
        if len(grupo) < 2:
            continue
        for l in sorted(libres.values(), key=lambda l: l.fecha):
            if l.id not in libres or not texto_de(grupo[0], l):
                continue
            disponibles = [f for f in grupo if f in pendientes]
            for n in range(2, min(MAX_FACTURAS_POR_CARGO, len(disponibles)) + 1):
                suma = next((c for c in combinations(disponibles, n) if sum((_esperado(f, sentido) for f in c), CERO) == l.importe), None)
                if suma:
                    emparejar(suma, (l,), "varias_facturas_un_cargo")
                    pendientes = [f for f in pendientes if f not in suma]
                    break

    # 4. una factura, dos pagos
    resto = []
    for f in pendientes:
        con_nombre = [l for l in libres.values() if l.importe * _esperado(f, sentido) > 0 and abs(l.importe) < abs(f.total) and texto_de(f, l)]
        par = next((c for c in combinations(sorted(con_nombre, key=lambda l: l.fecha), 2)
                    if sum((l.importe for l in c), CERO) == _esperado(f, sentido) and abs((c[1].fecha - c[0].fecha).days) <= DIAS_ENTRE_DOS_PAGOS), None)
        if par:
            emparejar((f,), par, "dos_pagos")
        else:
            resto.append(f)
    pendientes = resto

    # 5. dudosas: el nombre y una fecha cercana, pero otro importe (divisas, descuentos, redondeos), o una línea que ya ocupa otra factura igual
    for f in pendientes:
        esperado = _esperado(f, sentido)
        ocupada_por_otra = [l for l in usadas.values() if l.importe == esperado and texto_de(f, l)]
        if ocupada_por_otra:
            resultado.dudosas.append(Dudosa(f, "Otra factura con el mismo importe ya ocupa ese movimiento: ¿está repetida?", tuple(ocupada_por_otra)))
            continue
        parecidas = [l for l in libres.values() if l.importe * esperado > 0 and f.fecha and abs((l.fecha - f.fecha).days) <= DIAS_PARA_DUDAR and texto_de(f, l)
                     and abs(abs(l.importe) - abs(esperado)) <= abs(esperado) * MARGEN_DE_IMPORTE]
        if parecidas:
            resultado.dudosas.append(Dudosa(f, "Mismo nombre y fecha cercana, pero otro importe", tuple(sorted(parecidas, key=lambda l: abs(l.importe - esperado)))))
        else:
            resultado.sin_conciliar.append(f)
    resultado.libres = sorted(libres.values(), key=lambda l: (l.fecha, l.id))
    return resultado
