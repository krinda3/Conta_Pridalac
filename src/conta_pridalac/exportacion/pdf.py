"""Exportación de una `Tabla` a PDF (A4 apaisado, cabecera repetida en cada página, número de página)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from conta_pridalac.exportacion.tabla import DINERO, ENTERO, PORCENTAJE, Tabla, formatear

AZUL = colors.HexColor("#305496")


def a_pdf(tabla: Tabla, ruta: str | Path) -> Path:
    ruta = Path(ruta)
    estilos = getSampleStyleSheet()
    celda = ParagraphStyle("celda", parent=estilos["BodyText"], fontSize=7.5, leading=9)
    doc = SimpleDocTemplate(
        str(ruta), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
        title=tabla.titulo,
    )
    ancho_util = doc.width
    pesos = [c.ancho for c in tabla.columnas]
    anchos = [ancho_util * p / sum(pesos) for p in pesos]
    derecha = [i for i, c in enumerate(tabla.columnas) if c.tipo in (DINERO, PORCENTAJE, ENTERO)]

    def texto(valor, col):
        t = formatear(valor, col.tipo)
        return t if col.tipo != "texto" else Paragraph(t.replace("&", "&amp;").replace("<", "&lt;"), celda)

    datos = [[Paragraph(f"<b>{c.titulo}</b>", ParagraphStyle("cab", parent=celda, textColor=colors.white)) for c in tabla.columnas]]
    datos += [[texto(v, c) for v, c in zip(fila, tabla.columnas)] for fila in tabla.filas]
    if tabla.totales is not None:
        datos.append([texto(v, c) for v, c in zip(tabla.totales, tabla.columnas)])
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]
    estilo += [("ALIGN", (i, 0), (i, -1), "RIGHT") for i in derecha]
    if tabla.totales is not None:
        estilo += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black)]
    historia = [Paragraph(f"<b>{tabla.titulo}</b>", estilos["Title"])]
    if tabla.subtitulo:
        historia.append(Paragraph(tabla.subtitulo, estilos["Normal"]))
    historia.append(Spacer(1, 4 * mm))
    historia.append(Table(datos, colWidths=anchos, repeatRows=1, style=TableStyle(estilo)))
    for nota in tabla.notas:
        historia += [Spacer(1, 3 * mm), Paragraph(f"<i>{nota}</i>", estilos["Normal"])]

    def pie(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(documento.pagesize[0] - 12 * mm, 7 * mm, f"Página {canvas.getPageNumber()}")
        canvas.drawString(12 * mm, 7 * mm, tabla.titulo)
        canvas.restoreState()

    doc.build(historia, onFirstPage=pie, onLaterPages=pie)
    return ruta
