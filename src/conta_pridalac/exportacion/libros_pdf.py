"""PDF de los libros que se legalizan en el Registro Mercantil: el diario, el inventario y cuentas anuales (balances de sumas y saldos y memoria), el registro de socios y el de actas.

Cada página lleva la cabecera de la empresa (domicilio, NIF y nombre), el título del libro y «Página X de Y». Se hacen con ReportLab, como el resto de PDF del programa. Los libros se entregan
a Legalia2, que los firma y los presenta; aquí sólo se generan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as lienzo
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

CERO = Decimal("0")
GRIS = colors.HexColor("#E8E8E8")


@dataclass
class Cabecera:
    domicilio: str
    cp_poblacion: str
    provincia: str
    nif: str
    nombre: str


@dataclass
class LineaAsiento:
    cuenta: str
    descripcion: str
    concepto: str
    debe: Decimal
    haber: Decimal


@dataclass
class AsientoDiario:
    numero: int
    fecha: date
    lineas: list[LineaAsiento]


@dataclass
class FilaSumas:
    cuenta: str
    nombre: str
    debe: Decimal
    haber: Decimal
    deudor: Decimal
    acreedor: Decimal
    nivel: int = 0  # 0 = subcuenta; mayor que 0, un grupo, subgrupo, cuenta…: se pone en negrita


@dataclass
class SeccionSumas:
    titulo: str
    filas: list[FilaSumas]
    totales: tuple[Decimal, Decimal, Decimal, Decimal]


@dataclass
class Bloque:
    """Un elemento de la memoria: `h` encabezado, `p` párrafo, `tabla` filas de texto, `renglon` pares «concepto … importe»."""

    tipo: str
    texto: str = ""
    filas: list[list[str]] = field(default_factory=list)


def eur(valor: Decimal | None, *, vacio_si_cero: bool = False) -> str:
    if valor is None or (vacio_si_cero and valor == 0):
        return ""
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if valor < 0 else "") + texto


def _escapar(texto: str) -> str:
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Titulo(Flowable):
    """No dibuja nada: avisa al documento de que desde esta página el título del libro es otro."""

    def __init__(self, titulo: str):
        super().__init__()
        self.titulo, self.width, self.height = titulo, 0, 0

    def draw(self):
        pass


class _Documento(BaseDocTemplate):
    def __init__(self, ruta: Path, cabecera: Cabecera, titulo: str, **kw):
        super().__init__(str(ruta), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=40 * mm, bottomMargin=16 * mm, title=titulo, author=cabecera.nombre, **kw)
        self.cabecera, self.titulo_inicial, self.titulos = cabecera, titulo, {}
        self.addPageTemplates([PageTemplate(id="libro", frames=[Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cuerpo", leftPadding=0, rightPadding=0, topPadding=0,
                                                                         bottomPadding=0)])])

    def afterFlowable(self, flowable):
        if isinstance(flowable, _Titulo):
            self.titulos[self.page] = flowable.titulo

    def titulo_de(self, pagina: int) -> str:
        previos = [p for p in self.titulos if p <= pagina]
        return self.titulos[max(previos)] if previos else self.titulo_inicial

    def crear_lienzo(self):
        doc = self

        class _Lienzo(lienzo.Canvas):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self._paginas = []

            def showPage(self):
                self._paginas.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._paginas)
                for estado in self._paginas:
                    self.__dict__.update(estado)
                    _dibujar_cabecera_y_pie(self, doc, self._pageNumber, total)
                    super().showPage()
                super().save()

        return _Lienzo


def _dibujar_cabecera_y_pie(c, doc: _Documento, pagina: int, total: int) -> None:
    h = doc.cabecera
    ancho, alto = A4
    c.saveState()
    c.setFont("Helvetica", 8.5)
    y = alto - 14 * mm
    for linea in (h.domicilio, h.cp_poblacion, h.provincia, h.nif):
        c.drawString(14 * mm, y, linea)
        y -= 3.9 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(14 * mm, y, h.nombre)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(14 * mm, alto - 36 * mm, doc.titulo_de(pagina))
    c.setStrokeColor(colors.grey)
    c.line(14 * mm, alto - 38 * mm, ancho - 14 * mm, alto - 38 * mm)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(ancho - 14 * mm, 9 * mm, f"Página {pagina} de {total}")
    c.restoreState()


def _construir(doc: _Documento, historia: list) -> int:
    doc.build(historia, canvasmaker=doc.crear_lienzo())
    return doc.page


# ---------------------------------------------------------------------------------------------------- diario

def pdf_diario(ruta: Path, cabecera: Cabecera, ejercicio: int, asientos: list[AsientoDiario]) -> int:
    """El libro diario: cada asiento con su número y su fecha, sus apuntes y la suma del asiento. Devuelve el nº de páginas."""
    titulo = f"Libro de diario Ejercicio {ejercicio}"
    doc = _Documento(ruta, cabecera, titulo)
    celda = ParagraphStyle("c", fontName="Helvetica", fontSize=7.3, leading=8.6)
    anchos = [21 * mm, 48 * mm, 58 * mm, 27 * mm, 27 * mm]
    historia: list = [_Titulo(titulo)]
    cab = Table([["Subcuenta", "Descripción", "", "Debe", "Haber"]], colWidths=anchos)
    cab.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black)]))
    historia.append(cab)
    for a in asientos:
        filas = [[f"{a.numero}   {a.fecha:%d/%m/%Y}", "", "", "", ""]]
        for l in a.lineas:
            filas.append([l.cuenta, Paragraph(_escapar(l.descripcion), celda), Paragraph(_escapar(l.concepto), celda), eur(l.debe, vacio_si_cero=True), eur(l.haber, vacio_si_cero=True)])
        filas.append(["", "", "", eur(sum((l.debe for l in a.lineas), CERO)), eur(sum((l.haber for l in a.lineas), CERO))])
        t = Table(filas, colWidths=anchos, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.3), ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"), ("BACKGROUND", (0, 0), (-1, 0), GRIS), ("SPAN", (0, 0), (2, 0)), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (3, -1), (-1, -1), 0.4, colors.grey), ("TOPPADDING", (0, 0), (-1, -1), 1.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ]))
        historia.append(KeepTogether(t) if len(filas) <= 30 else t)
        historia.append(Spacer(1, 1.5 * mm))
    return _construir(doc, historia)


# ---------------------------------------------------------------------------------------------------- inventario y cuentas anuales

def _tabla_sumas(seccion: SeccionSumas) -> Table:
    anchos = [24 * mm, 70 * mm, 23 * mm, 23 * mm, 23 * mm, 23 * mm]
    cabeza = ["Subcuenta", "Descripción", "Debe", "Haber", "Saldo deudor", "Saldo acreedor"]
    filas = [cabeza]
    negritas = []
    for i, f in enumerate(seccion.filas, 1):
        filas.append([f.cuenta, f.nombre[:60], eur(f.debe), eur(f.haber), eur(f.deudor), eur(f.acreedor)])
        if f.nivel:
            negritas.append(i)
    filas.append(["", "Totales", *(eur(x) for x in seccion.totales)])
    t = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [("FONTSIZE", (0, 0), (-1, -1), 7.2), ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
              ("TOPPADDING", (0, 0), (-1, -1), 0.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]
    estilo += [("FONTNAME", (0, i), (-1, i), "Helvetica-Bold") for i in negritas]
    t.setStyle(TableStyle(estilo))
    return t


def pdf_inventario(ruta: Path, cabecera: Cabecera, ejercicio: int, secciones: list[SeccionSumas], memoria: list[Bloque]) -> int:
    """El libro de inventario y cuentas anuales: los balances de sumas y saldos (inicial, trimestres e inventario) y la memoria."""
    doc = _Documento(ruta, cabecera, f"Inventario y cuentas anuales Ejercicio {ejercicio}")
    historia: list = []
    for i, s in enumerate(secciones):
        if i:
            historia.append(PageBreak())
        historia += [_Titulo(s.titulo), _tabla_sumas(s)]
    historia += [PageBreak(), _Titulo(f"Memoria Ejercicio {ejercicio}")]
    historia += _bloques_de_memoria(memoria)
    return _construir(doc, historia)


def pdf_memoria(ruta: Path, cabecera: Cabecera, ejercicio: int, memoria: list[Bloque]) -> int:
    """La memoria de las cuentas anuales, sola: el PDF `MEMORIA.pdf` que se adjunta al depósito de cuentas."""
    doc = _Documento(ruta, cabecera, f"Memoria Ejercicio {ejercicio}", invariant=1)  # sin fecha ni identificador del momento: el mismo contenido da el mismo PDF, y con él el mismo ZIP
    return _construir(doc, [_Titulo(f"Memoria Ejercicio {ejercicio}")] + _bloques_de_memoria(memoria))


@dataclass
class Certificacion:
    """Los datos de la certificación del acuerdo de la junta que aprueba las cuentas (la que firma el administrador y se adjunta al depósito)."""

    sociedad: str
    nif_sociedad: str
    domicilio: str  # «CL MAYOR, 21, Majadahonda, MADRID»
    cargo: str  # «administradores mancomunados»
    firmante: str
    nif_firmante: str
    lugar: str
    fecha_junta: date
    fecha_formulacion: date | None
    fecha_emision: date
    ejercicio: int
    fecha_cierre: date
    resultado: Decimal
    aplicacion: list[tuple[str, Decimal]]  # (concepto, importe) del reparto de un beneficio
    huella: str
    orden: str = "JUS/616/2022, de 30 de junio"
    presidente: str = ""
    secretario: str = ""
    reformulacion: bool | None = None  # uso de la reformulación del RDL 4/2025 (Resolución DGSJFP de 19/05/2026, apartado segundo); None: no se menciona (depósitos anteriores)


def pdf_certificacion(ruta: Path, c: Certificacion) -> int:
    """La certificación (`CAC.pdf`): el texto del programa anterior, con la huella digital del ZIP del depósito. Sin firma: se firma digitalmente con Adobe antes de adjuntarla en D2."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate

    estilos = getSampleStyleSheet()
    base = ParagraphStyle("c", parent=estilos["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.2, alignment=TA_JUSTIFY, spaceAfter=5)
    centro = ParagraphStyle("t", parent=base, alignment=TA_CENTER, fontName="Helvetica-Bold")
    fecha = lambda d: f"{d:%d/%m/%Y}"  # noqa: E731
    presidente, secretario = c.presidente or c.firmante, c.secretario or c.firmante
    historia: list = [Paragraph("JUNTA UNIVERSAL. CUENTAS PYME", centro), Paragraph("Sin informe de Gestión ni Informe de Auditoria", ParagraphStyle("s", parent=centro, fontName="Helvetica")), Spacer(1, 4 * mm),
                      Paragraph(_escapar(f"{c.firmante} en su calidad de {c.cargo} de la sociedad {c.sociedad}, con domicilio en {c.domicilio} y C.I.F. {c.nif_sociedad}"), base),
                      Spacer(1, 2 * mm), Paragraph("CERTIFICO", centro), Paragraph("Que del Libro de Actas de la entidad resulta lo siguiente:", base),
                      Paragraph(_escapar(f"1º - Que en fecha {fecha(c.fecha_junta)} y en {c.lugar} se reunió su Junta General con el CARÁCTER DE UNIVERSAL."), base),
                      Paragraph(_escapar(f"2º - Que en el acta figura el nombre y la firma de los asistentes, quienes al finalizar la reunión aprobaron el acta, la cual fue firmada por el Presidente {presidente} y el Secretario de la Junta {secretario}."), base),
                      Paragraph("3.º - Que fueron adoptados por unanimidad los siguientes acuerdos:", base),
                      Paragraph(_escapar(f"a) APROBAR LAS CUENTAS ANUALES correspondientes al ejercicio {c.ejercicio} cerrado el {fecha(c.fecha_cierre)}"), base),
                      Paragraph("b) APLICAR EL RESULTADO en los siguientes términos:", base)]
    if c.resultado < 0:
        historia.append(Paragraph(_escapar(f"Debido a las pérdidas obtenidas durante el ejercicio {c.ejercicio}, con un importe de {eur(-c.resultado)}€ en la cuenta de Pérdidas y Ganancias, se acuerda que el resultado negativo se aplicará para compensarse con futuros beneficios."), base))
    elif c.resultado == 0:
        historia.append(Paragraph(_escapar(f"El ejercicio {c.ejercicio} se cierra sin beneficio ni pérdida: no hay resultado que aplicar."), base))
    else:
        filas = [[f"- {concepto}", eur(importe) if importe else ""] for concepto, importe in c.aplicacion] + [["TOTAL:", eur(sum((i for _, i in c.aplicacion), Decimal("0")))]]
        tabla = Table(filas, colWidths=[110 * mm, 30 * mm])
        tabla.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.grey)]))
        historia += [tabla, Spacer(1, 3 * mm)]
    formulacion = fecha(c.fecha_formulacion) if c.fecha_formulacion else "—"
    historia += [Spacer(1, 2 * mm), Paragraph("IGUALMENTE CERTIFICO", centro),
                 Paragraph(_escapar(f"1) Las Cuentas Anuales aprobadas son las que se presentan telemáticamente al Registro, conforme a lo dispuesto en la Orden {c.orden}, con la huella digital siguiente: {c.huella}"), base),
                 Paragraph("2) Que la sociedad puede formular las cuentas conforme al Plan General de Contabilidad de PYMES (R.D. 1159/2010) y no está obligada a someter sus cuentas a verificación de auditor ni a elaborar el Informe de Gestión de conformidad con los artículos 253 y ss. del Texto Refundido de la Ley de Sociedades de Capital.", base),
                 Paragraph(_escapar(f"3) Que las cuentas anuales han sido formuladas el día {formulacion}, habiendo sido firmadas por todos los miembros del órgano de administración vigentes en dicha fecha."), base),
                 Paragraph("4) Que la Sociedad no ha realizado operaciones con participaciones propias durante dicho ejercicio.", base),
                 *([Paragraph("5) Que la Sociedad " + ("SÍ" if c.reformulacion else "no") + " ha hecho uso de la previsión de reformulación de cuentas anuales contenida en la disposición adicional primera del Real Decreto-ley 4/2025, de 8 de abril.", base)]
                   if c.reformulacion is not None else []),
                 Paragraph(_escapar(f"Y para que así conste, expido la presente certificación en {c.lugar}, a {fecha(c.fecha_emision)}."), base), Spacer(1, 6 * mm), Paragraph("FIRMA", base), Spacer(1, 22 * mm),
                 Paragraph(_escapar(c.firmante), ParagraphStyle("f", parent=base, alignment=0, spaceAfter=0)), Paragraph(_escapar(c.nif_firmante), ParagraphStyle("n", parent=base, alignment=0))]
    doc = SimpleDocTemplate(str(ruta), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=16 * mm, bottomMargin=14 * mm, title="Certificación del acuerdo de la junta")
    doc.build(historia)
    from pypdf import PdfReader

    return len(PdfReader(str(ruta)).pages)


