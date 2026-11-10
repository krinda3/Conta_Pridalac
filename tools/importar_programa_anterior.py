"""Crea la base de una empresa a partir de un respaldo del programa anterior (`C000X.SDB`) y, si se indica, de la carpeta de comprobantes.

Uso (no sobrescribe nada: si la base de destino existe, se niega):

    python tools/importar_programa_anterior.py --sdb D:/OneDrive/Downloads/C0001.SDB --empresa 1 --nombre empresa_b \
        --comprobantes "docs/Exportaciones del programa anterior/Comprobantes"

Escribe la base en `datos_locales/bd/<nombre>.sqlite`, los comprobantes en `datos_locales/justificantes/` y el informe
de auditoría en `datos_locales/salida/auditoria_comprobantes_<nombre>.txt`. Para usarla en la aplicación: `CONTA_DATOS=datos_locales/bd`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.migracion.comprobantes import importar_comprobantes, informe
from conta_pridalac.migracion.programa_anterior import cargar_sdb
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos

RAIZ = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdb", required=True, type=Path)
    ap.add_argument("--empresa", required=True, type=int, help="nº de empresa del programa anterior (1 Empresa B, 2 Empresa A)")
    ap.add_argument("--nombre", required=True, help="nombre de la base, sin extensión (empresa_b, empresa_a)")
    ap.add_argument("--comprobantes", type=Path)
    ap.add_argument("--ficha", type=Path, help="JSON con datos de la empresa que el programa anterior no guarda (por defecto datos_locales/ficha_<nombre>.json si existe)")
    ap.add_argument("--desde", type=int, help="primer ejercicio que se carga (por defecto, todos)")
    ap.add_argument("--destino", type=Path, default=RAIZ / "datos_locales" / "bd")
    ap.add_argument("--almacen", type=Path, default=RAIZ / "datos_locales" / "justificantes")
    a = ap.parse_args(argv)

    base = a.destino / f"{a.nombre}.sqlite"
    if base.exists():
        print(f"Ya existe {base}: bórrela o renómbrela antes de importar.", file=sys.stderr)
        return 1
    a.destino.mkdir(parents=True, exist_ok=True)
    motor = crear_motor(base)
    crear_esquema(motor)
    with nueva_sesion(motor) as sesion:
        ficha_ruta = a.ficha or RAIZ / "datos_locales" / f"ficha_{a.nombre}.json"
        ficha = json.loads(ficha_ruta.read_text(encoding="utf-8")) if ficha_ruta.is_file() else None
        r = cargar_sdb(sesion, a.sdb, codigo_empresa=a.empresa, desde=a.desde, ficha=ficha)
        print(f"{r.ejercicios} ejercicios · {r.cuentas} cuentas · {r.terceros} terceros · {r.asientos} asientos · {r.apuntes} apuntes · {r.facturas} facturas · {r.declaraciones} declaraciones de IVA · {r.bienes} bienes · {r.bancos} bancos · {r.movimientos} movimientos · {r.pagos} pagos · {r.vencimientos} vencimientos")
        print(f"Líneas con importe negativo pasadas al lado contrario: {r.lineas_con_signo_negativo}")
        for d in r.descuadrados:
            print("DESCUADRADO", d)
        for av in r.avisos:
            print("AVISO", av)
        if a.comprobantes:
            empresa = sesion.scalars(select(Empresa)).one()
            c = importar_comprobantes(sesion, AlmacenAdjuntos(a.almacen), empresa, a.comprobantes)
            salida = RAIZ / "datos_locales" / "salida"
            salida.mkdir(parents=True, exist_ok=True)
            texto = informe(c, f"{empresa.nombre} ({a.sdb.name})")
            (salida / f"auditoria_comprobantes_{a.nombre}.txt").write_text(texto, encoding="utf-8")
            print(texto.splitlines()[1])
        sesion.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
