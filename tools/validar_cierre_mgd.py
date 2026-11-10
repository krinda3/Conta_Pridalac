"""Valida regularización y cierre: reconstruye R y Z desde un Diario.dbf de un ejercicio ya cerrado en MGD y los compara.

Uso: python tools/validar_cierre_mgd.py <Diario.dbf> <año> [cuenta_PYG_8_dígitos]
Sólo hace falta la tabla Diario (los nombres de cuenta no se comparan). Las cuentas se convierten de 7 a 8 dígitos con
`cuenta_8` (parámetro `tras`: variable de entorno CERO_TRAS, 4 por defecto para Empresa A; Empresa B = 3).
"""
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dbfread import DBF

from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Parametro
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.migracion.cuentas import cuenta_8
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cierre import asiento_de_cierre, regularizar_ingresos_gastos

CERO = Decimal("0.00")


def main(ruta, anio, pyg="12900000"):
    tras = int(os.environ.get("CERO_TRAS", "4"))
    anio = int(anio)
    filas = list(DBF(ruta, encoding="latin-1", ignore_missing_memofile=True))
    grupos = defaultdict(lambda: {"cab": None, "lineas": []})
    for f in filas:
        if (f["CUENTA"] or "").strip() == "":
            if f["TIPO"] or f["NUMERO"]:
                grupos[(f["TIPO"], f["NUMERO"], (f["MULTI"] or "").strip())]["cab"] = f
            continue
        grupos[(f["TIPO"], f["NUMERO"], (f["MULTI"] or "").strip())]["lineas"].append(f)
    reales = {}  # subtipo → {cuenta: debe − haber} de los asientos R y Z que trae el Diario
    motor = crear_motor(None)
    crear_esquema(motor)
    s = nueva_sesion(motor)
    emp = Empresa(codigo=1, nombre="Validación")
    ej = Ejercicio(anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, 31), empresa=emp)
    s.add_all([emp, ej])
    s.flush()
    cuentas = {cuenta_8(f["CUENTA"].strip(), tras) for g in grupos.values() for f in g["lineas"]} | {pyg}
    for c in sorted(cuentas):
        s.add(Cuenta(empresa_id=emp.id, codigo=c, nombre=c))
    s.add(Parametro(empresa_id=emp.id, clave="PYG", valor=pyg))
    s.flush()
    n = 0
    for (tipo, numero, multi), g in grupos.items():
        if not g["lineas"]:
            continue
        cab = g["cab"] or g["lineas"][0]
        sub = (cab["TPASIENTO"] or "").strip()
        importes = defaultdict(CERO.__class__)
        for l in g["lineas"]:
            importes[cuenta_8(l["CUENTA"].strip(), tras)] += Decimal(str(l["IMPORTE"]))
        if sub in ("R", "Z"):
            reales[sub] = {c: i for c, i in importes.items() if i != 0}
            continue
        n += 1
        grabar_asiento(s, ej, tipo=4, numero=n, fecha=cab["FECHA"],
                       lineas=[LineaAsiento(c, i) for c, i in importes.items()], subtipo=sub or None)
    regularizar_ingresos_gastos(s, ej)
    from conta_pridalac.servicios.cierre import saldos_del_ejercicio  # noqa: E402
    mios = {"R": None, "Z": None}
    for a in s.query(Asiento).filter(Asiento.subtipo.in_(("R", "Z"))):
        mios[a.subtipo] = {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}
    asiento_de_cierre(s, ej)
    for a in s.query(Asiento).filter(Asiento.subtipo == "Z"):
        mios["Z"] = {ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes}
    return reales, mios


def informar(reales, mios):
    for sub in ("R", "Z"):
        r, m = reales.get(sub, {}), mios.get(sub) or {}
        dif = {c: (r.get(c, CERO), m.get(c, CERO)) for c in set(r) | set(m) if r.get(c, CERO) != m.get(c, CERO)}
        print(f"{sub}: MGD {len(r)} lineas / motor {len(m)} lineas / diferencias {len(dif)}")
        for c, (a, b) in sorted(dif.items()):
            print(f"   {c}: MGD {a:>12} / motor {b:>12}")


if __name__ == "__main__":
    informar(*main(*sys.argv[1:4]))
