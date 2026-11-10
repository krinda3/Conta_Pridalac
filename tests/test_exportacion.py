"""Exportación de informes a Excel y PDF."""
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.exportacion import Columna, Tabla, a_excel, a_pdf
from conta_pridalac.exportacion.tabla import DINERO, FECHA, formatear
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, libro_diario, libro_iva, mayor
from conta_pridalac.servicios.tablas_informes import tabla_balance, tabla_diario, tabla_libro_iva, tabla_mayor
from test_informes import ej  # noqa: F401  (fixture)

D = Decimal


def test_formato_espanol_de_importes_y_fechas():
    assert formatear(D("1234567.8"), DINERO) == "1.234.567,80"
    assert formatear(D("-5"), DINERO) == "-5,00"
    assert formatear(date(2026, 3, 9), FECHA) == "09/03/2026"
    assert formatear(None, DINERO) == ""


def test_la_tabla_valida_sus_dimensiones():
    with pytest.raises(ValueError):
        Tabla("x", [Columna("a")], [["1", "2"]])
    with pytest.raises(ValueError):
        Tabla("x", [Columna("a")], [["1"]], totales=[1, 2])


def _texto_pdf(ruta):
    return "\n".join(p.extract_text() for p in PdfReader(str(ruta)).pages)


def test_diario_a_excel_y_pdf(sesion, ej, tmp_path):
    ej = sesion.get(Ejercicio, ej.id)
    t = tabla_diario(libro_diario(sesion, ej), ej)
    hoja = load_workbook(a_excel(t, tmp_path / "diario.xlsx")).active
    filas = list(hoja.iter_rows(values_only=True))
    cab = next(i for i, f in enumerate(filas) if f[0] == "Fecha")
    assert filas[cab][5:7] == ("Debe", "Haber")
    datos = filas[cab + 1 : cab + 1 + 8]
    assert datos[0][0].date() == date(2026, 1, 2) and datos[0][5] == 1000.0 and datos[0][2] == "57200001"
    assert filas[cab + 9][4:7] == ("Totales", 1450.0, 1450.0)
    assert hoja.freeze_panes == f"A{cab + 2}"
    texto = _texto_pdf(a_pdf(t, tmp_path / "diario.pdf"))
    assert "Libro Diario" in texto and "1.450,00" in texto and "Prueba" in texto and "BANCO" in texto


def test_mayor_con_saldo_anterior(sesion, ej, tmp_path):
    ej = sesion.get(Ejercicio, ej.id)
    t = tabla_mayor(mayor(sesion, ej, "57200001", desde=date(2026, 3, 1)), ej, desde=date(2026, 3, 1))
    assert t.filas[0][2] == "Saldo anterior" and t.filas[0][5] == D("1000.00")
    assert t.totales[5] == D("750.00")
    assert "Mayor de 57200001 BANCO" in _texto_pdf(a_pdf(t, tmp_path / "m.pdf"))


def test_balance_a_pdf_y_excel(sesion, ej, tmp_path):
    ej = sesion.get(Ejercicio, ej.id)
    t = tabla_balance(balance_sumas_y_saldos(sesion, ej, nivel=3), ej, nivel=3)
    assert "3 dígitos" in t.titulo and t.totales[2] == t.totales[3] == D("1450.00")
    assert t.totales[4] == t.totales[5]  # saldos deudores = acreedores en un diario cuadrado
    a_excel(t, tmp_path / "b.xlsx")
    assert "Saldo acreedor" in _texto_pdf(a_pdf(t, tmp_path / "b.pdf"))


@pytest.mark.datos_reales
def test_libro_iva_real_a_varias_paginas(sesion, carga_mgd, tmp_path):
    e = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    libro = libro_iva(sesion, e, "R")
    t = tabla_libro_iva(libro, e)
    hoja = load_workbook(a_excel(t, tmp_path / "iva.xlsx")).active
    assert hoja.max_row >= len(libro.lineas) + 4
    pdf = PdfReader(str(a_pdf(t, tmp_path / "iva.pdf")))
    assert "Libro de IVA" in pdf.pages[0].extract_text()
    assert f"{libro.total_base:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") in _texto_pdf(tmp_path / "iva.pdf")
