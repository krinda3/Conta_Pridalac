"""Los libros registro que no salen de la contabilidad: el de socios (con los movimientos de sus participaciones) y el de actas. Se escriben aquí y se incluyen en la legalización de libros."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from conta_pridalac.db.modelos import Acta, MovimientoSocio, Socio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha
from conta_pridalac.exportacion.tabla import ENTERO, FECHA, TEXTO
from conta_pridalac.web.comun import fecha_texto
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

TIPOS_MOVIMIENTO = ("Constitución", "Compra", "Venta", "Ampliación", "Reducción", "Herencia", "Donación", "Otro")
CAMPOS_SOCIO = ("nif", "nombre", "nacionalidad", "domicilio", "poblacion", "provincia", "profesion", "estado_civil")
CAMPOS_MOV = ("mov_fecha", "mov_tipo", "mov_concepto", "mov_participaciones", "mov_desde", "mov_hasta", "mov_nominal")


def _entero(texto: str, nombre: str, *, obligatorio: bool = False) -> int | None:
    texto = (texto or "").strip().replace(".", "")
    if not texto:
        if obligatorio:
            raise ErrorContable(f"{nombre}: falta el número")
        return None
    try:
        return int(texto)
    except ValueError:
        raise ErrorContable(f"{nombre}: «{texto}» no es un número entero") from None


def _nominal(texto: str) -> str:
    texto = (texto or "").strip().replace(",", ".") or "1.00"
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise ErrorContable(f"Valor nominal: «{texto}» no es un importe") from None
    if valor <= 0:
        raise ErrorContable("El valor nominal debe ser mayor que cero")
    return format(valor, "f")


def _lista(datos: list[tuple[str, object]], clave: str) -> list[str]:
    return [str(v) for k, v in datos if k == clave]


class ListadoSocios(Listado):
    nombre, titulo = "libro-socios", "Libro de socios"
    descripcion = ("Los socios de la sociedad y los movimientos de sus participaciones (constitución, compras, ventas, ampliaciones…): con ellos se hace el libro registro de socios que se legaliza cada año "
                   "en el Registro Mercantil. Doble clic en un socio para ver o corregir sus datos y sus movimientos.")
    borrar = True
    formulario_propio = True
    editable = True
    acciones_extra = [("Nuevo socio…", "f/nuevo")]
    columnas = [Col("orden", "Nº", ENTERO, 0.6), Col("nombre", "Socio", TEXTO, 3), Col("nif", "NIF", TEXTO, 1.2), Col("participaciones", "Participaciones", ENTERO, 1.2), Col("porcentaje", "%", TEXTO, 0.8),
                Col("movimientos", "Movimientos", ENTERO, 1)]

    def texto_vacio(self, ctx, params):
        return "Todavía no hay socios: pulse «Nuevo socio…»"

    def filas(self, ctx, params):
        socios = list(ctx.sesion.scalars(select(Socio).where(Socio.empresa_id == ctx.empresa.id).order_by(Socio.orden, Socio.id)))
        total = sum(sum(m.participaciones for m in s.movimientos) for s in socios)
        filas = []
        for s in socios:
            propias = sum(m.participaciones for m in s.movimientos)
            filas.append(Fila(str(s.id), dict(orden=s.orden, nombre=s.nombre, nif=s.nif or "", participaciones=propias, porcentaje=f"{propias * 100 / total:.2f} %".replace(".", ",") if total else "",
                                              movimientos=len(s.movimientos))))
        return filas

    def resumen(self, ctx, filas):
        total = sum(f.valores["participaciones"] for f in filas)
        capital = sum((Decimal(m.valor_nominal) * m.participaciones for s in ctx.sesion.scalars(select(Socio).where(Socio.empresa_id == ctx.empresa.id)) for m in s.movimientos), Decimal("0"))
        return f"{len(filas)} socio(s) · {total} participaciones · capital {capital:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") if filas else ""

    def totales(self, filas):
        return None

    def _socio(self, ctx: Contexto, id) -> Socio | None:
        if str(id) in ("nuevo", "0", ""):
            return None
        s = ctx.sesion.get(Socio, int(id)) if str(id).isdigit() else None
        if s is None or s.empresa_id != ctx.empresa.id:
            raise ErrorContable("El socio no existe")
        return s

    def formulario(self, ctx, id, errores=None, valores=None, movimientos=None):
        s = self._socio(ctx, id)
        if valores is None:
            valores = {c: (getattr(s, c) or "") if s else "" for c in CAMPOS_SOCIO}
            valores["fecha_nacimiento"] = fecha_texto(s.fecha_nacimiento) if s and s.fecha_nacimiento else ""
            valores["orden"] = str(s.orden if s else (ctx.sesion.scalar(select(func.max(Socio.orden)).where(Socio.empresa_id == ctx.empresa.id)) or 0) + 1)
            if s is None:
                valores["nacionalidad"] = "ESPAÑA"
        if movimientos is None:
            movimientos = [(fecha_texto(m.fecha), m.tipo, m.concepto or "", str(m.participaciones), str(m.desde or ""), str(m.hasta or ""), m.valor_nominal.replace(".", ",")) for m in (s.movimientos if s else [])]
        return "_socio.html", dict(id=str(s.id) if s else "nuevo", socio=s, valores=valores, movimientos=list(movimientos) + [("", "Constitución", "", "", "", "", "1,00")] * 2, tipos=TIPOS_MOVIMIENTO,
                                   errores=list(errores or []))

    def guardar_formulario(self, ctx, items, ficheros):
        datos = [(k, v) for k, v in items if isinstance(v, str)]
        plano = {k: v for k, v in datos}
        id_ = plano.get("id", "nuevo")
        valores = {c: plano.get(c, "") for c in (*CAMPOS_SOCIO, "fecha_nacimiento", "orden")}
        movimientos = list(zip(*(_lista(datos, c) for c in CAMPOS_MOV)))
        try:
            s = self._socio(ctx, id_)
            if not valores["nombre"].strip():
                raise ErrorContable("Falta el nombre del socio («Apellidos, Nombre» o la razón social)")
            nacimiento = parsear_fecha(valores["fecha_nacimiento"]) if valores["fecha_nacimiento"].strip() else None
            nuevos = []
            for i, (fecha, tipo, concepto, participaciones, desde, hasta, nominal) in enumerate(movimientos, 1):
                if not any(x.strip() for x in (fecha, concepto, participaciones, desde, hasta)):
                    continue
                if not fecha.strip():
                    raise ErrorContable(f"Movimiento {i}: falta la fecha")
                nuevos.append(MovimientoSocio(fecha=parsear_fecha(fecha), tipo=(tipo or "Constitución").strip()[:32], concepto=concepto.strip()[:128] or None,
                                              participaciones=_entero(participaciones, f"Movimiento {i}: participaciones", obligatorio=True), desde=_entero(desde, f"Movimiento {i}: desde"),
                                              hasta=_entero(hasta, f"Movimiento {i}: hasta"), valor_nominal=_nominal(nominal)))
            if s is None:
                s = Socio(empresa_id=ctx.empresa.id, nombre=valores["nombre"].strip())
                ctx.sesion.add(s)
            s.nombre, s.fecha_nacimiento = valores["nombre"].strip()[:128], nacimiento
            for c in CAMPOS_SOCIO[:1] + CAMPOS_SOCIO[2:]:
                setattr(s, c, valores[c].strip() or None)
            s.nif = (valores["nif"].strip().upper().replace(" ", "")[:20]) or None
            s.orden = _entero(valores["orden"], "Nº de orden") or 0
            s.movimientos[:] = nuevos
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, id_, errores=[str(ex)], valores=valores, movimientos=movimientos)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, str(s.id))
        contexto["_mensaje"] = "Socio guardado"
        return None, plantilla, contexto, []

    def eliminar(self, ctx, ids):
        for i in ids:
            s = self._socio(ctx, i)
            if s is not None:
                ctx.sesion.delete(s)


class ListadoActas(Listado):
    nombre, titulo = "libro-actas", "Libro de actas"
    descripcion = ("Las actas de las reuniones de la sociedad (la de aprobación de cuentas, sobre todo). Cada acta entra en el libro del ejercicio al que pertenece su fecha: la reunión de marzo de 2025 (que aprobó las cuentas de 2024) va en el libro de 2025, "
                   "que se legaliza en abril de 2026. «Acta de aprobación de cuentas…» prepara una con el texto habitual, que se puede cambiar.")
    borrar = True
    formulario_propio = True
    editable = True
    acciones_extra = [("Acta de aprobación de cuentas…", "f/nueva"), ("Acta en blanco…", "f/nuevo")]
    columnas = [Col("numero", "Nº", ENTERO, 0.6), Col("fecha", "Fecha", FECHA, 1.1), Col("libro", "Libro del ejercicio", TEXTO, 1.4), Col("clase", "Reunión", TEXTO, 2), Col("asuntos", "Orden del día", TEXTO, 6)]

    def texto_vacio(self, ctx, params):
        return "Todavía no hay actas"

    def filas(self, ctx, params):
        return [Fila(str(a.id), dict(numero=a.numero, fecha=a.fecha, libro=str(a.fecha.year), clase=f"{a.clase} · {a.organo}", asuntos=" · ".join(l.strip() for l in (a.orden_del_dia or "").splitlines() if l.strip())))
                for a in ctx.sesion.scalars(select(Acta).where(Acta.empresa_id == ctx.empresa.id).order_by(Acta.fecha.desc(), Acta.numero.desc()))]

    def totales(self, filas):
        return None

    def _acta(self, ctx: Contexto, id) -> Acta | None:
        if str(id) in ("nuevo", "nueva", "0", ""):
            return None
        a = ctx.sesion.get(Acta, int(id)) if str(id).isdigit() else None
        if a is None or a.empresa_id != ctx.empresa.id:
            raise ErrorContable("El acta no existe")
        return a

    def _propuesta(self, ctx: Contexto, de_cuentas: bool) -> dict:
        anio = ctx.ejercicio.anio
        socios = list(ctx.sesion.scalars(select(Socio).where(Socio.empresa_id == ctx.empresa.id).order_by(Socio.orden, Socio.id)))
        numero = (ctx.sesion.scalar(select(func.max(Acta.numero)).where(Acta.empresa_id == ctx.empresa.id, Acta.fecha >= ctx.ejercicio.fecha_inicio, Acta.fecha <= ctx.ejercicio.fecha_fin)) or 0) + 1
        valores = dict(numero=str(numero), fecha=fecha_texto(min(date(anio, 3, 31), ctx.ejercicio.fecha_fin)), hora_inicio="18:00", hora_fin="19:00", clase="Ordinaria", organo="Junta General",
                       asistentes="\n".join(s.nombre for s in socios), orden_del_dia="", resumen="", intervenciones="", acuerdos="", votaciones="",
                       presidente_nombre=socios[0].nombre if socios else "", presidente_nif=(socios[0].nif or "") if socios else "",
                       secretario_nombre=socios[0].nombre if socios else "", secretario_nif=(socios[0].nif or "") if socios else "")
        if de_cuentas:
            valores.update(
                orden_del_dia=f"1.- Aprobación de las cuentas anuales del ejercicio {anio - 1}\n2.- Aplicación del resultado\n3.- Programa de actividades para {anio}",
                resumen=f"1.- Presentación de las cuentas anuales de {anio - 1}\n2.- Presentación del programa de actividades para {anio}",
                acuerdos=f"Se aprueban por unanimidad las cuentas anuales del ejercicio {anio - 1}\nSe acuerda aplicar el resultado conforme a la propuesta presentada\nSe acuerda continuar con la actividad de la sociedad según el plan previsto",
                votaciones="Todas a favor con el 100% de los votos")
        return valores

    def formulario(self, ctx, id, errores=None, valores=None):
        a = self._acta(ctx, id)
        if valores is None:
            if a is None:
                valores = self._propuesta(ctx, str(id) == "nueva")
            else:
                valores = {c: (getattr(a, c) or "") for c in ("hora_inicio", "hora_fin", "clase", "organo", "asistentes", "orden_del_dia", "resumen", "intervenciones", "acuerdos", "votaciones",
                                                              "presidente_nombre", "presidente_nif", "secretario_nombre", "secretario_nif")}
                valores.update(numero=str(a.numero), fecha=fecha_texto(a.fecha))
        return "_acta.html", dict(id=str(a.id) if a else "nuevo", acta=a, valores=valores, errores=list(errores or []))

    def guardar_formulario(self, ctx, items, ficheros):
        plano = {k: v for k, v in items if isinstance(v, str)}
        id_ = plano.get("id", "nuevo")
        campos = ("hora_inicio", "hora_fin", "clase", "organo", "asistentes", "orden_del_dia", "resumen", "intervenciones", "acuerdos", "votaciones", "presidente_nombre", "presidente_nif",
                  "secretario_nombre", "secretario_nif")
        valores = {c: plano.get(c, "") for c in (*campos, "numero", "fecha")}
        try:
            a = self._acta(ctx, id_)
            fecha = parsear_fecha(valores["fecha"]) if valores["fecha"].strip() else None
            if fecha is None:
                raise ErrorContable("Falta la fecha de la reunión")
            numero = _entero(valores["numero"], "Nº de acta", obligatorio=True)
            if a is None:
                a = Acta(empresa_id=ctx.empresa.id, numero=numero, fecha=fecha)
                ctx.sesion.add(a)
            a.numero, a.fecha = numero, fecha
            for c in campos:
                setattr(a, c, valores[c].strip() or None)
            a.clase = (valores["clase"].strip() or "Ordinaria")[:32]
            a.organo = (valores["organo"].strip() or "Junta General")[:48]
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, id_, errores=[str(ex)], valores=valores)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, str(a.id))
        contexto["_mensaje"] = "Acta guardada"
        return None, plantilla, contexto, []

    def eliminar(self, ctx, ids):
        for i in ids:
            a = self._acta(ctx, i)
            if a is not None:
                ctx.sesion.delete(a)
