"""Exportación de una `Tabla` a Excel (.xlsx): importes y fechas son valores reales, no texto."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, PORCENTAJE, Tabla, formatear

FORMATOS = {DINERO: "#,##0.00", PORCENTAJE: "0.00", ENTERO: "0", FECHA: "DD/MM/YYYY"}


def a_excel(tabla: Tabla, ruta: str | Path) -> Path:
    libro = Workbook()
    hoja = libro.active
    hoja.title = (tabla.titulo[:28] or "Informe").replace("/", "-")
    fila = 1
    hoja.cell(fila, 1, tabla.titulo).font = Font(bold=True, size=14)
    fila += 1
    if tabla.subtitulo:
        hoja.cell(fila, 1, tabla.subtitulo)
        fila += 1
    fila += 1
    cabecera = fila
    for c, col in enumerate(tabla.columnas, start=1):
        celda = hoja.cell(fila, c, col.titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="305496")
        celda.alignment = Alignment(horizontal="right" if col.tipo in (DINERO, PORCENTAJE, ENTERO) else "left", wrap_text=True)
    for datos in tabla.filas:
        fila += 1
        _escribir(hoja, fila, tabla, datos, negrita=False)
    if tabla.totales is not None:
        fila += 1
        _escribir(hoja, fila, tabla, tabla.totales, negrita=True)
    for nota in tabla.notas:
        fila += 2
        hoja.cell(fila, 1, nota).font = Font(italic=True)
    hoja.freeze_panes = hoja.cell(cabecera + 1, 1)
    if tabla.filas:
        hoja.auto_filter.ref = f"A{cabecera}:{get_column_letter(len(tabla.columnas))}{cabecera + len(tabla.filas)}"
    for c, col in enumerate(tabla.columnas, start=1):
        largo = max([len(col.titulo)] + [len(formatear(f[c - 1], col.tipo)) for f in tabla.filas[:500]] + [8])
        hoja.column_dimensions[get_column_letter(c)].width = min(largo + 2, 60)
    ruta = Path(ruta)
    libro.save(ruta)
    return ruta


def _escribir(hoja, fila: int, tabla: Tabla, datos: list, *, negrita: bool) -> None:
    for c, (col, valor) in enumerate(zip(tabla.columnas, datos), start=1):
        if valor is None:
            continue
        celda = hoja.cell(fila, c, float(valor) if isinstance(valor, Decimal) else valor)
        if col.tipo in FORMATOS:
            celda.number_format = FORMATOS[col.tipo]
        if negrita:
            celda.font = Font(bold=True)
