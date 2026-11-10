"""Balance y cuenta de pérdidas y ganancias oficiales del PGC de PYMES (Real Decreto 1515/2007), con las líneas del modelo que imprime el programa anterior («Balance de PYMES» y «Cuenta de pérdidas y ganancias de PYMES»).

Cada cuenta se asigna a la línea cuyo prefijo coincide más largo (p. ej. 2403 va a «empresas del grupo» y el resto de 24 a «inversiones financieras»). Una línea con `suma` es la suma de otras.
Un prefijo con asterisco (`*551`) es el de la «Configuración de cuentas anuales (PYME)» del programa anterior para las cuentas que van **según el signo de su saldo**: al activo si es deudor y al pasivo si es acreedor.
**Política de saldos de signo contrario**: salvo las cuentas con asterisco, como en el programa anterior, cada cuenta suma con su signo dentro de su línea (un proveedor 410 con saldo deudor resta de «Acreedores comerciales» en lugar de pasar al activo). Si el PGC
llevaría un saldo al otro lado del balance (anticipos a proveedores, clientes acreedores…), se avisa en `avisos` para que lo decida quien deposita las cuentas.
Las cuentas con saldo que no caen en ninguna línea salen en `sin_asignar`, nunca se pierden en silencio: el total del balance siempre cuadra con el de gestión (`estados_contables`) cuando no hay ninguna sin asignar.
Los dos estados excluyen siempre los asientos de regularización y de cierre (subtipos R y Z): con ellos, la PyG saldría a cero y el balance, vacío.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, NIVEL_SUBCUENTA

CERO = Decimal("0.00")
SIN_CIERRE = ("R", "Z")


@dataclass(frozen=True)
class Linea:
    id: str
    etiqueta: str
    nivel: int  # sangría
    cuentas: tuple[str, ...] = ()  # prefijos de las cuentas que alimentan la línea
    suma: tuple[str, ...] = ()  # o ids de las líneas que suma
    total: bool = False  # se imprime como total


# ------------------------------------------------------------------------------------------------ balance de PYMES

ACTIVO = [
    Linea("A", "A) ACTIVO NO CORRIENTE", 0, suma=("A.I", "A.II", "A.III", "A.IV", "A.V", "A.VI", "A.VII"), total=True),
    Linea("A.I", "I. Inmovilizado intangible", 1, cuentas=("20", "280", "290")),
    Linea("A.II", "II. Inmovilizado material", 1, cuentas=("21", "23", "281", "291")),
    Linea("A.III", "III. Inversiones inmobiliarias", 1, cuentas=("22", "282", "292")),
    Linea("A.IV", "IV. Inversiones en empresas del grupo y asociadas a largo plazo", 1,
          cuentas=("2403", "2404", "2413", "2414", "2423", "2424", "2493", "2494", "2933", "2934", "2943", "2944", "2953", "2954")),
    Linea("A.V", "V. Inversiones financieras a largo plazo", 1, cuentas=("24", "25", "26", "249", "293", "294", "295", "296", "297", "298")),
    Linea("A.VI", "VI. Activos por impuesto diferido", 1, cuentas=("474",)),
    Linea("A.VII", "VII. Deudores comerciales no corrientes", 1),
    Linea("B", "B) ACTIVO CORRIENTE", 0, suma=("B.I", "B.II", "B.III", "B.IV", "B.V", "B.VI"), total=True),
    Linea("B.I", "I. Existencias", 1, cuentas=("30", "31", "32", "33", "34", "35", "36", "39", "407")),
    Linea("B.II", "II. Deudores comerciales y otras cuentas a cobrar", 1, suma=("B.II.1", "B.II.2", "B.II.3")),
    Linea("B.II.1", "1. Clientes por ventas y prestaciones de servicios", 2, suma=("B.II.1a", "B.II.1b")),
    Linea("B.II.1a", "a) Clientes por ventas y prestaciones de servicios a largo plazo", 3),
    Linea("B.II.1b", "b) Clientes por ventas y prestaciones de servicios a corto plazo", 3, cuentas=("430", "431", "432", "433", "434", "435", "436", "437", "490", "493")),
    Linea("B.II.2", "2. Accionistas (socios) por desembolsos exigidos", 2, cuentas=("558",)),
    Linea("B.II.3", "3. Otros deudores", 2, cuentas=("44", "460", "470", "471", "472", "473", "544")),
    Linea("B.III", "III. Inversiones en empresas del grupo y asociadas a corto plazo", 1,
          cuentas=("5303", "5304", "5313", "5314", "5323", "5324", "5333", "5334", "5343", "5344", "5353", "5354", "5393", "5394", "5933", "5934", "5943", "5944", "5953", "5954", "*5523", "*5524")),
    Linea("B.IV", "IV. Inversiones financieras a corto plazo", 1, cuentas=("53", "540", "541", "542", "543", "545", "546", "547", "548", "549", "565", "566", "5590", "*551", "*5525", "5935", "5945", "5955", "596", "597", "598")),
    Linea("B.V", "V. Periodificaciones a corto plazo", 1, cuentas=("480", "567")),
    Linea("B.VI", "VI. Efectivo y otros activos líquidos equivalentes", 1, cuentas=("57",)),
    Linea("TA", "TOTAL ACTIVO (A + B)", 0, suma=("A", "B"), total=True),
]

PASIVO = [
    Linea("PN", "A) PATRIMONIO NETO", 0, suma=("PN.1", "PN.2", "PN.3"), total=True),
    Linea("PN.1", "A-1) Fondos propios", 1, suma=("PN.1.I", "PN.1.II", "PN.1.III", "PN.1.IV", "PN.1.V", "PN.1.VI", "PN.1.VII", "PN.1.VIII"), total=True),
    Linea("PN.1.I", "I. Capital", 2, suma=("PN.1.I.1", "PN.1.I.2")),
    Linea("PN.1.I.1", "1. Capital escriturado", 3, cuentas=("100", "101", "102")),
    Linea("PN.1.I.2", "2. (Capital no exigido)", 3, cuentas=("1030", "1040")),
    Linea("PN.1.II", "II. Prima de emisión", 2, cuentas=("110",)),
    Linea("PN.1.III", "III. Reservas", 2, suma=("PN.1.III.1", "PN.1.III.2")),
    Linea("PN.1.III.1", "1. Reserva de capitalización", 3),
    Linea("PN.1.III.2", "2. Otras reservas", 3, cuentas=("112", "113", "114", "115", "119")),
    Linea("PN.1.IV", "IV. (Acciones y participaciones en patrimonio propias)", 2, cuentas=("108", "109")),
    Linea("PN.1.V", "V. Resultados de ejercicios anteriores", 2, cuentas=("120", "121")),
    Linea("PN.1.VI", "VI. Otras aportaciones de socios", 2, cuentas=("118",)),
    Linea("PN.1.VII", "VII. Resultado del ejercicio", 2, cuentas=("129",)),  # más lo que aún está en los grupos 6 y 7
    Linea("PN.1.VIII", "VIII. (Dividendo a cuenta)", 2, cuentas=("557",)),
    Linea("PN.2", "A-2) Ajustes en patrimonio neto", 1, cuentas=("133", "134", "135", "136", "137")),
    Linea("PN.3", "A-3) Subvenciones, donaciones y legados recibidos", 1, cuentas=("130", "131", "132")),
    Linea("PNC", "B) PASIVO NO CORRIENTE", 0, suma=("PNC.I", "PNC.II", "PNC.III", "PNC.IV", "PNC.V", "PNC.VI", "PNC.VII"), total=True),
    Linea("PNC.I", "I. Provisiones a largo plazo", 1, cuentas=("14",)),
    Linea("PNC.II", "II. Deudas a largo plazo", 1, suma=("PNC.II.1", "PNC.II.2", "PNC.II.3")),
    Linea("PNC.II.1", "1. Deudas con entidades de crédito", 2, cuentas=("1605", "170")),
    Linea("PNC.II.2", "2. Acreedores por arrendamiento financiero", 2, cuentas=("1625", "174")),
    Linea("PNC.II.3", "3. Otras deudas a largo plazo", 2, cuentas=("1615", "1635", "171", "172", "173", "175", "176", "177", "178", "179", "180", "185", "189", "16", "17")),
    Linea("PNC.III", "III. Deudas con empresas del grupo y asociadas a largo plazo", 1, cuentas=("1603", "1604", "1613", "1614", "1623", "1624", "1633", "1634")),
    Linea("PNC.IV", "IV. Pasivos por impuesto diferido", 1, cuentas=("479",)),
    Linea("PNC.V", "V. Periodificaciones a largo plazo", 1, cuentas=("181",)),
    Linea("PNC.VI", "VI. Acreedores comerciales no corrientes", 1),
    Linea("PNC.VII", "VII. Deuda con características especiales a largo plazo", 1, cuentas=("153",)),
    Linea("PC", "C) PASIVO CORRIENTE", 0, suma=("PC.I", "PC.II", "PC.III", "PC.IV", "PC.V", "PC.VI"), total=True),
    Linea("PC.I", "I. Provisiones a corto plazo", 1, cuentas=("499", "529")),
    Linea("PC.II", "II. Deudas a corto plazo", 1, suma=("PC.II.1", "PC.II.2", "PC.II.3")),
    Linea("PC.II.1", "1. Deudas con entidades de crédito", 2, cuentas=("5105", "520", "527")),
    Linea("PC.II.2", "2. Acreedores por arrendamiento financiero", 2, cuentas=("5125", "524")),
    Linea("PC.II.3", "3. Otras deudas a corto plazo", 2, cuentas=("1034", "1044", "190", "192", "194", "500", "505", "506", "509", "5115", "5135", "5145", "521", "522", "523", "525", "526", "528", "*551", "*5525", "555", "5565", "5566", "5595", "560", "561", "5598", "569", "550", "553", "554", "556", "51")),
    Linea("PC.III", "III. Deudas con empresas del grupo y asociadas a corto plazo", 1, cuentas=("5103", "5104", "5113", "5114", "5123", "5124", "5133", "5134", "5143", "5144", "*5523", "*5524", "5563", "5564")),
    Linea("PC.IV", "IV. Acreedores comerciales y otras cuentas a pagar", 1, suma=("PC.IV.1", "PC.IV.2")),
    Linea("PC.IV.1", "1. Proveedores", 2, suma=("PC.IV.1a", "PC.IV.1b")),
    Linea("PC.IV.1a", "a) Proveedores a largo plazo", 3),
    Linea("PC.IV.1b", "b) Proveedores a corto plazo", 3, cuentas=("400", "401", "403", "404", "405", "406")),
    Linea("PC.IV.2", "2. Otros acreedores", 2, cuentas=("41", "438", "465", "466", "475", "476", "477")),
    Linea("PC.V", "V. Periodificaciones a corto plazo", 1, cuentas=("485", "568")),
    Linea("PC.VI", "VI. Deuda con características especiales a corto plazo", 1, cuentas=("502", "507")),
    Linea("TP", "TOTAL PATRIMONIO NETO Y PASIVO (A + B + C)", 0, suma=("PN", "PNC", "PC"), total=True),
]

# ------------------------------------------------------------------------------------------------ cuenta de pérdidas y ganancias de PYMES

PYG = [
    Linea("1", "1. Importe neto de la cifra de negocios", 0, cuentas=("70",)),
    Linea("2", "2. Variación de existencias de productos terminados y en curso de fabricación", 0, cuentas=("71", "6930", "7930")),
    Linea("3", "3. Trabajos realizados por la empresa para su activo", 0, cuentas=("73",)),
    Linea("4", "4. Aprovisionamientos", 0, cuentas=("60", "61", "6931", "6932", "6933", "7931", "7932", "7933")),
    Linea("5", "5. Otros ingresos de explotación", 0, cuentas=("75", "740", "747")),
    Linea("6", "6. Gastos de personal", 0, cuentas=("64", "7950", "7957")),
    Linea("7", "7. Otros gastos de explotación", 0, cuentas=("62", "631", "634", "636", "639", "65", "694", "695", "794", "7954")),
    Linea("8", "8. Amortización del inmovilizado", 0, cuentas=("68",)),
    Linea("9", "9. Imputación de subvenciones de inmovilizado no financiero y otras", 0, cuentas=("746",)),
    Linea("10", "10. Excesos de provisiones", 0, cuentas=("7951", "7952", "7955", "7956")),
    Linea("11", "11. Deterioro y resultado por enajenaciones del inmovilizado", 0, cuentas=("670", "671", "672", "690", "691", "692", "770", "771", "772", "790", "791", "792")),
    Linea("12", "12. Otros resultados", 0, cuentas=("678", "778")),
    Linea("A", "A) RESULTADO DE EXPLOTACIÓN (1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12)", 0, suma=("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"), total=True),
    Linea("13", "13. Ingresos financieros", 0, suma=("13a", "13b")),
    Linea("13a", "a) Imputación de subvenciones, donaciones y legados de carácter financiero", 1, cuentas=("7463",)),
    Linea("13b", "b) Otros ingresos financieros", 1, cuentas=("760", "761", "762", "767", "769")),
    Linea("14", "14. Gastos financieros", 0, cuentas=("660", "661", "662", "664", "665", "669")),
    Linea("15", "15. Variación de valor razonable en instrumentos financieros", 0, cuentas=("663", "763")),
    Linea("16", "16. Diferencias de cambio", 0, cuentas=("668", "768")),
    Linea("17", "17. Deterioro y resultado por enajenaciones de instrumentos financieros", 0,
          cuentas=("666", "667", "673", "675", "696", "697", "698", "699", "766", "773", "775", "796", "797", "798", "799")),
    Linea("18", "18. Otros ingresos y gastos de carácter financiero", 0, suma=("18a", "18b", "18c")),
    Linea("18a", "a) Incorporación al activo de gastos financieros", 1, cuentas=("733",)),
    Linea("18b", "b) Ingresos financieros derivados de convenios de acreedores", 1, cuentas=("774",)),
    Linea("18c", "c) Resto de ingresos y gastos", 1),
    Linea("B", "B) RESULTADO FINANCIERO (13 + 14 + 15 + 16 + 17 + 18)", 0, suma=("13", "14", "15", "16", "17", "18"), total=True),
    Linea("C", "C) RESULTADO ANTES DE IMPUESTOS (A + B)", 0, suma=("A", "B"), total=True),
    Linea("19", "19. Impuestos sobre beneficios", 0, cuentas=("630", "633", "638")),
    Linea("D", "D) RESULTADO DEL EJERCICIO (C + 19)", 0, suma=("C", "19"), total=True),
]

# cuentas que por su naturaleza tienen el saldo contrario al de su línea (amortizaciones, deterioros, acciones propias…): no son una anomalía
CONTRARIAS_POR_NATURALEZA = ("28", "29", "39", "490", "493", "1030", "1040", "108", "109", "121", "557", "5580", "5585", "5595", "5598", "2493", "2494", "249")


@dataclass
class LineaCalculada:
    id: str
    etiqueta: str
    nivel: int
    importe: Decimal | None  # None: una línea sin cuentas ni suma con nada (el modelo la imprime en blanco)
    total: bool = False


@dataclass
class Estado:
    lineas: list[LineaCalculada]
    sin_asignar: list[tuple[str, str, Decimal]] = field(default_factory=list)  # (cuenta, nombre, saldo debe − haber)
    avisos: list[str] = field(default_factory=list)

    def importe(self, id: str) -> Decimal:
        return next((l.importe or CERO for l in self.lineas if l.id == id), CERO)


def _prefijos(lineas: list[Linea]) -> dict[str, tuple[str, bool]]:
    """{prefijo: (id de la línea, va según el signo del saldo)}."""
    return {p.lstrip("*"): (l.id, p.startswith("*")) for l in lineas for p in l.cuentas}


def _linea_de(cuenta: str, prefijos: dict[str, tuple[str, bool]]) -> tuple[str, bool] | None:
    for n in range(len(cuenta), 0, -1):
        if cuenta[:n] in prefijos:
            return prefijos[cuenta[:n]]
    return None


def _lado_y_linea(cuenta: str, saldo: Decimal, pref_activo, pref_pasivo) -> tuple[str, str, bool] | None:
    """(lado, línea, según_signo) de una cuenta con saldo: una cuenta fija va a su línea; una con asterisco, al activo si el saldo es deudor y al pasivo si es acreedor."""
    a, p = _linea_de(cuenta, pref_activo), _linea_de(cuenta, pref_pasivo)
    if a and not a[1]:
        return "activo", a[0], False
    if p and not p[1]:
        return "pasivo", p[0], False
    if (a and saldo > 0) or (a and not p):
        return "activo", a[0], True
    if p:
        return "pasivo", p[0], True
    return None


def _calcular(lineas: list[Linea], propios: dict[str, Decimal]) -> list[LineaCalculada]:
    valores: dict[str, Decimal] = {}

    def valor(l: Linea) -> Decimal:
        if l.id not in valores:
            valores[l.id] = sum((valor(por_id[i]) for i in l.suma), CERO) if l.suma else propios.get(l.id, CERO)
        return valores[l.id]

    por_id = {l.id: l for l in lineas}
    return [LineaCalculada(l.id, l.etiqueta, l.nivel, valor(l) if (l.suma or l.cuentas or l.id in propios) else None, l.total) for l in lineas]


def _saldos(sesion: Session, ejercicio: Ejercicio, hasta=None) -> dict[str, tuple[str, Decimal]]:
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=NIVEL_SUBCUENTA, hasta=hasta, excluir_subtipos=SIN_CIERRE)
    return {f.cuenta: (f.nombre, f.debe - f.haber) for f in b.filas}


def balance_pymes(sesion: Session, ejercicio: Ejercicio, *, hasta=None) -> Estado:
    """Balance de PYMES del ejercicio (o hasta una fecha): activo con los saldos deudores (debe − haber) y patrimonio neto y pasivo con los acreedores (haber − debe)."""
    return balance_con_modelo(sesion, ejercicio, ACTIVO, PASIVO, "PN.1.VII", hasta=hasta)


def balance_con_modelo(sesion: Session, ejercicio: Ejercicio, lineas_activo: list[Linea], lineas_pasivo: list[Linea], linea_resultado: str, *, hasta=None) -> Estado:
    """El motor del balance, con las líneas de un modelo: el de PYMES, o el de las entidades sin fines lucrativos (`cuentas_anuales_esfl`).

    `linea_resultado` es la línea del pasivo que recoge el resultado (o excedente) del ejercicio, con lo que aún esté sin regularizar en los grupos 6 y 7.
    """
    saldos = _saldos(sesion, ejercicio, hasta)
    pref_a, pref_p = _prefijos(lineas_activo), _prefijos(lineas_pasivo)
    propios: dict[str, Decimal] = {}
    sin_asignar, avisos = [], []
    resultado_abierto = CERO  # lo que todavía está en los grupos 6 y 7 (antes de regularizar)
    for cuenta, (nombre, saldo) in sorted(saldos.items()):
        if saldo == 0:
            continue
        if cuenta[0] in "67":
            resultado_abierto -= saldo
            continue
        destino = _lado_y_linea(cuenta, saldo, pref_a, pref_p)
        if destino is None:
            sin_asignar.append((cuenta, nombre, saldo))
            continue
        lado, id_, segun_signo = destino
        importe = saldo if lado == "activo" else -saldo
        clave = id_ if lado == "activo" else "P:" + id_
        propios[clave] = propios.get(clave, CERO) + importe
        if not segun_signo and (saldo < 0 if lado == "activo" else saldo > 0) and not cuenta.startswith(CONTRARIAS_POR_NATURALEZA):
            avisos.append(f"{cuenta} {nombre}: saldo {'acreedor' if saldo < 0 else 'deudor'} de {abs(saldo)} en una línea de {lado}; "
                          f"el PGC lo llevaría al {'pasivo' if lado == 'activo' else 'activo'} (se resta dentro de su línea, como el programa anterior)")
    if resultado_abierto:
        propios["P:" + linea_resultado] = propios.get("P:" + linea_resultado, CERO) + resultado_abierto
    activo = _calcular(lineas_activo, {k: v for k, v in propios.items() if not k.startswith("P:")})
    pasivo = _calcular(lineas_pasivo, {k[2:]: v for k, v in propios.items() if k.startswith("P:")})
    ta, tp = next(l.importe for l in activo if l.id == "TA"), next(l.importe for l in pasivo if l.id == "TP")
    if not sin_asignar and ta != tp:
        avisos.append(f"El activo ({ta}) y el patrimonio neto y pasivo ({tp}) no coinciden: diferencia {ta - tp}")
    return Estado(activo + pasivo, sin_asignar, avisos)


def pyg_pymes(sesion: Session, ejercicio: Ejercicio, *, desde=None, hasta=None) -> Estado:
    """Cuenta de pérdidas y ganancias de PYMES: ingresos y gastos en el formato (debe)/haber, con los gastos en negativo."""
    return resultados_con_modelo(sesion, ejercicio, PYG, desde=desde, hasta=hasta)


def resultados_con_modelo(sesion: Session, ejercicio: Ejercicio, lineas: list[Linea], *, desde=None, hasta=None, extra: dict[str, Decimal] | None = None) -> Estado:
    """El motor de la cuenta de resultados, con las líneas de un modelo. `extra`: importes que no salen de las cuentas de los grupos 6 y 7 (líneas calculadas aparte)."""
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=NIVEL_SUBCUENTA, desde=desde, hasta=hasta, excluir_subtipos=SIN_CIERRE)
    prefijos = _prefijos(lineas)
    propios: dict[str, Decimal] = {}
    sin_asignar = []
    for f in b.filas:
        if f.cuenta[0] not in "67":
            continue
        saldo = f.debe - f.haber
        if saldo == 0:
            continue
        destino = _linea_de(f.cuenta, prefijos)
        if destino is None:
            sin_asignar.append((f.cuenta, f.nombre, saldo))
            continue
        propios[destino[0]] = propios.get(destino[0], CERO) - saldo
    propios.update(extra or {})
    estado = Estado(_calcular(lineas, propios), sin_asignar)
    if sin_asignar:
        estado.avisos.append(f"{len(sin_asignar)} cuenta(s) con saldo no tienen línea asignada en el modelo: el resultado no incluye {sum((-s for _, _, s in sin_asignar), CERO)}")
    return estado


def ejercicio_anterior(sesion: Session, ejercicio: Ejercicio) -> Ejercicio | None:
    return sesion.scalar(select(Ejercicio).where(Ejercicio.empresa_id == ejercicio.empresa_id, Ejercicio.anio == ejercicio.anio - 1))


# ------------------------------------------------------------------------------------------------ estado de cambios en el patrimonio neto de PYMES

# columnas del estado: (clave, título, línea del balance de PYMES de la que sale). Las cuentas de cada una son las de la configuración de cuentas anuales del programa anterior.
COLUMNAS_PN = [
    ("capital", "Capital escriturado", "PN.1.I.1"), ("no_exigido", "(Capital no exigido)", "PN.1.I.2"), ("prima", "Prima de emisión", "PN.1.II"), ("reservas", "Reservas", "PN.1.III"),
    ("acciones", "(Acciones y participaciones en patrimonio propias)", "PN.1.IV"), ("anteriores", "Resultados de ejercicios anteriores", "PN.1.V"), ("aportaciones", "Otras aportaciones de socios", "PN.1.VI"),
    ("resultado", "Resultado del ejercicio", "PN.1.VII"), ("dividendo", "(Dividendo a cuenta)", "PN.1.VIII"), ("ajustes", "Ajustes por cambios de valor", "PN.2"), ("subvenciones", "Subvenciones, donaciones y legados recibidos", "PN.3"),
]
OPERACIONES_CON_SOCIOS = ("capital", "no_exigido", "prima", "acciones", "aportaciones", "dividendo")  # el resto de columnas se mueve por resultados, aplicación del resultado y otras variaciones


@dataclass
class FilaPN:
    id: str
    etiqueta: str
    total: bool  # fila de saldo (negrita)
    valores: dict  # clave de columna → importe

    @property
    def suma(self) -> Decimal:
        return sum(self.valores.values(), CERO)


@dataclass
class EstadoPN:
    filas: list[FilaPN]
    avisos: list[str] = field(default_factory=list)


def estado_cambios_pn(sesion: Session, ejercicio: Ejercicio) -> EstadoPN:
    """Estado de cambios en el patrimonio neto de PYMES, del saldo final del ejercicio anterior al saldo final de éste.

    Los saldos salen del balance de PYMES de cada año. «Total de ingresos y gastos reconocidos» es el resultado del ejercicio; «Operaciones con socios» recoge lo que se mueve en el capital, la prima, las acciones propias,
    las aportaciones de socios y el dividendo a cuenta; «Otras variaciones» es lo que falta hasta el saldo final (en la práctica, la aplicación del resultado del año anterior).
    """
    final = balance_pymes(sesion, ejercicio)
    previo = ejercicio_anterior(sesion, ejercicio)
    avisos = []
    if previo is None:
        avisos.append(f"No hay ejercicio {ejercicio.anio - 1} en la base: el saldo inicial sale a cero y todo el patrimonio aparece como variación del año")
        inicial = {k: CERO for k, _, _ in COLUMNAS_PN}
    else:
        base = balance_pymes(sesion, previo)
        inicial = {k: base.importe(linea) for k, _, linea in COLUMNAS_PN}
    fin = {k: final.importe(linea) for k, _, linea in COLUMNAS_PN}
    ingresos = {k: CERO for k, _, _ in COLUMNAS_PN}
    ingresos["resultado"] = pyg_pymes(sesion, ejercicio).importe("D")
    socios = {k: (fin[k] - inicial[k] if k in OPERACIONES_CON_SOCIOS else CERO) for k, _, _ in COLUMNAS_PN}
    otras = {k: fin[k] - inicial[k] - ingresos[k] - socios[k] for k, _, _ in COLUMNAS_PN}
    anterior = ejercicio.anio - 1
    filas = [
        FilaPN("SI", f"A) SALDO, FINAL DEL AÑO {anterior}", True, inicial),
        FilaPN("AJ1", f"I. Ajustes por cambios de criterio {anterior} y anteriores", False, {}),
        FilaPN("AJ2", f"II. Ajustes por errores {anterior} y anteriores", False, {}),
        FilaPN("SA", f"B) SALDO AJUSTADO, INICIO DEL AÑO {ejercicio.anio}", True, inicial),
        FilaPN("IG", "I. Total ingresos y gastos reconocidos", False, ingresos),
        FilaPN("OS", "II. Operaciones con socios o propietarios", False, socios),
        FilaPN("OV", "III. Otras variaciones del patrimonio neto", False, otras),
        FilaPN("SF", f"C) SALDO, FINAL DEL AÑO {ejercicio.anio}", True, fin),
    ]
    return EstadoPN(filas, avisos + final.avisos[:2])
