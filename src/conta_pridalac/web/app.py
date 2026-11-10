"""Aplicación web local (FastAPI + HTMX): `uvicorn conta_pridalac.web.app:crear_app --factory` o `python -m conta_pridalac.web`."""
from __future__ import annotations

import json
import logging
import os
import time
import secrets
import tempfile
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from conta_pridalac.db.modelos import Adjunto, Asiento, DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaTrimestre, MovimientoBanco, PresentacionAeat
from conta_pridalac.servicios.entorno import es_ensayo
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion import a_excel, a_pdf
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, PORCENTAJE, formatear
from conta_pridalac.web.config import Configuracion
from conta_pridalac.web.empresa import EmpresaBloqueada, EmpresaSinCertificado, exigir_acceso
from conta_pridalac.web import ayuda
from conta_pridalac.web import datos as datos_web
from conta_pridalac.web import sistema
from conta_pridalac.web.alta_empresa import crear_router as router_de_alta
from conta_pridalac.web.empresa import crear_router as router_de_empresa
from conta_pridalac.web import preferencias
from conta_pridalac.web.definiciones import caja_de, construir_menu, menu_de_empresa, todos_los_listados
from conta_pridalac.servicios.empresa import modelos_visibles
from conta_pridalac.web.listados import (
    Contexto,
    a_texto_de_formulario,
    filtrar,
    leer_formulario,
    ordenar,
    tabla_de_listado,
)
from conta_pridalac.web.tema import css_de_tema

AQUI = Path(__file__).resolve().parent
TIPOS_MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _clase_numero(valor, tipo: str) -> str:
    if tipo not in (DINERO, ENTERO, PORCENTAJE):
        return ""
    return "num neg" if isinstance(valor, Decimal) and valor < 0 else "num"


