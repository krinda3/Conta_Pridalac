"""Carga en la base las categorías de análisis del gasto y clasifica las facturas recibidas según un fichero de reglas. No cambia ningún asiento, importe, IVA ni fecha: comprueba que los saldos de
todas las cuentas quedan idénticos y, si no, no guarda nada.

    python tools/cargar_categorias_gasto.py --bd ruta/empresa_b.sqlite --reglas datos_locales/categorias_gasto_empresa_b.json            (simula sobre una copia)
    python tools/cargar_categorias_gasto.py --bd ruta/empresa_b.sqlite --reglas ... --aplicar --en-la-base-real --copia-hecha            (lo hace)

El fichero de reglas es el de `docs/12_categorias_de_gasto.md` (categorías, cuentas que mandan, reglas por proveedor, cuenta por defecto y excepciones por factura).
Las facturas que ya tienen categoría se respetan, salvo con `--sobrescribir`. Se niega a trabajar sobre la carpeta de datos de la aplicación salvo con `--en-la-base-real`;
con `--aplicar` exige además `--copia-hecha` (confirmar que ya se hizo una copia de seguridad).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.servicios import categorias_gasto as cg
from conta_pridalac.web.config import Configuracion


def saldos(sesion, empresa_id: int) -> dict[str, Decimal]:
    return {c: (d or 0) - (h or 0) for c, d, h in sesion.execute(
        select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber)).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Cuenta.empresa_id == empresa_id).group_by(Cuenta.codigo))}


def tabla(informe: cg.InformeCategorias) -> str:
    def eur(v):
        return f"{v:,.0f}".replace(",", ".") if abs(v) >= Decimal("0.5") else "·"
    lineas = [f"{'Categoría':<58}" + "".join(f"{a:>9}" for a in informe.anios) + f"{'Total':>10}"]
    for f in informe.filas:
        lineas.append(f"{f.nombre[:56]:<58}" + "".join(f"{eur(f.por_anio.get(a, Decimal('0'))):>9}" for a in informe.anios) + f"{eur(f.total):>10}")
        if f.amortizacion_teorica:
            lineas.append(f"{'   · amortización teórica (informativa)':<58}" + "".join(f"{eur(f.amortizacion_teorica.get(a, Decimal('0'))):>9}" for a in informe.anios))
    lineas.append(f"{'GASTO CORRIENTE (sin inversión, amortización, impuestos…)':<58}" + "".join(f"{eur(informe.total_gasto(a)):>9}" for a in informe.anios))
    return "\n".join(lineas)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--reglas", required=True)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--en-la-base-real", action="store_true")
    ap.add_argument("--copia-hecha", action="store_true", help="confirma que ya se hizo una copia de seguridad (obligatorio con --aplicar)")
    ap.add_argument("--sobrescribir", action="store_true")
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
            antes = saldos(sesion, empresa.id)
            print("\n".join(cg.importar_catalogo(sesion, empresa.id, reglas)))
            res = cg.clasificar_facturas(sesion, empresa.id, reglas, sobrescribir=a.sobrescribir)
            sesion.flush()
            if saldos(sesion, empresa.id) != antes:
                raise RuntimeError("Cambian los saldos de las cuentas: no debería. No se guarda nada.")
            print(f"\nFacturas recibidas: {res.facturas} · categoría fijada: {res.asignadas} · ya la tenían: {res.iguales} · sale sola de la cuenta: {res.por_cuenta}")
            for s in res.sin_categoria:
                print("  SIN CATEGORÍA:", s)
            print("\n" + tabla(cg.informe_por_categoria(sesion, empresa.id)))
            if res.sin_categoria:
                raise RuntimeError("Hay facturas con una categoría que no existe en el catálogo.")
            sesion.commit()
        except (RuntimeError, KeyError) as e:
            sesion.rollback()
            print(f"\nNO SE HA CAMBIADO NADA: {e}", file=sys.stderr)
            return 1
        finally:
            sesion.close()
            motor.dispose()
    print("\nSaldos de todas las cuentas sin cambios." + (" Hecho." if a.aplicar else " Simulación: no se ha guardado nada."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
