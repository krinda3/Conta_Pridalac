"""Añade a una base ya cargada los modelos 111 presentados (tabla 199 del programa anterior) y enlaza sus PDF, sin tocar nada más.

    python tools/importar_111_presentados.py --sdb D:/OneDrive/Downloads/C0002.SDB --nombre empresa_a \\
        --comprobantes "docs/Exportaciones del programa anterior/Comprobantes"

Es seguro repetirlo: no duplica las declaraciones que ya están. Hace falta para que el programa sepa qué trimestres del 111 están presentados (y no deje preparar otro «normal»).
Antes de ejecutarlo conviene hacer una copia de seguridad de la empresa (pantalla «Copias de seguridad»).
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.migracion.comprobantes import enlazar_pdfs_de_declaraciones
from conta_pridalac.migracion.programa_anterior import cargar_declaraciones_111
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdb", required=True, type=Path)
    ap.add_argument("--nombre", required=True, help="nombre de la empresa (su .sqlite en datos_locales/bd)")
    ap.add_argument("--comprobantes", type=Path, help="carpeta con los PDF presentados (C000X_111_<año>_<mm>.PDF)")
    ap.add_argument("--desde", type=int, default=2021)
    a = ap.parse_args(argv)
    motor = crear_motor(RAIZ / "datos_locales" / "bd" / f"{a.nombre}.sqlite")
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    empresa = sesion.scalars(select(Empresa)).first()
    con = sqlite3.connect(f"file:{a.sdb.as_posix()}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    prefijo = f"C{empresa.codigo:04d}"
    nuevas = cargar_declaraciones_111(sesion, con, prefijo, empresa, a.desde)
    print(f"Modelos 111 añadidos: {nuevas}")
    if a.comprobantes:
        enlazados, sin = enlazar_pdfs_de_declaraciones(sesion, AlmacenAdjuntos(RAIZ / "datos_locales" / "justificantes"), empresa, a.comprobantes, ("111",))
        print(f"PDF enlazados: {enlazados}" + (f" · sin declaración en la base: {len(sin)} ({', '.join(sin[:5])}…)" if sin else ""))
    sesion.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
