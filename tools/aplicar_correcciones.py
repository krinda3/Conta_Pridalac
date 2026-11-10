"""Aplica a una empresa una lista de correcciones de facturas (JSON) y regenera sus asientos.

    python tools/aplicar_correcciones.py --nombre empresa_b --correcciones datos_locales/correcciones_empresa_b.json [--simular]

Cada corrección es un objeto con `ejercicio`, `sentido` (R o E), `numero` y `motivo`, y UNA de estas acciones:
- `"exento": 13.20`  añade una línea de IVA al 0 % (importe exento o no sujeto que va incluido en el total de la factura);
- `"base": 14.67`    cambia la base de la única línea de IVA (y, con `"cuota": 5.33`, también su cuota);
- `"total": 165.66`  (junto a `exento`) cambia además el total de la factura y el de su único vencimiento.
La factura se vuelve a grabar con `servicios.facturas.grabar_factura`, que regenera su asiento, y el motivo se anota en sus notas. Una corrección sólo se
aplica si deja el total de la factura igual a base + IVA + recargo + ajustes; si no, se salta y se cuenta. Los ejercicios cerrados no se tocan.
Es idempotente: una corrección ya aplicada (su motivo está en las notas) se salta. Con `--simular` trabaja sobre una copia de la base y no guarda nada.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Ejercicio, Factura, FacturaIva, Vencimiento
from conta_pridalac.db.sesion import crear_motor, nueva_sesion
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.facturas import total_esperado
from conta_pridalac.servicios.facturas import grabar_factura

RAIZ = Path(__file__).resolve().parents[1]


def aplicar(sesion, c: dict) -> str | None:
    """Aplica una corrección y devuelve su resumen; `None` si ya estaba aplicada."""
    ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == c["ejercicio"])).one()
    if ejercicio.cerrado:
        raise ErrorContable(f"el ejercicio {ejercicio.anio} está cerrado")
    f = sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == c["sentido"], Factura.numero == c["numero"])).one()
    marca = f"Corrección: {c['motivo']}"
    if marca in (f.notas or ""):
        return None
    antes = f"base+IVA {total_esperado(f)} · total {f.total}"
    if "total" in c:
        vencimientos = list(sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)))
        if len(vencimientos) != 1:
            raise ErrorContable("el total sólo se cambia si la factura tiene un único vencimiento")
        vencimientos[0].importe = -dinero(c["total"]) if vencimientos[0].importe < 0 else dinero(c["total"])
        f.total = dinero(c["total"])
    if "exento" in c:
        f.ivas.append(FacturaIva(base=dinero(c["exento"]), pct_iva=dinero(0), cuota_iva=dinero(0), deducible=True))
    elif "base" in c:
        if len(f.ivas) != 1:
            raise ErrorContable("hay más de una línea de IVA: no se sabe cuál cambiar")
        f.ivas[0].base = dinero(c["base"])
        if "cuota" in c:
            f.ivas[0].cuota_iva = dinero(c["cuota"])
    else:
        raise ErrorContable("la corrección no trae ninguna acción")
    sesion.flush()
    if total_esperado(f) != f.total:
        raise ErrorContable(f"con el cambio la suma ({total_esperado(f)}) no iguala el total ({f.total})")
    f.notas = ((f.notas + "\n") if f.notas else "") + marca
    grabar_factura(sesion, ejercicio, f)
    return f"{antes} → base+IVA {total_esperado(f)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--correcciones", required=True, type=Path)
    ap.add_argument("--destino", type=Path, default=RAIZ / "datos_locales" / "bd")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args(argv)
    lista = json.loads(a.correcciones.read_text(encoding="utf-8"))
    origen = a.destino / f"{a.nombre}.sqlite"
    if a.simular:  # se trabaja sobre una copia: la base real no se toca
        origen = Path(shutil.copy(origen, Path(tempfile.mkdtemp()) / origen.name))
    motor = crear_motor(origen)
    hechas = ya = saltadas = 0
    with nueva_sesion(motor) as sesion:
        for c in lista:
            etiqueta = f"{c['ejercicio']} {c['sentido']} {c['numero']}"
            try:
                resumen = aplicar(sesion, c)
                if resumen is None:
                    print(f"YA     {etiqueta}: ya estaba aplicada")
                    ya += 1
                    continue
                sesion.commit()
                print(f"OK     {etiqueta}: {resumen}")
                hechas += 1
            except (ErrorContable, ValueError) as ex:
                sesion.rollback()
                print(f"SALTA  {etiqueta}: {ex}")
                saltadas += 1
    motor.dispose()
    print(f"{hechas} corregidas, {ya} ya aplicadas, {saltadas} saltadas{' (simulación: no se ha guardado nada)' if a.simular else ''}")
    return 0 if not saltadas else 1


if __name__ == "__main__":
    sys.exit(main())
