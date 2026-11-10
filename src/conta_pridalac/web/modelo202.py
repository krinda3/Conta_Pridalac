"""Modelo 202 en la web: un renglón por pago fraccionado (1P, 2P, 3P) con su estado y, al abrirlo, la ficha con la base sacada del Impuesto sobre Sociedades, los controles, el borrador, el fichero, la copia para
presentar y el registro de la presentación con el PDF de la sede. Mismo molde que el 111 (`web/modelo111.py`).
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
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.ficheros_aeat import fichero202
from conta_pridalac.servicios.exportar import exportar_presentacion, nombre_para_presentar
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion202 import (
    MODELO,
    TIPOS_DE_PRESENTACION,
    a_ingresar_de,
    calcular_202,
    controlar_202,
    crear_borrador,
    etiqueta,
    generar_fichero,
    lo_anterior,
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
    ("Modelo 202 en la sede de la AEAT (ayuda de presentación)", "https://sede.agenciatributaria.gob.es/Sede/ayuda/consultas-informaticas/presentacion-declaraciones-ayuda-tecnica/modelo-202.html"),
]
TIPOS = {"I": "Ingreso", "U": "Domiciliación", "G": "Cuenta corriente tributaria", "N": "Resultado cero"}
NOMBRES = {1: "1P · abril", 2: "2P · octubre", 3: "3P · diciembre"}


def _periodo(id) -> int:
    try:
        periodo = int(str(id).split(":")[0])
    except (TypeError, ValueError):
        raise ErrorContable("Periodo no válido") from None
    if periodo not in (1, 2, 3):
        raise ErrorContable("El 202 tiene tres pagos fraccionados: periodo 1 a 3")
    return periodo


def _ultima(ctx: Contexto, periodo: int, estados: tuple[str, ...]) -> PresentacionAeat | None:
    return ctx.sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == ctx.empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ctx.ejercicio.anio,
               PresentacionAeat.periodo == etiqueta(periodo), PresentacionAeat.estado.in_(estados))
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
    if ruta is None:
        return None
    d = fichero202.datos_del_fichero(ruta.read_text(encoding="latin-1"))
    return [("Declarante", f"{d['nif']} · {d['nombre']}"), ("Periodo", f"{d['periodo']}P {d['ejercicio']} · inicio {d['inicio']:%d/%m/%Y}"), ("Tipo de declaración", TIPOS.get(d["tipo"], d["tipo"])),
            ("Modalidad", "A · art. 40.2 LIS" if d["modalidad"] == "A" else d["modalidad"]), ("Tipo de gravamen", d["tipo_gravamen"]), ("Base del pago [01]", f"{d['base']}"),
            ("A ingresar [03]", f"{d['a_ingresar']}")] + ([("IBAN", d["iban"])] if d["iban"] else []) + ([("Complementaria", "sí")] if d["complementaria"] else [])


class ListadoModelo202(Listado):
    nombre, titulo = "modelo-202", "Modelo 202"
    descripcion = ("Pago fraccionado del Impuesto sobre Sociedades (abril, octubre y diciembre, del 1 al 20). La base es la cuota del último IS presentado, que se lee de su fichero .200 (herramienta importar_is); el pago es el "
                   "18 % de esa base. Doble clic en un pago para ver el cálculo, los controles, guardar el borrador, generar el fichero y registrar la presentación.")
    borrar = True  # sólo borra lo que no se ha presentado
    acciones_extra = [("Copiar fichero para presentar…", "accion/copiar")]
    formulario_propio = True
    editable = True
    columnas = [
        Col("periodo", "Pago", TEXTO, 1.4), Col("desde", "Desde", FECHA, 1.1), Col("hasta", "Hasta", FECHA, 1.1), Col("estado", "Estado", TEXTO, 2.2), Col("tipo", "Tipo", TEXTO, 1.4),
        Col("is", "IS de referencia", TEXTO, 1.2), Col("base", "Base [01]", DINERO, 1.2), Col("resultado", "A ingresar [03]", DINERO, 1.3), Col("justificante", "Justificante", TEXTO, 1.6), Col("fichero", "Fichero generado", TEXTO, 2.4),
    ]

    def _valores(self, d, periodo: int, ctx: Contexto) -> dict:
        referencia = f"IS {ctx.ejercicio.anio - 1 if periodo >= 2 else ctx.ejercicio.anio - 2}"
        if isinstance(d, PresentacionAeat):
            c = json.loads(d.casillas or "{}")
            return {"tipo": TIPOS.get(d.tipo_declaracion, d.tipo_declaracion), "is": f"IS {c.get('anio_is', '')}", "base": Decimal(c.get("base", "0")), "resultado": d.resultado, "justificante": d.justificante}
        if d is not None:  # importada del programa anterior
            c = json.loads(d.casillas or "{}")
            return {"tipo": "Resultado cero" if not d.resultado else "Presentada", "is": referencia, "base": Decimal(c.get("1", "0")), "resultado": d.resultado, "justificante": d.justificante}
        return {"is": referencia}

    def filas(self, ctx, params):
        filas = []
        for periodo in (1, 2, 3):
            p = plazo(MODELO, ctx.ejercicio.anio, periodo)
            estado, d = _estado(ctx, periodo)
            valores = dict(periodo=f"{NOMBRES[periodo]} {ctx.ejercicio.anio}", desde=p.inicio, hasta=p.fin, estado=estado, fichero=d.fichero_nombre if isinstance(d, PresentacionAeat) else None, **self._valores(d, periodo, ctx))
            filas.append(Fila(str(periodo), valores, borrable=not estado.startswith("Presentado") and d is not None))
            if estado.startswith("Presentado"):  # una complementaria en preparación no se pierde de vista
                pendiente = _ultima(ctx, periodo, (BORRADOR, GENERADA))
                if pendiente is not None:
                    filas.append(Fila(f"{periodo}:{pendiente.id}", dict(
                        periodo=f"{NOMBRES[periodo]} {ctx.ejercicio.anio} · {pendiente.tipo_presentacion}", desde=p.inicio, hasta=p.fin,
                        estado=("Fichero generado" if pendiente.estado == GENERADA else "Borrador") + " (sin presentar)", fichero=pendiente.fichero_nombre, **self._valores(pendiente, periodo, ctx),
                    ), clase="aviso-fila"))
        return filas

    # ---- ficha del pago
    def _entradas_iniciales(self, borrador: PresentacionAeat | None, presentada) -> dict:
        if borrador is not None:
            return dict(tipo_presentacion=borrador.tipo_presentacion, domiciliar=borrador.domiciliar, nrc=borrador.nrc or "")
        return dict(tipo_presentacion="complementaria" if presentada is not None else "normal", domiciliar=True, nrc="")

    def formulario(self, ctx, id, errores=None, entradas=None):
        periodo = _periodo(id)
        p = plazo(MODELO, ctx.ejercicio.anio, periodo)
        estado, existente = _estado(ctx, periodo)
        presentada = existente if estado.startswith("Presentado") else None
        borrador = existente if isinstance(existente, PresentacionAeat) and not estado.startswith("Presentado") else _ultima(ctx, periodo, (BORRADOR, GENERADA))
        entradas = entradas or self._entradas_iniciales(borrador, presentada)
        errores = list(errores or [])
        a_ingresar = CERO
        try:
            nrc = entradas["nrc"].strip().upper() or None
            previa, anterior = lo_anterior(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, entradas["tipo_presentacion"])
            calculo = calcular_202(ctx.sesion, ctx.ejercicio, periodo)
            a_ingresar = a_ingresar_de(calculo, anterior)
            hallazgos = controlar_202(
                ctx.sesion, ctx.ejercicio, periodo, calculo, tipo_presentacion=entradas["tipo_presentacion"], anterior=anterior, domiciliar=entradas["domiciliar"], nrc=nrc,
                nrc_importe=importe_del_nrc(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, nrc, a_ingresar, MODELO),
            )
        except ErrorContable as e:
            errores.append(str(e))
            calculo = hallazgos = None
            anterior = CERO
        fichero = borrador if borrador is not None and borrador.fichero_ruta else None
        return "_modelo202.html", dict(
            id=str(periodo), periodo=periodo, nombre_periodo=NOMBRES[periodo], desde=p.inicio, hasta=p.fin, estado=estado, presentada=presentada, borrador=borrador, fichero=fichero, calculo=calculo, errores=errores,
            hallazgos=hallazgos or [], hay_errores=bool(hallazgos) and hay_errores(hallazgos), entradas=entradas, tipos_de_presentacion=TIPOS_DE_PRESENTACION, a_ingresar=a_ingresar, anterior=anterior,
            cerrado=ctx.ejercicio.cerrado, tipo_de_fichero=TIPOS.get(borrador.tipo_declaracion, "") if borrador else "", diseno_actual=fichero202.DISENO_VERSION, plazo=p,
            sin_presentar=len(sin_presentar(ctx.sesion, ctx.empresa.id, ctx.ejercicio.anio, periodo, MODELO)), registrada=presentada if isinstance(presentada, PresentacionAeat) else None,
            enlaces_sede=ENLACES_SEDE, contenido=_contenido_del_fichero(ctx, fichero),
            para_la_sede=borrador if borrador is not None and borrador.estado == GENERADA and ruta_del_fichero(ctx.config.almacen, borrador) is not None else None, hoy=date.today(),
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
                mensaje = f"Eliminado lo que no se presentó del {etiqueta(periodo)}: {n} borrador(es) o fichero(s), {borrados} fichero(s) del disco"
            elif accion in ("registrar", "rechazar"):
                if ctx.ejercicio.cerrado:
                    raise ErrorContable("El ejercicio está cerrado")
                generada = _ultima(ctx, periodo, (GENERADA,))
                if generada is None:
                    raise ErrorContable("No hay un fichero generado de este pago pendiente de presentar")
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
        """Borra lo no presentado: la fila de una complementaria o borrador pendiente («2:12») o todo lo pendiente del pago («2»)."""
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
        opciones = [(p, nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.202").suffix)) for p in candidatas]
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
