"""Concilia el IVA de los libros con las declaraciones de IVA ya presentadas (tablas 440/444 del respaldo del programa anterior).

    python tools/conciliar_iva.py --sdb D:/OneDrive/Downloads/C0001.SDB --empresa 1 --nombre empresa_b

Lee `datos_locales/bd/<nombre>.sqlite` y el respaldo (sólo lectura) y escribe `datos_locales/salida/conciliacion_iva_<nombre>.xlsx` con dos hojas:
- «Periodos»: por trimestre, lo presentado (modelo 303) frente a lo que dan las cuentas 472/477 por fecha contable (sólo las facturas, asientos 1 y 2), y la diferencia.
- «Facturas»: facturas con IVA que se declararon en un periodo distinto del de su fecha contable, o que no están en ninguna declaración.
Sólo desde el primer ejercicio con declaraciones en el programa anterior (antes se presentaron con el programa anterior).
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

RAIZ = Path(__file__).resolve().parents[1]
FIRMA = ("A", "Z", "R", "P")  # asientos que no son operaciones: apertura, cierre, regularización, liquidación


def _hoja(libro, titulo, columnas, filas, primera=False):
    hoja = libro.active if primera else libro.create_sheet()
    hoja.title = titulo
    for c, (nombre, ancho) in enumerate(columnas, start=1):
        celda = hoja.cell(1, c, nombre)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="305496")
        celda.alignment = Alignment(wrap_text=True)
        hoja.column_dimensions[get_column_letter(c)].width = ancho
    for f, fila in enumerate(filas, start=2):
        for c, v in enumerate(fila, start=1):
            celda = hoja.cell(f, c, v)
            if isinstance(v, float):
                celda.number_format = "#,##0.00"
    hoja.freeze_panes = "A2"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdb", required=True, type=Path)
    ap.add_argument("--empresa", required=True, type=int)
    ap.add_argument("--nombre", required=True)
    a = ap.parse_args(argv)
    p = f"C{a.empresa:04d}"

    sdb = sqlite3.connect(f"file:{a.sdb.as_posix()}?mode=ro&immutable=1", uri=True)
    sdb.row_factory = sqlite3.Row
    bd = sqlite3.connect(RAIZ / "datos_locales" / "bd" / f"{a.nombre}.sqlite")

    periodos = []
    for r in sdb.execute(f"select ANO, PER, CAS27, CAS45, CAS46, CAS87 from {p}440 where ANO >= 2021 order by ANO, PER"):
        ano, per = r["ANO"], r["PER"]
        if per > 4:  # declaraciones fuera de los 4 trimestres (complementarias o mensuales): se ven pero no se comparan
            periodos.append([f"{ano} · periodo {per}", None, None, None, None, None, None, None, "complementaria o periodo no trimestral"])
            continue
        mi, mf = (per - 1) * 3 + 1, per * 3
        rep, sop = bd.execute(
            """select coalesce(sum(case when cu.codigo like '477%' then a.haber - a.debe else 0 end), 0) / 100.0,
                      coalesce(sum(case when cu.codigo like '472%' then a.debe - a.haber else 0 end), 0) / 100.0
               from apunte a join asiento s on s.id = a.asiento_id join ejercicio e on e.id = s.ejercicio_id join cuenta cu on cu.id = a.cuenta_id
               where e.anio = ? and cast(strftime('%m', s.fecha) as int) between ? and ? and s.tipo in (1, 2)""",
            (ano, mi, mf),
        ).fetchone()
        dec_rep, dec_sop = float(r["CAS27"] or 0), float(r["CAS45"] or 0)
        dif_rep, dif_sop = round(rep - dec_rep, 2), round(sop - dec_sop, 2)
        nota = "" if abs(dif_rep) < 0.05 and abs(dif_sop) < 0.05 else "los libros no coinciden con lo presentado"
        periodos.append([f"{ano} · {per}T", dec_rep, rep, dif_rep, dec_sop, sop, dif_sop, float(r["CAS46"] or 0), nota])

    cab = {(r["EJE"], r["SER"], r["COD"]): r for r in sdb.execute(f"select EJE, SER, COD, FEC, FECFAC, DES, CIVA1, CIVA2, CIVA3, CIVA4, CIVA5, CIVA6 from {p}006 where SER in ('1','2') and EJE >= '2022'")}
    declaradas: dict[tuple, set] = {}
    for r in sdb.execute(f"select ANO, PER, EJE, SER, COD from {p}444 where ANO >= 2022"):
        declaradas.setdefault((r["EJE"], r["SER"], r["COD"]), set()).add((r["ANO"], r["PER"]))
    facturas = []
    for k, c in cab.items():
        cuota = round(sum((c[f"CIVA{i}"] or 0) for i in range(1, 7)), 2)
        trimestre = (int(c["FEC"]) // 100 % 100 - 1) // 3 + 1
        propio = (int(c["FEC"]) // 10000, trimestre)
        ds = declaradas.get(k)
        if ds is None:
            if abs(cuota) >= 0.005:
                facturas.append([f"{k[0]}/{k[1]}/{k[2]}", str(c["FEC"]), str(c["FECFAC"]), c["DES"][:60], cuota, f"{propio[0]} · {propio[1]}T", "—", "no está en ninguna declaración"])
        elif ds != {propio}:
            donde = ", ".join(f"{a_} · {p_}T" if p_ <= 4 else f"{a_} · periodo {p_}" for a_, p_ in sorted(ds))
            facturas.append([f"{k[0]}/{k[1]}/{k[2]}", str(c["FEC"]), str(c["FECFAC"]), c["DES"][:60], cuota, f"{propio[0]} · {propio[1]}T", donde, "declarada en otro periodo"])

    libro = Workbook()
    _hoja(libro, "Periodos", [("Periodo", 18), ("Repercutido presentado", 16), ("Repercutido en libros", 16), ("Diferencia", 12), ("Soportado presentado", 16), ("Soportado en libros", 16), ("Diferencia", 12), ("Resultado 303", 14), ("Observación", 40)], periodos, primera=True)
    _hoja(libro, "Facturas", [("Asiento", 14), ("Fecha contable", 14), ("Fecha factura", 14), ("Concepto", 50), ("Cuota IVA", 12), ("Periodo por su fecha", 18), ("Declarada en", 24), ("Qué ocurre", 32)], facturas)
    salida = RAIZ / "datos_locales" / "salida" / f"conciliacion_iva_{a.nombre}.xlsx"
    salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(salida)
    print(f"{len(periodos)} periodos · {len(facturas)} facturas a revisar -> {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
