"""Rellena la provincia de los terceros que no la tienen (ni código postal que la dé), a partir de los 347 ya presentados (`AEAT/C000X_347_<año>.347`).

    python tools/provincia_terceros.py --nombre empresa_a             # sólo enseña lo que haría
    python tools/provincia_terceros.py --nombre empresa_a --aplicar   # lo guarda (con el programa cerrado y copia hecha)

Busca al tercero por su NIF. Sólo escribe en fichas cuya provincia está vacía y cuyo código postal no da una provincia: nunca pisa lo que ya hay. Si un mismo NIF aparece con provincias distintas en
años distintos, vale la del año más reciente.
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa, Tercero
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero347 import leer
from conta_pridalac.ficheros_aeat.provincias import PROVINCIAS, codigo_de_provincia

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd")
    ap.add_argument("--ficheros", type=Path, default=RAIZ / "AEAT")
    a = ap.parse_args(argv)
    sesion = nueva_sesion(crear_motor(a.datos / f"{a.nombre}.sqlite"))
    empresa = sesion.scalars(select(Empresa)).first()
    por_nif: dict[str, str] = {}
    for ruta in sorted(glob.glob(str(a.ficheros / "C000?_347_*.347"))):
        d = leer(Path(ruta).read_bytes().decode("latin-1"))
        if d.nif != (empresa.nif or "").strip():
            continue
        for p in d.declarados:
            if p.provincia in PROVINCIAS:
                por_nif[p.nif] = p.provincia  # los años van en orden: queda el más reciente
    cambios = 0
    for nif, codigo in sorted(por_nif.items()):
        for t in sesion.scalars(select(Tercero).where(Tercero.empresa_id == empresa.id, Tercero.nif == nif)):
            if codigo_de_provincia(t.codigo_postal, t.provincia):
                continue
            print(f"{t.nombre} ({nif}): provincia = {PROVINCIAS[codigo]} ({codigo})")
            cambios += 1
            if a.aplicar:
                t.provincia = PROVINCIAS[codigo]
    if a.aplicar:
        sesion.commit()
        print(f"\n{cambios} fichas actualizadas")
    else:
        print(f"\n{cambios} fichas por actualizar (añada --aplicar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
