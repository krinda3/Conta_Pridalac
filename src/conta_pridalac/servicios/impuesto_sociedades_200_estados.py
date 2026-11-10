"""Balance y cuenta de pérdidas y ganancias del modelo 200 (páginas 03000 a 08000) a partir de los estados PYMES de Conta.

El 200 desglosa más que las líneas PYMES, pero el programa anterior no lo desglosa del todo: pone cada línea PYMES en su casilla «padre» y, a veces, en una «hija» concreta, y deja a cero las hijas más
finas. Se ha comprobado con los `.200` de 2025 de Empresa A y Empresa B que esa es la forma de hacerlo (`tools/comparar_200.py`). Por eso el balance es una tabla de línea PYMES → casillas.
La cuenta de pérdidas y ganancias, en cambio, sí se reparte por cuentas donde el 200 lo pide (compras de mercaderías, servicios profesionales independientes, arrendamientos…).

Verificado con los dos ficheros reales (importe distinto de cero): marcado `✓` en las tablas. Sin marca: casillas que valen cero en las dos empresas, elegidas por su nombre en el diseño de registro;
hay que revisarlas el día que alguna tenga importe (el generador avisa cuando lo escribe en una casilla sin verificar).
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.ficheros_aeat import fichero200 as f200
from conta_pridalac.ficheros_aeat.fichero200 import Pagina
from conta_pridalac.servicios import cuentas_anuales
from conta_pridalac.servicios import impuesto_sociedades_datos as isd

CERO = Decimal("0.00")
PAGINAS_ESTADOS = ("03000", "04000", "05000", "06000", "07000", "08000")

# línea PYMES → casillas donde va su importe. (✓ = comprobado con importes reales de Empresa A y Empresa B 2025)
BALANCE: dict[str, tuple[int, ...]] = {
    "A": (101,), "A.I": (102, 110), "A.II": (111,), "A.III": (115,), "A.IV": (118,), "A.V": (126,), "A.VI": (134,), "A.VII": (135,),  # ✓ A, A.I, A.II, A.VI
    "B": (136,), "B.I": (138,), "B.II": (149,), "B.II.1": (150,), "B.II.1a": (151,), "B.II.1b": (152,), "B.II.2": (158,), "B.II.3": (159,),  # ✓ B, B.I, B.II, B.II.1, B.II.1b, B.II.3
    "B.III": (160,), "B.IV": (168,), "B.V": (176,), "B.VI": (177,), "TA": (180,),  # ✓ B.VI, TA
    "PN": (185,), "PN.1": (186,), "PN.1.I": (187,), "PN.1.I.1": (188,), "PN.1.I.2": (189,), "PN.1.II": (190,), "PN.1.III": (191,), "PN.1.III.1": (1001,), "PN.1.III.2": (193,),  # ✓ PN…III.2
    "PN.1.IV": (194,), "PN.1.V": (195,), "PN.1.VI": (198,), "PN.1.VII": (199,), "PN.1.VIII": (200,), "PN.2": (208,), "PN.3": (209,),  # ✓ V, VI, VII
    "PNC": (210,), "PNC.I": (211,), "PNC.II": (216,), "PNC.II.1": (218,), "PNC.II.2": (219,), "PNC.II.3": (222,), "PNC.III": (223,), "PNC.IV": (224,), "PNC.V": (225,), "PNC.VI": (226), "PNC.VII": (227,),
    "PC": (228,), "PC.I": (230,), "PC.II": (231,), "PC.II.1": (233,), "PC.II.2": (234,), "PC.II.3": (237,), "PC.III": (238,), "PC.IV": (239,), "PC.IV.1": (240,), "PC.IV.1a": (241,), "PC.IV.1b": (242,),
    "PC.IV.2": (249,), "PC.V": (250,), "PC.VI": (251,), "TP": (252,),  # ✓ PC, PC.II, PC.II.3, PC.IV, PC.IV.2, TP
}
BALANCE = {k: (v if isinstance(v, tuple) else (v,)) for k, v in BALANCE.items()}

# líneas de la cuenta de pérdidas y ganancias cuyo importe va entero a sus casillas (sin desglose por cuentas)
PYG_SIMPLE: dict[str, tuple[int, ...]] = {
    "1": (255,), "2": (258,), "3": (259,), "8": (284,), "9": (285,), "10": (286,), "A": (296,),
    "13": (297,), "13a": (304,), "14": (305,), "15": (309,), "16": (312,), "17": (313,), "18": (329,), "18a": (330,), "18b": (331,), "B": (324,),
    "C": (325,), "19": (326,), "D": (327, 500),
}
# desglose por cuentas, línea PYMES → casilla del padre y las hijas directas con sus prefijos de cuenta. Lo que no cae en ninguna hija va a la casilla «resto» (y se avisa),
# para que las hijas sumen siempre lo mismo que el padre.
PYG_PADRE = {"4": 260, "5": 265, "6": 270, "7": 279, "11": 287, "12": 295}
PYG_HIJAS: dict[str, list[tuple[int, tuple[str, ...]]]] = {
    "4": [(261, ("600", "6060", "6080", "6090", "610")), (262, ("601", "602", "6061", "6062", "6081", "6082", "6091", "6092", "611", "612")), (263, ("607",)),
          (264, ("6931", "6932", "6933", "7931", "7932", "7933"))],
    "5": [(266, ("75",)), (269, ("740", "747"))],
    "6": [(271, ("640",)), (273, ("641",)), (274, ("642",)), (275, ("643", "644")), (276, ("645",)), (277, ("649",)), (278, ("7950", "7957"))],
    "7": [(280, ("62",)), (281, ("631", "634", "636", "639")), (282, ("650", "694", "695", "794", "7954")), (283, ("651", "652", "653", "654", "655", "656", "657", "658", "659"))],
    "11": [(289, ("690", "691", "692")), (290, ("790", "791", "792")), (292, ("770", "771", "772")), (293, ("670", "671", "672"))],
}
RESTO_PYG = {"4": 262, "6": 277, "7": 283}  # donde se pone lo que no cae en ninguna hija
# desglose de una hija en sus propias casillas por cuentas: casilla → prefijos
PYG_NIETOS: dict[int, tuple[str, ...]] = {760: ("600", "6060", "6080", "6090"), 761: ("610",), 762: ("601", "602", "6061", "6062", "6081", "6082", "6091", "6092"), 763: ("611", "612"),
                                           267: ("752",), 253: ("623",)}
# casillas que se calculan de otras: destino → (suman, restan)
PYG_DERIVADAS: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {268: ((266,), (267,)), 254: ((280,), (253,)), 288: ((289, 290), ()), 291: ((292, 293), ())}


def _importe_de_prefijos(saldos: dict[str, Decimal], prefijos: tuple[str, ...]) -> Decimal:
    return -sum((s for c, s in saldos.items() if c.startswith(prefijos)), CERO)


def casillas_de_estados(sesion: Session, ejercicio: Ejercicio) -> tuple[dict[int, Decimal], list[str]]:
    """({casilla: importe}, avisos) del balance y la PyG del ejercicio, con el criterio del programa anterior para el 200."""
    balance, pyg = cuentas_anuales.balance_pymes(sesion, ejercicio), cuentas_anuales.pyg_pymes(sesion, ejercicio)
    saldos = isd._saldos(sesion, ejercicio)
    valores: dict[int, Decimal] = {}
    avisos: list[str] = []
    for linea, casillas in BALANCE.items():
        for c in casillas:
            valores[c] = balance.importe(linea)
    for linea, casillas in PYG_SIMPLE.items():
        for c in casillas:
            valores[c] = pyg.importe(linea)
    for linea, padre in PYG_PADRE.items():
        total = pyg.importe(linea)
        valores[padre] = total
        asignado = CERO
        for casilla, prefijos in PYG_HIJAS.get(linea, []):
            valores[casilla] = _importe_de_prefijos(saldos, prefijos)
            asignado += valores[casilla]
        resto = total - asignado if linea in PYG_HIJAS else CERO  # una línea sin hijas (la 12) va entera a su casilla
        if resto != 0:
            destino = RESTO_PYG.get(linea)
            if destino is None:
                avisos.append(f"Línea {linea} de la cuenta de pérdidas y ganancias: {resto} sin casilla propia en el modelo 200")
            else:
                valores[destino] = valores.get(destino, CERO) + resto
                avisos.append(f"Línea {linea} de la cuenta de pérdidas y ganancias: {resto} no cae en ninguna casilla concreta; se ha puesto en la {destino:05d}")
    for casilla, prefijos in PYG_NIETOS.items():
        valores[casilla] = _importe_de_prefijos(saldos, prefijos)
    for destino, (suman, restan) in PYG_DERIVADAS.items():
        valores[destino] = sum((valores[c] for c in suman), CERO) - sum((valores[c] for c in restan), CERO)
    return valores, avisos


def paginas_de_estados(sesion: Session, ejercicio: Ejercicio) -> tuple[list[Pagina], list[str]]:
    valores, avisos = casillas_de_estados(sesion, ejercicio)
    paginas = {codigo: Pagina.nueva(codigo) for codigo in PAGINAS_ESTADOS}
    donde: dict[int, tuple[str, int]] = {}
    for codigo in PAGINAS_ESTADOS:
        for n, c in f200._CAMPOS[codigo].items():
            if c["casilla"]:
                donde.setdefault(int(c["casilla"]), (codigo, n))
    for casilla, importe in valores.items():
        if casilla not in donde:
            avisos.append(f"La casilla {casilla:05d} no existe en las páginas 3 a 8 del modelo 200")
            continue
        codigo, n = donde[casilla]
        if importe:
            paginas[codigo].poner_importe(n, importe)
    return [paginas[c] for c in PAGINAS_ESTADOS], avisos


# ------------------------------------------------------------------------------------------------ estado de cambios en el patrimonio neto (9000, 10000, 11000)

def _norm(texto: str) -> str:
    sin = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower().replace(",", " ")
    return re.sub(r"\s+", " ", sin).strip()


# columna del 200 (normalizada) → columna del estado de Conta; «total» se calcula
COLUMNAS_ECPN = {
    "escriturado": "capital", "no exigido": "no_exigido", "prima de emision": "prima", "reservas": "reservas", "acciones y participaciones en patrimonio propias": "acciones",
    "resultados ejercicios anteriores": "anteriores", "otras aportaciones de socios": "aportaciones", "otras aportaciones socios": "aportaciones", "resultado del ejercicio": "resultado",
    "dividendo a cuenta": "dividendo", "ajustes por cambios de valor": "ajustes", "ajustes por cambio de valor": "ajustes", "subvenciones donaciones y legados recibidos": "subvenciones", "total": None,
}
# fila de Conta → filas del 200 (normalizadas) donde se escribe. El programa anterior rellena solo estas: el resultado en «Resultado cuenta de pérdidas y ganancias» y las otras variaciones en el total y en «Otras variaciones».
FILAS_ECPN = {
    "SI": [("saldo final del ejercicio anterior",)], "AJ1": [("ajustes por cambio de criterio de ejercicios anteriores",)], "AJ2": [("ajustes por errores de ejercicios anteriores",)],
    "SA": [("saldo ajustado inicio del ejercicio",)], "IG": [("resultado cuenta perdidas y ganancias",)], "OS": [("operaciones con socios o propietarios",)],
    "OV": [("otras variaciones del patrimonio neto",), ("otras variaciones del patrimonio neto", "otras variaciones")], "SF": [("saldo final del ejercicio",)],
}


def _indice_ecpn(codigo: str) -> dict[tuple[tuple[str, ...], str], int]:
    """(fila normalizada, columna normalizada) → nº de campo, de las descripciones del diseño: «(II) - Saldo final… - Capital - Escriturado [00380]»."""
    indice = {}
    for n, c in f200._CAMPOS[codigo].items():
        if not c["casilla"]:
            continue
        partes = [_norm(x) for x in re.sub(r"\s*\[\d{5}\]", "", c["desc"]).split(" - ")][1:]  # sin «Estado de cambios patrimonio neto (II)»
        columna, fila = partes[-1], partes[:-1]
        if fila and fila[-1] == "capital":  # «Capital - Escriturado / No exigido»: el grupo no es parte de la fila
            fila = fila[:-1]
        indice[(tuple(fila), columna)] = n
    return indice


def paginas_ecpn(sesion: Session, ejercicio: Ejercicio) -> tuple[list[Pagina], list[str]]:
    estado = cuentas_anuales.estado_cambios_pn(sesion, ejercicio)
    p9, p10, p11 = Pagina.nueva("09000"), Pagina.nueva("10000"), Pagina.nueva("11000")
    resultado = next(f for f in estado.filas if f.id == "IG").valores.get("resultado", CERO)
    for casilla in (500, 355):  # resultado de la cuenta de pérdidas y ganancias y total de ingresos y gastos reconocidos
        p9.poner_importe(p9.n_de_casilla(casilla), resultado)
    avisos = list(estado.avisos)
    for pagina in (p10, p11):
        indice = _indice_ecpn(pagina.codigo)
        for fila in estado.filas:
            destinos = FILAS_ECPN.get(fila.id, [])
            for ruta in destinos:
                for columna, clave in COLUMNAS_ECPN.items():
                    n = indice.get((ruta, columna))
                    if n is None:
                        continue
                    importe = fila.suma if clave is None else fila.valores.get(clave, CERO)
                    if importe:
                        pagina.poner_importe(n, importe)
    if any(f.id == "OS" and f.suma for f in estado.filas):
        avisos.append("Operaciones con socios: el importe va en la fila total del estado de cambios del patrimonio neto, sin desglose por tipo de operación")
    return [p9, p10, p11], avisos
