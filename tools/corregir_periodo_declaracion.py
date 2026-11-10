r"""Cambia el periodo (y, si se pide, el tipo) de una declaración presentada importada, por ejemplo el 2T de 2022 de Empresa B que el programa anterior guardó como periodo 6.

    python tools/corregir_periodo_declaracion.py --nombre empresa_b --modelo 111 --anio 2022 --de 6 --a 2            # sólo enseña lo que haría
    python tools/corregir_periodo_declaracion.py --nombre empresa_b --modelo 111 --anio 2022 --de 6 --a 2 --aplicar  # lo guarda
    python tools/corregir_periodo_declaracion.py --nombre empresa_b --modelo 303 --anio 2022 --de 6 --a 2 --tipo 2 --tipo-destino 3

Sólo cambia el periodo y el tipo: no toca importes, justificante ni PDF. No lo hace si ya hay otra declaración del mismo tipo en el periodo de destino (en ese caso, elija un tipo libre con
`--tipo-destino`). Con el programa cerrado y una copia hecha.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa
from conta_pridalac.db.sesion import crear_motor, nueva_sesion

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--anio", required=True, type=int)
    ap.add_argument("--de", required=True, type=int, dest="origen")
    ap.add_argument("--a", required=True, type=int, dest="destino", choices=(1, 2, 3, 4))
    ap.add_argument("--tipo", type=int, help="sólo las de este tipo (por defecto, todas las del periodo de origen)")
    ap.add_argument("--tipo-destino", type=int, help="el tipo que tendrán tras el cambio (por defecto, el que tienen)")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd")
    a = ap.parse_args(argv)
    sesion = nueva_sesion(crear_motor(a.datos / f"{a.nombre}.sqlite"))
    empresa = sesion.scalars(select(Empresa)).first()
    consulta = select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == a.modelo, DeclaracionPresentada.anio == a.anio)
    filtro_origen = [DeclaracionPresentada.periodo == a.origen] + ([DeclaracionPresentada.tipo == a.tipo] if a.tipo else [])
    origen = list(sesion.scalars(consulta.where(*filtro_origen)))
    if not origen:
        print(f"No hay ningún {a.modelo} de {a.anio} con periodo {a.origen}.")
        return 1
    ocupados = {d.tipo for d in sesion.scalars(consulta.where(DeclaracionPresentada.periodo == a.destino))}
    if ocupados & {a.tipo_destino or d.tipo for d in origen}:
        print(f"Ya hay un {a.modelo} de {a.anio} en el periodo {a.destino} del mismo tipo: no se cambia nada (use --tipo-destino con un tipo libre).")
        return 1
    for d in origen:
        nuevo_tipo = a.tipo_destino or d.tipo
        print(f"{a.modelo} {a.anio}: periodo {d.periodo} → {a.destino}, tipo {d.tipo} → {nuevo_tipo} (justificante {d.justificante or '—'}, emitida {d.fecha_emision or '—'}, PDF {d.pdf_nombre or '—'})")
        if a.aplicar:
            d.periodo, d.tipo = a.destino, nuevo_tipo
    if a.aplicar:
        sesion.commit()
        print("Hecho.")
    else:
        print("(añada --aplicar para guardarlo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
