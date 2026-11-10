"""Líneas sin factura en la web: lo que queda libre en el extracto tras conciliar (`servicios/lineas_sin_factura.py`), con la propuesta de las reglas para cada una."""
from __future__ import annotations

from sqlalchemy import select

from conta_pridalac.db.modelos import Banco, Cuenta, ExtractoLinea, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.domain.fechas import introducir_fecha
from conta_pridalac.servicios import lineas_sin_factura as svc
from conta_pridalac.servicios import pagos_extracto
from conta_pridalac.servicios import trimestre
from conta_pridalac.web.comun import cuentas_para_listas, dinero_opcional, fecha_texto, texto_dinero
from conta_pridalac.web.conciliacion import _buscar_proveedor, _proveedores
from conta_pridalac.web.conciliar_pagos import ListadoConciliarPagos
from conta_pridalac.web.extractos import _opciones_de_bancos
from conta_pridalac.web.listados import Campo, Col, Fila, Listado


def _lineas_libres(ctx) -> list[ExtractoLinea]:
    p = trimestre.proponer(ctx.sesion, ctx.empresa.id)
    return sorted((p.lineas[l.id] for l in p.resultado.libres), key=lambda l: (l.fecha, l.id))


def _cuenta(ctx, codigo: str | None) -> Cuenta | None:
    if not (codigo or "").strip():
        return None
    c = ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo == codigo.strip())).first()
    if c is None:
        raise ErrorContable(f"La subcuenta {codigo} no existe en el plan de cuentas")
    return c


