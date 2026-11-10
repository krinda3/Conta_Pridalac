"""Conciliación de facturas con el extracto, en la web: la lista de trabajo del trimestre (`servicios/trimestre.py`) con la línea del banco que propone el motor para cada factura."""
from __future__ import annotations

from sqlalchemy import func, select

from conta_pridalac.db.modelos import Banco, CorrespondenciaTercero, Cuenta, ExtractoLinea, Factura, FacturaTrimestre, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import introducir_fecha
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.servicios import pagos_extracto
from conta_pridalac.servicios import trimestre as svc
from conta_pridalac.servicios.importar_facturas import normalizar_nif
from conta_pridalac.web.comun import cuentas_para_listas, texto_dinero
from conta_pridalac.web.extractos import _opciones_de_bancos
from conta_pridalac.web.listados import Campo, Col, Fila, Listado

MAX_BYTES = 10 * 1024 * 1024
REGLAS = {
    "importe_y_texto": "Misma cantidad y el nombre coincide", "importe_unico": "Cantidad con céntimos que sólo tiene un movimiento", "importe_y_fecha": "Misma cantidad el mismo día",
    "varias_facturas_un_cargo": "Varias facturas en un solo cargo (confirmar)", "dos_pagos": "Pagada en dos veces (confirmar)",
}
A_CONFIRMAR = ("varias_facturas_un_cargo", "dos_pagos")


SEPARADOR = " · "


def _texto_de_proveedor(t: Tercero, codigos: dict[int, str]) -> str:
    """«NOMBRE · nombre comercial · NIF · subcuenta»: todo en una sola cadena, para que la lista del navegador encuentre al proveedor por cualquiera de esas partes."""
    comercial = (t.comercial or "").strip()
    partes = [t.nombre.strip(), comercial if comercial and comercial.lower() != t.nombre.strip().lower() else "", (t.nif or "").strip(), codigos.get(t.cuenta_id, "")]
    return SEPARADOR.join(p for p in partes if p)


def _buscar_proveedor(proveedores: list[Tercero], codigos: dict[int, str], escrito: str) -> list[Tercero]:
    """El proveedor que se ha escrito o elegido de la lista: por su nombre, su nombre comercial, su NIF o su subcuenta (la cadena de la lista lleva todo junto, separado por « · »)."""
    escrito = escrito.strip()
    if not escrito:
        return []
    trozos = [escrito] + [p.strip() for p in escrito.split(SEPARADOR) if p.strip()]
    for trozo in trozos:
        por_nombre = [t for t in proveedores if t.nombre.strip().lower() == trozo.lower()]
        if por_nombre:
            return por_nombre
    for trozo in trozos:
        encontrados = [t for t in proveedores if (t.comercial or "").strip().lower() == trozo.lower() or (t.nif and normalizar_nif(t.nif) == normalizar_nif(trozo)) or codigos.get(t.cuenta_id) == trozo]
        if encontrados:
            return encontrados
    return []


def _proveedores(ctx) -> list[tuple[str, str]]:
    """Los proveedores de Conta, para elegir uno."""
    codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
    return [(_texto_de_proveedor(t, codigos), "") for t in ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == "P").order_by(Tercero.nombre))]


def _proveedor_de_conta(ctx, fac: FacturaTrimestre) -> tuple[str, str]:
    """(proveedor, subcuenta de gasto) que le tocan a la factura en Conta, o el aviso de que falta decidir."""
    prov = svc.resolver_proveedor(ctx.sesion, fac)
    if prov.tercero is None:
        return ("Nuevo: se creará" if fac.crear_proveedor else "⚠ Nuevo: elegir proveedor"), ""
    cuenta = ctx.sesion.get(Cuenta, prov.cuenta_gasto_id or prov.tercero.cuenta_gasto_id) if (prov.cuenta_gasto_id or prov.tercero.cuenta_gasto_id) else None
    return prov.tercero.nombre, cuenta.codigo if cuenta else ""


