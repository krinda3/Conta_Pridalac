"""Pantallas de toda la instalación, no de una empresa: **Programa** (versión, buscar actualizaciones y actualizar) y **Normativa y diseños** (de qué normas depende Conta y si han cambiado).

Cuelgan de la pantalla de empresas (`/programa`, `/normativa`). Son páginas sencillas: cada acción es un formulario que se envía y vuelve a la página con su mensaje (`?m=`), sin diálogos.
Los datos son comunes a todas las empresas (`_normativa.json` y `_programa.json` en la carpeta de datos). La auditoría de cada empresa sigue avisando de la normativa pendiente.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from urllib.parse import quote, urlparse

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import actualizar_programa as ap
from conta_pridalac.servicios import copias as svc_copias
from conta_pridalac.servicios import normativa as nv
from conta_pridalac.web.config import Configuracion

ESTADOS = {"cambio": "¡Cambio en la sede!", "revisar": "Por revisar", "al_dia": "Al día"}
LOCALES = ("127.0.0.1", "localhost", "::1", "testserver")


def situacion(e: nv.Estado) -> str:
    return "cambio" if e.cambio_detectado else ("revisar" if e.por_revisar else "al_dia")


def consulta(e: nv.Estado) -> str:
    """Lo último que se supo de la sede y del BOE para esta fuente, en una línea."""
    s = e.sondeo
    if not (e.fuente.url or e.fuente.siguiente or e.fuente.boe):
        return "—"
    if not s:
        return "sin consultar"
    fecha = date.fromisoformat(s["fecha"]).strftime("%d/%m/%Y") if s.get("fecha") else ""
    if s.get("error"):
        return f"{fecha} · BOE a medias: vuelva a consultar" if "vuelva a consultar" in s["error"] else f"{fecha} · sin respuesta"
    partes = []
    if e.fuente.url or e.fuente.siguiente:
        partes.append("diseño cambiado" if s.get("cambiado") else "ya hay diseño nuevo" if s.get("siguiente_existe") else "sin cambios")
    if e.fuente.boe:
        n = len(e.novedades_boe)
        partes.append(f"BOE: {n} novedad(es)" if n else "BOE: sin novedades")
    return f"{fecha} · " + " · ".join(partes)


def resumen_para_inicio(config: Configuracion) -> dict:
    """Lo que enseñan las tarjetas de la pantalla de empresas. No llama a internet: sólo lo ya sabido. Si algo falla, la pantalla de inicio no se cae."""
    r = {"version": "", "programa": "", "programa_aviso": False, "normativa": "", "normativa_aviso": False}
    try:
        motivo = ap.disponible()
        r["version"] = str(ap.version())
        ultima = ap.ultima_comprobacion(config.datos)
        if motivo:
            r["programa"] = "no se puede actualizar desde aquí"
        elif not ultima:
            r["programa"] = "sin comprobar todavía"
        elif ultima["pendientes"] > 0:
            r["programa"], r["programa_aviso"] = f"hay {ultima['pendientes']} cambio(s) nuevo(s)", True
        elif ultima["pendientes"] == 0:
            r["programa"] = "al día"
        else:
            r["programa"] = "no se pudo comprobar la última vez"
    except Exception:  # noqa: BLE001 - un fallo de git no debe tumbar la pantalla de inicio
        pass
    try:
        pendientes = [e for e in nv.estados(config) if situacion(e) != "al_dia"]
        r["normativa"] = f"{len(pendientes)} fuente(s) por revisar" if pendientes else "todo al día"
        r["normativa_aviso"] = bool(pendientes)
    except Exception:  # noqa: BLE001
        pass
    return r


def _copia_previa(config: Configuracion):
    """Lo que se hace justo antes de actualizar: una copia ligera de cada empresa. Si alguna falla, no se actualiza."""
    def copiar() -> list[str]:
        hechas = []
        for slug in config.empresas():
            ruta = config.datos / f"{slug}.sqlite"
            if ruta.is_file():
                svc_copias.hacer_copia(slug, ruta, config.almacen, config.copias, etiqueta="antes_de_actualizar")
                hechas.append(slug)
        return [f"Copia de seguridad ligera hecha de: {', '.join(hechas)}."] if hechas else []
    return copiar


def _mismo_origen(request: Request) -> None:
    """Estas acciones cambian cosas (descargar una versión nueva): sólo valen si las envía una página de este mismo programa, no otra web abierta en el navegador."""
    origen = request.headers.get("origin")
    if origen and urlparse(origen).hostname not in LOCALES:
        raise HTTPException(403, "No permitido")


def _volver(ruta: str, texto: str, error: bool = False) -> RedirectResponse:
    return RedirectResponse(f"{ruta}?m={quote(texto)}&t={'error' if error else 'ok'}", status_code=303)


def registrar(app, render) -> None:
    """Añade `/programa` y `/normativa`. Hay que llamarla antes de las rutas genéricas de la aplicación."""

    def config_de(request: Request) -> Configuracion:
        return request.app.state.config

    # ------------------------------------------------------------------ programa
    def pagina_programa(request: Request, m: str = "", t: str = "ok", resultado=None):
        config = config_de(request)
        motivo = ap.disponible()
        ultima = ap.ultima_comprobacion(config.datos)
        cuando = datetime.fromisoformat(ultima["fecha"]).strftime("%d/%m/%Y %H:%M") if ultima else ""
        return render(request, "programa.html", ctx=None, listado=SimpleNamespace(nombre="programa"), version=ap.version(), origen="" if motivo else ap.origen(), motivo=motivo, ultima=ultima, cuando=cuando,
                      empresas=[s for s in config.empresas() if (config.datos / f"{s}.sqlite").is_file()], mensaje=m, tipo=t, resultado=resultado)

    @app.get("/programa", response_class=HTMLResponse)
    def programa(request: Request, m: str = "", t: str = "ok"):
        return pagina_programa(request, m, t)

    @app.post("/programa/comprobar")
    def programa_comprobar(request: Request):
        _mismo_origen(request)
        c = ap.comprobar()
        ap.guardar_comprobacion(config_de(request).datos, c)
        return _volver("/programa", c.mensaje + (" Pulse «Actualizar ahora» para descargarlos." if c.pendientes > 0 else ""), c.pendientes < 0)

    @app.post("/programa/actualizar", response_class=HTMLResponse)
    def programa_actualizar(request: Request):
        _mismo_origen(request)
        config = config_de(request)
        r = ap.actualizar(antes=_copia_previa(config))
        ap.guardar_comprobacion(config.datos, ap.comprobar())
        return pagina_programa(request, resultado=r)

    # ------------------------------------------------------------------ normativa
    def estado(request: Request, clave: str) -> nv.Estado:
        e = next((x for x in nv.estados(config_de(request)) if x.fuente.clave == clave), None)
        if e is None:
            raise HTTPException(404, "Fuente desconocida")
        return e

    @app.get("/normativa", response_class=HTMLResponse)
    def normativa(request: Request, m: str = "", t: str = "ok"):
        filas = [dict(e=e, situacion=situacion(e), estado=ESTADOS[situacion(e)], consulta=consulta(e)) for e in nv.estados(config_de(request))]
        return render(request, "normativa.html", ctx=None, listado=SimpleNamespace(nombre="normativa"), filas=filas, mensaje=m, tipo=t)

    @app.post("/normativa/consultar")
    def normativa_consultar(request: Request):
        _mismo_origen(request)
        config = config_de(request)
        resultados = nv.sondear_todo(config)
        if resultados and all(v["error"] and "vuelva a consultar" not in v["error"] for v in resultados.values()):
            return _volver("/normativa", "No se ha podido consultar (¿sin conexión?): " + next(iter(resultados.values()))["error"], True)
        cambios = [k for k, v in resultados.items() if v.get("cambiado") or v.get("siguiente_existe")]
        cambios += [e.fuente.clave for e in nv.estados(config) if e.fuente.clave in resultados and e.novedades_boe and e.fuente.clave not in cambios]
        a_medias = any(v["error"] and "vuelva a consultar" in v["error"] for v in resultados.values())
        texto = f"Consulta hecha: {len(resultados)} fuente(s) comprobadas; " + (f"CAMBIOS en {', '.join(cambios)}." if cambios else "sin cambios ni novedades.")
        return _volver("/normativa", texto + (" El BOE se ha mirado solo en parte: pulse otra vez para seguir." if a_medias else ""))

    @app.get("/normativa/{clave}", response_class=HTMLResponse)
    def normativa_ficha(request: Request, clave: str, m: str = "", t: str = "ok"):
        e = estado(request, clave)
        return render(request, "normativa_ficha.html", ctx=None, listado=SimpleNamespace(nombre="normativa"), e=e, f=e.fuente, situacion=situacion(e), estado_texto=ESTADOS[situacion(e)], consulta=consulta(e),
                      direccion=(nv.BASE_DISENOS + e.fuente.url) if e.fuente.url else "", mensaje=m, tipo=t)

    @app.post("/normativa/{clave}/consultar")
    def normativa_ficha_consultar(request: Request, clave: str):
        _mismo_origen(request)
        e = estado(request, clave)
        r = nv.sondear(e.fuente, previo=e.sondeo)
        nv.guardar_sondeo(config_de(request), clave, r)
        if r["error"]:
            return _volver(f"/normativa/{clave}", "No se ha podido consultar: " + r["error"], True)
        return _volver(f"/normativa/{clave}", "Consulta hecha: " + consulta(estado(request, clave)).split(" · ", 1)[-1])

    @app.post("/normativa/{clave}/revisada")
    def normativa_ficha_revisada(request: Request, clave: str):
        _mismo_origen(request)
        estado(request, clave)
        try:
            dia = nv.marcar_revisada(config_de(request), clave)
        except (ValueError, ErrorContable) as ex:
            return _volver(f"/normativa/{clave}", str(ex), True)
        return _volver(f"/normativa/{clave}", f"Marcada como revisada el {dia:%d/%m/%Y}: no vuelve a avisar hasta la próxima ventana ({estado(request, clave).proxima:%d/%m/%Y})")
