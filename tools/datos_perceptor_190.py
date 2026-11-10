"""Rellena provincia, clave y subclave del modelo 190 en la ficha de cada perceptor, a partir de los 190 ya presentados (`AEAT/C000X_190_<año>.190`).

    python tools/datos_perceptor_190.py --nombre empresa_a             # sólo enseña lo que haría
    python tools/datos_perceptor_190.py --nombre empresa_a --aplicar   # lo guarda (con el programa cerrado y copia hecha)

Sólo rellena lo que está vacío en la ficha (nunca pisa lo que ya hay) y busca al tercero por su NIF; si un mismo NIF aparece con datos distintos en años distintos, vale el del año más reciente.
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

from sqlalchemy import inspect, select

from conta_pridalac.db.modelos import Empresa, Tercero
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero190 import leer

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--datos", default=str(RAIZ / "datos_locales" / "bd"), help="carpeta de las bases (por defecto datos_locales/bd)")
    a = ap.parse_args(argv)
    motor = crear_motor(Path(a.datos) / f"{a.nombre}.sqlite")
    if a.aplicar:
        crear_esquema(motor)  # añade las columnas nuevas si la base es anterior
    if not a.aplicar and "provincia_190" not in {c["name"] for c in inspect(motor).get_columns("tercero")}:
        print("A esta base le faltan las columnas del modelo 190: abra el programa una vez (las añade solo), o use --aplicar, y repita.")
        return 1
    sesion = nueva_sesion(motor)
    empresa = sesion.scalars(select(Empresa)).first()
    datos: dict[str, tuple[str, str, str]] = {}
    for ruta in sorted(glob.glob(str(RAIZ / "AEAT" / "C000?_190_*.190"))):
        d = leer(Path(ruta).read_bytes().decode("latin-1"))
        if d.nif != empresa.nif:
            continue
        for p in d.percepciones:
            datos[p.nif] = (p.provincia, p.clave, p.subclave)  # los años van en orden: queda el más reciente
    if not datos:
        print("No hay 190 presentados de esta empresa en AEAT/")
        return 0
    cambios = 0
    for nif, (provincia, clave, subclave) in datos.items():
        terceros = sesion.scalars(select(Tercero).where(Tercero.empresa_id == empresa.id, Tercero.nif == nif)).all()
        if not terceros:
            print(f"{nif}: no hay ningún tercero con ese NIF — se añadirá a mano")
        for t in terceros:
            nuevo = {c: v for c, v in (("provincia_190", provincia), ("clave_190", clave), ("subclave_190", subclave)) if not getattr(t, c, None)}
            if not nuevo:
                print(f"{t.nombre} ({nif}): ya tiene sus datos del 190")
                continue
            print(f"{t.nombre} ({nif}): {', '.join(f'{c} = {v}' for c, v in nuevo.items())}")
            cambios += 1
            if a.aplicar:
                for c, v in nuevo.items():
                    setattr(t, c, v)
    if a.aplicar:
        sesion.commit()
        print(f"\n{cambios} fichas actualizadas")
    else:
        print(f"\n{cambios} fichas por actualizar (añada --aplicar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
