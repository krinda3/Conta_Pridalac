"""Compara las facturas recibidas de un periodo entre la base original y la del ensayo (una copia donde se han vuelto a contabilizar desde la conciliación).

    python tools/comparar_trimestre.py --original ruta/empresa_a_original.sqlite --ensayo ruta/empresa_a.sqlite --desde 2026-07-01 --hasta 2026-09-30

Sólo lee. Dice qué facturas están en una base y no en la otra, en qué difieren las que están en las dos (fechas, cuentas, pagos) y qué saldos de cuenta no coinciden en el periodo.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from conta_pridalac.servicios.ensayo import FacturaComparada, comparar_recibidas


def _e(c: int) -> str:
    return f"{c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linea(f: FacturaComparada) -> str:
    pagos = "; ".join(f"{p[0]} {p[1]} {_e(p[2])}" for p in f.pagos) or "sin pago"
    return f"{f.fecha_factura} {f.nombre[:28]:28} nº {f.numero[:18]:18} {_e(f.total):>11}  gasto {f.gasto}  [{pagos}]"


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", required=True)
    ap.add_argument("--ensayo", required=True)
    ap.add_argument("--desde", required=True)
    ap.add_argument("--hasta", required=True)
    a = ap.parse_args(argv)
    for ruta in (a.original, a.ensayo):
        if not Path(ruta).is_file():
            ap.error(f"no existe {ruta}")
    con_a, con_b = (sqlite3.connect(f"file:{Path(r).resolve().as_posix()}?mode=ro", uri=True) for r in (a.original, a.ensayo))
    c = comparar_recibidas(con_a, con_b, date.fromisoformat(a.desde), date.fromisoformat(a.hasta))
    print(f"Iguales: {c.iguales} · Distintas: {len(c.distintas)} · Sólo en la original: {len(c.solo_original)} · Sólo en el ensayo: {len(c.solo_ensayo)}")
    for titulo, lista in (("SÓLO EN LA ORIGINAL (no se han recuperado)", c.solo_original), ("SÓLO EN EL ENSAYO (sobran)", c.solo_ensayo)):
        if lista:
            print(f"\n{titulo}")
            for f in lista:
                print("  ", _linea(f))
    if c.distintas:
        print("\nDISTINTAS")
        for f, g, dif in c.distintas:
            print(f"   {f.nombre[:30]} nº {f.numero} {_e(f.total)}")
            for d in dif:
                print(f"       {d}")
    if c.saldos:
        print("\nSALDOS DE CUENTA QUE DIFIEREN EN EL PERIODO (debe − haber)")
        for cuenta, (x, y) in c.saldos.items():
            print(f"   {cuenta}  original {_e(x):>13}  ensayo {_e(y):>13}  diferencia {_e(y - x):>13}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
