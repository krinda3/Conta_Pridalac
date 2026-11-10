"""El mapa de cuentas MGD (7 dígitos) → el programa anterior (8) contrastado con los asientos automáticos de 2022 del programa anterior.

Los PDF viven en `docs/Exportaciones del programa anterior/` (datos reales, no versionados): el test se omite si no están.
"""
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio
from conta_pridalac.migracion.cuentas import CERO_TRAS_POR_EMPRESA, cuenta_8
from conta_pridalac.servicios.cierre import regularizar_ingresos_gastos, saldos_del_ejercicio

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
from leer_diario_programa_anterior_pdf import leer  # noqa: E402

pytestmark = pytest.mark.datos_reales

PDF = {
    "empresa_a": ("EMPRESA A Asientos automaticos año 2022.pdf", "9.1"),
    "empresa_b": ("EMPRESA B Asientos automaticos año 2022.pdf", "9.3"),
}
# Cuentas cuyo código distingue las dos reglas y que aparecen en la apertura del programa anterior 2022
EJEMPLOS = {
    "empresa_a": [("2811000", "28110000"), ("2813001", "28130001"), ("2812001", "28120001"), ("4721701", "47210701")],
    "empresa_b": [("4108123", "41008123"), ("4108274", "41008274"), ("1000000", "10000000")],
}
IDENTICAS_MINIMAS = {"empresa_a": 21, "empresa_b": 19}  # cuentas con el mismo saldo en la apertura del programa anterior y en la prevista desde MGD

norm = lambda s: re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFD", (s or "").upper()).encode("ascii", "ignore").decode())


def _asientos(clave):
    fichero, _ = PDF[clave]
    ruta = RAIZ / "docs" / "Exportaciones del programa anterior" / fichero
    if not ruta.exists():
        pytest.skip(f"No está {ruta.name}")
    return {a.id: a for a in leer(str(ruta))}


def test_la_conversion_de_los_ejemplos_distintivos(carga_mgd):
    for c7, esperado in EJEMPLOS[carga_mgd.clave]:
        codigo = {"empresa_a": 11, "empresa_b": 12}[carga_mgd.clave]
        assert cuenta_8(c7, CERO_TRAS_POR_EMPRESA[codigo]) == esperado


def test_los_nombres_de_las_cuentas_convertidas_coinciden_con_los_de_programa_anterior(sesion, carga_mgd):
    """La inmensa mayoría de las cuentas de la apertura del programa anterior que existen tras convertir tienen el mismo nombre."""
    lineas = {l.cuenta: norm(l.texto) for l in _asientos(carga_mgd.clave)[PDF[carga_mgd.clave][1]].lineas}
    nombres = {c.codigo: norm(c.nombre) for c in sesion.scalars(select(Cuenta))}
    existentes = {c: n for c, n in lineas.items() if c in nombres}
    iguales = [c for c, n in existentes.items() if nombres[c][:10] == n[:10] or n[:10] in nombres[c] or nombres[c][:10] in n]
    assert len(existentes) >= 25
    assert len(iguales) / len(existentes) >= 0.85, sorted(set(existentes) - set(iguales))


def test_la_apertura_prevista_desde_mgd_reproduce_buena_parte_de_la_de_programa_anterior(sesion, carga_mgd):
    """Las copias de MGD acaban en el 3.er trimestre, así que no se espera coincidencia total: sirve de regresión del mapa."""
    real = _asientos(carga_mgd.clave)[PDF[carga_mgd.clave][1]].saldos
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    regularizar_ingresos_gastos(sesion, ej, date(2021, 12, 31))
    previsto = saldos_del_ejercicio(sesion, ej)
    identicas = [c for c in real if previsto.get(c) == real[c]]
    assert len(identicas) >= IDENTICAS_MINIMAS[carga_mgd.clave]
    # el capital, los inmovilizados sin movimiento nuevo y los bancos con saldo estable coinciden siempre
    assert real["10000000"] == previsto["10000000"]


def test_el_pdf_de_la_apertura_se_lee_bien(carga_mgd):
    a = _asientos(carga_mgd.clave)[PDF[carga_mgd.clave][1]]
    assert sum(l.debe for l in a.lineas) == sum(l.haber for l in a.lineas) == a.total_debe == a.total_haber
    assert a.fecha == date(2022, 1, 1) and a.lineas[0].texto.startswith(("CAPITAL", "A PORTACIONES", "RESERVA", "RESULTA"))
