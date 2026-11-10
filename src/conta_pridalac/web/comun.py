"""Utilidades compartidas por los formularios propios (facturas, asientos, plantillas)."""
from __future__ import annotations

import tempfile
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta
from conta_pridalac.servicios import adjuntos as svc_adjuntos
from conta_pridalac.web.listados import Contexto, parsear_dinero

CERO = Decimal("0.00")


def texto_dinero(valor: Decimal | None) -> str:
    """`1234.5` → `1234,50` (como se rellena un campo de importe)."""
    return "" if valor is None else f"{valor:.2f}".replace(".", ",")


def dinero_opcional(texto: str, nombre: str) -> Decimal | None:
    """Importe tecleado → `Decimal`; vacío → `None`; algo que no es un importe → `ValueError` con el nombre del campo."""
    if not (texto or "").strip():
        return None
    try:
        return parsear_dinero(texto)
    except ValueError:
        raise ValueError(f"«{nombre}»: «{texto}» no es un importe válido") from None


def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CERO, rounding=ROUND_HALF_UP)


def fecha_texto(f: date | None) -> str:
    return f"{f:%d/%m/%Y}" if f else ""


def codigo_de_cuenta(ctx: Contexto, cuenta_id: int | None) -> str:
    return ctx.sesion.scalar(select(Cuenta.codigo).where(Cuenta.id == cuenta_id)) if cuenta_id else ""


def id_de_cuenta(ctx: Contexto, codigo: str, para: str, errores: list[str], *, obligatoria: bool = True) -> int | None:
    """Id de la cuenta con ese código; si no existe (o falta y es obligatoria) añade el motivo a `errores`."""
    codigo = (codigo or "").strip()
    if not codigo:
        if obligatoria:
            errores.append(f"Falta la cuenta de {para}")
        return None
    c = ctx.sesion.scalar(select(Cuenta.id).where(Cuenta.empresa_id == ctx.empresa.id, Cuenta.codigo == codigo))
    if c is None:
        errores.append(f"No existe la cuenta {codigo} ({para})")
    return c


def cuentas_para_listas(ctx: Contexto) -> list[tuple[str, str]]:
    return [(c, n) for c, n in ctx.sesion.execute(select(Cuenta.codigo, Cuenta.nombre).where(Cuenta.empresa_id == ctx.empresa.id).order_by(Cuenta.codigo))]


def guardar_justificantes(ctx: Contexto, destino, quitar: set[int], ficheros: list) -> list[str]:
    """Quita los justificantes marcados y sube los nuevos. Devuelve las advertencias (p. ej. un duplicado). Un fichero inválido lanza error."""
    almacen = ctx.config.almacen_de_adjuntos()
    for adjunto in list(destino.adjuntos if hasattr(destino, "adjuntos") else _adjuntos(ctx, destino)):
        if adjunto.id in quitar:
            svc_adjuntos.quitar(ctx.sesion, almacen, ctx.ejercicio, adjunto)
    ctx.sesion.refresh(destino)
    advertencias: list[str] = []
    for nombre, contenido in ficheros:
        if not nombre:
            continue
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / svc_adjuntos.nombre_seguro(nombre)
            ruta.write_bytes(contenido)
            advertencias += svc_adjuntos.adjuntar(ctx.sesion, almacen, ctx.ejercicio, destino, ruta, nombre=nombre).advertencias
    return advertencias


def _adjuntos(ctx: Contexto, destino):
    return svc_adjuntos.listar(ctx.sesion, destino)
