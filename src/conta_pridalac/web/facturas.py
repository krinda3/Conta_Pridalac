"""Facturas recibidas y emitidas en la web: listado y formulario con líneas de IVA, ajustes, vencimientos y justificantes.

El formulario es del servidor: cada cambio (tipo de IVA, base, tercero, añadir o quitar una línea) vuelve a
calcular cuotas, total y vencimientos con las mismas reglas que el resto de la aplicación y devuelve el cuerpo del formulario
renderizado. Al guardar se graba la factura, se regeneran sus asientos y sus vencimientos y se suben los justificantes, todo en
una sola transacción: si algo falla no se guarda nada.
"""
from __future__ import annotations

import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import func, select

from conta_pridalac.db.modelos import Adjunto, Banco, Cuenta, ExtractoLinea, Factura, FacturaAjuste, FacturaIva, FormaPago, Tercero, TipoIva, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha, validar_en_ejercicio
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO
from conta_pridalac.servicios import categorias_gasto as svc_categorias
from conta_pridalac.servicios import adjuntos as svc_adjuntos
from conta_pridalac.servicios import importar_facturas as svc_importar
from conta_pridalac.servicios.bloqueo import exigir_factura_libre
from conta_pridalac.servicios.facturas import buscar_posible_duplicada, eliminar_factura, grabar_factura
from conta_pridalac.servicios.tesoreria import ORDEN_DE_BANCOS
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, definir_vencimientos, signo
from conta_pridalac.web.comun import (
    codigo_de_cuenta as _codigo,
    cuentas_para_listas,
    dinero_opcional as _dinero_opcional,
    fecha_texto as _fecha_texto,
    guardar_justificantes,
    id_de_cuenta as _cuenta_id,
    redondear as _redondear,
    texto_dinero as _texto_dinero,
)
from conta_pridalac.web.listados import Campo, Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
CONTRAS = [("G", "Gasto"), ("I", "Ingreso"), ("P", "Proveedor"), ("C", "Cliente")]


# ------------------------------------------------------------------------------------------------ estado del formulario


@dataclass
class LineaIva:
    tipo: str = ""  # número del tipo de IVA del catálogo
    tipo_previo: str = ""
    base: str = ""
    pct: str = ""
    cuota: str = ""
    auto: str = "1"  # «1» mientras la cuota la calcula el programa; pasa a «0» cuando se teclea
    cuenta: str = ""
    pct_rec: str = "0,00"
    cuota_rec: str = ""
    cuenta_rec: str = ""
    deducible: bool = True
    bien: bool = False


@dataclass
class LineaAjuste:
    cuenta: str = ""
    importe: str = ""
    contra: str = "G"
    afecta_iva: bool = False
    decl: bool = False


@dataclass
class LineaPlazo:
    fecha: str = ""
    importe: str = ""
    forma: str = ""  # forma de pago de la ficha (ya no se elige aquí, pero se respeta la que traía el vencimiento)
    banco: str = ""  # id del banco o tarjeta con el que se prevé pagar
    cuenta: str = ""  # sólo en los plazos de una retención
    pagos: bool = False  # ya tiene cobros o pagos: no se quita
    vid: str = ""  # id del vencimiento guardado (para enseñar sus pagos); vacío en uno nuevo


@dataclass
class Estado:
    sentido: str
    id: int | None = None
    fecha_contable: str = ""
    fecha_factura: str = ""
    numero_factura: str = ""
    tercero: str = ""
    tercero_previo: str = ""
    tercero_texto: str | None = None  # lo que se ve y se teclea en el buscador del tercero
    aviso_tercero: str = ""
    cuenta_tercero: str = ""
    contrapartida: str = ""
    concepto: str = ""
    notas: str = ""
    ivas: list[LineaIva] = field(default_factory=list)
    ajustes: list[LineaAjuste] = field(default_factory=list)
    plazos: list[LineaPlazo] = field(default_factory=list)
    plazos_auto: bool = True
    quitar_adjuntos: set[int] = field(default_factory=set)
    confirmar_duplicada: bool = False  # se marcó «grabar de todos modos» tras el aviso de posible duplicada
    hay_duplicada: bool = False  # el último intento de grabar se paró por una posible duplicada
    # derivados (se calculan en `completar`)
    total: Decimal | None = None
    a_vencer: Decimal | None = None
    suma_plazos: Decimal | None = None










# ------------------------------------------------------------------------------------------------ catálogos


def _tipos_iva(ctx: Contexto, sentido: str) -> list[TipoIva]:
    return list(ctx.sesion.scalars(select(TipoIva).where(TipoIva.empresa_id == ctx.empresa.id, TipoIva.sentido == sentido, TipoIva.inactivo.is_(False)).order_by(TipoIva.numero)))


def _tipo_por_defecto(ctx: Contexto, sentido: str) -> TipoIva | None:
    """El tipo marcado por defecto; si ninguno lo está, el más usado en las facturas ya grabadas; si no hay, el primero del catálogo."""
    tipos = _tipos_iva(ctx, sentido)
    marcado = next((t for t in tipos if t.por_defecto), None)
    if marcado or not tipos:
        return marcado
    usados = ctx.sesion.execute(
        select(FacturaIva.pct_iva, FacturaIva.cuenta_iva_id, func.count()).join(Factura).where(Factura.sentido == sentido).group_by(FacturaIva.pct_iva, FacturaIva.cuenta_iva_id).order_by(func.count().desc())
    ).all()
    por_clave = {(t.pct_iva, t.cuenta_iva_id): t for t in tipos}
    return next((por_clave[(pct, cuenta)] for pct, cuenta, _ in usados if (pct, cuenta) in por_clave), tipos[0])


