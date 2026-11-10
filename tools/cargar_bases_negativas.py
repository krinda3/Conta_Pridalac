"""Carga en una empresa el histórico de bases imponibles negativas pendientes de compensar (los datos de la pantalla «Bases imponibles negativas» del programa anterior) desde un JSON.

    python tools/cargar_bases_negativas.py --bd datos_locales/bd/empresa_a.sqlite --json datos_locales/bases_negativas_empresa_a.json --en-la-base-real            (simula)
    python tools/cargar_bases_negativas.py --bd datos_locales/bd/empresa_a.sqlite --json datos_locales/bases_negativas_empresa_a.json --aplicar --en-la-base-real  (lo hace)

El JSON es `{"nif_empresa": "B00000010", "bases": [{"anio": 2014, "base": "4161.28", "aplicado": "0.00", "pendiente_manual": "4161.28"}]}`. `pendiente_manual` solo si el saldo viene
de otro programa (la casilla «Manual» del programa anterior). Un año que ya está se actualiza. Antes de aplicar se guarda una copia de la base junto a ella (`.antes_bn_AAAAMMDD_HHMMSS`).
Se niega a trabajar sobre la carpeta de datos de la aplicación salvo con `--en-la-base-real`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.web.config import Configuracion


def cargar(sesion, datos: dict) -> list[str]:
    empresa = sesion.scalars(select(Empresa)).one()
    if (datos.get("nif_empresa") or "").upper() != (empresa.nif or "").upper():
        raise ErrorContable(f"El JSON es del NIF {datos.get('nif_empresa')}, no del de la empresa ({empresa.nif})")
    previas = {b.anio: b for b in isd.bases_negativas(sesion, empresa.id)}
    hechos = []
    for d in datos["bases"]:
        anio = int(d["anio"])
        manual = Decimal(d["pendiente_manual"]) if d.get("pendiente_manual") not in (None, "") else None
        fila = isd.guardar_base_negativa(sesion, empresa.id, anio, Decimal(d["base"]), Decimal(d.get("aplicado") or "0"), manual)
        hechos.append(f"{anio}: base {fila.base} · aplicado {fila.aplicado} · pendiente {fila.pendiente}" + (" (manual)" if manual is not None else "") + (" [actualiza]" if anio in previas else ""))
    return hechos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la empresa")
    ap.add_argument("--json", required=True, help="el JSON con las bases negativas")
    ap.add_argument("--aplicar", action="store_true", help="hace los cambios (sin esto sólo se dice lo que se cargaría)")
    ap.add_argument("--en-la-base-real", action="store_true", help="permite trabajar sobre la carpeta de datos de la aplicación")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if not bd.is_file() or not Path(a.json).is_file():
        ap.error("no existe la base o el JSON")
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    datos = json.loads(Path(a.json).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name  # sin --aplicar se trabaja sobre otra copia y no se guarda nada
        if a.aplicar:
            copia = bd.with_name(bd.name + datetime.now().strftime(".antes_bn_%Y%m%d_%H%M%S"))
            shutil.copyfile(bd, copia)
            print(f"Copia de seguridad: {copia}")
        else:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            try:
                hechos = cargar(sesion, datos)
            except ErrorContable as e:
                sesion.rollback()
                print(f"No se puede: {e}", file=sys.stderr)
                return 1
            sesion.commit()
        finally:
            sesion.close()
            motor.dispose()
    for h in hechos:
        print(f"  {h}")
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {len(hechos)} año(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
