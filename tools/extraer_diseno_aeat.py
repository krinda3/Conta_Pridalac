"""Convierte el diseño de registro oficial de la AEAT (Excel) en un JSON que usa el generador de ficheros.

    python tools/extraer_diseno_aeat.py AEAT/diseno/DR303e26v101.xlsx src/conta_pridalac/ficheros_aeat/dr303_2026.json

El Excel se baja de la sede (Ayuda técnica del modelo → Diseño de registro) y se guarda en `AEAT/diseno/` (no se versiona). El JSON sí: es la especificación pública.
Cada hoja es una página del fichero; cada campo: [posición, longitud, tipo, descripción, contenido], y `casilla` si la descripción lleva `[NN]`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl


def _entero(v) -> int | None:
    try:
        return int(str(v).lstrip("=").strip())
    except ValueError:
        return None


def extraer(ruta: Path) -> dict:
    libro = openpyxl.load_workbook(ruta, read_only=True)
    paginas = {}
    for hoja in libro:
        campos, pos, desplazamiento, sin_validacion = [], 1, 0, 0
        for fila in hoja.iter_rows(min_row=1, max_row=300, max_col=9, values_only=True):
            if str(fila[0]).strip() == "Nº":  # las páginas con campos complementarios (390) llevan una columna «Com» tras el tipo
                desplazamiento = 1 if str(fila[4] or "").strip() == "Com" else 0
                sin_validacion = 1 if str(fila[5 + desplazamiento] or "").strip().lower().startswith("contenido") else 0  # el 202 no tiene la columna «Validación»: el contenido va justo tras la descripción
                continue
            numero, longitud = fila[0], _entero(fila[2])
            if longitud is None or numero is None or str(numero).strip().upper() == "TOTAL":
                continue
            if not (str(numero).strip().isdigit() or str(numero).startswith("=")):
                continue
            tipo, descripcion, contenido = (fila[3] or "").strip(), " ".join(str(fila[4 + desplazamiento] or "").split()), " ".join(str(fila[6 - sin_validacion + desplazamiento] or "").split())
            casilla = re.findall(r"\[(\d+)\]\s*\.?\s*$", descripcion)
            campos.append({"pos": pos, "lon": longitud, "tipo": tipo, "desc": descripcion, "contenido": contenido, "casilla": int(casilla[0]) if casilla else None})
            pos += longitud
        paginas[hoja.title] = campos
    return paginas


def main(argv=None) -> int:
    origen, destino = Path(argv[0] if argv else sys.argv[1]), Path(argv[1] if argv else sys.argv[2])
    paginas = extraer(origen)
    destino.write_text(json.dumps(paginas, ensure_ascii=False, indent=0), encoding="utf-8")
    for nombre, campos in paginas.items():
        print(nombre, len(campos), "campos,", campos[-1]["pos"] + campos[-1]["lon"] - 1, "posiciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
