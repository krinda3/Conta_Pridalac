"""Genera `domain/pgc.py` (nombres de las cuentas de 3 dígitos del PGC) desde los "Listado de cuentas" de MGD (PDF).

Uso: python tools/generar_pgc.py <listado1.pdf> [<listado2.pdf> ...]
En el listado las cuentas salen como `XXX.Y.Z`; la primera entrada de cada `XXX.0.0` es el nombre estándar del PGC y las
siguientes son subcuentas propias de la empresa (que no se incluyen). Si dos listados discrepan se avisa.
"""
import re
import sys
from pathlib import Path

from pypdf import PdfReader

FILA = re.compile(r"^\s+(\d{3})\.0\.0\s+(\S.*?)\s*$")


def primeras(ruta):
    vistas = {}
    for pagina in PdfReader(ruta).pages:
        for linea in pagina.extract_text(extraction_mode="layout").splitlines():
            m = FILA.match(linea)
            if m and m.group(1) not in vistas:
                vistas[m.group(1)] = m.group(2)
    return vistas


def frase(titulo):
    t = titulo.strip().lower()
    t = re.sub(r"(?<![a-zñáéíóú])(iva|irpf)(?![a-zñáéíóú])", lambda m: m.group(1).upper(), t)
    return t[:1].upper() + t[1:]


def main(*rutas):
    listados = [primeras(r) for r in rutas]
    union = {}
    for l in listados:
        for c, n in l.items():
            if c in union and union[c].upper() != n.upper():
                print(f"AVISO {c}: «{union[c]}» != «{n}»")
            union.setdefault(c, n)
    salida = Path(__file__).resolve().parents[1] / "src" / "conta_pridalac" / "domain" / "pgc_cuentas.py"
    lineas = ['"""Nombres de las cuentas de 3 dígitos del PGC (generado por tools/generar_pgc.py; no editar a mano)."""', "", "CUENTAS_3 = {"]
    lineas += [f'    "{c}": {frase(n)!r},' for c, n in sorted(union.items())]
    lineas.append("}")
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{len(union)} cuentas -> {salida}")


if __name__ == "__main__":
    main(*sys.argv[1:])
