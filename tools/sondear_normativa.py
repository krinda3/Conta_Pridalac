"""Pregunta a la sede de la AEAT si han cambiado los diseños de registro que usa Conta y dice qué hay por revisar. No descarga nada: solo pide el tamaño y la fecha de cada fichero.

    python tools/sondear_normativa.py                      (sondea y muestra el estado de todo)
    python tools/sondear_normativa.py --revisada 390       (marca esa fuente como revisada hoy)
    python tools/sondear_normativa.py --sin-red            (solo el calendario, sin consultar la sede)

Con red, también mira si ya existe el diseño del ejercicio siguiente. El resultado y las revisiones se guardan en `_normativa.json`, junto a las bases de datos.
"""
from __future__ import annotations

import argparse
import sys

from conta_pridalac.servicios import normativa as nv
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--revisada", metavar="CLAVE", help="marca esa fuente como revisada hoy (200, 202, 303, 390, 190, 347, 111, plazos, d2, legalia, pgc)")
    ap.add_argument("--sin-red", action="store_true")
    a = ap.parse_args(argv)
    config = Configuracion()
    if a.revisada:
        try:
            dia = nv.marcar_revisada(config, a.revisada)
        except ValueError as e:
            ap.error(str(e))
        print(f"{a.revisada}: marcada como revisada el {dia:%d/%m/%Y}")
    if not a.sin_red:
        nv.sondear_todo(config)
    hay_que_mirar = 0
    for e in nv.estados(config):
        s = e.sondeo
        if s.get("error"):
            sonda = f"sin respuesta ({s['error'][:50]})"
        elif s.get("cambiado") or s.get("siguiente_existe"):
            sonda = "¡CAMBIO EN LA SEDE!" if s.get("cambiado") else "¡YA HAY DISEÑO NUEVO!"
        elif s:
            sonda = f"sin cambios ({s['fecha']})"
        else:
            sonda = "sin sondeo automático"
        marca = "REVISAR" if (e.por_revisar or e.cambio_detectado) else "al día "
        hay_que_mirar += marca == "REVISAR"
        print(f"{marca}  {e.fuente.clave:<8} {e.fuente.nombre[:50]:<50} {e.fuente.version[:24]:<24} revisada {e.revisada:%d/%m/%Y} · próxima ventana {e.proxima:%d/%m/%Y} · {sonda}")
        if marca == "REVISAR":
            print(f"          → {e.fuente.que_hacer}")
    return 1 if hay_que_mirar else 0


if __name__ == "__main__":
    sys.exit(main())
