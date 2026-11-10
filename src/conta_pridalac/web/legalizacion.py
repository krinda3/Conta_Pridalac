"""Legalización de libros en la web: un renglón por ejercicio y, al abrirlo, los controles, los números de libro y los PDF que Conta ya genera (diario e inventario y cuentas anuales).
Lo que sale de aquí se entrega a Legalia2, que firma y presenta en el Registro Mercantil.
"""
from __future__ import annotations

import shutil
from datetime import date

from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import ENVIADA, Ejercicio, Legalizacion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha
from conta_pridalac.exportacion.tabla import ENTERO, TEXTO
from conta_pridalac.servicios import libros_oficiales as lo
from conta_pridalac.web.comun import fecha_texto
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

ESTADOS = {"preparada": "Preparada", "enviada": "Enviada al Registro"}


def _ejercicio(ctx: Contexto, id) -> Ejercicio:
    try:
        anio = int(str(id))
    except (TypeError, ValueError):
        raise ErrorContable("Ejercicio no válido") from None
    ej = ctx.sesion.scalar(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id, Ejercicio.anio == anio))
    if ej is None:
        raise ErrorContable(f"No existe el ejercicio {anio}")
    return ej


def _legalizacion(ctx: Contexto, anio: int) -> Legalizacion | None:
    return ctx.sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == ctx.empresa.id, Legalizacion.anio == anio))