def etiqueta_tercero(t: Tercero) -> str:
    return f"{t.nombre} · {t.nif}" if t.nif else t.nombre


def resolver_tercero(ctx: Contexto, e: Estado) -> None:
    """El buscador del tercero es un campo de texto: si lo escrito no es el tercero que ya está elegido, se busca entre los de la clase
    (texto exacto, o una única coincidencia por parte del nombre o del NIF) y se deja elegido; vacío quita el tercero."""
    e.aviso_tercero = ""
    actual = ctx.sesion.get(Tercero, int(e.tercero)) if e.tercero.isdigit() else None
    if e.tercero_texto is None or (actual is not None and e.tercero_texto.strip() == etiqueta_tercero(actual)):  # sin buscador en el envío, o no se ha tocado
        e.tercero_texto = etiqueta_tercero(actual) if actual is not None else ""
        return
    texto = e.tercero_texto.strip()
    if not texto:
        e.tercero = ""
        return
    candidatos = _terceros(ctx, e.sentido)
    clave = texto.casefold()
    exactos = [t for t in candidatos if clave in (etiqueta_tercero(t).casefold(), t.nombre.casefold())]
    parciales = exactos or [t for t in candidatos if clave in etiqueta_tercero(t).casefold()]
    if len(parciales) == 1:
        e.tercero = str(parciales[0].id)
        e.tercero_texto = etiqueta_tercero(parciales[0])
        return
    e.tercero = ""
    nombre, plural = ("proveedor", "proveedores") if e.sentido == "R" else ("cliente", "clientes")
    e.aviso_tercero = f"Hay varios {plural} que coinciden con «{texto}»: elija uno de la lista" if parciales else f"No hay ningún {nombre} que coincida con «{texto}»"


def _terceros(ctx: Contexto, sentido: str) -> list[Tercero]:
    clase = "P" if sentido == "R" else "C"
    return list(ctx.sesion.scalars(select(Tercero).where(Tercero.empresa_id == ctx.empresa.id, Tercero.clase == clase).order_by(Tercero.nombre)))






# ------------------------------------------------------------------------------------------------ de la factura al estado y del formulario al estado


def estado_vacio(ctx: Contexto, sentido: str) -> Estado:
    e = Estado(sentido=sentido, fecha_contable=_fecha_texto(date.today() if ctx.ejercicio.fecha_inicio <= date.today() <= ctx.ejercicio.fecha_fin else ctx.ejercicio.fecha_inicio))
    por_defecto = _tipo_por_defecto(ctx, sentido)
    e.ivas.append(_linea_de_tipo(ctx, por_defecto) if por_defecto else LineaIva())
    return e


def _con_recargo(ctx: Contexto, e: Estado) -> bool:
    """El recargo de equivalencia sólo se aplica si el tercero está en ese régimen (casilla de su ficha); el tipo de IVA del catálogo sólo dice cuánto es."""
    t = ctx.sesion.get(Tercero, int(e.tercero)) if e.tercero.isdigit() else None
    return bool(t is not None and t.recargo_equivalencia)


def _linea_de_tipo(ctx: Contexto, t: TipoIva, con_recargo: bool = False) -> LineaIva:
    return LineaIva(tipo=str(t.numero), tipo_previo=str(t.numero), pct=_texto_dinero(t.pct_iva), cuenta=_codigo(ctx, t.cuenta_iva_id),
                    pct_rec=_texto_dinero(t.pct_recargo) if con_recargo else "0,00", cuenta_rec=_codigo(ctx, t.cuenta_recargo_id) if con_recargo else "")


def estado_de_factura(ctx: Contexto, f: Factura) -> Estado:
    tipos = {(t.pct_iva, t.cuenta_iva_id): t for t in _tipos_iva(ctx, f.sentido)}
    e = Estado(
        sentido=f.sentido, id=f.id, fecha_contable=_fecha_texto(f.fecha_contable), fecha_factura=_fecha_texto(f.fecha_factura), numero_factura=f.numero_factura or "",
        tercero=str(f.tercero_id or ""), tercero_previo=str(f.tercero_id or ""), cuenta_tercero=_codigo(ctx, f.cuenta_tercero_id), contrapartida=_codigo(ctx, f.cuenta_contrapartida_id),
        concepto=f.concepto or "", notas=f.notas or "", plazos_auto=False,
    )
    for i in f.ivas:
        t = tipos.get((i.pct_iva, i.cuenta_iva_id))
        e.ivas.append(LineaIva(
            tipo=str(t.numero) if t else "", tipo_previo=str(t.numero) if t else "", base=_texto_dinero(i.base), pct=_texto_dinero(i.pct_iva), cuota=_texto_dinero(i.cuota_iva),
            auto="1" if _redondear(i.base * i.pct_iva / 100) == i.cuota_iva else "0",  # una cuota fuera de lo habitual se respeta
            cuenta=_codigo(ctx, i.cuenta_iva_id), pct_rec=_texto_dinero(i.pct_recargo), cuota_rec=_texto_dinero(i.cuota_recargo) if i.cuota_recargo else "",
            cuenta_rec=_codigo(ctx, i.cuenta_recargo_id), deducible=i.deducible, bien=i.bien_inversion,
        ))
    for a in f.ajustes:
        e.ajustes.append(LineaAjuste(cuenta=a.cuenta.codigo, importe=_texto_dinero(a.importe), contra=a.contra, afecta_iva=a.afecta_iva, decl=a.declaracion_terceros))
    s = signo(f)
    for v in sorted(ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)), key=lambda v: v.id):
        e.plazos.append(LineaPlazo(fecha=_fecha_texto(v.fecha), importe=_texto_dinero(s * v.importe), forma=str(v.forma_pago.id) if v.forma_pago else "", banco=str(v.banco_previsto_id or ""),
                                   cuenta=_codigo(ctx, v.cuenta_id), pagos=bool(v.pagos), vid=str(v.id)))
    e.total = f.total
    return e


