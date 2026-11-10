"""Compara el cálculo del 190 desde los libros con los ficheros presentados (sólo lectura).

    python tools/comparar_190.py --nombre empresa_a

Lee `datos_locales/bd/<nombre>.sqlite` y los `AEAT/C000X_190_<año>.190` de esa empresa (por su NIF): para cada año enseña si coinciden perceptores, percepciones y retenciones.
"""
from __future__ import annotations

import argparse
import glob
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero190 import leer
from conta_pridalac.servicios.modelo190 import calcular_190

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    a = ap.parse_args(argv)
    motor = crear_motor(RAIZ / "datos_locales" / "bd" / f"{a.nombre}.sqlite")
    if "provincia_190" not in {c["name"] for c in inspect(motor).get_columns("tercero")}:
        print("A esta base le faltan las columnas del modelo 190: abra el programa una vez (las añade solo) y repita.")
        return 1
    sesion = nueva_sesion(motor)
    ejercicios = {e.anio: e for e in sesion.scalars(select(Ejercicio))}
    nif = next(iter(ejercicios.values())).empresa.nif
    iguales = total = 0
    for ruta in sorted(glob.glob(str(RAIZ / "AEAT" / "C000?_190_*.190"))):
        pres = leer(Path(ruta).read_bytes().decode("latin-1"))
        if pres.nif != nif or pres.ejercicio not in ejercicios:
            continue
        total += 1
        calc = calcular_190(sesion, ejercicios[pres.ejercicio])
        a_pres = {p.nif: (p.percepcion, p.retencion) for p in pres.percepciones}
        a_calc = {p.nif: (p.percepcion, p.retencion) for p in calc.perceptores}
        difs = [f"{k}: presentado {a_pres.get(k)} / calculado {a_calc.get(k)}" for k in sorted(set(a_pres) | set(a_calc), key=str)
                if a_pres.get(k) is None or a_calc.get(k) is None or any(abs(x - y) > Decimal("0.01") for x, y in zip(a_pres[k], a_calc[k]))]
        iguales += not difs
        print(f"{pres.ejercicio}  presentado {len(pres.percepciones)} perceptores / calculado {len(calc.perceptores)}  {'igual' if not difs else 'DIFIERE'}")
        for d in difs:
            print("     ", d)
        for av in calc.avisos:
            print("      aviso:", av)
    print(f"\n{iguales} de {total} años coinciden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
