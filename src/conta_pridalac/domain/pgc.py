"""Nombres del Plan General de Contabilidad (PYMES) para los niveles agrupados: grupo (1), subgrupo (2) y cuenta (3).

Las cuentas de 3 dígitos vienen de `pgc_cuentas.py` (generado desde los listados de MGD); grupos y subgrupos se
escriben aquí. Las subcuentas de 8 dígitos son del plan de cada empresa.
"""
from conta_pridalac.domain.pgc_cuentas import CUENTAS_3
from conta_pridalac.domain.pgc_esfl import CUENTAS_3_ESFL, CUENTAS_4_ESFL, GRUPOS_ESFL, SUBGRUPOS_ESFL

GRUPOS = {
    "1": "Financiación básica",
    "2": "Activo no corriente",
    "3": "Existencias",
    "4": "Acreedores y deudores por operaciones comerciales",
    "5": "Cuentas financieras",
    "6": "Compras y gastos",
    "7": "Ventas e ingresos",
}

SUBGRUPOS = {
    "10": "Capital",
    "11": "Reservas y otros instrumentos de patrimonio",
    "12": "Resultados pendientes de aplicación",
    "13": "Subvenciones, donaciones y ajustes por cambios de valor",
    "14": "Provisiones",
    "15": "Deudas a largo plazo con características especiales",
    "16": "Deudas a largo plazo con partes vinculadas",
    "17": "Deudas a largo plazo por préstamos recibidos, empréstitos y otros conceptos",
    "18": "Pasivos por fianzas, garantías y otros conceptos a largo plazo",
    "19": "Situaciones transitorias de financiación",
    "20": "Inmovilizaciones intangibles",
    "21": "Inmovilizaciones materiales",
    "22": "Inversiones inmobiliarias",
    "23": "Inmovilizaciones materiales en curso",
    "24": "Inversiones financieras a largo plazo en partes vinculadas",
    "25": "Otras inversiones financieras a largo plazo",
    "26": "Fianzas y depósitos constituidos a largo plazo",
    "28": "Amortización acumulada del inmovilizado",
    "29": "Deterioro de valor de activos no corrientes",
    "30": "Comerciales",
    "31": "Materias primas",
    "32": "Otros aprovisionamientos",
    "33": "Productos en curso",
    "34": "Productos semiterminados",
    "35": "Productos terminados",
    "36": "Subproductos, residuos y materiales recuperados",
    "39": "Deterioro de valor de las existencias",
    "40": "Proveedores",
    "41": "Acreedores varios",
    "43": "Clientes",
    "44": "Deudores varios",
    "46": "Personal",
    "47": "Administraciones públicas",
    "48": "Ajustes por periodificación",
    "49": "Deterioro de valor de créditos comerciales y provisiones a corto plazo",
    "50": "Empréstitos, deudas con características especiales y otras emisiones análogas a corto plazo",
    "51": "Deudas a corto plazo con partes vinculadas",
    "52": "Deudas a corto plazo por préstamos recibidos y otros conceptos",
    "53": "Inversiones financieras a corto plazo en partes vinculadas",
    "54": "Otras inversiones financieras a corto plazo",
    "55": "Otras cuentas no bancarias",
    "56": "Fianzas y depósitos recibidos y constituidos a corto plazo y ajustes por periodificación",
    "57": "Tesorería",
    "58": "Activos no corrientes mantenidos para la venta y activos y pasivos asociados",
    "59": "Deterioro de valor de inversiones financieras a corto plazo y de activos no corrientes mantenidos para la venta",
    "60": "Compras",
    "61": "Variación de existencias",
    "62": "Servicios exteriores",
    "63": "Tributos",
    "64": "Gastos de personal",
    "65": "Otros gastos de gestión",
    "66": "Gastos financieros",
    "67": "Pérdidas procedentes de activos no corrientes y gastos excepcionales",
    "68": "Dotaciones para amortizaciones",
    "69": "Pérdidas por deterioro y otras dotaciones",
    "70": "Ventas de mercaderías, de producción propia, de servicios, etc.",
    "71": "Variación de existencias",
    "73": "Trabajos realizados para la empresa",
    "74": "Subvenciones, donaciones y legados",
    "75": "Otros ingresos de gestión",
    "76": "Ingresos financieros",
    "77": "Beneficios procedentes de activos no corrientes e ingresos excepcionales",
    "79": "Excesos y aplicaciones de provisiones y de pérdidas por deterioro",
}


TIPOS_DE_PLAN = {"pymes": "PGC de pequeñas y medianas empresas", "esfl": "Entidad sin fines lucrativos (ONG, fundación, asociación)"}


def nombre_pgc(codigo: str, tipo_plan: str = "pymes") -> str:
    """Nombre del plan de un grupo (1 dígito), subgrupo (2), cuenta (3) o, en el plan de entidades sin fines lucrativos, subcuenta de 4 dígitos; vacío si no se conoce."""
    if tipo_plan == "esfl":
        return {1: GRUPOS_ESFL, 2: SUBGRUPOS_ESFL, 3: CUENTAS_3_ESFL, 4: CUENTAS_4_ESFL}.get(len(codigo), {}).get(codigo, "")
    if len(codigo) == 1:
        return GRUPOS.get(codigo, "")
    if len(codigo) == 2:
        return SUBGRUPOS.get(codigo, "")
    if len(codigo) == 3:
        return CUENTAS_3.get(codigo, "")
    return ""
