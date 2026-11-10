"""Vuelca el esquema de las tablas DBF de GestionMGD a Markdown.

Uso: python tools/volcar_esquema.py <carpeta_dbf> <salida_esquema.md> <salida_muestras.md>

- esquema (versionable): campos, tipos, longitudes, nº de registros.
- muestras (NO versionar, datos reales): primeros valores no vacíos por campo.
"""
import sys
from pathlib import Path

from dbfread import DBF


def valor_corto(v, n=40):
    s = str(v).strip().replace("\n", " ").replace("|", "/")
    return s if len(s) <= n else s[:n] + "…"


def main(carpeta, out_esquema, out_muestras):
    tablas = sorted(Path(carpeta).glob("*.dbf"), key=lambda p: p.name.lower()) + sorted(
        Path(carpeta).glob("*.DBF"), key=lambda p: p.name.lower()
    )
    vistos, esquema, muestras = set(), ["# Esquema de tablas (DBF 2021)\n"], ["# Muestras (DATOS REALES, no versionar)\n"]
    resumen = ["| Tabla | Registros | Campos |", "|---|---:|---:|"]
    cuerpo_e, cuerpo_m = [], []
    for p in tablas:
        if p.name.lower() in vistos:
            continue
        vistos.add(p.name.lower())
        try:
            t = DBF(str(p), encoding="latin-1", ignore_missing_memofile=True, load=False)
            filas = list(t)
        except Exception as e:  # tabla ilegible: se anota y se sigue
            resumen.append(f"| {p.stem} | ERROR | {e} |")
            continue
        campos = t.fields
        resumen.append(f"| {p.stem} | {len(filas)} | {len(campos)} |")
        cuerpo_e.append(f"\n## {p.stem}\n\nRegistros: {len(filas)}\n\n| Campo | Tipo | Long | Dec |\n|---|---|---:|---:|")
        cuerpo_m.append(f"\n## {p.stem}\n\n| Campo | Ejemplos (hasta 3 distintos no vacíos) | Distintos |\n|---|---|---:|")
        for f in campos:
            cuerpo_e.append(f"| {f.name} | {f.type} | {f.length} | {f.decimal_count} |")
            distintos, ejemplos = set(), []
            for r in filas:
                v = r.get(f.name)
                if v in (None, "", 0, False) or str(v).strip() == "":
                    continue
                k = str(v)
                if k not in distintos:
                    distintos.add(k)
                    if len(ejemplos) < 3:
                        ejemplos.append(valor_corto(v))
            cuerpo_m.append(f"| {f.name} | {' ; '.join(ejemplos)} | {len(distintos)} |")
    Path(out_esquema).write_text("\n".join(esquema + [""] + resumen + cuerpo_e) + "\n", encoding="utf-8")
    Path(out_muestras).write_text("\n".join(muestras + cuerpo_m) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:4])
