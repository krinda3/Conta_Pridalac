"""Modelo 390 en la web: las casillas del resumen anual del IVA calculadas desde los libros (`servicios/modelo390.py`) y los controles contra los cuatro 303 del año.

La tabla es la hoja de casillas para comprobar (el Excel y el PDF de la barra la exportan). El botón «Generar fichero y presentar» abre la ficha del ejercicio con los controles, el borrador,
el fichero para la sede, la copia para presentar y el registro de la presentación con el PDF de la sede (mismo molde que el 190).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import BORRADOR, GENERADA, PRESENTADA, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, TEXTO
from conta_pridalac.ficheros_aeat import fichero390
from conta_pridalac.servicios.exportar import exportar_presentacion, nombre_para_presentar
from conta_pridalac.servicios.modelo390 import calcular_390
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion303 import eliminar_sin_presentar, hay_errores, marcar_rechazada, presentada_del_periodo, ruta_del_fichero, sin_presentar
from conta_pridalac.servicios.presentacion390 import MODELO, PERIODO, TIPOS_DE_PRESENTACION, controlar_390, crear_borrador, generar_fichero, registrar
from conta_pridalac.web.listados import Campo, Col, Fila, Listado

ROTULO = {"ok": "✔ Coincide", "aviso": "⚠ Revisar", "error": "✖ Error"}
ENLACES_SEDE = [
    ("Sede electrónica de la AEAT", "https://sede.agenciatributaria.gob.es"),
    ("Diseño de registro del 390 (Excel)", "https://sede.agenciatributaria.gob.es/static_files/Sede/Disenyo_registro/DR_300_399/archivos_26/dr390e2026.xlsx"),
]


def _ultima(ctx, estados):
    return ctx.sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ctx.ejercicio.anio, PresentacionAeat.periodo == PERIODO,
               PresentacionAeat.estado.in_(estados))
        .order_by(PresentacionAeat.id.desc())
    ).first()


def _estado(ctx):
    presentada = presentada_del_periodo(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, MODELO)
    if presentada is not None:
        return ("Presentado" if isinstance(presentada, PresentacionAeat) else "Presentado (importado)"), presentada
    borrador = _ultima(ctx, (BORRADOR, GENERADA))
    if borrador is not None:
        return ("Fichero generado" if borrador.estado == GENERADA else "Borrador"), borrador
    return "Sin presentar", None


def _contenido_del_fichero(ctx, presentacion):
    """Lo que lleva el fichero generado (identificación y nº de casillas), o `None` si no está en el almacén o ha cambiado."""
    if presentacion is None or not presentacion.fichero_ruta:
        return None
    ruta = ruta_del_fichero(ctx.config.almacen, presentacion)
    if ruta is None:
        return None
    texto = ruta.read_bytes().decode(fichero390.CODIFICACION)
    p1 = fichero390.leer(texto)["01000"]
    representantes = [(p1[n].strip(), p1[i], p1[f]) for n, i, f in fichero390.POS_REPRESENTANTES_LECTURA if p1[n].strip()]
    actividades = [(p1[a].strip(), p1[a + 40].strip(), p1[a + 43].strip()) for a in fichero390.POS_ACTIVIDADES if p1[a].strip()]
    return dict(nif=p1[14].strip(), nombre=p1[23].strip(), ejercicio=p1[103], actividades=actividades, representantes=representantes,
                casillas=len(fichero390.casillas_del_fichero(texto)), sustitutiva=p1[134] == "1", justificante_anterior=p1[136].strip())


class ListadoModelo390(Listado):
    nombre, titulo = "modelo-390", "Modelo 390"
    descripcion = ("Declaración-resumen anual del IVA del ejercicio, calculada con las mismas facturas que los cuatro 303. Arriba, los controles contra los 303 (lo que la AEAT cruza); debajo, las casillas "
                   "por apartado del formulario. El botón «Generar fichero y presentar» prepara el fichero y registra la presentación.")
    columnas = [Col("seccion", "Apartado", TEXTO, 2.6), Col("concepto", "Concepto", TEXTO, 5), Col("casillas", "Casillas", TEXTO, 1.2), Col("tipo", "Tipo %", DINERO, 0.8), Col("base", "Base imponible", DINERO, 1.4),
                Col("cuota", "Cuota / importe", DINERO, 1.4), Col("nota", "Nota", TEXTO, 2.2)]
    formulario_propio = True
    acciones_extra = [("Generar fichero y presentar…", "f/0"), ("Copiar fichero para presentar…", "accion/copiar")]
    parametros = [Campo("prorrata", "Prorrata definitiva (%)", "dinero", ayuda="Sólo si se aplica la regla de prorrata: se anota a mano en la casilla 118 de la sede")]

    def texto_vacio(self, ctx, params):
        return "No hay IVA en este ejercicio"

    def _calculo(self, ctx, params):
        prorrata = params.get("prorrata")
        try:
            return calcular_390(ctx.sesion, ctx.ejercicio, prorrata=Decimal(prorrata) if prorrata not in (None, "") else None)
        except ArithmeticError:
            raise ErrorContable("La prorrata no es un número") from None

    def filas(self, ctx, params):
        c = self._calculo(ctx, params)
        filas = [Fila(None, dict(seccion="Controles contra los 303", concepto=k.texto, casillas=ROTULO[k.gravedad], tipo=None, base=None, cuota=None, nota=""), clase="" if k.gravedad == "ok" else "aviso-fila") for k in c.controles]
        filas += [Fila(None, dict(seccion="Aviso del cálculo", concepto=a, casillas="⚠", tipo=None, base=None, cuota=None, nota=""), clase="aviso-fila") for a in c.avisos]
        filas += [Fila(None, dict(seccion=f.seccion, concepto=f.concepto, casillas=f.casillas, tipo=f.tipo, base=f.base, cuota=f.cuota, nota=f.nota)) for f in c.filas]
        return filas

    def resumen(self, ctx, filas):
        c = self._calculo(ctx, {})
        pendientes = [k for k in c.controles if k.gravedad != "ok"]
        origen = ", ".join(f"{p}T {o}" for p, o in c.origen_303.items())
        return f"Ejercicio {c.anio}: {'los controles coinciden con los 303' if not pendientes and c.controles else f'{len(pendientes)} control(es) por revisar'} · 303: {origen}"

    # ---- ficha del ejercicio: controles, borrador, fichero y registro de la presentación
    def formulario(self, ctx, id, errores=None, entradas=None):
        estado, existente = _estado(ctx)
        presentada = existente if estado.startswith("Presentado") else None
        borrador = existente if isinstance(existente, PresentacionAeat) and not estado.startswith("Presentado") else _ultima(ctx, (BORRADOR, GENERADA))
        entradas = entradas or dict(tipo_presentacion=borrador.tipo_presentacion if borrador is not None else ("sustitutiva" if presentada is not None else "normal"))
        errores = list(errores or [])
        try:
            calculo = calcular_390(ctx.sesion, ctx.ejercicio)
            hallazgos = controlar_390(ctx.sesion, ctx.ejercicio, calculo, tipo_presentacion=entradas["tipo_presentacion"])
        except ErrorContable as e:
            errores.append(str(e))
            calculo = hallazgos = None
        fichero = borrador if borrador is not None and borrador.fichero_ruta else None
        return "_modelo390.html", dict(
            id="0", estado=estado, presentada=presentada, borrador=borrador, fichero=fichero, calculo=calculo, errores=errores, hallazgos=hallazgos or [],
            hay_errores=bool(hallazgos) and hay_errores(hallazgos), entradas=entradas, tipos_de_presentacion=TIPOS_DE_PRESENTACION, cerrado=ctx.ejercicio.cerrado,
            diseno_actual=fichero390.DISENO_VERSION, plazo=plazo(MODELO, ctx.ejercicio.anio), sin_presentar=len(sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, 0, MODELO)),
            registrada=presentada if isinstance(presentada, PresentacionAeat) else None, enlaces_sede=ENLACES_SEDE, contenido=_contenido_del_fichero(ctx, fichero),
            para_la_sede=borrador if borrador is not None and borrador.estado == GENERADA and ruta_del_fichero(ctx.config.almacen, borrador) is not None else None, hoy=date.today(),
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
        opciones = [(p, nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.390").suffix)) for p in candidatas]
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
