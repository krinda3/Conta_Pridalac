"""Declaraciones presentadas a la AEAT (hoy el modelo 303, importado del programa anterior): sólo lectura.

Sirven para dejar las liquidaciones de IVA ya presentadas como definitivas y para comparar lo que calculemos con lo que se presentó.
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO, Columna, Tabla
from conta_pridalac.ficheros_aeat import fichero111
from conta_pridalac.servicios import iva as svc_iva
from conta_pridalac.web.listados import Col, Contexto, Detalle, Fila, Listado

CERO = Decimal("0.00")
# casillas más habituales del 303 (las demás se enseñan con su número)
CASILLAS = {
    "27": "Total cuota devengada", "29": "Cuotas soportadas en operaciones interiores corrientes", "45": "Total a deducir", "46": "Resultado del régimen general",
    "64": "Suma de resultados", "66": "Atribuible a la Administración del Estado", "69": "Resultado", "71": "Resultado de la liquidación",
    "87": "Cuotas a compensar pendientes para periodos siguientes",
}


def _estado(ctx: Contexto, d: DeclaracionPresentada) -> str:
    if d.asiento is None:
        return "Sin asiento de liquidación"
    return "Coincide con el asiento" if svc_iva.coincide_con_lo_presentado(d.asiento, d) else "Distinta del asiento"


class ListadoDeclaraciones(Listado):
    modelo = "303"
    nombre, titulo = "declaraciones", "Declaraciones presentadas"
    descripcion = "Modelo 303 de cada periodo, tal como se presentó, con las facturas de cada casilla. Sólo lectura."
    columnas = [
        Col("modelo", "Modelo", TEXTO, 0.8), Col("periodo", "Periodo", TEXTO, 0.9), Col("tipo", "Tipo", TEXTO, 1.1), Col("emision", "Emitida", FECHA, 1.1), Col("justificante", "Justificante", TEXTO, 1.8),
        Col("liquidacion", "Resultado", DINERO, 1.3), Col("resultado", "Tras compensar", DINERO, 1.3), Col("compensar", "A compensar", DINERO, 1.3), Col("asiento", "Asiento", TEXTO, 0.9), Col("estado", "Estado", TEXTO, 2),
    ]

    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        consulta = select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ctx.empresa.id, DeclaracionPresentada.modelo == self.modelo, DeclaracionPresentada.anio == ctx.ejercicio.anio).order_by(
            DeclaracionPresentada.periodo, DeclaracionPresentada.tipo
        )
        filas = []
        for d in ctx.sesion.scalars(consulta):
            estado = _estado(ctx, d)
            filas.append(Fila(str(d.id), dict(
                modelo=d.modelo, periodo=f"{d.periodo}T", tipo="Presentada" if d.tipo == 1 else f"Tipo {d.tipo}", emision=d.fecha_emision, justificante=d.justificante,
                liquidacion=d.resultado_liquidacion, resultado=d.resultado, compensar=d.a_compensar or None, asiento=d.asiento.identificador if d.asiento else None, estado=estado,
            ), clase="aviso-fila" if estado == "Distinta del asiento" else ""))
        return filas

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        d = ctx.sesion.get(DeclaracionPresentada, int(id))
        if d is None or d.empresa_id != ctx.empresa.id:
            return None
        casillas = json.loads(d.casillas or "{}")
        filas = [[f"Casilla {c}", CASILLAS.get(c, ""), Decimal(str(v))] for c, v in sorted(casillas.items(), key=lambda x: int(x[0]))]
        tabla = Tabla(
            f"Modelo {d.modelo} · {d.periodo}T {d.anio}", [Columna("Casilla", ancho=1.2), Columna("Concepto", ancho=4), Columna("Importe", DINERO, 1.3)], filas,
            f"{'Emitida el ' + format(d.fecha_emision, '%d/%m/%Y') if d.fecha_emision else 'Sin fecha de emisión'}{' · justificante ' + d.justificante if d.justificante else ''}",
        )
        extras = []
        if d.lineas:
            lineas = [[l.numero_factura or "", l.fecha_factura, l.fecha_fiscal, l.casilla or "", l.base, l.porcentaje, l.cuota] for l in d.lineas]
            extras.append(Tabla(
                "Facturas incluidas", [Columna("Nº factura", ancho=2), Columna("Fecha factura", FECHA, 1.2), Columna("Fecha fiscal", FECHA, 1.2), Columna("Casilla", ancho=0.8), Columna("Base", DINERO, 1.2), Columna("%", DINERO, 0.7), Columna("Cuota", DINERO, 1.2)], lineas,
            ))
        enlaces = [("Ir a «Liquidación del IVA»", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/liquidacion-iva")]
        if d.pdf_ruta:
            enlaces.insert(0, ("Ver el PDF presentado", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/declaraciones/{d.id}/pdf"))
        datos = [("Estado", _estado(ctx, d)), ("PDF presentado", d.pdf_nombre or "no disponible")]
        return Detalle(f"Declaración presentada · modelo {d.modelo} · {d.periodo}T {d.anio}", tabla, datos, extras, enlaces)


class ListadoDeclaraciones111(ListadoDeclaraciones):
    """Las del modelo 111 (importadas del programa anterior): no hay asiento de liquidación que comparar; es lo presentado y su justificante."""

    modelo = "111"
    nombre, titulo = "declaraciones-111", "Declaraciones presentadas"
    descripcion = "Modelo 111 de cada periodo, tal como se presentó, con su justificante en PDF. Sólo lectura."
    columnas = [
        Col("periodo", "Periodo", TEXTO, 0.9), Col("tipo", "Tipo", TEXTO, 1.1), Col("emision", "Emitida", FECHA, 1.1), Col("justificante", "Justificante", TEXTO, 1.8),
        Col("retenciones", "Retenciones", DINERO, 1.3), Col("resultado", "A ingresar", DINERO, 1.3), Col("pdf", "PDF", TEXTO, 1.4),
    ]

    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        consulta = select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ctx.empresa.id, DeclaracionPresentada.modelo == self.modelo, DeclaracionPresentada.anio == ctx.ejercicio.anio).order_by(
            DeclaracionPresentada.periodo, DeclaracionPresentada.tipo)
        return [
            Fila(str(d.id), dict(periodo=f"{d.periodo}T", tipo="Presentada" if d.tipo == 1 else f"Tipo {d.tipo}", emision=d.fecha_emision, justificante=d.justificante, retenciones=d.resultado_liquidacion or None,
                                 resultado=d.resultado, pdf="Disponible" if d.pdf_ruta else None))
            for d in ctx.sesion.scalars(consulta)
        ]

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        d = ctx.sesion.get(DeclaracionPresentada, int(id))
        if d is None or d.empresa_id != ctx.empresa.id or d.modelo != self.modelo:
            return None
        casillas = json.loads(d.casillas or "{}")
        etiquetas = {c["casilla"]: c["desc"] for c in fichero111.DISENO if c["casilla"] is not None}
        filas = [[f"Casilla {int(c):02d}", etiquetas.get(int(c), ""), Decimal(str(v))] for c, v in sorted(casillas.items(), key=lambda x: int(x[0]))]
        tabla = Tabla(f"Modelo 111 · {d.periodo}T {d.anio}", [Columna("Casilla", ancho=1.2), Columna("Concepto", ancho=4), Columna("Importe", DINERO, 1.3)], filas,
                      f"{'Emitida el ' + format(d.fecha_emision, '%d/%m/%Y') if d.fecha_emision else 'Sin fecha de emisión'}{' · justificante ' + d.justificante if d.justificante else ''}")
        enlaces = [("Ver el PDF presentado", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/declaraciones/{d.id}/pdf")] if d.pdf_ruta else []
        return Detalle(f"Declaración presentada · modelo 111 · {d.periodo}T {d.anio}", tabla, [("PDF presentado", d.pdf_nombre or "no disponible")], [], enlaces)


class ListadoDeclaraciones190(ListadoDeclaraciones):
    """Las del modelo 190 (los ficheros presentados que hay en AEAT/ y su PDF): perceptores, percepciones y retenciones del ejercicio."""

    modelo = "190"
    nombre, titulo = "declaraciones-190", "Declaraciones presentadas"
    descripcion = "Modelo 190 de cada ejercicio, tal como se presentó, con su justificante en PDF. Sólo lectura."
    columnas = [
        Col("anio", "Ejercicio", TEXTO, 0.9), Col("emision", "Presentada", FECHA, 1.1), Col("justificante", "Justificante", TEXTO, 1.8), Col("perceptores", "Perceptores", TEXTO, 1.1),
        Col("percepciones", "Percepciones", DINERO, 1.3), Col("retenciones", "Retenciones", DINERO, 1.3), Col("pdf", "PDF", TEXTO, 1.4),
    ]

    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        consulta = select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ctx.empresa.id, DeclaracionPresentada.modelo == self.modelo, DeclaracionPresentada.anio == ctx.ejercicio.anio)
        filas = []
        for d in ctx.sesion.scalars(consulta):
            c = json.loads(d.casillas or "{}")
            filas.append(Fila(str(d.id), dict(anio=str(d.anio), emision=d.fecha_emision, justificante=d.justificante, perceptores=str(c.get("perceptores", 0)), percepciones=Decimal(str(c.get("percepciones", 0))),
                                              retenciones=Decimal(str(c.get("retenciones", 0))), pdf="Disponible" if d.pdf_ruta else None)))
        return filas

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        d = ctx.sesion.get(DeclaracionPresentada, int(id))
        if d is None or d.empresa_id != ctx.empresa.id or d.modelo != self.modelo:
            return None
        c = json.loads(d.casillas or "{}")
        filas = [[p["nif"], p["nombre"], f"{p['provincia']}{p['clave']}{p['subclave']}", Decimal(str(p["percepcion"])), Decimal(str(p["retencion"]))] for p in c.get("lista", [])]
        tabla = Tabla(f"Modelo 190 · ejercicio {d.anio}", [Columna("NIF", ancho=1.4), Columna("Perceptor", ancho=4), Columna("Prov./clave", ancho=1.2), Columna("Percepción", DINERO, 1.3), Columna("Retención", DINERO, 1.3)], filas,
                      f"Presentada{' el ' + format(d.fecha_emision, '%d/%m/%Y') if d.fecha_emision else ''}{' · justificante ' + d.justificante if d.justificante else ''}")
        enlaces = [("Ver el PDF presentado", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/declaraciones/{d.id}/pdf")] if d.pdf_ruta else []
        return Detalle(f"Declaración presentada · modelo 190 · ejercicio {d.anio}", tabla, [("PDF presentado", d.pdf_nombre or "no disponible")], [], enlaces)


class ListadoDeclaraciones347(ListadoDeclaraciones):
    """Las del modelo 347 (los ficheros presentados que hay en AEAT/ y su PDF): declarados e importe total del ejercicio."""

    modelo = "347"
    nombre, titulo = "declaraciones-347", "Declaraciones presentadas"
    descripcion = "Modelo 347 de cada ejercicio, tal como se presentó, con su justificante en PDF. Sólo lectura."
    columnas = [
        Col("anio", "Ejercicio", TEXTO, 0.9), Col("emision", "Presentada", FECHA, 1.1), Col("justificante", "Justificante", TEXTO, 1.8), Col("declarados", "Declarados", TEXTO, 1.1),
        Col("total", "Importe total", DINERO, 1.3), Col("pdf", "PDF", TEXTO, 1.4),
    ]

    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        consulta = select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ctx.empresa.id, DeclaracionPresentada.modelo == self.modelo, DeclaracionPresentada.anio == ctx.ejercicio.anio)
        return [
            Fila(str(d.id), dict(anio=str(d.anio), emision=d.fecha_emision, justificante=d.justificante, declarados=str(json.loads(d.casillas or "{}").get("declarados", 0)),
                                 total=Decimal(str(json.loads(d.casillas or "{}").get("total", 0))), pdf="Disponible" if d.pdf_ruta else None))
            for d in ctx.sesion.scalars(consulta)
        ]

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        d = ctx.sesion.get(DeclaracionPresentada, int(id))
        if d is None or d.empresa_id != ctx.empresa.id or d.modelo != self.modelo:
            return None
        c = json.loads(d.casillas or "{}")
        filas = [[p["clave"], p["nif"], p["nombre"], p["provincia"], *[Decimal(str(x)) for x in p["trimestres"]], Decimal(str(p["anual"]))] for p in c.get("lista", [])]
        tabla = Tabla(f"Modelo 347 · ejercicio {d.anio}", [Columna("Clave", ancho=0.7), Columna("NIF", ancho=1.4), Columna("Nombre", ancho=4), Columna("Prov.", ancho=0.7), Columna("1T", DINERO, 1.2),
                                                         Columna("2T", DINERO, 1.2), Columna("3T", DINERO, 1.2), Columna("4T", DINERO, 1.2), Columna("Anual", DINERO, 1.3)], filas,
                      f"Presentada{' el ' + format(d.fecha_emision, '%d/%m/%Y') if d.fecha_emision else ''}{' · justificante ' + d.justificante if d.justificante else ''}")
        enlaces = [("Ver el PDF presentado", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/declaraciones/{d.id}/pdf")] if d.pdf_ruta else []
        return Detalle(f"Declaración presentada · modelo 347 · ejercicio {d.anio}", tabla, [("PDF presentado", d.pdf_nombre or "no disponible")], [], enlaces)