class ListadoLineasSinFactura(Listado):
    nombre, titulo = "lineas-sin-factura", "Líneas sin factura"
    descripcion = ("Todo lo que queda libre en el extracto: tickets de la tarjeta, la liquidación de la tarjeta, pagos del socio, impuestos, y los cargos que pagan facturas pendientes. Cada línea sale con lo que proponen las "
                   "reglas (las que ha guardado con «Recordar» y las aprendidas de su contabilidad anterior). Doble clic para decidir una; «Aplicar sugerencias» contabiliza de golpe las que tienen regla; "
                   "marque una o varias líneas y use «Pagar vencimientos con las marcadas» si pagan facturas pendientes. Las sugerencias automáticas de pago están en «Sugerencias de pago».")
    editable = True
    columnas = [
        Col("banco", "Banco", TEXTO, 2), Col("fecha", "Fecha", FECHA, 1.1), Col("concepto", "Concepto", TEXTO, 4), Col("importe", "Importe", DINERO, 1.3),
        Col("propuesta", "Qué se propone", TEXTO, 4), Col("origen", "Regla", TEXTO, 1.8),
    ]
    campos = [
        Campo("tratamiento", "Qué hacer con la línea", "select", opciones=[("", "— elija —"), (svc.CUENTA, "Llevarla a una cuenta (socio, liquidación de la tarjeta, impuestos…)"),
                                                                          (svc.TICKET, "Ticket: una factura de un proveedor con el IVA al 21 % incluido, pagada por la línea (si es un abono, la factura sale en negativo)")], requerido=True),
        Campo("cuenta", "Subcuenta", sugerencias=cuentas_para_listas, lista="cuentas", ayuda="Para «llevarla a una cuenta»: la subcuenta contra la que va el movimiento"),
        Campo("proveedor", "Proveedor del ticket", sugerencias=_proveedores, ayuda="Para «ticket»: un proveedor genérico (taxis, aparcamientos, manutención…); se busca por nombre, NIF o subcuenta"),
        Campo("gasto", "Subcuenta de gasto del ticket", sugerencias=cuentas_para_listas, lista="cuentas", ayuda="Déjela vacía para usar la del proveedor"),
        Campo("recordar", "Recordar para los conceptos como éste", "checkbox"),
    ]
    acciones_extra = [("Aplicar sugerencias", "accion/aplicar"), ("Pagar sin línea (socio)", "accion/sin_linea")]
    acciones_con_seleccion = [("Pagar vencimientos con las marcadas", "accion/pagar"), ("Crear factura con las marcadas", "accion/crear")]

    def texto_vacio(self, ctx, params):
        return "No hay líneas libres en el extracto del trimestre"

    def trimestre_de_trabajo(self, ctx):
        return trimestre.etiqueta_del_trimestre(trimestre.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio} · trabajando en {trimestre.etiqueta_del_trimestre(trimestre.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))}"

    def filas(self, ctx, params):
        filas = []
        de_pago = {}  # línea → la sugerencia de pago que la incluye: una línea que paga una factura pendiente no es «sin regla», se paga desde su sugerencia
        for sg in pagos_extracto.sugerir(ctx.sesion, ctx.ejercicio, trimestre.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)):
            for l in sg.lineas:
                de_pago.setdefault(l.id, sg)
        for p in svc.propuestas(ctx.sesion, ctx.empresa.id, _lineas_libres(ctx)):
            l, r = p.linea, p.regla
            sg = de_pago.get(l.id)
            if r is None and sg is not None:
                quien = pagos_extracto._nombre(sg.vencimientos[0]) if len(sg.vencimientos) == 1 else f"{len(sg.vencimientos)} vencimientos"
                propuesta, origen = f"Paga a {quien} (vencimiento del {sg.vencimientos[0].fecha:%d/%m/%Y}): confírmelo en «Sugerencias de pago»", "sugerencia de pago"
            else:
                propuesta, origen = (r.describir() if r else "— sin regla —"), ("" if r is None else ("manual" if r.origen == "manual" else f"aprendida ({r.veces})"))
            filas.append(Fila(f"l{l.id}", dict(banco=l.banco.nombre, fecha=l.fecha_valor or l.fecha, concepto=" · ".join(t for t in (l.texto, l.mas_datos) if t), importe=l.importe, propuesta=propuesta, origen=origen)))
        return filas

    def totales(self, filas):
        return {"importe": sum((f.valores["importe"] for f in filas), svc.CERO)}

    # ---- decidir una línea
    def _linea(self, ctx, id) -> ExtractoLinea:
        l = ctx.sesion.get(ExtractoLinea, int(str(id).lstrip("l"))) if str(id).lstrip("l").isdigit() else None
        if l is None or l.empresa_id != ctx.empresa.id:
            raise ErrorContable("La línea no existe")
        return l

    def cabecera_de_formulario(self, ctx, id):
        l = self._linea(ctx, id)
        dinero = f"{l.importe:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        return [("Banco", l.banco.nombre), ("Fecha", f"{(l.fecha_valor or l.fecha):%d/%m/%Y}"), ("Concepto", " · ".join(t for t in (l.texto, l.mas_datos) if t)), ("Importe", dinero)]

    def valores_formulario(self, ctx, id):
        l = self._linea(ctx, id)
        r = svc.regla_de(l, svc.reglas_manuales(ctx.sesion, ctx.empresa.id), svc.reglas_aprendidas(ctx.sesion, ctx.empresa.id))
        return {"tratamiento": r.tratamiento if r else "", "cuenta": r.cuenta.codigo if r and r.cuenta else "", "proveedor": r.tercero.nombre if r and r.tercero else "",
                "gasto": r.gasto.codigo if r and r.gasto else "", "recordar": False}

    def guardar(self, ctx, id, datos):
        l = self._linea(ctx, id)
        tratamiento = datos.get("tratamiento")
        cuenta, gasto, tercero = _cuenta(ctx, datos.get("cuenta")), _cuenta(ctx, datos.get("gasto")), None
        if gasto is not None and gasto.codigo[:1] not in trimestre.GRUPOS_DE_GASTO:
            raise ErrorContable(f"La subcuenta {gasto.codigo} ({gasto.nombre}) no es de gasto")
        if tratamiento == svc.TICKET:
            proveedores = list(ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == "P")))
            codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
            encontrados = _buscar_proveedor(proveedores, codigos, datos.get("proveedor") or "")
            if len(encontrados) != 1:
                raise ErrorContable("Elija el proveedor del ticket de la lista" if not encontrados else "Hay varios proveedores con ese nombre")
            tercero = encontrados[0]
        regla = svc.Regla(tratamiento or "", cuenta if tratamiento == svc.CUENTA else None, tercero, gasto if tratamiento == svc.TICKET else None)
        svc._comprobar(l, regla)
        if datos.get("recordar"):
            svc.recordar(ctx.sesion, ctx.empresa.id, l, regla.tratamiento, cuenta=regla.cuenta, tercero=regla.tercero, gasto=regla.gasto)
        svc.aplicar(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, [svc.Propuesta(l, regla)])
        return f"l{l.id}"

    # ---- aplicar las sugerencias de golpe
    def accion(self, ctx, accion, items):
        if accion == "pagar":
            return self._pagar(ctx, items)
        if accion == "sin_linea":
            return self._sin_linea(ctx, items)
        if accion == "crear":
            return self._crear(ctx, items)
        if accion != "aplicar":
            raise ErrorContable("Acción desconocida")
        prep = svc.preparar(ctx.sesion, ctx.ejercicio, svc.propuestas(ctx.sesion, ctx.empresa.id, _lineas_libres(ctx)))
        contexto = dict(preparadas=prep, resultado=None, errores=[])
        if items is None or not prep.aplicables:
            return "_lineas_sin_factura_aplicar.html", contexto
        elegidas = {int(v) for k, v in items if k == "linea" and isinstance(v, str) and v.isdigit()}
        marcadas = [p for p in prep.aplicables if p.linea.id in elegidas]
        if not marcadas:
            contexto["errores"] = ["Marque al menos una línea"]
            return "_lineas_sin_factura_aplicar.html", contexto
        try:
            contexto["resultado"] = svc.aplicar(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, marcadas)
            ctx.sesion.commit()
        except ErrorContable as e:
            ctx.sesion.rollback()
            contexto["errores"] = str(e).split(chr(10))
        return "_lineas_sin_factura_aplicar.html", contexto


    # ---- pagar vencimientos pendientes con las líneas marcadas
    def _pagar(self, ctx, items):
        """Con las líneas marcadas en la lista: elegir los vencimientos pendientes que pagan y ver el resumen (el mismo que en «Sugerencias de pago»)."""
        if items is None:
            raise ErrorContable("Marque primero las líneas del extracto")
        datos = {k: v for k, v in items if isinstance(v, str)}
        ids_l = [int(v[1:]) for k, v in items if k == "ids" and isinstance(v, str) and v[1:].isdigit()]
        ids_v = [int(v) for k, v in items if k == "venc" and isinstance(v, str) and v.isdigit()]
        lineas = [l for l in (ctx.sesion.get(ExtractoLinea, i) for i in ids_l) if l is not None and l.empresa_id == ctx.empresa.id]
        errores = []
        if not lineas:
            errores.append("Marque al menos una línea del extracto")
        elif datos.get("paso") == "resumen":
            if not ids_v:
                errores.append("Marque al menos un vencimiento pendiente")
            else:
                return ListadoConciliarPagos().formulario(ctx, "v" + "-".join(map(str, ids_v)) + "_l" + "-".join(str(l.id) for l in lineas))
        pendientes = pagos_extracto.vencimientos_a_pagar(ctx.sesion, ctx.ejercicio)
        total = sum((-l.importe for l in lineas), svc.CERO)
        return "_lineas_pagar.html", dict(lineas=lineas, total=total, vencimientos=[(v, pte, pagos_extracto._nombre(v)) for v, pte in pendientes], errores=errores)

    def _sin_linea(self, ctx, items):
        """Pagar vencimientos pendientes con un banco o cuenta de socio sin línea de extracto (lo que adelantó un socio con su dinero)."""
        contexto = dict(errores=[], hecho=None, bancos=[(int(i), n) for i, n in _opciones_de_bancos(ctx)])
        if items is not None:
            datos = {k: v for k, v in items if isinstance(v, str)}
            ids_v = [int(v) for k, v in items if k == "venc" and isinstance(v, str) and v.isdigit()]
            try:
                banco = ctx.sesion.get(Banco, int(datos["banco"])) if datos.get("banco", "").isdigit() else None
                if banco is None or banco.empresa_id != ctx.empresa.id:
                    raise ErrorContable("Elija el banco o la cuenta de socio que pagó")
                fecha = introducir_fecha(datos["fecha"], ctx.ejercicio) if datos.get("fecha", "").strip() else None
                vencimientos = [v for v in (ctx.sesion.get(Vencimiento, i) for i in ids_v) if v is not None]
                contexto["hecho"] = dict(n=pagos_extracto.pagar_con_banco(ctx.sesion, ctx.ejercicio, vencimientos, banco, fecha).movimientos, banco=banco.nombre)
                ctx.sesion.commit()
            except ErrorContable as ex:
                ctx.sesion.rollback()
                contexto["errores"] = [str(ex)]
        contexto["vencimientos"] = [(v, pte, pagos_extracto._nombre(v)) for v, pte in pagos_extracto.vencimientos_a_pagar(ctx.sesion, ctx.ejercicio)]
        return "_pagar_sin_linea.html", contexto

    def _crear(self, ctx, items):
        """Con las líneas marcadas: dar de alta la factura recibida que pagan (su total es lo que suman, con el IVA incluido) y dejarla pagada con ellas."""
        if items is None:
            raise ErrorContable("Marque primero las líneas del extracto")
        datos = {k: v for k, v in items if isinstance(v, str)}
        ids_l = [int(v[1:]) for k, v in items if k == "ids" and isinstance(v, str) and v[1:].isdigit()]
        lineas = [l for l in (ctx.sesion.get(ExtractoLinea, i) for i in ids_l) if l is not None and l.empresa_id == ctx.empresa.id]
        errores, hecho = [], None
        total = sum((-l.importe for l in lineas), svc.CERO)
        if not lineas:
            errores.append("Marque al menos una línea del extracto")
        regla = svc.regla_de(lineas[0], svc.reglas_manuales(ctx.sesion, ctx.empresa.id), svc.reglas_aprendidas(ctx.sesion, ctx.empresa.id)) if lineas else None
        valores = dict(proveedor=datos.get("proveedor", regla.tercero.nombre if regla and regla.tercero else ""), numero=datos.get("numero", ""),
                       fecha=datos.get("fecha", fecha_texto(min((l.fecha_valor or l.fecha) for l in lineas)) if lineas else ""), iva=datos.get("iva", texto_dinero(svc.IVA_DE_LOS_TICKETS)),
                       gasto=datos.get("gasto", regla.gasto.codigo if regla and regla.gasto else ""))
        if lineas and datos.get("paso") == "crear":
            try:
                proveedores = list(ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == "P")))
                codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
                encontrados = _buscar_proveedor(proveedores, codigos, valores["proveedor"])
                if len(encontrados) != 1:
                    raise ErrorContable("Elija el proveedor de la lista" if not encontrados else "Hay varios proveedores con ese nombre: elija uno de la lista")
                gasto = _cuenta(ctx, valores["gasto"])
                if gasto is not None and gasto.codigo[:1] not in trimestre.GRUPOS_DE_GASTO:
                    raise ErrorContable(f"La subcuenta {gasto.codigo} ({gasto.nombre}) no es de gasto")
                iva = dinero_opcional(valores["iva"], "% de IVA")
                if iva is None or not 0 <= iva <= 100:
                    raise ErrorContable("El % de IVA tiene que estar entre 0 y 100")
                fecha = introducir_fecha(valores["fecha"], ctx.ejercicio)
                factura = svc.crear_factura(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, lineas, encontrados[0], valores["numero"], fecha, iva, gasto)
                ctx.sesion.commit()
                hecho = dict(numero=factura.numero_factura, proveedor=encontrados[0].nombre, total=total, lineas=len(lineas))
            except (ErrorContable, ValueError) as ex:
                ctx.sesion.rollback()
                errores.append(str(ex))
                lineas = [l for l in (ctx.sesion.get(ExtractoLinea, i) for i in ids_l) if l is not None]
        return "_lineas_crear.html", dict(lineas=lineas, total=total, valores=valores, errores=errores, hecho=hecho, proveedores=_proveedores(ctx), cuentas=cuentas_para_listas(ctx))
