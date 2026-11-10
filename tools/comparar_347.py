"""Compara el cálculo del 347 desde las facturas con los ficheros presentados (sólo lectura).

    python tools/comparar_347.py --nombre empresa_a [--detalle] [--fecha contable]

Lee `datos_locales/bd/<nombre>.sqlite` y los `AEAT/C000X_347_<año>.347` de esa empresa (por su NIF): para cada año y clave enseña si coinciden los declarados y sus importes por trimestre
(un céntimo de diferencia se acepta como redondeo). No modifica nada.
"""
from __future__ import annotations

import argparse
import glob
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero347 import leer
from conta_pridalac.servicios.modelo347 import calcular_347

RAIZ = Path(__file__).resolve().parents[1]
CERO = Decimal("0")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--detalle", action="store_true")
    ap.add_argument("--fecha", choices=("factura", "contable"), help="qué fecha decide el trimestre (por defecto, la del servicio)")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd")
    a = ap.parse_args(argv)
    sesion = nueva_sesion(crear_motor(a.datos / f"{a.nombre}.sqlite"))
    ejercicios = {e.anio: e for e in sesion.scalars(select(Ejercicio))}
    nif = next(iter(ejercicios.values())).empresa.nif
    iguales = total = 0
    for ruta in sorted(glob.glob(str(RAIZ / "AEAT" / "C000?_347_*.347"))):
        pres = leer(Path(ruta).read_bytes().decode("latin-1"))
        if pres.nif != nif or pres.ejercicio not in ejercicios:
            continue
        total += 1
        calc = calcular_347(sesion, ejercicios[pres.ejercicio], fecha_del_trimestre=a.fecha)
        a_pres = {(p.nif, p.clave): p.trimestres for p in pres.declarados}
        a_calc = {(p.nif, p.clave): p.trimestres for p in calc.declarados}
        difs = []
        for k in sorted(set(a_pres) | set(a_calc)):
            x, y = a_pres.get(k), a_calc.get(k)
            if x is None or y is None or any(abs(p - q) > Decimal("0.01") for p, q in zip(x, y)):
                difs.append(f"{k[1]} {k[0]}: presentado {[str(v) for v in x] if x else None} / calculado {[str(v) for v in y] if y else None}")
        iguales += not difs
        print(f"{pres.ejercicio}  presentado {len(pres.declarados)} declarados / calculado {len(calc.declarados)}  {'igual' if not difs else 'DIFIERE'}")
        for d in difs:
            print("     ", d)
        if a.detalle:
            for av in calc.avisos:
                print("      aviso:", av)
    print(f"\n{iguales} de {total} años coinciden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
