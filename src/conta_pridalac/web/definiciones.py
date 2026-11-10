"""Definición de los listados de la aplicación (cada uno declara columnas, campos y servicios; el comportamiento es común)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select

from conta_pridalac.db.modelos import Adjunto, Apunte, Asiento, Cuenta, Factura, FormaPago, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.pgc import nombre_pgc
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, PORCENTAJE, TEXTO, Columna, Tabla, formatear
from conta_pridalac.servicios import cuentas as svc_cuentas
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, libro_iva, mayor_general
from conta_pridalac.web.comun import cuentas_para_listas
from conta_pridalac.web.listados import Campo, Col, Contexto, Detalle, Fila, Listado

CERO = Decimal("0.00")


def _sumas(filas: list[Fila], *claves: str) -> dict:
    return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in claves}


# ------------------------------------------------------------------------------------------------ plan de cuentas


class ListadoCuentas(Listado):
    nombre, titulo = "cuentas", "Plan de cuentas"
    descripcion = "Subcuentas con sus sumas del ejercicio. Doble clic para editar."
    columnas = [
        Col("codigo", "Cuenta", TEXTO, 1), Col("nombre", "Nombre", TEXTO, 4), Col("subgrupo", "Subgrupo PGC", TEXTO, 3),
        Col("debe", "Debe", DINERO, 1.3), Col("haber", "Haber", DINERO, 1.3), Col("saldo", "Saldo", DINERO, 1.3), Col("usos", "Apuntes", ENTERO, 0.8),
    ]
    campos = [Campo("codigo", "Código de la subcuenta", requerido=True), Campo("nombre", "Nombre", requerido=True)]
    anadir = borrar = editable = True

    def filas(self, ctx, params):
        sumas = {
            codigo: (debe or CERO, haber or CERO, n)
            for codigo, debe, haber, n in ctx.sesion.execute(
                select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber), func.count(Apunte.id))
                .join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
                .where(Cuenta.empresa_id == ctx.empresa.id, Asiento.ejercicio_id == ctx.ejercicio.id).group_by(Cuenta.codigo)
            )
        }
        filas = []
        for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id).order_by(Cuenta.codigo)):
            debe, haber, n = sumas.get(c.codigo, (CERO, CERO, 0))
            filas.append(Fila(str(c.id), dict(codigo=c.codigo, nombre=c.nombre, subgrupo=nombre_pgc(c.codigo[:2], ctx.empresa.tipo_plan), debe=debe, haber=haber, saldo=debe - haber, usos=n)))
        return filas

    def totales(self, filas):
        return _sumas(filas, "debe", "haber", "saldo")

    def valores_formulario(self, ctx, id):
        c = ctx.sesion.get(Cuenta, int(id))
        return {"codigo": c.codigo, "nombre": c.nombre}

    def guardar(self, ctx, id, datos):
        if id is None:
            return str(svc_cuentas.crear_cuenta(ctx.sesion, ctx.empresa.id, datos["codigo"], datos["nombre"]).id)
        cuenta = ctx.sesion.get(Cuenta, int(id))
        svc_cuentas.modificar_cuenta(ctx.sesion, cuenta, codigo=datos["codigo"], nombre=datos["nombre"])
        return id

    def eliminar(self, ctx, ids):
        for i in ids:
            svc_cuentas.borrar_cuenta(ctx.sesion, ctx.sesion.get(Cuenta, int(i)))


# ------------------------------------------------------------------------------------------------ terceros


IDENTIFICADORES = [("", "—"), ("NIF", "NIF"), ("NIF-IVA", "NIF-IVA (operador intracomunitario)"), ("PASAPORTE", "Pasaporte"),
                   ("DOC_OFICIAL", "Documento oficial del país de residencia"), ("CERT_RESIDENCIA", "Certificado de residencia fiscal"), ("OTRO", "Otro documento")]
# campos de la ficha que se guardan tal cual (formulario → servicio)
FICHA_TEXTO = ("tipo_identificador", "domicilio", "codigo_postal", "poblacion", "provincia", "pais", "telefonos", "email", "web", "observaciones", "divisa", "tipos_iva_defecto",
               "tipo_operacion", "tipo_exencion_iva", "iban", "bic", "provincia_190", "clave_190", "subclave_190") + svc_cuentas.CAMPOS_DEL_INMUEBLE
FICHA_MARCAS = ("recargo_equivalencia", "no_incluir_347", "generico", "criterio_caja", "reagp", "pago_directo")
FICHA_CUENTAS = ("cuenta_gasto", "cuenta_suplidos", "cuenta_pago")


def _cuentas_del_plan(ctx: Contexto) -> list[tuple[str, str]]:
    return cuentas_para_listas(ctx)


def _formas_de_pago(ctx: Contexto) -> list[tuple[str, str]]:
    return [("", "—")] + [(str(f.id), f.texto) for f in ctx.sesion.scalars(select(FormaPago).where(FormaPago.empresa_id == ctx.empresa.id).order_by(FormaPago.numero_origen))]


class ListadoTerceros(Listado):
    """Base de los listados de proveedores y de clientes (uno por clase); sin `clase_fija` mostraría los dos."""

    clase_fija: str | None = None
    nombre, titulo = "terceros", "Clientes y proveedores"
    descripcion = "Terceros con su cuenta contable y los datos que se proponen en sus facturas. Doble clic para editar."
    columnas = [
        Col("clase", "Clase", TEXTO, 1), Col("nombre", "Nombre", TEXTO, 4), Col("comercial", "Nombre comercial", TEXTO, 3), Col("tipo_identificador", "Identificador", TEXTO, 1.2), Col("nif", "NIF", TEXTO, 1.3),
        Col("cuenta", "Cuenta", TEXTO, 1.2), Col("cuenta_irpf", "Cuenta IRPF", TEXTO, 1.2), Col("cuenta_gasto", "Gasto / ingreso", TEXTO, 1.3), Col("cuenta_suplidos", "Suplidos", TEXTO, 1.1),
        Col("domicilio", "Domicilio", TEXTO, 3), Col("codigo_postal", "C. postal", TEXTO, 0.9), Col("poblacion", "Población", TEXTO, 2), Col("provincia", "Provincia", TEXTO, 1.5), Col("pais", "País", TEXTO, 1.2),
        Col("telefonos", "Teléfonos", TEXTO, 1.6), Col("email", "Correo", TEXTO, 2.2), Col("web", "Web", TEXTO, 2), Col("divisa", "Divisa", TEXTO, 0.8),
        Col("recargo", "Rec. equiv.", TEXTO, 0.9), Col("no347", "No 347", TEXTO, 0.8), Col("generico", "Genérico", TEXTO, 0.9), Col("caja", "Crit. caja", TEXTO, 0.9), Col("reagp", "REAGP", TEXTO, 0.8),
        Col("tipos_iva", "Tipos de IVA", TEXTO, 1.1), Col("retencion", "Retención %", PORCENTAJE, 0.9), Col("deducible", "% IVA deducible", PORCENTAJE, 1.1), Col("operacion", "Tipo de operación", TEXTO, 1.5),
        Col("exencion", "Exención de IVA", TEXTO, 1.5), Col("pago_directo", "Pago directo", TEXTO, 0.9), Col("cuenta_pago", "Cuenta de pago/cobro", TEXTO, 1.3), Col("forma", "Forma de pago", TEXTO, 1.3),
        Col("iban", "IBAN", TEXTO, 2.4), Col("bic", "BIC", TEXTO, 1.1), Col("observaciones", "Observaciones", TEXTO, 3), Col("origen", "Nº MGD", ENTERO, 0.8),
        Col("clave_190", "Modelo 190", TEXTO, 0.9),
    ]
    campos = [
        Campo("clase", "Clase", "select", requerido=True, opciones=[("P", "Proveedor"), ("C", "Cliente")], seccion="Datos generales"),
        Campo("nombre", "Nombre", requerido=True, ancho=2), Campo("comercial", "Nombre comercial", ancho=2),
        Campo("tipo_identificador", "Tipo de identificador", "select", opciones=IDENTIFICADORES), Campo("nif", "NIF / identificador"),
        Campo("domicilio", "Domicilio", ancho=2), Campo("codigo_postal", "Código postal"), Campo("poblacion", "Población"), Campo("provincia", "Provincia"), Campo("pais", "País"),
        Campo("telefonos", "Teléfonos"), Campo("email", "Correo electrónico"), Campo("web", "Página web"), Campo("divisa", "Divisa", ayuda="EUR, USD…"),
        Campo("observaciones", "Observaciones", "textarea", ancho=2),
        Campo("cuenta", "Cuenta contable", sugerencias=_cuentas_del_plan, lista="cuentas", ayuda="Al crear, déjela vacía y el programa crea la siguiente cuenta libre del grupo elegido; o escriba una existente (subcuenta completa)", seccion="Contabilidad"),
        Campo("grupo_cuenta", "Grupo de la cuenta nueva", "select", opciones=[("", "Según la clase (proveedor 400, cliente 430)")] + list(svc_cuentas.GRUPOS_DE_TERCERO.items()),
              ayuda="Sólo se usa al crear con la cuenta vacía", solo_alta=True),
        Campo("cuenta_irpf", "Cuenta de IRPF", sugerencias=_cuentas_del_plan, lista="cuentas"),
        Campo("recargo_equivalencia", "Recargo de equivalencia", "checkbox"), Campo("no_incluir_347", "No incluir en el 347", "checkbox"), Campo("generico", "Genérico (varios en uno)", "checkbox"),
        Campo("criterio_caja", "Aplicar criterio de caja", "checkbox"), Campo("reagp", "REAGP (agricultura, ganadería y pesca)", "checkbox"),
        Campo("cuenta_gasto", "Subcuenta de gasto (proveedor) o de ingreso (cliente)", sugerencias=_cuentas_del_plan, lista="cuentas", ayuda="Se propone en sus facturas", seccion="Por defecto en las facturas"),
        Campo("cuenta_suplidos", "Subcuenta de suplidos", sugerencias=_cuentas_del_plan, lista="cuentas"),
        Campo("tipos_iva_defecto", "Tipos de IVA por defecto", ayuda="Números del catálogo separados por comas, hasta tres (por ejemplo 1,2); se propone el primero"),
        Campo("retencion_pct", "Retención por defecto (%)", "dinero"), Campo("pct_iva_deducible", "% de IVA deducible", "dinero", ayuda="100 salvo prorrata"),
        Campo("tipo_operacion", "Tipo de operación"), Campo("tipo_exencion_iva", "Tipo de exención de IVA (clientes)"),
        Campo("pago_directo", "Pago o cobro directo en la factura", "checkbox", seccion="Datos de pago o de cobro"), Campo("cuenta_pago", "Subcuenta de pago o de cobro por defecto", sugerencias=_cuentas_del_plan, lista="cuentas"),
        Campo("forma_pago", "Forma de pago por defecto", "select", opciones=_formas_de_pago), Campo("iban", "IBAN / CCC", ayuda="Se comprueban los dígitos de control"), Campo("bic", "BIC"),
        Campo("provincia_190", "Provincia (código de 2 cifras)", ayuda="28 Madrid, 13 Ciudad Real, 45 Toledo… Es la del domicilio del perceptor: sirve para el 190 y para el 180", seccion="Perceptor de retenciones (modelo 190)"),
        Campo("clave_190", "Clave de percepción", ayuda="Una letra: H actividades agrícolas, G profesionales, I forestales…"), Campo("subclave_190", "Subclave", ayuda="Dos cifras (H03 = agrícolas y ganaderas)"),
        Campo("inmueble_situacion", "Situación del inmueble", "select", seccion="Inmueble que alquila (modelo 180)", opciones=[
            ("", "—"), ("1", "1 · Con referencia catastral (resto de España)"), ("2", "2 · Con referencia catastral en el País Vasco"), ("3", "3 · Con referencia catastral en Navarra"), ("4", "4 · Sin referencia catastral")]),
        Campo("inmueble_catastro", "Referencia catastral", ayuda="14 a 20 letras y cifras, sin espacios (viene en el recibo del IBI y en el contrato)"),
        Campo("inmueble_tipo_via", "Tipo de vía", ayuda="CL calle, AV avenida, PZ plaza, CR carretera…"), Campo("inmueble_via", "Nombre de la vía", ancho=2),
        Campo("inmueble_tipo_numeracion", "Tipo de numeración", ayuda="NUM, KM o S/N"), Campo("inmueble_numero", "Número de la casa"), Campo("inmueble_calificador", "Calificador del número", ayuda="BIS, DUP…"),
        Campo("inmueble_bloque", "Bloque"), Campo("inmueble_portal", "Portal"), Campo("inmueble_escalera", "Escalera"), Campo("inmueble_planta", "Planta o piso"), Campo("inmueble_puerta", "Puerta"),
        Campo("inmueble_complemento", "Complemento", ayuda="Por ejemplo «Centro Comercial …, local …»", ancho=2), Campo("inmueble_localidad", "Localidad o población", ayuda="Sólo si es distinta del municipio"),
        Campo("inmueble_municipio", "Municipio"), Campo("inmueble_codigo_municipio", "Código de municipio (INE)", ayuda="5 cifras: las dos de la provincia y tres del municipio"),
        Campo("inmueble_provincia", "Provincia del inmueble (código)", ayuda="Dos cifras: 28 Madrid, 13 Ciudad Real…"), Campo("inmueble_codigo_postal", "Código postal del inmueble"),
    ]
    anadir = borrar = editable = True

    def filas(self, ctx, params):
        codigos = {i: c for i, c in ctx.sesion.execute(select(Cuenta.id, Cuenta.codigo).where(Cuenta.empresa_id == ctx.empresa.id))}
        formas = {f.id: f.texto for f in ctx.sesion.scalars(select(FormaPago).where(FormaPago.empresa_id == ctx.empresa.id))}
        si = lambda v: "Sí" if v else None  # noqa: E731
        return [
            Fila(str(t.id), dict(
                clase="Cliente" if t.clase == "C" else "Proveedor", nombre=t.nombre, comercial=t.comercial, tipo_identificador=t.tipo_identificador, nif=t.nif, cuenta=codigos.get(t.cuenta_id),
                cuenta_irpf=codigos.get(t.cuenta_irpf_id), cuenta_gasto=codigos.get(t.cuenta_gasto_id), cuenta_suplidos=codigos.get(t.cuenta_suplidos_id), domicilio=t.domicilio,
                codigo_postal=t.codigo_postal, poblacion=t.poblacion, provincia=t.provincia, pais=t.pais, telefonos=t.telefonos, email=t.email, web=t.web, divisa=t.divisa,
                recargo=si(t.recargo_equivalencia), no347=si(t.no_incluir_347), generico=si(t.generico), caja=si(t.criterio_caja), reagp=si(t.reagp), tipos_iva=t.tipos_iva_defecto,
                retencion=t.retencion_pct, deducible=t.pct_iva_deducible, operacion=t.tipo_operacion, exencion=t.tipo_exencion_iva, pago_directo=si(t.pago_directo),
                cuenta_pago=codigos.get(t.cuenta_pago_id), forma=formas.get(t.forma_pago_id), iban=t.iban, bic=t.bic, observaciones=t.observaciones, origen=t.numero_origen,
                clave_190=(f"{t.provincia_190 or '--'}{t.clave_190}{t.subclave_190 or '--'}" if t.clave_190 else None),
            ))
            for t in ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, *([Tercero.clase == self.clase_fija] if self.clase_fija else [])).order_by(Tercero.nombre))
        ]

    def valores_formulario(self, ctx, id):
        t = ctx.sesion.get(Tercero, int(id))
        codigos = {i: c for i, c in ctx.sesion.execute(select(Cuenta.id, Cuenta.codigo).where(Cuenta.empresa_id == ctx.empresa.id))}
        valores = {"clase": t.clase, "nombre": t.nombre, "comercial": t.comercial, "nif": t.nif, "cuenta": codigos.get(t.cuenta_id), "cuenta_irpf": codigos.get(t.cuenta_irpf_id),
                   "retencion_pct": t.retencion_pct, "pct_iva_deducible": t.pct_iva_deducible, "forma_pago": str(t.forma_pago_id) if t.forma_pago_id else "",
                   "cuenta_gasto": codigos.get(t.cuenta_gasto_id), "cuenta_suplidos": codigos.get(t.cuenta_suplidos_id), "cuenta_pago": codigos.get(t.cuenta_pago_id)}
        valores.update({c: getattr(t, c) for c in FICHA_TEXTO})
        valores.update({c: getattr(t, c) for c in FICHA_MARCAS})
        return valores

    def guardar(self, ctx, id, datos):
        clase = self.clase_fija or datos["clase"]
        extra = dict(comercial=datos["comercial"], nif=datos["nif"], cuenta=datos["cuenta"], cuenta_irpf=datos.get("cuenta_irpf"))
        ficha = {c: datos.get(c) for c in FICHA_TEXTO + FICHA_MARCAS + FICHA_CUENTAS + ("retencion_pct", "pct_iva_deducible")}
        ficha["forma_pago_id"] = int(datos["forma_pago"]) if datos.get("forma_pago") else None
        if id is None:
            return str(svc_cuentas.crear_tercero(ctx.sesion, ctx.empresa.id, clase, datos["nombre"], grupo_cuenta=datos.get("grupo_cuenta"), **extra, **ficha).id)
        svc_cuentas.modificar_tercero(ctx.sesion, ctx.sesion.get(Tercero, int(id)), clase, datos["nombre"], **extra, **ficha)
        return id

    def eliminar(self, ctx, ids):
        for i in ids:
            svc_cuentas.borrar_tercero(ctx.sesion, ctx.sesion.get(Tercero, int(i)))


def _sin(lista, *nombres):
    return [x for x in lista if getattr(x, "nombre", None) not in nombres and getattr(x, "clave", None) not in nombres]


def _con_titulo(lista, **titulos):
    campos = [dataclasses.replace(x, titulo=titulos.get(x.nombre, x.titulo)) for x in lista]
    campos[0] = dataclasses.replace(campos[0], seccion=campos[0].seccion or "Datos generales")  # el campo «clase», que abría la sección, ya no está
    return campos


class ListadoProveedores(ListadoTerceros):
    clase_fija = "P"
    nombre, titulo = "proveedores", "Proveedores"
    descripcion = "Proveedores con su cuenta contable y los datos que se proponen en sus facturas. Doble clic para editar."
    columnas = _sin(ListadoTerceros.columnas, "clase", "exencion")
    campos = _con_titulo(_sin(ListadoTerceros.campos, "clase", "tipo_exencion_iva"), cuenta_gasto="Subcuenta de gasto", cuenta_pago="Subcuenta de pago por defecto", pago_directo="Pago directo en la factura")


class ListadoClientes(ListadoTerceros):
    clase_fija = "C"
    nombre, titulo = "clientes", "Clientes"
    descripcion = "Clientes con su cuenta contable y los datos que se proponen en sus facturas. Doble clic para editar."
    columnas = _sin(ListadoTerceros.columnas, "clase", "cuenta_irpf", "clave_190")
    campos = _con_titulo(_sin(ListadoTerceros.campos, "clase", "cuenta_irpf", "provincia_190", "clave_190", "subclave_190", *svc_cuentas.CAMPOS_DEL_INMUEBLE), cuenta_gasto="Subcuenta de ingreso", cuenta_pago="Subcuenta de cobro por defecto", pago_directo="Cobro directo en la factura",
                         retencion_pct="Retención por defecto (%)")


# ------------------------------------------------------------------------------------------------ informes (sólo lectura)

PARAMETROS_FECHAS = [Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]


class ListadoDiario(Listado):
    nombre, titulo = "diario", "Libro Diario"
    descripcion = "Un renglón por apunte, por orden de fecha y número. Doble clic para ver el asiento completo."
    columnas = [
        Col("fecha", "Fecha", FECHA, 1.1), Col("asiento", "Asiento", TEXTO, 0.9), Col("diario", "Nº diario", ENTERO, 0.9), Col("subtipo", "Tipo", TEXTO, 0.6),
        Col("cuenta", "Cuenta", TEXTO, 1.1), Col("nombre", "Nombre de la cuenta", TEXTO, 3), Col("concepto", "Concepto", TEXTO, 3),
        Col("debe", "Debe", DINERO, 1.2), Col("haber", "Haber", DINERO, 1.2),
    ]
    parametros = PARAMETROS_FECHAS

    def filas(self, ctx, params):
        from conta_pridalac.servicios.informes import libro_diario

        filas = []
        for a in libro_diario(ctx.sesion, ctx.ejercicio, desde=params.get("desde"), hasta=params.get("hasta")).asientos:
            for ap in a.apuntes:
                filas.append(Fila(str(a.id), dict(fecha=a.fecha, asiento=a.identificador, diario=a.numero_diario, subtipo=a.subtipo, cuenta=ap.cuenta.codigo,
                                                    nombre=ap.cuenta.nombre, concepto=ap.concepto or a.concepto, debe=ap.debe or None, haber=ap.haber or None)))
        return filas

    def totales(self, filas):
        return _sumas(filas, "debe", "haber")

    def detalle(self, ctx, id):
        a = ctx.sesion.get(Asiento, int(id))
        filas = [[ap.cuenta.codigo, ap.cuenta.nombre, ap.concepto or a.concepto, ap.debe or None, ap.haber or None] for ap in a.apuntes]
        tabla = Tabla(
            f"Asiento {a.identificador}", [Columna("Cuenta"), Columna("Nombre", ancho=3), Columna("Concepto", ancho=3), Columna("Debe", DINERO), Columna("Haber", DINERO)], filas,
            f"{a.fecha:%d/%m/%Y} · tipo {a.subtipo or '—'} · nº diario {a.numero_diario or '—'}",
            totales=[None, None, "Totales", sum((ap.debe for ap in a.apuntes), CERO), sum((ap.haber for ap in a.apuntes), CERO)],
        )
        return Detalle(f"Asiento {a.identificador}", tabla)


class ListadoBalance(Listado):
    nombre, titulo = "balance", "Balance de sumas y saldos"
    descripcion = "Sumas y saldos por cuenta, agrupables a 1, 2 o 3 dígitos o por subcuenta."
    columnas = [
        Col("cuenta", "Cuenta", TEXTO, 1), Col("nombre", "Nombre", TEXTO, 4), Col("debe", "Debe", DINERO, 1.3), Col("haber", "Haber", DINERO, 1.3),
        Col("deudor", "Saldo deudor", DINERO, 1.3), Col("acreedor", "Saldo acreedor", DINERO, 1.3),
    ]
    parametros = [Campo("nivel", "Agrupar a", "select", opciones=[("3", "3 dígitos (cuentas)"), ("12", "Subcuentas (código completo)"), ("2", "2 dígitos (subgrupos)"), ("1", "1 dígito (grupos)")], defecto="3"),
                  Campo("cierre", "Regularización y cierre", "select", opciones=[("no", "Sin incluir (como el programa anterior)"), ("si", "Incluidos")], defecto="no")] + PARAMETROS_FECHAS

    def filas(self, ctx, params):
        nivel = int(params.get("nivel") or 3)
        sin = () if params.get("cierre") == "si" else ("R", "Z")  # por defecto, el balance previo a la regularización y al cierre
        b = balance_sumas_y_saldos(ctx.sesion, ctx.ejercicio, nivel=nivel, desde=params.get("desde"), hasta=params.get("hasta"), excluir_subtipos=sin)
        return [Fila(f.cuenta, dict(cuenta=f.cuenta, nombre=f.nombre, debe=f.debe, haber=f.haber, deudor=f.saldo_deudor or None, acreedor=f.saldo_acreedor or None)) for f in b.filas]

    def totales(self, filas):
        return _sumas(filas, "debe", "haber", "deudor", "acreedor")



def _cuentas_con_movimientos(ctx: Contexto) -> list[tuple[str, str]]:
    return list(
        ctx.sesion.execute(
            select(Cuenta.codigo, Cuenta.nombre)
            .join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
            .where(Cuenta.empresa_id == ctx.empresa.id, Asiento.ejercicio_id == ctx.ejercicio.id).group_by(Cuenta.codigo, Cuenta.nombre).order_by(Cuenta.codigo)
        )
    )


class ListadoMayor(Listado):
    nombre, titulo = "mayor", "Libro Mayor"
    descripcion = "Movimientos de todas las cuentas, cada una con su saldo acumulado. Se puede acotar a una cuenta (57200001) o a un grupo (572)."
    columnas = [
        Col("cuenta", "Cuenta", TEXTO, 1.1), Col("nombre", "Nombre de la cuenta", TEXTO, 3), Col("fecha", "Fecha", FECHA, 1.1), Col("asiento", "Asiento", TEXTO, 0.9),
        Col("concepto", "Concepto", TEXTO, 4), Col("debe", "Debe", DINERO, 1.2), Col("haber", "Haber", DINERO, 1.2), Col("saldo", "Saldo", DINERO, 1.3),
    ]
    parametros = [Campo("cuenta", "Cuenta o grupo", ayuda="vacío = todas · 57200001 · 572", sugerencias=lambda ctx: _cuentas_con_movimientos(ctx))] + PARAMETROS_FECHAS

    def texto_vacio(self, ctx, params):
        return "No hay movimientos con esos criterios"

    def filas(self, ctx, params):
        prefijo = (params.get("cuenta") or "").strip()
        if prefijo and not prefijo.isdigit():
            primera = prefijo.split()[0]  # «57200003 BANCO EMPRESA A BBVA»: vale el número del principio
            if not primera.isdigit():
                raise ErrorContable("La cuenta sólo lleva dígitos")
            prefijo = primera
        filas = []
        for m in mayor_general(ctx.sesion, ctx.ejercicio, prefijo, desde=params.get("desde"), hasta=params.get("hasta")):
            comun = dict(cuenta=m.cuenta, nombre=m.nombre)
            if m.saldo_anterior != 0:
                filas.append(Fila(None, dict(comun, fecha=None, asiento="", concepto="Saldo anterior", debe=None, haber=None, saldo=m.saldo_anterior), clase="resumen"))
            filas += [Fila(None, dict(comun, fecha=l.fecha, asiento=l.asiento, concepto=l.concepto, debe=l.debe or None, haber=l.haber or None, saldo=l.saldo)) for l in m.lineas]
            filas.append(Fila(None, dict(comun, fecha=None, asiento="", concepto="Total de la cuenta", debe=m.total_debe, haber=m.total_haber, saldo=m.saldo_final), clase="resumen total"))
        return filas

    def subtitulo(self, ctx, params):
        prefijo = (params.get("cuenta") or "").strip()
        base = f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio}"
        if not prefijo:
            return base + " · todas las cuentas"
        nombre = ctx.sesion.scalar(select(Cuenta.nombre).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo == prefijo))
        return base + (f" · cuenta {prefijo} {nombre}" if nombre else f" · cuentas que empiezan por {prefijo}")

    def totales(self, filas):
        movimientos = [f for f in filas if "resumen" not in f.clase]
        if not movimientos:
            return None
        cuentas = {f.valores["cuenta"] for f in movimientos}
        finales = [f for f in filas if "total" in f.clase]
        return {**_sumas(movimientos, "debe", "haber"), "saldo": finales[0].valores["saldo"] if len(cuentas) == 1 and len(finales) == 1 else None}


TIPO_DE_ASIENTO = {"E": 1, "R": 2}


def detalle_de_factura(ctx: Contexto, f: Factura) -> Detalle:
    """Ficha de sólo lectura de una factura: datos, IVA, ajustes, asiento, vencimientos y justificantes."""
    sentido = "recibida" if f.sentido == "R" else "emitida"
    tercero = f.tercero
    datos = [
        ("Documento", f"{f.sentido} {f.numero}"), ("Fecha contable", f"{f.fecha_contable:%d/%m/%Y}"),
        ("Fecha de la factura", f"{f.fecha_factura:%d/%m/%Y}" if f.fecha_factura else None), ("Nº de factura", f.numero_factura),
        ("Tercero", tercero.nombre if tercero else None), ("NIF", tercero.nif if tercero else None),
        ("Cuenta del tercero", f.cuenta_tercero.codigo if f.cuenta_tercero else None),
        ("Gasto" if f.sentido == "R" else "Ingreso", f.cuenta_contrapartida.codigo if f.cuenta_contrapartida else None),
        ("Total", formatear(f.total, DINERO)), ("Concepto", f.concepto), ("Notas", f.notas),
    ]
    iva = Tabla(
        "IVA", [Columna("Base", DINERO, 1.2), Columna("% IVA", PORCENTAJE, 0.8), Columna("Cuota", DINERO, 1.2), Columna("% recargo", PORCENTAJE, 0.9), Columna("Recargo", DINERO, 1.1),
                Columna("Cuenta de IVA", ancho=1.3), Columna("Deducible", ancho=0.9), Columna("Bien de inversión", ancho=1.1)],
        [[i.base, i.pct_iva, i.cuota_iva, i.pct_recargo, i.cuota_recargo or None, i.cuenta_iva.codigo if i.cuenta_iva else None, "Sí" if i.deducible else "No", "Sí" if i.bien_inversion else "No"] for i in f.ivas],
    )
    extras = []
    if f.ajustes:
        etiquetas = {"C": "Cliente", "I": "Ingreso", "G": "Gasto", "P": "Proveedor"}
        extras.append(Tabla(
            "Ajustes (retenciones y otros)", [Columna("Cuenta", ancho=1.2), Columna("Nombre", ancho=3), Columna("Importe", DINERO, 1.2), Columna("Contra", ancho=1), Columna("Afecta al IVA", ancho=1)],
            [[a.cuenta.codigo, a.cuenta.nombre, a.importe, etiquetas.get(a.contra, a.contra), "Sí" if a.afecta_iva else "No"] for a in f.ajustes],
        ))
    asientos = ctx.sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ctx.ejercicio.id, Asiento.tipo == TIPO_DE_ASIENTO[f.sentido], Asiento.numero == f.numero).order_by(Asiento.sub)).all()
    lineas = [[a.identificador, ap.cuenta.codigo, ap.cuenta.nombre, ap.debe or None, ap.haber or None] for a in asientos for ap in a.apuntes]
    extras.append(Tabla(
        "Asiento contable", [Columna("Asiento"), Columna("Cuenta", ancho=1.2), Columna("Nombre", ancho=3), Columna("Debe", DINERO, 1.2), Columna("Haber", DINERO, 1.2)], lineas,
        totales=[None, None, "Totales", sum((ap.debe for a in asientos for ap in a.apuntes), CERO), sum((ap.haber for a in asientos for ap in a.apuntes), CERO)],
    ))
    vencimientos = ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id).order_by(Vencimiento.fecha)).all()
    if vencimientos:
        extras.append(Tabla(
            "Vencimientos", [Columna("Fecha", FECHA, 1.2), Columna("Importe", DINERO, 1.2), Columna("Pendiente", DINERO, 1.2)],
            [[v.fecha, v.importe, pendiente(ctx.sesion, v)] for v in vencimientos],
        ))
    adjuntos = ctx.sesion.scalars(select(Adjunto).where(Adjunto.factura_id == f.id).order_by(Adjunto.orden)).all()
    if adjuntos:
        extras.append(Tabla("Justificantes", [Columna("Fichero", ancho=4), Columna("Tamaño (KB)", ENTERO, 1), Columna("En disco", ancho=1)],
                            [[a.nombre, round(a.tamano / 1024) if a.tamano else None, "Sí" if a.presente else "No"] for a in adjuntos]))
    return Detalle(f"Factura {sentido} {f.numero}" + (f" · {f.numero_factura}" if f.numero_factura else ""), iva, datos, extras)


class ListadoIva(Listado):
    sentido = "R"
    columnas = [
        Col("fecha", "Fecha", FECHA, 1.1), Col("numero", "Nº", ENTERO, 0.6), Col("factura", "Nº factura", TEXTO, 1.5), Col("tercero", "Tercero", TEXTO, 3),
        Col("nif", "NIF", TEXTO, 1.2), Col("base", "Base", DINERO, 1.2), Col("pct", "% IVA", PORCENTAJE, 0.8), Col("cuota", "Cuota", DINERO, 1.1),
        Col("recargo", "Recargo", DINERO, 1.0), Col("deducible", "Deducible", TEXTO, 0.9), Col("total", "Total", DINERO, 1.2),
    ]
    parametros = PARAMETROS_FECHAS

    def filas(self, ctx, params):
        libro = libro_iva(ctx.sesion, ctx.ejercicio, self.sentido, desde=params.get("desde"), hasta=params.get("hasta"))
        return [
            Fila(str(l.factura_id), dict(fecha=l.fecha, numero=l.numero, factura=l.numero_factura, tercero=l.tercero, nif=l.nif, base=l.base, pct=l.pct_iva, cuota=l.cuota,
                            recargo=l.cuota_recargo or None, deducible="Sí" if l.deducible else "No", total=l.base + l.cuota + l.cuota_recargo))
            for l in libro.lineas
        ]

    def totales(self, filas):
        return _sumas(filas, "base", "cuota", "recargo", "total")

    def detalle(self, ctx, id):
        return detalle_de_factura(ctx, ctx.sesion.get(Factura, int(id)))


class ListadoIvaRecibidas(ListadoIva):
    nombre, titulo, sentido = "iva-recibidas", "Libro de IVA — facturas recibidas", "R"
    descripcion = "IVA soportado: una línea por tipo de IVA de cada factura. Doble clic para ver la factura."


class ListadoIvaEmitidas(ListadoIva):
    nombre, titulo, sentido = "iva-emitidas", "Libro de IVA — facturas emitidas", "E"
    descripcion = "IVA repercutido: una línea por tipo de IVA de cada factura. Doble clic para ver la factura."


def todos_los_listados() -> dict[str, Listado]:
    from conta_pridalac.web.asientos import ListadoAsientos, ListadoPlantillas
    from conta_pridalac.web.auditoria import ListadoAuditoria
    from conta_pridalac.web.bienes import ListadoBienes, ListadoLibroBienes
    from conta_pridalac.web.copias import ListadoCopias
    from conta_pridalac.web.registro_cambios import ListadoRegistroCambios
    from conta_pridalac.web.declaraciones import ListadoDeclaraciones, ListadoDeclaraciones111, ListadoDeclaraciones190, ListadoDeclaraciones347
    from conta_pridalac.web.ejercicios import ListadoEjercicios
    from conta_pridalac.web.conciliacion import ListadoConciliacion, ListadoCorrespondencias, ListadoEmitidas
    from conta_pridalac.web.conciliar_pagos import ListadoConciliarPagos
    from conta_pridalac.web.lineas_sin_factura import ListadoLineasSinFactura
    from conta_pridalac.web.extractos import ListadoCuadreBancos, ListadoExtractos
    from conta_pridalac.web.estados import ListadoBalanceOficial, ListadoBalanceSituacion, ListadoEstadoCambiosPN, ListadoPerdidasYGanancias, ListadoPyGOficial, ListadoSaldosAcumulados
    from conta_pridalac.web.facturacion import ListadoFacturacionTerceros
    from conta_pridalac.web.gastos_categoria import ListadoGastosCategoria
    from conta_pridalac.web.facturas import ListadoFacturasEmitidas, ListadoFacturasRecibidas
    from conta_pridalac.web.iva import ListadoLiquidacionesIva
    from conta_pridalac.web.modelo111 import ListadoModelo111
    from conta_pridalac.web.modelo115 import ListadoModelo115
    from conta_pridalac.web.modelo180 import ListadoModelo180
    from conta_pridalac.web.modelo190 import ListadoModelo190
    from conta_pridalac.web.modelo347 import ListadoModelo347
    from conta_pridalac.web.deposito import ListadoDeposito
    from conta_pridalac.web.impuesto_sociedades import ListadoModelo200
    from conta_pridalac.web.legalizacion import ListadoLegalizacion
    from conta_pridalac.web.libros_registro import ListadoActas, ListadoSocios
    from conta_pridalac.web.modelo202 import ListadoModelo202
    from conta_pridalac.web.modelo303 import ListadoModelo303
    from conta_pridalac.web.modelo390 import ListadoModelo390
    from conta_pridalac.web.trimestre import ListadoTrimestre
    from conta_pridalac.web.tesoreria import ListadoBancos, ListadoMovimientos, ListadoVencimientos

    lista = [ListadoTrimestre(), ListadoFacturasRecibidas(), ListadoFacturasEmitidas(), ListadoFacturacionTerceros(), ListadoAsientos(), ListadoPlantillas(), ListadoMovimientos(), ListadoVencimientos(), ListadoBancos(), ListadoExtractos(), ListadoCuadreBancos(), ListadoConciliacion(), ListadoEmitidas(), ListadoConciliarPagos(), ListadoLineasSinFactura(), ListadoCorrespondencias(), ListadoBienes(), ListadoLibroBienes(), ListadoCuentas(), ListadoProveedores(), ListadoClientes(), ListadoDiario(), ListadoBalance(), ListadoSaldosAcumulados(), ListadoBalanceSituacion(), ListadoPerdidasYGanancias(), ListadoGastosCategoria(), ListadoBalanceOficial(), ListadoPyGOficial(), ListadoEstadoCambiosPN(), ListadoMayor(), ListadoIvaRecibidas(), ListadoIvaEmitidas(), ListadoLiquidacionesIva(), ListadoModelo303(), ListadoDeclaraciones(), ListadoModelo111(), ListadoDeclaraciones111(), ListadoModelo115(), ListadoModelo190(), ListadoDeclaraciones190(), ListadoModelo180(), ListadoModelo347(), ListadoDeclaraciones347(), ListadoModelo202(), ListadoModelo390(), ListadoModelo200(), ListadoLegalizacion(), ListadoDeposito(), ListadoSocios(), ListadoActas(), ListadoEjercicios(), ListadoAuditoria(), ListadoCopias(), ListadoRegistroCambios()]
    return {l.nombre: l for l in lista}


@dataclass
class Opcion:
    """Una entrada del menú: un listado o pantalla (`nombre`) o algo que aún no está (`proximamente`)."""

    nombre: str | None
    titulo: str
    descripcion: str = ""
    proximamente: bool = False
    alias: tuple[str, ...] = ()  # otras pantallas que pertenecen a esta entrada (p. ej. las declaraciones presentadas de un modelo)


@dataclass
class Caja:
    id: str
    titulo: str
    opciones: list[Opcion]


# (id de la caja, título, entradas): una entrada es el nombre de un listado (su título y su descripción salen del propio listado), o (nombre, título, alias, descripción) si se quiere otro título u otra descripción,
# o «~título|descripción» si todavía no está. La descripción se ve debajo de cada opción: explica para qué sirve.
CAJAS = [
    ("trimestre", "Trimestre", ["trimestre", "extractos", "conciliacion", "emitidas-trimestre", "conciliar-pagos", "lineas-sin-factura", "cuadre-bancos", "correspondencias"]),
    ("facturas", "Facturas", ["facturas-recibidas", "facturas-emitidas"]),
    ("tesoreria", "Tesorería", ["movimientos", "vencimientos", "bancos"]),
    ("asientos", "Asientos", ["asientos", "plantillas"]),
    ("inmovilizado", "Inmovilizado", ["bienes", "bienes-iva"]),
    ("datos", "Datos", ["cuentas", "proveedores", "clientes"]),
    ("listados", "Listados", ["diario", "mayor", "balance", "saldos-acumulados", "iva-recibidas", "iva-emitidas", "balance-situacion", "perdidas-ganancias", "balance-oficial", "pyg-oficial",
                              "estado-cambios-pn"]),
    ("liquidaciones", "Liquidaciones", [
        ("liquidacion-iva", "Liquidación del IVA (asiento)", (), None),
        ("modelo-303", "303 · IVA", ("declaraciones",), "Autoliquidación trimestral: cálculo, controles, fichero para la sede, justificantes y declaraciones presentadas."),
        ("modelo-111", "111 · Retenciones", ("declaraciones-111",), "Retenciones e ingresos a cuenta del IRPF (trimestral): cálculo, fichero para la sede, justificantes y declaraciones presentadas."),
        ("modelo-115", "115 · Retenciones por alquileres", (), "Retenciones del 19 % por el alquiler de locales y otros inmuebles urbanos (trimestral): cálculo, fichero para la sede, justificantes."),
        ("modelo-190", "190 · Resumen anual de retenciones", ("declaraciones-190",), "Perceptores, percepciones y retenciones del ejercicio: cálculo, fichero para la sede, justificantes y declaraciones presentadas."),
        ("modelo-180", "180 · Resumen anual de alquileres", (), "Arrendadores, rentas y retenciones del ejercicio (la suma de los cuatro 115) con los datos de cada inmueble: cálculo, fichero para la sede y justificantes."),
        ("modelo-347", "347 · Operaciones con terceros", ("declaraciones-347",), "Clientes y proveedores con más de 3.005,06 € en el año: cálculo, fichero para la sede, justificantes y declaraciones presentadas."),
        ("modelo-202", "202 · Pago fraccionado", (), "Pago fraccionado del Impuesto sobre Sociedades (abril, octubre y diciembre): base del último IS presentado, fichero para la sede y justificantes."), ("modelo-390", "390 · Resumen anual del IVA", (), "Declaración-resumen anual del IVA: las casillas del año calculadas con las mismas facturas que los 303 y los controles contra ellos.")]),
    ("sociedades", "Impuesto sobre Sociedades", ["modelo-200"]),
    ("mercantil", "Registro Mercantil", ["libro-socios", "libro-actas", ("legalizacion-libros", "Legalización de libros", (), "Diario, inventario y cuentas anuales, socios y actas del ejercicio para legalizar en el Registro Mercantil con Legalia2."), ("deposito-cuentas", "Depósito de cuentas", (), "Formulario de D2 y memoria de las cuentas anuales para depositar en el Registro Mercantil con Legalia2.")]),
    ("ejercicio", "Ejercicio", ["ejercicios", "auditoria", "registro-cambios", "copias"]),
    ("gestion", "Gestión", ["gastos-categoria", "facturacion-terceros"]),
]


def construir_menu(listados: dict[str, Listado]) -> list[Caja]:
    """Las cajas del menú con los títulos y las descripciones de cada listado."""
    cajas = []
    for id_, titulo, entradas in CAJAS:
        opciones = []
        for e in entradas:
            if isinstance(e, str) and e.startswith("~"):
                titulo_pendiente, _, explicacion = e[1:].partition("|")
                opciones.append(Opcion(None, titulo_pendiente, explicacion, proximamente=True))
                continue
            nombre, titulo_propio, alias, explicacion = (e, None, (), None) if isinstance(e, str) else e
            listado = listados.get(nombre)
            opciones.append(Opcion(nombre, titulo_propio or (listado.titulo if listado else nombre), explicacion or (listado.descripcion if listado else ""), alias=tuple(alias)))
        cajas.append(Caja(id_, titulo, opciones))
    return cajas


def menu_de_empresa(menu: list[Caja], visibles: set[str]) -> list[Caja]:
    """El menú sin las pantallas de los modelos que la empresa no presenta (ni tiene presentados); las cajas que se quedan sin opciones desaparecen."""
    from conta_pridalac.servicios.empresa import PANTALLA_A_MODELO

    cajas = []
    for caja in menu:
        opciones = [o for o in caja.opciones if o.nombre is None or PANTALLA_A_MODELO.get(o.nombre) is None or PANTALLA_A_MODELO[o.nombre] in visibles]
        if opciones:
            cajas.append(Caja(caja.id, caja.titulo, opciones))
    return cajas


def caja_de(menu: list[Caja], nombre: str | None) -> str | None:
    """El id de la caja a la que pertenece una pantalla (para dejarla abierta)."""
    for caja in menu:
        for o in caja.opciones:
            if nombre and (o.nombre == nombre or nombre in o.alias):
                return caja.id
    return None