def _pagos_de_los_vencimientos(ctx: Contexto, e: Estado) -> dict[str, list[tuple]]:
    """Por id de vencimiento: (id del movimiento, fecha, banco, importe, línea del extracto que lo pagó) de cada pago ya hecho."""
    ids = [int(p.vid) for p in e.plazos if p.vid.isdigit() and p.pagos]
    if not ids:
        return {}
    lineas = {l.movimiento_id: l.texto for l in ctx.sesion.scalars(select(ExtractoLinea).where(ExtractoLinea.empresa_id == ctx.empresa.id, ExtractoLinea.movimiento_id.is_not(None)))}
    resultado: dict[str, list[tuple]] = {}
    for v in ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.id.in_(ids))):
        pagos = sorted(v.pagos, key=lambda p: (p.movimiento.fecha, p.movimiento.numero))
        resultado[str(v.id)] = [(p.movimiento_id, p.movimiento.fecha, p.movimiento.banco.nombre, abs(p.importe), lineas.get(p.movimiento_id, "")) for p in pagos]
    return resultado


def estado_de_formulario(items: list[tuple[str, object]], sentido: str) -> Estado:
    """Reconstruye el estado a partir de lo que envía el navegador (los ficheros se ignoran aquí)."""
    simples: dict[str, str] = {}
    listas: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
    quitar: set[int] = set()
    for clave, valor in items:
        if not isinstance(valor, str):
            continue
        m = re.fullmatch(r"(iva|aj|pl)-(\d+)-(\w+)", clave)
        if m:
            listas[(m.group(1), int(m.group(2)))][m.group(3)] = valor
        elif clave == "quitar_adjunto" and valor.isdigit():
            quitar.add(int(valor))
        else:
            simples[clave] = valor
    marca = lambda d, k: d.get(k) in ("on", "1", "true")  # noqa: E731
    e = Estado(
        sentido=sentido, id=int(simples["id"]) if simples.get("id", "").isdigit() else None,
        fecha_contable=simples.get("fecha_contable", ""), fecha_factura=simples.get("fecha_factura", ""), numero_factura=simples.get("numero_factura", ""),
        tercero=simples.get("tercero", ""), tercero_previo=simples.get("tercero_previo", ""), tercero_texto=simples.get("tercero_texto"), cuenta_tercero=simples.get("cuenta_tercero", ""),
        contrapartida=simples.get("contrapartida", ""), concepto=simples.get("concepto", ""), notas=simples.get("notas", ""),
        plazos_auto=simples.get("plazos_auto", "1") == "1", quitar_adjuntos=quitar,
        confirmar_duplicada=marca(simples, "confirmar_duplicada"),
    )
    for (tipo, _), d in sorted(((k, v) for k, v in listas.items()), key=lambda kv: (kv[0][0], kv[0][1])):
        if tipo == "iva":
            e.ivas.append(LineaIva(tipo=d.get("tipo", ""), tipo_previo=d.get("tipo_previo", ""), base=d.get("base", ""), pct=d.get("pct", ""), cuota=d.get("cuota", ""),
                                   auto=d.get("auto", "1"), cuenta=d.get("cuenta", ""), pct_rec=d.get("pct_rec", "0,00"), cuota_rec=d.get("cuota_rec", ""),
                                   cuenta_rec=d.get("cuenta_rec", ""), deducible=marca(d, "deducible"), bien=marca(d, "bien")))
        elif tipo == "aj":
            e.ajustes.append(LineaAjuste(cuenta=d.get("cuenta", ""), importe=d.get("importe", ""), contra=d.get("contra", "G"), afecta_iva=marca(d, "afecta_iva"), decl=marca(d, "decl")))
        else:
            e.plazos.append(LineaPlazo(fecha=d.get("fecha", ""), importe=d.get("importe", ""), forma=d.get("forma", ""), banco=d.get("banco", ""), cuenta=d.get("cuenta", ""), pagos=d.get("pagos") == "1", vid=d.get("vid", "")))
    return e


# ------------------------------------------------------------------------------------------------ cálculos y acciones


def aplicar_accion(ctx: Contexto, e: Estado, accion: str) -> None:
    if accion == "add-iva":
        por_defecto = _tipo_por_defecto(ctx, e.sentido)
        e.ivas.append(_linea_de_tipo(ctx, por_defecto, _con_recargo(ctx, e)) if por_defecto else LineaIva())
    elif accion.startswith("del-iva-") and accion[8:].isdigit():
        i = int(accion[8:])
        if 0 <= i < len(e.ivas):
            del e.ivas[i]
    elif accion == "add-aj":
        e.ajustes.append(LineaAjuste(contra="G" if e.sentido == "R" else "I"))
    elif accion.startswith("del-aj-") and accion[7:].isdigit():
        i = int(accion[7:])
        if 0 <= i < len(e.ajustes):
            del e.ajustes[i]
    elif accion == "add-pl":
        e.plazos.append(LineaPlazo())
        e.plazos_auto = False
    elif accion.startswith("del-pl-") and accion[7:].isdigit():
        i = int(accion[7:])
        if 0 <= i < len(e.plazos) and not e.plazos[i].pagos:
            del e.plazos[i]
            e.plazos_auto = False


