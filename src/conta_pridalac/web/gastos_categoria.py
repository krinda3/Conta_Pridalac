"""Listado «Gastos por categoría»: el gasto de todos los años por categorías de análisis (gas, electricidad, combustible…), con el detalle por proveedor (`servicios/categorias_gasto.py`)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from conta_pridalac.exportacion.tabla import DINERO, TEXTO, Columna, Tabla
from conta_pridalac.servicios.categorias_gasto import informe_por_categoria
from conta_pridalac.web.listados import Contexto, Col, Detalle, Fila, Listado

CERO = Decimal("0.00")
PRIMER_ANIO = 2021  # primer ejercicio llevado en el programa


class ListadoGastosCategoria(Listado):
    nombre, titulo = "gastos-categoria", "Gastos por categoría"
    descripcion = ("Gasto de todos los ejercicios por categorías de análisis (gas, electricidad, combustible, abonos, labores…). Son etiquetas por factura: no cambian ningún asiento ni ningún modelo, "
                   "y las de ejercicios cerrados se pueden ajustar sin reabrirlos. Doble clic en una categoría para ver sus proveedores año a año.")

    @property
    def columnas(self) -> list[Col]:  # una columna por año, de 2021 al año actual
        return [Col("categoria", "Categoría", TEXTO, 5)] + [Col(f"a{a}", str(a), DINERO, 1.2) for a in range(PRIMER_ANIO, date.today().year + 1)] + [Col("total", "Total", DINERO, 1.4)]

    def subtitulo(self, ctx: Contexto, params: dict) -> str:
        return f"{ctx.empresa.nombre} · todos los ejercicios · base imponible más IVA no deducible · sin los asientos que consumen existencias (ya contadas al comprar)"

    def texto_vacio(self, ctx: Contexto, params: dict) -> str:
        return "Todavía no hay categorías de gasto cargadas en esta empresa"

    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        informe = informe_por_categoria(ctx.sesion, ctx.empresa.id)
        anios = range(PRIMER_ANIO, date.today().year + 1)

        def valores(nombre, por_anio, total=None):
            v = {"categoria": nombre, "total": total if total is not None else sum(por_anio.values(), CERO) or None}
            v.update({f"a{a}": por_anio.get(a) or None for a in anios})
            return v

        filas: list[Fila] = []
        gasto = [f for f in informe.filas if f.tipo == "gasto"]
        otras = [f for f in informe.filas if f.tipo != "gasto"]
        for f in gasto:
            filas.append(Fila(f.categoria.codigo if f.categoria else "_sin", valores(f.nombre, f.por_anio)))
        if gasto:
            filas.append(Fila(None, valores("GASTO CORRIENTE", {a: informe.total_gasto(a) for a in anios}), clase="resumen total"))
        for f in otras:
            filas.append(Fila(f.categoria.codigo, valores(f.nombre, f.por_anio)))
            if f.amortizacion_teorica:
                filas.append(Fila(None, valores("      · amortización teórica a título informativo (no contabilizada)", f.amortizacion_teorica, total=CERO), clase="resumen"))
        return filas

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        informe = informe_por_categoria(ctx.sesion, ctx.empresa.id)
        fila = next((f for f in informe.filas if (f.categoria.codigo if f.categoria else "_sin") == id), None)
        if fila is None:
            return None
        anios = informe.anios
        columnas = [Columna("Proveedor / cuenta", TEXTO, 5)] + [Columna(str(a), DINERO, 1.2) for a in anios] + [Columna("Total", DINERO, 1.4)]
        datos = []
        for proveedor, por_anio in sorted(fila.proveedores.items(), key=lambda kv: -abs(sum(kv[1].values(), CERO))):
            datos.append([proveedor] + [por_anio.get(a) for a in anios] + [sum(por_anio.values(), CERO)])
        tabla = Tabla(fila.nombre, columnas, datos, totales=["Total"] + [fila.por_anio.get(a) for a in anios] + [fila.total])
        return Detalle(titulo=fila.nombre, tabla=tabla)
