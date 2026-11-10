"""Asientos manuales y plantillas en la web.

Un asiento manual (tipo 4, «extra» de MGD) se teclea línea a línea: cuenta, lado (Debe/Haber), importe y, si procede, sus
vencimientos (cuotas de un préstamo, una retención…). Puede salir de una **plantilla**: la línea de cuadre se calcula sola y los
vencimientos se generan con las reglas de cada línea (`D=25 M+1 A=`…). Como en las facturas, el formulario se recalcula en el
servidor y todo se graba junto o no se graba nada.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from conta_pridalac.db.modelos import TIPO_GENERAL, Adjunto, Apunte, Asiento, Plantilla, PlantillaLinea, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import introducir_fecha, parsear_fecha
from conta_pridalac.domain.plantillas import LineaPlantilla, evaluar_texto, fecha_de_vencimiento, validar_plantilla
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO
from conta_pridalac.servicios import adjuntos as svc_adjuntos
from conta_pridalac.servicios.extras import LineaManual, _con_pagos, eliminar_extra, grabar_extra
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, repartir_en_plazos
from conta_pridalac.web.comun import (
    cuentas_para_listas,
    dinero_opcional,
    fecha_texto,
    guardar_justificantes,
    id_de_cuenta,
    texto_dinero,
)
from conta_pridalac.web.listados import Campo, Col, Contexto, Fila, Listado

CERO = Decimal("0.00")


# ------------------------------------------------------------------------------------------------ estado del formulario


@dataclass
class PlazoAs:
    fecha: str = ""
    importe: str = ""  # con signo: positivo a cobrar, negativo a pagar
    pagos: bool = False


@dataclass
class LineaAs:
    cuenta: str = ""
    dh: str = "D"
    importe: str = ""
    ayuda: str = ""
    cuadre: bool = False  # la línea que equilibra el asiento (plantillas)
    reglas: str = ""  # reglas de vencimiento de la plantilla, separadas por comas
    plauto: bool = True  # los vencimientos siguen a las reglas mientras no se toquen
    plazos: list[PlazoAs] = field(default_factory=list)


@dataclass
class EstadoAs:
    id: int | None = None
    fecha: str = ""
    concepto: str = ""
    plantilla: str = ""
    lineas: list[LineaAs] = field(default_factory=list)
    quitar_adjuntos: set[int] = field(default_factory=set)
    debe: Decimal = CERO
    haber: Decimal = CERO


def estado_vacio(ctx: Contexto) -> EstadoAs:
    hoy = date.today()
    fecha = hoy if ctx.ejercicio.fecha_inicio <= hoy <= ctx.ejercicio.fecha_fin else ctx.ejercicio.fecha_inicio
    return EstadoAs(fecha=fecha_texto(fecha), lineas=[LineaAs(dh="D"), LineaAs(dh="H")])


def estado_de_asiento(ctx: Contexto, a: Asiento) -> EstadoAs:
    e = EstadoAs(id=a.id, fecha=fecha_texto(a.fecha), concepto=a.concepto or "")
    for ap in a.apuntes:
        plazos = [
            PlazoAs(fecha_texto(v.fecha), texto_dinero(v.importe), _con_pagos(ctx.sesion, v))
            for v in sorted(ctx.sesion.scalars(select(Vencimiento).where(Vencimiento.apunte_id == ap.id)), key=lambda v: v.id)
        ]
        e.lineas.append(LineaAs(
            cuenta=ap.cuenta.codigo, dh="D" if ap.debe > 0 else "H", importe=texto_dinero(ap.debe if ap.debe > 0 else ap.haber), ayuda=ap.concepto or "", plauto=False, plazos=plazos,
        ))
    return e


def estado_de_plantilla(ctx: Contexto, p: Plantilla, fecha: date) -> EstadoAs:
    e = EstadoAs(fecha=fecha_texto(fecha), concepto=evaluar_texto(p.titulo, fecha)[:255], plantilla=str(p.id))
    for l in p.lineas:
        e.lineas.append(LineaAs(cuenta=l.cuenta, dh="H" if l.dhc in ("H", "C") else "D", ayuda=l.ayuda, cuadre=l.dhc == "C", reglas=l.vencimientos))
    return e


_LINEA = re.compile(r"ln-(\d+)-(\w+)")
_PLAZO = re.compile(r"ln-(\d+)-pl-(\d+)-(\w+)")


def estado_de_formulario(items: list[tuple[str, object]]) -> EstadoAs:
    simples: dict[str, str] = {}
    lineas: dict[int, dict[str, str]] = defaultdict(dict)
    plazos: dict[tuple[int, int], dict[str, str]] = defaultdict(dict)
    quitar: set[int] = set()
    for clave, valor in items:
        if not isinstance(valor, str):
            continue
        m = _PLAZO.fullmatch(clave)
        if m:
            plazos[(int(m.group(1)), int(m.group(2)))][m.group(3)] = valor
        elif (m := _LINEA.fullmatch(clave)):
            lineas[int(m.group(1))][m.group(2)] = valor
        elif clave == "quitar_adjunto" and valor.isdigit():
            quitar.add(int(valor))
        else:
            simples[clave] = valor
    e = EstadoAs(id=int(simples["id"]) if simples.get("id", "").isdigit() else None, fecha=simples.get("fecha", ""), concepto=simples.get("concepto", ""),
                 plantilla=simples.get("plantilla", ""), quitar_adjuntos=quitar)
    for i in sorted(lineas):
        d = lineas[i]
        linea = LineaAs(cuenta=d.get("cuenta", ""), dh=d.get("dh", "D") if d.get("dh") in ("D", "H") else "D", importe=d.get("importe", ""), ayuda=d.get("ayuda", ""),
                        cuadre=d.get("cuadre") == "1", reglas=d.get("reglas", ""), plauto=d.get("plauto", "1") == "1")
        for (li, j), p in sorted(plazos.items()):
            if li == i:
                linea.plazos.append(PlazoAs(fecha=p.get("fecha", ""), importe=p.get("importe", ""), pagos=p.get("pagos") == "1"))
        e.lineas.append(linea)
    return e


# ------------------------------------------------------------------------------------------------ cálculos y acciones


def aplicar_accion(e: EstadoAs, accion: str) -> None:
    if accion == "add-ln":
        e.lineas.append(LineaAs(dh="H" if sum(1 for l in e.lineas if l.dh == "D") > sum(1 for l in e.lineas if l.dh == "H") else "D"))
    elif accion == "cuadrar":
        if not any(l.cuadre for l in e.lineas):
            e.lineas.append(LineaAs(cuadre=True, dh="H"))
    elif (m := re.fullmatch(r"del-ln-(\d+)", accion)):
        i = int(m.group(1))
        if 0 <= i < len(e.lineas):
            del e.lineas[i]
    elif (m := re.fullmatch(r"add-pl-(\d+)", accion)):
        i = int(m.group(1))
        if 0 <= i < len(e.lineas):
            e.lineas[i].plazos.append(PlazoAs())
            e.lineas[i].plauto = False
    elif (m := re.fullmatch(r"del-pl-(\d+)-(\d+)", accion)):
        i, j = int(m.group(1)), int(m.group(2))
        if 0 <= i < len(e.lineas) and 0 <= j < len(e.lineas[i].plazos) and not e.lineas[i].plazos[j].pagos:
            del e.lineas[i].plazos[j]
            e.lineas[i].plauto = False


def _importe(l: LineaAs) -> Decimal | None:
    try:
        return dinero_opcional(l.importe, "Importe")
    except ValueError:
        return None


def completar(ctx: Contexto, e: EstadoAs) -> None:
    """Calcula la línea de cuadre, los vencimientos que mandan las reglas de la plantilla y los totales."""
    debe = sum((_importe(l) or CERO for l in e.lineas if l.dh == "D" and not l.cuadre), CERO)
    haber = sum((_importe(l) or CERO for l in e.lineas if l.dh == "H" and not l.cuadre), CERO)
    for l in e.lineas:
        if l.cuadre:
            dif = debe - haber
            l.dh, l.importe = ("H", texto_dinero(dif)) if dif >= 0 else ("D", texto_dinero(-dif))
            if dif == 0:
                l.importe = ""
    try:
        fecha = parsear_fecha(e.fecha, referencia=ctx.ejercicio.fecha_inicio) if e.fecha.strip() else None
    except ErrorContable:
        fecha = None
    for l in e.lineas:
        importe = _importe(l)
        if l.reglas and l.plauto and fecha is not None and importe and importe > 0:
            reglas = [r.strip() for r in l.reglas.split(",") if r.strip()]
            fechas = [fecha_de_vencimiento(r, fecha) for r in reglas]
            signo = 1 if l.dh == "D" else -1  # a cobrar si va al debe; a pagar si va al haber
            l.plazos = [PlazoAs(fecha_texto(f), texto_dinero(signo * p.importe)) for p, f in zip(repartir_en_plazos(importe, len(fechas), None), fechas)] if fechas else []
        elif l.reglas and l.plauto and (importe is None or importe == 0):
            l.plazos = []
    e.debe = debe + sum((_importe(l) or CERO for l in e.lineas if l.cuadre and l.dh == "D"), CERO)
    e.haber = haber + sum((_importe(l) or CERO for l in e.lineas if l.cuadre and l.dh == "H"), CERO)


# ------------------------------------------------------------------------------------------------ guardar


def construir_y_grabar(ctx: Contexto, e: EstadoAs, ficheros: list) -> tuple[Asiento | None, list[str], list[str]]:
    errores: list[str] = []
    completar(ctx, e)
    fecha = None
    try:
        fecha = introducir_fecha(e.fecha, ctx.ejercicio)
    except ErrorContable as ex:
        errores.append(f"Fecha: {ex}")
    previo = None
    if e.id:
        previo = ctx.sesion.get(Asiento, e.id)
        if previo is None or previo.ejercicio_id != ctx.ejercicio.id or previo.tipo != TIPO_GENERAL:
            return None, ["El asiento no existe o no es un asiento manual"], []
    lineas: list[LineaManual] = []
    for n, l in enumerate(e.lineas, start=1):
        if not l.cuenta.strip() and not l.importe.strip():
            continue
        try:
            importe = dinero_opcional(l.importe, f"Importe de la línea {n}")
        except ValueError as ex:
            errores.append(str(ex))
            continue
        id_de_cuenta(ctx, l.cuenta, f"la línea {n}", errores)
        if importe is None or importe == 0:
            if not l.cuadre:
                errores.append(f"Falta el importe de la línea {n}")
            continue
        if importe < 0:
            errores.append(f"La línea {n} tiene importe negativo: use el otro lado (Debe/Haber)")
            continue
        plazos = []
        for k, p in enumerate(l.plazos, start=1):
            try:
                pi = dinero_opcional(p.importe, f"Importe del vencimiento {k} de la línea {n}")
                pf = parsear_fecha(p.fecha, referencia=ctx.ejercicio.fecha_inicio) if p.fecha.strip() else None
            except (ValueError, ErrorContable) as ex:
                errores.append(str(ex) if "«" in str(ex) else f"Vencimiento {k} de la línea {n}: {ex}")
                continue
            if pi is None:
                errores.append(f"Falta el importe del vencimiento {k} de la línea {n}")
                continue
            plazos.append(PlazoVencimiento(importe=pi, fecha=pf))
        lineas.append(LineaManual(l.cuenta.strip(), l.dh, importe, l.ayuda.strip(), plazos if (plazos or previo is not None) else None))
    if not lineas and not errores:
        errores.append("Añada al menos dos líneas con importe")
    if errores:
        return None, errores, []
    resultado = grabar_extra(ctx.sesion, ctx.ejercicio, fecha=fecha, texto=e.concepto.strip(), lineas=lineas, numero=previo.numero if previo else None)
    asiento = resultado.asiento
    advertencias = list(resultado.advertencias)
    advertencias += guardar_justificantes(ctx, asiento, e.quitar_adjuntos, ficheros)
    return asiento, [], advertencias


# ------------------------------------------------------------------------------------------------ listado


class ListadoAsientos(Listado):
    nombre, titulo = "asientos", "Asientos manuales"
    descripcion = "Asientos tecleados a mano o creados desde una plantilla. Doble clic para editar; los de facturas, bancos y cierre se generan solos."
    formulario_propio = True
    anadir = borrar = editable = True
    columnas = [
        Col("numero", "Nº", ENTERO, 0.6), Col("fecha", "Fecha", FECHA, 1.1), Col("diario", "Nº diario", ENTERO, 0.9), Col("concepto", "Concepto", TEXTO, 4),
        Col("cuentas", "Cuentas", TEXTO, 2.5), Col("lineas", "Líneas", ENTERO, 0.7), Col("debe", "Debe", DINERO, 1.2), Col("haber", "Haber", DINERO, 1.2),
        Col("vencimientos", "Vtos.", ENTERO, 0.7), Col("justificantes", "Justif.", ENTERO, 0.7),
    ]
    parametros = [Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]
    acciones_extra = [("＋ Desde plantilla", "accion/plantilla")]

    def filas(self, ctx, params):
        consulta = (
            select(Asiento).where(Asiento.ejercicio_id == ctx.ejercicio.id, Asiento.tipo == TIPO_GENERAL)
            .options(selectinload(Asiento.apuntes).selectinload(Apunte.cuenta)).order_by(Asiento.numero, Asiento.sub)
        )
        if params.get("desde"):
            consulta = consulta.where(Asiento.fecha >= params["desde"])
        if params.get("hasta"):
            consulta = consulta.where(Asiento.fecha <= params["hasta"])
        asientos = list(ctx.sesion.scalars(consulta))
        venc = {a_id: n for a_id, n in ctx.sesion.execute(select(Apunte.asiento_id, func.count(Vencimiento.id)).join(Vencimiento, Vencimiento.apunte_id == Apunte.id).group_by(Apunte.asiento_id))}
        just = {a_id: n for a_id, n in ctx.sesion.execute(select(Adjunto.asiento_id, func.count()).where(Adjunto.asiento_id.is_not(None), Adjunto.sha256.is_not(None)).group_by(Adjunto.asiento_id))}
        filas = []
        for a in asientos:
            codigos = [ap.cuenta.codigo for ap in a.apuntes]
            filas.append(Fila(str(a.id), dict(
                numero=a.numero, fecha=a.fecha, diario=a.numero_diario, concepto=a.concepto, cuentas=", ".join(codigos[:4]) + (" …" if len(codigos) > 4 else ""), lineas=len(codigos),
                debe=sum((ap.debe for ap in a.apuntes), CERO), haber=sum((ap.haber for ap in a.apuntes), CERO), vencimientos=venc.get(a.id, 0), justificantes=just.get(a.id, 0),
            )))
        return filas

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("debe", "haber")}

    # ---- formulario
    def formulario(self, ctx, id, estado=None, errores=None):
        if estado is None:
            if id:
                a = ctx.sesion.get(Asiento, int(id))
                if a is None or a.ejercicio_id != ctx.ejercicio.id or a.tipo != TIPO_GENERAL:
                    raise ErrorContable("El asiento no existe o no es manual")
                estado = estado_de_asiento(ctx, a)
            else:
                estado = estado_vacio(ctx)
            completar(ctx, estado)
        return "_asiento.html", self._contexto(ctx, estado, errores or [])

    def _contexto(self, ctx, e: EstadoAs, errores):
        adjuntos = list(ctx.sesion.scalars(select(Adjunto).where(Adjunto.asiento_id == e.id).order_by(Adjunto.orden))) if e.id else []
        return dict(e=e, errores=errores, cuentas=cuentas_para_listas(ctx), adjuntos=adjuntos, diferencia=e.debe - e.haber)

    def recalcular(self, ctx, items):
        e = estado_de_formulario(items)
        aplicar_accion(e, next((v for k, v in items if k == "accion" and isinstance(v, str)), ""))
        completar(ctx, e)
        return "_asiento_cuerpo.html", self._contexto(ctx, e, [])

    def guardar_formulario(self, ctx, items, ficheros):
        e = estado_de_formulario(items)
        try:
            asiento, errores, advertencias = construir_y_grabar(ctx, e, ficheros)
        except (ErrorContable, ValueError) as ex:
            asiento, errores, advertencias = None, [str(ex)], []
        if errores:
            ctx.sesion.rollback()
            try:
                completar(ctx, e)
            except (ErrorContable, ValueError):
                pass
            return None, "_asiento.html", self._contexto(ctx, e, errores), []
        ctx.sesion.commit()
        return str(asiento.id), None, None, advertencias

    def eliminar(self, ctx, ids):
        almacen = ctx.config.almacen_de_adjuntos()
        for i in ids:
            a = ctx.sesion.get(Asiento, int(i))
            if a is None or a.ejercicio_id != ctx.ejercicio.id or a.tipo != TIPO_GENERAL:
                raise ErrorContable("El asiento no existe o no es manual")
            for adj in list(svc_adjuntos.listar(ctx.sesion, a)):
                svc_adjuntos.quitar(ctx.sesion, almacen, ctx.ejercicio, adj)
            ctx.sesion.expire(a, ["apuntes"])
            eliminar_extra(ctx.sesion, ctx.ejercicio, a)

    # ---- «Desde plantilla»: elegir plantilla y fecha, y se abre el asiento ya rellenado
    def accion(self, ctx, accion, items):
        if accion != "plantilla":
            raise ErrorContable("Acción desconocida")
        plantillas = list(ctx.sesion.scalars(select(Plantilla).where(Plantilla.empresa_id == ctx.empresa.id).order_by(Plantilla.titulo)))
        if items is None:
            return "_desde_plantilla.html", dict(plantillas=plantillas, errores=[], fecha=fecha_texto(date.today() if ctx.ejercicio.fecha_inicio <= date.today() <= ctx.ejercicio.fecha_fin else ctx.ejercicio.fecha_inicio), elegida="")
        datos = {k: v for k, v in items if isinstance(v, str)}
        elegida = datos.get("plantilla", "")
        try:
            fecha = introducir_fecha(datos.get("fecha", ""), ctx.ejercicio)
            p = ctx.sesion.get(Plantilla, int(elegida)) if elegida.isdigit() else None
            if p is None or p.empresa_id != ctx.empresa.id:
                raise ErrorContable("Elija una plantilla")
        except ErrorContable as ex:
            return "_desde_plantilla.html", dict(plantillas=plantillas, errores=[str(ex)], fecha=datos.get("fecha", ""), elegida=elegida)
        estado = estado_de_plantilla(ctx, p, fecha)
        completar(ctx, estado)
        return "_asiento.html", self._contexto(ctx, estado, [])


# ------------------------------------------------------------------------------------------------ plantillas


@dataclass
class LineaPl:
    cuenta: str = ""
    dhc: str = "D"
    ayuda: str = ""
    importe: str = ""
    reglas: str = ""


@dataclass
class EstadoPl:
    id: int | None = None
    titulo: str = ""
    lineas: list[LineaPl] = field(default_factory=list)


_LINEA_PL = re.compile(r"ln-(\d+)-(\w+)")


def estado_pl_de_formulario(items) -> EstadoPl:
    simples: dict[str, str] = {}
    lineas: dict[int, dict[str, str]] = defaultdict(dict)
    for clave, valor in items:
        if not isinstance(valor, str):
            continue
        m = _LINEA_PL.fullmatch(clave)
        if m:
            lineas[int(m.group(1))][m.group(2)] = valor
        else:
            simples[clave] = valor
    e = EstadoPl(id=int(simples["id"]) if simples.get("id", "").isdigit() else None, titulo=simples.get("titulo", ""))
    for i in sorted(lineas):
        d = lineas[i]
        e.lineas.append(LineaPl(cuenta=d.get("cuenta", ""), dhc=d.get("dhc", "D") if d.get("dhc") in ("D", "H", "C") else "D", ayuda=d.get("ayuda", ""),
                                importe=d.get("importe", ""), reglas=d.get("reglas", "")))
    return e


class ListadoPlantillas(Listado):
    nombre, titulo = "plantillas", "Plantillas de asientos"
    descripcion = "Modelos de asientos repetitivos (nóminas, cuotas, seguros…). Doble clic para editar. Se usan desde «Asientos manuales → Desde plantilla»."
    formulario_propio = True
    anadir = borrar = editable = True
    columnas = [Col("titulo", "Título", TEXTO, 4), Col("lineas", "Líneas", ENTERO, 0.7), Col("cuentas", "Cuentas", TEXTO, 4), Col("vencimientos", "Con vencimientos", ENTERO, 1.1)]

    def filas(self, ctx, params):
        return [
            Fila(str(p.id), dict(titulo=p.titulo, lineas=len(p.lineas), cuentas=", ".join(l.cuenta for l in p.lineas[:5]) + (" …" if len(p.lineas) > 5 else ""),
                                 vencimientos=sum(1 for l in p.lineas if l.vencimientos)))
            for p in ctx.sesion.scalars(select(Plantilla).where(Plantilla.empresa_id == ctx.empresa.id).options(selectinload(Plantilla.lineas)).order_by(Plantilla.titulo))
        ]

    def formulario(self, ctx, id, estado=None, errores=None):
        if estado is None:
            if id:
                p = ctx.sesion.get(Plantilla, int(id))
                if p is None or p.empresa_id != ctx.empresa.id:
                    raise ErrorContable("La plantilla no existe")
                estado = EstadoPl(id=p.id, titulo=p.titulo, lineas=[LineaPl(l.cuenta, l.dhc, l.ayuda, texto_dinero(l.importe) if l.importe else "", l.vencimientos) for l in p.lineas])
            else:
                estado = EstadoPl(lineas=[LineaPl(dhc="D"), LineaPl(dhc="C")])
        return "_plantilla.html", dict(e=estado, errores=errores or [], cuentas=cuentas_para_listas(ctx))

    def recalcular(self, ctx, items):
        e = estado_pl_de_formulario(items)
        accion = next((v for k, v in items if k == "accion" and isinstance(v, str)), "")
        if accion == "add-ln":
            e.lineas.append(LineaPl())
        elif (m := re.fullmatch(r"del-ln-(\d+)", accion)) and 0 <= int(m.group(1)) < len(e.lineas):
            del e.lineas[int(m.group(1))]
        return "_plantilla_cuerpo.html", dict(e=e, errores=[], cuentas=cuentas_para_listas(ctx))

    def guardar_formulario(self, ctx, items, ficheros):
        e = estado_pl_de_formulario(items)
        errores = self._validar(ctx, e)
        if not errores:
            p = ctx.sesion.get(Plantilla, e.id) if e.id else Plantilla(empresa_id=ctx.empresa.id)
            if p is None or p.empresa_id != ctx.empresa.id:
                errores.append("La plantilla no existe")
            else:
                p.titulo = e.titulo.strip()
                p.lineas.clear()
                ctx.sesion.flush()
                for orden, l in enumerate((l for l in e.lineas if l.cuenta.strip()), start=1):
                    p.lineas.append(PlantillaLinea(orden=orden, cuenta=l.cuenta.strip(), ayuda=l.ayuda.strip()[:64], dhc=l.dhc,
                                                   importe=dinero_opcional(l.importe, "Importe") or CERO, vencimientos=",".join(r.strip() for r in l.reglas.split(",") if r.strip())))
                ctx.sesion.add(p)
                try:
                    ctx.sesion.flush()
                except Exception as ex:  # título repetido u otro fallo de base de datos
                    ctx.sesion.rollback()
                    errores.append("Ya existe una plantilla con ese título" if "UNIQUE" in str(ex) else str(ex))
        if errores:
            ctx.sesion.rollback()
            return None, "_plantilla.html", dict(e=e, errores=errores, cuentas=cuentas_para_listas(ctx)), []
        ctx.sesion.commit()
        return str(p.id), None, None, []

    def _validar(self, ctx, e: EstadoPl) -> list[str]:
        errores = []
        if not e.titulo.strip():
            errores.append("Falta el título de la plantilla")
        lineas = [l for l in e.lineas if l.cuenta.strip()]
        for n, l in enumerate(lineas, start=1):
            if len(l.cuenta.strip()) != ctx.empresa.digitos_cuenta or not l.cuenta.strip().isdigit():
                errores.append(f"Línea {n}: la cuenta {l.cuenta.strip()!r} no tiene {ctx.empresa.digitos_cuenta} dígitos")
            try:
                dinero_opcional(l.importe, f"Importe de la línea {n}")
            except ValueError as ex:
                errores.append(str(ex))
            for r in (r.strip() for r in l.reglas.split(",") if r.strip()):
                if fecha_de_vencimiento(r, date(2026, 1, 15)) is None:
                    errores.append(f"Línea {n}: la regla de vencimiento «{r}» no es válida (por ejemplo «D=25 M+1 A=»)")
        try:
            validar_plantilla([LineaPlantilla(l.cuenta, l.ayuda, l.dhc, CERO, []) for l in lineas])
        except ErrorContable as ex:
            errores.append(str(ex))
        return errores

    def eliminar(self, ctx, ids):
        for i in ids:
            p = ctx.sesion.get(Plantilla, int(i))
            if p is None or p.empresa_id != ctx.empresa.id:
                raise ErrorContable("La plantilla no existe")
            ctx.sesion.delete(p)
        ctx.sesion.flush()
