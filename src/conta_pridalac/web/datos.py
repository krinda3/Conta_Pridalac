"""Carpeta de datos y candado en la web: `/datos` (dónde están los datos, usar otra carpeta, mover los datos) y `/bloqueado` (los datos los tiene abiertos otro equipo).

Lógica en `servicios/ubicacion_datos.py` y `servicios/candado.py`; aquí sólo el cableado:

- **Candado** (`config.usar_candado`): se toma al arrancar, se renueva su señal cada pocos segundos y se suelta al cerrar. Si lo tiene otro equipo, o alguien lo fuerza mientras tanto, el programa se bloquea:
  todas las pantallas llevan a `/bloqueado`, donde se puede reintentar, forzar (escribiendo FORZAR) o elegir otra carpeta de datos.
- **Mover los datos** corre en segundo plano (puede tardar minutos con muchos justificantes) y, mientras dura, el programa sólo deja ver `/datos`, para que nadie escriba en lo que se está copiando.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import candado as cd
from conta_pridalac.servicios import ubicacion_datos as ub
from conta_pridalac.web.sistema import _mismo_origen, _volver

PERMITIDAS = ("/bloqueado", "/datos", "/static", "/tema.css", "/favicon.ico", "/_latido", "/_apagar", "/_preferencias", "/ayuda")  # lo que se puede ver estando bloqueado o moviendo datos
CODIGO_CARPETA = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "print(filedialog.askdirectory(title='Carpeta de datos de Conta', mustexist=False))\n"
)


def elegir_carpeta() -> str:
    """Abre el cuadro de «Elegir carpeta» del sistema (el programa corre en este mismo equipo) y devuelve la ruta, o vacío si se cancela."""
    try:
        r = subprocess.run([sys.executable, "-I", "-c", CODIGO_CARPETA], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as ex:
        raise ErrorContable(f"No se pudo abrir el selector de carpetas: {ex}") from ex
    if r.returncode != 0:
        raise ErrorContable("No se pudo abrir el selector de carpetas; escriba la ruta a mano")
    return r.stdout.strip()


# ------------------------------------------------------------------------------------------------ el candado en el estado de la aplicación

def iniciar_candado(app) -> None:
    """Toma el candado de la carpeta de datos actual. Si lo tiene otro equipo, deja el programa bloqueado (`app.state.bloqueo`)."""
    config = app.state.config
    app.state.candado, app.state.bloqueo, app.state.bloqueo_perdido = None, None, False
    if not config.usar_candado:
        return
    raiz = config.raiz
    # una carpeta que no existe, o una elegida a mano que está vacía y sin marca (¿unidad desconectada?), no se toca: tomar el candado la crearía
    if not raiz.is_dir() or ub.pide_guia(raiz, ub.resolver()[1]):
        return
    c = cd.Candado(raiz)
    conseguido, quien = c.adquirir()
    app.state.candado = c
    app.state.bloqueo = None if conseguido else quien


def latir(app) -> None:
    """Un latido: renueva la señal del candado y se entera de si alguien lo forzó. Lo llama el hilo de fondo cada `SENAL_CADA`."""
    c = getattr(app.state, "candado", None)
    if c is None:
        if app.state.config.usar_candado and getattr(app.state, "bloqueo", None) is None:
            iniciar_candado(app)  # la carpeta de datos puede haber aparecido (se montó la unidad, se eligió una)
        return
    if app.state.bloqueo is not None:
        return  # bloqueado: no se toma solo; lo decide una persona en /bloqueado
    if not c.renovar():
        estado, titular = c.estado()
        if estado == cd.LIBRE:
            c.adquirir()  # el fichero desapareció (p. ej. lo borró la sincronización): se vuelve a poner
        else:
            app.state.bloqueo, app.state.bloqueo_perdido = titular, True  # lo forzó otro equipo: este programa deja de escribir


def soltar(app) -> None:
    c = getattr(app.state, "candado", None)
    if c is not None:
        c.liberar()


def cambiar_a(app, raiz) -> None:
    """Pasa a usar otra carpeta de datos: toma su candado, suelta el de la anterior, guarda la ubicación y cambia la configuración sin reiniciar. Lanza `ErrorContable` si no se puede."""
    config = app.state.config
    if ub.resolver()[1] == "variable":
        raise ErrorContable("La carpeta de datos la fija la variable de entorno CONTA_DATOS: para cambiarla desde aquí, quítela y vuelva a arrancar el programa")
    nuevo = None
    if config.usar_candado:
        nuevo = cd.Candado(raiz)
        conseguido, quien = nuevo.adquirir()
        if not conseguido:
            raise ErrorContable(f"Esa carpeta de datos la tiene abierta otro equipo: {quien.describir(datetime.now())}. Ciérrelo allí y espere a que termine la sincronización, o fuércelo si quedó pillado")
    soltar(app)
    ub.marcar(raiz)
    ub.guardar_ubicacion(raiz)
    config.cambiar_raiz(raiz)
    app.state.candado, app.state.bloqueo, app.state.bloqueo_perdido = nuevo, None, False


def resumen_para_inicio(config, origen: str | None = None) -> dict:
    """Lo que enseña la pantalla de empresas sobre la carpeta de datos. No lanza nunca."""
    origen = origen or ub.resolver()[1]
    try:
        i = ub.inspeccionar(config.raiz)
        return {"raiz": str(config.raiz), "origen": origen, "existe": i.existe, "problema": i.problema, "guiado": ub.pide_guia(config.raiz, origen)}
    except Exception:  # noqa: BLE001 - la pantalla de inicio no se cae por esto
        return {"raiz": str(config.raiz), "origen": origen, "existe": False, "problema": "", "guiado": False}


# ------------------------------------------------------------------------------------------------ rutas

def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:,.1f} MB".replace(",", "X").replace(".", ",").replace("X", ".")


def registrar(app, render) -> None:
    """Añade `/datos`, `/bloqueado` y el guardián que lleva ahí a quien no puede trabajar. Arranca el candado (si la configuración lo pide) y su hilo de latidos."""
    app.state.traslado = None
    iniciar_candado(app)
    if app.state.config.usar_candado and os.environ.get("CONTA_SIN_HILO") != "1":  # (las pruebas lo apagan y llaman a `latir` a mano)
        def bucle():
            while True:
                time.sleep(cd.SENAL_CADA.total_seconds())
                try:
                    latir(app)
                except Exception:  # noqa: BLE001 - un fallo puntual (carpeta en red que no responde) no mata el hilo
                    pass
        threading.Thread(target=bucle, daemon=True, name="candado").start()

    def moviendo() -> bool:
        t = app.state.traslado
        return t is not None and t["estado"] == "copiando"

    @app.middleware("http")
    async def guardian(request: Request, call_next):
        ruta = request.url.path
        if (app.state.bloqueo is not None or moviendo()) and not ruta.startswith(PERMITIDAS):
            destino = "/datos" if moviendo() else "/bloqueado"
            if request.headers.get("HX-Request"):
                return Response(status_code=401, headers={"HX-Redirect": destino})
            return RedirectResponse(destino, status_code=303)
        return await call_next(request)

    # ------------------------------------------------------------------ bloqueo
    @app.get("/bloqueado", response_class=HTMLResponse)
    def bloqueado(request: Request, m: str = "", t: str = "ok"):
        titular = app.state.bloqueo
        if titular is None:
            return RedirectResponse("/", status_code=303)
        c = app.state.candado
        ahora = datetime.now()
        return render(request, "bloqueado.html", ctx=None, listado=SimpleNamespace(nombre="datos"), titular=titular, quien=titular.describir(ahora), perdido=app.state.bloqueo_perdido,
                      reciente=c.en_uso_reciente(titular), pillado=c.posiblemente_pillado(titular), raiz=str(app.state.config.raiz), mensaje=m, tipo=t)

    @app.post("/bloqueado/reintentar")
    def reintentar(request: Request):
        _mismo_origen(request)
        c = app.state.candado
        if c is None:
            return RedirectResponse("/", status_code=303)
        conseguido, quien = c.adquirir()
        if conseguido:
            app.state.bloqueo, app.state.bloqueo_perdido = None, False
            return RedirectResponse("/", status_code=303)
        app.state.bloqueo = quien
        return _volver("/bloqueado", f"Sigue en uso: {quien.describir(datetime.now())}", True)

    @app.post("/bloqueado/forzar")
    def forzar(request: Request, confirmacion: str = Form("")):
        _mismo_origen(request)
        c = app.state.candado
        if c is None:
            return RedirectResponse("/", status_code=303)
        if confirmacion.strip() != "FORZAR":
            return _volver("/bloqueado", "Para tomar el control escriba FORZAR (en mayúsculas)", True)
        c.forzar()
        app.state.bloqueo, app.state.bloqueo_perdido = None, False
        return RedirectResponse("/", status_code=303)

    # ------------------------------------------------------------------ carpeta de datos
    @app.get("/datos", response_class=HTMLResponse)
    def datos(request: Request, m: str = "", t: str = "ok"):
        config = app.state.config
        origen = ub.resolver()[1]
        i = ub.inspeccionar(config.raiz)
        c = app.state.candado
        estado_candado = ""
        if config.usar_candado:
            estado_candado = "tomado por este programa" if (c is not None and c.tengo()) else ("sin tomar (la carpeta no está lista)" if c is None else "lo tiene otro equipo")
        return render(request, "datos.html", ctx=None, listado=SimpleNamespace(nombre="datos"), raiz=str(config.raiz), origen=origen, fija=origen == "variable", i=i, mb=_mb, traslado=app.state.traslado,
                      candado=estado_candado, usa_candado=config.usar_candado, mensaje=m, tipo=t, por_defecto=str(ub.raiz_por_defecto()))

    @app.get("/datos/estado")
    def estado(request: Request):
        t = app.state.traslado
        return JSONResponse(t or {"estado": "ninguno"})

    @app.post("/datos/examinar")
    def examinar(request: Request):
        _mismo_origen(request)
        try:
            return JSONResponse({"ruta": elegir_carpeta()})
        except ErrorContable as ex:
            return JSONResponse({"error": str(ex)})

    @app.post("/datos/usar")
    def usar(request: Request, ruta: str = Form("")):
        _mismo_origen(request)
        if not ruta.strip():
            return _volver("/datos", "Indique la carpeta que ya tiene los datos", True)
        try:
            raiz = ub.normalizar_eleccion(ruta)
            i = ub.comprobar_destino_para_usar(raiz)
            cambiar_a(app, raiz)
        except ErrorContable as ex:
            return _volver("/datos", str(ex), True)
        return _volver("/", f"Ahora Conta usa la carpeta {raiz} ({len(i.empresas)} empresa(s))")

    @app.post("/datos/empezar")
    def empezar(request: Request):
        """Datos nuevos en la carpeta configurada: se marca como carpeta de Conta (y se toma su candado) para que se pueda crear la primera empresa."""
        _mismo_origen(request)
        config = app.state.config
        try:
            ub.marcar(config.raiz)
        except OSError as ex:
            return _volver("/datos", f"No se puede crear la carpeta de datos: {ex.strerror or ex}", True)
        iniciar_candado(app)
        return _volver("/", "Carpeta de datos lista: añada la primera empresa")

    @app.post("/datos/mover")
    def mover(request: Request, destino: str = Form("")):
        _mismo_origen(request)
        config = app.state.config
        if ub.resolver()[1] == "variable":
            return _volver("/datos", "La carpeta de datos la fija la variable de entorno CONTA_DATOS: para moverla desde aquí, quítela y vuelva a arrancar el programa", True)
        if moviendo():
            return _volver("/datos", "Ya se está moviendo una carpeta de datos", True)
        if not destino.strip():
            return _volver("/datos", "Indique la carpeta de destino", True)
        origen, destino_ruta = config.raiz, ub.normalizar_eleccion(destino)
        try:
            total = ub.comprobar_traslado(origen, destino_ruta).total
        except ErrorContable as ex:
            return _volver("/datos", str(ex), True)
        for motor in list(config.motores.values()):  # sin conexiones abiertas a lo que se va a copiar
            motor.dispose()
        config.motores.clear()
        trabajo = {"estado": "copiando", "mensaje": "Empezando", "hecho": 0, "total": total, "origen": str(origen), "destino": str(destino_ruta), "error": ""}
        app.state.traslado = trabajo

        def progreso(que: str, hecho: int, total_: int) -> None:
            trabajo.update(mensaje=que, hecho=hecho, total=total_ or total)

        def correr() -> None:
            try:
                informe = ub.trasladar(origen, destino_ruta, progreso)
                cambiar_a(app, destino_ruta)
                trabajo.update(estado="listo", mensaje=f"Hecho: {len(informe.bases)} empresa(s) y {informe.ficheros} fichero(s) copiados y verificados. La carpeta antigua queda intacta con una nota (MOVIDO_A.txt).")
            except BaseException as ex:  # noqa: BLE001 - el motivo se enseña en pantalla; lo copiado a medias ya lo borró `trasladar`
                trabajo.update(estado="error", error=str(ex) if isinstance(ex, ErrorContable) else f"Error inesperado: {ex}", mensaje="No se ha movido nada")

        threading.Thread(target=correr, daemon=True, name="traslado").start()
        return RedirectResponse("/datos", status_code=303)

    @app.post("/datos/mover/cerrar")
    def cerrar_aviso(request: Request):
        _mismo_origen(request)
        if not moviendo():
            app.state.traslado = None
        return RedirectResponse("/datos", status_code=303)
