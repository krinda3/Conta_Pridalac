"""Listado «Facturación por cliente o proveedor»: lo facturado a cada cliente y por cada proveedor en un rango de fechas, con las facturas de cada uno al hacer doble clic."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO, Columna, Tabla
from conta_pridalac.servicios.facturacion_terceros import facturacion_por_tercero
from conta_pridalac.web.listados import Campo, Col, Contexto, Detalle, Fila, Listado

CERO = Decimal("0.00")
NOMBRES = {"E": "Cliente", "R": "Proveedor"}


def _minimo(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor).replace(",", "."))
    except InvalidOperation:
        raise ErrorContable("El importe mínimo no es un número") from None


class ListadoFacturacionTerceros(Listado):
    nombre, titulo = "facturacion-terceros", "Facturación por cliente o proveedor"
    descripcion = ("Lo facturado a cada cliente (facturas emitidas) y por cada proveedor (facturas recibidas) en un rango de fechas contables, de más a menos. «Total con IVA» es lo que cuenta para el 347. "
                   "Doble clic para ver las facturas de cada uno.")
    columnas = [
        Col("tipo", "Tipo", TEXTO, 1), Col("tercero", "Tercero", TEXTO, 4), Col("nif", "NIF", TEXTO, 1.3), Col("facturas", "Facturas", ENTERO, 0.9), Col("base", "Base", DINERO, 1.3),
        Col("iva", "IVA y recargo", DINERO, 1.3), Col("total", "Total con IVA", DINERO, 1.4), Col("neto", "Neto de las facturas", DINERO, 1.4),
    ]
    parametros = [
        Campo("sentido", "Mostrar", "select", opciones=[("", "Clientes y proveedores"), ("E", "Sólo clientes (emitidas)"), ("R", "Sólo proveedores (recibidas)")]),
        Campo("tercero", "Nombre o NIF", ayuda="parte del nombre o del NIF"), Campo("minimo", "Más de (€ con IVA)", "dinero", ayuda="3005.06 = los del 347"),
        Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha"),
    ]

    def texto_vacio(self, ctx, params):
        return "No hay facturas con esos criterios"

    def _datos(self, ctx, params):
        return facturacion_por_tercero(ctx.sesion, ctx.ejercicio, desde=params.get("desde"), hasta=params.get("hasta"), sentido=params.get("sentido") or None, texto=params.get("tercero"),
                                       minimo=_minimo(params.get("minimo")))

    def filas(self, ctx, params):
        rango = f"{params.get('desde') or ''}|{params.get('hasta') or ''}"  # el detalle de cada fila enseña el mismo rango que la pantalla
        return [Fila(f"{g.clave}|{rango}", dict(tipo=NOMBRES[g.sentido], tercero=g.nombre, nif=g.nif, facturas=len(g.facturas), base=g.base, iva=g.iva, total=g.total_con_iva, neto=g.neto)) for g in self._datos(ctx, params)]

    def totales(self, filas):
        if not filas:
            return None
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("base", "iva", "total", "neto")} | {"facturas": sum(f.valores["facturas"] for f in filas)}

    def detalle(self, ctx, id):
        clave, _, resto = id.partition("|")
        desde, _, hasta = resto.partition("|")
        try:
            rango = dict(desde=date.fromisoformat(desde) if desde else None, hasta=date.fromisoformat(hasta) if hasta else None)
        except ValueError:
            return None
        g = next((g for g in facturacion_por_tercero(ctx.sesion, ctx.ejercicio, **rango) if g.clave == clave), None)
        if g is None:
            return None
        filas = [[l.documento, l.fecha_contable, l.fecha_factura, l.numero_factura or "", l.base, l.iva, l.total_con_iva, l.neto] for l in g.facturas]
        tabla = Tabla(
            f"{NOMBRES[g.sentido]} · {g.nombre}",
            [Columna("Documento", ancho=1), Columna("Fecha contable", FECHA, 1.2), Columna("Fecha factura", FECHA, 1.2), Columna("Nº factura", ancho=1.6), Columna("Base", DINERO, 1.2),
             Columna("IVA y recargo", DINERO, 1.2), Columna("Total con IVA", DINERO, 1.3), Columna("Neto", DINERO, 1.3)],
            filas, f"Ejercicio {ctx.ejercicio.anio}{f' · del {rango['desde']:%d/%m/%Y}' if rango['desde'] else ''}{f' · hasta el {rango['hasta']:%d/%m/%Y}' if rango['hasta'] else ''} · {len(filas)} factura(s) · total con IVA {g.total_con_iva}",
        )
        pantalla = "facturas-emitidas" if g.sentido == "E" else "facturas-recibidas"
        return Detalle(f"Facturación · {g.nombre}", tabla, [("NIF", g.nif or "—"), ("Tipo", NOMBRES[g.sentido])], [], [(f"Ir a «{'Facturas emitidas' if g.sentido == 'E' else 'Facturas recibidas'}»", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/{pantalla}")])
