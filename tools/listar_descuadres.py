"""Lista (Excel) de los asientos descuadrados de una empresa, con la factura y el comprobante para revisarlos a mano.

    python tools/listar_descuadres.py --nombre empresa_b

Lee `datos_locales/bd/<nombre>.sqlite` (sin modificarla) y escribe `datos_locales/salida/descuadres_<nombre>.xlsx`.
La columna «Ajuste propuesto» es sólo una sugerencia: hay que mirar el comprobante para saber qué concepto falta o sobra.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select

from conta_pridalac.db.modelos import Adjunto, Apunte, Asiento, Ejercicio, Factura
from conta_pridalac.db.sesion import crear_motor, nueva_sesion

RAIZ = Path(__file__).resolve().parents[1]
COLUMNAS = [
    ("Asiento", 12), ("Fecha", 12), ("Nº factura", 22), ("Proveedor / cliente", 34), ("NIF", 12), ("Total factura", 14), ("Base + IVA", 14),
    ("Debe", 12), ("Haber", 12), ("Diferencia", 12), ("Cuenta de gasto/ingreso", 14), ("Ajuste propuesto", 58), ("Comprobante", 40), ("Decisión", 24),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--destino", type=Path, default=RAIZ / "datos_locales" / "bd")
    a = ap.parse_args(argv)

    motor = crear_motor(a.destino / f"{a.nombre}.sqlite")
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Descuadres"
    for c, (titulo, ancho) in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(1, c, titulo)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="305496")
        celda.alignment = Alignment(wrap_text=True)
        hoja.column_dimensions[get_column_letter(c)].width = ancho
    fila = 1
    with nueva_sesion(motor) as sesion:
        consulta = (
            select(Asiento, func.sum(Apunte.debe), func.sum(Apunte.haber))
            .join(Apunte, Apunte.asiento_id == Asiento.id)
            .group_by(Asiento.id)
            .order_by(Asiento.ejercicio_id, Asiento.tipo, Asiento.numero)
        )
        for asiento, debe, haber in sesion.execute(consulta):
            if debe == haber:
                continue
            ejercicio = sesion.get(Ejercicio, asiento.ejercicio_id)
            factura = sesion.scalars(
                select(Factura).where(Factura.ejercicio_id == asiento.ejercicio_id, Factura.numero == asiento.numero, Factura.sentido == {1: "E", 2: "R"}.get(asiento.tipo, "-"))
            ).first()
            diferencia = debe - haber
            fila += 1
            total = factura.total if factura else None
            base_iva = sum((i.base + i.cuota_iva + i.cuota_recargo for i in factura.ivas), Decimal("0.00")) if factura else None
            cuenta = factura.cuenta_contrapartida.codigo if factura and factura.cuenta_contrapartida else ""
            comprobante = ""
            if factura:
                adj = sesion.scalars(select(Adjunto).where(Adjunto.factura_id == factura.id)).first()
                comprobante = adj.nombre if adj else "(sin comprobante)"
            if diferencia < 0:
                ajuste = f"Falta apuntar {-diferencia} € al debe (parte de la factura sin base ni IVA: suplido, tasa o redondeo) en {cuenta or 'la cuenta de gasto'}"
            else:
                ajuste = f"Sobran {diferencia} € en el debe, o falta apuntar {diferencia} € al haber; el total de la factura es menor que base + IVA"
            valores = [
                f"{ejercicio.anio}/{asiento.identificador}", asiento.fecha, factura.numero_factura if factura else asiento.concepto,
                factura.tercero.nombre if factura and factura.tercero else "", factura.tercero.nif if factura and factura.tercero else "",
                total, base_iva, debe, haber, diferencia, cuenta, ajuste, comprobante, "",
            ]
            for c, v in enumerate(valores, start=1):
                celda = hoja.cell(fila, c, float(v) if isinstance(v, Decimal) else v)
                if isinstance(v, Decimal):
                    celda.number_format = "#,##0.00"
                if c == 2:
                    celda.number_format = "DD/MM/YYYY"
    hoja.freeze_panes = "A2"
    salida = RAIZ / "datos_locales" / "salida" / f"descuadres_{a.nombre}.xlsx"
    salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(salida)
    print(f"{fila - 1} asientos descuadrados -> {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