def _movimiento(lineas) -> dict:
    """Banco, fecha de pago, concepto e importe de las líneas del extracto que pagan una factura."""
    return dict(banco=" + ".join(dict.fromkeys(l.banco.nombre for l in lineas)), pago=lineas[0].fecha_valor or lineas[0].fecha, concepto=" · ".join(l.texto for l in lineas),
                importe=sum((l.importe for l in lineas), svc.CERO))


class ListadoConciliacion(Listado):
    nombre, titulo = "conciliacion", "Recibidas del trimestre"
    descripcion = ("La lista de trabajo del trimestre: las facturas recibidas que ha reconocido Verifactu («Cargar facturas»), cada una con el movimiento del extracto que parece haberla pagado. "
                   "Las dudosas y las que no tienen movimiento se señalan; debajo salen los movimientos del extracto que no corresponden a ninguna factura. «Aplicar propuestas» crea la factura con su pago; «Contabilizar el resto» deja las demás como pendientes de pago.")
    columnas = [
        Col("estado", "Estado", TEXTO, 1.5), Col("fecha", "Fecha factura", FECHA, 1.1), Col("nombre", "Proveedor (Verifactu)", TEXTO, 3), Col("proveedor", "Proveedor en Conta", TEXTO, 2.6), Col("gasto", "Gasto", TEXTO, 1.2), Col("numero", "Nº factura", TEXTO, 1.6),
        Col("total", "Total", DINERO, 1.2),
        Col("banco", "Banco", TEXTO, 1.8), Col("pago", "Fecha pago", FECHA, 1.1), Col("concepto", "Concepto del banco", TEXTO, 3.5), Col("importe", "Importe banco", DINERO, 1.2), Col("motivo", "Por qué", TEXTO, 3),
    ]
    borrar = editable = True
    campos = [
        Campo("numero", "Nº de factura", ayuda="Cámbielo si Verifactu no lo ha reconocido (por ejemplo «No reconocido») o si choca con una factura que ya existe"),
        Campo("proveedor", "Proveedor de Conta", sugerencias=_proveedores, ayuda="Escriba o elija el proveedor de Conta al que va esta factura (por ejemplo, un genérico de tickets): su nombre, su nombre comercial, su NIF o su subcuenta; la lista busca en todo eso"),
        Campo("crear", "Crear el proveedor nuevo con los datos de Verifactu", "checkbox"),
        Campo("gasto", "Subcuenta de gasto", sugerencias=cuentas_para_listas, lista="cuentas", ayuda="Déjela vacía para usar la del proveedor"),
        Campo("recordar", "Recordar el proveedor para el NIF de Verifactu en esta y en las próximas cargas (la subcuenta de gasto no se recuerda)", "checkbox"),
        Campo("pagador", "Pagada por", "select", opciones=lambda ctx: [("", "— se busca en el extracto —")] + _opciones_de_bancos(ctx), seccion="Pago",
              ayuda="Para lo que pagó un socio con su dinero (sin movimiento en el extracto): se contabiliza con un pago de su cuenta"),
        Campo("fecha_pago", "Fecha del pago", "fecha", ayuda="Si se deja vacía, la de la factura"),
        Campo("base", "Base imponible", "dinero", seccion="Importes (sólo si Verifactu los ha leído mal)", ayuda="La base y la cuota de IVA tienen que sumar el total de la factura"),
        Campo("pct_iva", "% de IVA", "dinero"),
        Campo("cuota_iva", "Cuota de IVA", "dinero"),
    ]
    sentido, clase_tercero, cobrada = "R", "P", "pagada"
    parametros = [Campo("ver", "Ver", "select", opciones=[("pendientes", "Pendientes"), ("hechas", "Hechas"), ("todas", "Todas")], defecto="pendientes")]
    acciones_extra = [("⇪ Cargar facturas", "accion/cargar"), ("Pagadas por el socio", "accion/socio"), ("Quitar duplicadas", "accion/duplicadas"), ("Aplicar propuestas", "accion/aplicar"), ("Contabilizar el resto", "accion/pendientes"), ("Enlazar con el extracto", "accion/enlazar")]

    def texto_vacio(self, ctx, params):
        return "La lista de trabajo está vacía: use «Cargar facturas» con el Excel de recibidas de Verifactu"

    def _hechas(self, ctx) -> list[Fila]:
        """Las facturas de la lista que ya están contabilizadas, con lo que se hizo: su pago (línea del extracto o socio) o «pendiente de pago»."""
        lineas: dict[int, list] = {}
        for l in ctx.sesion.scalars(select(ExtractoLinea).where(ExtractoLinea.empresa_id == ctx.empresa.id, ExtractoLinea.movimiento_id.is_not(None))):
            lineas.setdefault(l.movimiento_id, []).append(l)
        salida = []
        consulta = select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == ctx.empresa.id, FacturaTrimestre.sentido == self.sentido, FacturaTrimestre.factura_id.is_not(None),
                                                  FacturaTrimestre.descartada.is_(False)).order_by(FacturaTrimestre.fecha_factura, FacturaTrimestre.id)
        periodo = svc.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id, self.sentido)
        if periodo is None:
            return []
        consulta = consulta.where(FacturaTrimestre.fecha_factura >= periodo[0], FacturaTrimestre.fecha_factura <= periodo[1])  # sólo el trimestre en que se trabaja
        for fac in ctx.sesion.scalars(consulta):
            factura = ctx.sesion.get(Factura, fac.factura_id)
            pagos = [p for v in ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == fac.factura_id)) for p in v.pagos]
            pagos.sort(key=lambda p: (p.movimiento.fecha, p.movimiento.numero))
            valores = dict(estado="Hecha", fecha=fac.fecha_factura, nombre=fac.nombre, proveedor=factura.tercero.nombre if factura and factura.tercero else "", gasto="", numero=fac.numero_factura,
                           total=fac.total, banco="", pago=None, concepto="", importe=None, motivo="")
            if not pagos:
                valores["motivo"] = "Contabilizada, pendiente de " + ("cobro" if self.sentido == "E" else "pago")
            else:
                con_linea = [l for p in pagos for l in lineas.get(p.movimiento_id, [])]
                valores.update(banco=" + ".join(dict.fromkeys(p.movimiento.banco.nombre for p in pagos)), pago=pagos[0].movimiento.fecha,
                               concepto=" · ".join(l.texto for l in con_linea) if con_linea else "Sin línea de extracto (pago del socio o a mano)",
                               importe=sum((p.importe for p in pagos), svc.CERO), motivo=f"Contabilizada y {self.cobrada}")
            salida.append(Fila(None, valores, borrable=False))
        return salida

    def filas(self, ctx, params):
        ver = params.get("ver") or "pendientes"
        if ver == "hechas":
            return self._hechas(ctx)
        pendientes = self._pendientes(ctx)
        return pendientes + self._hechas(ctx) if ver == "todas" else pendientes

    def _pendientes(self, ctx):
        p = svc.proponer(ctx.sesion, ctx.empresa.id, sentido=self.sentido)
        r = p.resultado
        vacio = dict(banco="", pago=None, concepto="", importe=None, motivo="", proveedor="", gasto="")

        def fila(f, estado, clase="", **resto):
            fac = p.facturas[f.id]
            proveedor, gasto = _proveedor_de_conta(ctx, fac)
            return fac, Fila(f"f{f.id}", {**vacio, "estado": estado, "fecha": fac.fecha_factura, "nombre": fac.nombre, "proveedor": proveedor, "gasto": gasto, "numero": fac.numero_factura, "total": fac.total, **resto},
                             clase=clase)

        con_fila = []
        for e in r.emparejadas:
            dudoso = e.regla in A_CONFIRMAR
            movimiento = _movimiento([p.lineas[l.id] for l in e.lineas])
            for f in e.facturas:
                datos, motivo = dict(movimiento), REGLAS.get(e.regla, e.regla)
                if e.regla == "varias_facturas_un_cargo":  # el cargo es uno solo: en cada factura se ve lo que le toca, y en el motivo el total del cargo
                    datos["importe"] = f.total if self.sentido == "E" else -f.total
                    motivo = f"Un solo {'ingreso' if self.sentido == 'E' else 'cargo'} de {texto_dinero(abs(movimiento['importe']))} € para {len(e.facturas)} facturas: confirme el reparto"
                con_fila.append(fila(f, "Revisar" if dudoso else "Propuesta", "aviso-fila" if dudoso else "", motivo=motivo, **datos))
        for d in r.dudosas:
            candidata = [p.lineas[d.candidatas[0].id]] if d.candidatas else None
            con_fila.append(fila(d.factura, "Dudosa", "aviso-fila", motivo=d.motivo, **(_movimiento(candidata) if candidata else {})))
        for f in r.sin_conciliar:
            con_fila.append(fila(f, "Sin movimiento", motivo="Ningún movimiento del extracto encaja: ¿lo pagó el socio o falta el extracto?" if self.sentido == "R" else "Ningún ingreso del extracto encaja: ¿todavía no se ha cobrado?"))
        for f in p.pagadas_por_banco:
            banco = ctx.sesion.get(Banco, f.pagada_por_id)
            proveedor, gasto = _proveedor_de_conta(ctx, f)
            con_fila.append((f, Fila(f"f{f.id}", {**vacio, "estado": "Pagada por socio", "fecha": f.fecha_factura, "nombre": f.nombre, "proveedor": proveedor, "gasto": gasto, "numero": f.numero_factura,
                                                  "total": f.total, "banco": banco.nombre if banco else "", "pago": f.pagada_fecha or f.fecha_factura, "concepto": "Sin extracto: pagada con el dinero del socio",
                                                  "importe": -f.total, "motivo": "Elegido por usted: se contabiliza con un pago de su cuenta"})))
        for copia_id, original in p.duplicadas.items():
            copia = ctx.sesion.get(FacturaTrimestre, copia_id)
            motivo = f"Parece la misma que la del {original.fecha_factura:%d/%m/%Y} (nº {original.numero_factura or '—'}): Verifactu la reconoció dos veces, factura y justificante de pago"
            con_fila.append((copia, Fila(f"f{copia.id}", {**vacio, "estado": "Duplicada", "fecha": copia.fecha_factura, "nombre": copia.nombre, "numero": copia.numero_factura, "total": copia.total, "motivo": motivo},
                                         clase="aviso-fila")))
        con_fila.sort(key=lambda x: (x[0].fecha_factura, x[0].id))
        salida = [f for _, f in con_fila]
        for l in (r.libres if self.sentido == "R" else []):  # las líneas sin factura de las emitidas se ven en «Líneas sin factura»
            lin = p.lineas[l.id]
            salida.append(Fila(None, {**vacio, "estado": "Sin factura", "fecha": None, "nombre": "", "numero": "", "total": None, "banco": lin.banco.nombre, "pago": lin.fecha_valor or lin.fecha,
                                      "concepto": " · ".join(t for t in (lin.texto, lin.mas_datos) if t), "importe": lin.importe, "motivo": "Movimiento del extracto sin factura"}, clase="suave", borrable=False))
        return salida

    def trimestre_de_trabajo(self, ctx):
        return svc.etiqueta_del_trimestre(svc.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id, self.sentido))

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio} · trabajando en {svc.etiqueta_del_trimestre(svc.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id, self.sentido))}"

    def _factura(self, ctx, id) -> FacturaTrimestre:
        f = ctx.sesion.get(FacturaTrimestre, int(str(id).lstrip("f"))) if str(id).lstrip("f").isdigit() else None
        if f is None or f.empresa_id != ctx.empresa.id:
            raise ErrorContable("La factura no está en la lista de trabajo")
        return f

    def cabecera_de_formulario(self, ctx, id):
        f = self._factura(ctx, id)
        dinero = f"{f.total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        return [("Proveedor (Verifactu)", f"{f.nombre} {f.nif}".strip()), ("Factura", f"{f.numero_factura or '—'} · {f.fecha_factura:%d/%m/%Y}"), ("Total", dinero)]

    def enlaces_de_formulario(self, ctx, id):
        f = self._factura(ctx, id)
        return [("Ver el PDF de la factura", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/conciliacion/pdf/{f.id}")] if f.ruta_pdf else []

    def valores_formulario(self, ctx, id):
        f = self._factura(ctx, id)
        prov = svc.resolver_proveedor(ctx.sesion, f)
        cuenta = ctx.sesion.get(Cuenta, f.cuenta_gasto_id) if f.cuenta_gasto_id else None
        return {"numero": f.numero_factura, "proveedor": prov.tercero.nombre if prov.tercero else "", "crear": f.crear_proveedor, "gasto": cuenta.codigo if cuenta else "", "recordar": False,
                "pagador": str(f.pagada_por_id) if f.pagada_por_id else "", "fecha_pago": f.pagada_fecha.strftime("%d/%m/%Y") if f.pagada_fecha else "",
                "base": f.base, "pct_iva": f.porcentaje_iva, "cuota_iva": f.cuota_iva}

    def guardar(self, ctx, id, datos):
        f = self._factura(ctx, id)
        if datos.get("numero") and datos["numero"].strip() != (f.numero_factura or "").strip():
            f.numero_factura = datos["numero"].strip()[:60]
        for campo, atributo in (("base", "base"), ("pct_iva", "porcentaje_iva"), ("cuota_iva", "cuota_iva")):  # los importes se corrigen si se teclean; vacío = como vinieron
            if datos.get(campo) is not None:
                setattr(f, atributo, datos[campo])
        tercero = None
        if datos.get("proveedor"):
            proveedores = list(ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == self.clase_tercero)))
            codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
            escrito = datos["proveedor"].strip()
            coinciden = _buscar_proveedor(proveedores, codigos, escrito)  # su nombre, su nombre comercial, su NIF o su subcuenta
            if not coinciden:
                raise ErrorContable(f"No hay ningún proveedor llamado «{datos['proveedor']}», ni con ese NIF ni con esa subcuenta: elíjalo de la lista")
            if len(coinciden) > 1:
                raise ErrorContable(f"Hay {len(coinciden)} proveedores llamados «{datos['proveedor']}»")
            tercero = coinciden[0]
        cuenta = None
        if datos.get("gasto"):
            cuenta = ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo == datos["gasto"])).first()
            if cuenta is None:
                raise ErrorContable(f"La subcuenta {datos['gasto']} no existe en el plan de cuentas")
        banco = None
        if datos.get("pagador"):
            banco = ctx.sesion.get(Banco, int(datos["pagador"]))
            if banco is None or banco.empresa_id != ctx.empresa.id:
                raise ErrorContable("El banco o la cuenta de socio elegidos no existen")
        decide_proveedor = tercero is not None or datos.get("crear")
        if decide_proveedor:
            svc.fijar_proveedor(ctx.sesion, f, tercero=tercero, cuenta_gasto=cuenta, crear=bool(datos.get("crear")), recordar=bool(datos.get("recordar")))
        elif banco is None:  # no se ha decidido nada
            raise ErrorContable("Elija el proveedor de Conta, marque «crear el proveedor nuevo» o diga quién pagó la factura" if self.sentido == "R" else "Elija el cliente de Conta o marque «crear el cliente nuevo»")
        svc.marcar_pagadas_por(ctx.sesion, ctx.empresa.id, [f.id], banco, datos.get("fecha_pago"))
        return f"f{f.id}"

    def eliminar(self, ctx, ids):
        svc.descartar(ctx.sesion, ctx.empresa.id, [int(i[1:]) for i in ids if i.startswith("f")])

    def accion(self, ctx, accion, items):
        if accion == "duplicadas":
            return self._quitar_duplicadas(ctx, items)
        if accion == "aplicar":
            return self._aplicar(ctx, items)
        if accion == "socio":
            return self._pagadas_por_el_socio(ctx, items)
        if accion == "pendientes":
            return self._contabilizar_el_resto(ctx, items)
        if accion == "enlazar":
            return self._enlazar(ctx, items)
        if accion != "cargar":
            raise ErrorContable("Acción desconocida")
        contexto = dict(errores=[], resultado=None)
        if items is None:
            return "_trimestre_cargar.html", contexto
        fichero = next((v for k, v in items if k == "fichero" and getattr(v, "filename", "")), None)
        try:
            if fichero is None:
                raise ErrorContable("Elija el Excel de facturas recibidas de Verifactu" if self.sentido == "R" else "Elija el Excel de facturas emitidas de Verifactu")
            contenido = fichero.file.read()
            if len(contenido) > MAX_BYTES:
                raise ErrorContable("El Excel pesa más de 10 MB")
            contexto["resultado"] = self._cargar(ctx, fichero.filename, contenido)
            ctx.sesion.commit()
        except ErrorContable as e:
            ctx.sesion.rollback()
            contexto["errores"] = [str(e)]
        return "_trimestre_cargar.html", contexto

    def _enlazar(self, ctx, items):
        """Primero enseña qué líneas del extracto son ya movimientos contabilizados (mismo banco, importe y día); al confirmar, las enlaza. No toca ningún asiento."""
        periodo = svc.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id, self.sentido)  # sólo las líneas del trimestre de trabajo
        previsto = pagos_extracto.enlazables(ctx.sesion, ctx.empresa.id, periodo)
        contexto = dict(previsto=previsto, hecho=None)
        if items is not None and previsto.pares:
            contexto["hecho"] = pagos_extracto.enlazar(ctx.sesion, ctx.empresa.id, periodo)
            ctx.sesion.commit()
        return "_enlazar_extracto.html", contexto

    def _cargar(self, ctx, fichero, contenido):
        return svc.cargar_recibidas(ctx.sesion, ctx.empresa.id, fichero, contenido)

    def _aplicar(self, ctx, items):
        """Primero cuenta lo que se aplicaría y lo que se deja fuera; al confirmar, crea las facturas y sus pagos de golpe."""
        preparadas = svc.preparar(ctx.sesion, ctx.ejercicio, svc.proponer(ctx.sesion, ctx.empresa.id, sentido=self.sentido))
        contexto = dict(preparadas=preparadas, resultado=None, errores=[])
        if items is None or not preparadas.aplicables:
            return "_trimestre_aplicar.html", contexto
        try:
            contexto["resultado"] = svc.aplicar(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, preparadas.aplicables)
            ctx.sesion.commit()
        except ErrorContable as e:
            ctx.sesion.rollback()
            contexto["errores"] = str(e).split("\n")
        return "_trimestre_aplicar.html", contexto

    def _contabilizar_el_resto(self, ctx, items):
        """Lo que no tiene pago se contabiliza con su vencimiento pendiente: la lista de Vencimientos pendientes pasa a ser la comprobación final."""
        preparadas = svc.preparar_pendientes(ctx.sesion, ctx.ejercicio, svc.proponer(ctx.sesion, ctx.empresa.id, sentido=self.sentido))
        contexto = dict(preparadas=preparadas, resultado=None, errores=[])
        if items is None or not preparadas.aplicables:
            return "_trimestre_pendientes.html", contexto
        try:
            contexto["resultado"] = svc.aplicar(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, preparadas.aplicables)
            ctx.sesion.commit()
        except ErrorContable as e:
            ctx.sesion.rollback()
            contexto["errores"] = str(e).split(chr(10))
        return "_trimestre_pendientes.html", contexto

    def _pagadas_por_el_socio(self, ctx, items):
        """Enseña las facturas que no tienen movimiento en el extracto y deja marcar las que pagó un socio con su dinero, con el banco o cuenta y el día del pago."""
        bancos = [(int(i), n) for i, n in _opciones_de_bancos(ctx)]
        contexto = dict(facturas=[], bancos=bancos, errores=[], hecho=None)
        if items is not None:
            datos = {k: v for k, v in items if isinstance(v, str)}
            ids = [int(v) for k, v in items if k == "factura" and isinstance(v, str) and v.isdigit()]
            try:
                banco = ctx.sesion.get(Banco, int(datos["banco"])) if datos.get("banco", "").isdigit() else None
                if banco is None or banco.empresa_id != ctx.empresa.id:
                    raise ErrorContable("Elija el banco o la cuenta de socio que pagó")
                if not ids:
                    raise ErrorContable("Marque las facturas que pagó")
                fecha = introducir_fecha(datos["fecha"], ctx.ejercicio) if datos.get("fecha", "").strip() else None
                contexto["hecho"] = dict(n=svc.marcar_pagadas_por(ctx.sesion, ctx.empresa.id, ids, banco, fecha), banco=banco.nombre)
                ctx.sesion.commit()
            except ErrorContable as e:
                ctx.sesion.rollback()
                contexto["errores"] = [str(e)]
        if not contexto["hecho"]:
            p = svc.proponer(ctx.sesion, ctx.empresa.id, sentido=self.sentido)
            contexto["facturas"] = sorted((p.facturas[f.id] for f in p.resultado.sin_conciliar), key=lambda x: (x.fecha_factura, x.id))
        return "_trimestre_socio.html", contexto

    def _quitar_duplicadas(self, ctx, items):
        """Primero enseña las parejas y pide confirmación; al confirmar, descarta las copias (el original se queda)."""
        if items is None:
            p = svc.proponer(ctx.sesion, ctx.empresa.id, sentido=self.sentido)
            parejas = [(ctx.sesion.get(FacturaTrimestre, c), o) for c, o in p.duplicadas.items()]
            return "_trimestre_duplicadas.html", dict(parejas=parejas, quitadas=None)
        quitadas = svc.quitar_duplicadas(ctx.sesion, ctx.empresa.id)
        ctx.sesion.commit()
        return "_trimestre_duplicadas.html", dict(parejas=[], quitadas=quitadas)