def _bloques_de_memoria(memoria: list[Bloque]) -> list:
    estilos = getSampleStyleSheet()
    parrafo = ParagraphStyle("p", parent=estilos["BodyText"], fontName="Helvetica", fontSize=8.8, leading=11.2, alignment=TA_JUSTIFY, spaceAfter=4)
    encabezado = ParagraphStyle("h", parent=parrafo, fontName="Helvetica-Bold", fontSize=10, spaceBefore=6, spaceAfter=3, alignment=0)
    historia: list = []
    for b in memoria:
        if b.tipo == "h":
            historia.append(Paragraph(_escapar(b.texto), encabezado))
        elif b.tipo == "p":
            historia.append(Paragraph(_escapar(b.texto), parrafo))
        elif b.tipo == "tabla":
            t = Table(b.filas, colWidths=[90 * mm, 50 * mm])
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
            historia += [t, Spacer(1, 3 * mm)]
        elif b.tipo == "renglon":
            t = Table(b.filas, colWidths=[140 * mm, 40 * mm])
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
            historia += [t, Spacer(1, 3 * mm)]
    return historia


# ---------------------------------------------------------------------------------------------------- registro de socios

@dataclass
class MovimientoLibro:
    fecha: date
    tipo: str
    concepto: str
    participaciones: int
    desde: int | None
    hasta: int | None
    valor_nominal: str
    importe: Decimal


