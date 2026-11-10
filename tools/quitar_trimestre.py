"""Quita de una COPIA de la base las facturas recibidas de un periodo y sus pagos, para ensayar la conciliación del trimestre.

    python tools/quitar_trimestre.py --bd datos_locales/ensayo/empresa_a.sqlite --desde 2026-07-01 --hasta 2026-09-30            (simula: cuenta lo que quitaría)
    python tools/quitar_trimestre.py --bd datos_locales/ensayo/empresa_a.sqlite --desde 2026-07-01 --hasta 2026-09-30 --aplicar (lo hace)

Quita las declaraciones 303 presentadas de esos trimestres (si no, el bloqueo de trimestre presentado impide borrar), los pagos de las facturas, los movimientos de banco que se quedan sin
pagos y las facturas. No toca las emitidas ni el extracto. Se niega a trabajar sobre la carpeta de datos de la aplicación salvo que se indique `--en-la-base-real`: haga antes una copia
del fichero .sqlite fuera de esa carpeta.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.ensayo import quitar_recibidas
from conta_pridalac.servicios.entorno import marcar_ensayo
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la copia")
    ap.add_argument("--desde", required=True, help="AAAA-MM-DD, fecha contable")
    ap.add_argument("--hasta", required=True, help="AAAA-MM-DD, fecha contable")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios (sin esto sólo se cuenta lo que se quitaría)")
    ap.add_argument("--en-la-base-real", action="store_true", help="permite trabajar sobre la carpeta de datos de la aplicación")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if not bd.is_file():
        ap.error(f"no existe {bd}")
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    desde, hasta = date.fromisoformat(a.desde), date.fromisoformat(a.hasta)
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name  # sin --aplicar se trabaja sobre otra copia y no se guarda nada
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)  # una base antigua gana las columnas nuevas
        sesion = nueva_sesion(motor)
        try:
            ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == desde.year)).one()
            if not a.en_la_base_real:  # una copia fuera de la carpeta de datos queda marcada como ensayo: ya no puede presentar nada
                marcar_ensayo(sesion, ejercicio.empresa_id, "preparada con quitar_trimestre.py")
            r = quitar_recibidas(sesion, ejercicio, desde, hasta)
            sesion.commit()
        except ErrorContable as e:
            sesion.rollback()
            print(f"No se puede: {e}", file=sys.stderr)
            return 1
        finally:
            sesion.close()
            motor.dispose()
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {r.facturas} facturas recibidas ({r.total} €), {r.pagos} pagos, {r.movimientos_borrados} movimientos de banco borrados, "
          f"{r.movimientos_rehechos} rehechos, {r.declaraciones} declaraciones 303 quitadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
