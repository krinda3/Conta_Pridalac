"""Bienes de inversión en la web: ficha, cuadro de amortización, amortización del ejercicio, baja y libro de bienes de inversión (IVA)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from conta_pridalac.db.modelos import AmortizacionPeriodo, BienInversion, Cuenta
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import introducir_fecha, parsear_fecha
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, PORCENTAJE, TEXTO
from conta_pridalac.servicios import bienes as svc
from conta_pridalac.servicios.bienes_iva import libro_bienes_inversion
from conta_pridalac.servicios.cuentas import cuenta_estandar
from conta_pridalac.web.comun import cuentas_para_listas, dinero_opcional, fecha_texto, id_de_cuenta, texto_dinero
from conta_pridalac.web.listados import Campo, Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
def _cuentas_baja_defecto(ctx) -> dict[str, str]:
    """Pérdidas (671) y beneficios (771) del inmovilizado, con los dígitos de la empresa."""
    return {"cuenta_perdidas": cuenta_estandar("67100000", ctx.empresa.digitos_cuenta), "cuenta_beneficios": cuenta_estandar("77100000", ctx.empresa.digitos_cuenta)}


def _amortizado(b: BienInversion) -> Decimal:
    return sum((a.importe_contable or CERO for a in b.amortizaciones), CERO)


def _estado(b: BienInversion) -> str:
    if b.fecha_baja:
        return "Dado de baja"
    neto = b.precio_compra - b.valor_residual
    amortizado = _amortizado(b)
    if amortizado == 0:
        return "Sin amortizar"
    return "Totalmente amortizado" if amortizado >= neto else "En amortización"


def _periodos_del_ejercicio(ctx: Contexto, b: BienInversion) -> list[AmortizacionPeriodo]:
    return [a for a in b.amortizaciones if ctx.ejercicio.fecha_inicio <= a.hasta <= ctx.ejercicio.fecha_fin]


def _entero(texto: str, nombre: str) -> int | None:
    if not (texto or "").strip():
        return None
    try:
        n = int(texto.strip())
    except ValueError:
        raise ValueError(f"«{nombre}»: «{texto}» no es un número entero") from None
    if n <= 0:
        raise ValueError(f"«{nombre}» debe ser mayor que cero")
    return n


class ListadoBienes(Listado):
    nombre, titulo = "bienes", "Bienes de inversión"
    descripcion = "Inmovilizado con su cuadro de amortización. Doble clic para ver y editar el bien, amortizar sus periodos o darlo de baja."
    formulario_propio = True
    anadir = borrar = editable = True
    columnas = [
        Col("codigo", "Cód.", ENTERO, 0.6), Col("descripcion", "Descripción", TEXTO, 4), Col("tipo", "Tipo", TEXTO, 1.5), Col("cuenta", "Cuenta", TEXTO, 1.2),
        Col("funcionamiento", "Puesta en funcionamiento", FECHA, 1.4), Col("precio", "Precio", DINERO, 1.2), Col("residual", "Residual", DINERO, 1.0), Col("vida", "Vida (periodos)", ENTERO, 0.9),
        Col("amortizado", "Amortizado", DINERO, 1.2), Col("pendiente", "Pendiente de amortizar", DINERO, 1.4), Col("baja", "Baja", FECHA, 1.0), Col("estado", "Estado", TEXTO, 1.5),
    ]
    parametros = [Campo("estado", "Mostrar", "select", opciones=[("", "Todos"), ("uso", "En uso"), ("baja", "Dados de baja"), ("amortizados", "Totalmente amortizados")])]
    acciones_extra = [("Amortizar el ejercicio", "accion/amortizar")]

    def filas(self, ctx, params):
        filas = []
        for b in ctx.sesion.scalars(select(BienInversion).where(BienInversion.empresa_id == ctx.empresa.id).order_by(BienInversion.codigo)):
            estado = _estado(b)
            filtro = params.get("estado")
            if (filtro == "uso" and estado == "Dado de baja") or (filtro == "baja" and estado != "Dado de baja") or (filtro == "amortizados" and estado != "Totalmente amortizado"):
                continue
            amortizado = _amortizado(b)
            filas.append(Fila(str(b.id), dict(
                codigo=b.codigo, descripcion=b.descripcion, tipo=b.tipo_elemento, cuenta=b.cuenta_inmovilizado.codigo if b.cuenta_inmovilizado else None,
                funcionamiento=b.fecha_funcionamiento, precio=b.precio_compra, residual=b.valor_residual or None, vida=b.periodos_vida, amortizado=amortizado,
                pendiente=max(b.precio_compra - b.valor_residual - amortizado, CERO) if not b.fecha_baja else None, baja=b.fecha_baja, estado=estado,
            )))
        return filas

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("precio", "amortizado", "pendiente")}

    # ---- formulario
    def formulario(self, ctx, id, errores=None, valores=None):
        bien = None
        if id:
            bien = ctx.sesion.get(BienInversion, int(id))
            if bien is None or bien.empresa_id != ctx.empresa.id:
                raise ErrorContable("El bien no existe")
        if valores is None:
            valores = self._valores_de(ctx, bien)
        cuadro = []
        if bien is not None:
            periodos_aqui = {a.id for a in _periodos_del_ejercicio(ctx, bien)}
            cuadro = [(a, a.id in periodos_aqui) for a in bien.amortizaciones]
        return "_bien.html", dict(
            b=bien, valores=valores, errores=errores or [], cuadro=cuadro, cuentas=cuentas_para_listas(ctx), estado=_estado(bien) if bien else "",
            amortizado=_amortizado(bien) if bien else CERO, previsto=sum((a.importe_previsto for a in bien.amortizaciones), CERO) if bien else CERO,
        )

    def _valores_de(self, ctx, bien):
        if bien is None:
            return dict(descripcion="", tipo_elemento="", numero_factura_compra="", fecha_adquisicion="", fecha_funcionamiento="", precio_compra="", valor_residual="", periodos_vida="",
                        coeficiente_pct="", meses_periodo="12", iva_soportado="", cuenta_inmovilizado="", cuenta_amortizacion="", cuenta_dotacion="", notas="",
                        fecha_baja="", causa_baja="", no_amortizar_en_baja="", precio_venta="", cuenta_cobro="", fecha_asiento_baja="", **_cuentas_baja_defecto(ctx))
        return dict(
            descripcion=bien.descripcion, tipo_elemento=bien.tipo_elemento or "", numero_factura_compra=bien.numero_factura_compra or "", fecha_adquisicion=fecha_texto(bien.fecha_adquisicion),
            fecha_funcionamiento=fecha_texto(bien.fecha_funcionamiento), precio_compra=texto_dinero(bien.precio_compra), valor_residual=texto_dinero(bien.valor_residual) if bien.valor_residual else "",
            periodos_vida=str(bien.periodos_vida or ""), coeficiente_pct=texto_dinero(bien.coeficiente_pct) if bien.coeficiente_pct else "", meses_periodo=str(bien.meses_periodo or 12),
            iva_soportado=texto_dinero(bien.iva_soportado) if bien.iva_soportado else "", cuenta_inmovilizado=bien.cuenta_inmovilizado.codigo if bien.cuenta_inmovilizado else "",
            cuenta_amortizacion=bien.cuenta_amortizacion.codigo if bien.cuenta_amortizacion else "", cuenta_dotacion=bien.cuenta_dotacion.codigo if bien.cuenta_dotacion else "", notas=bien.notas or "",
            fecha_baja=fecha_texto(bien.fecha_baja), causa_baja=bien.causa_baja or "", no_amortizar_en_baja="on" if bien.no_amortizar_en_baja else "", precio_venta="", cuenta_cobro="",
            fecha_asiento_baja=fecha_texto(bien.fecha_baja), **_cuentas_baja_defecto(ctx),
        )

    def _leer_ficha(self, ctx, datos) -> dict:
        errores: list[str] = []

        def f(nombre, titulo, requerida=False):
            texto = (datos.get(nombre) or "").strip()
            if not texto:
                if requerida:
                    errores.append(f"Falta «{titulo}»")
                return None
            try:
                return parsear_fecha(texto, referencia=ctx.ejercicio.fecha_inicio)
            except ErrorContable as ex:
                errores.append(f"«{titulo}»: {ex}")

        def d(nombre, titulo):
            try:
                return dinero_opcional(datos.get(nombre, ""), titulo)
            except ValueError as ex:
                errores.append(str(ex))

        def n(nombre, titulo):
            try:
                return _entero(datos.get(nombre, ""), titulo)
            except ValueError as ex:
                errores.append(str(ex))

        ficha = dict(
            descripcion=(datos.get("descripcion") or "").strip(), tipo_elemento=(datos.get("tipo_elemento") or "").strip()[:64] or None,
            numero_factura_compra=(datos.get("numero_factura_compra") or "").strip()[:40] or None, fecha_adquisicion=f("fecha_adquisicion", "Fecha de adquisición"),
            fecha_funcionamiento=f("fecha_funcionamiento", "Puesta en funcionamiento", True), precio_compra=d("precio_compra", "Precio de compra"), valor_residual=d("valor_residual", "Valor residual") or CERO,
            periodos_vida=n("periodos_vida", "Vida útil (periodos)"), coeficiente_pct=d("coeficiente_pct", "Porcentaje por periodo"), meses_periodo=n("meses_periodo", "Meses por periodo") or 12,
            iva_soportado=d("iva_soportado", "IVA soportado") or CERO, notas=(datos.get("notas") or "").strip() or None,
        )
        if not ficha["descripcion"]:
            errores.append("Falta la descripción del bien")
        if ficha["precio_compra"] is None:
            errores.append("Falta el precio de compra")
        for clave, titulo in (("cuenta_inmovilizado", "inmovilizado"), ("cuenta_amortizacion", "amortización acumulada"), ("cuenta_dotacion", "dotación (gasto)")):
            codigo = (datos.get(clave) or "").strip()
            id_de_cuenta(ctx, codigo, titulo, errores)
            ficha[clave] = codigo
        return ficha, errores

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        accion = datos.get("accion", "guardar")
        bien = ctx.sesion.get(BienInversion, int(datos["id"])) if datos.get("id", "").isdigit() else None
        if datos.get("id") and (bien is None or bien.empresa_id != ctx.empresa.id):
            raise ErrorContable("El bien no existe")
        mensaje = None
        try:
            if accion == "guardar":
                ficha, errores = self._leer_ficha(ctx, datos)
                if errores:
                    raise ErrorContable(" · ".join(errores))
                if bien is None:
                    cuentas = {k: ficha.pop(k) for k in ("cuenta_inmovilizado", "cuenta_amortizacion", "cuenta_dotacion")}
                    bien = svc.alta_bien(ctx.sesion, ctx.empresa.id, **ficha, **cuentas)
                    mensaje = "Bien creado: ya puede ver su cuadro de amortización"
                else:
                    svc.modificar_ficha(ctx.sesion, bien, **ficha)
                    ctx.sesion.commit()
                    return str(bien.id), None, None, []
            elif bien is None:
                raise ErrorContable("Guarde primero el bien")
            elif re.fullmatch(r"(amortizar|deshacer)-\d+", accion):
                periodo = ctx.sesion.get(AmortizacionPeriodo, int(accion.split("-", 1)[1]))
                if periodo is None or periodo.bien_id != bien.id:
                    raise ErrorContable("El periodo no existe")
                if not (ctx.ejercicio.fecha_inicio <= periodo.hasta <= ctx.ejercicio.fecha_fin):
                    raise ErrorContable(f"El periodo acaba el {periodo.hasta:%d/%m/%Y}, en otro ejercicio: ábralo en ese ejercicio")
                if accion.startswith("amortizar-"):
                    svc.amortizar_periodo(ctx.sesion, ctx.ejercicio, periodo)
                    mensaje = f"Amortizado el periodo {periodo.anio}: {texto_dinero(periodo.importe_contable)}"
                else:
                    svc.deshacer_amortizacion(ctx.sesion, ctx.ejercicio, periodo)
                    mensaje = f"Deshecha la amortización del periodo {periodo.anio}"
            elif accion == "periodos":
                cambiados = 0
                for periodo in bien.amortizaciones:
                    if periodo.asiento_id or f"prev-{periodo.id}" not in datos:
                        continue
                    previsto = dinero_opcional(datos[f"prev-{periodo.id}"], "Importe previsto") or CERO
                    contable = dinero_opcional(datos.get(f"cont-{periodo.id}", ""), "Importe contabilizado")
                    if previsto != periodo.importe_previsto or contable != periodo.importe_contable:
                        svc.editar_periodo(ctx.sesion, periodo, importe_previsto=previsto, importe_contable=contable)
                        cambiados += 1
                mensaje = f"Cuadro actualizado: {cambiados} periodo(s) modificado(s)" if cambiados else "No había cambios en el cuadro"
            elif accion == "baja":
                fecha = parsear_fecha(datos.get("fecha_baja", ""), referencia=ctx.ejercicio.fecha_inicio) if datos.get("fecha_baja", "").strip() else None
                if fecha is None:
                    raise ErrorContable("Falta la fecha de baja")
                svc.dar_de_baja(ctx.sesion, bien, fecha, (datos.get("causa_baja") or "").strip(), no_amortizar_en_baja=datos.get("no_amortizar_en_baja") == "on")
                mensaje = f"Baja el {fecha:%d/%m/%Y}: el cuadro queda acortado"
            elif accion == "anular-baja":
                svc.anular_baja(ctx.sesion, bien)
                mensaje = "Baja anulada: el cuadro vuelve a ser el completo"
            elif accion == "asiento-baja":
                fecha = introducir_fecha(datos["fecha_asiento_baja"], ctx.ejercicio) if datos.get("fecha_asiento_baja", "").strip() else None
                r = svc.asiento_de_baja(
                    ctx.sesion, ctx.ejercicio, bien, fecha=fecha, precio_venta=dinero_opcional(datos.get("precio_venta", ""), "Precio de venta") or CERO,
                    cuenta_cobro=(datos.get("cuenta_cobro") or "").strip() or None, cuenta_perdidas=(datos.get("cuenta_perdidas") or "").strip() or _cuentas_baja_defecto(ctx)["cuenta_perdidas"],
                    cuenta_beneficios=(datos.get("cuenta_beneficios") or "").strip() or _cuentas_baja_defecto(ctx)["cuenta_beneficios"],
                )
                mensaje = f"Asiento de baja {r.asiento.identificador}: " + ("pérdida" if r.resultado < 0 else "beneficio" if r.resultado > 0 else "sin resultado") + (f" de {texto_dinero(abs(r.resultado))}" if r.resultado else "")
            elif accion == "deshacer-asiento-baja":
                svc.deshacer_asiento_de_baja(ctx.sesion, ctx.ejercicio, bien)
                mensaje = "Asiento de baja deshecho"
            else:
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            if bien is not None and bien.id is not None:
                plantilla, contexto = self.formulario(ctx, bien.id, errores=[str(ex)], valores={**self._valores_de(ctx, bien), **{k: datos.get(k, "") for k in self._valores_de(ctx, None)}})
            else:
                plantilla, contexto = self.formulario(ctx, None, errores=[str(ex)], valores={k: datos.get(k, "") for k in self._valores_de(ctx, None)})
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, bien.id)  # el formulario sigue abierto con el resultado
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []

    def eliminar(self, ctx, ids):
        for i in ids:
            bien = ctx.sesion.get(BienInversion, int(i))
            if bien is None or bien.empresa_id != ctx.empresa.id:
                raise ErrorContable("El bien no existe")
            svc.borrar_bien(ctx.sesion, bien)

    # ---- «Amortizar el ejercicio»
    def accion(self, ctx, accion, items):
        if accion != "amortizar":
            raise ErrorContable("Acción desconocida")
        hasta = None
        if items is not None:
            datos = {k: v for k, v in items if isinstance(v, str)}
            try:
                hasta = introducir_fecha(datos["hasta"], ctx.ejercicio) if datos.get("hasta", "").strip() else None
                resultado = svc.amortizar_ejercicio(ctx.sesion, ctx.ejercicio, hasta=hasta)
                ctx.sesion.commit()
            except (ErrorContable, ValueError) as ex:
                ctx.sesion.rollback()
                return "_amortizar.html", dict(errores=[str(ex)], pendientes=self._pendientes(ctx, None), hasta=datos.get("hasta", ""))
            n = len(resultado.amortizados)
            texto = f"Amortizados {n} periodo(s) por {texto_dinero(resultado.total)}" + (f"; sin amortizar: {'; '.join(resultado.omitidos)}" if resultado.omitidos else "")
            return None, {"mensaje": texto}
        return "_amortizar.html", dict(errores=[], pendientes=self._pendientes(ctx, hasta), hasta="")

    def _pendientes(self, ctx, hasta):
        filas = [(p.bien.descripcion, p.desde, p.hasta, p.importe_previsto) for p in svc.periodos_pendientes(ctx.sesion, ctx.ejercicio, hasta=hasta)]
        return dict(filas=filas, total=sum((f[3] for f in filas), CERO))


class ListadoLibroBienes(Listado):
    nombre, titulo = "bienes-iva", "Libro de bienes de inversión (IVA)"
    descripcion = "Bienes de más de 3.005,06 € con IVA soportado y su periodo de regularización de deducciones (5 años; 10 en terrenos y edificios)."
    columnas = [
        Col("codigo", "Cód.", ENTERO, 0.6), Col("bien", "Bien", TEXTO, 4), Col("factura", "Nº factura", TEXTO, 1.3), Col("adquisicion", "Adquisición", FECHA, 1.1), Col("funcionamiento", "Funcionamiento", FECHA, 1.2),
        Col("base", "Base", DINERO, 1.2), Col("iva", "IVA soportado", DINERO, 1.2), Col("anios", "Años", ENTERO, 0.6), Col("desde", "Desde", ENTERO, 0.7), Col("hasta", "Hasta", ENTERO, 0.7),
        Col("pct_inicial", "% inicial", PORCENTAJE, 0.8), Col("pct_anio", "% del año", PORCENTAJE, 0.8), Col("regularizacion", "Regularización", DINERO, 1.2), Col("avisos", "Avisos", TEXTO, 4),
    ]

    def filas(self, ctx, params):
        return [
            Fila(str(l.bien.id), dict(codigo=l.bien.codigo, bien=l.bien.descripcion, factura=l.bien.numero_factura_compra, adquisicion=l.bien.fecha_adquisicion, funcionamiento=l.bien.fecha_funcionamiento,
                                      base=l.base, iva=l.iva_soportado, anios=l.plazo, desde=l.primer_anio, hasta=l.ultimo_anio, pct_inicial=l.pct_deducible_inicial, pct_anio=l.pct_deducible_ejercicio,
                                      regularizacion=l.regularizacion, avisos="; ".join(l.avisos) or None), clase="aviso-fila" if l.avisos else "")
            for l in libro_bienes_inversion(ctx.sesion, ctx.ejercicio)
        ]

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("base", "iva", "regularizacion")}
