"""Cierre y apertura del ejercicio en la web.

Un listado con los ejercicios de la empresa y, en la ficha de cada uno, la lista de comprobación previa al cierre (auditoría, IVA,
amortizaciones, cartera de vencimientos), el resultado provisional y los botones de **cerrar** (regulariza, cierra y abre el siguiente),
**reabrir** (deshace el cierre) y la creación de un ejercicio nuevo.
"""
from __future__ import annotations

import calendar
from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from conta_pridalac.auditoria import ERROR, auditar
from conta_pridalac.db.modelos import Asiento, Ejercicio, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO
from conta_pridalac.servicios import bienes as svc_bienes
from conta_pridalac.servicios import cierre as svc
from conta_pridalac.web import iva as web_iva
from conta_pridalac.web.comun import texto_dinero
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado
from conta_pridalac.web.tesoreria import _vencimientos_con_pendiente

CERO = Decimal("0.00")


def _contexto_de(ctx: Contexto, ejercicio: Ejercicio) -> Contexto:
    return Contexto(ctx.sesion, ctx.empresa, ejercicio, ctx.slug, ctx.config)


def _resultado(ctx: Contexto, ej: Ejercicio) -> Decimal:
    """Beneficio (positivo) o pérdida (negativo) del ejercicio: lo que suman las cuentas de ingresos y gastos sin contar regularización ni cierre."""
    prefijos = svc.prefijos_ingresos_y_gastos(ctx.sesion, ej)
    saldos = svc.saldos_del_ejercicio(ctx.sesion, ej, excluir=(svc.SUBTIPO_REGULARIZACION, svc.SUBTIPO_CIERRE))
    return -sum((s for c, s in saldos.items() if c.startswith(prefijos)), CERO)


def _asiento(ctx: Contexto, ej: Ejercicio, subtipo: str) -> Asiento | None:
    return ctx.sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.subtipo == subtipo).order_by(Asiento.numero)).first()


def _siguiente(ctx: Contexto, ej: Ejercicio) -> Ejercicio | None:
    inicio = date.fromordinal(ej.fecha_fin.toordinal() + 1)
    return ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ej.empresa_id, Ejercicio.fecha_inicio == inicio)).first()


