"""Compara el asiento de apertura del programa anterior (PDF de asientos automáticos) con el que genera nuestro motor desde MGD.

Uso: python tools/comparar_apertura_programa_anterior.py <carpeta_mgd> <código_empresa> <nombre> <año_mgd> <pdf_programa_anterior> <id_asiento_apertura>
Ej.: ... "D:\\...\\BBDD 2021" 11 "Empresa A" 2021 "docs/Exportaciones del programa anterior/EMPRESA A Asientos automaticos año 2022.pdf" 9.1

La copia de MGD suele terminar en septiembre u octubre, así que la apertura real incluye el último trimestre: las diferencias
son esperables. Sirve sobre todo para comprobar el **mapa de cuentas** (7 → 8 dígitos) y localizar qué cambió.
"""
import re
import sys
import unicodedata
from datetime import date
from decimal import Decimal

sys.path.insert(0, __file__.rsplit("tools", 1)[0] + "tools")
from leer_diario_programa_anterior_pdf import leer  # noqa: E402
from sqlalchemy import select  # noqa: E402

from conta_pridalac.db.modelos import Cuenta, Ejercicio  # noqa: E402
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion  # noqa: E402
from conta_pridalac.migracion.mgd import cargar_mgd  # noqa: E402
from conta_pridalac.servicios.cierre import regularizar_ingresos_gastos, saldos_del_ejercicio  # noqa: E402

CERO = Decimal(0)


def main(carpeta, codigo, nombre, anio, pdf, ident):
    real = {a.id: a for a in leer(pdf)}[ident].saldos
    motor = crear_motor(None)
    crear_esquema(motor)
    s = nueva_sesion(motor)
    r = cargar_mgd(s, carpeta, codigo_empresa=int(codigo), nombre_empresa=nombre, anio=int(anio))
    ej = s.get(Ejercicio, r.ejercicio_id)
    regularizar_ingresos_gastos(s, ej, date(int(anio), 12, 31))
    previsto = saldos_del_ejercicio(s, ej)  # lo que abriría el ejercicio siguiente
    nombres = {c.codigo: c.nombre for c in s.scalars(select(Cuenta))}
    comunes = [c for c in set(real) | set(previsto) if real.get(c, CERO) == previsto.get(c, CERO)]
    print(f"{nombre}: apertura ANTERIOR {len(real)} cuentas · prevista desde MGD {len(previsto)} · idénticas {len(comunes)}")
    solo_dz = sorted(c for c in real if c not in previsto)
    solo_mgd = sorted(c for c in previsto if c not in real)
    distintas = sorted(c for c in real if c in previsto and real[c] != previsto[c])
    for titulo, lista in (("sólo en el programa anterior", solo_dz), ("sólo en MGD", solo_mgd), ("importe distinto", distintas)):
        print(f"\n  {titulo} ({len(lista)}):")
        for c in lista:
            print(f"    {c} {nombres.get(c, '')[:34]:34} ANTERIOR {real.get(c, CERO):>12} · MGD {previsto.get(c, CERO):>12}")


if __name__ == "__main__":
    main(*sys.argv[1:7])
