"""Compara el cálculo del 111 desde los libros con los ficheros presentados (sólo lectura).

    python tools/comparar_111.py --nombre empresa_a [--detalle]

Lee `datos_locales/bd/<nombre>.sqlite` y los `AEAT/C000X_111_<año>_<n>T.111` de esa empresa (por su NIF), y para cada trimestre enseña si coinciden el tipo de declaración, el nº de perceptores,
las percepciones y las retenciones (un céntimo de diferencia se cuenta como redondeo). No modifica nada.
"""
from __future__ import annotations

import argparse
import glob
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.ficheros_aeat.fichero111 import casillas_de, leer
from conta_pridalac.servicios.modelo111 import calcular_111

RAIZ = Path(__file__).resolve().parents[1]
CERO = Decimal("0")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--detalle", action="store_true")
    a = ap.parse_args(argv)
    sesion = nueva_sesion(crear_motor(RAIZ / "datos_locales" / "bd" / f"{a.nombre}.sqlite"))
    ejercicios = {e.anio: e for e in sesion.scalars(select(Ejercicio))}
    nif = next(iter(ejercicios.values())).empresa.nif
    iguales = total = 0
    for ruta in sorted(glob.glob(str(RAIZ / "AEAT" / "C000?_111_*_?T.111"))):
        texto = Path(ruta).read_text(encoding="latin-1")
        c = leer(texto)
        if c[7].strip() != nif or int(c[10]) not in ejercicios or not c[11].endswith("T"):
            continue
        total += 1
        anio, periodo = int(c[10]), int(c[11][0])
        presentado, calculo = casillas_de(texto), calcular_111(sesion, ejercicios[anio], periodo)
        presentado.setdefault(28, CERO)
        difs = {k: (presentado.get(k, CERO), calculo[k]) for k in (7, 8, 9, 28, 30) if abs(presentado.get(k, CERO) - calculo[k]) > (CERO if k == 7 else Decimal('0.01'))}
        tipo_calculado = "N" if not calculo[30] else "U"
        marca = "igual" if not difs and c[6] == tipo_calculado else "DIFIERE"
        iguales += marca == "igual"
        print(f"{anio}-{periodo}T  tipo {c[6]} / {tipo_calculado}  {marca}" + (f"  {difs}" if difs else "") + (f"  (presentado: {presentado})" if a.detalle and presentado else ""))
        if a.detalle:
            for l in calculo.lineas:
                print(f"      {l.asiento} {l.fecha:%d/%m/%Y} {l.perceptor[:34]:<34} percepción {l.percepcion} retención {l.retencion} ({l.porcentaje} %)")
            for av in calculo.avisos:
                print("      aviso:", av)
    print(f"\n{iguales} de {total} trimestres coinciden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
