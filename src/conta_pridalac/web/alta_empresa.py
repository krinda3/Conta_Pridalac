"""Pantalla «Añadir empresa»: una empresa vacía con el plan del PGC, o cargada desde una copia de Gestión MGD (`servicios/alta_empresa.py`)."""
from __future__ import annotations

import secrets
import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.pgc import TIPOS_DE_PLAN
from conta_pridalac.servicios import alta_empresa as svc
from conta_pridalac.servicios.empresa import PROTECCIONES

DIGITOS_A_ELEGIR = [6, 7, 8, 9, 10]
PENDIENTES_MAXIMAS = 3  # copias subidas a la espera de confirmar: las más antiguas se descartan


def crear_router(config_de, render) -> APIRouter:
    router = APIRouter()

    def pendientes(request: Request) -> dict[str, dict]:
        return request.app.state.__dict__.setdefault("altas_pendientes", {})

    def olvidar(request: Request, token: str) -> None:
        p = pendientes(request).pop(token, None)
        if p:
            Path(p["zip"]).unlink(missing_ok=True)

    def pagina(request: Request, errores=None, valores=None, **extra):
        return render(request, "alta_empresa.html", ctx=None, anio_actual=date.today().year, digitos_a_elegir=DIGITOS_A_ELEGIR, tipos_de_plan=TIPOS_DE_PLAN, errores=errores or [], valores=valores or {},
                      protecciones=PROTECCIONES, **extra)

    def destino(request: Request, alta: svc.Alta) -> str:
        """Si se eligió proteger la empresa con certificado, lo primero es indicarlo en su ficha; si no, se entra en la empresa."""
        return f"/empresa/{alta.slug}?sin_certificado=1" if proteccion_elegida(request, alta) == "certificado" else f"/e/{alta.slug}/{alta.anio}"

    def proteccion_elegida(request: Request, alta: svc.Alta) -> str:
        from conta_pridalac.db.modelos import Empresa

        sesion = config_de(request).sesion(alta.slug)
        try:
            empresa = sesion.query(Empresa).first()
            return (empresa.proteccion if empresa else None) or ("certificado" if config_de(request).exigir_certificado else "ninguna")
        finally:
            sesion.close()

    def proteccion_por_defecto(request: Request) -> str:
        return "certificado" if config_de(request).exigir_certificado else "ninguna"

    @router.get("/empresa-nueva", response_class=HTMLResponse)
    def formulario(request: Request):
        return pagina(request, valores={"anio": date.today().year, "digitos": 8, "tipo_plan": "pymes", "proteccion": proteccion_por_defecto(request)})

    @router.post("/empresa-nueva/vacia")
    def crear_vacia(request: Request, nombre: str = Form(""), nif: str = Form(""), anio: int = Form(0), digitos: int = Form(8), tipo_plan: str = Form("pymes"), proteccion: str = Form("")):
        proteccion = proteccion or proteccion_por_defecto(request)
        try:
            alta = svc.crear_empresa_nueva(config_de(request), nombre=nombre, nif=nif, anio=anio, digitos=digitos, tipo_plan=tipo_plan, proteccion=proteccion)
        except ErrorContable as e:
            return pagina(request, errores=[str(e)], valores={"nombre": nombre, "nif": nif, "anio": anio, "digitos": digitos, "tipo_plan": tipo_plan, "proteccion": proteccion})
        return RedirectResponse(destino(request, alta), status_code=303)

    @router.post("/empresa-nueva/mgd")
    def subir_copia(request: Request, archivo: UploadFile = File(...)):
        """Recibe el `.zip` de la copia de MGD, lo examina y enseña lo que ha encontrado para confirmarlo."""
        guardados = pendientes(request)
        while len(guardados) >= PENDIENTES_MAXIMAS:
            olvidar(request, next(iter(guardados)))
        with tempfile.NamedTemporaryFile(prefix="conta_alta_", suffix=".zip", delete=False) as f:
            shutil.copyfileobj(archivo.file, f)
            ruta = Path(f.name)
        try:
            with svc.abrir_copia(ruta) as carpeta:
                copia = svc.examinar_copia(carpeta)
        except (ErrorContable, OSError) as e:
            ruta.unlink(missing_ok=True)
            return pagina(request, errores=[f"No se puede usar «{archivo.filename}»: {e}"], valores={"anio": date.today().year, "digitos": 8})
        token = secrets.token_urlsafe(16)
        guardados[token] = {"zip": str(ruta), "fichero": archivo.filename, "copia": copia}
        valores = {"nombre": copia.nombre or "", "nif": "", "anio": copia.anio or date.today().year, "tipo_plan": "pymes", "proteccion": proteccion_por_defecto(request)}
        return render(request, "alta_mgd.html", ctx=None, token=token, fichero=archivo.filename, copia=copia, valores=valores, errores=[], tipos_de_plan=TIPOS_DE_PLAN, protecciones=PROTECCIONES)

    @router.post("/empresa-nueva/mgd/crear")
    def crear_desde_copia(request: Request, token: str = Form(""), nombre: str = Form(""), nif: str = Form(""), anio: int = Form(0), tipo_plan: str = Form("pymes"), proteccion: str = Form("")):
        proteccion = proteccion or proteccion_por_defecto(request)
        pendiente = pendientes(request).get(token)
        if pendiente is None:
            return pagina(request, errores=["La copia ya no está disponible: vuelva a subirla"], valores={"anio": date.today().year, "digitos": 8})
        copia = pendiente["copia"]
        try:
            with svc.abrir_copia(pendiente["zip"]) as carpeta:
                alta = svc.crear_desde_mgd(config_de(request), carpeta, nombre=nombre, nif=nif, anio=anio, codigo=copia.codigo_empresa or 1, tipo_plan=tipo_plan, proteccion=proteccion)
        except ErrorContable as e:
            return render(request, "alta_mgd.html", ctx=None, token=token, fichero=pendiente["fichero"], copia=copia, valores={"nombre": nombre, "nif": nif, "anio": anio, "tipo_plan": tipo_plan, "proteccion": proteccion}, errores=[str(e)], tipos_de_plan=TIPOS_DE_PLAN,
                          protecciones=PROTECCIONES)
        olvidar(request, token)
        return RedirectResponse(destino(request, alta), status_code=303)

    @router.post("/empresa-nueva/mgd/cancelar")
    def cancelar(request: Request, token: str = Form("")):
        olvidar(request, token)
        return RedirectResponse("/empresa-nueva", status_code=303)

    return router
