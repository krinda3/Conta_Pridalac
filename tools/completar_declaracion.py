"""Completa el justificante y las fechas de una declaración presentada importada que los tiene vacíos (sólo rellena lo que está vacío; nunca pisa).

    python tools/completar_declaracion.py --nombre empresa_b --modelo 303 --anio 2022 --periodo 1 --justificante 3033015265052 --fecha 2022-04-14   # sólo enseña
    python tools/completar_declaracion.py --nombre empresa_b --modelo 303 --anio 2022 --periodo 1 --pdf "ruta al PDF de la sede" --aplicar            # lee los datos del PDF y lo guarda

El justificante y la fecha se leen del PDF de la sede si se indica con `--pdf`. Con el programa cerrado y una copia hecha.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.servicios.justificante_aeat import leer_justificante

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--anio", required=True, type=int)
    ap.add_argument("--periodo", required=True, type=int)
    ap.add_argument("--tipo", type=int, default=1)
    ap.add_argument("--justificante")
    ap.add_argument("--fecha", type=date.fromisoformat, help="AAAA-MM-DD: fecha en que se presentó")
    ap.add_argument("--pdf", type=Path, help="PDF de la sede del que leer el justificante y la fecha")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd")
    a = ap.parse_args(argv)
    if a.pdf is not None:
        leido = leer_justificante(a.pdf.read_bytes())
        if leido is None:
            print("El PDF no se puede leer como justificante de la sede.")
            return 1
        a.justificante, a.fecha = a.justificante or leido.justificante, a.fecha or leido.momento.date()
    sesion = nueva_sesion(crear_motor(a.datos / f"{a.nombre}.sqlite"))
    empresa = sesion.scalars(select(Empresa)).first()
    d = sesion.scalar(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == a.modelo, DeclaracionPresentada.anio == a.anio, DeclaracionPresentada.periodo == a.periodo,
        DeclaracionPresentada.tipo == a.tipo))
    if d is None:
        print(f"No hay un {a.modelo} de {a.periodo}T {a.anio} de tipo {a.tipo}.")
        return 1
    cambios = {}
    if a.justificante and not d.justificante:
        cambios["justificante"] = a.justificante
    if a.fecha and not d.fecha_envio:
        cambios["fecha_envio"] = a.fecha
    if a.fecha and not d.fecha_emision:
        cambios["fecha_emision"] = a.fecha
    ya = [nombre for nombre, valor in (("justificante", a.justificante and d.justificante), ("fecha de envío", a.fecha and d.fecha_envio)) if valor]
    if ya:
        print(f"Ya tiene {', '.join(ya)}: no se pisa.")
    if not cambios:
        print("Nada que completar.")
        return 0
    print(f"{a.modelo} {a.periodo}T {a.anio} (tipo {d.tipo}): " + ", ".join(f"{c} = {v}" for c, v in cambios.items()))
    if a.aplicar:
        for c, v in cambios.items():
            setattr(d, c, v)
        sesion.commit()
        print("Hecho.")
    else:
        print("(añada --aplicar para guardarlo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