ICONO_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#8cb33e"/><path d="M16 26V12m0 0c0-4 3-7 8-7 0 5-3 8-8 7zm0 6c0-3-2-5-6-5 0 4 2 6 6 5z" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def crear_app(config: Configuracion | None = None) -> FastAPI:
    app = FastAPI(title="Conta Pridalac", docs_url=None, redoc_url=None)
    app.state.config = config or Configuracion()
    app.state.listados = todos_los_listados()
    app.state.importaciones = {}  # token → ((empresa, ejercicio, listado), bytes del Excel, nombre): vistas previas pendientes de confirmar
    app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
    plantillas = Jinja2Templates(directory=AQUI / "plantillas")
    plantillas.env.filters["fmt"] = formatear
    menu = construir_menu(app.state.listados)
    plantillas.env.globals.update(ayuda_url=ayuda.url_de_ayuda, clase_numero=_clase_numero, a_texto=a_texto_de_formulario, menu=menu, caja_de=lambda nombre: caja_de(menu, nombre))

    # ---------------------------------------------------------------------------------------- dependencias

    def contexto(slug: str, anio: int, request: Request):
        config: Configuracion = request.app.state.config
        try:
            sesion = config.sesion(slug)
        except KeyError:
            raise HTTPException(404, f"No existe la empresa «{slug}»") from None
        try:
            empresa = sesion.scalars(select(Empresa)).first()
            ejercicio = sesion.scalar(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id, Ejercicio.anio == anio)) if empresa else None
            if ejercicio is None:
                raise HTTPException(404, f"La empresa «{slug}» no tiene el ejercicio {anio}")
            exigir_acceso(request, slug, empresa)
            yield Contexto(sesion, empresa, ejercicio, slug, config, es_ensayo(sesion, empresa.id))
        finally:
            sesion.close()

    @app.exception_handler(EmpresaBloqueada)
    def empresa_bloqueada(request: Request, ex: EmpresaBloqueada):
        volver = request.url.path if not request.headers.get("HX-Request") else (request.headers.get("HX-Current-URL", "").split("//", 1)[-1].partition("/")[2] or "")
        destino = f"/empresa/{ex.slug}/entrar?" + urlencode({"volver": volver if volver.startswith("/") else "/" + volver})
        if request.headers.get("HX-Request"):
            return Response(status_code=401, headers={"HX-Redirect": destino})
        return RedirectResponse(destino, status_code=303)

    @app.exception_handler(EmpresaSinCertificado)
    def empresa_sin_certificado(request: Request, ex: EmpresaSinCertificado):
        destino = f"/empresa/{ex.slug}?sin_certificado=1"
        if request.headers.get("HX-Request"):
            return Response(status_code=401, headers={"HX-Redirect": destino})
        return RedirectResponse(destino, status_code=303)

    def listado_de(nombre: str, request: Request):
        listado = request.app.state.listados.get(nombre)
        if listado is None:
            raise HTTPException(404, f"No existe el listado «{nombre}»")
        return listado

    def menu_de(ctx) -> list:
        """El menú de la empresa sin los modelos que no presenta. Usa una sesión propia y corta: la de la petición puede estar ya cerrada (tras restaurar una copia se sustituye la base),
        y volver a usarla dejaría abierta una conexión a un fichero que se acaba de reemplazar."""
        config = getattr(ctx, "config", None)
        if config is None:
            return menu
        try:
            sesion = config.sesion(ctx.slug)
        except Exception:  # noqa: BLE001 - el menú completo es mejor que ninguna pantalla
            return menu
        try:
            empresa = sesion.scalars(select(Empresa)).first()
            return menu_de_empresa(menu, modelos_visibles(sesion, empresa)) if empresa is not None else menu
        finally:
            sesion.close()

    def render(request: Request, nombre: str, **datos) -> HTMLResponse:
        datos.setdefault("preferencias", preferencias.leer(request.app.state.config))
        ctx = datos.get("ctx")
        if ctx is not None and getattr(ctx, "empresa", None) is not None and "menu" not in datos:  # el menú de cada empresa: sólo los modelos que presenta
            datos["menu"] = menu_de(ctx)
        datos.setdefault("ensayo", ctx is not None and ctx.ensayo)  # el aviso de copia de ensayo sale en todas las pantallas de la empresa
        return plantillas.TemplateResponse(request, nombre, datos)

    def ejercicios_de(sesion) -> list[Ejercicio]:
        return list(sesion.scalars(select(Ejercicio).order_by(Ejercicio.anio.desc())))

    def leer_listado(request: Request, listado, ctx: Contexto):
        """Parámetros, filtro y orden de la petición; devuelve (filas, errores, estado de la barra)."""
        consulta = request.query_params
        crudos = {c.nombre: consulta.get(c.nombre, c.defecto) for c in listado.parametros}
        params, errores = leer_formulario(listado.parametros, crudos, ctx, alta=False)
        for c in listado.parametros:  # los selects con valor por defecto
            if params.get(c.nombre) is None and c.defecto and c.tipo == "select":
                params[c.nombre] = c.defecto
        filas = []
        if not errores:
            try:
                filas = listado.filas(ctx, params)
            except (ErrorContable, ValueError) as e:
                errores.append(str(e))
        q = consulta.get("q", "")
        orden, direccion = consulta.get("orden", ""), consulta.get("dir", "asc")
        if orden:  # las filas de resumen (saldo anterior, total de la cuenta) sólo tienen sentido en el orden natural
            filas = [f for f in filas if "resumen" not in f.clase]
        filas = ordenar(filtrar(filas, listado.columnas, q), listado.columnas, orden or None, direccion == "desc")
        estado = dict(q=q, orden=orden, dir=direccion, crudos=crudos, ocultas={c for c in consulta.get("ocultas", "").split(",") if c})
        return filas, params, errores, estado

    # ---------------------------------------------------------------------------------------- generales

    @app.post("/_apagar", include_in_schema=False)
    def apagar(request: Request):
        """Cierra el programa. Exige una cabecera propia (un navegador no la puede enviar desde otra web sin permiso) y que la petición venga de este equipo."""
        if request.headers.get("X-Conta") != "apagar" or (request.client and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient")):
            raise HTTPException(403, "No permitido")
        servidor = getattr(request.app.state, "servidor", None)
        if servidor is None:
            raise HTTPException(409, "El programa no se arrancó con su propio servidor: ciérrelo desde la ventana donde se ejecuta")
        servidor.should_exit = True
        return Response(status_code=204)

    @app.post("/_latido", include_in_schema=False)
    def latido(request: Request):
        """Señal de que hay una página abierta (sirve para que el programa se cierre solo al cerrar la última pestaña)."""
        request.app.state.ultimo_latido = time.monotonic()
        return Response(status_code=204)

    @app.post("/_preferencias", include_in_schema=False)
    async def guardar_preferencia(request: Request):
        """Guarda una preferencia de pantalla (tema, disposición del menú, última caja abierta). Mismas garantías que `/_apagar`: cabecera propia y petición de este equipo."""
        if request.headers.get("X-Conta") != "preferencia" or (request.client and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient")):
            raise HTTPException(403, "No permitido")
        datos = await request.json()
        try:
            preferencias.guardar(request.app.state.config, str(datos.get("clave")), str(datos.get("valor")))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return Response(status_code=204)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(ICONO_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/tema.css")
    def tema_css():
        return Response(css_de_tema(), media_type="text/css", headers={"Cache-Control": "no-cache"})

    app.include_router(router_de_empresa(lambda request: request.app.state.config, lambda *a, **k: render(*a, **k)))
    app.include_router(router_de_alta(lambda request: request.app.state.config, lambda *a, **k: render(*a, **k)))
    ayuda.registrar(app, render, contexto)  # antes de las rutas genéricas de los listados
    sistema.registrar(app, render)  # /programa y /normativa: de toda la instalación, no de una empresa
    datos_web.registrar(app, render)  # /datos y /bloqueado: la carpeta de datos y el candado

    @app.get("/e/{slug}/{anio}/plantilla-excel/{tipo}")
    def plantilla_de_excel(tipo: str, ctx: Contexto = Depends(contexto)):
        """La plantilla de Excel para cargar facturas recibidas o emitidas sin Verifactu."""
        from conta_pridalac.servicios.plantillas_excel import plantilla

        try:
            contenido, nombre = plantilla(tipo)
        except ValueError:
            raise HTTPException(404, "Solo hay plantillas de facturas recibidas y emitidas") from None
        return Response(contenido, media_type=TIPOS_MIME["xlsx"], headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request, m: str = "", t: str = "ok"):
        config: Configuracion = request.app.state.config
        empresas = []
        for slug in config.empresas():
            sesion = config.sesion(slug)
            try:
                empresa = sesion.scalars(select(Empresa)).first()
                empresas.append(dict(slug=slug, nombre=empresa.nombre if empresa else slug, protegida=bool(empresa and empresa.certificado_ruta), ejercicios=[(e.anio, e.cerrado) for e in ejercicios_de(sesion)]))
            finally:
                sesion.close()
        return render(request, "inicio.html", empresas=empresas, carpeta=config.datos, ctx=None, sistema=sistema.resumen_para_inicio(config), datos=datos_web.resumen_para_inicio(config), mensaje=m, tipo=t)

    def _plazos_del_panel(ctx: Contexto, ejercicios) -> list:
        """Los plazos de los modelos que corren. Si la vigilancia fallara no debe tumbar el panel: se anota y se sigue."""
        from conta_pridalac.servicios.vigilancia import plazos_de_la_empresa

        try:
            return plazos_de_la_empresa(ctx.sesion, ejercicios)
        except Exception:  # noqa: BLE001
            logging.getLogger("conta_pridalac").exception("No se pudieron calcular los plazos de los modelos")
            return []

    @app.get("/e/{slug}/{anio}", response_class=HTMLResponse)
    def panel(request: Request, ctx: Contexto = Depends(contexto)):
        ejercicios = ejercicios_de(ctx.sesion)
        return render(request, "panel.html", ctx=ctx, listados=request.app.state.listados, ejercicios=ejercicios, listado=None, plazos=_plazos_del_panel(ctx, ejercicios))

    # ---------------------------------------------------------------------------------------- listados

    @app.get("/e/{slug}/{anio}/{nombre}", response_class=HTMLResponse)
    def pagina(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        crudos = {c.nombre: request.query_params.get(c.nombre, c.defecto) for c in listado.parametros}
        return render(request, "listado.html", ctx=ctx, listado=listado, listados=request.app.state.listados, ejercicios=ejercicios_de(ctx.sesion), crudos=crudos,
                      subtitulo=listado.subtitulo(ctx, {}), q=request.query_params.get("q", ""))

    @app.get("/e/{slug}/{anio}/{nombre}/tabla", response_class=HTMLResponse)
    def tabla(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        filas, params, errores, estado = leer_listado(request, listado, ctx)
        return render(request, "_tabla.html", ctx=ctx, listado=listado, filas=filas, errores=errores, totales=listado.totales(filas) if filas else None,
                      vacio=listado.texto_vacio(ctx, params), resumen=listado.resumen(ctx, filas), **estado)

    @app.get("/e/{slug}/{anio}/{nombre}/exportar.{formato}")
    def exportar(request: Request, nombre: str, formato: str, ctx: Contexto = Depends(contexto)):
        if formato not in TIPOS_MIME:
            raise HTTPException(404, "Formato no admitido (pdf o xlsx)")
        listado = listado_de(nombre, request)
        filas, params, errores, estado = leer_listado(request, listado, ctx)
        if errores:
            raise HTTPException(400, "; ".join(errores))
        tabla = tabla_de_listado(listado, ctx, filas, params, estado["ocultas"])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / f"{nombre}.{formato}"
            (a_pdf if formato == "pdf" else a_excel)(tabla, ruta)
            contenido = ruta.read_bytes()
        fichero = f"{ctx.slug}_{ctx.ejercicio.anio}_{nombre}.{formato}"
        return Response(contenido, media_type=TIPOS_MIME[formato], headers={"Content-Disposition": f'attachment; filename="{fichero}"'})

    def formulario(request: Request, listado, ctx, id=None, valores=None, errores=None):
        if valores is None:
            if id:
                actuales = listado.valores_formulario(ctx, id)
                valores = {c.nombre: a_texto_de_formulario(actuales.get(c.nombre), c.tipo) for c in listado.campos}
            else:
                valores = {c.nombre: c.defecto for c in listado.campos}
        return render(request, "_formulario.html", ctx=ctx, listado=listado, id=id, valores=valores, errores=errores or [],
                      opciones={c.nombre: c.lista_de_opciones(ctx) for c in listado.campos if c.tipo == "select"})

    def formulario_propio(request: Request, listado, ctx, id):
        try:
            plantilla, datos = listado.formulario(ctx, id)
        except ErrorContable as e:
            raise HTTPException(404, str(e)) from None
        return render(request, plantilla, ctx=ctx, listado=listado, **datos)

    @app.get("/e/{slug}/{anio}/{nombre}/nuevo", response_class=HTMLResponse)
    def nuevo(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        if not listado.anadir:
            raise HTTPException(405, "Este listado no admite altas")
        if listado.formulario_propio:
            return formulario_propio(request, listado, ctx, None)
        return formulario(request, listado, ctx)

    @app.get("/e/{slug}/{anio}/{nombre}/f/{id}", response_class=HTMLResponse)
    def abrir(request: Request, nombre: str, id: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        if listado.formulario_propio:
            return formulario_propio(request, listado, ctx, id)
        if listado.editable:
            return formulario(request, listado, ctx, id)
        detalle = listado.detalle(ctx, id)
        if detalle is None:
            raise HTTPException(404, "Sin detalle")
        return render(request, "_detalle.html", ctx=ctx, listado=listado, detalle=detalle, id=id)

    def mensaje(tipo: str, texto: str, **extra) -> dict:
        return {"mensaje": {"tipo": tipo, "texto": texto}, **extra}

    @app.post("/e/{slug}/{anio}/{nombre}/guardar", response_class=HTMLResponse)
    async def guardar(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        formulario_http = await request.form()
        if listado.formulario_propio:
            items = list(formulario_http.multi_items())
            ficheros = [(f.filename, await f.read()) for _, f in items if hasattr(f, "filename") and f.filename]
            try:
                id_nuevo, plantilla, datos, advertencias = listado.guardar_formulario(ctx, items, ficheros)
            except ErrorContable as e:
                ctx.sesion.rollback()
                raise HTTPException(400, str(e)) from None
            if plantilla:
                aviso = datos.pop("_mensaje", None)  # el formulario sigue abierto pero se avisa de lo hecho y se refresca el listado
                respuesta = render(request, plantilla, ctx=ctx, listado=listado, **datos)
                if aviso:
                    respuesta.headers["HX-Trigger"] = json.dumps(mensaje("ok", aviso, refrescar=True))
                return respuesta
            respuesta = HTMLResponse("")
            texto = "Guardado" + ("; ojo: " + " · ".join(advertencias) if advertencias else "")
            respuesta.headers["HX-Trigger"] = json.dumps(mensaje("aviso" if advertencias else "ok", texto, refrescar=True, cerrarModal=True))
            return respuesta
        datos_crudos = {k: v for k, v in formulario_http.items()}
        id = datos_crudos.pop("id", None) or None
        if not (listado.editable if id else listado.anadir):
            raise HTTPException(405, "Operación no admitida")
        datos, errores = leer_formulario(listado.campos, datos_crudos, ctx, alta=id is None)
        if not errores:
            try:
                listado.guardar(ctx, id, datos)
                ctx.sesion.commit()
            except (ErrorContable, ValueError, IntegrityError) as e:
                ctx.sesion.rollback()
                errores.append(str(e.orig) if isinstance(e, IntegrityError) else str(e))
        if errores:
            return formulario(request, listado, ctx, id, valores=datos_crudos, errores=errores)
        respuesta = HTMLResponse("")
        respuesta.headers["HX-Trigger"] = json.dumps(mensaje("ok", "Guardado", refrescar=True, cerrarModal=True))
        return respuesta

    @app.post("/e/{slug}/{anio}/{nombre}/recalcular", response_class=HTMLResponse)
    async def recalcular(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        if not listado.formulario_propio:
            raise HTTPException(405, "Este listado no recalcula")
        plantilla, datos = listado.recalcular(ctx, list((await request.form()).multi_items()))
        return render(request, plantilla, ctx=ctx, listado=listado, **datos)

    @app.api_route("/e/{slug}/{anio}/{nombre}/accion/{accion}", methods=["GET", "POST"], response_class=HTMLResponse)
    async def accion_propia(request: Request, nombre: str, accion: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        if not hasattr(listado, "accion"):
            raise HTTPException(404, "Acción desconocida")
        items = list((await request.form()).multi_items()) if request.method == "POST" else None
        try:
            plantilla, datos = listado.accion(ctx, accion, items)
        except ErrorContable as e:
            raise HTTPException(404, str(e)) from None
        if plantilla is None:  # la acción terminó bien: se cierra el diálogo y se refresca el listado
            respuesta = HTMLResponse("")
            respuesta.headers["HX-Trigger"] = json.dumps(mensaje("ok", datos.get("mensaje", "Hecho"), refrescar=True, cerrarModal=True))
            return respuesta
        return render(request, plantilla, ctx=ctx, listado=listado, **datos)

    @app.api_route("/e/{slug}/{anio}/{nombre}/importar", methods=["GET", "POST"], response_class=HTMLResponse)
    async def importar_excel(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        """Importación de facturas desde el Excel de conciliación: formulario → vista previa → importación."""
        listado = listado_de(nombre, request)
        if not getattr(listado, "importa_excel", False):
            raise HTTPException(404, "Este listado no importa Excel")
        pendientes = request.app.state.importaciones
        if request.method == "GET":
            return render(request, "_importar.html", ctx=ctx, listado=listado, errores=[])
        formulario_http = await request.form()
        try:
            if formulario_http.get("paso") == "confirmar":
                token = str(formulario_http.get("token", ""))
                guardado = pendientes.pop(token, None)
                if guardado is None or guardado[0] != (ctx.slug, ctx.ejercicio.anio, listado.nombre):
                    raise ErrorContable("La vista previa ha caducado: vuelva a elegir el fichero")
                try:
                    datos = listado.importar_confirmar(ctx, guardado[1], {k: str(v) for k, v in formulario_http.items()}, guardado[2])
                    ctx.sesion.commit()
                except Exception:
                    ctx.sesion.rollback()
                    raise
                respuesta = render(request, "_importar_resultado.html", ctx=ctx, listado=listado, **datos)
                respuesta.headers["HX-Trigger"] = json.dumps(mensaje("ok", f"{len(datos['resultado'].importadas)} facturas importadas", refrescar=True))
                return respuesta
            fichero = formulario_http.get("fichero")
            if fichero is None or not getattr(fichero, "filename", ""):
                raise ErrorContable("Elija el fichero Excel (.xlsx)")
            contenido = await fichero.read()
            if len(contenido) > 10 * 1024 * 1024:
                raise ErrorContable("El Excel pesa más de 10 MB")
            datos = listado.importar_vista(ctx, fichero.filename, contenido)
        except ErrorContable as e:
            ctx.sesion.rollback()
            return render(request, "_importar.html", ctx=ctx, listado=listado, errores=[str(e)])
        token = secrets.token_urlsafe(16)
        while len(pendientes) >= 8:  # sólo se guardan las últimas vistas previas
            pendientes.pop(next(iter(pendientes)))
        pendientes[token] = ((ctx.slug, ctx.ejercicio.anio, listado.nombre), contenido, fichero.filename)
        return render(request, "_importar_vista.html", ctx=ctx, listado=listado, token=token, **datos)

    @app.get("/e/{slug}/{anio}/adjuntos/{adjunto_id}")
    def ver_adjunto(adjunto_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        adjunto = ctx.sesion.get(Adjunto, adjunto_id)
        pertenece = adjunto is not None and (
            (adjunto.factura_id and ctx.sesion.scalar(select(Factura.id).where(Factura.id == adjunto.factura_id, Factura.ejercicio_id == ctx.ejercicio.id)))
            or (adjunto.movimiento_banco_id and ctx.sesion.scalar(select(MovimientoBanco.id).where(MovimientoBanco.id == adjunto.movimiento_banco_id, MovimientoBanco.ejercicio_id == ctx.ejercicio.id)))
            or (adjunto.asiento_id and ctx.sesion.scalar(select(Asiento.id).where(Asiento.id == adjunto.asiento_id, Asiento.ejercicio_id == ctx.ejercicio.id)))
        )
        if not pertenece:
            raise HTTPException(404, "No existe ese justificante")
        try:
            ruta = ctx.config.almacen_de_adjuntos().ruta(adjunto)
        except ErrorContable:
            raise HTTPException(404, "Ruta no válida") from None
        if not ruta.is_file():
            raise HTTPException(404, "El fichero del justificante no está en el almacén")
        nombre = adjunto.nombre.replace('"', "")
        return FileResponse(ruta, media_type=adjunto.tipo_mime, headers={"Content-Disposition": f'inline; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})

    @app.get("/e/{slug}/{anio}/conciliacion/pdf/{factura_id}")
    def ver_pdf_de_la_lista(factura_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        """El PDF de una factura de la lista de trabajo, desde la ruta que trae el Excel de Verifactu. Sólo se abre el de una factura de esta empresa y sólo si es un PDF o una imagen."""
        f = ctx.sesion.get(FacturaTrimestre, factura_id)
        if f is None or f.empresa_id != ctx.empresa.id or not f.ruta_pdf:
            raise HTTPException(404, "Esa factura no tiene PDF")
        ruta = Path(f.ruta_pdf)
        tipos = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        if ruta.suffix.lower() not in tipos or not ruta.is_file():
            raise HTTPException(404, "No se encuentra el PDF en esa ruta del disco: " + ruta.name)
        return FileResponse(ruta, media_type=tipos[ruta.suffix.lower()], headers={"Content-Disposition": f'inline; filename="{ruta.name.replace(chr(34), "")}"', "X-Content-Type-Options": "nosniff"})

    @app.get("/e/{slug}/{anio}/declaraciones/{declaracion_id}/pdf")
    def ver_declaracion(declaracion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        d = ctx.sesion.get(DeclaracionPresentada, declaracion_id)
        if d is None or d.empresa_id != ctx.empresa.id or not d.pdf_ruta:
            raise HTTPException(404, "No hay PDF de esa declaración")
        ruta = (ctx.config.almacen_de_adjuntos().raiz / d.pdf_ruta).resolve()
        if ctx.config.almacen_de_adjuntos().raiz.resolve() not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El PDF de la declaración no está en el almacén")
        nombre = (d.pdf_nombre or "declaracion.pdf").replace('"', "")
        return FileResponse(ruta, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})

    @app.get("/e/{slug}/{anio}/modelo-303/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-111/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-115/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-190/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-180/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-390/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-202/{presentacion_id}/fichero")
    @app.get("/e/{slug}/{anio}/modelo-347/{presentacion_id}/fichero")
    def descargar_fichero_aeat(presentacion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        p = ctx.sesion.get(PresentacionAeat, presentacion_id)
        if p is None or p.empresa_id != ctx.empresa.id or not p.fichero_ruta:
            raise HTTPException(404, "No hay fichero de esa presentación")
        raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
        ruta = (raiz / p.fichero_ruta).resolve()
        if raiz not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El fichero no está en el almacén")
        nombre = (p.fichero_nombre or "modelo303.303").replace('"', "")
        return FileResponse(ruta, media_type="text/plain; charset=iso-8859-1", headers={"Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})

    @app.post("/e/{slug}/{anio}/modelo-303/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-111/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-115/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-190/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-180/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-390/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-202/{presentacion_id}/carpeta")
    @app.post("/e/{slug}/{anio}/modelo-347/{presentacion_id}/carpeta")
    def abrir_carpeta_del_fichero(presentacion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        """Abre en el explorador de archivos la carpeta del fichero generado (sólo desde el propio equipo)."""
        p = ctx.sesion.get(PresentacionAeat, presentacion_id)
        if p is None or p.empresa_id != ctx.empresa.id or not p.fichero_ruta:
            raise HTTPException(404, "No hay fichero de esa presentación")
        if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(403, "Sólo se puede abrir la carpeta desde el equipo donde está el programa")
        raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
        ruta = (raiz / p.fichero_ruta).resolve()
        if raiz not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El fichero no está en el almacén")
        from conta_pridalac.servicios.exportar import abrir_en_el_explorador

        try:
            abrir_en_el_explorador(ruta)
        except ErrorContable as e:
            raise HTTPException(500, str(e)) from None
        respuesta = HTMLResponse("")
        respuesta.headers["HX-Trigger"] = json.dumps({"mensaje": {"tipo": "ok", "texto": f"Carpeta abierta: {ruta.parent}"}})
        return respuesta

    @app.get("/e/{slug}/{anio}/copias/{nombre}/descargar")
    def descargar_copia(nombre: str, request: Request, ctx: Contexto = Depends(contexto)):
        from conta_pridalac.servicios.copias import listar_copias

        copia = next((c for c in listar_copias(ctx.config.copias, ctx.slug) if c.nombre == nombre), None)  # sólo las copias de esta empresa, por su nombre exacto
        if copia is None:
            raise HTTPException(404, "No existe esa copia")
        return FileResponse(copia.ruta, media_type="application/zip", filename=copia.nombre, headers={"X-Content-Type-Options": "nosniff"})

    def _presentacion_con_fichero(ctx: Contexto, presentacion_id: int) -> PresentacionAeat:
        p = ctx.sesion.get(PresentacionAeat, presentacion_id)
        if p is None or p.empresa_id != ctx.empresa.id or not p.fichero_ruta:
            raise HTTPException(404, "No hay fichero de esa presentación")
        return p

    @app.post("/e/{slug}/{anio}/modelo-303/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-111/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-115/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-190/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-180/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-390/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-202/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-347/{presentacion_id}/copiar")
    @app.post("/e/{slug}/{anio}/modelo-200/{presentacion_id}/copiar")
    def copiar_fichero_para_presentar(presentacion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        """Copia el fichero generado a la carpeta de ficheros para presentar, con un nombre claro."""
        from conta_pridalac.servicios.exportar import exportar_presentacion

        p = _presentacion_con_fichero(ctx, presentacion_id)
        try:
            ruta, nueva = exportar_presentacion(p, ctx.empresa, ctx.config.almacen, ctx.config.descargas)
        except ErrorContable as e:
            respuesta = HTMLResponse("")
            respuesta.headers["HX-Trigger"] = json.dumps({"mensaje": {"tipo": "error", "texto": str(e)}})
            return respuesta
        respuesta = HTMLResponse("")
        respuesta.headers["HX-Trigger"] = json.dumps({"mensaje": {"tipo": "ok", "texto": ("Copiado a " if nueva else "Ya estaba copiado en ") + str(ruta)}})
        return respuesta

    @app.post("/e/{slug}/{anio}/modelo-303/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-111/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-115/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-190/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-180/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-390/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-202/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-347/{presentacion_id}/carpeta-copia")
    @app.post("/e/{slug}/{anio}/modelo-200/{presentacion_id}/carpeta-copia")
    def abrir_carpeta_de_copia(presentacion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        """Abre la carpeta de ficheros para presentar, con la copia de esta presentación seleccionada (sólo desde el propio equipo)."""
        from conta_pridalac.servicios.exportar import abrir_en_el_explorador, nombre_para_presentar

        p = _presentacion_con_fichero(ctx, presentacion_id)
        if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(403, "Sólo se puede abrir la carpeta desde el equipo donde está el programa")
        nombre = nombre_para_presentar(ctx.empresa, p.modelo, p.anio, p.periodo, p.tipo_presentacion, Path(p.fichero_nombre or "x.303").suffix)
        ruta = ctx.config.descargas / nombre
        if not ruta.is_file():
            raise HTTPException(404, "Todavía no se ha copiado: use «Copiar para presentar»")
        try:
            abrir_en_el_explorador(ruta)
        except ErrorContable as e:
            raise HTTPException(500, str(e)) from None
        return HTMLResponse("")

    @app.get("/e/{slug}/{anio}/modelo-303/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-111/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-115/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-190/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-180/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-390/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-202/{presentacion_id}/justificante")
    @app.get("/e/{slug}/{anio}/modelo-347/{presentacion_id}/justificante")
    def ver_justificante_aeat(presentacion_id: int, request: Request, ctx: Contexto = Depends(contexto)):
        p = ctx.sesion.get(PresentacionAeat, presentacion_id)
        if p is None or p.empresa_id != ctx.empresa.id or not p.respuesta_ruta:
            raise HTTPException(404, "No hay justificante de esa presentación")
        raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
        ruta = (raiz / p.respuesta_ruta).resolve()
        if raiz not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El justificante no está en el almacén")
        return FileResponse(ruta, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="justificante_{p.justificante}.pdf"', "X-Content-Type-Options": "nosniff"})

    @app.get("/e/{slug}/{anio}/legalizacion-libros/{legalizacion_id}/libro/{clave}")
    def ver_libro_legalizado(legalizacion_id: int, clave: str, request: Request, ctx: Contexto = Depends(contexto)):
        from conta_pridalac.db.modelos import Legalizacion

        leg = ctx.sesion.get(Legalizacion, legalizacion_id)
        if clave == "acuse" and leg is not None and leg.empresa_id == ctx.empresa.id and leg.acuse_ruta:
            raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
            ruta = (raiz / leg.acuse_ruta).resolve()
            if raiz not in ruta.parents or not ruta.is_file():
                raise HTTPException(404, "El acuse no está en el almacén")
            return FileResponse(ruta, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{ruta.name}"', "X-Content-Type-Options": "nosniff"})
        if clave == "zip" and leg is not None and leg.empresa_id == ctx.empresa.id and leg.zip_ruta:
            raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
            ruta = (raiz / leg.zip_ruta).resolve()
            if raiz not in ruta.parents or not ruta.is_file():
                raise HTTPException(404, "El ZIP no está en el almacén")
            return FileResponse(ruta, media_type="application/zip", filename=leg.zip_nombre, headers={"X-Content-Type-Options": "nosniff"})
        libro = next((l for l in leg.libros if l.clave == clave), None) if leg is not None and leg.empresa_id == ctx.empresa.id else None
        if libro is None or not libro.fichero_ruta:
            raise HTTPException(404, "Ese libro no está generado")
        raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
        ruta = (raiz / libro.fichero_ruta).resolve()
        if raiz not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El PDF no está en el almacén")
        return FileResponse(ruta, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{libro.fichero_nombre}"', "X-Content-Type-Options": "nosniff"})

    @app.get("/e/{slug}/{anio}/deposito-cuentas/{deposito_id}/doc/{clave}")
    def ver_documento_del_deposito(deposito_id: int, clave: str, request: Request, ctx: Contexto = Depends(contexto)):
        from conta_pridalac.db.modelos import DepositoCuentas

        dep = ctx.sesion.get(DepositoCuentas, deposito_id)
        if dep is None or dep.empresa_id != ctx.empresa.id:
            raise HTTPException(404, "Ese depósito no existe")
        raiz = ctx.config.almacen_de_adjuntos().raiz.resolve()
        if clave == "acuse" and dep.acuse_ruta:
            ruta, tipo = (raiz / dep.acuse_ruta).resolve(), "application/pdf"
        elif clave == "xml" and dep.carpeta_ruta:
            ruta, tipo = (raiz / dep.carpeta_ruta / "DEPOSITO.xml").resolve(), "application/xml"
        elif clave == "memoria" and dep.carpeta_ruta:
            ruta, tipo = (raiz / dep.carpeta_ruta / "MEMORIA.pdf").resolve(), "application/pdf"
        elif clave == "xbrl" and dep.carpeta_ruta:
            ruta, tipo = (raiz / dep.carpeta_ruta / "DEPOSITO.xbrl").resolve(), "application/xml"
        elif clave == "cac" and dep.carpeta_ruta and dep.huella_d2:
            from conta_pridalac.servicios.deposito_cuentas import nombre_de_la_certificacion

            ruta, tipo = (raiz / dep.carpeta_ruta / nombre_de_la_certificacion(ctx.empresa, dep.anio)).resolve(), "application/pdf"
        elif clave == "zip" and dep.carpeta_ruta and dep.zip_nombre:
            ruta, tipo = (raiz / dep.carpeta_ruta / dep.zip_nombre).resolve(), "application/zip"
        else:
            raise HTTPException(404, "Ese documento no está generado")
        if raiz not in ruta.parents or not ruta.is_file():
            raise HTTPException(404, "El documento no está en el almacén")
        return FileResponse(ruta, media_type=tipo, headers={"Content-Disposition": f'{"inline" if tipo == "application/pdf" else "attachment"}; filename="{ruta.name}"', "X-Content-Type-Options": "nosniff"})

    @app.post("/e/{slug}/{anio}/{nombre}/borrar", response_class=HTMLResponse)
    async def borrar(request: Request, nombre: str, ctx: Contexto = Depends(contexto)):
        listado = listado_de(nombre, request)
        if not listado.borrar:
            raise HTTPException(405, "Este listado no admite borrados")
        ids = [v for k, v in (await request.form()).multi_items() if k == "ids"]
        respuesta = HTMLResponse("")
        if not ids:
            respuesta.headers["HX-Trigger"] = json.dumps(mensaje("aviso", "No hay filas seleccionadas"))
            return respuesta
        try:
            listado.eliminar(ctx, ids)
            ctx.sesion.commit()
            disparador = mensaje("ok", f"Borrado{'s' if len(ids) > 1 else ''} {len(ids)} registro{'s' if len(ids) > 1 else ''}", refrescar=True)
        except (ErrorContable, ValueError, IntegrityError) as e:
            ctx.sesion.rollback()
            disparador = mensaje("error", str(e.orig) if isinstance(e, IntegrityError) else str(e), refrescar=True)
        respuesta.headers["HX-Trigger"] = json.dumps(disparador)
        return respuesta

    return app


def crear_app_por_defecto() -> FastAPI:
    return crear_app()