class ListadoCorrespondencias(Listado):
    nombre, titulo = "correspondencias", "Correspondencias de proveedor"
    descripcion = ("Lo que se ha guardado con «Recordar» en la conciliación: cuando Verifactu trae un NIF, la factura va a ese proveedor de Conta. Si un NIF no debe ir siempre al mismo proveedor "
                   "(por ejemplo, una cadena con parking y restaurante), bórrelo aquí y elija el proveedor factura a factura.")
    columnas = [Col("nif", "NIF de Verifactu", TEXTO, 1.6), Col("proveedor", "Proveedor de Conta", TEXTO, 3.5), Col("nif_conta", "NIF en Conta", TEXTO, 1.6), Col("cuenta", "Subcuenta", TEXTO, 1.2),
                Col("gasto", "Gasto propio", TEXTO, 1.2), Col("pendientes", "Facturas en la lista", TEXTO, 1.3)]
    borrar = True

    def texto_vacio(self, ctx, params):
        return "No hay correspondencias guardadas"

    def filas(self, ctx, params):
        codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
        en_lista: dict[str, int] = {}
        for f in svc.facturas_pendientes(ctx.sesion, ctx.empresa.id):
            en_lista[normalizar_nif(f.nif)] = en_lista.get(normalizar_nif(f.nif), 0) + 1
        filas = []
        for c in ctx.sesion.scalars(select(CorrespondenciaTercero).where(CorrespondenciaTercero.empresa_id == ctx.empresa.id).order_by(CorrespondenciaTercero.nif)):
            filas.append(Fila(str(c.id), dict(nif=c.nif, proveedor=c.tercero.nombre, nif_conta=c.tercero.nif or "", cuenta=codigos.get(c.tercero.cuenta_id, ""), gasto=codigos.get(c.cuenta_gasto_id, "") if c.cuenta_gasto_id else "",
                                              pendientes=str(en_lista.get(c.nif, 0))), clase="aviso-fila" if c.cuenta_gasto_id else ""))
        return filas

    def eliminar(self, ctx, ids):
        for c in ctx.sesion.scalars(select(CorrespondenciaTercero).where(CorrespondenciaTercero.empresa_id == ctx.empresa.id, CorrespondenciaTercero.id.in_([int(i) for i in ids]))):
            ctx.sesion.delete(c)