class ListadoEjercicios(Listado):
    nombre, titulo = "ejercicios", "Cierre del ejercicio"
    descripcion = "Ejercicios de la empresa. Doble clic para ver la lista de comprobación, cerrar el ejercicio (y abrir el siguiente) o reabrirlo."
    formulario_propio = True
    editable = True
    acciones_extra = [("＋ Nuevo ejercicio", "accion/nuevo")]
    columnas = [
        Col("anio", "Ejercicio", ENTERO, 1), Col("desde", "Desde", FECHA, 1.1), Col("hasta", "Hasta", FECHA, 1.1), Col("estado", "Estado", TEXTO, 1.2), Col("asientos", "Asientos", ENTERO, 0.9),
        Col("resultado", "Resultado", DINERO, 1.3), Col("cierre", "Asiento de cierre", TEXTO, 1.3), Col("apertura", "Apertura del siguiente", TEXTO, 1.5),
    ]

    def filas(self, ctx, params):
        filas = []
        for ej in ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id).order_by(Ejercicio.anio.desc())):
            cierre = _asiento(ctx, ej, svc.SUBTIPO_CIERRE)
            siguiente = _siguiente(ctx, ej)
            apertura = _asiento(ctx, siguiente, svc.SUBTIPO_APERTURA) if siguiente else None
            filas.append(Fila(str(ej.anio), dict(
                anio=ej.anio, desde=ej.fecha_inicio, hasta=ej.fecha_fin, estado="Cerrado" if ej.cerrado else "Abierto", resultado=_resultado(ctx, ej) or None,
                asientos=ctx.sesion.scalar(select(func.count()).select_from(Asiento).where(Asiento.ejercicio_id == ej.id)),
                cierre=cierre.identificador if cierre else None, apertura=f"{apertura.identificador} ({siguiente.anio})" if apertura else None,
            )))
        return filas

    # ---- ficha de un ejercicio
    def formulario(self, ctx, id, errores=None, mensaje_cierre=None):
        ej = ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id, Ejercicio.anio == int(id))).first() if str(id).isdigit() else None
        if ej is None:
            raise ErrorContable("El ejercicio no existe")
        c = _contexto_de(ctx, ej)
        hallazgos = auditar(ctx.sesion, ej)
        errores_aud = [h for h in hallazgos if h.gravedad == ERROR]
        avisos = Counter(h.codigo for h in hallazgos if h.gravedad != ERROR)

        # IVA
        iva = None
        try:
            estados = []
            n = web_iva._periodicidad(c)
            for desde, hasta in web_iva._periodos(c):
                liq = web_iva.svc.calcular_liquidacion(ctx.sesion, ej, desde, hasta)
                asiento, grabada = web_iva._grabada(c, hasta)
                estados.append(web_iva._estado(grabada, asiento, liq))
            iva = Counter(estados)
        except ErrorContable as ex:
            iva = str(ex)

        pendientes_amortizar = svc_bienes.periodos_pendientes(ctx.sesion, ej)
        cartera = [(v, pte) for v, pte in _vencimientos_con_pendiente(c) if pte != 0]
        regul = _asiento(ctx, ej, svc.SUBTIPO_REGULARIZACION)
        cierre = _asiento(ctx, ej, svc.SUBTIPO_CIERRE)
        siguiente = _siguiente(ctx, ej)
        apertura = _asiento(ctx, siguiente, svc.SUBTIPO_APERTURA) if siguiente else None
        prefijos = svc.prefijos_ingresos_y_gastos(ctx.sesion, ej)
        sin_regularizar = [(cuenta, saldo) for cuenta, saldo in sorted(svc.saldos_del_ejercicio(ctx.sesion, ej, excluir=(svc.SUBTIPO_CIERRE,)).items()) if cuenta.startswith(prefijos)]
        return "_ejercicio.html", dict(
            ej=ej, errores=errores or [], errores_aud=errores_aud, avisos=avisos, iva=iva, resultado=_resultado(ctx, ej), n_asientos=ctx.sesion.scalar(select(func.count()).select_from(Asiento).where(Asiento.ejercicio_id == ej.id)),
            pendientes_amortizar=len(pendientes_amortizar), importe_amortizar=sum((p.importe_previsto for p in pendientes_amortizar), CERO),
            n_cartera=len(cartera), importe_cartera=sum((abs(pte) for _, pte in cartera), CERO), regul=regul, cierre=cierre, siguiente=siguiente, apertura=apertura,
            sin_regularizar=len(sin_regularizar), mensaje_cierre=mensaje_cierre,
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        id, accion = datos.get("id", ""), datos.get("accion", "")
        mensaje = None
        try:
            ej = ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id, Ejercicio.anio == int(id))).first() if id.isdigit() else None
            if ej is None:
                raise ErrorContable("El ejercicio no existe")
            from conta_pridalac.servicios.huellas import anotar_al_confirmar

            if accion == "cerrar":
                r = svc.cerrar_ejercicio(ctx.sesion, ej, abrir_siguiente=datos.get("abrir_siguiente") == "on")
                anotar_al_confirmar(ctx.sesion, ctx.config.almacen, ctx.empresa.codigo, f"cierre del ejercicio {ej.anio}")
                signo = "Beneficio" if r.resultado >= 0 else "Pérdida"
                mensaje = f"Ejercicio {ej.anio} cerrado. {signo} del ejercicio: {texto_dinero(abs(r.resultado))}"
                if r.apertura is not None:
                    mensaje += f". Abierto el {r.apertura.ejercicio.anio} con {r.apertura.vencimientos_arrastrados} vencimiento(s) arrastrado(s)"
                if r.advertencias:
                    mensaje += ". Ojo: " + " · ".join(r.advertencias)
            elif accion == "reabrir":
                svc.reabrir_ejercicio(ctx.sesion, ej)
                anotar_al_confirmar(ctx.sesion, ctx.config.almacen, ctx.empresa.codigo, f"reapertura del ejercicio {ej.anio}")
                mensaje = f"Ejercicio {ej.anio} reabierto: se deshicieron el asiento de cierre, la regularización de ingresos y gastos y la apertura del siguiente"
            else:
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, id if id.isdigit() else str(ctx.ejercicio.anio), errores=[str(ex)])
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, id)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []

    # ---- nuevo ejercicio
    def accion(self, ctx, accion, items):
        if accion != "nuevo":
            raise ErrorContable("Acción desconocida")
        ultimo = ctx.sesion.scalar(select(func.max(Ejercicio.anio)).where(Ejercicio.empresa_id == ctx.empresa.id)) or date.today().year
        base = dict(errores=[], anio=str(ultimo + 1))
        if items is None:
            return "_nuevo_ejercicio.html", base
        datos = {k: (v or "").strip() for k, v in items if isinstance(v, str)}
        base["anio"] = datos.get("anio", "")
        try:
            if not datos.get("anio", "").isdigit() or not 1990 <= int(datos["anio"]) <= 2100:
                raise ErrorContable("Indique un año entre 1990 y 2100")
            anio = int(datos["anio"])
            if ctx.sesion.scalar(select(Ejercicio.id).where(Ejercicio.empresa_id == ctx.empresa.id, Ejercicio.anio == anio)):
                raise ErrorContable(f"Ya existe el ejercicio {anio}")
            ctx.sesion.add(Ejercicio(empresa_id=ctx.empresa.id, anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, calendar.monthrange(anio, 12)[1]), cerrado=False))
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            base["errores"] = [str(ex)]
            return "_nuevo_ejercicio.html", base
        return None, {"mensaje": f"Ejercicio {anio} creado (vacío): ya puede elegirlo arriba"}
