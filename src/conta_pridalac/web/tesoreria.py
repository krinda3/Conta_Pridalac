"""Tesorería en la web: bancos, movimientos (cobros y pagos), vencimientos pendientes y transferencias.

Un movimiento de banco agrupa líneas que saldan vencimientos, van a una cuenta o quedan pendientes de aplicar; su asiento se genera
solo y el formulario lo enseña antes de grabar. Desde un vencimiento se puede cobrar o pagar de golpe, o compensarlo contra una cuenta.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from conta_pridalac.db.modelos import (
    BANCO_NORMAL,
    TIPO_TESORERIA,
    Adjunto,
    Apunte,
    Asiento,
    Banco,
    Cuenta,
    FormaPago,
    MovimientoBanco,
    Pago,
    Vencimiento,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import introducir_fecha, parsear_fecha
from conta_pridalac.domain.tesoreria import cuenta_efectiva, cuenta_pendiente_de_aplicar
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO
from conta_pridalac.servicios import adjuntos as svc_adjuntos
from conta_pridalac.servicios import tesoreria as svc
from conta_pridalac.web.comun import (
    cuentas_para_listas,
    dinero_opcional,
    fecha_texto,
    guardar_justificantes,
    id_de_cuenta,
    texto_dinero,
)
from conta_pridalac.web.listados import Campo, Col, Contexto, Fila, Listado, a_texto_de_formulario

CERO = Decimal("0.00")


# ------------------------------------------------------------------------------------------------ utilidades


def _bancos(ctx: Contexto, *, solo_normales: bool = True) -> list[Banco]:
    consulta = select(Banco).where(Banco.empresa_id == ctx.empresa.id).order_by(*svc.ORDEN_DE_BANCOS)
    if solo_normales:
        consulta = consulta.where(Banco.clase == BANCO_NORMAL)
    return list(ctx.sesion.scalars(consulta))


def _bancos_ordenados(ctx: Contexto) -> list[Banco]:
    """Los bancos reales primero y después las compensaciones y remesas; cada grupo por su número."""
    return sorted(_bancos(ctx, solo_normales=False), key=lambda b: (b.clase != BANCO_NORMAL, b.orden is None, b.orden or 0, b.numero))


def _pagado_por_vencimiento(ctx: Contexto) -> dict[int, Decimal]:
    return {vid: total for vid, total in ctx.sesion.execute(select(Pago.vencimiento_id, func.sum(Pago.importe)).where(Pago.vencimiento_id.is_not(None)).group_by(Pago.vencimiento_id))}


def _nombre_de(v: Vencimiento) -> str:
    if v.factura is not None and v.factura.tercero is not None:
        return v.factura.tercero.nombre
    cuenta = cuenta_efectiva(v)
    return cuenta.nombre if cuenta is not None else ""


def _etiqueta(v: Vencimiento, pendiente: Decimal) -> str:
    fecha = f"{v.fecha:%d/%m/%y}" if v.fecha else "sin fecha"
    return f"{v.origen_tipo} {v.origen_numero} · {_nombre_de(v)} · {fecha} · pendiente {texto_dinero(pendiente)}"


def _vencimientos_con_pendiente(ctx: Contexto) -> list[tuple[Vencimiento, Decimal]]:
    pagado = _pagado_por_vencimiento(ctx)
    consulta = (
        select(Vencimiento).where(Vencimiento.ejercicio_id == ctx.ejercicio.id)
        .options(selectinload(Vencimiento.factura)).order_by(Vencimiento.fecha, Vencimiento.id)
    )
    return [(v, v.importe - pagado.get(v.id, CERO)) for v in ctx.sesion.scalars(consulta)]


# ------------------------------------------------------------------------------------------------ bancos


class ListadoBancos(Listado):
    nombre, titulo = "bancos", "Bancos"
    descripcion = "Cuentas bancarias con su saldo inicial, el saldo que resulta de sus movimientos y el de su cuenta contable (deben coincidir)."
    anadir = borrar = editable = True
    columnas = [
        Col("numero", "Nº", ENTERO, 0.6), Col("orden", "Orden", ENTERO, 0.7), Col("nombre", "Banco", TEXTO, 3), Col("sucursal", "Sucursal", TEXTO, 2), Col("iban", "IBAN", TEXTO, 3), Col("bic", "BIC", TEXTO, 1.2),
        Col("cuenta", "Cuenta", TEXTO, 1.2), Col("inicial", "Saldo inicial", DINERO, 1.3), Col("movimientos", "Movs.", ENTERO, 0.7), Col("saldo_mov", "Saldo por movimientos", DINERO, 1.5),
        Col("saldo_cuenta", "Saldo de la cuenta", DINERO, 1.4), Col("diferencia", "Diferencia", DINERO, 1.1),
    ]
    campos = [
        Campo("nombre", "Banco", requerido=True), Campo("sucursal", "Sucursal"), Campo("iban", "IBAN / CCC"), Campo("bic", "BIC"),
        Campo("cuenta", "Cuenta contable", requerido=True, sugerencias=cuentas_para_listas, ayuda="código completo de la subcuenta, por ejemplo la del banco; debe existir en el plan de cuentas"),
        Campo("saldo_inicial", "Saldo inicial", "dinero", ayuda="el de la apertura del ejercicio"),
        Campo("orden", "Orden en las listas", "numero", ayuda="1 = el primero que sale al elegir banco en todas las pantallas; vacío = detrás de los ordenados, por su número"),
    ]

    def filas(self, ctx, params):
        movs = {bid: (n, total or CERO) for bid, n, total in ctx.sesion.execute(
            select(MovimientoBanco.banco_id, func.count(func.distinct(MovimientoBanco.id)), func.sum(Pago.importe))
            .outerjoin(Pago, Pago.movimiento_id == MovimientoBanco.id).where(MovimientoBanco.ejercicio_id == ctx.ejercicio.id).group_by(MovimientoBanco.banco_id))}
        cuentas = {cid: (d or CERO) - (h or CERO) for cid, d, h in ctx.sesion.execute(
            select(Apunte.cuenta_id, func.sum(Apunte.debe), func.sum(Apunte.haber)).join(Asiento, Asiento.id == Apunte.asiento_id)
            .where(Asiento.ejercicio_id == ctx.ejercicio.id, func.coalesce(Asiento.subtipo, "") != "Z").group_by(Apunte.cuenta_id))}
        filas = []
        for b in _bancos(ctx):
            n, total = movs.get(b.id, (0, CERO))
            saldo_mov, saldo_cuenta = b.saldo_inicial + total, cuentas.get(b.cuenta_id, CERO)
            filas.append(Fila(str(b.id), dict(numero=b.numero, orden=b.orden, nombre=b.nombre, sucursal=b.sucursal, iban=b.iban, bic=b.bic, cuenta=b.cuenta.codigo if b.cuenta else None,
                                              inicial=b.saldo_inicial, movimientos=n, saldo_mov=saldo_mov, saldo_cuenta=saldo_cuenta, diferencia=(saldo_cuenta - saldo_mov) or None),
                            clase="aviso-fila" if saldo_cuenta != saldo_mov else ""))
        return filas

    def valores_formulario(self, ctx, id):
        b = ctx.sesion.get(Banco, int(id))
        return {"nombre": b.nombre, "sucursal": b.sucursal, "iban": b.iban, "bic": b.bic, "cuenta": b.cuenta.codigo if b.cuenta else "", "saldo_inicial": b.saldo_inicial, "orden": b.orden}

    def guardar(self, ctx, id, datos):
        extra = dict(iban=datos["iban"], bic=datos["bic"], sucursal=datos["sucursal"], saldo_inicial=datos["saldo_inicial"] or CERO, orden=datos.get("orden"))
        if id is None:
            return str(svc.crear_banco(ctx.sesion, ctx.empresa.id, datos["nombre"], datos["cuenta"], **extra).id)
        banco = ctx.sesion.get(Banco, int(id))
        if banco is None or banco.empresa_id != ctx.empresa.id:
            raise ErrorContable("El banco no existe")
        svc.modificar_banco(ctx.sesion, banco, datos["nombre"], datos["cuenta"], **extra)
        return id

    def eliminar(self, ctx, ids):
        for i in ids:
            banco = ctx.sesion.get(Banco, int(i))
            if banco is None or banco.empresa_id != ctx.empresa.id:
                raise ErrorContable("El banco no existe")
            svc.borrar_banco(ctx.sesion, banco)

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("inicial", "saldo_mov", "saldo_cuenta")}


# ------------------------------------------------------------------------------------------------ movimientos


@dataclass
class LineaMov:
    tipo: str = "V"  # V salda un vencimiento · C va a una cuenta · P pendiente de aplicar
    venc: str = ""
    cuenta: str = ""
    importe: str = ""
    auto: str = "1"  # «1» mientras el importe lo propone el programa (el pendiente del vencimiento)


@dataclass
class EstadoMov:
    id: int | None = None
    banco: str = ""
    fecha: str = ""
    texto: str = ""
    lineas: list[LineaMov] = field(default_factory=list)
    quitar_adjuntos: set[int] = field(default_factory=set)
    total: Decimal = CERO
    asiento: list[tuple[str, str, Decimal, Decimal]] = field(default_factory=list)  # vista previa: (cuenta, nombre, debe, haber)
    solo_lectura: str = ""  # motivo por el que no se puede editar


_LINEA = re.compile(r"ln-(\d+)-(\w+)")


def estado_vacio(ctx: Contexto, banco: str = "") -> EstadoMov:
    hoy = date.today()
    fecha = hoy if ctx.ejercicio.fecha_inicio <= hoy <= ctx.ejercicio.fecha_fin else ctx.ejercicio.fecha_inicio
    bancos = _bancos(ctx)
    return EstadoMov(banco=banco or (str(bancos[0].id) if bancos else ""), fecha=fecha_texto(fecha), lineas=[LineaMov(tipo="C")])


def estado_de_movimiento(ctx: Contexto, m: MovimientoBanco) -> EstadoMov:
    # el texto automático se deja en blanco para que se regenere con las líneas; uno heredado de MGD (con otro formato) se conserva tal cual
    automatico = m.texto_automatico and m.texto == svc.texto_automatico(m)
    e = EstadoMov(id=m.id, banco=str(m.banco_id), fecha=fecha_texto(m.fecha), texto="" if automatico else m.texto)
    for p in m.pagos:
        if p.vencimiento_id:
            e.lineas.append(LineaMov("V", str(p.vencimiento_id), "", texto_dinero(p.importe), "0"))
        elif p.cuenta_directa is not None:
            e.lineas.append(LineaMov("C", "", p.cuenta_directa.codigo, texto_dinero(p.importe), "0"))
        else:
            e.lineas.append(LineaMov("P", "", "", texto_dinero(p.importe), "0"))
    if m.banco.clase != BANCO_NORMAL:
        e.solo_lectura = f"Es un movimiento del banco «{m.banco.nombre}», que gestiona el sistema"
    elif any(p.movimiento_contraparte_id for p in m.pagos) or ctx.sesion.scalar(select(Pago.id).where(Pago.movimiento_contraparte_id == m.id)):
        e.solo_lectura = "Es una de las dos mitades de una transferencia: bórrela y vuelva a crearla para cambiarla"
    return e


def estado_de_formulario(items) -> EstadoMov:
    simples: dict[str, str] = {}
    lineas: dict[int, dict[str, str]] = defaultdict(dict)
    quitar: set[int] = set()
    for clave, valor in items:
        if not isinstance(valor, str):
            continue
        m = _LINEA.fullmatch(clave)
        if m:
            lineas[int(m.group(1))][m.group(2)] = valor
        elif clave == "quitar_adjunto" and valor.isdigit():
            quitar.add(int(valor))
        else:
            simples[clave] = valor
    e = EstadoMov(id=int(simples["id"]) if simples.get("id", "").isdigit() else None, banco=simples.get("banco", ""), fecha=simples.get("fecha", ""),
                  texto=simples.get("texto", ""), quitar_adjuntos=quitar)
    for i in sorted(lineas):
        d = lineas[i]
        e.lineas.append(LineaMov(tipo=d.get("tipo", "V") if d.get("tipo") in ("V", "C", "P") else "V", venc=d.get("venc", ""), cuenta=d.get("cuenta", ""),
                                 importe=d.get("importe", ""), auto=d.get("auto", "1")))
    return e


def aplicar_accion(e: EstadoMov, accion: str) -> None:
    if accion == "add-ln":
        e.lineas.append(LineaMov())
    elif (m := re.fullmatch(r"del-ln-(\d+)", accion)) and 0 <= int(m.group(1)) < len(e.lineas):
        del e.lineas[int(m.group(1))]


def completar(ctx: Contexto, e: EstadoMov) -> None:
    """Propone el importe de los vencimientos elegidos (su pendiente), suma el total y calcula el asiento que saldría."""
    pagado = _pagado_por_vencimiento(ctx)
    propios: dict[int, Decimal] = defaultdict(lambda: CERO)
    if e.id:
        m = ctx.sesion.get(MovimientoBanco, e.id)
        for p in (m.pagos if m else []):
            if p.vencimiento_id:
                propios[p.vencimiento_id] += p.importe
    banco = ctx.sesion.get(Banco, int(e.banco)) if e.banco.isdigit() else None
    asiento: dict[str, Decimal] = defaultdict(lambda: CERO)
    total = CERO
    pendiente_aplicar = None
    for l in e.lineas:
        v = ctx.sesion.get(Vencimiento, int(l.venc)) if l.tipo == "V" and l.venc.isdigit() else None
        if v is not None and (l.auto == "1" or not l.importe.strip()):
            l.importe, l.auto = texto_dinero(v.importe - (pagado.get(v.id, CERO) - propios.get(v.id, CERO))), "1"
        try:
            importe = dinero_opcional(l.importe, "Importe") or CERO
        except ValueError:
            continue
        total += importe
        if l.tipo == "V" and v is not None:
            cuenta = cuenta_efectiva(v)
            codigo = cuenta.codigo if cuenta else "?"
        elif l.tipo == "C":
            codigo = l.cuenta.strip() or "?"
        elif l.tipo == "P":
            try:
                pendiente_aplicar = pendiente_aplicar or cuenta_pendiente_de_aplicar(ctx.sesion, ctx.empresa.id)
            except ValueError:
                pendiente_aplicar = "?"
            codigo = pendiente_aplicar
        else:
            continue
        asiento[codigo] -= importe
    if banco is not None and banco.cuenta is not None and total != 0:
        asiento[banco.cuenta.codigo] += total
    nombres = {c: n for c, n in ctx.sesion.execute(select(Cuenta.codigo, Cuenta.nombre).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo.in_(list(asiento))))}
    e.total = total
    e.asiento = [(c, nombres.get(c, ""), v if v > 0 else CERO, -v if v < 0 else CERO) for c, v in sorted(asiento.items()) if v != 0]


def construir_y_grabar(ctx: Contexto, e: EstadoMov, ficheros: list):
    errores: list[str] = []
    completar(ctx, e)
    banco = ctx.sesion.get(Banco, int(e.banco)) if e.banco.isdigit() else None
    if banco is None or banco.empresa_id != ctx.empresa.id or banco.clase != BANCO_NORMAL:
        errores.append("Elija el banco")
    fecha = None
    try:
        fecha = introducir_fecha(e.fecha, ctx.ejercicio)
    except ErrorContable as ex:
        errores.append(f"Fecha: {ex}")
    previo = None
    if e.id:
        previo = ctx.sesion.get(MovimientoBanco, e.id)
        if previo is None or previo.ejercicio_id != ctx.ejercicio.id:
            return None, ["El movimiento no existe"], []
        motivo = estado_de_movimiento(ctx, previo).solo_lectura
        if motivo:
            return None, [motivo], []
    lineas: list[svc.LineaPago] = []
    for n, l in enumerate(e.lineas, start=1):
        try:
            importe = dinero_opcional(l.importe, f"Importe de la línea {n}")
        except ValueError as ex:
            errores.append(str(ex))
            continue
        if l.tipo == "V":
            v = ctx.sesion.get(Vencimiento, int(l.venc)) if l.venc.isdigit() else None
            if v is None or v.ejercicio_id != ctx.ejercicio.id:
                errores.append(f"Línea {n}: elija el vencimiento que se salda")
                continue
        if not importe:
            errores.append(f"Falta el importe de la línea {n}")
            continue
        if l.tipo == "V":
            lineas.append(svc.LineaPago(importe, v))
        elif l.tipo == "C":
            if id_de_cuenta(ctx, l.cuenta, f"la línea {n}", errores) is not None:
                lineas.append(svc.LineaPago(importe, cuenta_directa=l.cuenta.strip()))
        else:
            lineas.append(svc.LineaPago(importe))
    if not e.lineas:
        errores.append("Añada al menos una línea")
    if errores:
        return None, errores, []
    r = svc.registrar_movimiento(ctx.sesion, ctx.ejercicio, banco, fecha, lineas, texto=e.texto.strip(), clave=previo.clave if previo else "", movimiento=previo)
    advertencias = list(r.advertencias)
    advertencias += guardar_justificantes(ctx, r.movimiento, e.quitar_adjuntos, ficheros)
    return r.movimiento, [], advertencias


class ListadoMovimientos(Listado):
    nombre, titulo = "movimientos", "Movimientos de banco"
    descripcion = "Cobros, pagos y transferencias, con el saldo de cada banco tras cada movimiento. Su asiento se genera solo."
    formulario_propio = True
    anadir = borrar = editable = True
    columnas = [
        Col("numero", "Nº", ENTERO, 0.6), Col("fecha", "Fecha", FECHA, 1.1), Col("banco", "Banco", TEXTO, 2), Col("texto", "Texto", TEXTO, 4), Col("lineas", "Líneas", ENTERO, 0.7),
        Col("importe", "Importe", DINERO, 1.3), Col("saldo", "Saldo del banco", DINERO, 1.4), Col("tipo", "Tipo", TEXTO, 1.1), Col("justificantes", "Justif.", ENTERO, 0.7),
    ]
    parametros = [
        Campo("banco", "Banco", "select", opciones=lambda ctx: [(str(b.id), b.nombre) for b in _bancos_ordenados(ctx)]),
        Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha"),
    ]
    acciones_extra = [("⇄ Transferencia", "accion/transferencia")]

    def texto_vacio(self, ctx, params):
        return "Esta empresa no tiene bancos" if not _bancos_ordenados(ctx) else "Este banco no tiene movimientos en el ejercicio"

    def filas(self, ctx, params):
        if not params.get("banco"):  # la pantalla trabaja con un solo banco: por defecto, el primero
            primero = next(iter(_bancos_ordenados(ctx)), None)
            params = {**params, "banco": str(primero.id) if primero else "0"}
        movs = list(ctx.sesion.scalars(
            select(MovimientoBanco).where(MovimientoBanco.ejercicio_id == ctx.ejercicio.id)
            .options(selectinload(MovimientoBanco.pagos), selectinload(MovimientoBanco.banco))
            .order_by(MovimientoBanco.fecha, MovimientoBanco.clave, MovimientoBanco.numero)
        ))
        espejos = {p.movimiento_contraparte_id for m in movs for p in m.pagos if p.movimiento_contraparte_id}
        just = {mid: n for mid, n in ctx.sesion.execute(select(Adjunto.movimiento_banco_id, func.count()).where(Adjunto.movimiento_banco_id.is_not(None), Adjunto.sha256.is_not(None)).group_by(Adjunto.movimiento_banco_id))}
        bancos = {b.id: b for b in _bancos(ctx, solo_normales=False)}
        por_cuenta = {b.cuenta_id: b for b in bancos.values() if b.clase == BANCO_NORMAL and b.cuenta_id}
        # el saldo de cada banco arranca en lo que su asiento de apertura pone en su cuenta; sin apertura, en el saldo inicial de su ficha
        apertura = {cid: (d or CERO) - (h or CERO) for cid, d, h in ctx.sesion.execute(
            select(Apunte.cuenta_id, func.sum(Apunte.debe), func.sum(Apunte.haber)).join(Asiento).where(Asiento.ejercicio_id == ctx.ejercicio.id, Asiento.subtipo == "A").group_by(Apunte.cuenta_id))}
        saldos: dict[int, Decimal] = {}
        filas = []

        def anotar(m, banco, importe, tipo):
            saldos[banco.id] = saldos.get(banco.id, apertura.get(banco.cuenta_id, banco.saldo_inicial)) + importe
            if params.get("banco") and str(banco.id) != params["banco"]:
                return
            if params.get("desde") and m.fecha < params["desde"] or params.get("hasta") and m.fecha > params["hasta"]:
                return
            filas.append(Fila(str(m.id), dict(numero=m.numero, fecha=m.fecha, banco=banco.nombre, texto=m.texto, lineas=len(m.pagos), importe=importe, saldo=saldos[banco.id],
                                              tipo=tipo, justificantes=just.get(m.id, 0))))

        for m in movs:
            importe = sum((p.importe for p in m.pagos), CERO)
            tipo = "Transferencia" if (m.id in espejos or any(p.movimiento_contraparte_id for p in m.pagos)) else {"C": "Compensación", "R": "Remesa"}.get(m.banco.clase, "")
            anotar(m, m.banco, importe, tipo)
            # un traspaso de un solo asiento (el del programa anterior) también es un movimiento del banco que recibe
            for p in m.pagos:
                destino = por_cuenta.get(p.cuenta_directa_id)
                if destino is not None and destino.id != m.banco_id and p.movimiento_contraparte_id is None:
                    anotar(m, destino, -p.importe, "Transferencia (entrada)")
        return filas

    def totales(self, filas):
        return {"importe": sum((f.valores.get("importe") or CERO for f in filas), CERO)}

    # ---- formulario
    def formulario(self, ctx, id, estado=None, errores=None):
        if estado is None:
            if id:
                m = ctx.sesion.get(MovimientoBanco, int(id))
                if m is None or m.ejercicio_id != ctx.ejercicio.id:
                    raise ErrorContable("El movimiento no existe")
                estado = estado_de_movimiento(ctx, m)
            else:
                estado = estado_vacio(ctx)
            completar(ctx, estado)
        return "_movimiento.html", self._contexto(ctx, estado, errores or [])

    def _contexto(self, ctx, e: EstadoMov, errores):
        elegidos = {int(l.venc) for l in e.lineas if l.tipo == "V" and l.venc.isdigit()}
        pagado = _pagado_por_vencimiento(ctx)
        propios: dict[int, Decimal] = defaultdict(lambda: CERO)
        if e.id:
            m = ctx.sesion.get(MovimientoBanco, e.id)
            for p in (m.pagos if m else []):
                if p.vencimiento_id:
                    propios[p.vencimiento_id] += p.importe
        opciones = []
        for v, pte in _vencimientos_con_pendiente(ctx):
            antes = pte + propios.get(v.id, CERO)  # lo que quedaba antes de este movimiento
            if antes != 0 or v.id in elegidos:
                opciones.append((v.id, _etiqueta(v, antes)))
        adjuntos = list(ctx.sesion.scalars(select(Adjunto).where(Adjunto.movimiento_banco_id == e.id).order_by(Adjunto.orden))) if e.id else []
        return dict(e=e, errores=errores, bancos=_bancos(ctx), vencimientos=opciones, cuentas=cuentas_para_listas(ctx), adjuntos=adjuntos)

    def recalcular(self, ctx, items):
        e = estado_de_formulario(items)
        aplicar_accion(e, next((v for k, v in items if k == "accion" and isinstance(v, str)), ""))
        completar(ctx, e)
        return "_movimiento_cuerpo.html", self._contexto(ctx, e, [])

    def guardar_formulario(self, ctx, items, ficheros):
        e = estado_de_formulario(items)
        try:
            movimiento, errores, advertencias = construir_y_grabar(ctx, e, ficheros)
        except (ErrorContable, ValueError) as ex:
            movimiento, errores, advertencias = None, [str(ex)], []
        if errores:
            ctx.sesion.rollback()
            try:
                completar(ctx, e)
            except (ErrorContable, ValueError):
                pass
            return None, "_movimiento.html", self._contexto(ctx, e, errores), []
        ctx.sesion.commit()
        return str(movimiento.id), None, None, advertencias

    def eliminar(self, ctx, ids):
        almacen = ctx.config.almacen_de_adjuntos()
        for i in ids:
            m = ctx.sesion.get(MovimientoBanco, int(i))
            if m is None or m.ejercicio_id != ctx.ejercicio.id:
                raise ErrorContable("El movimiento no existe")
            for adj in list(svc_adjuntos.listar(ctx.sesion, m)):
                svc_adjuntos.quitar(ctx.sesion, almacen, ctx.ejercicio, adj)
            ctx.sesion.expire(m, ["pagos"])
            svc.eliminar_movimiento(ctx.sesion, ctx.ejercicio, m)

    # ---- transferencia entre bancos
    def accion(self, ctx, accion, items):
        if accion != "transferencia":
            raise ErrorContable("Acción desconocida")
        bancos = _bancos(ctx)
        hoy = date.today()
        base = dict(bancos=bancos, errores=[], valores=dict(origen="", destino="", fecha=fecha_texto(hoy if ctx.ejercicio.fecha_inicio <= hoy <= ctx.ejercicio.fecha_fin else ctx.ejercicio.fecha_inicio), importe="", texto=""))
        if items is None:
            return "_transferencia.html", base
        datos = {k: v for k, v in items if isinstance(v, str)}
        base["valores"] = {k: datos.get(k, "") for k in base["valores"]}
        try:
            origen = ctx.sesion.get(Banco, int(datos["origen"])) if datos.get("origen", "").isdigit() else None
            destino = ctx.sesion.get(Banco, int(datos["destino"])) if datos.get("destino", "").isdigit() else None
            if origen is None or destino is None:
                raise ErrorContable("Elija el banco de origen y el de destino")
            importe = dinero_opcional(datos.get("importe", ""), "Importe")
            if not importe:
                raise ErrorContable("Falta el importe")
            fecha = introducir_fecha(datos.get("fecha", ""), ctx.ejercicio)
            svc.transferir(ctx.sesion, ctx.ejercicio, origen, destino, fecha, importe, texto=datos.get("texto", "").strip())
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            base["errores"] = [str(ex)]
            return "_transferencia.html", base
        return None, {"mensaje": "Transferencia registrada"}


# ------------------------------------------------------------------------------------------------ vencimientos (cartera)


class ListadoVencimientos(Listado):
    nombre, titulo = "vencimientos", "Vencimientos pendientes"
    descripcion = "Lo que queda por cobrar y por pagar. Doble clic en uno para cobrarlo, pagarlo, compensarlo o cambiar su fecha."
    formulario_propio = True
    editable = True
    columnas = [
        Col("tipo", "Origen", TEXTO, 0.8), Col("documento", "Documento", ENTERO, 0.9), Col("tercero", "Tercero", TEXTO, 3), Col("fecha", "Vencimiento", FECHA, 1.1),
        Col("importe", "Importe", DINERO, 1.2), Col("pagado", "Cobrado/pagado", DINERO, 1.3), Col("pendiente", "Pendiente", DINERO, 1.2), Col("cuenta", "Cuenta", TEXTO, 1.2),
        Col("banco", "Banco previsto", TEXTO, 2), Col("forma", "Forma de pago", TEXTO, 1.4), Col("estado", "Estado", TEXTO, 1),
    ]
    parametros = [
        Campo("estado", "Mostrar", "select", opciones=[("pendientes", "Pendientes"), ("todos", "Todos"), ("pagados", "Saldados")], defecto="pendientes"),
        Campo("origen", "Origen", "select", opciones=[("", "Todos"), ("R", "Facturas recibidas (a pagar)"), ("E", "Facturas emitidas (a cobrar)"), ("X", "Asientos manuales"), ("B", "Remesas")]),
        Campo("desde", "Vence desde", "fecha"), Campo("hasta", "Vence hasta", "fecha"),
    ]

    def filas(self, ctx, params):
        estado = params.get("estado") or "pendientes"
        filas = []
        for v, pte in _vencimientos_con_pendiente(ctx):
            if estado == "pendientes" and pte == 0 or estado == "pagados" and pte != 0:
                continue
            if params.get("origen") and v.origen_tipo != params["origen"]:
                continue
            if v.fecha and (params.get("desde") and v.fecha < params["desde"] or params.get("hasta") and v.fecha > params["hasta"]):
                continue
            cuenta = cuenta_efectiva(v)
            vencido = pte != 0 and v.fecha is not None and v.fecha < date.today()
            filas.append(Fila(str(v.id), dict(
                tipo=v.origen_tipo, documento=v.origen_numero, tercero=_nombre_de(v), fecha=v.fecha, importe=v.importe, pagado=v.importe - pte, pendiente=pte,
                cuenta=cuenta.codigo if cuenta else None, banco=v.banco_previsto.nombre if v.banco_previsto else None, forma=v.forma_pago.texto if v.forma_pago else None,
                estado="Saldado" if pte == 0 else ("Vencido" if vencido else "Pendiente"),
            ), clase="aviso-fila" if vencido else ""))
        return filas

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("importe", "pagado", "pendiente")}

    def formulario(self, ctx, id, estado=None, errores=None, valores=None):
        v = ctx.sesion.get(Vencimiento, int(id)) if id else None
        if v is None or v.ejercicio_id != ctx.ejercicio.id:
            raise ErrorContable("El vencimiento no existe")
        pte = v.importe - _pagado_por_vencimiento(ctx).get(v.id, CERO)
        pagos = [(p.movimiento.numero, p.movimiento.fecha, p.movimiento.banco.nombre, p.importe) for p in sorted(v.pagos, key=lambda p: (p.movimiento.fecha, p.movimiento.numero))]
        valores = valores or dict(fecha=fecha_texto(v.fecha), forma=str(v.forma_pago.id) if v.forma_pago else "", banco_previsto=str(v.banco_previsto.id) if v.banco_previsto else "",
                                  banco=str(v.banco_previsto.id) if v.banco_previsto else "", fecha_pago=fecha_texto(v.fecha or date.today()), importe=texto_dinero(pte), texto="", cuenta="")
        cuenta = cuenta_efectiva(v)
        ficha = [("Origen", f"{v.origen_tipo} {v.origen_numero}"), ("Tercero", _nombre_de(v)), ("Cuenta", f"{cuenta.codigo} {cuenta.nombre}" if cuenta else ""),
                 ("Importe", texto_dinero(v.importe)), ("Pendiente", texto_dinero(pte))]
        return "_vencimiento.html", dict(
            v=v, pte=pte, pagos=pagos, ficha=ficha, errores=errores or [], valores=valores, bancos=_bancos(ctx), formas=list(ctx.sesion.scalars(select(FormaPago).where(FormaPago.empresa_id == ctx.empresa.id).order_by(FormaPago.numero_origen))),
            cuentas=cuentas_para_listas(ctx), sentido="cobrar" if v.importe > 0 else "pagar",
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        v = ctx.sesion.get(Vencimiento, int(datos["id"])) if datos.get("id", "").isdigit() else None
        if v is None or v.ejercicio_id != ctx.ejercicio.id:
            return None, "_vencimiento.html", None, []
        accion, advertencias = datos.get("accion", "guardar"), []
        try:
            if accion in ("pagar", "compensar"):
                fecha = introducir_fecha(datos.get("fecha_pago", ""), ctx.ejercicio)
                if accion == "pagar":
                    banco = ctx.sesion.get(Banco, int(datos["banco"])) if datos.get("banco", "").isdigit() else None
                    if banco is None:
                        raise ErrorContable("Elija el banco")
                    importe = dinero_opcional(datos.get("importe", ""), "Importe")
                    r = svc.pagar_vencimiento(ctx.sesion, ctx.ejercicio, v, banco, fecha, importe=importe, texto=datos.get("texto", "").strip())
                else:
                    errores_cuenta: list[str] = []
                    if id_de_cuenta(ctx, datos.get("cuenta", ""), "la compensación", errores_cuenta) is None:
                        raise ErrorContable(errores_cuenta[0])
                    r = svc.compensar_vencimiento(ctx.sesion, ctx.ejercicio, v, datos["cuenta"].strip(), fecha, texto=datos.get("texto", "").strip())
                advertencias += r.advertencias
            else:  # cambios en el propio vencimiento
                if ctx.ejercicio.cerrado:
                    raise ErrorContable(f"El ejercicio {ctx.ejercicio.anio} está cerrado")
                v.fecha = parsear_fecha(datos["fecha"], referencia=ctx.ejercicio.fecha_inicio) if datos.get("fecha", "").strip() else None
                v.forma_pago = ctx.sesion.get(FormaPago, int(datos["forma"])) if datos.get("forma", "").isdigit() else None
                v.banco_previsto = ctx.sesion.get(Banco, int(datos["banco_previsto"])) if datos.get("banco_previsto", "").isdigit() else None
                ctx.sesion.flush()
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, v.id, errores=[str(ex)], valores={**{k: datos.get(k, "") for k in ("fecha", "forma", "banco_previsto", "banco", "fecha_pago", "importe", "texto", "cuenta")}})
            return None, plantilla, contexto, []
        return str(v.id), None, None, advertencias
