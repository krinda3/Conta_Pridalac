"""Liquidación del IVA en la web: un renglón por periodo (trimestre, bimestre o mes) con su estado, y la ficha de cada periodo
para ver el cálculo, liquidar, volver a liquidar o deshacer. Los parámetros (periodicidad, días de pago y cuentas de Hacienda)
se editan desde el propio listado.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Parametro, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.servicios import iva as svc
from conta_pridalac.servicios.extras import eliminar_extra
from conta_pridalac.web.comun import cuentas_para_listas, id_de_cuenta, texto_dinero
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
PARAMETROS = ("IVA_PERIODICIDAD", "IVA_DIAS_PAGO", "IVA_DEBE", "IVA_HABER")


def _periodicidad(ctx: Contexto) -> int:
    try:
        n = int(svc.parametro(ctx.sesion, ctx.ejercicio, "IVA_PERIODICIDAD", "4"))
    except ValueError:
        n = 4
    return n if n in (4, 6, 12) else 4


def _dias_pago(ctx: Contexto) -> list[int] | None:
    texto = svc.parametro(ctx.sesion, ctx.ejercicio, "IVA_DIAS_PAGO")
    try:
        return [int(x) for x in texto.split(",")] if texto else None
    except ValueError:
        return None


def _periodos(ctx: Contexto) -> list[tuple[date, date]]:
    n = _periodicidad(ctx)
    meses = 12 // n
    anio = ctx.ejercicio.anio
    return [svc.periodo_de(date(anio, 1 + i * meses, 1), n) for i in range(n)]


def _grabada(ctx: Contexto, hasta: date) -> tuple[Asiento | None, dict[str, Decimal]]:
    a = svc._asiento_de_liquidacion(ctx.sesion, ctx.ejercicio, hasta)
    if a is None:
        return None, {}
    lineas: dict[str, Decimal] = {}
    for ap in a.apuntes:
        lineas[ap.cuenta.codigo] = lineas.get(ap.cuenta.codigo, CERO) + ap.debe - ap.haber
    return a, {c: v for c, v in lineas.items() if v != 0}


def _estado(grabada: dict, asiento, calculada: svc.Liquidacion, presentada=None) -> str:
    nueva = {c: v for c, v in calculada.lineas.items() if v != 0}
    if asiento is None:
        return "Sin liquidar" if nueva else "Sin IVA"
    if presentada is not None:  # una liquidación presentada es definitiva: sólo cuenta que coincida con lo presentado
        return "Presentado" if svc.coincide_con_lo_presentado(asiento, presentada) else "Distinto de lo presentado"
    return "Liquidado" if grabada == nueva else "Desactualizado"


class ListadoLiquidacionesIva(Listado):
    nombre, titulo = "liquidacion-iva", "Liquidación del IVA"
    descripcion = "Un renglón por periodo. Doble clic para ver el cálculo, liquidarlo, volver a liquidarlo o deshacer la liquidación."
    formulario_propio = True
    editable = True
    acciones_extra = [("Parámetros del IVA", "accion/parametros")]
    columnas = [
        Col("periodo", "Periodo", TEXTO, 2.2), Col("desde", "Desde", FECHA, 1.1), Col("hasta", "Hasta", FECHA, 1.1), Col("soportado", "IVA soportado", DINERO, 1.3),
        Col("repercutido", "IVA repercutido", DINERO, 1.3), Col("compensado", "Compensado", DINERO, 1.2), Col("resultado", "Resultado", DINERO, 1.3), Col("sentido", "A…", TEXTO, 1.1),
        Col("pago", "Fecha de pago", FECHA, 1.1), Col("asiento", "Asiento", TEXTO, 0.9), Col("estado", "Estado", TEXTO, 1.4),
    ]

    def filas(self, ctx, params):
        n = _periodicidad(ctx)
        filas = []
        for desde, hasta in _periodos(ctx):
            liq = svc.calcular_liquidacion(ctx.sesion, ctx.ejercicio, desde, hasta)
            asiento, grabada = _grabada(ctx, hasta)
            presentada = svc.declaracion_de(ctx.sesion, asiento) if asiento else None
            estado = _estado(grabada, asiento, liq, presentada)
            if liq.a_pagar > 0:
                resultado, sentido = liq.a_pagar, "pagar"
            elif liq.a_compensar > 0:
                resultado, sentido = liq.a_compensar, "compensar"
            else:
                resultado, sentido = None, None
            filas.append(Fila(hasta.isoformat(), dict(
                periodo=svc.texto_periodo(desde, hasta, n).replace("REGUL. ", ""), desde=desde, hasta=hasta, soportado=liq.soportado or None, repercutido=liq.repercutido or None,
                compensado=liq.compensado or None, resultado=resultado, sentido=sentido, pago=svc.fecha_de_pago(hasta, n, _dias_pago(ctx)) if liq.a_pagar > 0 else None,
                asiento=asiento.identificador if asiento else None, estado=estado,
            ), clase="aviso-fila" if estado == "Desactualizado" else ""))
        return filas

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("soportado", "repercutido", "compensado")}

    # ---- ficha del periodo
    def formulario(self, ctx, id, errores=None, compensar=True):
        try:
            hasta = date.fromisoformat(id)
        except (TypeError, ValueError):
            raise ErrorContable("Periodo no válido") from None
        n = _periodicidad(ctx)
        desde, fin = svc.periodo_de(hasta, n)
        if fin != hasta or hasta.year != ctx.ejercicio.anio:
            raise ErrorContable("Ese periodo no es de este ejercicio")
        liq = svc.calcular_liquidacion(ctx.sesion, ctx.ejercicio, desde, hasta, compensar=compensar)
        asiento, grabada = _grabada(ctx, hasta)
        presentada = svc.declaracion_de(ctx.sesion, asiento) if asiento else None
        estado = _estado(grabada, asiento, liq, presentada)
        nombres = {c: nombre for c, nombre in ctx.sesion.execute(select(Cuenta.codigo, Cuenta.nombre).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo.in_(set(liq.lineas) | set(grabada) | set(liq.saldos))))}
        comparacion = [(c, nombres.get(c, ""), grabada.get(c), liq.lineas.get(c)) for c in sorted(set(liq.lineas) | set(grabada))]
        vencimiento = None
        if asiento is not None:
            v = ctx.sesion.scalars(select(Vencimiento).join(Apunte, Apunte.id == Vencimiento.apunte_id).where(Apunte.asiento_id == asiento.id)).first()
            vencimiento = (v.fecha, v.importe) if v else None
        return "_liquidacion_iva.html", dict(
            id=id, desde=desde, hasta=hasta, liq=liq, estado=estado, asiento=asiento, comparacion=comparacion, compensar=compensar, errores=errores or [],
            saldos=[(c, nombres.get(c, ""), s) for c, s in sorted(liq.saldos.items())], fecha_pago=svc.fecha_de_pago(hasta, n, _dias_pago(ctx)) if liq.a_pagar > 0 else None,
            vencimiento=vencimiento, texto=svc.texto_periodo(desde, hasta, n), cerrado=ctx.ejercicio.cerrado, presentada=presentada,
            resultado_asiento=svc.resultado_del_asiento(asiento) if asiento else None,
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        id, accion, compensar = datos.get("id", ""), datos.get("accion", "liquidar"), datos.get("compensar") == "on"
        mensaje = None
        try:
            hasta = date.fromisoformat(id)
            asiento_actual = svc._asiento_de_liquidacion(ctx.sesion, ctx.ejercicio, hasta) if accion in ("liquidar", "deshacer") else None
            if asiento_actual is not None and svc.declaracion_de(ctx.sesion, asiento_actual) is not None:
                raise ErrorContable("Esta liquidación ya está presentada a la AEAT: no se puede volver a liquidar ni deshacer")
            if accion == "liquidar":
                liq, r = svc.liquidar_iva(ctx.sesion, ctx.ejercicio, hasta, compensar=compensar, periodicidad=_periodicidad(ctx), dias_pago=_dias_pago(ctx))
                if liq.a_pagar > 0:
                    mensaje = f"Liquidado: a pagar {texto_dinero(liq.a_pagar)} el {svc.fecha_de_pago(hasta, _periodicidad(ctx), _dias_pago(ctx)):%d/%m/%Y}"
                elif liq.a_compensar > 0:
                    mensaje = f"Liquidado: {texto_dinero(liq.a_compensar)} a compensar en periodos siguientes"
                else:
                    mensaje = "Liquidado: sin diferencia que pagar ni compensar"
            elif accion == "deshacer":
                asiento = svc._asiento_de_liquidacion(ctx.sesion, ctx.ejercicio, hasta)
                if asiento is None:
                    raise ErrorContable("Este periodo no está liquidado")
                eliminar_extra(ctx.sesion, ctx.ejercicio, asiento)
                mensaje = "Liquidación deshecha"
            elif accion != "ver":  # «ver» sólo recalcula la vista con la opción de compensar elegida
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, id, errores=[str(ex)], compensar=compensar)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, id, compensar=compensar)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []

    # ---- parámetros del IVA
    def accion(self, ctx, accion, items):
        if accion != "parametros":
            raise ErrorContable("Acción desconocida")
        actuales = {c: svc.parametro(ctx.sesion, ctx.ejercicio, c, "") or "" for c in PARAMETROS}
        actuales["IVA_PERIODICIDAD"] = actuales["IVA_PERIODICIDAD"] or "4"
        contexto = dict(valores=actuales, errores=[], cuentas=cuentas_para_listas(ctx))
        if items is None:
            return "_parametros_iva.html", contexto
        datos = {k: (v or "").strip() for k, v in items if isinstance(v, str)}
        contexto["valores"] = {c: datos.get(c, "") for c in PARAMETROS}
        errores: list[str] = []
        if datos.get("IVA_PERIODICIDAD") not in ("4", "6", "12"):
            errores.append("La periodicidad es trimestral (4), bimestral (6) o mensual (12)")
        dias = datos.get("IVA_DIAS_PAGO", "")
        if dias:
            try:
                valores = [int(x) for x in dias.split(",")]
                if not all(1 <= v <= 31 for v in valores):
                    raise ValueError
            except ValueError:
                errores.append("Los días de pago son números del 1 al 31 separados por comas (uno por periodo), por ejemplo 20,20,20,30")
        for clave, nombre in (("IVA_DEBE", "Hacienda deudora por IVA"), ("IVA_HABER", "Hacienda acreedora por IVA")):
            id_de_cuenta(ctx, datos.get(clave, ""), nombre, errores)
        if errores:
            contexto["errores"] = errores
            return "_parametros_iva.html", contexto
        for clave in PARAMETROS:
            fila = ctx.sesion.scalar(select(Parametro).where(Parametro.empresa_id == ctx.empresa.id, Parametro.clave == clave))
            if fila is None:
                ctx.sesion.add(Parametro(empresa_id=ctx.empresa.id, clave=clave, valor=datos.get(clave, "")))
            else:
                fila.valor = datos.get(clave, "")
        ctx.sesion.commit()
        return None, {"mensaje": "Parámetros del IVA guardados"}
