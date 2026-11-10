"""Genera `domain/pgc_esfl.py`: el cuadro de cuentas del plan de pequeñas y medianas entidades sin fines lucrativos (PGC-PyMESFL).

Uso: python tools/generar_pgc_esfl.py <cuadro de cuentas.xlsx> <BOE-A-2013-3736.pdf>

El Excel da el código y la jerarquía de cada cuenta; el BOE (Resolución del ICAC de 26-3-2013, cuarta parte: cuadro de cuentas) da el nombre oficial.
El Excel tiene erratas («dusoso», «benecifios», «renumeraciones»…) y el texto del BOE alguna de numeración (369 sale como 269), así que se toma el
nombre del BOE cuando se parece lo bastante al del Excel y, si no, el del Excel. Los nombres se pasan a frase (el cuadro oficial pone los grupos en mayúsculas).
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl
from pypdf import PdfReader

PARECIDO = 0.6


def _norma(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower())


def limpio(nombre: str) -> str:
    n = re.sub(r"\s+", " ", str(nombre)).strip().rstrip(".").strip()
    if n.isupper():
        n = n.capitalize()
    return re.sub(r"\b(iva|irpf)\b", lambda m: m.group(1).upper(), n, flags=re.IGNORECASE)


def nombres_del_boe(ruta_pdf: str) -> dict[str, str]:
    texto = "\n".join(p.extract_text() or "" for p in PdfReader(ruta_pdf).pages)
    inicio = re.search(r"CUARTA PARTE\s+Cuadro de cuentas", texto)
    fin = re.search(r"QUINTA PARTE", texto[inicio.end():]) if inicio else None
    if not inicio or not fin:
        raise SystemExit("No encuentro la cuarta parte (cuadro de cuentas) en el PDF")
    boe: dict[str, str] = {}
    actual = None
    for linea in texto[inicio.end():inicio.end() + fin.start()].splitlines():
        l = linea.strip()
        if re.match(r"^GRUPO \d", l):
            actual = None  # la línea siguiente es el título del grupo, no la continuación de una cuenta
        elif re.match(r"^\d{5}\. ", l):
            actual = None  # las subcuentas de cinco dígitos no se cargan, y no son continuación de la cuenta anterior
        elif m := re.match(r"^(\d{1,4})\. (.+)$", l):
            actual = m.group(1)
            boe[actual] = m.group(2)
        elif actual and l and not re.match(r"^(BOLETÍN OFICIAL DEL ESTADO|LEGISLACIÓN CONSOLIDADA|Página \d+|=====)", l):
            boe[actual] += " " + l
    return boe


def main(ruta_excel: str, ruta_pdf: str) -> None:
    hoja = openpyxl.load_workbook(ruta_excel, data_only=True).worksheets[0]
    excel = {str(r[1]): limpio(r[2]) for r in hoja.iter_rows(min_row=2, values_only=True) if r[1] is not None and r[2]}
    boe = {c: limpio(n) for c, n in nombres_del_boe(ruta_pdf).items()}
    nombres, del_excel = {}, []
    for codigo, x in excel.items():
        b = boe.get(codigo)
        if b and SequenceMatcher(None, _norma(x), _norma(b)).ratio() >= PARECIDO:
            nombres[codigo] = b
        else:
            nombres[codigo] = x
            if b and _norma(x) != _norma(b):
                del_excel.append((codigo, x, b))
    if del_excel:
        print("Nombres que se dejan como en el Excel por no parecerse al del BOE:")
        for c, x, b in del_excel:
            print(f"  {c}: Excel «{x}» | BOE «{b}»")
    por_nivel = {n: {c: nombres[c] for c in sorted(nombres) if len(c) == n} for n in (1, 2, 3, 4)}

    def bloque(nombre: str, datos: dict[str, str]) -> str:
        return f"{nombre} = {{\n" + "".join(f"    {json.dumps(c)}: {json.dumps(n, ensure_ascii=False)},\n" for c, n in datos.items()) + "}\n"

    salida = Path(__file__).resolve().parents[1] / "src" / "conta_pridalac" / "domain" / "pgc_esfl.py"
    salida.write_text(
        '"""Cuadro de cuentas del plan de pequeñas y medianas entidades sin fines lucrativos (PGC-PyMESFL, Resolución del ICAC de 26-3-2013).\n\n'
        'Generado por `tools/generar_pgc_esfl.py` (no editar a mano): grupos (1 dígito), subgrupos (2), cuentas (3) y subcuentas de cuatro dígitos.\n"""\n\n'
        + bloque("GRUPOS_ESFL", por_nivel[1]) + "\n" + bloque("SUBGRUPOS_ESFL", por_nivel[2]) + "\n" + bloque("CUENTAS_3_ESFL", por_nivel[3]) + "\n" + bloque("CUENTAS_4_ESFL", por_nivel[4]),
        encoding="utf-8",
    )
    print(f"Escrito {salida}: {len(por_nivel[1])} grupos, {len(por_nivel[2])} subgrupos, {len(por_nivel[3])} cuentas, {len(por_nivel[4])} de cuatro dígitos")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
