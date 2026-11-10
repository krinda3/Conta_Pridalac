"""Pasa las facturas recibidas de un ejercicio ABIERTO a las cuentas de gasto «con sentido» (la cuenta destino de su categoría) y deja esa cuenta en la ficha de los proveedores.

    python tools/reclasificar_gasto_ejercicio.py --bd ruta/empresa_a.sqlite --reglas datos_locales/categorias_gasto_empresa_a.json --anio 2026            (simula sobre una copia)
    python tools/reclasificar_gasto_ejercicio.py --bd ... --reglas ... --anio 2026 --aplicar --en-la-base-real --copia-hecha                        (lo hace)

Antes de reclasificar, carga las categorías y clasifica las facturas de todos los años (lo mismo que `cargar_categorias_gasto.py`, que es idempotente). Después:
1. crea las subcuentas nuevas (`cuentas_nuevas` de las reglas) y mueve cada factura a la cuenta destino de su categoría (no cambia importes, IVA ni fechas);
2. pone la cuenta destino en la ficha de los proveedores cuyas facturas son todas de una categoría;
3. hace los asientos de `regularizaciones` (p. ej. llevar a gasto el gasóleo que quedó en existencias).
Comprueba que el IVA (472/477) y las cuentas de proveedores no cambian, que no queda ningún asiento descuadrado, y enseña el efecto en el resultado del ejercicio. Los ejercicios cerrados no se tocan.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from conta_pridalac.db.integridad import asientos_descuadrados
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import categorias_gasto as cg
from conta_pridalac.web.config import Configuracion

CERO = Decimal("0.00")


def saldos_del_ejercicio(sesion, ejercicio_id: int) -> dict[str, Decimal]:
    return {c: Decimal(s) for c, s in sesion.execute(
        select(Cuenta.codigo, cg.NETO).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ejercicio_id, func.coalesce(Asiento.subtipo, "").notin_(("R", "Z"))).group_by(Cuenta.codigo))}


def eur(v) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--reglas", required=True)
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--en-la-base-real", action="store_true")
    ap.add_argument("--copia-hecha", action="store_true")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    if a.aplicar and not a.copia_hecha:
        print("Para aplicar hace falta una copia de seguridad antes: hágala y añada --copia-hecha.", file=sys.stderr)
        return 2
    reglas = json.loads(Path(a.reglas).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            empresa = sesion.scalars(select(Empresa)).one()
            ej = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id, Ejercicio.anio == a.anio)).one()
            antes = saldos_del_ejercicio(sesion, ej.id)
            cg.importar_catalogo(sesion, empresa.id, reglas)
            cg.clasificar_facturas(sesion, empresa.id, reglas)
            res = cg.reclasificar_ejercicio(sesion, empresa.id, ej, reglas)
            extra: list[str] = []
            for r in reglas.get("regularizaciones", []):
                extra += cg.regularizar_saldo(sesion, empresa.id, ej, prefijo=r["prefijo"], a=r["a"], fecha=date.fromisoformat(r["fecha"]), concepto=r["concepto"])
            sesion.flush()
            descuadrados = [x for e in sesion.scalars(select(Ejercicio)) for x in asientos_descuadrados(sesion, e.id)]
            if descuadrados:
                raise ErrorContable(f"Quedarían asientos descuadrados: {descuadrados[:5]}")
            despues = saldos_del_ejercicio(sesion, ej.id)
            cambios = {c: despues.get(c, CERO) - antes.get(c, CERO) for c in sorted(set(antes) | set(despues)) if despues.get(c, CERO) != antes.get(c, CERO)}
            prohibidos = {c: d for c, d in cambios.items() if c.startswith(("472", "477", "4000", "4100", "400", "410", "57"))}
            if prohibidos:
                raise ErrorContable(f"Cambiarían cuentas de IVA, proveedores o tesorería: {prohibidos}")
            resultado = sum((d for c, d in cambios.items() if c[0] in "67"), CERO)  # +gasto − ingreso: lo que empeora el resultado
            print(f"== {empresa.nombre} · ejercicio {a.anio}")
            print(f"\nCuentas nuevas ({len(res.cuentas_creadas)}):")
            for x in res.cuentas_creadas:
                print("  +", x)
            print(f"\nFacturas movidas de cuenta: {len(res.facturas_movidas)} · ya estaban bien: {res.sin_cambio} · con reparto (a mano): {len(res.con_reparto)} · sin cuenta destino: {len(res.sin_destino)}")
            for x in res.facturas_movidas:
                print("  ", x)
            for x in res.sin_destino:
                print("   SIN DESTINO:", x)
            for x in res.con_reparto:
                print("   CON REPARTO:", x)
            print(f"\nFichas de proveedor con cuenta de gasto nueva: {len(res.fichas)}")
            for x in res.fichas:
                print("  ", x)
            print(f"\nProveedores con facturas de varias categorías (ficha sin tocar): {len(res.fichas_varias)}")
            for x in res.fichas_varias:
                print("  ", x)
            for x in extra:
                print("\nAsiento de regularización:", x)
            print("\nCuentas cuyo saldo del ejercicio cambia (debe − haber):")
            for c, d in cambios.items():
                print(f"   {c}  {eur(d):>14}")
            print(f"\nEfecto en el resultado de {a.anio}: {'empeora' if resultado > 0 else 'mejora'} {eur(abs(resultado))} € (suma de gastos que suben o bajan; el IVA no cambia)")
            sesion.commit()
        except (ErrorContable, KeyError) as e:
            sesion.rollback()
            print(f"\nNO SE HA CAMBIADO NADA: {e}", file=sys.stderr)
            return 1
        finally:
            sesion.close()
            motor.dispose()
    print("\n" + ("Hecho." if a.aplicar else "Simulación: no se ha guardado nada."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