def _ultima_del_tercero(ctx: Contexto, e: Estado) -> Factura | None:
    if not e.tercero.isdigit():
        return None
    return ctx.sesion.scalars(
        select(Factura).where(Factura.tercero_id == int(e.tercero), Factura.sentido == e.sentido).order_by(Factura.fecha_contable.desc(), Factura.numero.desc()).limit(1)
    ).first()


def _ajustar_recargo(ctx: Contexto, e: Estado) -> None:
    """Al elegir tercero: con recargo de equivalencia, las líneas sin recargo toman el del tipo de IVA; sin él, las líneas que traían el del tipo lo pierden."""
    catalogo = {str(t.numero): t for t in _tipos_iva(ctx, e.sentido)}
    con_recargo = _con_recargo(ctx, e)
    for l in e.ivas:
        tipo = catalogo.get(l.tipo)
        if tipo is None or not tipo.pct_recargo:
            continue
        sin_recargo = l.pct_rec.strip() in ("", "0", "0,00")
        if con_recargo and sin_recargo:
            l.pct_rec, l.cuenta_rec, l.cuota_rec = _texto_dinero(tipo.pct_recargo), l.cuenta_rec or _codigo(ctx, tipo.cuenta_recargo_id), ""
        elif not con_recargo and l.pct_rec == _texto_dinero(tipo.pct_recargo):
            l.pct_rec, l.cuenta_rec, l.cuota_rec = "0,00", "", ""


def completar(ctx: Contexto, e: Estado) -> None:
    """Rellena lo que el programa propone (cuentas del tercero, datos del tipo de IVA, cuotas, vencimientos) y calcula los totales."""
    resolver_tercero(ctx, e)
    # al cambiar de tercero se proponen sus cuentas y las de su última factura
    if e.tercero != e.tercero_previo:
        e.tercero_previo = e.tercero
        _ajustar_recargo(ctx, e)
        if e.tercero.isdigit():
            t = ctx.sesion.get(Tercero, int(e.tercero))
            if t is not None:
                e.cuenta_tercero = _codigo(ctx, t.cuenta_id) or e.cuenta_tercero
                ultima = _ultima_del_tercero(ctx, e)
                # la subcuenta de gasto o de ingreso de la ficha manda; si no la tiene, la de su última factura
                e.contrapartida = e.contrapartida or _codigo(ctx, t.cuenta_gasto_id) or (_codigo(ctx, ultima.cuenta_contrapartida_id) if ultima is not None else "")
                primero = (t.tipos_iva_defecto or "").split(",")[0].strip()
                if primero in {str(x.numero) for x in _tipos_iva(ctx, e.sentido)} and e.ivas and not e.ivas[0].tipo:
                    e.ivas[0].tipo = primero
    # datos del tipo de IVA elegido
    catalogo = {str(t.numero): t for t in _tipos_iva(ctx, e.sentido)}
    for l in e.ivas:
        if l.tipo and l.tipo != l.tipo_previo and l.tipo in catalogo:
            nuevo = _linea_de_tipo(ctx, catalogo[l.tipo], _con_recargo(ctx, e))
            l.pct, l.cuenta, l.pct_rec, l.cuenta_rec, l.tipo_previo = nuevo.pct, nuevo.cuenta, nuevo.pct_rec, nuevo.cuenta_rec, l.tipo
            l.auto, l.cuota, l.cuota_rec = "1", "", ""
    # cuotas calculadas
    for l in e.ivas:
        try:
            base, pct, pct_rec = _dinero_opcional(l.base, "Base"), _dinero_opcional(l.pct, "% IVA"), _dinero_opcional(l.pct_rec, "% recargo")
        except ValueError:
            continue
        if base is not None and pct is not None and (l.auto == "1" or not l.cuota.strip()):
            l.cuota, l.auto = _texto_dinero(_redondear(base * pct / 100)), "1"
        if base is not None and pct_rec and (l.auto == "1" or not l.cuota_rec.strip()):
            l.cuota_rec = _texto_dinero(_redondear(base * pct_rec / 100))
        if not pct_rec:
            l.cuota_rec = ""
    # total
    try:
        suma = CERO
        for l in e.ivas:
            suma += (_dinero_opcional(l.base, "Base") or CERO) + (_dinero_opcional(l.cuota, "Cuota") or CERO) + (_dinero_opcional(l.cuota_rec, "Recargo") or CERO)
        ajustes = sum(((_dinero_opcional(a.importe, "Ajuste") or CERO) for a in e.ajustes), CERO)
        e.total = suma + (ajustes if e.sentido == "R" else CERO)
        e.a_vencer = e.total - ajustes
    except ValueError:
        e.total = e.a_vencer = None
    # vencimientos
    if e.plazos_auto or not e.plazos:
        elegidos = [(l.banco, l.forma) for l in e.plazos]  # el banco que se haya elegido no se pierde porque el importe siga al total
        e.plazos = _plazos_propuestos(ctx, e)
        for linea, (banco, forma) in zip(e.plazos, elegidos):
            linea.banco, linea.forma = banco or linea.banco, forma or linea.forma
    try:
        e.suma_plazos = sum((_dinero_opcional(p.importe, "Vencimiento") or CERO for p in e.plazos), CERO)
    except ValueError:
        e.suma_plazos = None


