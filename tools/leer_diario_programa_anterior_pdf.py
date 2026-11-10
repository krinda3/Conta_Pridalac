"""Lee un «Libro de diario» del programa anterior en PDF (p. ej. los asientos automáticos de un año) y devuelve los asientos.

Uso: python tools/leer_diario_programa_anterior_pdf.py <fichero.pdf>

El programa anterior imprime Debe y Haber en columnas; `pypdf` en modo `layout` las conserva, y se asigna cada importe a su columna por
la posición en la que termina (la cabecera «Debe  Haber» marca dónde acaba cada columna). Devuelve, por asiento
(`9.1`, `9.2`…): fecha, líneas (cuenta, texto, concepto, debe, haber) y los totales que imprime el programa anterior, que se usan para
comprobar la lectura.
"""
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader

IMPORTE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
CABECERA_ASIENTO = re.compile(r"^(\d+\.\d+)\s+(\d{2}/\d{2}/\d{4})\s+\d+\s*$")
LINEA = re.compile(r"^(\d{8})\s{2,}(.*)$")


def a_decimal(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


@dataclass
class LineaDiario:
    cuenta: str
    texto: str
    debe: Decimal
    haber: Decimal


@dataclass
class AsientoPdf:
    id: str
    fecha: object
    lineas: list[LineaDiario] = field(default_factory=list)
    total_debe: Decimal | None = None
    total_haber: Decimal | None = None

    @property
    def saldos(self) -> dict[str, Decimal]:
        s: dict[str, Decimal] = {}
        for l in self.lineas:
            s[l.cuenta] = s.get(l.cuenta, Decimal(0)) + l.debe - l.haber
        return {c: v for c, v in s.items() if v}


def leer(ruta: str) -> list[AsientoPdf]:
    paginas = [p.extract_text(extraction_mode="layout") or "" for p in PdfReader(ruta).pages]
    asientos: list[AsientoPdf] = []
    actual: AsientoPdf | None = None
    fin_debe = fin_haber = None
    for pagina in paginas:
        for linea in pagina.splitlines():
            if "Debe" in linea and "Haber" in linea:
                fin_debe, fin_haber = linea.index("Debe") + 4, linea.index("Haber") + 5
                continue
            texto = linea.strip()
            m = CABECERA_ASIENTO.match(texto)
            if m:
                actual = AsientoPdf(m.group(1), datetime.strptime(m.group(2), "%d/%m/%Y").date())
                asientos.append(actual)
                continue
            if actual is None or fin_debe is None:
                continue
            importes = [(m.group(), m.end()) for m in IMPORTE.finditer(linea)]
            m = LINEA.match(texto)
            if m and importes:
                # el importe pertenece a la columna cuyo final está más cerca
                valor, fin = importes[-1]
                en_haber = abs(fin - fin_haber) < abs(fin - fin_debe)
                concepto = IMPORTE.sub("", m.group(2)).strip()
                actual.lineas.append(
                    LineaDiario(m.group(1), concepto, Decimal(0) if en_haber else a_decimal(valor), a_decimal(valor) if en_haber else Decimal(0))
                )
            elif len(importes) == 2 and not LINEA.match(texto):  # fila de totales «127,82 127,82»
                actual.total_debe, actual.total_haber = a_decimal(importes[0][0]), a_decimal(importes[1][0])
    return asientos


if __name__ == "__main__":
    for a in leer(sys.argv[1]):
        cuadra = a.total_debe == sum(l.debe for l in a.lineas) and a.total_haber == sum(l.haber for l in a.lineas)
        print(f"{a.id} {a.fecha} · {len(a.lineas)} líneas · debe {sum(l.debe for l in a.lineas)} haber {sum(l.haber for l in a.lineas)} · totales del PDF {'coinciden' if cuadra else 'NO coinciden'}")
