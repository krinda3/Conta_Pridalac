"""Pasa a «Movimientos de banco», como cobro o pago de una operación, la parte del banco de los asientos manuales: es lo que la auditoría señala como «el saldo del banco no cuadra» (`saldo_de_banco`).

    python tools/pasar_asientos_a_movimientos.py --bd ruta/empresa_b.sqlite --banco "LA CAIXA CTA 000001" --anio 2026                      (simula)
    python tools/pasar_asientos_a_movimientos.py --bd ruta/empresa_b.sqlite --banco "LA CAIXA CTA 000001" --anio 2026 --asientos 4.1 4.2    (sólo esos dos, simulando)
    python tools/pasar_asientos_a_movimientos.py --bd ruta/empresa_b.sqlite --banco "LA CAIXA CTA 000001" --anio 2026 --aplicar --en-la-base-real

Un movimiento de banco no se inventa: tiene que ser el cobro o el pago de algo que la contabilidad ya recoge. La herramienta sólo pasa los asientos que contienen esa operación (la concesión de una
subvención y su cobro, una corrección y su devolución): anota en la operación un vencimiento y el movimiento de banco lo salda, como el cobro de una factura. Los demás se dejan y se dice por qué. Los saldos
de todas las cuentas quedan igual; si alguno cambiase, no se guarda nada. Sin `--aplicar` se trabaja sobre una copia y no se guarda nada. Con `--aplicar` se hace antes una copia de la base junto a ella
(`…antes_de_pasar_asientos_<fecha>`): cierre antes la aplicación, y para la base de la aplicación hace falta `--en-la-base-real`.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.auditoria import auditar
from conta_pridalac.db.integridad import asientos_descuadrados
from conta_pridalac.db.modelos import Apunte, Asiento, Banco, Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.pasar_asientos import asientos_a_pasar, pasar_todos
from conta_pridalac.web.config import Configuracion


def saldos(sesion, ejercicio_id: int) -> dict[str, Decimal]:
    filas = sesion.execute(select(Cuenta.codigo, Apunte.debe, Apunte.haber).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id).where(Asiento.ejercicio_id == ejercicio_id)).all()
    resultado: dict[str, Decimal] = {}
    for codigo, debe, haber in filas:  # se suma en Python: restar en SQL pierde el tipo de importe
        resultado[codigo] = resultado.get(codigo, Decimal(0)) + debe - haber
    return resultado


def _euros(valor: Decimal) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--banco", required=True, help="nombre del banco (como sale en Bancos) o su número")
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--asientos", nargs="*", help="sólo estos asientos, por su identificador (4.1 4.2); sin esto, todos los que se puedan decidir")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--en-la-base-real", action="store_true")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name
        if a.aplicar:
            copia = bd.with_name(f"{bd.name}.antes_de_pasar_asientos_{datetime.now():%Y%m%d_%H%M%S}")
            shutil.copyfile(bd, copia)
            print(f"Copia de seguridad de la base: {copia}")
        else:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        try:
            empresa = sesion.scalars(select(Empresa)).one()
            ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id, Ejercicio.anio == a.anio)).one_or_none()
            if ejercicio is None:
                raise ErrorContable(f"No existe el ejercicio {a.anio}")
            bancos = [b for b in sesion.scalars(select(Banco).where(Banco.empresa_id == empresa.id)) if str(b.numero) == a.banco or b.nombre.strip().upper() == a.banco.strip().upper()]
            if len(bancos) != 1:
                raise ErrorContable(f"Banco «{a.banco}»: hay {len(bancos)} y tiene que haber uno")
            banco = bancos[0]
            if banco.cuenta_id is None:
                raise ErrorContable(f"El banco «{banco.nombre}» no tiene cuenta contable")
            pendientes = asientos_a_pasar(sesion, ejercicio, banco)
            print(f"Banco «{banco.nombre}» ({banco.cuenta.codigo}) · ejercicio {a.anio}: {len(pendientes)} asiento(s) manual(es) mueven el banco sin ser movimientos")
            antes = saldos(sesion, ejercicio.id)
            erroneos_antes = [h for h in auditar(sesion, ejercicio) if h.codigo == "saldo_de_banco"]
            conversiones = pasar_todos(sesion, ejercicio, banco, set(a.asientos) if a.asientos else None)
            sesion.flush()
            descuadrados = asientos_descuadrados(sesion, ejercicio.id)
            if descuadrados:
                raise ErrorContable(f"Quedarían asientos descuadrados: {descuadrados[:5]}")
            despues = saldos(sesion, ejercicio.id)
            cambian = {c: despues.get(c, 0) - antes.get(c, 0) for c in set(antes) | set(despues) if despues.get(c, 0) != antes.get(c, 0)}
            if cambian:
                raise ErrorContable(f"El saldo de alguna cuenta cambiaría: {dict(sorted(cambian.items()))}")
            erroneos_despues = [h for h in auditar(sesion, ejercicio) if h.codigo == "saldo_de_banco"]
            sesion.commit()
        except (ErrorContable, KeyError) as e:
            sesion.rollback()
            print(f"\nNO SE HA CAMBIADO NADA: {e}", file=sys.stderr)
            return 1
        finally:
            sesion.close()
            motor.dispose()
    for c in conversiones:
        if c.problema:
            print(f"\n  {c.asiento} ({c.fecha:%d/%m/%Y}) «{c.concepto}»: SIN TOCAR, {c.problema}")
            continue
        print(f"\n  {c.asiento} ({c.fecha:%d/%m/%Y}) «{c.concepto}»")
        print(f"      el {'cobro' if c.importe > 0 else 'pago'} de {_euros(abs(c.importe))} € en {banco.nombre} salda un vencimiento de la operación en {c.contrapartida}" + (f" → movimiento nº {c.movimiento}" if c.movimiento else ""))
        print("      el asiento manual se queda con: " + (", ".join(f"{cuenta} {'debe' if i > 0 else 'haber'} {_euros(abs(i))}" for cuenta, i in c.resto) or "nada: se borra"))
    print(f"\nSaldos de todas las cuentas: sin cambios. Avisos «saldo del banco no cuadra»: antes {len(erroneos_antes)} → después {len(erroneos_despues)}.")
    print("Hecho." if a.aplicar else "Simulación: no se ha guardado nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