def _plazos_propuestos(ctx: Contexto, e: Estado) -> list[LineaPlazo]:
    """Un vencimiento con el total y uno por cada retención, como en MGD. Si hace falta más de uno, se añaden con «＋ Vencimiento»."""
    if e.total is None:
        return []
    try:
        fecha = parsear_fecha(e.fecha_factura or e.fecha_contable, referencia=ctx.ejercicio.fecha_inicio) if (e.fecha_factura or e.fecha_contable) else None
    except ErrorContable:
        fecha = None
    ajustes = [(a, _dinero_opcional(a.importe, "Ajuste") or CERO) for a in e.ajustes]
    tercero = ctx.sesion.get(Tercero, int(e.tercero)) if e.tercero.isdigit() else None
    forma = str(tercero.forma_pago_id) if tercero is not None and tercero.forma_pago_id else ""
    lineas = [LineaPlazo(fecha=_fecha_texto(fecha), importe=_texto_dinero(e.total), forma=forma)]
    for a, importe in ajustes:
        if importe != 0:
            lineas.append(LineaPlazo(fecha=_fecha_texto(parsear_fecha(e.fecha_contable, referencia=ctx.ejercicio.fecha_inicio)) if e.fecha_contable else "", importe=_texto_dinero(-importe), cuenta=a.cuenta))
    return lineas


def _completar_vencimiento_nuevo(ctx: Contexto, e: Estado) -> None:
    """Tras «＋ Vencimiento»: la línea nueva trae lo que falta para cuadrar con la factura (y la fecha de la anterior), para que sólo haya que ajustar."""
    if not e.plazos or e.plazos[-1].importe.strip() or e.a_vencer is None or e.suma_plazos is None:
        return
    falta = e.a_vencer - e.suma_plazos
    if falta > 0:
        e.plazos[-1].importe = _texto_dinero(falta)
        e.suma_plazos += falta
    if len(e.plazos) > 1 and not e.plazos[-1].fecha.strip():
        e.plazos[-1].fecha = e.plazos[-2].fecha


# ------------------------------------------------------------------------------------------------ guardar


def _aviso_de_duplicada(ctx: Contexto, e: Estado, tercero_id: int | None) -> str:
    """El texto del aviso si la factura parece una que ya existe; vacío si no. Al editar sin cambiar el número ni el tercero no se vuelve a avisar."""
    numero = e.numero_factura.strip()
    if e.id:
        original = ctx.sesion.get(Factura, e.id)
        if original is not None and (original.numero_factura or "").strip().upper() == numero.upper() and original.tercero_id == tercero_id:
            return ""
    d = buscar_posible_duplicada(ctx.sesion, ctx.ejercicio, e.sentido, tercero_id, numero, e.total, excluir_id=e.id)
    if d is None:
        return ""
    f = d.factura
    quien = f"«{f.tercero.nombre}»" if f.tercero is not None else "un tercero sin ficha"
    que = f"nº {f.numero_factura}, {_fecha_texto(f.fecha_factura or f.fecha_contable)}, total {_texto_dinero(f.total)} €"
    if d.motivo == "mismo_tercero":
        return f"Ya existe una factura de {quien} con el número {numero} ({que}). Si es otra factura distinta, marque «Grabar de todos modos»."
    if d.motivo == "mismo_numero":
        return f"Ya existe en este ejercicio la factura emitida {numero} a {quien} ({que}): los números de las emitidas no se repiten. Si es otra factura distinta, marque «Grabar de todos modos»."
    return f"Hay otra factura {numero} de {quien} por el mismo importe ({que}). ¿Es la misma con el tercero mal elegido? Si es otra factura distinta, marque «Grabar de todos modos»."