def _clientes(ctx) -> list[tuple[str, str]]:
    """Los clientes de Conta, para elegir uno."""
    codigos = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
    return [(_texto_de_proveedor(t, codigos), "") for t in ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == "C").order_by(Tercero.nombre))]


class ListadoEmitidas(ListadoConciliacion):
    nombre, titulo = "emitidas-trimestre", "Emitidas del trimestre"
    descripcion = ("Las facturas emitidas que ha sacado Verifactu («Cargar emitidas»: un Excel por empresa), cada una con el ingreso del extracto que parece ser su cobro. Las que Conta ya tiene contabilizadas "
                   "(las del programa anterior, por ejemplo) no se repiten: salen en «Hechas». «Aplicar propuestas» crea las facturas nuevas con su cobro; «Contabilizar el resto» deja las demás como pendientes de cobro.")
    sentido, clase_tercero, cobrada = "E", "C", "cobrada"
    columnas = [
        Col("estado", "Estado", TEXTO, 1.5), Col("fecha", "Fecha factura", FECHA, 1.1), Col("nombre", "Cliente (Verifactu)", TEXTO, 3), Col("proveedor", "Cliente en Conta", TEXTO, 2.6), Col("gasto", "Ingreso", TEXTO, 1.2),
        Col("numero", "Nº factura", TEXTO, 1.6), Col("total", "Total", DINERO, 1.2), Col("banco", "Banco", TEXTO, 1.8), Col("pago", "Fecha cobro", FECHA, 1.1), Col("concepto", "Concepto del banco", TEXTO, 3.5),
        Col("importe", "Importe banco", DINERO, 1.2), Col("motivo", "Por qué", TEXTO, 3),
    ]
    campos = [
        Campo("numero", "Nº de factura", ayuda="Cámbielo si choca con una factura que ya existe"),
        Campo("proveedor", "Cliente de Conta", sugerencias=_clientes, ayuda="Escriba o elija el cliente de Conta al que va esta factura: su nombre, su nombre comercial, su NIF o su subcuenta"),
        Campo("crear", "Crear el cliente nuevo con los datos de Verifactu", "checkbox"),
        Campo("gasto", "Subcuenta de ingreso", sugerencias=cuentas_para_listas, lista="cuentas", ayuda="Déjela vacía para usar la del cliente"),
        Campo("recordar", "Recordar el cliente para el NIF de Verifactu en esta y en las próximas cargas (la subcuenta de ingreso no se recuerda)", "checkbox"),
        Campo("base", "Base imponible", "dinero", seccion="Importes (sólo si Verifactu los ha leído mal)", ayuda="La base y la cuota de IVA tienen que sumar el total de la factura"),
        Campo("pct_iva", "% de IVA", "dinero"),
        Campo("cuota_iva", "Cuota de IVA", "dinero"),
    ]
    acciones_extra = [("⇪ Cargar emitidas", "accion/cargar"), ("Aplicar propuestas", "accion/aplicar"), ("Contabilizar el resto", "accion/pendientes"), ("Enlazar con el extracto", "accion/enlazar")]

    def texto_vacio(self, ctx, params):
        return "La lista de trabajo está vacía: use «Cargar emitidas» con el Excel de facturas emitidas de Verifactu"

    def cabecera_de_formulario(self, ctx, id):
        f = self._factura(ctx, id)
        dinero = f"{f.total:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        return [("Cliente (Verifactu)", f"{f.nombre} {f.nif}".strip()), ("Factura", f"{f.numero_factura or '—'} · {f.fecha_factura:%d/%m/%Y}"), ("Total", dinero)]

    def enlaces_de_formulario(self, ctx, id):
        return []

    def _cargar(self, ctx, fichero, contenido):
        return svc.cargar_emitidas(ctx.sesion, ctx.empresa.id, fichero, contenido)
