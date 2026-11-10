"""Crea una empresa nueva desde una copia de seguridad de Gestión MGD (el .zip o la carpeta con sus .dbf).

    python tools/importar_mgd.py "C:\\copias\\mi empresa 2021.zip" --nombre "Mi Empresa S.L."
    python tools/importar_mgd.py "C:\\copias\\mi empresa 2021.zip" --nombre "Mi Empresa S.L." --nif B12345678 --slug mi-empresa

Sin más opciones sólo MIRA la copia y dice qué haría; para crear la empresa hay que añadir `--aplicar`.
Los dígitos de las subcuentas son los del plan de cuentas de la copia (no se inventan cuentas); `--digitos` fuerza otros.
La empresa queda en `datos_locales/bd/<slug>.sqlite` (o en `CONTA_DATOS`) y sus justificantes en `datos_locales/justificantes`.
Nunca sustituye una empresa que ya exista: si el nombre interno (`--slug`) está cogido, se para.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.alta_empresa import abrir_copia, crear_desde_mgd, examinar_copia, slug_de
from conta_pridalac.web.config import Configuracion


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("copia", help="el .zip de la copia de MGD o la carpeta con sus .dbf")
    ap.add_argument("--nombre", help="razón social (por defecto, la que traiga la copia)")
    ap.add_argument("--nif", help="NIF o CIF de la empresa")
    ap.add_argument("--slug", help="nombre interno: el del fichero y el de la dirección web (por defecto, sale del nombre)")
    ap.add_argument("--anio", type=int, help="año del ejercicio (por defecto, el de los apuntes)")
    ap.add_argument("--codigo", type=int, help="número de empresa de MGD (por defecto, el de sus justificantes)")
    ap.add_argument("--plan", choices=["pymes", "esfl"], default="pymes", help="plan de cuentas: pymes (empresas) o esfl (entidad sin fines lucrativos: ONG, fundación, asociación)")
    ap.add_argument("--digitos", type=int, help="dígitos de las subcuentas (por defecto, los del plan de la copia)")
    ap.add_argument("--aplicar", action="store_true", help="crea la empresa; sin esto sólo se muestra lo que se haría")
    a = ap.parse_args(argv)

    config = Configuracion()
    origen = Path(a.copia)
    if not origen.exists():
        print(f"No encuentro «{a.copia}» en la carpeta {Path.cwd()}. Escriba la ruta completa del .zip (en el Explorador, selecciónelo y pulse Ctrl+Mayús+C para copiarla).", file=sys.stderr)
        return 1
    try:
        with abrir_copia(origen) as carpeta:
            copia = examinar_copia(carpeta)
            nombre = (a.nombre or copia.nombre or "").strip()
            if not nombre:
                raise ErrorContable("La copia no trae el nombre de la empresa: indíquelo con --nombre")
            anio = a.anio or copia.anio
            if anio is None:
                raise ErrorContable("No se puede saber el año de la copia: indíquelo con --anio")
            digitos = a.digitos or copia.digitos_cuenta
            destino = config.datos / f"{slug_de(a.slug or nombre)}.sqlite"
            print(f"Copia de MGD: {copia.asientos} asientos, {copia.justificantes} justificantes, año {copia.anio}, empresa nº {copia.codigo_empresa}, subcuentas de {copia.digitos_cuenta} dígitos")
            print(f"Empresa que se crearía: «{nombre}»{' · ' + a.nif if a.nif else ''} · ejercicio {anio} · subcuentas de {digitos} dígitos · plan {a.plan} · fichero {destino}")
            if destino.exists():
                raise ErrorContable(f"Ya existe una empresa «{destino.stem}»: elija otro --slug (esta herramienta nunca sustituye una empresa)")
            if not a.aplicar:
                print("No se ha creado nada. Para crearla, repita la orden añadiendo --aplicar")
                return 0
            r = crear_desde_mgd(config, carpeta, nombre=nombre, nif=a.nif, anio=anio, codigo=a.codigo or copia.codigo_empresa or 1, digitos=digitos, tipo_plan=a.plan, slug=a.slug)
    except ErrorContable as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Creada «{nombre}»: {r.cuentas} cuentas, {r.asientos} asientos, {r.justificantes} justificantes ({r.copiados} copiados)")
    for aviso in r.avisos[:10]:
        print("  aviso:", aviso)
    if len(r.avisos) > 10:
        print(f"  y {len(r.avisos) - 10} avisos más")
    print(f"Ya puede abrirla desde la pantalla de inicio de Conta Pridalac: «{nombre}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
