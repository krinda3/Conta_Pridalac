"""Genera un mapa de clases/métodos/funciones de los .prg de Visual Objects.

Uso: python tools/mapa_codigo.py <carpeta_fuentes> <salida.md>
Salida: por módulo, clases (con herencia y nº de métodos) y funciones sueltas, con nº de línea y tamaño.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

RE_CLASE = re.compile(r"^\s*CLASS\s+(\w+)(?:\s+INHERIT\s+(\w+))?", re.I)
RE_RUT = re.compile(
    r"^\s*(?:(?:STATIC|EXPORT|HIDDEN|PROTECT)\s+)*(METHOD|FUNCTION|PROCEDURE|ACCESS|ASSIGN)\s+(\w+)\s*\(?[^\n]*?(?:CLASS\s+(\w+))?\s*$",
    re.I,
)
RE_FIN = re.compile(r"^\s*RETURN\b", re.I)


def analizar(p: Path):
    lineas = p.read_text(encoding="latin-1").splitlines()
    clases, rutinas = {}, []
    for i, l in enumerate(lineas, 1):
        m = RE_CLASE.match(l)
        if m:
            clases[m.group(1)] = (m.group(2) or "", i)
            continue
        m = RE_RUT.match(l)
        if m:
            cl = re.search(r"\bCLASS\s+(\w+)", l, re.I)
            rutinas.append((m.group(1).upper(), m.group(2), cl.group(1) if cl else "", i))
    # tamaño aproximado = hasta la siguiente rutina
    out = []
    for k, (tipo, nombre, cl, ini) in enumerate(rutinas):
        fin = rutinas[k + 1][3] - 1 if k + 1 < len(rutinas) else len(lineas)
        out.append((tipo, nombre, cl, ini, fin - ini + 1))
    return len(lineas), clases, out


def main(carpeta, salida):
    md = ["# Mapa del código (Visual Objects)\n"]
    resumen = ["| Módulo | Líneas | Clases | Rutinas |", "|---|---:|---:|---:|"]
    cuerpo = []
    for p in sorted(Path(carpeta).glob("*.prg")):
        n, clases, rut = analizar(p)
        resumen.append(f"| {p.stem} | {n} | {len(clases)} | {len(rut)} |")
        cuerpo.append(f"\n## {p.stem}  ({n} líneas)\n")
        por_clase = defaultdict(list)
        for r in rut:
            por_clase[r[2]].append(r)
        sueltas = por_clase.pop("", [])
        for cl, ms in sorted(por_clase.items(), key=lambda kv: -sum(m[4] for m in kv[1])):
            herencia = clases.get(cl, ("", 0))[0]
            cuerpo.append(f"\n### class {cl}" + (f" : {herencia}" if herencia else "") + f"  ({len(ms)} métodos, {sum(m[4] for m in ms)} líneas)\n")
            cuerpo.append(", ".join(f"{m[1]}@{m[3]}" for m in ms))
        if sueltas:
            cuerpo.append(f"\n### funciones/procedimientos sueltos ({len(sueltas)})\n")
            cuerpo.append(", ".join(f"{m[1]}@{m[3]}({m[4]})" for m in sueltas))
    Path(salida).write_text("\n".join(md + resumen + cuerpo) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:3])