class ListadoLegalizacion(Listado):
    nombre, titulo = "legalizacion-libros", "Legalización de libros"
    descripcion = ("Los libros que se legalizan cada año en el Registro Mercantil: diario, inventario y cuentas anuales, registro de socios y registro de actas. Conta prepara los PDF para Legalia2, que los firma y "
                   "los presenta. Doble clic en un ejercicio para ver los controles, los números de libro y generar los libros. Se presentan en los cuatro meses siguientes al cierre (hasta el 30 de abril).")
    formulario_propio = True
    editable = True
    columnas = [Col("anio", "Ejercicio", TEXTO, 1), Col("estado", "Estado", TEXTO, 1.6), Col("libros", "Libros preparados", ENTERO, 1.2), Col("preparada", "Preparados el", TEXTO, 1.6), Col("zip", "ZIP para Legalia2", TEXTO, 2.4)]

    def texto_vacio(self, ctx, params):
        return "No hay ejercicios"

    def filas(self, ctx, params):
        filas = []
        for ej in ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id).order_by(Ejercicio.anio.desc())):
            leg = _legalizacion(ctx, ej.anio)
            estado = "Sin preparar" if leg is None else ESTADOS.get(leg.estado, leg.estado)
            if leg is None and not ej.cerrado:
                estado = "Ejercicio abierto"
            filas.append(Fila(str(ej.anio), dict(anio=str(ej.anio), estado=estado, libros=len([l for l in leg.libros if l.fichero_ruta]) if leg else 0,
                                                  preparada=f"{leg.preparada_en:%d/%m/%Y %H:%M}" if leg and leg.preparada_en else "", zip=leg.zip_nombre if leg else "")))
        return filas

    def formulario(self, ctx, id, errores=None, entradas=None):
        ej = _ejercicio(ctx, id)
        leg = _legalizacion(ctx, ej.anio)
        propuestos = lo.numeros_propuestos(ctx.sesion, ctx.empresa.id, ej.anio)
        actuales = {l.clave: l.numero for l in leg.libros} if leg else {}
        entradas = entradas or {clave: str(actuales.get(clave) or propuestos[clave][0]) for _, clave, _, _ in lo.LIBROS}
        libros_actuales = {l.clave: l for l in leg.libros} if leg else {}
        for _, clave, _, _ in lo.LIBROS:  # la fecha hasta la que se legalizó antes: la guardada, la del libro anterior o, si no es el primero, el fin del año anterior
            if f"anterior_{clave}" not in entradas:
                numero = int(entradas[clave]) if str(entradas[clave]).isdigit() else 1
                guardada = libros_actuales[clave].fecha_ejercicio_anterior if clave in libros_actuales else None
                propuesta = guardada or propuestos[clave][1] or (date(ej.anio - 1, 12, 31) if numero > 1 else None)
                entradas[f"anterior_{clave}"] = fecha_texto(propuesta) if propuesta else ""
        try:
            hallazgos = lo.controlar(ctx.sesion, ej, ctx.config.almacen_de_adjuntos())
            avisos_memoria = lo.memoria(ctx.sesion, ej)[1]
        except ErrorContable as e:
            hallazgos, avisos_memoria = [], []
            errores = list(errores or []) + [str(e)]
        libros = {l.clave: l for l in leg.libros} if leg else {}
        return "_legalizacion.html", dict(
            id=str(ej.anio), ej=ej, leg=leg, errores=list(errores or []), hallazgos=hallazgos, hay_errores=any(h.gravedad == ERROR for h in hallazgos), entradas=entradas, libros_def=lo.LIBROS,
            libros=libros, generados=lo.GENERADOS, avisos_memoria=avisos_memoria, faltan_para_el_zip=lo.datos_que_faltan_para_el_zip(ctx.empresa), enviada=leg is not None and leg.estado == ENVIADA, propuestos=propuestos,
        )

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        anio, accion = datos.get("id", ""), datos.get("accion", "ver")
        entradas = {clave: datos.get(f"numero_{clave}", "").strip() for _, clave, _, _ in lo.LIBROS}
        entradas.update({f"anterior_{clave}": datos.get(f"anterior_{clave}", "").strip() for _, clave, _, _ in lo.LIBROS})
        mensaje = None
        try:
            ej = _ejercicio(ctx, anio)
            if accion == "generar":
                try:
                    numeros = {c: int(entradas[c]) for _, c, _, _ in lo.LIBROS if entradas[c]}
                except ValueError:
                    raise ErrorContable("Los números de libro son enteros") from None
                if any(n < 1 for n in numeros.values()):
                    raise ErrorContable("Los números de libro empiezan en 1")
                try:
                    anteriores = {c: (parsear_fecha(entradas[f"anterior_{c}"]) if entradas[f"anterior_{c}"] else None) for _, c, _, _ in lo.LIBROS}
                except ErrorContable as e:
                    raise ErrorContable(f"Fecha del ejercicio anterior: {e}") from None
                leg = lo.generar_libros(ctx.sesion, ej, ctx.config.almacen, numeros=numeros, anteriores=anteriores)
                mensaje = "Libros generados: " + ", ".join(l.fichero_nombre for l in leg.libros if l.fichero_ruta) + (f" · ZIP para Legalia2: {leg.zip_nombre}" if leg.zip_nombre else "")
            elif accion == "registrar_envio":
                pdf = next((contenido for nombre, contenido in ficheros if contenido), b"")
                fecha = parsear_fecha(datos["fecha_envio"]) if datos.get("fecha_envio", "").strip() else None
                leg = lo.registrar_envio(ctx.sesion, ej, ctx.config.almacen, pdf=pdf or None, fecha=fecha, referencia=datos.get("referencia", "").strip() or None)
                mensaje = f"Envío registrado: {leg.enviada_en:%d/%m/%Y}" + (f" · entrada {leg.numero_entrada}" if leg.numero_entrada else "")
            elif accion == "copiar_zip":
                leg = _legalizacion(ctx, ej.anio)
                if leg is None or not leg.zip_ruta:
                    raise ErrorContable("Todavía no hay ZIP: genere los libros (y complete los datos de la ficha que falten)")
                origen = ctx.config.almacen_de_adjuntos().raiz / leg.zip_ruta
                if not origen.is_file():
                    raise ErrorContable("El ZIP no está en el almacén: genere los libros de nuevo")
                ctx.config.descargas.mkdir(parents=True, exist_ok=True)
                destino = ctx.config.descargas / leg.zip_nombre
                shutil.copyfile(origen, destino)
                mensaje = f"ZIP copiado a {destino}"
            elif accion != "ver":
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, anio, errores=[str(ex)], entradas=entradas)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, anio, entradas=entradas if accion == "ver" else None)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []
