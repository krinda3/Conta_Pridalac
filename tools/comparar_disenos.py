"""Compara dos versiones de un diseño de registro de la AEAT (los JSON de `src/conta_pridalac/ficheros_aeat/`) y dice qué páginas, campos y casillas cambian.

    python tools/comparar_disenos.py dr200_2025.json dr200_2026.json [--salida docs/modelo200/cambios_2025_2026.txt]

Para tener el JSON del diseño nuevo: `tools/dr200_a_json.py` (modelo 200) o `tools/extraer_diseno_aeat.py` (los demás). Procedimiento completo: `docs/11_control_de_cambios_normativos.md`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conta_pridalac.ficheros_aeat.comparar import cargar, comparar


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("viejo")
    ap.add_argument("nuevo")
    ap.add_argument("--salida", help="guarda el informe en este fichero además de mostrarlo")
    a = ap.parse_args(argv)
    for ruta in (a.viejo, a.nuevo):
        if not Path(ruta).is_file():
            ap.error(f"no existe {ruta}")
    informe = comparar(cargar(a.viejo), cargar(a.nuevo))
    texto = informe.texto()
    print(texto)
    if a.salida:
        Path(a.salida).write_text(texto, encoding="utf-8")
        print(f"Informe guardado en {a.salida}")
    return 0 if informe.sin_cambios else 1


if __name__ == "__main__":
    sys.exit(main())
