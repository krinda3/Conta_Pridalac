"""Modelo 390 (declaración-resumen anual del IVA, régimen general): cálculo de las casillas desde los libros.

Reglas, deducidas de los 390 de 2025 de Empresa A y Empresa B y de la guía de la AEAT (ver `tools/comparar_390.py`, que compara con lo presentado):

- **Periodo**: el ejercicio entero, con las mismas facturas (fecha contable en el año) que entran en los cuatro 303.
- **Devengado, régimen ordinario** (facturas emitidas), por tipo: 0 % (700, 701), 2 % (667, 668), 4 % (01, 02), 5 % (702, 703), 7,5 % (669, 670), 10 % (03, 04) y 21 % (05, 06). Las líneas al 0 % (los
  alquileres de Empresa B) van a la 700 en todos los ejercicios: el 390 las recoge aunque el 303 no las pidiera hasta 2026. **33/34** = totales; **47** = 34 (no hay recargo de equivalencia).
- **Deducible, operaciones interiores corrientes** (facturas recibidas con IVA deducible), por tipo: 2 % (695, 696), 4 % (190, 191), 5 % (724, 725), 7,5 % (697, 698), 10 % (603, 604), 21 % (605, 606), con
  totales **48/49**; los **bienes de inversión** en sus filas (749…614) con totales **50/51**. Las compras a agricultores en régimen especial (12 % y 10,5 %) van a la **60/61**. Las rectificativas
  que rectifican deducciones de periodos anteriores (las que marcó cada 303) van a la **639/62**; las demás restan en su tipo.
- **522**: regularización por prorrata = suma de la casilla 44 de los 303 del año. **64** = 49 + 51 + 61 + 62 + 522 (+ lo que no tiene casilla propia: ver los avisos) · **65** = 47 − 64.
- **84** = 65 · **85** compensación de cuotas del ejercicio anterior (lo que se aplicó de la casilla 110 del primer 303) · **86** = 84 − 85 · **95** = suma de los resultados a ingresar de los cuatro 303 ·
  **97** a compensar = lo que queda pendiente al terminar el año.
- **99** y **108** volumen de operaciones = bases devengadas (33).
- Controles: las cuotas, las bases y el resultado se contrastan con la suma de los cuatro 303 del año (los presentados; si un trimestre no está presentado, el calculado).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import PRESENTADA, DeclaracionPresentada, Ejercicio, Factura, FacturaIva, PresentacionAeat
from conta_pridalac.servicios.modelo303 import calcular_303

CERO = Decimal("0.00")
# tipo de IVA → (casilla de la base, casilla de la cuota)
DEVENGADO = {Decimal("0"): (700, 701), Decimal("2"): (667, 668), Decimal("4"): (1, 2), Decimal("5"): (702, 703), Decimal("7.5"): (669, 670), Decimal("10"): (3, 4), Decimal("21"): (5, 6)}
DEDUCIBLE_CORRIENTE = {Decimal("2"): (695, 696), Decimal("4"): (190, 191), Decimal("5"): (724, 725), Decimal("7.5"): (697, 698), Decimal("10"): (603, 604), Decimal("21"): (605, 606)}
DEDUCIBLE_INVERSION = {Decimal("2"): (749, 750), Decimal("4"): (196, 197), Decimal("5"): (728, 729), Decimal("7.5"): (751, 752), Decimal("10"): (611, 612), Decimal("21"): (613, 614)}
COMPENSACION_AGRARIA = (Decimal("12"), Decimal("10.5"))  # las compras a agricultores y ganaderos en régimen especial: casillas 60 y 61
TOLERANCIA = Decimal("0.02")  # el 390 y los 303 pueden diferir en céntimos por redondeos


def _dec(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Fila390:
    """Una fila del formulario: lo que se ve en pantalla y en la hoja de casillas."""

    seccion: str
    concepto: str
    casillas: str  # «01 · 02», «47»…
    tipo: Decimal | None = None
    base: Decimal | None = None
    cuota: Decimal | None = None
    nota: str = ""


@dataclass
class Control390:
    gravedad: str  # «ok», «aviso» o «error»
    texto: str


@dataclass
class Calculo390:
    anio: int
    casillas: dict[int, Decimal] = field(default_factory=dict)
    filas: list[Fila390] = field(default_factory=list)
    controles: list[Control390] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    origen_303: dict[int, str] = field(default_factory=dict)  # trimestre → «presentada», «calculada» o «presentada sin casillas»

    def __getitem__(self, casilla: int) -> Decimal:
        return self.casillas.get(casilla, CERO)


def _casillas_de_presentada(p) -> dict[int, Decimal]:
    return {int(k): Decimal(str(v)) for k, v in json.loads(p.casillas or "{}").items()}


def casillas_303(sesion: Session, ejercicio: Ejercicio, periodo: int) -> tuple[dict[int, Decimal], str]:
    """Las casillas del 303 del trimestre: las de lo presentado con este programa, o importado del programa anterior, o, si no hay nada presentado, las calculadas."""
    nuestra = sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ejercicio.empresa_id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ejercicio.anio, PresentacionAeat.periodo == f"{periodo}T",
               PresentacionAeat.estado == PRESENTADA)
        .order_by(PresentacionAeat.id.desc())
    ).first()
    if nuestra is not None:
        return _casillas_de_presentada(nuestra), "presentada"
    previa = sesion.scalars(
        select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ejercicio.empresa_id, DeclaracionPresentada.modelo == "303", DeclaracionPresentada.anio == ejercicio.anio,
                                            DeclaracionPresentada.periodo == periodo, DeclaracionPresentada.tipo == 1)
    ).first()
    if previa is not None:
        casillas = _casillas_de_presentada(previa)
        return casillas, ("presentada" if casillas else "presentada sin casillas")
    return dict(calcular_303(sesion, ejercicio, periodo).casillas), "calculada"


def _rectificativas_de_deducciones(sesion: Session, ejercicio: Ejercicio) -> set[int]:
    """Las facturas que los 303 del año han marcado como rectificación de deducciones de periodos anteriores."""
    ids: set[int] = set()
    for p in sesion.scalars(select(PresentacionAeat).where(PresentacionAeat.empresa_id == ejercicio.empresa_id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ejercicio.anio,
                                                          PresentacionAeat.estado == PRESENTADA)):
        ids |= {int(i) for i in json.loads(p.rectifican or "[]")}
    return ids


def calcular_390(sesion: Session, ejercicio: Ejercicio, *, prorrata: Decimal | None = None) -> Calculo390:
    """Casillas del 390 del ejercicio desde las facturas con fecha contable en él y los 303 del año. `prorrata`: porcentaje definitivo (casilla 118), si se aplica."""
    c = Calculo390(ejercicio.anio)
    rectifican = _rectificativas_de_deducciones(sesion, ejercicio)
    devengado: dict[Decimal, list[Decimal]] = {t: [CERO, CERO] for t in DEVENGADO}
    corriente: dict[Decimal, list[Decimal]] = {t: [CERO, CERO] for t in DEDUCIBLE_CORRIENTE}
    inversion: dict[Decimal, list[Decimal]] = {t: [CERO, CERO] for t in DEDUCIBLE_INVERSION}
    sin_fila_corriente = [CERO, CERO]  # tipos que el formulario no tiene (22 %…): entran en los totales, no en una fila
    sin_fila_inversion = [CERO, CERO]
    agraria, rectificacion, no_deducible_base = [CERO, CERO], [CERO, CERO], CERO
    consulta = (select(FacturaIva, Factura).join(Factura, Factura.id == FacturaIva.factura_id)
                .where(Factura.ejercicio_id == ejercicio.id, Factura.fecha_contable >= ejercicio.fecha_inicio, Factura.fecha_contable <= ejercicio.fecha_fin).order_by(Factura.sentido, Factura.numero, FacturaIva.id))
    for i, f in sesion.execute(consulta):
        tipo = i.pct_iva.normalize() if i.pct_iva else Decimal("0")
        if f.sentido == "E":
            if tipo in devengado:
                devengado[tipo][0] += i.base
                devengado[tipo][1] += i.cuota_iva
            else:
                c.avisos.append(f"Emitida {f.numero}: el tipo {i.pct_iva:.2f} % no tiene fila en el régimen ordinario del 390")
            continue
        if not i.deducible:
            if i.cuota_iva or i.base:
                no_deducible_base += i.base
            continue
        if tipo == 0 and i.cuota_iva == 0:
            continue  # exento o no sujeto: no va a ninguna fila del IVA deducible
        if (i.base < 0 or i.cuota_iva < 0) and f.id in rectifican:
            rectificacion[0] += i.base
            rectificacion[1] += i.cuota_iva
        elif tipo in COMPENSACION_AGRARIA:
            agraria[0] += i.base
            agraria[1] += i.cuota_iva
        elif i.bien_inversion:
            destino = inversion.get(tipo)
            if destino is None:
                destino = sin_fila_inversion
                c.avisos.append(f"Recibida {f.numero}: el tipo {i.pct_iva:.2f} % no tiene fila de bienes de inversión; entra en el total 50/51 pero no en una fila")
            destino[0] += i.base
            destino[1] += i.cuota_iva
        else:
            destino = corriente.get(tipo)
            if destino is None:
                destino = sin_fila_corriente
                c.avisos.append(f"Recibida {f.numero}: el tipo {i.pct_iva:.2f} % no tiene fila de operaciones corrientes; entra en el total 48/49 pero no en una fila")
            destino[0] += i.base
            destino[1] += i.cuota_iva
    cas: dict[int, Decimal] = {}
    secc = "5. IVA devengado · régimen ordinario"
    for tipo, (cb, cq) in DEVENGADO.items():
        base, cuota = devengado[tipo]
        if base or cuota:
            cas[cb], cas[cq] = _dec(base), _dec(cuota)
            c.filas.append(Fila390(secc, "Régimen ordinario", f"{cb:02d} · {cq:02d}" if cb < 100 else f"{cb} · {cq}", tipo, cas[cb], cas[cq]))
    cas[33] = _dec(sum((devengado[t][0] for t in devengado), CERO))
    cas[34] = _dec(sum((devengado[t][1] for t in devengado), CERO))
    cas[47] = cas[34]
    c.filas.append(Fila390(secc, "Total bases y cuotas IVA", "33 · 34", None, cas[33], cas[34]))
    c.filas.append(Fila390(secc, "Total cuotas de IVA y recargo de equivalencia", "47", None, None, cas[47]))
    secc = "5. IVA deducible"
    for nombre, tabla, resto, total in (("Operaciones interiores corrientes", corriente, sin_fila_corriente, (48, 49)), ("Operaciones interiores de bienes de inversión", inversion, sin_fila_inversion, (50, 51))):
        for tipo, (cb, cq) in ((t, par) for t, par in (DEDUCIBLE_CORRIENTE if tabla is corriente else DEDUCIBLE_INVERSION).items()):
            base, cuota = tabla[tipo]
            if base or cuota:
                cas[cb], cas[cq] = _dec(base), _dec(cuota)
                c.filas.append(Fila390(secc, nombre, f"{cb} · {cq}", tipo, cas[cb], cas[cq]))
        base = sum((v[0] for v in tabla.values()), CERO) + resto[0]
        cuota = sum((v[1] for v in tabla.values()), CERO) + resto[1]
        if base or cuota:
            cas[total[0]], cas[total[1]] = _dec(base), _dec(cuota)
            c.filas.append(Fila390(secc, f"Total {nombre.lower()}", f"{total[0]} · {total[1]}", None, cas[total[0]], cas[total[1]]))
    if agraria[0] or agraria[1]:
        cas[60], cas[61] = _dec(agraria[0]), _dec(agraria[1])
        c.filas.append(Fila390(secc, "Compensaciones en el régimen especial de la agricultura, ganadería y pesca", "60 · 61", None, cas[60], cas[61]))
    if rectificacion[0] or rectificacion[1]:
        cas[639], cas[62] = _dec(rectificacion[0]), _dec(rectificacion[1])
        c.filas.append(Fila390(secc, "Rectificación de deducciones", "639 · 62", None, cas[639], cas[62]))
    # 522: la regularización por prorrata es la casilla 44 de los 303 del año
    trimestres = {p: casillas_303(sesion, ejercicio, p) for p in (1, 2, 3, 4)}
    c.origen_303 = {p: origen for p, (_, origen) in trimestres.items()}
    regularizacion = sum((t[0].get(44, CERO) for t in trimestres.values()), CERO)
    if regularizacion:
        cas[522] = _dec(regularizacion)
        c.filas.append(Fila390(secc, "Regularización por aplicación del porcentaje definitivo de prorrata", "522", None, None, cas[522]))
    cas[64] = _dec(cas.get(49, CERO) + cas.get(51, CERO) + cas.get(61, CERO) + cas.get(62, CERO) + cas.get(522, CERO))
    cas[65] = _dec(cas[47] - cas[64])
    c.filas.append(Fila390(secc, "Suma de deducciones", "64", None, None, cas[64]))
    c.filas.append(Fila390(secc, "Resultado régimen general (47 − 64)", "65", None, None, cas[65]))
    # 7. resultado de la liquidación anual y 9. resultado de las liquidaciones
    secc = "7. Resultado de la liquidación anual"
    cas[84] = cas[65]
    bolsa_inicial = trimestres[1][0].get(110, CERO)  # lo que el 1T traía pendiente de compensar del ejercicio anterior
    cas[85] = _dec(min(bolsa_inicial, cas[84])) if cas[84] > 0 and bolsa_inicial > 0 else CERO
    cas[86] = _dec(cas[84] - cas[85])
    c.filas += [Fila390(secc, "Suma de resultados (65 + 83 + 658)", "84", None, None, cas[84]), Fila390(secc, "Compensación de cuotas del ejercicio anterior", "85", None, None, cas[85]),
                Fila390(secc, "Resultado de la liquidación (84 + 659 − 85)", "86", None, None, cas[86])]
    secc = "9. Resultado de las liquidaciones"
    ingresado = sum((max(CERO, t[0].get(71, CERO)) for t in trimestres.values()), CERO)
    cas[95] = _dec(ingresado)
    pendiente = max(CERO, -cas[86]) + max(CERO, bolsa_inicial - cas[85])
    cas[97] = _dec(pendiente)
    c.filas.append(Fila390(secc, "Total resultados a ingresar en las autoliquidaciones del ejercicio", "95", None, None, cas[95]))
    c.filas.append(Fila390(secc, "A compensar", "97", None, None, cas[97]))
    # 10. volumen de operaciones
    secc = "10. Volumen de operaciones"
    cas[99], cas[108] = cas[33], cas[33]
    c.filas.append(Fila390(secc, "Operaciones en régimen general", "99", None, None, cas[99]))
    c.filas.append(Fila390(secc, "Total volumen de operaciones (Art. 121 Ley IVA)", "108", None, None, cas[108]))
    # 11 y 12
    secc = "11 y 12. Operaciones específicas y prorrata"
    if no_deducible_base:
        cas[232] = _dec(no_deducible_base)
        c.filas.append(Fila390(secc, "Bases imponibles del IVA soportado no deducible", "232", None, cas[232], None))
    if prorrata is not None:
        c.filas.append(Fila390(secc, "Porcentaje de prorrata definitivo", "118", prorrata, None, None, "se anota a mano en la sede"))
    c.casillas = cas
    c.controles = _controles(c, trimestres)
    return c


def _controles(c: Calculo390, trimestres: dict[int, tuple[dict[int, Decimal], str]]) -> list[Control390]:
    """Lo que la AEAT cruza: el 390 contra la suma de los cuatro 303 del año."""
    controles: list[Control390] = []
    sin_casillas = [p for p, (_, origen) in trimestres.items() if origen == "presentada sin casillas"]
    for p in sin_casillas:
        controles.append(Control390("aviso", f"El 303 del {p}T consta presentado pero sin sus casillas en Conta (importado del programa anterior): no se puede contrastar con él"))
    if sin_casillas:  # con un trimestre menos, la suma no es la del año: no se compara
        calculados = [p for p, (_, origen) in trimestres.items() if origen == "calculada"]
        return controles + ([Control390("aviso", f"El 303 del {', '.join(f'{p}T' for p in calculados)} no está presentado: se ha contrastado con el calculado ahora")] if calculados else [])
    utiles = dict(trimestres)
    detalle = " + ".join(f"{p}T" for p in sorted(utiles))
    comparaciones = (
        ("cuotas devengadas", c[34], sum((t[0].get(27, CERO) for t in utiles.values()), CERO)),
        ("cuotas deducibles (49 + 51 + 61 + 62 + 522)", c[64], sum((t[0].get(45, CERO) for t in utiles.values()), CERO)),
        ("resultado del régimen general (65)", c[65], sum((t[0].get(46, CERO) for t in utiles.values()), CERO)),
    )
    for nombre, del_390, de_303 in comparaciones:
        if abs(del_390 - de_303) <= TOLERANCIA:
            controles.append(Control390("ok", f"{nombre}: coincide con los 303 ({detalle}): {_euros(del_390)}"))
        else:
            controles.append(Control390("aviso", f"{nombre}: el 390 da {_euros(del_390)} y los 303 ({detalle}) suman {_euros(de_303)}: diferencia de {_euros(del_390 - de_303)}"))
    calculados = [p for p, (_, origen) in trimestres.items() if origen == "calculada"]
    if calculados:
        controles.append(Control390("aviso", f"El 303 del {', '.join(f'{p}T' for p in calculados)} no está presentado: se ha contrastado con el calculado ahora"))
    return controles


def _euros(valor: Decimal) -> str:
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
