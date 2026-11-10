"""Añade a una base ya cargada los modelos 347 presentados (a partir de sus ficheros de AEAT/) y enlaza sus PDF, sin tocar nada más.

    python tools/importar_347_presentados.py --nombre empresa_a --comprobantes "docs/Exportaciones del programa anterior/Comprobantes"

Es seguro repetirlo: no duplica los años que ya están. Hace falta para que el programa sepa qué ejercicios del 347 están presentados (y no deje preparar otro «normal»).
Antes de ejecutarlo conviene hacer una copia de seguridad de la empresa (pantalla «Copias de seguridad») y tener el programa cerrado.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.migracion.comprobantes import enlazar_pdfs_de_declaraciones
from conta_pridalac.migracion.declaraciones347 import cargar_declaraciones_347
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True, help="nombre de la empresa (su .sqlite en la carpeta de datos)")
    ap.add_argument("--ficheros", type=Path, default=RAIZ / "AEAT", help="carpeta con los C000X_347_<año>.347 (por defecto AEAT/)")
    ap.add_argument("--comprobantes", type=Path, help="carpeta con los PDF presentados (C000X_347_<año>_00.PDF)")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd", help="carpeta de las bases (por defecto datos_locales/bd)")
    ap.add_argument("--almacen", type=Path, default=RAIZ / "datos_locales" / "justificantes")
    a = ap.parse_args(argv)
    motor = crear_motor(a.datos / f"{a.nombre}.sqlite")
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    empresa = sesion.scalars(select(Empresa)).first()
    nuevas, avisos = cargar_declaraciones_347(sesion, empresa, a.ficheros, a.comprobantes)
    print(f"Modelos 347 añadidos: {nuevas}")
    for aviso in avisos:
        print("  aviso:", aviso)
    if a.comprobantes:
        enlazados, sin = enlazar_pdfs_de_declaraciones(sesion, AlmacenAdjuntos(a.almacen), empresa, a.comprobantes, ("347",))
        print(f"PDF enlazados: {enlazados}" + (f" · sin declaración en la base: {len(sin)} ({', '.join(sin[:5])}…)" if sin else ""))
    sesion.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
