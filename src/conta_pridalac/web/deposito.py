"""Depósito de cuentas en la web: un renglón por ejercicio y, al abrirlo, la pantalla de «Datos de cierre» (como la del programa anterior: personal, otros datos, presentador, certificación, memoria, periodo medio de pago y base de reparto),
los controles, los importes con su código de D2 y el ZIP que D2 importa.
Lo que sale de aquí se entrega a D2 (Legalia2), que firma y presenta en el Registro Mercantil; Conta calcula la huella del ZIP y prepara el PDF de la certificación y el de la huella.
"""
from __future__ import annotations

import shutil

from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import ENVIADA, DepositoCuentas, Ejercicio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha
from conta_pridalac.exportacion import libros_pdf as pdf
from conta_pridalac.exportacion.tabla import TEXTO
from conta_pridalac.servicios import deposito_cuentas as dc
from conta_pridalac.web.comun import fecha_texto
from conta_pridalac.web.legalizacion import _ejercicio
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado

CARPETA_DESCARGAS = "Registro Mercantil"  # subcarpeta de la carpeta de descargas donde se dejan el ZIP y la certificación del depósito
ESTADOS = {"preparado": "Preparado", "preparada": "Preparado", "enviada": "Depositado"}
CAMPOS_DEPOSITO = ("fecha_formulacion", "fecha_aprobacion", "pmp_actual", "pmp_anterior", "mujeres_organo", "miembros_organo", "mujeres_organo_anterior", "miembros_organo_anterior")


def _deposito(ctx: Contexto, anio: int) -> DepositoCuentas | None:
    return ctx.sesion.scalar(select(DepositoCuentas).where(DepositoCuentas.empresa_id == ctx.empresa.id, DepositoCuentas.anio == anio))


def _entero(texto: str, nombre: str) -> int | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    if not texto.isdigit():
        raise ErrorContable(f"{nombre}: indique un número entero")
    return int(texto)


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


