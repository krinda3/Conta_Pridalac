"""Ficha de la empresa y acceso con la contraseña de su certificado digital.

La contraseña no se guarda: se comprueba abriendo el `.pfx` y se mantiene en memoria, por navegador (cookie de sesión) y empresa, hasta
que se cierra la empresa o se para el programa. Una empresa sin certificado asociado se abre sin contraseña.
"""
from __future__ import annotations

import secrets
import subprocess
import sys
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import object_session

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import parsear_fecha
from conta_pridalac.servicios import empresa as svc
from conta_pridalac.servicios import ficha_390
from conta_pridalac.web.comun import fecha_texto
from conta_pridalac.web.listados import Contexto

COOKIE = "conta_sesion"

# (sección, [(campo, título, columnas que ocupa)])
SECCIONES = [
    ("Datos generales", [("nombre", "Razón social *", 2), ("nif", "NIF", 1), ("nombre_corto", "Nombre corto (para los nombres de fichero)", 1), ("tipo_entidad", "Tipo de entidad", 1), ("fecha_constitucion", "Fecha de constitución", 1), ("actividad", "Actividad", 2), ("cnae", "CNAE", 1)]),
    ("Domicilio y contacto", [("domicilio", "Domicilio", 2), ("codigo_postal", "Código postal", 1), ("poblacion", "Población", 1), ("provincia", "Provincia", 1), ("pais", "País", 1),
                              ("telefono", "Teléfono", 1), ("email", "Correo electrónico", 1), ("web", "Página web", 1), ("iban", "IBAN", 2)]),
    ("Impuesto sobre Sociedades (modelo 202)", [("is_tipo_gravamen", "Tipo de gravamen del IS del ejercicio (25 si se deja vacío)", 1)]),
    ("Registro Mercantil: legalización de libros (Legalia2)", [
        ("municipio_ine", "Municipio de la empresa (código INE, 5 cifras: 28065)", 1), ("provincia_ine", "Provincia (código INE, 2 cifras: 28)", 1),
        ("presentador_nombre", "Quien presenta · nombre", 1), ("presentador_apellido1", "Primer apellido", 1), ("presentador_apellido2", "Segundo apellido", 1), ("presentador_nif", "NIF", 1),
        ("presentador_domicilio", "Domicilio", 2), ("presentador_poblacion", "Población", 1), ("presentador_cp", "Código postal", 1),
        ("presentador_telefono", "Teléfono", 1), ("presentador_email", "Correo electrónico", 2)]),
    ("Copias en OneDrive", [("carpeta_justificantes", "Carpeta donde copiar los PDF de los modelos presentados (con {año} donde va el año; vacía = no se copian)", 3),
                            ("carpeta_copias", "Carpeta donde llevar la copia de seguridad del final del trimestre (vacía = no se lleva)", 3)]),
    ("Representante", [("representante_nombre", "Nombre", 2), ("representante_nif", "NIF", 1), ("representante_cargo", "Cargo", 1)]),
    ("Registro Mercantil", [("registro_provincia", "Registro de", 1), ("registro_tomo", "Tomo", 1), ("registro_libro", "Libro", 1), ("registro_folio", "Folio", 1), ("registro_hoja", "Hoja", 1),
                            ("registro_inscripcion", "Inscripción", 1), ("forma_administracion", "Forma de administración", 2), ("codigo_irus", "Código IRUS", 1)]),
]


CODIGO_EXAMINAR = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
    "print(filedialog.askopenfilename(title='Certificado digital', filetypes=[('Certificados', '*.pfx *.p12'), ('Todos los ficheros', '*.*')]))\n"
)


