r"""Registra como presentada una declaración 303 o 111 de la que sólo se tiene el PDF de la sede.

    python tools/importar_declaracion_pdf.py --nombre empresa_a --modelo 303 --anio 2025 --periodo 4 --pdf "ruta\C0002_303_2025_04.PDF"
    python tools/importar_declaracion_pdf.py --nombre empresa_a --modelo 303 --anio 2025 --periodo 4 --tipo 2 --pdf "ruta\C0002_C303_2025_04.PDF"
    python tools/importar_declaracion_pdf.py --nombre empresa_b --modelo 111 --anio 2022 --periodo 1 --pdf "ruta\...1T 2022.pdf" --sin-lectura

Del PDF se leen justificante, fecha y presentador; no se leen los importes (queda sin casillas). `--sin-lectura` es para un PDF cuyo texto no se puede leer: se enlaza el PDF y queda constancia
de que se presentó, sin justificante. No repite lo que ya consta. Con el programa cerrado y una copia de seguridad hecha.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.migracion.declaraciones_pdf import importar_declaracion_desde_pdf
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos
from conta_pridalac.servicios.justificante_aeat import leer_justificante

RAIZ = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--modelo", required=True, choices=("303", "111"))
    ap.add_argument("--anio", required=True, type=int)
    ap.add_argument("--periodo", required=True, type=int, choices=(1, 2, 3, 4))
    ap.add_argument("--tipo", type=int, default=1, help="1 la presentada; 2 una complementaria (por defecto 1)")
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--sin-lectura", action="store_true", help="el PDF no se puede leer: se enlaza sin justificante ni fecha")
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos_locales" / "bd")
    ap.add_argument("--almacen", type=Path, default=RAIZ / "datos_locales" / "justificantes")
    a = ap.parse_args(argv)
    if not a.pdf.is_file():
        print(f"No existe el PDF: {a.pdf}")
        return 1
    if not a.sin_lectura and leer_justificante(a.pdf.read_bytes()) is None:
        print("El PDF no se puede leer como justificante de la sede. Si es una copia sin los valores, use --sin-lectura.")
        return 1
    motor = crear_motor(a.datos / f"{a.nombre}.sqlite")
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    empresa = sesion.scalars(select(Empresa)).first()
    try:
        d = importar_declaracion_desde_pdf(sesion, AlmacenAdjuntos(a.almacen), empresa, a.modelo, a.anio, a.periodo, a.pdf, tipo=a.tipo)
    except ErrorContable as e:
        sesion.rollback()
        print(f"No se importa: {e}")
        return 1
    sesion.commit()
    print(f"Añadido: modelo {d.modelo} {d.periodo}T {d.anio} (tipo {d.tipo}) · justificante {d.justificante or 'sin justificante'} · fecha {d.fecha_emision or '—'} · PDF {d.pdf_nombre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