@dataclass
class SocioLibro:
    nif: str
    nombre: str
    nacionalidad: str
    nacimiento: str
    domicilio: str
    poblacion: str
    provincia: str
    profesion: str
    estado_civil: str
    movimientos: list[MovimientoLibro]
    total_participaciones: int
    total_importe: Decimal
    porcentaje: Decimal


def _entero(n: int | None) -> str:
    return "" if n is None else f"{n:,}".replace(",", ".")


def pdf_socios(ruta: Path, cabecera: Cabecera, ejercicio: int, registro: str, socios: list[SocioLibro], capital: Decimal) -> int:
    """El libro registro de socios: cada socio con sus datos, sus movimientos de participaciones y su total; al final, el capital social."""
    titulo = f"Libro Registro de Socios Ejercicio {ejercicio}"
    doc = _Documento(ruta, cabecera, titulo)
    celda = ParagraphStyle("c", fontName="Helvetica", fontSize=7.8, leading=9.4)
    etiqueta = ParagraphStyle("e", parent=celda, fontName="Helvetica-Bold")
    cabeza = ParagraphStyle("k", parent=celda, fontName="Helvetica-Bold", fontSize=7.2, leading=8.6)
    derecha = ParagraphStyle("d", parent=celda, alignment=2)

    def e(texto):  # etiqueta que se parte en dos líneas si no cabe, en vez de pisar el dato de al lado
        return Paragraph(_escapar(texto), etiqueta)

    def v(texto):
        return Paragraph(_escapar(texto), celda)

    historia: list = [_Titulo(titulo)]
    for s in socios:
        datos = Table([
            [e("N.I.F.:"), v(s.nif), e("Apellidos, Nombre / Razón Social:"), v(s.nombre)],
            [e("Nacionalidad:"), v(s.nacionalidad), e("Fecha de nacimiento:"), v(s.nacimiento)],
            [e("Domicilio:"), v(s.domicilio), e("Población:"), v(s.poblacion)],
            [e("Provincia:"), v(s.provincia), e("Profesión:"), v(s.profesion)],
            [e("Estado civil:"), v(s.estado_civil), e("Registro Mercantil:"), v(registro)],
        ], colWidths=[23 * mm, 55 * mm, 36 * mm, 66 * mm])
        datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), GRIS), ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        filas = [[Paragraph(t, cabeza) for t in ("Fecha", "Tipo", "Concepto", "Nº participaciones", "De", "A", "Valor nominal", "Importe participaciones")]]
        for m in s.movimientos:
            filas.append([f"{m.fecha:%d/%m/%Y}", Paragraph(_escapar(m.tipo), celda), v(m.concepto), _entero(m.participaciones), _entero(m.desde), _entero(m.hasta), m.valor_nominal.replace(".", ","), eur(m.importe)])
        filas.append(["", "", Paragraph("<b>Total participaciones socio</b>", celda), _entero(s.total_participaciones), "", "", Paragraph("<b>% participación</b>", derecha), f"{eur(s.porcentaje)} %"])
        filas.append(["", "", Paragraph("<b>Total importe participaciones socio</b>", celda), "", "", "", "", eur(s.total_importe)])
        mov = Table(filas, colWidths=[19 * mm, 24 * mm, 43 * mm, 21 * mm, 14 * mm, 14 * mm, 20 * mm, 25 * mm], repeatRows=1)
        mov.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black), ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("FONTNAME", (3, -2), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -2), (-1, -2), 0.5, colors.grey), ("TOPPADDING", (0, 0), (-1, -1), 1.3),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3)]))
        historia.append(KeepTogether([datos, Spacer(1, 1.5 * mm), mov, Spacer(1, 5 * mm)]))
    cierre = Table([["Total Capital Social:", eur(capital)]], colWidths=[50 * mm, 40 * mm])
    cierre.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    historia.append(cierre)
    return _construir(doc, historia)


