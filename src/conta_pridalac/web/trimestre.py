"""El asistente del trimestre en la web: los pasos del cierre en orden, con su estado (`servicios/asistente_trimestre.py`), para el trimestre con el que se trabaja. Doble clic en un paso para ver qué hacer y abrir su pantalla."""
from __future__ import annotations

from conta_pridalac.auditoria import auditar
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import ENTERO, TEXTO
from conta_pridalac.servicios import asistente_trimestre as svc
from conta_pridalac.servicios import copia_externa, copia_justificantes
from conta_pridalac.servicios import trimestre as tri
from conta_pridalac.servicios.modelo115 import calcular_115
from conta_pridalac.web.listados import Col, Fila, Listado
from conta_pridalac.web.modelo111 import _estado as _estado_111
from conta_pridalac.web.modelo115 import _estado as _estado_115
from conta_pridalac.web.modelo303 import _estado as _estado_303


class ListadoTrimestre(Listado):
    nombre, titulo = "trimestre", "Trimestre"
    descripcion = ("Los pasos del cierre del trimestre con el que se trabaja, en orden, cada uno con lo que queda por hacer. Todas las pantallas del trimestre (recibidas, emitidas, líneas sin factura, sugerencias) "
                   "se limitan a sus fechas. Se calcula en el momento con los datos de la contabilidad. Doble clic en un paso para ver qué hacer y abrir su pantalla; «Cambiar de trimestre» para trabajar con otro.")
    columnas = [Col("numero", "Paso", ENTERO, 0.6), Col("titulo", "Qué hacer", TEXTO, 4), Col("estado", "Estado", TEXTO, 1.4), Col("detalle", "Situación", TEXTO, 7)]
    formulario_propio = True
    editable = True
    acciones_extra = [("Cambiar de trimestre", "accion/cambiar"), ("Copiar justificantes de Hacienda", "accion/copiar"), ("Copia de seguridad en OneDrive", "accion/respaldo")]

    def texto_vacio(self, ctx, params):
        return "No hay pasos"

    def trimestre_de_trabajo(self, ctx):
        return tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio} · trabajando en {tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))}"

    def _pasos(self, ctx, periodo) -> list[svc.Paso]:
        trimestre = (periodo[0].month - 1) // 3 + 1
        try:
            hallazgos = auditar(ctx.sesion, ctx.ejercicio, almacen=ctx.config.almacen_de_adjuntos())
        except Exception:  # noqa: BLE001 - un fallo de la auditoría no debe impedir ver el resto de los pasos
            hallazgos = None
        return svc.pasos(ctx.sesion, ctx.empresa, ctx.ejercicio, periodo, _estado_303(ctx, trimestre)[0], _estado_111(ctx, trimestre)[0], ctx.config.almacen, hallazgos, copia_externa.estado(ctx.empresa, ctx.slug, ctx.config.datos / f"{ctx.slug}.sqlite"),
                          estado_115=_estado_115(ctx, trimestre)[0], hay_alquileres=bool(calcular_115(ctx.sesion, ctx.ejercicio, trimestre)[3]))

    def filas(self, ctx, params):
        periodo = tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)
        if periodo[0].year != ctx.ejercicio.anio:  # los modelos y los asientos son del ejercicio abierto: no se mezclan
            return [Fila(None, dict(numero=0, titulo=f"Trabaja en {tri.etiqueta_del_trimestre(periodo)} y tiene abierto el ejercicio {ctx.ejercicio.anio}", estado="⚠ Revisar",
                                    detalle=f"Abra el ejercicio {periodo[0].year} (arriba) o elija otro trimestre con «Cambiar de trimestre»"), clase="aviso-fila")]
        return [Fila(str(p.numero), dict(numero=p.numero, titulo=p.titulo, estado=p.rotulo, detalle=p.detalle), clase="aviso-fila" if p.estado == svc.REVISAR else "") for p in self._pasos(ctx, periodo)]

    def resumen(self, ctx, filas):
        hechos = sum(1 for f in filas if f.valores["estado"] == svc.ROTULO[svc.HECHO])
        return f"{tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))}: {hechos} de {len(filas)} pasos hechos"

    def formulario(self, ctx, id, **_):
        periodo = tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)
        try:
            numero = int(str(id))
            paso = next(p for p in self._pasos(ctx, periodo) if p.numero == numero)
        except (ValueError, StopIteration):
            raise ErrorContable("El paso no existe") from None
        trimestre = (periodo[0].month - 1) // 3 + 1
        enlace = f"/e/{ctx.slug}/{ctx.ejercicio.anio}/{paso.pantalla}" + (f"?abrir={trimestre}" if paso.pantalla in ("modelo-303", "modelo-111") else "")
        if paso.pantalla == "empresa":  # la ficha de la empresa no es un listado del ejercicio
            enlace = f"/empresa/{ctx.slug}"
        return "_paso_trimestre.html", dict(paso=paso, trimestre=trimestre, enlace=enlace)

    def accion(self, ctx, accion, items):
        if accion == "cambiar":
            return self._cambiar(ctx, items)
        if accion == "respaldo":
            return self._respaldo(ctx, items)
        if accion != "copiar":
            raise ErrorContable("Acción desconocida")
        periodo = tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)
        anio, trimestre = periodo[0].year, (periodo[0].month - 1) // 3 + 1
        carpeta = copia_justificantes.carpeta_de(ctx.empresa, anio)
        previsto = copia_justificantes.revisar_copias(ctx.sesion, ctx.empresa, anio, ctx.config.almacen, trimestre) if carpeta is not None else None  # sólo el trimestre de trabajo: los anteriores ya están
        hecho = None
        if items is not None and previsto is not None and previsto.copias:
            hecho = copia_justificantes.copiar_todos(ctx.sesion, ctx.empresa, anio, ctx.config.almacen, trimestre)
        return "_copiar_justificantes.html", dict(carpeta=carpeta, previsto=previsto, hecho=hecho, anio=anio, etiqueta=tri.etiqueta_del_trimestre(periodo))

    def _cambiar(self, ctx, items):
        """Elegir el trimestre con el que se trabaja: todas las pantallas del trimestre se limitan a sus fechas."""
        actual = tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)
        opciones = [(f"{ctx.ejercicio.anio}-{q}", f"{q}T {ctx.ejercicio.anio}") for q in (4, 3, 2, 1)]  # los trimestres del año que está abierto
        contexto = dict(opciones=opciones, actual=f"{actual[0].year}-{(actual[0].month - 1) // 3 + 1}", etiqueta=tri.etiqueta_del_trimestre(actual), hecho=None, errores=[])
        if items is not None:
            valor = next((v for k, v in items if k == "trimestre" and isinstance(v, str)), "")
            try:
                if valor not in {o for o, _ in opciones}:
                    raise ErrorContable("Elija un trimestre de la lista")
                tri.fijar_trimestre_de_trabajo(ctx.sesion, ctx.empresa, int(valor[:4]), int(valor[5]))
                ctx.sesion.commit()
                contexto["hecho"] = tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))
            except ErrorContable as ex:
                ctx.sesion.rollback()
                contexto["errores"] = [str(ex)]
        return "_cambiar_trimestre.html", contexto

    def _respaldo(self, ctx, items):
        """La copia de seguridad del final del trimestre: se hace, se lleva a la carpeta de la empresa y se verifica allí."""
        ruta_bd = ctx.config.datos / f"{ctx.slug}.sqlite"
        contexto = dict(estado=copia_externa.estado(ctx.empresa, ctx.slug, ruta_bd), errores=[])
        if items is not None and contexto["estado"].carpeta is not None:
            try:
                local, destino = copia_externa.hacer_y_llevar(ctx.empresa, ctx.slug, ruta_bd, ctx.config.almacen, ctx.config.copias)
                return None, {"mensaje": f"Copia de seguridad hecha, verificada y llevada a {destino.parent}: {destino.name}"}  # se cierra el diálogo y se avisa
            except ErrorContable as ex:
                contexto["errores"] = [str(ex)]
        return "_respaldo_externo.html", contexto
