"""Paso A1 del modelo 303 (sólo lectura): qué casillas llevan las declaraciones ya presentadas y cómo se relacionan, y qué sale de los libros.

    python tools/analizar_303.py --nombre empresa_a [--anio 2026 --periodo 3]

1. Inventario de las casillas de las declaraciones presentadas (modelo 303 importado del programa anterior) y comprobación de las relaciones entre ellas
   (total devengado, total a deducir, resultado, compensaciones…); lo que no cumple una relación se enseña con sus valores.
2. Con `--anio` y `--periodo`: lo que dicen los libros (facturas por fecha contable) frente a lo presentado, casilla a casilla.
No modifica nada.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
D = Decimal
CERO = D("0.00")

# casillas del 303 que aparecen en las declaraciones importadas (nombres del formulario oficial)
NOMBRES = {
    "1": "Base 4 %", "2": "Tipo 4", "3": "Cuota 4 %", "4": "Base 5 %", "5": "Tipo 10", "6": "Cuota 10 %", "7": "Base 21 %", "8": "Tipo 21", "9": "Cuota 21 %",
    "20": "Tipo recargo 1,4", "23": "Tipo recargo 5,2", "27": "Total cuota devengada",
    "28": "Base soportado interior corriente", "29": "Cuota soportado interior corriente", "40": "Base rectificación deducciones", "41": "Cuota rectificación deducciones",
    "44": "Regularización (prorrata definitiva)", "45": "Total a deducir", "46": "Resultado régimen general", "64": "Suma de resultados", "65": "% Estado",
    "66": "Cuota atribuible al Estado", "69": "Resultado", "71": "Resultado de la liquidación", "87": "A compensar de periodos anteriores",
}


def cargar(con: sqlite3.Connection):
    filas = []
    for anio, periodo, tipo, cas in con.execute("select anio, periodo, tipo, casillas from declaracion_presentada where tipo = 1 order by anio, periodo"):
        filas.append((anio, periodo, {int(k): D(str(v)) for k, v in json.loads(cas).items()}))
    return filas


def relaciones(c: dict[int, Decimal]):
    """Relaciones que deberían cumplirse; devuelve {nombre: (esperado, real)} de las que no."""
    g = lambda k: c.get(k, CERO)  # noqa: E731
    r = {
        "27 = 3 + 6 + 9": (g(3) + g(6) + g(9), g(27)),
        "45 = 29 + 41 + 44": (g(29) + g(41) + g(44), g(45)),
        "46 = 27 − 45": (g(27) - g(45), g(46)),
        "64 = 46": (g(46), g(64)),
        "66 = 64 × 65 %": ((g(64) * g(65) / 100).quantize(D("0.01")), g(66)),
    }
    return {k: v for k, v in r.items() if abs(v[0] - v[1]) > D("0.011")}


def libros(con: sqlite3.Connection, anio: int, periodo: int):
    """Devengado por tipo y deducible, por fecha contable, sin las facturas de IVA no deducible."""
    mi, mf = (periodo - 1) * 3 + 1, periodo * 3
    consulta = """
        select f.sentido, i.pct_iva/100.0, i.bien_inversion, i.deducible, sum(i.base)/100.0, sum(i.cuota_iva)/100.0, count(*)
        from factura_iva i join factura f on f.id = i.factura_id join ejercicio e on e.id = f.ejercicio_id
        where e.anio = ? and cast(strftime('%m', f.fecha_contable) as int) between ? and ?
        group by f.sentido, i.pct_iva, i.bien_inversion, i.deducible order by f.sentido, i.pct_iva"""
    return con.execute(consulta, (anio, mi, mf)).fetchall()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--anio", type=int)
    ap.add_argument("--periodo", type=int)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{(RAIZ / 'datos_locales' / 'bd' / (a.nombre + '.sqlite')).as_posix()}?mode=ro", uri=True)
    decl = cargar(con)
    print(f"== {a.nombre}: {len(decl)} declaraciones presentadas (tipo 1)")
    uso: dict[int, list[Decimal]] = {}
    for _, _, c in decl:
        for k, v in c.items():
            uso.setdefault(k, []).append(v)
    print("\nCasillas que aparecen (nº, veces, mínimo, máximo, nombre):")
    for k in sorted(uso):
        print(f"  [{k:>3}] {len(uso[k]):>2}  {min(uso[k]):>10}  {max(uso[k]):>10}  {NOMBRES.get(str(k), '?')}")
    print("\nRelaciones entre casillas que NO se cumplen:")
    ninguna = True
    for anio, periodo, c in decl:
        for nombre, (esperado, real) in relaciones(c).items():
            ninguna = False
            print(f"  {anio}-{periodo}T  {nombre}: esperado {esperado}, presentado {real}")
    if ninguna:
        print("  (todas se cumplen)")
    print("\nCompensación: periodos con el 87 (pendiente de periodos anteriores) o con resultado negativo")
    for anio, periodo, c in decl:
        if c.get(87) or c.get(46, CERO) < 0:
            print(f"  {anio}-{periodo}T  46={c.get(46, CERO):>10}  87={c.get(87, CERO):>10}  69={c.get(69, CERO):>10}  71={c.get(71, CERO):>10}")
    if a.anio and a.periodo:
        print(f"\n== Libros {a.anio}-{a.periodo}T (por fecha contable): sentido, % IVA, bien inversión, deducible, base, cuota, nº líneas")
        for fila in libros(con, a.anio, a.periodo):
            print("  ", fila)
        presentada = next((c for an, p, c in decl if (an, p) == (a.anio, a.periodo)), None)
        print("  presentado:", {k: str(v) for k, v in (presentada or {}).items() if k in (1, 3, 4, 6, 7, 9, 27, 28, 29, 40, 41, 44, 45, 46, 71, 87)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
