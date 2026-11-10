"""Modelo 190 en la web: un renglón por ejercicio (es un resumen anual) y, al abrirlo, la ficha con los perceptores calculados, los controles, el borrador, el fichero, la copia para presentar y el registro
de la presentación con el PDF de la sede. Mismo molde que el 111 (`web/modelo111.py`), sin pago ni NRC: el 190 es informativo.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import BORRADOR, GENERADA, PRESENTADA, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, TEXTO
from conta_pridalac.ficheros_aeat import fichero190
from conta_pridalac.servicios.exportar import exportar_presentacion, nombre_para_presentar
from conta_pridalac.servicios.modelo190 import calcular_190
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion190 import (
    MODELO,
    PERIODO,
    TIPOS_DE_PRESENTACION,
    controlar_190,
    crear_borrador,
    generar_fichero,
    identificativo_del_fichero,
    registrar,
)
from conta_pridalac.servicios.presentacion303 import (
    eliminar_presentacion,
    eliminar_sin_presentar,
    hay_errores,
    marcar_rechazada,
    presentada_del_periodo,
    ruta_del_fichero,
    sin_presentar,
)
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
ENLACES_SEDE = [
    ("Modelo 190 en la sede de la AEAT", "https://sede.agenciatributaria.gob.es/Sede/irpf/retenciones-ingresos-cuenta-pagos-fraccionados/retenciones-ingresos-cuenta/obligaciones-retenedor/modelo-190.html"),
    ("Ayuda: presentar el 190 con fichero", "https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/declaraciones-informativas-ayuda-tecnica/modelos-190-198/modelo-190-fichero.html"),
]


def _ultima(ctx: Contexto, estados: tuple[str, ...]) -> PresentacionAeat | None:
    return ctx.sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ctx.ejercicio.anio,
               PresentacionAeat.periodo == PERIODO, PresentacionAeat.estado.in_(estados))
        .order_by(PresentacionAeat.id.desc())
    ).first()


def _estado(ctx: Contexto) -> tuple[str, object | None]:
    presentada = presentada_del_periodo(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, MODELO)
    if presentada is not None:
        return ("Presentado" if isinstance(presentada, PresentacionAeat) else "Presentado (importado)"), presentada
    borrador = _ultima(ctx, (BORRADOR, GENERADA))
    if borrador is not None:
        return ("Fichero generado" if borrador.estado == GENERADA else "Borrador"), borrador
    return "Sin presentar", None


def _contenido_del_fichero(ctx: Contexto, presentacion: PresentacionAeat | None):
    if presentacion is None or not presentacion.fichero_ruta:
        return None
    ruta = ruta_del_fichero(ctx.config.almacen, presentacion)
    return fichero190.leer(ruta.read_bytes().decode(fichero190.CODIFICACION)) if ruta is not None else None


class ListadoModelo190(Listado):
    nombre, titulo = "modelo-190", "Modelo 190"
    descripcion = ("Resumen anual de retenciones e ingresos a cuenta del IRPF: lo retenido a cada perceptor en el ejercicio. Doble clic en el ejercicio para ver el cálculo, los controles, guardar el borrador, "
                   "generar el fichero y registrar la presentación. Debajo, las declaraciones ya presentadas.")
    borrar = True  # sólo borra lo que no se ha presentado
    acciones_extra = [("Copiar fichero para presentar…", "accion/copiar")]
    formulario_propio = True
    editable = True
    bloque_inferior = "declaraciones-190"
    columnas = [
        Col("periodo", "Ejercicio", TEXTO, 1), Col("estado", "Estado", TEXTO, 2.4), Col("tipo", "Tipo", TEXTO, 1.3), Col("perceptores", "Perceptores", ENTERO, 1.1), Col("percepciones", "Percepciones", DINERO, 1.3),
        Col("retenciones", "Retenciones", DINERO, 1.3), Col("justificante", "Justificante", TEXTO, 1.6), Col("fichero", "Fichero generado", TEXTO, 2.4),
    ]

    def _valores(self, d) -> dict:
        if isinstance(d, PresentacionAeat):
            c = json.loads(d.casillas or "{}")
            return dict(tipo=d.tipo_presentacion.capitalize(), perceptores=len(c.get("perceptores", [])) or None, percepciones=Decimal(c.get("percepciones", "0")) or None,
                        retenciones=Decimal(c.get("retenciones", "0")) or None, justificante=d.justificante)
        if d is not None:  # importada de lo ya presentado
            c = json.loads(d.casillas or "{}")
            return dict(tipo="Presentada", perceptores=int(c.get("perceptores", 0)) or None, percepciones=Decimal(str(c.get("percepciones", 0))) or None,
                        retenciones=Decimal(str(c.get("retenciones", 0))) or None, justificante=d.justificante)
        return {}

    def filas(self, ctx, params):
        estado, d = _estado(ctx)
        valores = dict(periodo=str(ctx.ejercicio.anio), estado=estado, fichero=d.fichero_nombre if isinstance(d, PresentacionAeat) else None, **self._valores(d))
        filas = [Fila("0", valores, borrable=not estado.startswith("Presentado") and d is not None)]
        if estado.startswith("Presentado"):  # una sustitutiva en preparación no se pierde de vista
            pendiente = _ultima(ctx, (BORRADOR, GENERADA))
            if pendiente is not None:
                filas.append(Fila(f"0:{pendiente.id}", dict(
                    periodo=f"{ctx.ejercicio.anio} · {pendiente.tipo_presentacion}", estado=("Fichero generado" if pendiente.estado == GENERADA else "Borrador") + " (sin presentar)",
                    fichero=pendiente.fichero_nombre, **self._valores(pendiente)), clase="aviso-fila"))
        return filas

    # ---- ficha del ejercicio
    def formulario(self, ctx, id, errores=None, entradas=None):
        estado, existente = _estado(ctx)
        presentada = existente if estado.startswith("Presentado") else None
        borrador = existente if isinstance(existente, PresentacionAeat) and not estado.startswith("Presentado") else _ultima(ctx, (BORRADOR, GENERADA))
        entradas = entradas or dict(tipo_presentacion=borrador.tipo_presentacion if borrador is not None else ("sustitutiva" if presentada is not None else "normal"))
        errores = list(errores or [])
        try:
            calculo = calcular_190(ctx.sesion, ctx.ejercicio)
            hallazgos = controlar_190(ctx.sesion, ctx.ejercicio, calculo, tipo_presentacion=entradas["tipo_presentacion"])
        except ErrorContable as e:
            errores.append(str(e))
            calculo = hallazgos = None
        fichero = borrador if borrador is not None and borrador.fichero_ruta else None
        leido = _contenido_del_fichero(ctx, fichero)
        return "_modelo190.html", dict(
            id="0", estado=estado, presentada=presentada, borrador=borrador, fichero=fichero, calculo=calculo, errores=errores, hallazgos=hallazgos or [],
            hay_errores=bool(hallazgos) and hay_errores(hallazgos), entradas=entradas, tipos_de_presentacion=TIPOS_DE_PRESENTACION, cerrado=ctx.ejercicio.cerrado,
            diseno_actual=fichero190.DISENO_VERSION, plazo=plazo(MODELO, ctx.ejercicio.anio), sin_presentar=len(sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, MODELO)),
            registrada=presentada if isinstance(presentada, PresentacionAeat) else None, enlaces_sede=ENLACES_SEDE, contenido=leido,
            para_la_sede=borrador if borrador is not None and borrador.estado == GENERADA and ruta_del_fichero(ctx.config.almacen, borrador) is not None else None,
            identificativo=identificativo_del_fichero(ctx.config.almacen, borrador) if borrador is not None and borrador.estado == GENERADA else None, hoy=date.today(),
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        accion = datos.get("accion", "ver")
        entradas = dict(tipo_presentacion=datos.get("tipo_presentacion", "normal"))
        mensaje = None
        try:
            if accion == "eliminar_sin_presentar":
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                n, borrados = eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, ctx.config.almacen, MODELO)
                mensaje = f"Eliminado lo que no se presentó: {n} borrador(es) o fichero(s), {borrados} fichero(s) del disco"
            elif accion in ("registrar", "rechazar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                generada = _ultima(ctx, (GENERADA,))
                if generada is None:
                    raise ErrorContable("No hay un fichero generado pendiente de presentar")
                if accion == "rechazar":
                    marcar_rechazada(ctx.sesion, generada, datos.get("motivo", ""))
                    mensaje = "Marcado como rechazado: puede preparar un borrador nuevo"
                else:
                    pdf = next((contenido for nombre, contenido in ficheros if contenido), b"")
                    if not pdf:
                        raise ErrorContable("Suba el PDF «Información de la presentación» que devuelve la sede: de él se leen el justificante, el CSV y la fecha")
                    momento = None
                    if datos.get("fecha_presentacion"):
                        try:
                            momento = datetime.fromisoformat(f"{datos['fecha_presentacion']}T{datos.get('hora_presentacion') or '00:00'}")
                        except ValueError:
                            raise ErrorContable("La fecha y la hora de presentación no son válidas") from None
                    registrar(ctx.sesion, ctx.ejercicio, generada, ctx.config.almacen, pdf=pdf, justificante=datos.get("justificante") or None, csv=datos.get("csv") or None, momento=momento)
                    mensaje = f"Presentación registrada: justificante {generada.justificante} (leído del PDF)" + getattr(generada, "aviso_copia", "")
            elif accion in ("guardar", "generar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                borrador, hallazgos = crear_borrador(ctx.sesion, ctx.ejercicio, tipo_presentacion=entradas["tipo_presentacion"])
                mensaje = "Borrador guardado" + (f" con {sum(h.gravedad == ERROR for h in hallazgos)} error(es) que hay que arreglar" if hay_errores(hallazgos) else "")
                ctx.sesion.commit()  # el borrador se conserva aunque el fichero no se pueda generar
                if accion == "generar":
                    generar_fichero(ctx.sesion, ctx.ejercicio, borrador, ctx.config.almacen)
                    mensaje = f"Fichero generado: {borrador.fichero_nombre}"
            elif accion != "ver":
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, "0", errores=[str(ex)], entradas=entradas)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, "0", entradas=entradas if accion == "ver" else None)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []

    def eliminar(self, ctx, ids):
        """Borra lo no presentado: la fila de una sustitutiva o borrador pendiente («0:12») o todo lo pendiente del ejercicio («0»)."""
        for i in ids:
            if ":" in str(i):
                presentacion = ctx.sesion.get(PresentacionAeat, int(str(i).split(":")[1]))
                if presentacion is None or presentacion.empresa_id != ctx.empresa.id or presentacion.modelo != MODELO:
                    raise ErrorContable("Esa presentación no existe")
                eliminar_presentacion(ctx.sesion, presentacion, ctx.config.almacen)
            else:
                eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, ctx.config.almacen, MODELO)

    # ---- copiar el fichero generado a la carpeta de ficheros para presentar
    def accion(self, ctx, accion, items):
        if accion != "copiar":
            raise ErrorContable("Acción desconocida")
        candidatas = list(ctx.sesion.scalars(
            select(PresentacionAeat)
            .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ctx.ejercicio.anio, PresentacionAeat.fichero_ruta.is_not(None),
                   PresentacionAeat.estado.in_((GENERADA, PRESENTADA)))
            .order_by(PresentacionAeat.id.desc())
        ))
        opciones = [(p, nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.190").suffix)) for p in candidatas]
        contexto = dict(opciones=opciones, destino=ctx.config.descargas, resultado=None, errores=[])
        if items is None:
            return "_copiar_fichero.html", contexto
        datos = {k: v for k, v in items if isinstance(v, str)}
        try:
            elegida = next((p for p, _ in opciones if str(p.id) == datos.get("presentacion")), None)
            if elegida is None:
                raise ErrorContable("Elija el fichero que quiere copiar")
            ruta, nueva = exportar_presentacion(elegida, ctx.empresa, ctx.config.almacen, ctx.config.descargas)
            contexto["resultado"] = dict(ruta=ruta, nueva=nueva, id=elegida.id)
        except ErrorContable as e:
            contexto["errores"] = [str(e)]
        return "_copiar_fichero.html", contexto