def elegir_fichero() -> str:
    """Abre el cuadro de «Abrir fichero» del sistema (la aplicación corre en este mismo equipo) y devuelve la ruta elegida, o vacío si se cancela."""
    try:
        r = subprocess.run([sys.executable, "-I", "-c", CODIGO_EXAMINAR], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as ex:
        raise ErrorContable(f"No se pudo abrir el selector de ficheros: {ex}") from ex
    if r.returncode != 0:
        raise ErrorContable("No se pudo abrir el selector de ficheros; escriba la ruta a mano")
    return r.stdout.strip()


class EmpresaBloqueada(Exception):
    def __init__(self, slug: str):
        self.slug = slug


class EmpresaSinCertificado(Exception):
    """La empresa no tiene certificado digital configurado y la aplicación lo exige para trabajar con ella."""

    def __init__(self, slug: str):
        self.slug = slug


def _claves(request: Request) -> dict[str, dict[str, str]]:
    return request.app.state.__dict__.setdefault("claves", {})


def contrasena_de(request: Request, slug: str) -> str | None:
    """La contraseña con la que este navegador abrió la empresa (para firmar más adelante); None si no está abierta."""
    return _claves(request).get(request.cookies.get(COOKIE, ""), {}).get(slug)


def exigir_acceso(request: Request, slug: str, empresa: Empresa | None, *, ficha: bool = False) -> None:
    """Con certificado, hace falta su contraseña. Sin él, depende de la protección que se haya elegido: «ninguna» se abre sin más; «certificado» (aún sin configurar) o, en las empresas anteriores,
    la exigencia general de la aplicación, dejan sólo la ficha (`ficha=True`) hasta que se indique un certificado o se elija «Sin protección»."""
    if empresa is None:
        return
    if empresa.certificado_ruta:
        if contrasena_de(request, slug) is None:
            raise EmpresaBloqueada(slug)
    elif empresa.proteccion == "ninguna":
        return
    elif not ficha and (empresa.proteccion == "certificado" or request.app.state.config.exigir_certificado):
        raise EmpresaSinCertificado(slug)


def _recordar(request: Request, respuesta: Response, slug: str, contrasena: str) -> None:
    token = request.cookies.get(COOKIE) or secrets.token_urlsafe(24)
    _claves(request).setdefault(token, {})[slug] = contrasena
    respuesta.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")


def _volver(destino: str) -> str:
    return destino if destino.startswith(("/e/", "/empresa/")) and "//" not in destino else "/"


def _valores(empresa: Empresa) -> dict[str, str]:
    v = {c: getattr(empresa, c) or "" for _, campos in SECCIONES for c, _, _ in campos if c != "fecha_constitucion"}
    v["fecha_constitucion"] = fecha_texto(empresa.fecha_constitucion) if empresa.fecha_constitucion else ""
    return v


def crear_router(config_de, render) -> APIRouter:
    router = APIRouter()

    def abrir(request: Request, slug: str):
        try:
            sesion = config_de(request).sesion(slug)
        except KeyError:
            raise HTTPException(404, f"No existe la empresa «{slug}»") from None
        empresa = sesion.scalars(select(Empresa)).first()
        if empresa is None:
            sesion.close()
            raise HTTPException(404, f"La base «{slug}» no tiene empresa")
        return sesion, empresa

    @router.get("/empresa/{slug}/entrar", response_class=HTMLResponse)
    def entrar_pagina(request: Request, slug: str, volver: str = "/"):
        sesion, empresa = abrir(request, slug)
        try:
            return render(request, "entrar_empresa.html", ctx=None, slug=slug, empresa_nombre=empresa.nombre, volver=_volver(volver), error=None)
        finally:
            sesion.close()

    @router.post("/empresa/{slug}/entrar")
    def entrar(request: Request, slug: str, contrasena: str = Form(""), volver: str = Form("/")):
        sesion, empresa = abrir(request, slug)
        try:
            if empresa.certificado_ruta:
                try:
                    svc.leer_certificado(empresa.certificado_ruta, contrasena)
                except ErrorContable as ex:
                    return render(request, "entrar_empresa.html", ctx=None, slug=slug, empresa_nombre=empresa.nombre, volver=_volver(volver), error=str(ex))
            respuesta = RedirectResponse(_volver(volver), status_code=303)
            if empresa.certificado_ruta:
                _recordar(request, respuesta, slug, contrasena)
            return respuesta
        finally:
            sesion.close()

    @router.post("/empresa/{slug}/salir")
    def salir(request: Request, slug: str):
        _claves(request).get(request.cookies.get(COOKIE, ""), {}).pop(slug, None)
        return RedirectResponse("/", status_code=303)

    def pagina(request: Request, slug: str, empresa: Empresa, valores: dict, errores: list[str], mensaje: str | None = None, info=None, actividades=None, representantes=None):
        ejercicios = sorted(empresa.ejercicios, key=lambda e: e.anio, reverse=True)
        ctx = None
        if ejercicios:  # la barra superior (casita y ejercicio) se mantiene: se trabaja sobre el ejercicio abierto más reciente
            ejercicio = next((e for e in ejercicios if not e.cerrado), ejercicios[0])
            ctx = Contexto(object_session(empresa), empresa, ejercicio, slug, config_de(request))
        if actividades is None:
            actividades = [(a.descripcion, a.codigo or "", a.epigrafe or "") for a in empresa.actividades]
        if representantes is None:
            representantes = [(r.nombre, r.nif or "", fecha_texto(r.fecha_poder) if r.fecha_poder else "", r.notaria or "") for r in empresa.representantes]
        return render(request, "ficha_empresa.html", ctx=ctx, ejercicios=ejercicios, listado=None, slug=slug, empresa=empresa, secciones=SECCIONES, v=valores, errores=errores, mensaje=mensaje, info=info,
                      actividades=list(actividades) + [("", "", "")], representantes=list(representantes) + [("", "", "", "")],
                      abierta=contrasena_de(request, slug) is not None, protecciones=svc.PROTECCIONES, modelos_texto={k: v[0] for k, v in svc.MODELOS.items()}, modelos_marcados=svc.modelos_de(empresa),
                      proteccion=valores.get("proteccion") or empresa.proteccion or ("certificado" if empresa.certificado_ruta else "ninguna"))

    def info_certificado(request: Request, slug: str, empresa: Empresa):
        contrasena = contrasena_de(request, slug)
        if not empresa.certificado_ruta or contrasena is None:
            return None
        try:
            return svc.leer_certificado(empresa.certificado_ruta, contrasena)
        except ErrorContable:
            return None

    @router.post("/empresa/{slug}/examinar")
    def examinar(request: Request, slug: str):
        sesion, empresa = abrir(request, slug)
        try:
            exigir_acceso(request, slug, empresa, ficha=True)
        finally:
            sesion.close()
        try:
            return JSONResponse({"ruta": elegir_fichero()})
        except ErrorContable as ex:
            return JSONResponse({"error": str(ex)})

    @router.post("/empresa/{slug}/certificado")
    def leer_datos(request: Request, slug: str, ruta: str = Form(""), contrasena: str = Form("")):
        """Lee el certificado (sin asociarlo) y devuelve lo que la ficha puede rellenar con él."""
        sesion, empresa = abrir(request, slug)
        try:
            exigir_acceso(request, slug, empresa, ficha=True)
        finally:
            sesion.close()
        try:
            info = svc.leer_certificado(ruta.strip().strip('"'), contrasena)
        except ErrorContable as ex:
            return JSONResponse({"error": str(ex)})
        return JSONResponse({"titular": info.titular, "caduca": fecha_texto(info.caduca), "caducado": info.caducado, "nombre": info.razon_social, "nif": info.nif_empresa,
                             "representante_nombre": info.representante_nombre, "representante_nif": info.representante_nif})

    @router.get("/empresa/{slug}", response_class=HTMLResponse)
    def ficha(request: Request, slug: str, guardada: int = 0, sin_certificado: int = 0):
        sesion, empresa = abrir(request, slug)
        try:
            exigir_acceso(request, slug, empresa, ficha=True)
            avisos = ["Esta empresa no tiene configurada su protección de acceso. En «Protección de acceso», indique su certificado digital (ruta y contraseña) o elija «Sin protección», y guarde la ficha."] if sin_certificado else []
            return pagina(request, slug, empresa, _valores(empresa), avisos, "Ficha guardada" if guardada else None, info_certificado(request, slug, empresa))
        finally:
            sesion.close()

    @router.post("/empresa/{slug}")
    async def guardar(request: Request, slug: str):
        sesion, empresa = abrir(request, slug)
        try:
            exigir_acceso(request, slug, empresa, ficha=True)
            form = await request.form()
            datos = {k: str(v) for k, v in form.items()}
            actividades = list(zip(*(form.getlist(c) for c in ("act_descripcion", "act_codigo", "act_epigrafe")))) if "act_descripcion" in form else None
            representantes = list(zip(*(form.getlist(c) for c in ("rep_nombre", "rep_nif", "rep_fecha_poder", "rep_notaria")))) if "rep_nombre" in form else None
            errores: list[str] = []
            try:
                fecha = parsear_fecha(datos["fecha_constitucion"]) if datos.get("fecha_constitucion", "").strip() else None
            except ErrorContable as ex:
                errores.append(f"Fecha de constitución: {ex}")
                fecha = None
            ruta_nueva = datos.get("certificado_ruta", "").strip().strip('"')
            contrasena = datos.get("certificado_contrasena", "")
            info = None
            if not errores:
                try:
                    svc.modificar_empresa(sesion, empresa, datos.get("nombre", ""), nif=datos.get("nif"), fecha_constitucion=fecha,
                                          **{c: datos.get(c, "") for c in svc.CAMPOS_DE_TEXTO})
                    if datos.get("is_cifra_presente"):  # casilla del 202: la cifra de negocios del periodo anterior es inferior a un millón de euros
                        empresa.is_cifra_menor_1m = datos.get("is_cifra_menor_1m") == "1"
                    if actividades is not None:
                        ficha_390.guardar_actividades(sesion, empresa, actividades)
                    if representantes is not None:
                        ficha_390.guardar_representantes(sesion, empresa, representantes)
                    if "modelos_presente" in datos:  # las casillas de «Modelos que presenta»
                        svc.fijar_modelos(sesion, empresa, form.getlist("modelos"))
                    if "proteccion" in datos:  # el formulario de la ficha
                        actual = empresa.proteccion or ("certificado" if empresa.certificado_ruta else None)
                        if datos["proteccion"] != actual or (datos["proteccion"] == "certificado" and ruta_nueva != (empresa.certificado_ruta or "")):
                            info = svc.fijar_proteccion(sesion, empresa, datos["proteccion"], ruta_nueva if datos["proteccion"] == "certificado" else "", contrasena)
                    elif ruta_nueva != (empresa.certificado_ruta or ""):  # quien no envía la protección: sólo cambia el certificado (con ruta vacía, se quita)
                        info = svc.fijar_certificado(sesion, empresa, ruta_nueva, contrasena)
                    if info is not None:
                        svc.completar_desde_certificado(empresa, info)  # sin pisar lo que ya esté escrito
                except ErrorContable as ex:
                    errores.append(str(ex))
            if errores:
                sesion.rollback()
                return pagina(request, slug, empresa, {**_valores(empresa), **datos}, errores, actividades=actividades, representantes=representantes)
            sesion.commit()
            respuesta = RedirectResponse(f"/empresa/{quote(slug)}?guardada=1", status_code=303)
            if info is not None:
                _recordar(request, respuesta, slug, contrasena)  # quien acaba de asociar el certificado no se queda fuera
            return respuesta
        finally:
            sesion.close()

    return router
