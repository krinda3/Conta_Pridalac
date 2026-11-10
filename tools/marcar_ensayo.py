"""Marca como COPIA DE ENSAYO la base de una empresa (un `.sqlite` copiado fuera de la carpeta de datos de la aplicación).

    python tools/marcar_ensayo.py --bd datos_locales/ensayo/empresa_a.sqlite            (simula: dice si ya está marcada)
    python tools/marcar_ensayo.py --bd datos_locales/ensayo/empresa_a.sqlite --aplicar  (la marca)

Una base marcada no puede generar ficheros para la sede ni registrar presentaciones, y todas las pantallas lo avisan. La marca no se puede quitar: si hace falta la base real, se restaura una copia de seguridad.
Se niega a marcar la carpeta de datos de la aplicación, que es la contabilidad real.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.servicios.entorno import es_ensayo, marcar_ensayo
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la copia")
    ap.add_argument("--aplicar", action="store_true", help="la marca (sin esto sólo se dice si ya lo está)")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if not bd.is_file():
        ap.error(f"no existe {bd}")
    if bd.parent == Configuracion().datos.resolve():
        print(f"{bd} está en la carpeta de datos de la aplicación: es la contabilidad real y no se marca como ensayo. Trabaje sobre una copia fuera de ella.", file=sys.stderr)
        return 2
    motor = crear_motor(bd)
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    try:
        empresa = sesion.scalars(select(Empresa)).one()
        if es_ensayo(sesion, empresa.id):
            print(f"{empresa.nombre}: ya estaba marcada como copia de ensayo.")
            return 0
        if not a.aplicar:
            print(f"Simulación: {empresa.nombre} NO está marcada como copia de ensayo; con --aplicar se marcaría.")
            return 0
        marcar_ensayo(sesion, empresa.id, "marcada con marcar_ensayo.py")
        sesion.commit()
        print(f"{empresa.nombre}: marcada como copia de ensayo.")
        return 0
    finally:
        sesion.close()
        motor.dispose()


if __name__ == "__main__":
    sys.exit(main())
