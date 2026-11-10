"""Copias de seguridad en la web: lista de copias de la empresa y las acciones hacer, verificar, restaurar y recuperar justificantes (sólo lo que se haya hecho desde aquí o esté en la carpeta de copias)."""
from __future__ import annotations

from pathlib import Path

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import ENTERO, TEXTO, Columna, Tabla
from conta_pridalac.servicios import copias as svc
from conta_pridalac.web.listados import Col, Contexto, Detalle, Fila, Listado

CONFIRMACION = "RESTAURAR"


def _tamano(n: int) -> str:
    return f"{n / 1024 / 1024:,.1f} MB".replace(",", "X").replace(".", ",").replace("X", ".")


def _copia(ctx: Contexto, nombre: str) -> svc.Copia:
    copia = next((c for c in svc.listar_copias(ctx.config.copias, ctx.slug) if c.nombre == nombre), None)
    if copia is None:
        raise ErrorContable("Esa copia no existe")
    return copia


def _clase(c: svc.Copia) -> str:
    return "completa" if c.completa else "ligera"


def _pdfs(c: svc.Copia) -> str:
    return "lleva todos los PDF de las facturas" if c.completa else f"no lleva {c.fuera} PDF de facturas ({_tamano(c.fuera_bytes)}): solo su huella"


def _liberar(ctx: Contexto):
    """Cierra la sesión de esta petición y las conexiones a la base de la empresa para poder sustituir su fichero."""
    def liberar() -> None:
        ctx.sesion.close()
        motor = ctx.config.motores.pop(ctx.slug, None)
        if motor is not None:
            motor.dispose()
    return liberar