def construir_y_grabar(ctx: Contexto, e: Estado, ficheros: list) -> tuple[Factura | None, list[str], list[str]]:
    """Valida el formulario, graba la factura con sus asientos, vencimientos y justificantes. Devuelve (factura, errores, advertencias).

    No hace `commit`: lo hace quien llama si no hay errores. Con errores deja la sesión para hacer `rollback`.
    """
    errores: list[str] = []
    completar(ctx, e)
    if e.aviso_tercero:
        errores.append(e.aviso_tercero)
    try:
        fecha_contable = validar_en_ejercicio(parsear_fecha(e.fecha_contable, referencia=ctx.ejercicio.fecha_inicio), ctx.ejercicio)
    except ErrorContable as ex:
        errores.append(f"Fecha contable: {ex}")
        fecha_contable = None
    fecha_factura = None
    if e.fecha_factura.strip():
        try:
            fecha_factura = parsear_fecha(e.fecha_factura, referencia=ctx.ejercicio.fecha_inicio)
        except ErrorContable as ex:
            errores.append(f"Fecha de la factura: {ex}")
    cuenta_tercero = _cuenta_id(ctx, e.cuenta_tercero, "cliente" if e.sentido == "E" else "proveedor", errores)
    contrapartida = _cuenta_id(ctx, e.contrapartida, "ingreso" if e.sentido == "E" else "gasto", errores)
    tercero_id = int(e.tercero) if e.tercero.isdigit() else None
    if not e.ivas:
        errores.append("Añada al menos una línea de IVA (también para operaciones exentas, con 0 %)")
    ivas = []
    for n, l in enumerate(e.ivas, start=1):
        try:
            base, pct, cuota = _dinero_opcional(l.base, f"Base (línea {n})"), _dinero_opcional(l.pct, f"% IVA (línea {n})"), _dinero_opcional(l.cuota, f"Cuota (línea {n})")
            pct_rec, cuota_rec = _dinero_opcional(l.pct_rec, f"% recargo (línea {n})") or CERO, _dinero_opcional(l.cuota_rec, f"Recargo (línea {n})") or CERO
        except ValueError as ex:
            errores.append(str(ex))
            continue
        if base is None:
            errores.append(f"Falta la base de la línea de IVA {n}")
            continue
        pct = CERO if pct is None else pct
        cuenta_iva = _cuenta_id(ctx, l.cuenta, f"IVA (línea {n})", errores, obligatoria=pct != 0 and l.deducible)
        cuenta_rec = _cuenta_id(ctx, l.cuenta_rec, f"recargo (línea {n})", errores, obligatoria=cuota_rec != 0)
        ivas.append(FacturaIva(base=base, pct_iva=pct, cuota_iva=cuota if cuota is not None else CERO, cuenta_iva_id=cuenta_iva, pct_recargo=pct_rec, cuota_recargo=cuota_rec,
                               cuenta_recargo_id=cuenta_rec, deducible=l.deducible, bien_inversion=l.bien))
    ajustes = []
    for n, a in enumerate(e.ajustes, start=1):
        try:
            importe = _dinero_opcional(a.importe, f"Importe del ajuste {n}")
        except ValueError as ex:
            errores.append(str(ex))
            continue
        cuenta = _cuenta_id(ctx, a.cuenta, f"ajuste {n}", errores)
        if importe is None:
            errores.append(f"Falta el importe del ajuste {n}")
        elif cuenta is not None:
            ajustes.append(FacturaAjuste(orden=n, cuenta_id=cuenta, importe=importe, contra=a.contra if a.contra in "CIGP" else "G", afecta_iva=a.afecta_iva, declaracion_terceros=a.decl))
    plazos = []
    for n, p in enumerate(e.plazos, start=1):
        try:
            importe = _dinero_opcional(p.importe, f"Importe del vencimiento {n}")
            fecha = parsear_fecha(p.fecha, referencia=ctx.ejercicio.fecha_inicio) if p.fecha.strip() else None
        except (ValueError, ErrorContable) as ex:
            errores.append(str(ex) if "«" in str(ex) else f"Vencimiento {n}: {ex}")
            continue
        if importe is None:
            errores.append(f"Falta el importe del vencimiento {n}")
            continue
        forma = ctx.sesion.get(FormaPago, int(p.forma)) if p.forma.isdigit() else None
        banco = ctx.sesion.get(Banco, int(p.banco)) if p.banco.isdigit() else None
        plazos.append(PlazoVencimiento(importe=importe, fecha=fecha, cuenta=p.cuenta or None, banco=banco, forma_pago=forma))
    if errores or e.total is None:
        return None, errores or ["Revise los importes"], []

    # ---- ¿ya está grabada? (se avisa y hay que confirmar; no se pisa nada)
    aviso = _aviso_de_duplicada(ctx, e, tercero_id)
    if aviso and not e.confirmar_duplicada:
        e.hay_duplicada = True
        return None, [aviso], []

    # ---- factura
    factura = ctx.sesion.get(Factura, e.id) if e.id else Factura(sentido=e.sentido)
    if factura is None or factura.ejercicio_id not in (None, ctx.ejercicio.id):
        return None, ["La factura no existe en este ejercicio"], []
    try:
        exigir_factura_libre(ctx.sesion, ctx.empresa.id, factura)  # antes de tocar nada: una factura de un trimestre presentado no se modifica
    except ErrorContable as ex:
        return None, [str(ex)], []
    factura.fecha_contable, factura.fecha_factura = fecha_contable, fecha_factura
    factura.numero_factura = e.numero_factura.strip() or None
    factura.tercero_id, factura.cuenta_tercero_id, factura.cuenta_contrapartida_id = tercero_id, cuenta_tercero, contrapartida
    factura.concepto, factura.notas = e.concepto.strip() or None, e.notas.strip() or None
    factura.total = e.total
    factura.ivas.clear()
    factura.ajustes.clear()
    ctx.sesion.flush()
    factura.ivas.extend(ivas)
    factura.ajustes.extend(ajustes)
    advertencias: list[str] = []
    resultado = grabar_factura(ctx.sesion, ctx.ejercicio, factura)
    advertencias += resultado.advertencias
    definir_vencimientos(ctx.sesion, ctx.ejercicio, factura, plazos)

    # ---- justificantes
    advertencias += guardar_justificantes(ctx, factura, e.quitar_adjuntos, ficheros)
    return factura, [], advertencias


# ------------------------------------------------------------------------------------------------ el listado


