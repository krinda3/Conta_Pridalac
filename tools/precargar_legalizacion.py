"""Rellena en la ficha de una empresa los datos de la legalización de libros (municipio, provincia y quien presenta) con los de un ZIP de Legalia2 del programa anterior.

    python tools/precargar_legalizacion.py --bd datos_locales/bd/empresa_a.sqlite --zip D:/OneDrive/Legalia2/LL28025B00000010.ZIP --en-la-base-real            (simula: dice lo que pondría)
    python tools/precargar_legalizacion.py --bd datos_locales/bd/empresa_a.sqlite --zip D:/OneDrive/Legalia2/LL28025B00000010.ZIP --aplicar --en-la-base-real  (lo hace)

Sólo rellena lo que está vacío: no pisa nada de lo ya escrito. Comprueba que el NIF del ZIP es el de la empresa. Se niega a trabajar sobre la carpeta de datos de la aplicación salvo con `--en-la-base-real`.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.libros_oficiales import leer_datos_txt, precargar_ficha
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la empresa")
    ap.add_argument("--zip", required=True, help="un ZIP de legalización del programa anterior (LL28…ZIP) con su DATOS.TXT")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios (sin esto sólo se dice lo que se pondría)")
    ap.add_argument("--en-la-base-real", action="store_true", help="permite trabajar sobre la carpeta de datos de la aplicación")
    a = ap.parse_args(argv)
    bd, ruta_zip = Path(a.bd).resolve(), Path(a.zip)
    if not bd.is_file() or not ruta_zip.is_file():
        ap.error("no existe la base o el ZIP")
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    with zipfile.ZipFile(ruta_zip) as z:
        nombre = next((n for n in z.namelist() if n.upper().endswith("DATOS.TXT")), None)
        if nombre is None:
            ap.error("el ZIP no lleva DATOS.TXT")
        datos = leer_datos_txt(z.read(nombre).decode("latin-1"))
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name  # sin --aplicar se trabaja sobre otra copia y no se guarda nada
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            empresa = sesion.scalars(select(Empresa)).one()
            try:
                puestos = precargar_ficha(empresa, datos)
            except ErrorContable as e:
                print(f"No se puede: {e}", file=sys.stderr)
                return 1
            sesion.commit()
        finally:
            sesion.close()
            motor.dispose()
    for campo, valor in puestos:
        print(f"  {campo}: {valor}")
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {len(puestos)} campo(s) de la ficha de {empresa.nombre} rellenados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
