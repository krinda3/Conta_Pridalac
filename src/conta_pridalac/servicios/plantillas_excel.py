"""Plantillas de Excel para cargar facturas sin depender de Verifactu.

Las columnas son las que lee `servicios/trimestre.py` (`COLUMNAS` y `COLUMNAS_EMITIDAS`); un test comprueba que cada una de las que lee el lector está aquí y que una plantilla con una factura escrita se
carga. Cada plantilla lleva la hoja de facturas (vacía, solo la cabecera) y una hoja «Instrucciones»; el lector solo mira la primera hoja.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# (cabecera, qué es, obligatoria, formato)
RECIBIDAS = [
    ("Empresa", "Nombre del proveedor tal como sale en la factura", True, None),
    ("CIF", "NIF o CIF del proveedor (sin espacios ni guiones)", False, None),
    ("FechaFactura", "Fecha de la factura", True, "dd/mm/yyyy"),
    ("NumFactura", "Número de la factura. Aunque el programa no lo exige, ponga siempre uno: con él se detectan las duplicadas", False, None),
    ("BaseImponible", "Base imponible", False, "#,##0.00"),
    ("IVA", "Porcentaje de IVA (21, 10, 4, 0)", False, "0.00"),
    ("MontoIVA", "Cuota de IVA", False, "#,##0.00"),
    ("MontoTotal", "Total de la factura, con IVA", True, "#,##0.00"),
    ("RutaCompleta", "Ruta del PDF de la factura en su equipo (opcional)", False, None),
    ("FechaContable", "Fecha contable si no es el último día del trimestre (opcional)", False, "dd/mm/yyyy"),
    ("IVA2", "Segundo tipo de IVA, si la factura tiene más de uno (opcional)", False, "0.00"),
    ("MontoIVA2", "Cuota del segundo tipo (opcional)", False, "#,##0.00"),
    ("IVA3", "Tercer tipo de IVA (opcional)", False, "0.00"),
    ("MontoIVA3", "Cuota del tercer tipo (opcional)", False, "#,##0.00"),
]
EMITIDAS = [
    ("N Factura", "Número de la factura emitida", True, None),
    ("Fecha Expedición", "Fecha de expedición", True, "dd/mm/yyyy"),
    ("Emisor NIF", "NIF de la empresa que emite (la de esta contabilidad)", False, None),
    ("Cliente Nombre", "Nombre del cliente", True, None),
    ("Cliente NIF", "NIF o CIF del cliente", False, None),
    ("Base Imponible", "Base imponible", False, "#,##0.00"),
    ("IVA", "Porcentaje de IVA (21, 10, 4, 0)", False, "0.00"),
    ("Cuota IVA", "Cuota de IVA", False, "#,##0.00"),
    ("Total", "Total de la factura, con IVA", True, "#,##0.00"),
    ("Estado", "Estado de la factura (opcional)", False, None),
]
TIPOS = {
    "recibidas": ("Facturas recibidas", RECIBIDAS, "Compras y gastos. Una fila por factura. El proveedor nuevo se da de alta al elegir los proveedores del trimestre."),
    "emitidas": ("Facturas emitidas", EMITIDAS, "Ventas e ingresos. Una fila por factura. Debe ser el Excel de esta empresa."),
}


def plantilla(tipo: str) -> tuple[bytes, str]:
    """(contenido del .xlsx, nombre del fichero) de la plantilla de facturas `recibidas` o `emitidas`."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de plantilla desconocido: {tipo}")
    titulo, columnas, explicacion = TIPOS[tipo]
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo
    relleno = PatternFill("solid", fgColor="DDEBC9")
    for i, (cabecera, _, obligatoria, formato) in enumerate(columnas, start=1):
        celda = hoja.cell(row=1, column=i, value=cabecera)
        celda.font, celda.fill = Font(bold=True), relleno
        hoja.column_dimensions[get_column_letter(i)].width = max(14, len(cabecera) + 4)
        if formato:
            for fila in range(2, 202):
                hoja.cell(row=fila, column=i).number_format = formato
    hoja.freeze_panes = "A2"
    ayuda = libro.create_sheet("Instrucciones")
    ayuda.column_dimensions["A"].width = 22
    ayuda.column_dimensions["B"].width = 14
    ayuda.column_dimensions["C"].width = 100
    filas = [(f"Plantilla de {titulo.lower()} para Conta Pridalac", None, None), (explicacion, None, None), (None, None, None),
             ("Reglas", None, None),
             ("1.", None, "Escriba las facturas en la primera hoja, desde la fila 2, sin dejar la cabecera de la fila 1 ni cambiar el nombre de las columnas."),
             ("2.", None, "Las columnas se reconocen por su nombre, sin importar mayúsculas, tildes ni espacios; el orden da igual y puede añadir columnas extra, que se ignoran."),
             ("3.", None, "Los importes, con punto o coma decimal. Las fechas, como fecha de Excel (dd/mm/aaaa)."),
             ("4.", None, "No deje filas de ejemplo: todo lo que haya en la hoja se carga como una factura."),
             ("5.", None, "En Conta: Trimestre → «Cargar facturas» (recibidas) o «Cargar emitidas», y elija este fichero. Las facturas que ya estaban no se repiten."),
             (None, None, None), ("Columna", "Obligatoria", "Qué es")]
    for fila in filas:
        ayuda.append(list(fila))
    for cabecera, descripcion, obligatoria, _ in columnas:
        ayuda.append([cabecera, "sí" if obligatoria else "no", descripcion])
    ayuda["A1"].font = Font(bold=True, size=13)
    ayuda["A4"].font = Font(bold=True)
    for celda in ayuda[11]:
        celda.font, celda.fill = Font(bold=True), relleno
    for fila in ayuda.iter_rows(min_row=1):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
    ayuda.merge_cells("A2:C2")
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue(), f"plantilla_{tipo}.xlsx"
