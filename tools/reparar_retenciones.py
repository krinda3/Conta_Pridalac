"""Anota en las facturas recibidas la retención de IRPF que sólo estaba en su asiento (la auditoría las da como «asiento distinto del regenerado»).

    python tools/reparar_retenciones.py --bd datos_locales/bd/empresa_a.sqlite --en-la-base-real            (simula: dice lo que haría)
    python tools/reparar_retenciones.py --bd datos_locales/bd/empresa_a.sqlite --aplicar --en-la-base-real  (lo hace)

Sólo añade a cada factura el ajuste de la retención, y sólo si con él su asiento regenerado queda igual al que hay. No cambia ningún asiento, importe ni fecha, así que sirve también en los
ejercicios cerrados. Se niega a trabajar sobre la carpeta de datos de la aplicación salvo con `--en-la-base-real`.
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
from conta_pridalac.servicios.retenciones_facturas import reparar
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la empresa")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios (sin esto sólo se cuenta lo que se haría)")
    ap.add_argument("--en-la-base-real", action="store_true", help="permite trabajar sobre la carpeta de datos de la aplicación")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if not bd.is_file():
        ap.error(f"no existe {bd}")
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
            hechas = [r for ej in sesion.scalars(select(Ejercicio).order_by(Ejercicio.anio)) for r in reparar(sesion, ej)]
            sesion.commit()
        finally:
            sesion.close()
            motor.dispose()
    for r in hechas:
        print(f"  {r.anio} · factura {r.factura} ({r.numero_factura}): {r.resultado}" + (f" · cuenta {r.cuenta}, importe {r.importe}" if r.cuenta else ""))
    anadidas = sum(1 for r in hechas if r.resultado == "añadido")
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {anadidas} factura(s) con la retención anotada, {len(hechas) - anadidas} sin tocar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
