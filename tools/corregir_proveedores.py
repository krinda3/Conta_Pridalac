"""Corrige proveedores y cuentas de gasto de facturas recibidas ya contabilizadas, desde un fichero JSON. No cambia importes, IVA ni fechas, así que no altera ningún modelo presentado.

    python tools/corregir_proveedores.py --bd ruta/empresa_b.sqlite --correcciones datos_locales/correcciones_proveedores_empresa_b.json            (simula)
    python tools/corregir_proveedores.py --bd ruta/empresa_b.sqlite --correcciones datos_locales/correcciones_proveedores_empresa_b.json --aplicar   (lo hace)

El JSON es una lista de operaciones; las facturas de un ejercicio cerrado nunca se tocan (se cuentan y se listan):
- `{"op": "renombrar", "nif": "E81458556", "nombre": "REG. MERCANTILES DE MADRID CB"}`: cambia el nombre del proveedor y el de su subcuenta.
- `{"op": "crear_cuenta", "codigo": "62900003", "nombre": "GASTOS DE VIAJE COMBUSTIBLE"}`: da de alta la subcuenta si no existe.
- `{"op": "crear", "nombre": "COLEGIO DE REGISTRADORES DE ESPAÑA", "nif": "Q2863012G", "gasto": "62300000"}`: da de alta el proveedor si no existe (por NIF).
- `{"op": "gasto_ficha", "tercero": {"nif": "E81458556"}, "gasto": "62300000", "desde": "2026-01-01"}`: pone esa subcuenta de gasto en la ficha y en sus facturas desde esa fecha.
- `{"op": "mover", "de": {"nif": "A86488087"}, "a": {"nif": "A08431090"}, "facturas": [{"numero": "FE26390001801100", "gasto": "62800002"}]}`: pasa facturas de un proveedor a otro y les pone su gasto.
Un tercero se indica por `nif` (sin espacios ni guiones) o por `nombre`. Sin `--aplicar` se trabaja sobre una copia y no se guarda nada. Se niega a trabajar sobre la carpeta de datos de la
aplicación salvo con `--en-la-base-real`.
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
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Factura, Tercero
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import cuentas as svc_cuentas
from conta_pridalac.servicios.correcciones import cambiar_proveedor_y_gasto
from conta_pridalac.servicios.importar_facturas import _grupo_de_terceros, normalizar_nif
from conta_pridalac.web.config import Configuracion


def _tercero(sesion, empresa_id: int, ref: dict) -> Tercero:
    consulta = select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.clase == "P")
    encontrados = [t for t in sesion.scalars(consulta) if (ref.get("nif") and normalizar_nif(t.nif) == normalizar_nif(ref["nif"])) or
                   (not ref.get("nif") and ref.get("nombre") and t.nombre.strip().upper() == ref["nombre"].strip().upper())]
    if len(encontrados) != 1:
        raise ErrorContable(f"Proveedor {ref}: hay {len(encontrados)} fichas y tiene que haber una")
    return encontrados[0]


def _cuenta(sesion, empresa_id: int, codigo: str) -> Cuenta:
    c = sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo)).first()
    if c is None:
        raise ErrorContable(f"La subcuenta {codigo} no existe en el plan de cuentas")
    return c


def _facturas(sesion, tercero: Tercero, desde: date | None = None, numero: str | None = None):
    consulta = select(Factura, Ejercicio).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(Factura.sentido == "R", Factura.tercero_id == tercero.id).order_by(Factura.fecha_contable, Factura.numero)
    if desde:
        consulta = consulta.where(Factura.fecha_contable >= desde)
    return [(f, e) for f, e in sesion.execute(consulta) if numero is None or (f.numero_factura or "").strip().upper() == numero.strip().upper()]


def operar(sesion, empresa_id: int, op: dict, informe: list[str]) -> None:
    tipo = op["op"]
    if tipo == "renombrar":
        t = _tercero(sesion, empresa_id, {"nif": op["nif"]})
        if t.nombre != op["nombre"]:
            informe.append(f"Renombrar «{t.nombre}» → «{op['nombre']}» ({t.nif})")
            t.nombre = op["nombre"]
            if t.cuenta_id:
                sesion.get(Cuenta, t.cuenta_id).nombre = op["nombre"].upper()
    elif tipo == "crear_cuenta":
        if sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == op["codigo"])).first():
            informe.append(f"Ya existe la subcuenta {op['codigo']}: no se crea")
        else:
            informe.append(f"Crear la subcuenta {svc_cuentas.crear_cuenta(sesion, empresa_id, op['codigo'], op['nombre']).codigo} {op['nombre']}")
    elif tipo == "crear":
        existentes = [t for t in sesion.scalars(select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.clase == "P")) if normalizar_nif(t.nif) == normalizar_nif(op["nif"])]
        if existentes:
            informe.append(f"Ya existe «{existentes[0].nombre}» ({op['nif']}): no se crea")
        else:
            t = svc_cuentas.crear_tercero(sesion, empresa_id, "P", op["nombre"], nif=normalizar_nif(op["nif"]), grupo_cuenta=_grupo_de_terceros(sesion, empresa_id, "P"), cuenta_gasto=op["gasto"])
            informe.append(f"Crear «{t.nombre}» ({t.nif}), subcuenta {sesion.get(Cuenta, t.cuenta_id).codigo}, gasto {op['gasto']}")
    elif tipo == "gasto_ficha":
        t, gasto = _tercero(sesion, empresa_id, op["tercero"]), _cuenta(sesion, empresa_id, op["gasto"])
        if t.cuenta_gasto_id != gasto.id:
            informe.append(f"Ficha «{t.nombre}»: gasto por defecto → {gasto.codigo}")
            t.cuenta_gasto_id = gasto.id
        hechas = cerradas = 0
        for f, e in _facturas(sesion, t, date.fromisoformat(op["desde"]) if op.get("desde") else None):
            try:
                hechas += cambiar_proveedor_y_gasto(sesion, e, f, gasto=gasto)
            except ErrorContable:
                cerradas += 1
        informe.append(f"   facturas de «{t.nombre}» pasadas a {gasto.codigo}: {hechas}" + (f" · sin tocar por ejercicio cerrado: {cerradas}" if cerradas else ""))
    elif tipo == "mover":
        de, a = _tercero(sesion, empresa_id, op["de"]), _tercero(sesion, empresa_id, op["a"])
        for item in op["facturas"]:
            gasto = _cuenta(sesion, empresa_id, item["gasto"]) if item.get("gasto") else None
            for f, e in _facturas(sesion, de, numero=item["numero"]) or [(None, None)]:
                if f is None:
                    informe.append(f"   NO ESTÁ la factura {item['numero']} en «{de.nombre}»")
                    continue
                try:
                    cambio = cambiar_proveedor_y_gasto(sesion, e, f, tercero=a, gasto=gasto)
                    informe.append(f"   {f.fecha_contable} {f.numero_factura} {f.total} € «{de.nombre}» → «{a.nombre}»" + (f", gasto {gasto.codigo}" if gasto else "") + ("" if cambio else " (ya estaba)"))
                except ErrorContable as ex:
                    informe.append(f"   SIN TOCAR {f.fecha_contable} {f.numero_factura}: {ex}")
    else:
        raise ErrorContable(f"Operación desconocida: {tipo}")


def saldos(sesion, empresa_id: int) -> dict[str, Decimal]:
    return {c: (d or 0) - (h or 0) for c, d, h in sesion.execute(
        select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber)).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Cuenta.empresa_id == empresa_id).group_by(Cuenta.codigo))}


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bd", required=True)
    ap.add_argument("--correcciones", required=True)
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--en-la-base-real", action="store_true")
    a = ap.parse_args(argv)
    bd = Path(a.bd).resolve()
    if bd.parent == Configuracion().datos.resolve() and not a.en_la_base_real:
        print(f"{bd} está en la carpeta de datos de la aplicación. Trabaje sobre una copia fuera de ella (o use --en-la-base-real).", file=sys.stderr)
        return 2
    operaciones = json.loads(Path(a.correcciones).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as t:
        trabajo = bd if a.aplicar else Path(t) / bd.name
        if not a.aplicar:
            shutil.copyfile(bd, trabajo)
        motor = crear_motor(trabajo)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        informe: list[str] = []
        try:
            empresa = sesion.scalars(select(Empresa)).one()
            antes = saldos(sesion, empresa.id)
            for op in operaciones:
                informe.append(f"# {op['op']}" + (f" · {op['motivo']}" if op.get("motivo") else ""))
                operar(sesion, empresa.id, op, informe)
            sesion.flush()
            descuadrados = [x for e in sesion.scalars(select(Ejercicio)) for x in asientos_descuadrados(sesion, e.id)]
            if descuadrados:
                raise ErrorContable(f"Quedarían asientos descuadrados: {descuadrados[:5]}")
            despues = saldos(sesion, empresa.id)
            sesion.commit()
        except (ErrorContable, KeyError) as e:
            sesion.rollback()
            print("\n".join(informe))
            print(f"\nNO SE HA CAMBIADO NADA: {e}", file=sys.stderr)
            return 1
        finally:
            sesion.close()
            motor.dispose()
    print("\n".join(informe))
    cambios = {c: despues.get(c, 0) - antes.get(c, 0) for c in sorted(set(antes) | set(despues)) if despues.get(c, 0) != antes.get(c, 0)}
    print("\nCuentas cuyo saldo cambia (debe − haber):")
    for c, d in cambios.items():
        print(f"   {c}  {d:>12,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    iva = {c: d for c, d in cambios.items() if c.startswith("472") or c.startswith("477")}
    print("IVA (472/477) sin cambios." if not iva else f"¡OJO! Cambia el IVA: {iva}")
    print(("Hecho." if a.aplicar else "Simulación: no se ha guardado nada."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