class ListadoFacturas(Listado):
    formulario_propio = True
    anadir = borrar = editable = True
    sentido = "R"
    columnas = [
        Col("numero", "Nº", ENTERO, 0.6), Col("fecha", "Fecha contable", FECHA, 1.1), Col("fecha_factura", "Fecha factura", FECHA, 1.1), Col("factura", "Nº factura", TEXTO, 1.4),
        Col("tercero", "Tercero", TEXTO, 3), Col("nif", "NIF", TEXTO, 1.2), Col("contrapartida", "Gasto / ingreso", TEXTO, 1.3), Col("base", "Base", DINERO, 1.2),
        Col("iva", "IVA", DINERO, 1.1), Col("total", "Total", DINERO, 1.2), Col("pendiente", "Pendiente", DINERO, 1.2), Col("justificantes", "Justif.", ENTERO, 0.7),
        Col("concepto", "Concepto", TEXTO, 3),
    ]
    parametros = [Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]
    importa_excel = True  # botón «Importar Excel» (facturas conciliadas con su pago o cobro, de Verifactu)

    # ---- importación del Excel de conciliación
    def importar_vista(self, ctx, nombre_fichero: str, contenido: bytes) -> dict:
        planes = svc_importar.planificar(ctx.sesion, ctx.ejercicio, self.sentido, svc_importar.leer_excel(contenido))
        nuevos = {}
        for p in planes:
            if p.importable and p.crear_tercero:
                nuevos.setdefault(svc_importar.clave_de_tercero(p.fila), p)
        return dict(
            planes=planes, nuevos=list(nuevos.items()), nombre_fichero=nombre_fichero, sentido=self.sentido, cuentas=cuentas_para_listas(ctx),
            defecto_gasto=svc_importar._gasto_por_defecto(ctx.sesion, ctx.empresa.id, self.sentido), importables=sum(1 for p in planes if p.importable),
            duplicadas=sum(1 for p in planes if p.estado == "duplicada"), con_errores=sum(1 for p in planes if p.estado == "nueva" and p.errores),
        )

    def importar_confirmar(self, ctx, contenido: bytes, formulario: dict, nombre_fichero: str) -> dict:
        planes = svc_importar.planificar(ctx.sesion, ctx.ejercicio, self.sentido, svc_importar.leer_excel(contenido))
        gastos = {k[len("gasto_"):]: v.strip() for k, v in formulario.items() if k.startswith("gasto_") and v.strip()}
        for clave, cuenta in gastos.items():
            if ctx.sesion.scalar(select(Cuenta.id).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo == cuenta)) is None:
                raise ErrorContable(f"La subcuenta {cuenta} no existe en el plan de cuentas")
        resultado = svc_importar.importar(ctx.sesion, ctx.config.almacen_de_adjuntos(), ctx.ejercicio, self.sentido, planes, cuentas_de_gasto=gastos, origen=f"Excel «{nombre_fichero}»")
        return dict(resultado=resultado, sentido=self.sentido, no_importadas=[p for p in planes if not p.importable])

    def filas(self, ctx, params):
        consulta = select(Factura).where(Factura.ejercicio_id == ctx.ejercicio.id, Factura.sentido == self.sentido).order_by(Factura.numero)
        if params.get("desde"):
            consulta = consulta.where(Factura.fecha_contable >= params["desde"])
        if params.get("hasta"):
            consulta = consulta.where(Factura.fecha_contable <= params["hasta"])
        con_fichero = {fid: n for fid, n in ctx.sesion.execute(select(Adjunto.factura_id, func.count()).where(Adjunto.factura_id.is_not(None), Adjunto.sha256.is_not(None)).group_by(Adjunto.factura_id))}
        filas = []
        for f in ctx.sesion.scalars(consulta):
            venc = ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)).all()
            filas.append(Fila(str(f.id), dict(
                numero=f.numero, fecha=f.fecha_contable, fecha_factura=f.fecha_factura, factura=f.numero_factura, tercero=f.tercero.nombre if f.tercero else (f.cuenta_tercero.nombre if f.cuenta_tercero else ""),
                nif=f.tercero.nif if f.tercero else None, contrapartida=f.cuenta_contrapartida.codigo if f.cuenta_contrapartida else None,
                base=sum((i.base for i in f.ivas), CERO), iva=sum((i.cuota_iva + i.cuota_recargo for i in f.ivas), CERO), total=f.total,
                pendiente=sum((abs(pendiente(ctx.sesion, v)) for v in venc), CERO) if venc else None, justificantes=con_fichero.get(f.id, 0), concepto=f.concepto,
            )))
        return filas

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("base", "iva", "total", "pendiente")}

    # ---- formulario propio
    def formulario(self, ctx, id, estado=None, errores=None):
        """(plantilla, contexto) del formulario completo."""
        if estado is None:
            if id:
                f = ctx.sesion.get(Factura, int(id))
                if f is None or f.ejercicio_id != ctx.ejercicio.id or f.sentido != self.sentido:
                    raise ErrorContable("La factura no existe")
                estado = estado_de_factura(ctx, f)
                completar_seguro(ctx, estado)  # sólo calcula los totales: lo grabado (cuotas, vencimientos) se respeta
            else:
                estado = estado_vacio(ctx, self.sentido)
                completar(ctx, estado)
        return "_factura.html", self._contexto(ctx, estado, errores or [])

    def _contexto(self, ctx, e: Estado, errores):
        adjuntos = []
        if e.id:
            adjuntos = list(ctx.sesion.scalars(select(Adjunto).where(Adjunto.factura_id == e.id).order_by(Adjunto.orden)))
        cuentas = cuentas_para_listas(ctx)
        return dict(
            e=e, errores=errores, sentido=self.sentido, pagos_de=_pagos_de_los_vencimientos(ctx, e), terceros=_terceros(ctx, self.sentido), tipos_iva=_tipos_iva(ctx, self.sentido),
            bancos=_bancos_de_pago(ctx, e), contras=CONTRAS,
            cuentas_tercero=[x for x in cuentas if x[0][0] == "4"], cuentas=cuentas,
            adjuntos=adjuntos, etiqueta_tercero="Proveedor" if self.sentido == "R" else "Cliente", etiqueta_contra="Gasto" if self.sentido == "R" else "Ingreso",
            diferencia=(e.suma_plazos - e.a_vencer) if e.suma_plazos is not None and e.a_vencer is not None else None,
        )

    def recalcular(self, ctx, items):
        e = estado_de_formulario(items, self.sentido)
        accion = next((v for k, v in items if k == "accion" and isinstance(v, str)), "")
        aplicar_accion(ctx, e, accion)
        completar(ctx, e)
        if accion == "add-pl":
            _completar_vencimiento_nuevo(ctx, e)
        return "_factura_cuerpo.html", self._contexto(ctx, e, [])

    def guardar_formulario(self, ctx, items, ficheros):
        """Devuelve (id, plantilla, contexto, advertencias): con errores, el formulario para volver a mostrarlo."""
        e = estado_de_formulario(items, self.sentido)
        try:
            factura, errores, advertencias = construir_y_grabar(ctx, e, ficheros)
        except (ErrorContable, ValueError) as ex:
            factura, errores, advertencias = None, [str(ex)], []
        if errores:
            ctx.sesion.rollback()
            completar_seguro(ctx, e)
            return None, "_factura.html", self._contexto(ctx, e, errores), []
        ctx.sesion.commit()
        return str(factura.id), None, None, advertencias

    def eliminar(self, ctx, ids):
        almacen = ctx.config.almacen_de_adjuntos()
        for i in ids:
            f = ctx.sesion.get(Factura, int(i))
            if f is None or f.ejercicio_id != ctx.ejercicio.id:
                raise ErrorContable("La factura no existe")
            for a in list(f.adjuntos):
                svc_adjuntos.quitar(ctx.sesion, almacen, ctx.ejercicio, a)
            ctx.sesion.expire(f, ["adjuntos"])
            eliminar_factura(ctx.sesion, ctx.ejercicio, f)


