"""Saca del diseño de registro oficial del modelo 200 (`DR200e25.xls`) el JSON compacto que usa el generador (`ficheros_aeat/dr200_2025.json`).

Incluye la cabecera del fichero y las páginas que usa Conta o puede usar (las que aparecen en algún `.200` presentado y las opcionales de `tools/inventario_dr200.py`);
las páginas de otros tipos de entidad (aseguradoras, cooperativas…) no se incluyen.

Uso:  python tools/dr200_a_json.py <DR200e25.xls> [salida=src/conta_pridalac/ficheros_aeat/dr200_2025.json] [carpeta_AEAT=AEAT]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import inventario_dr200 as inv  # noqa: E402

VERSION = "DR200e25 v1.02"


def main() -> None:
    xls = Path(sys.argv[1])
    salida = Path(sys.argv[2] if len(sys.argv) > 2 else "src/conta_pridalac/ficheros_aeat/dr200_2025.json")
    carpeta = Path(sys.argv[3] if len(sys.argv) > 3 else "AEAT")
    diseno = inv.leer_diseno(xls)
    reales = inv.leer_reales(carpeta)
    incluidas = {c for c in reales} | set(inv.OPCIONALES)
    paginas = {}
    for hoja, p in diseno.items():
        codigo = p["codigo"]
        if hoja == inv.CABECERA:
            continue
        if not codigo or codigo not in incluidas:
            continue
        paginas[codigo] = {
            "hoja": hoja,
            "campos": [
                {"n": c["n"], "pos": c["pos"], "lon": c["lon"], "tipo": c["tipo"], "casilla": (re.search(r"\[(\d{5})\]", c["desc"]) or [None, None])[1], "desc": c["desc"],
                 "validacion": c["validacion"], "contenido": c["contenido"]}
                for c in p["campos"]
            ],
        }
    cab = diseno[inv.CABECERA]
    cabecera = [{"n": c["n"], "pos": c["pos"], "lon": c["lon"], "tipo": c["tipo"], "desc": c["desc"], "contenido": c["contenido"]} for c in cab["campos"] if c["lon"] and c["n"] <= 8]
    datos = {"version": VERSION, "cabecera": cabecera, "paginas": dict(sorted(paginas.items()))}
    salida.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{salida}: {len(paginas)} páginas, {sum(len(p['campos']) for p in paginas.values())} campos, {salida.stat().st_size} bytes")


if __name__ == "__main__":
    main()
