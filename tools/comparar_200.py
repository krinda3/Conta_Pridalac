"""Compara el modelo 200 que genera Conta con el que presentó el programa anterior (el `.200` de la carpeta AEAT), página a página y campo a campo.

    python tools/comparar_200.py --bd datos_locales/bd/empresa_a.sqlite --real AEAT/C0002_200_2025.200 --en-la-base-real [--anio 2025] [--paginas 01000,14000] [--como-programa-anterior]

Trabaja sobre una copia de la base (no cambia nada). `--como-programa-anterior` no suma las multas ni el gasto por el impuesto (el programa anterior no lo hacía), para que la comparación sea limpia.
Las diferencias que se esperan (el nombre de la persona de contacto con una errata del programa anterior, las multas de Empresa B…) se muestran igualmente: se explican en `docs/modelo200/`.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat import fichero200 as f200
from conta_pridalac.ficheros_aeat.fichero200 import Fichero200
from conta_pridalac.servicios import impuesto_sociedades_200 as gen
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.web.config import Configuracion


def comparar(generado: Fichero200, real: Fichero200, solo: set[str] | None = None) -> tuple[list[str], int]:
    """(líneas del informe, nº de campos distintos)."""
    lineas, distintos = [], 0
    g = {}
    for p in generado.paginas:
        g.setdefault(p.codigo, []).append(p)
    r = {}
    for p in real.paginas:
        r.setdefault(p.codigo, []).append(p)
    for codigo in sorted(set(g) | set(r), key=f200.ORDEN.__getitem__):
        if solo and codigo not in solo:
            continue
        if codigo not in g:
            lineas.append(f"== {codigo}: FALTA (el programa anterior la lleva)")
            continue
        if codigo not in r:
            lineas.append(f"== {codigo}: SOBRA (el programa anterior no la lleva)")
            continue
        if len(g[codigo]) != len(r[codigo]):
            lineas.append(f"== {codigo}: {len(g[codigo])} página(s) generadas y {len(r[codigo])} en el programa anterior")
        for pg, pr in zip(g[codigo], r[codigo]):
            dif = [(n, pr.valores[n], pg.valores[n]) for n in sorted(pr.valores) if pr.valores[n] != pg.valores[n]]
            if not dif:
                lineas.append(f"== {codigo}: IGUAL")
                continue
            lineas.append(f"== {codigo}: {len(dif)} campo(s) distinto(s)")
            for n, vr, vg in dif:
                c = f200._CAMPOS[codigo][n]
                lineas.append(f"   n{n:<4d} {c['casilla'] or '-----'} {c['desc'].split(' - ', 1)[-1][:70]:<70s} ANTERIOR={vr.strip()!r:<22} CONTA={vg.strip()!r}")
            distintos += len(dif)
    return lineas, distintos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--real", required=True, help="el .200 presentado por el programa anterior")
    ap.add_argument("--anio", type=int, default=f200.EJERCICIO)
    ap.add_argument("--paginas", help="solo estas páginas (01000,14000…)")
    ap.add_argument("--como-programa-anterior", action="store_true")
    ap.add_argument("--forzar-25", action="store_true", help="tipo general del 25 % (el programa anterior presentó así los dos; en la base real aún no está marcada la entidad patrimonial de Empresa B)")
    ap.add_argument("--agricola", action="store_true", help="marca «actividades agrícolas» (en Empresa A el 2025 del programa anterior la llevó sin marcar por error)")
    ap.add_argument("--en-la-base-real", action="store_true")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print("La base está en la carpeta de datos de la aplicación: use --en-la-base-real (se trabaja sobre una copia).", file=sys.stderr)
        return 2
    real = Fichero200.leer(Path(a.real).read_bytes().decode(f200.CODIFICACION))
    with tempfile.TemporaryDirectory() as t:
        copia = Path(t) / bd.name
        shutil.copyfile(bd, copia)
        motor = crear_motor(copia)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            ej = sesion.scalar(select(Ejercicio).where(Ejercicio.anio == a.anio))
            datos = isd.datos_del_ejercicio(sesion, ej)
            datos.forzar_25, datos.agricola = datos.forzar_25 or a.forzar_25, datos.agricola or a.agricola
            generado = gen.generar(sesion, ej, datos, con_correcciones_automaticas=not a.como_programa_anterior)
        finally:
            sesion.close()
            motor.dispose()
    lineas, distintos = comparar(generado, real, set(a.paginas.split(",")) if a.paginas else None)
    print("\n".join(lineas))
    print(f"\n{distintos} campo(s) distinto(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
