"""Importa a una base los `.200` (Impuesto sobre Sociedades) y `.202` (pago fraccionado) ya presentados, de la carpeta `AEAT/` del programa anterior.

    python tools/importar_is.py --bd datos_locales/ensayo/empresa_a.sqlite --carpeta AEAT            (simula: dice lo que importaría)
    python tools/importar_is.py --bd datos_locales/ensayo/empresa_a.sqlite --carpeta AEAT --aplicar  (lo hace)

Del `.200` se leen la base imponible, la cuota íntegra, la cuota líquida, las retenciones, los pagos fraccionados y el resultado; de ahí sale la base del 202 siguiente. Cada fichero se asigna a la
empresa de la base por su NIF: los de otras empresas se saltan. Lo que ya estaba no se duplica. Se niega a trabajar sobre la carpeta de datos de la aplicación salvo que se indique `--en-la-base-real`:
haga antes una copia del fichero .sqlite fuera de esa carpeta.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.servicios.impuesto_sociedades import importar_carpeta, quitar_importada
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la base")
    ap.add_argument("--carpeta", required=True, help="carpeta con los .200 y .202 (la AEAT/ del programa anterior)")
    ap.add_argument("--quitar", metavar="MODELO:AÑO:PERIODO", help="en vez de importar, quita una declaración importada por error (por ejemplo 202:2026:3); el periodo es 0 en el 200")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios (sin esto sólo se cuenta lo que se importaría)")
    ap.add_argument("--en-la-base-real", action="store_true", help="permite trabajar sobre la carpeta de datos de la aplicación")
    a = ap.parse_args(argv)
    bd, carpeta = Path(a.bd).resolve(), Path(a.carpeta).resolve()
    if not bd.is_file():
        ap.error(f"no existe {bd}")
    if not carpeta.is_dir():
        ap.error(f"no existe la carpeta {carpeta}")
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name  # sin --aplicar se trabaja sobre otra copia y no se guarda nada
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            if a.quitar:
                modelo, anio, periodo = a.quitar.split(":")
                empresa = sesion.scalars(select(Empresa)).one()
                quitadas = quitar_importada(sesion, empresa.id, modelo, int(anio), int(periodo))
                sesion.commit()
                print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {quitadas} declaración(es) {modelo} {anio} periodo {periodo} quitadas de {empresa.nombre}.")
                return 0
            resultados = importar_carpeta(sesion, carpeta)
            sesion.commit()
        finally:
            sesion.close()
            motor.dispose()
    nuevas = sum(1 for _, r in resultados if r == "nueva")
    for nombre, estado in resultados:
        if estado != "ya estaba" and "que no es el de ninguna empresa" not in estado and "Todavía no se leen" not in estado:
            print(f"  {nombre}: {estado}")
    saltados = sum(1 for _, r in resultados if "que no es el de ninguna empresa" in r)
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {nuevas} fichero(s) nuevos, {sum(1 for _, r in resultados if r == 'ya estaba')} ya estaban, {saltados} de otras empresas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
