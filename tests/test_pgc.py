"""Catálogo PGC (grupos, subgrupos y cuentas de 3 dígitos) y su uso en el balance agrupado."""
import re
import unicodedata
from pathlib import Path

import pytest

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.domain.pgc import CUENTAS_3, GRUPOS, SUBGRUPOS, nombre_pgc
from conta_pridalac.servicios.informes import balance_sumas_y_saldos
from test_informes import ej  # noqa: F401  (fixture)

RAIZ = Path(__file__).resolve().parents[1]
norm = lambda s: re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode())


def test_nombres_conocidos():
    assert nombre_pgc("1") == "Financiación básica"
    assert nombre_pgc("57") == "Tesorería"
    assert nombre_pgc("472") == "Hacienda pública, IVA soportado"
    assert nombre_pgc("57200001") == "" and nombre_pgc("999") == ""


def test_el_catalogo_es_coherente():
    assert len(CUENTAS_3) > 250 and all(len(c) == 3 and c.isdigit() for c in CUENTAS_3)
    assert all(c[:2] in SUBGRUPOS or c[:2] in ("27", "37", "38", "42", "45", "72", "78") for c in CUENTAS_3), "cuenta de un subgrupo sin nombre"
    assert all(c[0] in GRUPOS for c in SUBGRUPOS)


def test_el_balance_agrupado_pone_nombres_pgc(sesion, ej):
    e = sesion.get(Ejercicio, ej.id)
    nombres = {f.cuenta: f.nombre for f in balance_sumas_y_saldos(sesion, e, nivel=3).filas}
    assert nombres["572"].startswith("Bancos") and nombres["629"] == "Otros servicios"
    assert {f.cuenta: f.nombre for f in balance_sumas_y_saldos(sesion, e, nivel=2).filas}["57"] == "Tesorería"


@pytest.mark.datos_reales
@pytest.mark.parametrize("empresa", ["EMPRESA A", "EMPRESA B"])
def test_nombres_coinciden_con_los_del_balance_de_programa_anterior(empresa):
    """Subgrupos (2 dígitos) y cuentas (3) que aparecen en el balance del programa anterior 2020 llevan el mismo nombre (tolerando el recorte)."""
    from pypdf import PdfReader

    pdf = RAIZ / "docs" / "Exportaciones del programa anterior" / f"{empresa} Balance de sumas y saldos del año 2020.pdf"
    if not pdf.exists():
        pytest.skip("Falta el balance en PDF")
    texto = "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(str(pdf)).pages)
    revisadas, distintas = 0, []
    for m in re.finditer(r"^\s+(\d{2,3})\.? (\S.*?)\s{2,}", texto, re.M):
        codigo, titulo = m.group(1), norm(m.group(2))
        propio = norm(nombre_pgc(codigo))
        if not propio or len(titulo) < 12:
            continue
        revisadas += 1
        if not (propio.startswith(titulo[:20]) or titulo.startswith(propio[:20])):
            distintas.append((codigo, titulo, propio))
    assert revisadas >= 20
    # MGD usa algún título del PGC anterior (p. ej. 520 «Préstamos a corto plazo…» frente a «Deudas a corto plazo…» en el programa anterior)
    assert len(distintas) <= 3, distintas
