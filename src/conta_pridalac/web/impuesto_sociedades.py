"""Impuesto sobre Sociedades (modelo 200) en la web: un renglón por ejercicio y, al abrirlo, los datos que el modelo necesita y no salen de la contabilidad
(caracteres de la declaración, datos de cierre, correcciones al resultado, retenciones, bases negativas pendientes) con el precálculo de la base y la cuota.
El fichero para la sede y la presentación vienen después; aquí solo se introducen y se revisan los datos.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import GENERADA, Ejercicio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion import libros_pdf as pdf
from conta_pridalac.exportacion.tabla import DINERO, TEXTO
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.servicios import presentacion200 as pres
from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac.web.legalizacion import _ejercicio
from conta_pridalac.web.listados import Col, Contexto, Fila, Listado, parsear_dinero

FILAS_NUEVAS = 3  # filas en blanco que se ofrecen al final de las correcciones y de las bases negativas


def _importe(texto: str | None, nombre: str) -> Decimal:
    if not (texto or "").strip():
        return isd.CERO
    try:
        return parsear_dinero(texto)
    except ValueError:
        raise ErrorContable(f"«{nombre}» no es un importe válido") from None


def _entero(texto: str | None, nombre: str) -> int:
    texto = (texto or "").strip()
    if not texto:
        return 0
    if not texto.isdigit():
        raise ErrorContable(f"{nombre}: indique un número entero")
    return int(texto)


def _txt(valor: Decimal) -> str:
    return "" if not valor else f"{valor:.2f}".replace(".", ",")


class ListadoModelo200(Listado):
    nombre, titulo = "modelo-200", "200 · Impuesto sobre Sociedades"
    descripcion = ("Liquidación anual del Impuesto sobre Sociedades. Doble clic en un ejercicio: los datos que el modelo necesita y no salen de la contabilidad (caracteres de la declaración, personal, "
                   "correcciones al resultado, retenciones, bases imponibles negativas pendientes) y el cálculo paso a paso: resultado contable, correcciones (las multas se suman solas), compensación de bases negativas, "
                   "tipo de gravamen y cuota. Se presenta en julio (los 25 días siguientes a los seis meses del cierre).")
    formulario_propio = True
    editable = True
    columnas = [Col("anio", "Ejercicio", TEXTO, 1), Col("estado", "Estado", TEXTO, 1.6), Col("resultado", "Resultado contable", DINERO, 1.4), Col("base", "Base imponible", DINERO, 1.4), Col("tipo", "Tipo", TEXTO, 1), Col("cuota", "Cuota íntegra", DINERO, 1.4)]

    def texto_vacio(self, ctx, params):
        return "No hay ejercicios"

    def filas(self, ctx, params):
        filas = []
        for ej in ctx.sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == ctx.empresa.id).order_by(Ejercicio.anio.desc())):
            try:
                p = isd.precalculo(ctx.sesion, ej)
                valores = dict(resultado=p.resultado, base=p.base_imponible, tipo="/".join(str(t) for t in p.tipo.tipos if t is not None) + " %", cuota=p.cuota_integra)
            except ErrorContable:
                valores = dict(resultado=None, base=None, tipo="", cuota=None)
            guardado = ctx.sesion.scalar(select(isd.ImpuestoSociedades).where(isd.ImpuestoSociedades.empresa_id == ctx.empresa.id, isd.ImpuestoSociedades.anio == ej.anio))
            estado = "Datos guardados" if guardado is not None else ("Sin datos" if ej.cerrado else "Ejercicio abierto")
            filas.append(Fila(str(ej.anio), dict(anio=str(ej.anio), estado=estado, **valores)))
        return filas

    # ------------------------------------------------------------------------------------------ formulario

    def formulario(self, ctx, id, errores=None, entradas=None, datos=None):
        ej = _ejercicio(ctx, id)
        errores = list(errores or [])
        datos = datos if datos is not None else isd.datos_del_ejercicio(ctx.sesion, ej)
        bases = isd.bases_negativas(ctx.sesion, ctx.empresa.id)
        if entradas is None:
            entradas = self._entradas(ctx, datos, bases)
        try:
            p = isd.precalculo(ctx.sesion, ej, datos)
        except ErrorContable as e:
            p = None
            errores.append(str(e))
        try:
            hallazgos = pres.controlar_200(ctx.sesion, ej, datos)
        except ErrorContable as e:
            hallazgos = []
            errores.append(str(e))
        generada = pres.ultima_generada(ctx.sesion, ctx.empresa.id, ej.anio)
        nombre = nombre_para_presentar(ctx.empresa, pres.MODELO, ej.anio, pres.PERIODO, "normal", "200")
        hecho = {"generar": generada is not None and generada.estado == GENERADA, "copiar": (ctx.config.descargas / nombre).is_file()}
        return "_impuesto_sociedades.html", dict(
            id=str(ej.anio), ej=ej, errores=errores, e=entradas, p=p, hallazgos=hallazgos, hay_errores=pres.hay_errores(hallazgos), generada=generada, hecho=hecho, nombre_fichero=nombre, carpeta=ctx.config.descargas, eur=pdf.eur, caracteres=isd.caracteres_disponibles(), marcadas=set(datos.marcas), retenciones=isd.CLAVES_RETENCIONES,
            n_correcciones=max(len(datos.correcciones), self._contar(entradas, "corr")) + FILAS_NUEVAS, n_bases=max(len(bases), self._contar(entradas, "bn")) + FILAS_NUEVAS,
            tipo_texto=("/".join(str(t) for t in p.tipo.tipos if t is not None) + " %") if p else "")

    @staticmethod
    def _contar(entradas, prefijo: str) -> int:
        return len({k.split("_")[1] for k in entradas if k.startswith(prefijo + "_")})

    @staticmethod
    def _entradas(ctx, datos: isd.DatosIS, bases) -> dict[str, str]:
        e = {"forzar_25": "1" if datos.forzar_25 else "", "agricola": "1" if datos.agricola else "", "compensar": "1" if datos.compensar_bases_negativas else "",
             "personal_fijo": str(datos.personal_fijo or ""), "personal_no_fijo": str(datos.personal_no_fijo or ""), "firmante_cargo": datos.firmante_cargo, "firmante_nif": datos.firmante_nif,
             "firmante_nombre": datos.firmante_nombre, "contacto_nombre": datos.contacto_nombre, "contacto_telefono": datos.contacto_telefono,
             "inc_perdida": _txt(datos.incremento_perdida_beneficios_fiscales), "intereses": _txt(datos.intereses_demora), "abono_idi": _txt(datos.abono_deducciones_idi),
             "no_deducibles": ",".join(isd.prefijos_guardados(ctx.sesion, ctx.empresa.id, isd.PARAM_NO_DEDUCIBLES)),
             "cuentas_impuesto": ",".join(isd.prefijos_guardados(ctx.sesion, ctx.empresa.id, isd.PARAM_IMPUESTO))}
        e.update({f"car_{c}": "1" for c in datos.marcas})
        e.update({f"ret_{k}": _txt(v) for k, v in datos.retenciones.items()})
        for i, c in enumerate(datos.correcciones):
            e.update({f"corr_{i}_concepto": c.concepto, f"corr_{i}_aumento": _txt(c.aumento), f"corr_{i}_disminucion": _txt(c.disminucion), f"corr_{i}_perm": "1" if c.permanente else ""})
        for i, b in enumerate(bases):
            e.update({f"bn_{i}_anio": str(b.anio), f"bn_{i}_base": _txt(b.base), f"bn_{i}_aplicado": _txt(b.aplicado), f"bn_{i}_manual": _txt(b.pendiente_manual) if b.pendiente_manual is not None else ""})
        return e

    @staticmethod
    def _datos_del_formulario(d: dict[str, str]) -> isd.DatosIS:
        datos = isd.DatosIS(
            marcas=sorted(int(k[4:]) for k, v in d.items() if k.startswith("car_") and v), forzar_25=bool(d.get("forzar_25")), agricola=bool(d.get("agricola")),
            compensar_bases_negativas=bool(d.get("compensar")), personal_fijo=_entero(d.get("personal_fijo"), "Personal fijo"), personal_no_fijo=_entero(d.get("personal_no_fijo"), "Personal no fijo"),
            firmante_cargo=d.get("firmante_cargo", "").strip(), firmante_nif=d.get("firmante_nif", "").strip().upper(), firmante_nombre=d.get("firmante_nombre", "").strip(),
            contacto_nombre=d.get("contacto_nombre", "").strip(), contacto_telefono=d.get("contacto_telefono", "").strip(),
            incremento_perdida_beneficios_fiscales=_importe(d.get("inc_perdida"), "Incremento por pérdida de beneficios fiscales"), intereses_demora=_importe(d.get("intereses"), "Intereses de demora"),
            abono_deducciones_idi=_importe(d.get("abono_idi"), "Abono de deducciones I+D+i"))
        for clave, _ in isd.CLAVES_RETENCIONES:
            importe = _importe(d.get(f"ret_{clave}"), "Retenciones")
            if importe:
                datos.retenciones[clave] = importe
        indices = sorted({int(k.split("_")[1]) for k in d if k.startswith("corr_")})
        for i in indices:
            concepto = d.get(f"corr_{i}_concepto", "").strip()
            aumento, disminucion = _importe(d.get(f"corr_{i}_aumento"), f"Aumento de «{concepto}»"), _importe(d.get(f"corr_{i}_disminucion"), f"Disminución de «{concepto}»")
            if concepto or aumento or disminucion:
                datos.correcciones.append(isd.Correccion(concepto, aumento, disminucion, bool(d.get(f"corr_{i}_perm"))))
        return datos

    def guardar_formulario(self, ctx, items, ficheros):
        d = {k: v for k, v in items if isinstance(v, str)}
        anio, accion = d.get("id", ""), d.get("accion", "ver")
        mensaje = None
        try:
            ej = _ejercicio(ctx, anio)
            datos = self._datos_del_formulario(d)
            if accion in ("guardar", "generar"):
                for clave, campo in ((isd.PARAM_NO_DEDUCIBLES, "no_deducibles"), (isd.PARAM_IMPUESTO, "cuentas_impuesto")):
                    isd.guardar_prefijos(ctx.sesion, ctx.empresa.id, clave, d.get(campo, ""))
                isd.guardar_datos(ctx.sesion, ej, datos)
                for i in sorted({int(k.split("_")[1]) for k in d if k.startswith("bn_")}):
                    año, base = d.get(f"bn_{i}_anio", "").strip(), d.get(f"bn_{i}_base", "").strip()
                    if not año:
                        continue
                    if not año.isdigit():
                        raise ErrorContable(f"Base negativa: el año «{año}» no es válido")
                    if not base:  # año sin importe: se quita
                        fila = next((b for b in isd.bases_negativas(ctx.sesion, ctx.empresa.id) if b.anio == int(año)), None)
                        if fila is not None:
                            ctx.sesion.delete(fila)
                        continue
                    manual = d.get(f"bn_{i}_manual", "").strip()
                    isd.guardar_base_negativa(ctx.sesion, ctx.empresa.id, int(año), _importe(base, f"Base negativa de {año}"), _importe(d.get(f"bn_{i}_aplicado"), f"Aplicado de {año}"),
                                              _importe(manual, f"Pendiente de {año}") if manual else None)
                mensaje = "Datos del Impuesto sobre Sociedades guardados"
                if accion == "generar":
                    ctx.sesion.commit()  # los datos se conservan aunque el fichero no se pueda generar
                    presentacion, _, avisos = pres.generar_fichero(ctx.sesion, ej, ctx.config.almacen)
                    mensaje = f"Fichero generado: {presentacion.fichero_nombre} ({len(avisos)} aviso(s) del generador)" if avisos else f"Fichero generado: {presentacion.fichero_nombre}"
            elif accion != "ver":
                raise ErrorContable("Acción desconocida")
            ctx.sesion.commit()
        except (ErrorContable, ValueError) as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, anio, errores=[str(ex)], entradas=d)
            return None, plantilla, contexto, []
        plantilla, contexto = self.formulario(ctx, anio, entradas=d if accion == "ver" else None, datos=self._datos_del_formulario(d) if accion == "ver" else None)
        contexto["_mensaje"] = mensaje
        return None, plantilla, contexto, []