class ListadoCopias(Listado):
    nombre, titulo = "copias", "Copias de seguridad"
    descripcion = ("Copia de la base de datos de la empresa, verificada al hacerla. La copia normal es ligera: lleva la base y los documentos que no se pueden recuperar de otro sitio, y de los PDF de las facturas solo su huella "
                   "(ya están en sus carpetas de trimestre); la completa los lleva también. «Recuperar justificantes» repone los PDF que falten buscándolos por su contenido. Doble clic en una copia para ver su contenido y comprobarla.")
    borrar = True
    acciones_extra = [("Hacer una copia ahora", "accion/hacer"), ("Verificar una copia", "accion/verificar"), ("Restaurar una copia…", "accion/restaurar"), ("Recuperar justificantes…", "accion/recuperar")]
    columnas = [
        Col("fecha", "Fecha y hora", TEXTO, 1.6), Col("tipo", "Tipo", TEXTO, 1.4), Col("tamano", "Tamaño", TEXTO, 1), Col("facturas", "Facturas", ENTERO, 0.9), Col("asientos", "Asientos", ENTERO, 0.9),
        Col("justificantes", "Ficheros de justificantes", ENTERO, 1.3), Col("nombre", "Fichero", TEXTO, 3),
    ]

    def filas(self, ctx, params):
        return [
            Fila(c.nombre, dict(fecha=f"{c.momento:%d/%m/%Y %H:%M}", tipo=("Antes de restaurar · " if "antes_de_restaurar" in c.etiqueta else "") + _clase(c).capitalize(), tamano=_tamano(c.tamano),
                                facturas=c.tablas.get("factura"), asientos=c.tablas.get("asiento"), justificantes=c.justificantes, nombre=c.nombre),
                 clase="aviso-fila" if "antes_de_restaurar" in c.etiqueta else "")
            for c in svc.listar_copias(ctx.config.copias, ctx.slug)
        ]

    def texto_vacio(self, ctx, params):
        return f"No hay copias de seguridad en {ctx.config.copias}"

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · carpeta de copias: {ctx.config.copias}"

    def detalle(self, ctx, id):
        copia = _copia(ctx, id)
        problemas = svc.verificar_copia(copia.ruta)
        tabla = Tabla("Registros en la copia", [Columna("Tabla", ancho=3), Columna("Registros", ENTERO, 1)], [[t, n] for t, n in copia.tablas.items()])
        datos = [
            ("Empresa", f"{copia.empresa} ({copia.nif})"), ("Hecha el", f"{copia.momento:%d/%m/%Y %H:%M:%S}"), ("Tamaño", _tamano(copia.tamano)), ("Tipo", f"{_clase(copia).capitalize()}: {_pdfs(copia)}"), ("Ficheros de justificantes que lleva", str(copia.justificantes)),
            ("Verificación", "Correcta: huellas, integridad de la base y recuento de registros" if not problemas else "CON PROBLEMAS: " + "; ".join(problemas)), ("Ruta", str(copia.ruta)),
        ]
        return Detalle(f"Copia de seguridad · {copia.nombre}", tabla, datos, [], [("Descargar la copia", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/copias/{copia.nombre}/descargar")])

    def eliminar(self, ctx, ids):
        for i in ids:
            _copia(ctx, i).ruta.unlink()

    # ---- hacer, verificar y restaurar
    def accion(self, ctx, accion, items):
        if accion not in ("hacer", "verificar", "restaurar", "recuperar"):
            raise ErrorContable("Acción desconocida")
        bd = ctx.config.datos / f"{ctx.slug}.sqlite"
        contexto = dict(modo=accion, copias=svc.listar_copias(ctx.config.copias, ctx.slug), carpeta=ctx.config.copias, errores=[], resultado=None, restaurado=None, confirmacion=CONFIRMACION, tamano=_tamano,
                        recuperacion=None, faltan=None, carpetas_buscadas="")
        if items is None:
            if accion == "recuperar":
                contexto["faltan"] = len(svc.justificantes_que_faltan(bd, ctx.config.almacen))
            return "_copias.html", contexto
        datos = {k: v for k, v in items if isinstance(v, str)}
        try:
            if accion == "hacer":
                completa = datos.get("completa") == "on"
                ruta = svc.hacer_copia(ctx.slug, bd, ctx.config.almacen, ctx.config.copias, completa=completa)
                return None, {"mensaje": f"Copia {'completa' if completa else 'ligera'} hecha y verificada: {ruta.name} ({_tamano(ruta.stat().st_size)})"}
            if accion == "recuperar":
                carpetas = [Path(linea.strip().strip('"')) for linea in datos.get("carpetas", "").splitlines() if linea.strip()]
                contexto["carpetas_buscadas"] = datos.get("carpetas", "")
                if not carpetas:
                    raise ErrorContable("Indique al menos una carpeta donde buscar los PDF (por ejemplo, la de su OneDrive con las facturas)")
                r = svc.recuperar_justificantes(bd, ctx.config.almacen, carpetas)
                contexto["recuperacion"] = dict(recuperados=r.recuperados, revisados=r.revisados, faltan=r.faltan[:40], mas=max(0, len(r.faltan) - 40), total_faltan=len(r.faltan))
                return "_copias.html", contexto
            copia = _copia(ctx, datos.get("copia", ""))
            if accion == "verificar":
                problemas = svc.verificar_copia(copia.ruta)
                contexto["resultado"] = {"copia": copia.nombre, "problemas": problemas, "tipo": _clase(copia), "pdfs": _pdfs(copia)}
                return "_copias.html", contexto
            if datos.get("confirmacion", "").strip() != CONFIRMACION:
                raise ErrorContable(f"Para restaurar escriba {CONFIRMACION} en el campo de confirmación")
            previa = svc.restaurar_copia(copia.ruta, ctx.slug, bd, ctx.config.almacen, ctx.config.copias, liberar=_liberar(ctx))
            contexto["copias"] = svc.listar_copias(ctx.config.copias, ctx.slug)
            contexto["restaurado"] = {"copia": copia.nombre, "previa": previa.name, "faltan": len(svc.justificantes_que_faltan(bd, ctx.config.almacen))}  # el resultado se queda en el diálogo: no es un aviso que desaparece
            return "_copias.html", contexto
        except (ErrorContable, OSError) as e:
            contexto["errores"] = [str(e) if isinstance(e, ErrorContable) else f"No se pudo completar: {e.strerror or e}"]
            return "_copias.html", contexto
