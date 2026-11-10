"""Balance y cuenta de resultados de las pequeñas y medianas entidades sin fines lucrativos (Resolución del ICAC de 26-3-2013, BOE-A-2013-3736).

Las líneas y las cuentas de cada una son las de los modelos de la tercera parte del BOE («Balance de PYMESFL» y «Cuenta de resultados de PYMESFL»). El motor es el
mismo que el de PYMES (`cuentas_anuales`): cada cuenta va a la línea cuyo prefijo coincide más largo, y las que no caen en ninguna salen en `sin_asignar`.
Los paréntesis del BOE (cuentas que restan) no hacen falta: el saldo de cada cuenta suma con su signo. Las cuentas que el BOE nombra en el activo y en el pasivo a la vez
(551, 5525, 5523 y 5524) van según el signo de su saldo, como en PYMES.

La cuenta de resultados de una ONG incluye, tras el excedente (A), las variaciones del patrimonio neto (B a I). Este plan no usa los grupos 8 y 9, así que se obtienen del balance:
B y C salen de la variación de las cuentas 130, 131 y 132 y de lo traspasado al excedente (745, 746 y 748); G, de la variación de la dotación fundacional o fondo social; I, de la variación
total del patrimonio neto; y H («otras variaciones») es lo que falta hasta I. E y F (ajustes por cambios de criterio y por errores) no se calculan.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.servicios.cuentas_anuales import (
    CERO, Estado, Linea, _saldos, balance_con_modelo, ejercicio_anterior, resultados_con_modelo,
)

# ------------------------------------------------------------------------------------------------ balance

ACTIVO_ESFL = [
    Linea("A", "A) ACTIVO NO CORRIENTE", 0, suma=("A.I", "A.II", "A.III", "A.IV", "A.V", "A.VI", "A.VII"), total=True),
    Linea("A.I", "I. Inmovilizado intangible", 1, cuentas=("20", "280", "2830", "290")),
    Linea("A.II", "II. Bienes del Patrimonio Histórico", 1, cuentas=("24", "299")),
    Linea("A.III", "III. Inmovilizado material", 1, cuentas=("21", "23", "281", "2831", "291")),
    Linea("A.IV", "IV. Inversiones inmobiliarias", 1, cuentas=("22", "282", "2832", "292")),
    Linea("A.V", "V. Inversiones en entidades del grupo y asociadas a largo plazo", 1,
          cuentas=("2503", "2504", "2513", "2514", "2523", "2524", "2593", "2594", "2933", "2934", "2943", "2944", "2953", "2954")),
    Linea("A.VI", "VI. Inversiones financieras a largo plazo", 1,
          cuentas=("25", "2505", "2515", "2525", "2595", "26", "27", "293", "294", "295", "2935", "2945", "2955", "296", "297", "298")),
    Linea("A.VII", "VII. Activos por impuesto diferido", 1, cuentas=("474",)),
    Linea("B", "B) ACTIVO CORRIENTE", 0, suma=("B.I", "B.II", "B.III", "B.IV", "B.V", "B.VI", "B.VII"), total=True),
    Linea("B.I", "I. Existencias", 1, cuentas=("30", "31", "32", "33", "34", "35", "36", "39", "407")),
    Linea("B.II", "II. Usuarios y otros deudores de la actividad propia", 1, cuentas=("447", "448", "495")),
    Linea("B.III", "III. Deudores comerciales y otras cuentas a cobrar", 1,
          cuentas=("430", "431", "432", "433", "434", "435", "436", "437", "490", "493", "440", "441", "446", "449", "460", "464", "470", "471", "472", "473", "544", "558")),
    Linea("B.IV", "IV. Inversiones en entidades del grupo y asociadas a corto plazo", 1,
          cuentas=("5303", "5304", "5313", "5314", "5323", "5324", "5333", "5334", "5343", "5344", "5353", "5354", "5393", "5394", "*5523", "*5524", "5933", "5934", "5943", "5944", "5953", "5954")),
    Linea("B.V", "V. Inversiones financieras a corto plazo", 1,
          cuentas=("53", "5305", "5315", "5325", "5335", "5345", "5355", "540", "541", "542", "543", "545", "546", "547", "548", "549", "*551", "*552", "*5525", "5590", "565", "566", "593", "594", "595", "5935", "5945", "5955", "596", "597", "598")),
    Linea("B.VI", "VI. Periodificaciones a corto plazo", 1, cuentas=("480", "567")),
    Linea("B.VII", "VII. Efectivo y otros activos líquidos equivalentes", 1, cuentas=("57",)),
    Linea("TA", "TOTAL ACTIVO (A + B)", 0, suma=("A", "B"), total=True),
]

PASIVO_ESFL = [
    Linea("PN", "A) PATRIMONIO NETO", 0, suma=("PN.1", "PN.2"), total=True),
    Linea("PN.1", "A-1) Fondos propios", 1, suma=("PN.1.I", "PN.1.II", "PN.1.III", "PN.1.IV"), total=True),
    Linea("PN.1.I", "I. Dotación fundacional/Fondo social", 2, suma=("PN.1.I.1", "PN.1.I.2")),
    Linea("PN.1.I.1", "1. Dotación fundacional/Fondo social", 3, cuentas=("100", "101")),
    Linea("PN.1.I.2", "2. (Dotación fundacional no exigida/Fondo social no exigido)", 3, cuentas=("103", "104")),
    Linea("PN.1.II", "II. Reservas", 2, cuentas=("11",)),
    Linea("PN.1.III", "III. Excedentes de ejercicios anteriores", 2, cuentas=("120", "121")),
    Linea("PN.1.IV", "IV. Excedente del ejercicio", 2, cuentas=("129",)),  # más lo que aún está en los grupos 6 y 7
    Linea("PN.2", "A-2) Subvenciones, donaciones y legados recibidos", 1, cuentas=("130", "131", "132")),
    Linea("PNC", "B) PASIVO NO CORRIENTE", 0, suma=("PNC.I", "PNC.II", "PNC.III", "PNC.IV", "PNC.V"), total=True),
    Linea("PNC.I", "I. Provisiones a largo plazo", 1, cuentas=("14",)),
    Linea("PNC.II", "II. Deudas a largo plazo", 1, suma=("PNC.II.1", "PNC.II.2", "PNC.II.3")),
    Linea("PNC.II.1", "1. Deudas con entidades de crédito", 2, cuentas=("1605", "170")),
    Linea("PNC.II.2", "2. Acreedores por arrendamiento financiero", 2, cuentas=("1625", "174")),
    Linea("PNC.II.3", "3. Otras deudas a largo plazo", 2, cuentas=("16", "17", "1615", "1635", "171", "172", "173", "175", "176", "177", "179", "180", "185", "178", "189")),
    Linea("PNC.III", "III. Deudas con entidades del grupo y asociadas a largo plazo", 1, cuentas=("1603", "1604", "1613", "1614", "1623", "1624", "1633", "1634")),
    Linea("PNC.IV", "IV. Pasivos por impuesto diferido", 1, cuentas=("479",)),
    Linea("PNC.V", "V. Periodificaciones a largo plazo", 1, cuentas=("181",)),
    Linea("PC", "C) PASIVO CORRIENTE", 0, suma=("PC.I", "PC.II", "PC.III", "PC.IV", "PC.V", "PC.VI"), total=True),
    Linea("PC.I", "I. Provisiones a corto plazo", 1, cuentas=("499", "529")),
    Linea("PC.II", "II. Deudas a corto plazo", 1, suma=("PC.II.1", "PC.II.2", "PC.II.3")),
    Linea("PC.II.1", "1. Deudas con entidades de crédito", 2, cuentas=("5105", "520", "527")),
    Linea("PC.II.2", "2. Acreedores por arrendamiento financiero", 2, cuentas=("5125", "524")),
    Linea("PC.II.3", "3. Otras deudas a corto plazo", 2,
          cuentas=("50", "51", "5115", "5135", "5145", "521", "522", "523", "525", "528", "*551", "*552", "*5525", "554", "555", "556", "5565", "5566", "5595", "560", "561", "569")),
    Linea("PC.III", "III. Deudas con entidades del grupo y asociadas a corto plazo", 1,
          cuentas=("5103", "5104", "5113", "5114", "5123", "5124", "5133", "5134", "5143", "5144", "*5523", "*5524", "5563", "5564")),
    Linea("PC.IV", "IV. Beneficiarios-Acreedores", 1, cuentas=("412",)),
    Linea("PC.V", "V. Acreedores comerciales y otras cuentas a pagar", 1, suma=("PC.V.1", "PC.V.2")),
    Linea("PC.V.1", "1. Proveedores", 2, cuentas=("400", "401", "403", "404", "405", "406")),
    Linea("PC.V.2", "2. Otros acreedores", 2, cuentas=("410", "411", "419", "438", "465", "475", "476", "477")),
    Linea("PC.VI", "VI. Periodificaciones a corto plazo", 1, cuentas=("485", "568")),
    Linea("TP", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0, suma=("PN", "PNC", "PC"), total=True),
]


def balance_esfl(sesion: Session, ejercicio: Ejercicio, *, hasta=None) -> Estado:
    """Balance de una entidad sin fines lucrativos: activo con los saldos deudores (debe − haber) y patrimonio neto y pasivo con los acreedores (haber − debe)."""
    return balance_con_modelo(sesion, ejercicio, ACTIVO_ESFL, PASIVO_ESFL, "PN.1.IV", hasta=hasta)


# ------------------------------------------------------------------------------------------------ cuenta de resultados

RESULTADOS_ESFL = [
    Linea("A", "A) EXCEDENTE DEL EJERCICIO", 0),
    Linea("1", "1. Ingresos de la actividad propia", 0, suma=("1a", "1b", "1c", "1d", "1e")),
    Linea("1a", "a) Cuotas de asociados y afiliados", 1, cuentas=("720",)),
    Linea("1b", "b) Aportaciones de usuarios", 1, cuentas=("721",)),
    Linea("1c", "c) Ingresos de promociones, patrocinadores y colaboraciones", 1, cuentas=("722", "723")),
    Linea("1d", "d) Subvenciones, donaciones y legados imputados al excedente del ejercicio", 1, cuentas=("740", "747", "748")),
    Linea("1e", "e) Reintegro de ayudas y asignaciones", 1, cuentas=("728",)),
    Linea("2", "2. Ventas y otros ingresos de la actividad mercantil", 0, cuentas=("700", "701", "702", "703", "704", "705", "706", "708", "709")),
    Linea("3", "3. Gastos por ayudas y otros", 0, suma=("3a", "3b", "3c", "3d")),
    Linea("3a", "a) Ayudas monetarias", 1, cuentas=("650",)),
    Linea("3b", "b) Ayudas no monetarias", 1, cuentas=("651",)),
    Linea("3c", "c) Gastos por colaboraciones y del órgano de gobierno", 1, cuentas=("653", "654")),
    Linea("3d", "d) Reintegro de subvenciones, donaciones y legados", 1, cuentas=("658",)),
    Linea("4", "4. Variación de existencias de productos terminados y en curso de fabricación", 0, cuentas=("6930", "71", "7930")),
    Linea("5", "5. Trabajos realizados por la entidad para su activo", 0, cuentas=("73",)),
    Linea("6", "6. Aprovisionamientos", 0, cuentas=("600", "601", "602", "606", "607", "608", "609", "61", "6931", "6932", "6933", "7931", "7932", "7933")),
    Linea("7", "7. Otros ingresos de la actividad", 0, cuentas=("75",)),
    Linea("8", "8. Gastos de personal", 0, cuentas=("64",)),
    Linea("9", "9. Otros gastos de la actividad", 0, cuentas=("62", "631", "634", "636", "639", "655", "656", "659", "678", "778", "694", "695", "794", "7954")),
    Linea("10", "10. Amortización del inmovilizado", 0, cuentas=("68",)),
    Linea("11", "11. Subvenciones, donaciones y legados de capital traspasados al excedente del ejercicio", 0, cuentas=("745", "746")),
    Linea("12", "12. Exceso de provisiones", 0, cuentas=("795", "7951", "7952", "7955")),
    Linea("13", "13. Deterioro y resultado por enajenaciones del inmovilizado", 0, cuentas=("670", "671", "672", "690", "691", "692", "770", "771", "772", "790", "791", "792")),
    Linea("A1", "A.1) EXCEDENTE DE LA ACTIVIDAD (1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12 + 13)", 0, suma=("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"), total=True),
    Linea("14", "14. Ingresos financieros", 0, cuentas=("760", "761", "762", "769")),
    Linea("15", "15. Gastos financieros", 0, cuentas=("660", "661", "662", "665", "669")),
    Linea("16", "16. Variación de valor razonable en instrumentos financieros", 0, cuentas=("663", "763")),
    Linea("17", "17. Diferencias de cambio", 0, cuentas=("668", "768")),
    Linea("18", "18. Deterioro y resultado por enajenaciones de instrumentos financieros", 0,
          cuentas=("666", "667", "673", "675", "696", "697", "698", "699", "766", "773", "775", "796", "797", "798", "799")),
    Linea("A2", "A.2) EXCEDENTE DE LAS OPERACIONES FINANCIERAS (14 + 15 + 16 + 17 + 18)", 0, suma=("14", "15", "16", "17", "18"), total=True),
    Linea("A3", "A.3) EXCEDENTE ANTES DE IMPUESTOS (A.1 + A.2)", 0, suma=("A1", "A2"), total=True),
    Linea("19", "19. Impuestos sobre beneficios", 0, cuentas=("6300", "6301", "633", "638")),
    Linea("A4", "A.4) VARIACIÓN DE PATRIMONIO NETO RECONOCIDA EN EL EXCEDENTE DEL EJERCICIO (A.3 + 19)", 0, suma=("A3", "19"), total=True),
    Linea("B", "B) Ingresos y gastos imputados directamente al patrimonio neto", 0),
    Linea("B1", "1. Subvenciones recibidas", 1),
    Linea("B2", "2. Donaciones y legados recibidos", 1),
    Linea("B3", "3. Otros ingresos y gastos", 1),
    Linea("B4", "4. Efecto impositivo", 1),
    Linea("BT", "B.1) Variación de patrimonio neto por ingresos y gastos reconocidos directamente en el patrimonio neto (1 + 2 + 3 + 4)", 0, suma=("B1", "B2", "B3", "B4"), total=True),
    Linea("C", "C) Reclasificaciones al excedente del ejercicio", 0),
    Linea("C1", "1. Subvenciones recibidas", 1),
    Linea("C2", "2. Donaciones y legados recibidos", 1),
    Linea("C3", "3. Otros ingresos y gastos", 1),
    Linea("C4", "4. Efecto impositivo", 1),
    Linea("CT", "C.1) Variación de patrimonio neto por reclasificaciones al excedente del ejercicio (1 + 2 + 3 + 4)", 0, suma=("C1", "C2", "C3", "C4"), total=True),
    Linea("D", "D) VARIACIONES DE PATRIMONIO NETO POR INGRESOS Y GASTOS IMPUTADOS DIRECTAMENTE AL PATRIMONIO NETO (B.1 + C.1)", 0, suma=("BT", "CT"), total=True),
    Linea("E", "E) Ajustes por cambios de criterio", 0),
    Linea("F", "F) Ajustes por errores", 0),
    Linea("G", "G) Variaciones en la dotación fundacional o fondo social", 0),
    Linea("H", "H) Otras variaciones", 0),
    Linea("I", "I) RESULTADO TOTAL, VARIACIÓN DEL PATRIMONIO NETO EN EL EJERCICIO (A.4 + D + E + F + G + H)", 0, suma=("A4", "D", "E", "F", "G", "H"), total=True),
]

# las líneas B a H se calculan aparte (ver el docstring del módulo); estas no tienen cuentas ni suma pero sí valor
CALCULADAS = ("B1", "B2", "B3", "C1", "C2", "C3", "G", "H")


def _acreedor(saldos: dict[str, tuple[str, Decimal]], prefijo: str) -> Decimal:
    """Saldo acreedor (haber − debe) de las cuentas que empiezan por el prefijo."""
    return -sum((s for c, (_, s) in saldos.items() if c.startswith(prefijo)), CERO)


def cuenta_resultados_esfl(sesion: Session, ejercicio: Ejercicio) -> Estado:
    """Cuenta de resultados de una entidad sin fines lucrativos del ejercicio, con las variaciones del patrimonio neto (B a I) obtenidas del balance."""
    final = balance_esfl(sesion, ejercicio)
    previo = ejercicio_anterior(sesion, ejercicio)
    avisos: list[str] = []
    if previo is None:
        avisos.append(f"No hay ejercicio {ejercicio.anio - 1} en la base: el patrimonio neto inicial sale a cero y todo aparece como variación del año")
    saldos_fin = _saldos(sesion, ejercicio)
    saldos_ini = _saldos(sesion, previo) if previo is not None else {}

    def variacion(prefijo: str) -> Decimal:
        return _acreedor(saldos_fin, prefijo) - _acreedor(saldos_ini, prefijo)

    traspasado = {c: _acreedor(saldos_fin, c) for c in ("745", "746", "748")}  # lo que salió del patrimonio neto hacia el excedente
    dotacion = final.importe("PN.1.I") - (balance_esfl(sesion, previo).importe("PN.1.I") if previo is not None else CERO)
    d_pn = final.importe("PN") - (balance_esfl(sesion, previo).importe("PN") if previo is not None else CERO)
    extra = {
        "B1": variacion("130") + traspasado["745"], "B2": variacion("131") + traspasado["746"], "B3": variacion("132") + traspasado["748"],
        "C1": -traspasado["745"], "C2": -traspasado["746"], "C3": -traspasado["748"], "G": dotacion,
    }
    estado = resultados_con_modelo(sesion, ejercicio, RESULTADOS_ESFL, extra=extra)
    a4 = estado.importe("A4")
    d = extra["B1"] + extra["B2"] + extra["B3"] + extra["C1"] + extra["C2"] + extra["C3"]
    extra["H"] = d_pn - a4 - d - dotacion
    estado = resultados_con_modelo(sesion, ejercicio, RESULTADOS_ESFL, extra=extra)
    estado.avisos = avisos + estado.avisos + ["Las secciones B a H salen de la variación de las cuentas de patrimonio neto: este plan no usa los grupos 8 y 9. Los ajustes por cambios de criterio y por errores (E, F) no se calculan."]
    return estado
