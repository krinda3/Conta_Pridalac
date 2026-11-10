"""Compara las casillas del 390 que calcula Conta con las de un 390 ya presentado.

    python tools/comparar_390.py --bd datos_locales/bd/empresa_b.sqlite --anio 2025 --esperado datos_locales/390_presentado_2025_empresa_b.json

El JSON es `{"casillas": {"05": 31768.60, "06": 6671.40, ...}, "notas": {"606": "explicación de una diferencia conocida"}}`, con las cifras del PDF presentado. Sólo lee: trabaja sobre una copia
temporal de la base. Sale con código 1 si alguna casilla difiere más de la tolerancia (2 céntimos) y no tiene nota que la explique.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.servicios.modelo390 import TOLERANCIA, calcular_390


def _euros(v: Decimal | None) -> str:
    return "—" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--esperado", required=True)
    a = ap.parse_args(argv)
    esperado = json.loads(Path(a.esperado).read_text(encoding="utf-8"))
    casillas = {int(k): Decimal(str(v)) for k, v in esperado["casillas"].items()}
    notas = {int(k): v for k, v in esperado.get("notas", {}).items()}
    with tempfile.TemporaryDirectory() as t:
        copia = Path(t) / Path(a.bd).name
        shutil.copyfile(a.bd, copia)
        motor = crear_motor(copia)
        sesion = nueva_sesion(motor)
        try:
            empresa = sesion.scalars(select(Empresa)).one()
            ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id, Ejercicio.anio == a.anio)).one()
            calculo = calcular_390(sesion, ejercicio)
        finally:
            sesion.close()
            motor.dispose()
    print(f"{empresa.nombre} · 390 de {a.anio} · 303 usados: " + ", ".join(f"{p}T {o}" for p, o in calculo.origen_303.items()))
    print(f"\n{'Casilla':>8} {'Presentado':>14} {'Conta':>14} {'Diferencia':>12}")
    sin_explicar = 0
    for casilla in sorted(casillas):
        mio = calculo.casillas.get(casilla, Decimal("0.00"))
        dif = mio - casillas[casilla]
        marca = "" if abs(dif) <= TOLERANCIA else ("  ← " + notas[casilla] if casilla in notas else "  ← DIFERENCIA SIN EXPLICAR")
        sin_explicar += abs(dif) > TOLERANCIA and casilla not in notas
        print(f"{casilla:>8} {_euros(casillas[casilla]):>14} {_euros(mio):>14} {_euros(dif):>12}{marca}")
    for k in calculo.controles:
        print(f"\nControl {k.gravedad}: {k.texto}")
    print(f"\n{len(casillas)} casillas comparadas · {sin_explicar} diferencia(s) sin explicar.")
    return 1 if sin_explicar else 0


if __name__ == "__main__":
    sys.exit(main())
