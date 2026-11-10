"""Modelo 303 en la web: un renglón por trimestre con su estado y, al abrirlo, la ficha del periodo con las casillas calculadas, los controles,
el desglose por factura y los botones para guardar el borrador y generar el fichero. Todavía no se envía nada a la AEAT.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import BORRADOR, GENERADA, PRESENTADA, Factura, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.ficheros_aeat import fichero303
from conta_pridalac.ficheros_aeat.fichero303 import contenido_legible
from conta_pridalac.servicios.exportar import exportar_presentacion, nombre_para_presentar
from conta_pridalac.servicios.modelo303 import calcular_303, periodo_de_fechas
from conta_pridalac.servicios.plazos import plazo_303
from conta_pridalac.servicios.presentacion303 import (
    TIPOS_DE_PRESENTACION,
    controlar_303,
    crear_borrador,
    eliminar_presentacion,
    eliminar_sin_presentar,
    generar_fichero,
    hay_errores,
    importe_del_nrc,
    lo_anterior,
    marcar_rechazada,
    pago_del_periodo,
    registrar_presentacion,
    ruta_del_fichero,
    sin_presentar,
    presentada_del_periodo,
)
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado, parsear_dinero

CERO = Decimal("0.00")
ENLACES_SEDE = [
    ("Modelo 303 en la sede de la AEAT (gestiones)", "https://sede.agenciatributaria.gob.es/Sede/iva/pre-303/gestiones.html"),
    ("Tutorial de presentación del modelo 303", "https://www.agenciatributaria.gob.es/Sede/todas-gestiones/impuestos-tasas/iva/modelo-303-iva-autoliquidacion_/tutorial-presentacion.html"),
]
CASILLAS_A_COMPROBAR = (27, 45, 46, 71, 87)
TIPOS = {"C": "Compensación", "I": "Ingreso", "U": "Domiciliación", "N": "Sin actividad", "D": "Devolución"}


def _etiquetas_de_casillas() -> dict[int, str]:
    """Nombre de cada casilla, sacado de la descripción del diseño de registro oficial."""
    etiquetas = {}
    for campos in fichero303.DISENO.values():
        for c in campos:
            if c["casilla"] is not None and c["casilla"] not in etiquetas:
                texto = c["desc"].replace("Liquidación (3) - Regimen General - ", "").replace("Información adicional - ", "")
                texto = re.sub(r"\s*\([^()]*\[[^()]*\)", "", texto.rsplit(" [", 1)[0])  # sin la fórmula entre paréntesis
                etiquetas[c["casilla"]] = texto.strip()
    return etiquetas


ETIQUETAS = _etiquetas_de_casillas()


def _periodo(id) -> int:
    try:
        periodo = int(str(id).split(":")[0])
    except (TypeError, ValueError):
        raise ErrorContable("Periodo no válido") from None
    if periodo not in (1, 2, 3, 4):
        raise ErrorContable("El 303 es trimestral: periodo 1 a 4")
    return periodo


def _ultima(ctx: Contexto, periodo: int, estados: tuple[str, ...]) -> PresentacionAeat | None:
    return ctx.sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ctx.ejercicio.anio,
               PresentacionAeat.periodo == f"{periodo}T", PresentacionAeat.estado.in_(estados))
        .order_by(PresentacionAeat.id.desc())
    ).first()


def _estado(ctx: Contexto, periodo: int) -> tuple[str, object | None]:
    presentada = presentada_del_periodo(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo)
    if presentada is not None:
        return ("Presentado" if isinstance(presentada, PresentacionAeat) else "Presentado (importado)"), presentada
    borrador = _ultima(ctx, periodo, (BORRADOR, GENERADA))
    if borrador is not None:
        return ("Fichero generado" if borrador.estado == GENERADA else "Borrador"), borrador
    return "Sin presentar", None


def _decimal(texto: str | None, nombre: str) -> Decimal | None:
    if not (texto or "").strip():
        return None
    try:
        return parsear_dinero(texto)
    except ValueError:
        raise ErrorContable(f"«{nombre}» no es un importe válido") from None


def _contenido_del_fichero(ctx: Contexto, presentacion: PresentacionAeat | None):
    """(datos, casillas) del fichero generado, leídos del propio fichero del almacén (lo que se enviará a la sede), o `None` si no está o ha cambiado."""
    if presentacion is None or not presentacion.fichero_ruta:
        return None
    ruta = ruta_del_fichero(ctx.config.almacen, presentacion)
    return contenido_legible(ruta.read_text(encoding="latin-1")) if ruta is not None else None


class ListadoModelo303(Listado):
    borrar = True  # sólo borra lo que no se ha presentado
    acciones_extra = [("Copiar fichero para presentar…", "accion/copiar")]
    nombre, titulo = "modelo-303", "Modelo 303"
    descripcion = "Autoliquidación trimestral del IVA. Doble clic en un trimestre para ver el cálculo, los controles, guardar el borrador, generar el fichero y registrar la presentación. Debajo, las declaraciones ya presentadas."
    formulario_propio = True
    editable = True
    bloque_inferior = "declaraciones"
    columnas = [
        Col("periodo", "Trimestre", TEXTO, 1), Col("desde", "Desde", FECHA, 1.1), Col("hasta", "Hasta", FECHA, 1.1), Col("estado", "Estado", TEXTO, 2.4),
        Col("tipo", "Tipo", TEXTO, 1.3), Col("resultado", "Resultado (71)", DINERO, 1.3), Col("compensar", "A compensar (87)", DINERO, 1.3), Col("justificante", "Justificante", TEXTO, 1.6), Col("fichero", "Fichero generado", TEXTO, 2.4),
    ]

    def filas(self, ctx, params):
        filas = []
        for periodo in (1, 2, 3, 4):
            desde, hasta = periodo_de_fechas(ctx.ejercicio.anio, periodo)
            estado, d = _estado(ctx, periodo)
            if isinstance(d, PresentacionAeat):
                casillas = json.loads(d.casillas or "{}")
                resultado, compensar, tipo, justificante = d.resultado, Decimal(casillas.get("87", "0")) or None, TIPOS.get(d.tipo_declaracion, d.tipo_declaracion), d.justificante
            elif d is not None:  # importada del programa anterior
                resultado, compensar, tipo, justificante = d.resultado, d.a_compensar or None, "Presentada" if d.tipo == 1 else f"Tipo {d.tipo}", d.justificante
            else:
                resultado = compensar = tipo = justificante = None
            fichero = d.fichero_nombre if isinstance(d, PresentacionAeat) else None
            filas.append(Fila(str(periodo), dict(periodo=f"{periodo}T {ctx.ejercicio.anio}", desde=desde, hasta=hasta, estado=estado, tipo=tipo, resultado=resultado, compensar=compensar, justificante=justificante, fichero=fichero), borrable=not estado.startswith("Presentado") and d is not None))  # lo presentado no se ofrece para borrar; sólo lo pendiente
            if estado.startswith("Presentado"):  # lo que se está preparando sobre un trimestre ya presentado (una rectificativa) no se pierde de vista
                pendiente = _ultima(ctx, periodo, (BORRADOR, GENERADA))
                if pendiente is not None:
                    casillas = json.loads(pendiente.casillas or "{}")
                    filas.append(Fila(f"{periodo}:{pendiente.id}", dict(
                        periodo=f"{periodo}T {ctx.ejercicio.anio} · {pendiente.tipo_presentacion}", desde=desde, hasta=hasta, estado=("Fichero generado" if pendiente.estado == GENERADA else "Borrador") + " (sin presentar)",
                        tipo=TIPOS.get(pendiente.tipo_declaracion, pendiente.tipo_declaracion), resultado=pendiente.resultado, compensar=Decimal(casillas.get("87", "0")) or None, justificante=None, fichero=pendiente.fichero_nombre,
                    ), clase="aviso-fila"))
        return filas

    # ---- ficha del trimestre
    def _entradas_iniciales(self, ctx, periodo: int, borrador: PresentacionAeat | None, presentada) -> dict:
        if borrador is not None:
            return dict(
                prorrata="" if borrador.prorrata is None else f"{borrador.prorrata:.2f}".replace(".", ","), bolsa=f"{borrador.bolsa_inicial:.2f}".replace(".", ",") if borrador.bolsa_manual else "",
                tipo_presentacion=borrador.tipo_presentacion, domiciliar=borrador.domiciliar, baja=borrador.baja_domiciliacion, nrc=borrador.nrc or "", rectifican=[str(i) for i in json.loads(borrador.rectifican or "[]")],
            )
        return dict(prorrata="", bolsa="", tipo_presentacion="rectificativa" if presentada is not None else "normal", domiciliar=True, baja=False, nrc="", rectifican=[])

    def formulario(self, ctx, id, errores=None, entradas=None):
        periodo = _periodo(id)
        desde, hasta = periodo_de_fechas(ctx.ejercicio.anio, periodo)
        estado, existente = _estado(ctx, periodo)
        presentada = existente if estado.startswith("Presentado") else None
        borrador = existente if isinstance(existente, PresentacionAeat) and not estado.startswith("Presentado") else _ultima(ctx, periodo, (BORRADOR, GENERADA))
        entradas = entradas or self._entradas_iniciales(ctx, periodo, borrador, presentada)
        errores = list(errores or [])
        try:
            prorrata, bolsa = _decimal(entradas["prorrata"], "Regularización de la prorrata"), _decimal(entradas["bolsa"], "Cuotas a compensar")
            rectifican = {int(i) for i in entradas["rectifican"]}
            nrc = entradas["nrc"].strip().upper() or None
            previa, anterior_69 = lo_anterior(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, entradas["tipo_presentacion"])
            calculo = calcular_303(ctx.sesion, ctx.ejercicio, periodo, regularizacion_prorrata=prorrata, rectifican=rectifican, bolsa=bolsa, anterior_69=anterior_69)
            hallazgos = controlar_303(
                ctx.sesion, ctx.ejercicio, periodo, calculo, tipo_presentacion=entradas["tipo_presentacion"], domiciliar=entradas["domiciliar"], iban=ctx.empresa.iban,
                prorrata_dada=prorrata is not None, bolsa_manual=bolsa is not None, nrc=nrc,
                nrc_importe=importe_del_nrc(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, nrc, calculo[71]),
            )
        except ErrorContable as e:
            errores.append(str(e))
            calculo = hallazgos = None
        rectificativas = [
            f for f in ctx.sesion.scalars(select(Factura).where(Factura.ejercicio_id == ctx.ejercicio.id, Factura.sentido == "R", Factura.fecha_contable >= desde, Factura.fecha_contable <= hasta).order_by(Factura.numero))
            if any(i.base < 0 or i.cuota_iva < 0 for i in f.ivas)
        ]
        desglose: dict[int, list] = {}
        if calculo is not None:
            for l in calculo.lineas:
                desglose.setdefault(l.casilla, []).append(l)
        fichero = borrador if borrador is not None and borrador.fichero_ruta else None
        return "_modelo303.html", dict(
            id=str(periodo), periodo=periodo, desde=desde, hasta=hasta, estado=estado, presentada=presentada, borrador=borrador, fichero=fichero, calculo=calculo, errores=errores,
            hallazgos=hallazgos or [], hay_errores=bool(hallazgos) and hay_errores(hallazgos), entradas=entradas, rectificativas=rectificativas, desglose=desglose, etiquetas=ETIQUETAS,
            casillas=sorted(calculo.casillas.items()) if calculo is not None else [], tipos_de_presentacion=TIPOS_DE_PRESENTACION, cerrado=ctx.ejercicio.cerrado,
            tipo_de_fichero=TIPOS.get(borrador.tipo_declaracion, "") if borrador else "", diseno_actual=fichero303.DISENO_VERSION,
            plazo=plazo_303(ctx.ejercicio.anio, periodo), pago=pago_del_periodo(ctx.sesion, ctx.ejercicio, periodo), sin_presentar=len(sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo)),
            registrada=presentada if isinstance(presentada, PresentacionAeat) else None, enlaces_sede=ENLACES_SEDE,
            contenido=_contenido_del_fichero(ctx, fichero),
            para_la_sede=borrador if borrador is not None and borrador.estado == GENERADA and ruta_del_fichero(ctx.config.almacen, borrador) is not None else None,
            comprobar=[(c, Decimal(json.loads(borrador.casillas or "{}").get(str(c), "0"))) for c in CASILLAS_A_COMPROBAR] if borrador is not None else [], hoy=date.today(),
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        periodo_id, accion = datos.get("id", ""), datos.get("accion", "ver")
        entradas = dict(
            prorrata=datos.get("prorrata", ""), bolsa=datos.get("bolsa", ""), tipo_presentacion=datos.get("tipo_presentacion", "normal"), domiciliar=datos.get("forma_pago", "domiciliacion") != "nrc", baja=datos.get("baja_domiciliacion") == "on", nrc=datos.get("nrc", ""),
            rectifican=[v for k, v in items if k == "rectifican" and isinstance(v, str)],
        )
        mensaje = None
        try:
            periodo = _periodo(periodo_id)
            if accion == "eliminar_sin_presentar":
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                n, ficheros = eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, ctx.config.almacen)
                mensaje = f"Eliminado lo que no se presentó del {periodo}T: {n} borrador(es) o fichero(s), {ficheros} fichero(s) del disco"
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
                    registrar_presentacion(
                        ctx.sesion, ctx.ejercicio, generada, ctx.config.almacen, pdf=pdf, justificante=datos.get("justificante") or None, csv=datos.get("csv") or None, momento=momento,
                    )
                    mensaje = f"Presentación registrada: justificante {generada.justificante} (leído del PDF)" + getattr(generada, "aviso_copia", "")
            elif accion in ("guardar", "generar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                borrador, hallazgos = crear_borrador(
                    ctx.sesion, ctx.ejercicio, periodo, regularizacion_prorrata=_decimal(entradas["prorrata"], "Regularización de la prorrata"), bolsa=_decimal(entradas["bolsa"], "Cuotas a compensar"),
                    rectifican={int(i) for i in entradas["rectifican"]}, tipo_presentacion=entradas["tipo_presentacion"], domiciliar=entradas["domiciliar"],
                    nrc=entradas["nrc"].strip().upper() or None, baja_domiciliacion=entradas["baja"],
                )
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
        """Borra lo no presentado: la fila de una rectificativa o borrador pendiente («3:12») o todo lo pendiente del trimestre («3»)."""
        for i in ids:
            if ":" in str(i):
                presentacion = ctx.sesion.get(PresentacionAeat, int(str(i).split(":")[1]))
                if presentacion is None or presentacion.empresa_id != ctx.empresa.id:
                    raise ErrorContable("Esa presentación no existe")
                eliminar_presentacion(ctx.sesion, presentacion, ctx.config.almacen)
            else:
                eliminar_sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, _periodo(i), ctx.config.almacen)

    # ---- copiar el fichero generado a la carpeta de ficheros para presentar
    def accion(self, ctx, accion, items):
        if accion != "copiar":
            raise ErrorContable("Acción desconocida")
        candidatas = list(ctx.sesion.scalars(
            select(PresentacionAeat)
            .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ctx.ejercicio.anio, PresentacionAeat.fichero_ruta.is_not(None),
                   PresentacionAeat.estado.in_((GENERADA, PRESENTADA)))
            .order_by(PresentacionAeat.id.desc())
        ))
        opciones = [(p, nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.303").suffix)) for p in candidatas]
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