class ListadoDeposito(Listado):
    nombre, titulo = "deposito-cuentas", "Depósito de cuentas"
    descripcion = ("Las cuentas anuales que se depositan en el Registro Mercantil. Doble clic en un ejercicio: la pantalla de datos de cierre (personal, certificación, memoria, periodo medio de pago y base de reparto) con lo que Conta sabe ya "
                   "calculado, los controles y el ZIP que importa D2 (formulario, XBRL y memoria) con su huella digital, la certificación del acuerdo de la junta lista para firmar y el PDF de la huella. "
                   "D2 firma y presenta. El plazo es de un mes desde la aprobación de las cuentas (antes del 30 de junio).")
    formulario_propio = True
    editable = True
    columnas = [Col("anio", "Ejercicio", TEXTO, 1), Col("estado", "Estado", TEXTO, 1.6), Col("aprobacion", "Cuentas aprobadas el", TEXTO, 1.6), Col("preparado", "Preparado el", TEXTO, 1.6), Col("carpeta", "ZIP para D2", TEXTO, 2.2)]

    def texto_vacio(self, ctx, params):
        return "No hay ejercicios"

    def filas(self, ctx, params):
        filas = []
        for ej in ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id).order_by(Ejercicio.anio.desc())):
            dep = _deposito(ctx, ej.anio)
            estado = "Sin preparar" if dep is None else ESTADOS.get(dep.estado, dep.estado)
            if dep is None and not ej.cerrado:
                estado = "Ejercicio abierto"
            filas.append(Fila(str(ej.anio), dict(anio=str(ej.anio), estado=estado, aprobacion=f"{dep.fecha_aprobacion:%d/%m/%Y}" if dep and dep.fecha_aprobacion else "",
                                                  preparado=f"{dep.preparado_en:%d/%m/%Y %H:%M}" if dep and dep.preparado_en else "", carpeta=dep.zip_nombre if dep and dep.zip_nombre else "")))
        return filas

    def formulario(self, ctx, id, errores=None, entradas=None):
        ej = _ejercicio(ctx, id)
        dep = _deposito(ctx, ej.anio)
        acta = dc.acta_de_aprobacion(ctx.sesion, ej)
        errores = list(errores or [])
        try:
            importes = dc.importes_de_las_cuentas(ctx.sesion, ej)
            cierre = dc.cierre_efectivo(ctx.sesion, ej, dep, importes)
            compras = dc.compras_netas(ctx.sesion, ej)
            avisos_memoria = dc.lo.memoria(ctx.sesion, ej)[1]
        except ErrorContable as e:
            importes, cierre, compras, avisos_memoria = None, {}, dc.CERO, []
            errores.append(str(e))
        if entradas is None:  # lo guardado o, si no hay nada, lo que Conta propone
            propuesta = dep.fecha_aprobacion if dep and dep.fecha_aprobacion else (acta.fecha if acta else None)
            previo = dc.organo_anterior(ctx.sesion, ej)
            entradas = {c: _texto(getattr(dep, c, None)) for c in CAMPOS_DEPOSITO}
            entradas["fecha_formulacion"] = fecha_texto(dep.fecha_formulacion) if dep and dep.fecha_formulacion else ""
            entradas["fecha_aprobacion"] = fecha_texto(propuesta) if propuesta else ""
            if dep is None and previo is not None:  # el órgano de administración rara vez cambia: se propone el del año anterior
                entradas["mujeres_organo"], entradas["miembros_organo"] = _texto(previo.mujeres_organo), _texto(previo.miembros_organo)
            entradas.update({f"c_{k}": v for k, v in cierre.items()})
        else:
            cierre = {**cierre, **{k[2:]: v for k, v in entradas.items() if k.startswith("c_") and v != ""}}
        try:
            pmp = (_entero(entradas.get("pmp_actual", ""), "Periodo medio de pago"), _entero(entradas.get("pmp_anterior", ""), "Periodo medio de pago anterior"))
        except ErrorContable as e:
            pmp = None
            errores.append(str(e))
        try:
            hallazgos = dc.controlar(ctx.sesion, ej, dep, pmp=pmp)
        except ErrorContable as e:
            hallazgos = []
            errores.append(str(e))
        try:
            aprobacion = parsear_fecha(entradas["fecha_aprobacion"]) if entradas.get("fecha_aprobacion", "").strip() else (dep.fecha_aprobacion if dep else None)
        except ErrorContable:
            aprobacion = None
        resultado = importes.estado_pyg.importe("D") if importes else dc.CERO
        return "_deposito.html", dict(
            id=str(ej.anio), ej=ej, dep=dep, errores=errores, hallazgos=hallazgos, hay_errores=any(h.gravedad == ERROR for h in hallazgos), entradas=entradas, importes=importes, avisos_memoria=avisos_memoria,
            enviado=dep is not None and dep.estado == ENVIADA, acta=acta, plazo=dc.plazo_de_deposito(ej, aprobacion), resultado=pdf.eur(resultado), compras=pdf.eur(compras), compras_importe=str(compras),
            aplicacion=dc.APLICACION, total_aplicacion=pdf.eur(dc.total_aplicacion({k[2:]: v for k, v in entradas.items() if k.startswith("c_")})), 
            hecho=self._pasos_hechos(ctx, ej, dep),
            nombre_cac=dc.nombre_de_la_certificacion(ctx.empresa, ej.anio), carpeta_rm=ctx.config.descargas / CARPETA_DESCARGAS, presentador=" ".join(x for x in (ctx.empresa.presentador_nombre, ctx.empresa.presentador_apellido1, ctx.empresa.presentador_apellido2) if x),
        )

    @staticmethod
    def _pasos_hechos(ctx, ej, dep) -> dict[str, bool]:
        """Qué pasos del depósito ya se han dado: el botón lo muestra (✓)."""
        def copiado(nombre: str | None) -> bool:
            return bool(nombre) and (ctx.config.descargas / CARPETA_DESCARGAS / nombre).is_file()
        preparado = dep is not None and bool(dep.zip_nombre)
        return {"preparar": preparado, "zip": preparado and copiado(dep.zip_nombre), "huella": preparado and bool(dep.huella_d2),
                "cac": preparado and bool(dep.huella_d2) and copiado(dc.nombre_de_la_certificacion(ctx.empresa, ej.anio)), "envio": dep is not None and dep.estado == ENVIADA}

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        anio, accion = datos.get("id", ""), datos.get("accion", "ver")
        entradas = {c: datos.get(c, "").strip() for c in CAMPOS_DEPOSITO}
        entradas.update({f"c_{k}": datos.get(f"c_{k}", "").strip() for k in dc.CLAVES_CIERRE})
        mensaje = None
        try:
            ej = _ejercicio(ctx, anio)
            if accion in ("preparar", "guardar"):
                try:
                    formulacion = parsear_fecha(entradas["fecha_formulacion"]) if entradas["fecha_formulacion"] else None
                    aprobacion = parsear_fecha(entradas["fecha_aprobacion"]) if entradas["fecha_aprobacion"] else None
                except ErrorContable as e:
                    raise ErrorContable(f"Fecha: {e}") from None
                dep = dc.preparar_deposito(
                    ctx.sesion, ej, ctx.config.almacen, fecha_formulacion=formulacion, fecha_aprobacion=aprobacion, pmp_actual=_entero(entradas["pmp_actual"], "Periodo medio de pago"),
                    pmp_anterior=_entero(entradas["pmp_anterior"], "Periodo medio de pago anterior"), mujeres_organo=_entero(entradas["mujeres_organo"], "Mujeres en el órgano de administración"),
                    miembros_organo=_entero(entradas["miembros_organo"], "Miembros del órgano de administración"), mujeres_organo_anterior=_entero(entradas["mujeres_organo_anterior"], "Mujeres en el órgano el año anterior"),
                    miembros_organo_anterior=_entero(entradas["miembros_organo_anterior"], "Miembros del órgano el año anterior"), cierre={k: entradas[f"c_{k}"] for k in dc.CLAVES_CIERRE},
                    solo_guardar=accion == "guardar")
                mensaje = "Datos de cierre guardados" if accion == "guardar" else f"Depósito preparado: {dep.zip_nombre} (huella {dep.zip_huella})"
            elif accion == "registrar_envio":
                pdf_acuse = next((contenido for nombre, contenido in ficheros if contenido), b"")
                fecha = parsear_fecha(datos["fecha_envio"]) if datos.get("fecha_envio", "").strip() else None
                dep = dc.registrar_envio(ctx.sesion, ej, ctx.config.almacen, pdf_acuse=pdf_acuse or None, fecha=fecha, referencia=datos.get("referencia", "").strip() or None)
                mensaje = f"Depósito registrado: {dep.enviado_en:%d/%m/%Y}" + (f" · entrada {dep.numero_entrada}" if dep.numero_entrada else "")
            elif accion == "registrar_huella":
                subido = next((contenido for nombre, contenido in ficheros if contenido), b"")
                dep = dc.registrar_huella(ctx.sesion, ej, ctx.config.almacen, huella=datos.get("huella_d2", "").strip() or None, pdf_o_txt=subido or None)
                mensaje = f"Huella de D2 guardada ({dep.huella_d2}): certificación preparada para firmar"
            elif accion in ("copiar_zip", "copiar_cac"):
                dep = _deposito(ctx, ej.anio)
                if dep is None or not dep.carpeta_ruta or not dep.zip_nombre:
                    raise ErrorContable("Todavía no hay ZIP: prepare el depósito")
                carpeta = ctx.config.almacen_de_adjuntos().raiz / dep.carpeta_ruta
                nombre = dep.zip_nombre if accion == "copiar_zip" else dc.nombre_de_la_certificacion(ctx.empresa, ej.anio)
                if not (carpeta / nombre).is_file():
                    raise ErrorContable("El ZIP no está en el almacén: prepare el depósito de nuevo" if accion == "copiar_zip" else "Todavía no hay certificación: registre antes la huella que genera D2")
                destino = ctx.config.descargas / CARPETA_DESCARGAS
                destino.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(carpeta / nombre, destino / nombre)
                mensaje = f"Copiado a {destino / nombre}"
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
