"""Convierte el diseño de registro oficial del modelo 115 (Excel antiguo `.xls`) en el JSON que usa el generador de ficheros.

    python tools/extraer_diseno_115.py AEAT/diseno/DR115e15v13.xls src/conta_pridalac/ficheros_aeat/dr115_v13.json

Hace falta `xlrd` (`pip install xlrd`), que sólo se usa aquí. El `.xls` se baja de la sede (Ayuda → Diseños de registro → Modelos 100-199) y se guarda en `AEAT/diseno/` (no se versiona).
Cada campo: posición, longitud, tipo, descripción y, para los importes del formulario, el número de casilla oficial (01-05).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# número de orden del campo en el diseño → casilla del formulario (el diseño no las numera)
CASILLA_DE_ORDEN = {12: 1, 13: 2, 14: 3, 15: 4, 16: 5}  # perceptores, base, retenciones, anteriores declaraciones, resultado a ingresar


def extraer(ruta: Path) -> list[dict]:
    import xlrd

    hoja = xlrd.open_workbook(ruta).sheet_by_name("DR 11501")
    campos = []
    for r in range(5, hoja.nrows):
        n = hoja.cell_value(r, 0)
        if not isinstance(n, float):
            continue
        n = int(n)
        campos.append({"orden": n, "pos": int(hoja.cell_value(r, 1)), "lon": int(hoja.cell_value(r, 2)), "tipo": hoja.cell_value(r, 3).strip(), "desc": " ".join(str(hoja.cell_value(r, 4)).split()),
                       "casilla": CASILLA_DE_ORDEN.get(n)})
    return campos


def main(argv=None) -> int:
    origen, destino = Path(argv[0] if argv else sys.argv[1]), Path(argv[1] if argv else sys.argv[2])
    campos = extraer(origen)
    destino.write_text(json.dumps(campos, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(campos), "campos,", campos[-1]["pos"] + campos[-1]["lon"] - 1, "posiciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
