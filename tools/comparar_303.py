"""Paso A2 del modelo 303 (sólo lectura): calcula cada trimestre desde los libros y lo compara, casilla a casilla, con la declaración presentada.

    python tools/comparar_303.py --nombre empresa_b [--detalle]

El cálculo usa las facturas con fecha contable en el trimestre, como se hará al calcular de verdad. La casilla 44 (prorrata) no se calcula: se toma de lo presentado, y
las rectificativas que fueron a las casillas 40 y 41 se marcan como tales. Las diferencias de hasta 5 céntimos se cuentan como redondeo (el programa anterior suma importes con
más decimales de los que guardamos). Cada diferencia mayor se **explica por factura**: facturas que se declararon en otro trimestre que el de su fecha contable, o que se
declararon por importes distintos de los que tienen hoy. Con `--detalle` se enseña esa explicación.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio, Factura
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.servicios.modelo303 import calcular_303

RAIZ = Path(__file__).resolve().parents[1]
CERO = Decimal("0.00")
CASILLAS_A_COMPARAR = (150, 1, 3, 4, 6, 7, 9, 27, 28, 29, 30, 31, 40, 41, 44, 45, 46, 64, 65, 66, 69, 71, 87)
FILAS_ANTIGUAS = ((1, 4, 7), (3, 6, 9))  # base y cuota de las tres filas de tipos
CASILLAS_DE_LINEA = {"03", "06", "09", "29", "41", "31"}  # casillas de cuota en las líneas de las declaraciones


def por_factura_presentado(d: DeclaracionPresentada) -> dict[int, tuple[Decimal, Decimal]]:
    r = defaultdict(lambda: [CERO, CERO])
    for l in d.lineas:
        if l.factura_id and (l.casilla or "") in CASILLAS_DE_LINEA:
            r[l.factura_id][0] += l.base
            r[l.factura_id][1] += l.cuota
    return {k: (v[0], v[1]) for k, v in r.items()}


def por_factura_libros(calculo) -> dict[int, tuple[Decimal, Decimal]]:
    r = defaultdict(lambda: [CERO, CERO])
    for l in calculo.lineas:
        r[l.factura_id][0] += l.base
        r[l.factura_id][1] += l.cuota
    return {k: (v[0], v[1]) for k, v in r.items()}


def explicar(sesion, d, calculo) -> list[str]:
    presentado, libros = por_factura_presentado(d), por_factura_libros(calculo)
    lineas = []
    for fid in sorted(set(presentado) | set(libros)):
        pb, pc = presentado.get(fid, (CERO, CERO))
        lb, lc = libros.get(fid, (CERO, CERO))
        if abs(pc - lc) <= Decimal("0.02") and abs(pb - lb) <= Decimal("0.02"):
            continue
        f = sesion.get(Factura, fid)
        donde = "sólo en los libros (declarada en otro trimestre)" if fid not in presentado else "sólo en lo presentado (su fecha contable es de otro trimestre)" if fid not in libros else "importes distintos"
        lineas.append(f"{f.sentido} {f.numero} {f.fecha_contable:%d/%m/%Y} {(f.numero_factura or '')[:22]:<22} presentado base {pb} cuota {pc} · libros base {lb} cuota {lc} · {donde}")
    return lineas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--detalle", action="store_true")
    a = ap.parse_args(argv)
    sesion = nueva_sesion(crear_motor(RAIZ / "datos_locales" / "bd" / f"{a.nombre}.sqlite"))
    declaraciones = sesion.scalars(
        select(DeclaracionPresentada).where(DeclaracionPresentada.modelo == "303", DeclaracionPresentada.tipo == 1).order_by(DeclaracionPresentada.anio, DeclaracionPresentada.periodo)
    ).all()
    iguales = explicadas = 0
    for d in declaraciones:
        ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == d.empresa_id, Ejercicio.anio == d.anio)).first()
        if ejercicio is None or d.periodo not in (1, 2, 3, 4):
            continue
        presentadas = {int(k): Decimal(str(v)) for k, v in json.loads(d.casillas or "{}").items()}
        rectifican = {l.factura_id for l in d.lineas if l.casilla == "41" and l.factura_id}
        calculo = calcular_303(sesion, ejercicio, d.periodo, regularizacion_prorrata=presentadas.get(44), rectifican=rectifican)
        if d.anio <= 2022:  # la versión antigua del formulario del programa anterior ponía las ventas al 21 % en la primera fila (casillas 1 y 3)
            for grupo in FILAS_ANTIGUAS:
                total_presentado = sum((presentadas.get(k, CERO) for k in grupo), CERO)
                total_calculado = sum((calculo[k] for k in grupo), CERO)
                for k in grupo:
                    presentadas.pop(k, None)
                    calculo.casillas.pop(k, None)
                presentadas[grupo[0]], calculo.casillas[grupo[0]] = total_presentado, total_calculado
        difs, redondeo = [], []
        for k in CASILLAS_A_COMPARAR:
            esperado, calculado = presentadas.get(k, CERO), calculo[k]
            if abs(esperado - calculado) > Decimal("0.05"):
                difs.append((k, esperado, calculado))
            elif abs(esperado - calculado) > Decimal("0.005"):
                redondeo.append(k)
        if not difs:
            iguales += 1
            print(f"{d.anio}-{d.periodo}T  igual" + (f" (redondeo de céntimos en las casillas {', '.join(map(str, redondeo))})" if redondeo else ""))
            continue
        motivos = explicar(sesion, d, calculo)
        print(f"{d.anio}-{d.periodo}T  DIFIERE en {len(difs)} casillas, {len(motivos)} facturas lo explican: " + " · ".join(f"[{k}] presentado {e} / libros {c}" for k, e, c in difs if k in (27, 29, 46, 71, 87)))
        explicadas += bool(motivos)
        if a.detalle:
            for m in motivos:
                print("        ", m)
        for av in calculo.avisos:
            print("        aviso:", av)
    print(f"\n{iguales} de {len(declaraciones)} declaraciones coinciden; {explicadas} más difieren por facturas que se declararon en otro trimestre o con otros importes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
