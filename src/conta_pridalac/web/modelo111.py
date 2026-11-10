"""Modelo 111 en la web: un renglón por trimestre con su estado y, al abrirlo, la ficha con las retenciones calculadas, los controles, el borrador, el fichero, la copia para presentar y el registro de la
presentación con el PDF de la sede. Mismo molde que el 303 (`web/modelo303.py`), con menos cosas: el 111 casi siempre se presenta sin actividad.
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
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, TEXTO
from conta_pridalac.ficheros_aeat import fichero111
from conta_pridalac.servicios.exportar import exportar_presentacion, nombre_para_presentar
from conta_pridalac.servicios.modelo111 import calcular_111
from conta_pridalac.servicios.modelo303 import periodo_de_fechas
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion111 import (
    MODELO,
    TIPOS_DE_PRESENTACION,
    controlar_111,
    crear_borrador,
    generar_fichero,
    lo_anterior,
    pago_del_periodo,
)
from conta_pridalac.servicios.presentacion303 import (
    eliminar_presentacion,
    eliminar_sin_presentar,
    hay_errores,
    importe_del_nrc,
    marcar_rechazada,
    presentada_del_periodo,
    registrar_presentacion,
    ruta_del_fichero,
    sin_presentar,
)
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
ENLACES_SEDE = [
    ("Modelo 111 en la sede de la AEAT (gestiones)", "https://sede.agenciatributaria.gob.es/Sede/irpf/retenciones-ingresos-cuenta-pagos-fraccionados/retenciones-ingresos-cuenta/obligaciones-retenedor/modelo-111.html"),
    ("Ayuda de presentación del modelo 111", "https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/presentacion-declaraciones-ayuda-tecnica/modelo-111.html"),
]
CASILLAS_A_COMPROBAR = (7, 8, 9, 28, 29, 30)
TIPOS = {"I": "Ingreso", "U": "Domiciliación", "G": "Cuenta corriente tributaria", "N": "Sin actividad"}
ETIQUETAS = {c["casilla"]: c["desc"] for c in fichero111.DISENO if c["casilla"] is not None}


def _periodo(id) -> int:
    try:
        periodo = int(str(id).split(":")[0])
    except (TypeError, ValueError):
        raise ErrorContable("Periodo no válido") from None
    if periodo not in (1, 2, 3, 4):
        raise ErrorContable("El 111 se presenta por trimestres: periodo 1 a 4")
    return periodo


def _ultima(ctx: Contexto, periodo: int, estados: tuple[str, ...]) -> PresentacionAeat | None:
    return ctx.sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ctx.ejercicio.anio,
               PresentacionAeat.periodo == f"{periodo}T", PresentacionAeat.estado.in_(estados))
        .order_by(PresentacionAeat.id.desc())
    ).first()


def _estado(ctx: Contexto, periodo: int) -> tuple[str, object | None]:
    presentada = presentada_del_periodo(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, MODELO)
    if presentada is not None:
        return ("Presentado" if isinstance(presentada, PresentacionAeat) else "Presentado (importado)"), presentada
    borrador = _ultima(ctx, periodo, (BORRADOR, GENERADA))
    if borrador is not None:
        return ("Fichero generado" if borrador.estado == GENERADA else "Borrador"), borrador
    return "Sin presentar", None


def _contenido_del_fichero(ctx: Contexto, presentacion: PresentacionAeat | None):
    if presentacion is None or not presentacion.fichero_ruta:
        return None
    ruta = ruta_del_fichero(ctx.config.almacen, presentacion)
    return fichero111.contenido_legible(ruta.read_text(encoding="latin-1")) if ruta is not None else None


class ListadoModelo111(Listado):
    nombre, titulo = "modelo-111", "Modelo 111"
    descripcion = ("Retenciones e ingresos a cuenta del IRPF (trimestral). Casi siempre se presenta sin actividad. Doble clic en un trimestre para ver el cálculo, los controles, guardar el borrador, generar el fichero y "
                   "registrar la presentación. Debajo, las declaraciones ya presentadas.")
    borrar = True  # sólo borra lo que no se ha presentado
    acciones_extra = [("Copiar fichero para presentar…", "accion/copiar")]
    formulario_propio = True
    editable = True
    bloque_inferior = "declaraciones-111"
    columnas = [
        Col("periodo", "Trimestre", TEXTO, 1), Col("desde", "Desde", FECHA, 1.1), Col("hasta", "Hasta", FECHA, 1.1), Col("estado", "Estado", TEXTO, 2.4), Col("tipo", "Tipo", TEXTO, 1.3),
        Col("perceptores", "Perceptores (07)", ENTERO, 1.2), Col("retenciones", "Retenciones (28)", DINERO, 1.3), Col("resultado", "A ingresar (30)", DINERO, 1.3), Col("justificante", "Justificante", TEXTO, 1.6),
        Col("fichero", "Fichero generado", TEXTO, 2.4),
    ]

    def _valores(self, d) -> dict:
        if isinstance(d, PresentacionAeat):
            c = json.loads(d.casillas or "{}")
            return dict(tipo=TIPOS.get(d.tipo_declaracion, d.tipo_declaracion), perceptores=int(Decimal(c.get("7", "0"))) or None, retenciones=Decimal(c.get("28", "0")) or None, resultado=d.resultado, justificante=d.justificante)
        if d is not None:  # importada del programa anterior
            c = json.loads(d.casillas or "{}")
            return dict(tipo="Sin actividad" if not d.resultado else "Presentada", perceptores=int(c.get("7", 0)) or None, retenciones=d.resultado_liquidacion or None, resultado=d.resultado, justificante=d.justificante)
        return {}

    def filas(self, ctx, params):
        filas = []
        for periodo in (1, 2, 3, 4):
            desde, hasta = periodo_de_fechas(ctx.ejercicio.anio, periodo)
            estado, d = _estado(ctx, periodo)
            valores = dict(periodo=f"{periodo}T {ctx.ejercicio.anio}", desde=desde, hasta=hasta, estado=estado, fichero=d.fichero_nombre if isinstance(d, PresentacionAeat) else None, **self._valores(d))
            filas.append(Fila(str(periodo), valores, borrable=not estado.startswith("Presentado") and d is not None))
            if estado.startswith("Presentado"):  # una complementaria en preparación no se pierde de vista
                pendiente = _ultima(ctx, periodo, (BORRADOR, GENERADA))
                if pendiente is not None:
                    filas.append(Fila(f"{periodo}:{pendiente.id}", dict(
                        periodo=f"{periodo}T {ctx.ejercicio.anio} · {pendiente.tipo_presentacion}", desde=desde, hasta=hasta,
                        estado=("Fichero generado" if pendiente.estado == GENERADA else "Borrador") + " (sin presentar)", fichero=pendiente.fichero_nombre, **self._valores(pendiente),
                    ), clase="aviso-fila"))
        return filas

    # ---- ficha del trimestre
    def _entradas_iniciales(self, borrador: PresentacionAeat | None, presentada) -> dict:
        if borrador is not None:
            return dict(tipo_presentacion=borrador.tipo_presentacion, domiciliar=borrador.domiciliar, nrc=borrador.nrc or "")
        return dict(tipo_presentacion="complementaria" if presentada is not None else "normal", domiciliar=True, nrc="")

    def formulario(self, ctx, id, errores=None, entradas=None):
        periodo = _periodo(id)
        desde, hasta = periodo_de_fechas(ctx.ejercicio.anio, periodo)
        estado, existente = _estado(ctx, periodo)
        presentada = existente if estado.startswith("Presentado") else None
        borrador = existente if isinstance(existente, PresentacionAeat) and not estado.startswith("Presentado") else _ultima(ctx, periodo, (BORRADOR, GENERADA))
        entradas = entradas or self._entradas_iniciales(borrador, presentada)
        errores = list(errores or [])
        try:
            nrc = entradas["nrc"].strip().upper() or None
            previa, anterior_30 = lo_anterior(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, entradas["tipo_presentacion"])
            calculo = calcular_111(ctx.sesion, ctx.ejercicio, periodo, anterior_30=anterior_30)
            hallazgos = controlar_111(
                ctx.sesion, ctx.ejercicio, periodo, calculo, tipo_presentacion=entradas["tipo_presentacion"], domiciliar=entradas["domiciliar"], iban=ctx.empresa.iban, nrc=nrc,
                nrc_importe=importe_del_nrc(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, nrc, calculo[30], MODELO),
            )
        except ErrorContable as e:
            errores.append(str(e))
            calculo = hallazgos = None
        fichero = borrador if borrador is not None and borrador.fichero_ruta else None
        return "_modelo111.html", dict(
            id=str(periodo), periodo=periodo, desde=desde, hasta=hasta, estado=estado, presentada=presentada, borrador=borrador, fichero=fichero, calculo=calculo, errores=errores,
            hallazgos=hallazgos or [], hay_errores=bool(hallazgos) and hay_errores(hallazgos), entradas=entradas, etiquetas=ETIQUETAS, tipos_de_presentacion=TIPOS_DE_PRESENTACION,
            casillas=sorted(calculo.casillas.items()) if calculo is not None else [], cerrado=ctx.ejercicio.cerrado, tipo_de_fichero=TIPOS.get(borrador.tipo_declaracion, "") if borrador else "",
            diseno_actual=fichero111.DISENO_VERSION, plazo=plazo(MODELO, ctx.ejercicio.anio, periodo), sin_presentar=len(sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, MODELO)),
            pago=pago_del_periodo(ctx.sesion, ctx.ejercicio, periodo, calculo[28]) if calculo is not None else None, registrada=presentada if isinstance(presentada, PresentacionAeat) else None,
            enlaces_sede=ENLACES_SEDE, contenido=_contenido_del_fichero(ctx, fichero),
            para_la_sede=borrador if borrador is not None and borrador.estado == GENERADA and ruta_del_fichero(ctx.config.almacen, borrador) is not None else None,
            comprobar=[(c, Decimal(json.loads(borrador.casillas or "{}").get(str(c), "0"))) for c in CASILLAS_A_COMPROBAR] if borrador is not None else [], hoy=date.today(),
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        periodo_id, accion = datos.get("id", ""), datos.get("accion", "ver")
        entradas = dict(tipo_presentacion=datos.get("tipo_presentacion", "normal"), domiciliar=datos.get("forma_pago", "domiciliacion") != "nrc", nrc=datos.get("nrc", ""))
        mensaje = None
        try:
            periodo = _periodo(periodo_id)
            if accion == "eliminar_sin_presentar":
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                n, borrados = eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, ctx.config.almacen, MODELO)
                mensaje = f"Eliminado lo que no se presentó del {periodo}T: {n} borrador(es) o fichero(s), {borrados} fichero(s) del disco"
            elif accion in ("registrar", "rechazar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                generada = _ultima(ctx, periodo, (GENERADA,))
                if generada is None:
                    raise ErrorContable("No hay un fichero generado de este trimestre pendiente de presentar")
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
                    registrar_presentacion(ctx.sesion, ctx.ejercicio, generada, ctx.config.almacen, pdf=pdf, justificante=datos.get("justificante") or None, csv=datos.get("csv") or None, momento=momento)
                    mensaje = f"Presentación registrada: justificante {generada.justificante} (leído del PDF)" + getattr(generada, "aviso_copia", "")
            elif accion in ("guardar", "generar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                borrador, hallazgos = crear_borrador(ctx.sesion, ctx.ejercicio, periodo, tipo_presentacion=entradas["tipo_presentacion"], domiciliar=entradas["domiciliar"], nrc=entradas["nrc"].strip().upper() or None)
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
            plantilla, contexto = self.formulario(ctx, periodo_id, errores=[str(ex)], entradas=entradas)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, periodo_id, entradas=entradas if accion == "ver" else None)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []

    def eliminar(self, ctx, ids):
        """Borra lo no presentado: la fila de una complementaria o borrador pendiente («4:12») o todo lo pendiente del trimestre («4»)."""
        for i in ids:
            if ":" in str(i):
                presentacion = ctx.sesion.get(PresentacionAeat, int(str(i).split(":")[1]))
                if presentacion is None or presentacion.empresa_id != ctx.empresa.id or presentacion.modelo != MODELO:
                    raise ErrorContable("Esa presentación no existe")
                eliminar_presentacion(ctx.sesion, presentacion, ctx.config.almacen)
            else:
                eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, _periodo(i), ctx.config.almacen, MODELO)

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
        opciones = [(p, nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.111").suffix)) for p in candidatas]
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
