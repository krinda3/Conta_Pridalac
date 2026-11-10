"""Copias de seguridad desde la línea de comandos (lo mismo que la pantalla «Copias de seguridad»).

    python tools/copia_seguridad.py hacer empresa_b
    python tools/copia_seguridad.py listar empresa_b
    python tools/copia_seguridad.py verificar empresa_b copia_empresa_b_20261027_180000.zip
    python tools/copia_seguridad.py restaurar empresa_b copia_empresa_b_20261027_180000.zip --si

Usa las mismas carpetas que la aplicación (`CONTA_DATOS`, `CONTA_ALMACEN` y `CONTA_COPIAS`, o `datos_locales/`). Para restaurar hay que parar antes la aplicación web.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import copias as svc
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=["hacer", "listar", "verificar", "restaurar"])
    ap.add_argument("empresa", help="nombre de la empresa (el de su fichero .sqlite sin extensión)")
    ap.add_argument("copia", nargs="?", help="fichero .zip (nombre dentro de la carpeta de copias, o ruta completa)")
    ap.add_argument("--si", action="store_true", help="confirma la restauración")
    a = ap.parse_args(argv)
    config = Configuracion()
    bd = config.datos / f"{a.empresa}.sqlite"
    try:
        if a.orden == "hacer":
            ruta = svc.hacer_copia(a.empresa, bd, config.almacen, config.copias)
            print(f"Copia hecha y verificada: {ruta}")
            return 0
        if a.orden == "listar":
            for c in svc.listar_copias(config.copias, a.empresa):
                print(f"{c.momento:%d/%m/%Y %H:%M}  {c.tamano / 1024 / 1024:8.1f} MB  {c.tablas.get('factura', 0):6} facturas  {c.nombre}")
            return 0
        if not a.copia:
            ap.error("falta el fichero de la copia")
        ruta = Path(a.copia) if Path(a.copia).is_file() else config.copias / a.copia
        if a.orden == "verificar":
            problemas = svc.verificar_copia(ruta)
            print("\n".join(problemas) if problemas else f"{ruta.name}: en buen estado")
            return 1 if problemas else 0
        if not a.si:
            print("Restaurar sustituye la base de datos y los justificantes de la empresa. Repita la orden con --si para confirmar.")
            return 2
        previa = svc.restaurar_copia(ruta, a.empresa, bd, config.almacen, config.copias)
        print(f"Restaurada. El estado anterior se guardó en {previa}")
        return 0
    except ErrorContable as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
