"""Bloqueo de las facturas de un trimestre ya presentado a la AEAT (modelo 303).

Una factura no se puede modificar ni borrar si su fecha contable cae en un trimestre del que consta un 303 presentado (con este programa o importado del programa anterior),
ni si aparece en alguna declaración presentada (aunque se declarase en un trimestre distinto del de su fecha). Tampoco se puede grabar una factura nueva con fecha
contable en un trimestre presentado: las facturas atrasadas se contabilizan en el periodo en que se introducen. Para corregir una factura presentada se hace una factura
rectificativa con fecha actual que la anule y se crea la factura nueva.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionLinea, DeclaracionPresentada, Factura, PresentacionAeat, PRESENTADA, SUSTITUIDA
from conta_pridalac.domain.errores import ErrorContable

CONSEJO = "Para corregirla, cree una factura rectificativa con la fecha de hoy que la anule y después la factura nueva."


def trimestre_de(fecha: date) -> int:
    return (fecha.month - 1) // 3 + 1


def trimestre_presentado(sesion: Session, empresa_id: int, fecha: date) -> str | None:
    """«2T 2026» si la fecha cae en un trimestre con un 303 presentado; `None` si no."""
    periodo = trimestre_de(fecha)
    nuestro = sesion.scalar(
        select(PresentacionAeat.id).where(
            PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == fecha.year, PresentacionAeat.periodo == f"{periodo}T",
            PresentacionAeat.estado.in_((PRESENTADA, SUSTITUIDA)),
        ).limit(1)
    )
    importado = sesion.scalar(
        select(DeclaracionPresentada.id).where(
            DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == "303", DeclaracionPresentada.anio == fecha.year, DeclaracionPresentada.periodo == periodo
        ).limit(1)
    )
    return f"{periodo}T {fecha.year}" if nuestro is not None or importado is not None else None


def declaracion_con_la_factura(sesion: Session, factura_id: int) -> str | None:
    """«2T 2026» si la factura figura en una declaración presentada (importada del programa anterior); `None` si no."""
    fila = sesion.execute(
        select(DeclaracionPresentada.periodo, DeclaracionPresentada.anio)
        .join(DeclaracionLinea, DeclaracionLinea.declaracion_id == DeclaracionPresentada.id)
        .where(DeclaracionLinea.factura_id == factura_id, DeclaracionPresentada.modelo == "303")
        .limit(1)
    ).first()
    return f"{fila[0]}T {fila[1]}" if fila else None


def exigir_factura_libre(sesion: Session, empresa_id: int, factura: Factura) -> None:
    """Para una factura ya grabada (llamar **antes** de modificarla): falla si está en un trimestre presentado o incluida en una declaración presentada."""
    if factura.id is None:
        return
    with sesion.no_autoflush:
        fecha = sesion.scalar(select(Factura.fecha_contable).where(Factura.id == factura.id))
        donde = (trimestre_presentado(sesion, empresa_id, fecha) if fecha else None) or declaracion_con_la_factura(sesion, factura.id)
    if donde:
        raise ErrorContable(f"La factura {factura.sentido} {factura.numero} ya está incluida en el 303 del {donde}, presentado a la AEAT: no se puede modificar ni borrar. {CONSEJO}")


def exigir_fecha_libre(sesion: Session, empresa_id: int, fecha: date) -> None:
    """Para una factura que se va a grabar: su fecha contable no puede estar en un trimestre presentado."""
    donde = trimestre_presentado(sesion, empresa_id, fecha)
    if donde:
        raise ErrorContable(
            f"El {donde} ya está presentado a la AEAT (modelo 303): no se pueden contabilizar facturas con fecha contable del {fecha:%d/%m/%Y}. "
            "Contabilícela con la fecha de hoy (las facturas atrasadas van en el periodo en que se introducen)."
        )