def _bancos_de_pago(ctx: Contexto, e: Estado) -> list[Banco]:
    """Los bancos y tarjetas con los que se puede pagar un vencimiento: los de las cuentas 572 (bancos), 551 (cuenta con socios o administradores) y 521 (deudas a corto plazo, tarjetas).
    Si un vencimiento ya traía otro banco previsto (un préstamo, una compensación…), se conserva en su lista para no perderlo al editar."""
    cuentas = {c.id: c.codigo for c in ctx.sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ctx.empresa.id))}
    bancos = list(ctx.sesion.scalars(select(Banco).where(Banco.empresa_id == ctx.empresa.id).order_by(*ORDEN_DE_BANCOS)))
    usados = {int(p.banco) for p in e.plazos if p.banco.isdigit()}
    return [b for b in bancos if b.id in usados or (b.clase == "B" and cuentas.get(b.cuenta_id, "").startswith(("572", "551", "521")))]


def completar_seguro(ctx: Contexto, e: Estado) -> None:
    try:
        completar(ctx, e)
    except (ErrorContable, ValueError):
        pass


class ListadoFacturasRecibidas(ListadoFacturas):
    nombre, titulo, sentido = "facturas-recibidas", "Facturas recibidas", "R"
    descripcion = ("Compras y gastos. Doble clic para ver y editar; el asiento y los vencimientos se generan solos. La columna «Categoría» es la de análisis del gasto: marque facturas y use «Categoría de las marcadas…» "
                   "para cambiarla (también en ejercicios cerrados: no es un dato contable).")
    columnas = ListadoFacturas.columnas[:7] + [Col("categoria", "Categoría", TEXTO, 2.2)] + ListadoFacturas.columnas[7:]
    acciones_con_seleccion = [("Categoría de las marcadas…", "accion/categoria")]

    def filas(self, ctx, params):
        filas = super().filas(ctx, params)
        categorias = svc_categorias.categorias_de(ctx.sesion, ctx.empresa.id)
        if not categorias:
            return filas
        por_id = {f.id: f for f in ctx.sesion.scalars(select(Factura).where(Factura.ejercicio_id == ctx.ejercicio.id, Factura.sentido == "R"))}
        for fila in filas:
            factura = por_id.get(int(fila.id))
            if factura is not None:
                c = svc_categorias.categoria_de_factura(categorias, factura, fila.valores.get("contrapartida"))
                fila.valores["categoria"] = c.nombre if c else "Sin clasificar"
        return filas

    def accion(self, ctx, accion, items):
        """Fijar la categoría de análisis de las facturas marcadas. No cambia ningún asiento, así que vale en ejercicios cerrados y trimestres presentados."""
        if accion != "categoria":
            raise ErrorContable("Acción desconocida")
        if items is None:
            raise ErrorContable("Marque primero las facturas")
        datos = {k: v for k, v in items if isinstance(v, str)}
        ids = [int(v) for k, v in items if k == "ids" and isinstance(v, str) and v.isdigit()]
        facturas = [f for f in (ctx.sesion.get(Factura, i) for i in ids) if f is not None and f.ejercicio_id == ctx.ejercicio.id and f.sentido == "R"]
        categorias = svc_categorias.categorias_de(ctx.sesion, ctx.empresa.id)
        if not facturas:
            raise ErrorContable("Marque al menos una factura")
        if "categoria" not in datos:  # primer paso: elegir la categoría
            return "_factura_categoria.html", dict(facturas=facturas, categorias=categorias, errores=[])
        try:
            elegida = None
            if datos["categoria"] != "auto":
                elegida = next((c for c in categorias if str(c.id) == datos["categoria"]), None)
                if elegida is None:
                    raise ErrorContable("Elija una categoría de la lista")
            cambiadas = sum(svc_categorias.asignar_categoria(ctx.sesion, f, elegida) for f in facturas)
            ctx.sesion.commit()
        except ErrorContable as ex:
            ctx.sesion.rollback()
            return "_factura_categoria.html", dict(facturas=facturas, categorias=categorias, errores=[str(ex)])
        return None, dict(mensaje=f"Categoría «{elegida.nombre if elegida else 'la de la cuenta de gasto'}»: {cambiadas} factura(s) cambiada(s)")



class ListadoFacturasEmitidas(ListadoFacturas):
    nombre, titulo, sentido = "facturas-emitidas", "Facturas emitidas", "E"
    descripcion = "Ventas e ingresos. Doble clic para ver y editar; el asiento y los vencimientos se generan solos."