# ---------------------------------------------------------------------------------------------------- registro de actas

@dataclass
class ActaLibro:
    titulo: str
    asistentes: list[str]
    apertura: str
    orden_del_dia: list[str]
    resumen: list[str]
    intervenciones: list[str]
    acuerdos: list[str]
    votaciones: list[str]
    cierre: str
    presidente: tuple[str, str]  # (nombre, NIF)
    secretario: tuple[str, str]


def pdf_actas(ruta: Path, cabecera: Cabecera, ejercicio: int, actas: list[ActaLibro]) -> int:
    """El libro registro de actas: cada acta empieza en página nueva, con sus apartados y las firmas del presidente y del secretario."""
    titulo = f"Libro registro de actas Ejercicio {ejercicio}"
    doc = _Documento(ruta, cabecera, titulo)
    estilos = getSampleStyleSheet()
    cuerpo = ParagraphStyle("p", parent=estilos["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12, alignment=TA_JUSTIFY, spaceAfter=3)
    seccion = ParagraphStyle("s", parent=cuerpo, fontName="Helvetica-Bold", fontSize=9.5, spaceBefore=7, spaceAfter=3, alignment=0)
    grande = ParagraphStyle("t", parent=cuerpo, fontName="Helvetica-Bold", fontSize=11, spaceAfter=5, alignment=0)
    historia: list = [_Titulo(titulo)]
    for i, a in enumerate(actas):
        if i:
            historia.append(PageBreak())
        historia.append(Paragraph(_escapar(a.titulo), grande))
        historia.append(Paragraph("Asistentes", seccion))
        historia += [Paragraph(_escapar(x), cuerpo) for x in a.asistentes]
        historia.append(Spacer(1, 2 * mm))
        historia.append(Paragraph(_escapar(a.apertura), cuerpo))
        for nombre, lineas in (("ORDEN DEL DÍA", a.orden_del_dia), ("RESUMEN DE LOS ASUNTOS DEBATIDOS", a.resumen), ("INTERVENCIONES", a.intervenciones), ("ACUERDOS ADOPTADOS", a.acuerdos),
                               ("RESULTADOS DE LAS VOTACIONES", a.votaciones)):
            if lineas:
                historia.append(Paragraph(nombre, seccion))
                historia += [Paragraph(_escapar(x), cuerpo) for x in lineas]
        historia += [Spacer(1, 3 * mm), Paragraph(_escapar(a.cierre), cuerpo), Spacer(1, 12 * mm)]
        firmas = Table([["Vº Bº PRESIDENTE", "EL SECRETARIO"], ["", ""], [a.presidente[1], a.secretario[1]], [a.presidente[0], a.secretario[0]]], colWidths=[90 * mm, 90 * mm], rowHeights=[6 * mm, 14 * mm, 5 * mm, 5 * mm])
        firmas.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        historia.append(KeepTogether(firmas))
    return _construir(doc, historia)
