"""Carga en una empresa los socios y los movimientos de sus participaciones desde un fichero JSON (los datos del libro de socios del programa anterior).

    python tools/cargar_socios.py --bd datos_locales/bd/empresa_a.sqlite --json datos_locales/socios_empresa_a.json --en-la-base-real            (simula: dice lo que cargaría)
    python tools/cargar_socios.py --bd datos_locales/bd/empresa_a.sqlite --json datos_locales/socios_empresa_a.json --aplicar --en-la-base-real  (lo hace)

El JSON es `{"nif_empresa": "B00000010", "socios": [{"nif", "nombre", "nacionalidad", "nacimiento": "14/04/1960", "domicilio", "poblacion", "provincia", "profesion", "estado_civil",
"movimientos": [{"fecha": "31/12/2013", "tipo": "Constitución", "concepto", "participaciones": 17500, "desde": 1, "hasta": 17500, "valor_nominal": "1.00"}]}]}`. Un socio que ya está (mismo NIF) no se toca.
Se niega a trabajar sobre la carpeta de datos de la aplicación salvo con `--en-la-base-real`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa, MovimientoSocio, Socio
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha
from conta_pridalac.web.config import Configuracion


def cargar(sesion, datos: dict) -> list[str]:
    empresa = sesion.scalars(select(Empresa)).one()
    if (datos.get("nif_empresa") or "").upper() != (empresa.nif or "").upper():
        raise ErrorContable(f"El JSON es del NIF {datos.get('nif_empresa')}, no del de la empresa ({empresa.nif})")
    existentes = {(s.nif or "").upper() for s in sesion.scalars(select(Socio).where(Socio.empresa_id == empresa.id))}
    hechos = []
    for orden, d in enumerate(datos["socios"], 1):
        if (d.get("nif") or "").upper() in existentes and d.get("nif"):
            hechos.append(f"{d['nombre']}: ya estaba")
            continue
        s = Socio(empresa_id=empresa.id, orden=orden, nif=(d.get("nif") or None), nombre=d["nombre"], nacionalidad=d.get("nacionalidad"), domicilio=d.get("domicilio"), poblacion=d.get("poblacion"),
                  provincia=d.get("provincia"), profesion=d.get("profesion"), estado_civil=d.get("estado_civil"), fecha_nacimiento=parsear_fecha(d["nacimiento"]) if d.get("nacimiento") else None)
        for m in d.get("movimientos", []):
            s.movimientos.append(MovimientoSocio(fecha=parsear_fecha(m["fecha"]), tipo=m.get("tipo", "Constitución"), concepto=m.get("concepto"), participaciones=int(m["participaciones"]),
                                                 desde=m.get("desde"), hasta=m.get("hasta"), valor_nominal=str(m.get("valor_nominal", "1.00"))))
        sesion.add(s)
        hechos.append(f"{d['nombre']}: {sum(int(m['participaciones']) for m in d.get('movimientos', []))} participaciones")
    return hechos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True, help="fichero .sqlite de la empresa")
    ap.add_argument("--json", required=True, help="el JSON con los socios")
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
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            try:
                hechos = cargar(sesion, datos)
            except ErrorContable as e:
                print(f"No se puede: {e}", file=sys.stderr)
                return 1
            sesion.commit()
        finally:
            sesion.close()
            motor.dispose()
    for h in hechos:
        print(f"  {h}")
    print(("Hecho" if a.aplicar else "Simulación (no se ha cambiado nada)") + f": {len(hechos)} socio(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
