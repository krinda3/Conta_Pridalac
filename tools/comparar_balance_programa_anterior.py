"""Compara el "Balance de sumas y saldos" del programa anterior (PDF) con las sumas del Diario.dbf de MGD, por cuenta de 3 dígitos.

Uso: python tools/comparar_balance_programa_anterior.py <Diario.dbf> <balance.pdf>
El balance incluye apertura, regularización y cierre, así que se suman todos los apuntes del Diario.
"""
import re
import sys
from collections import defaultdict
from decimal import Decimal

from dbfread import DBF
from pypdf import PdfReader

IMPORTE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
CERO = Decimal("0.00")


def num(s):
    return Decimal(s.replace(".", "").replace(",", "."))


def leer_balance(ruta):
    """{cuenta3: (debe, haber)}. Las columnas se distinguen por la posición final de cada importe."""
    texto = "\n".join(p.extract_text(extraction_mode="layout") for p in PdfReader(ruta).pages)
    ancla = next(l for l in texto.splitlines() if "DEBE" in l and "HABER" in l)
    fin_debe, fin_haber = ancla.index("DEBE") + 4, ancla.index("HABER") + 5
    filas = {}
    for linea in texto.splitlines():
        m = re.match(r"^\s+(\d{3})\. ", linea)
        if not m:
            continue
        debe = haber = CERO
        for im in IMPORTE.finditer(linea):
            # la columna más cercana al final del importe (la tolerancia absorbe el desfase entre cabecera y cifras)
            if abs(im.end() - fin_debe) <= abs(im.end() - fin_haber):
                debe = num(im.group())
            else:
                haber = num(im.group())
        filas[m.group(1)] = (debe, haber)
    return filas


def sumas_diario(ruta):
    s = defaultdict(lambda: [CERO, CERO])
    for f in DBF(ruta, encoding="latin-1", ignore_missing_memofile=True):
        c = (f["CUENTA"] or "").strip()
        if not c:
            continue
        i = Decimal(str(f["IMPORTE"]))
        s[c[:3]][0 if i > 0 else 1] += abs(i)
    return {c: (d, h) for c, (d, h) in s.items()}


def main(diario, pdf):
    real, mio = leer_balance(pdf), sumas_diario(diario)
    difs = {c: (real.get(c, (CERO, CERO)), mio.get(c, (CERO, CERO))) for c in set(real) | set(mio) if real.get(c, (CERO, CERO)) != mio.get(c, (CERO, CERO))}
    return real, mio, difs


if __name__ == "__main__":
    real, mio, difs = main(*sys.argv[1:3])
    print(f"cuentas en el balance {len(real)} · en el Diario {len(mio)} · diferencias {len(difs)}")
    for c, (r, m) in sorted(difs.items()):
        print(f"  {c}: ANTERIOR {r[0]:>12} {r[1]:>12} · MGD {m[0]:>12} {m[1]:>12}")
