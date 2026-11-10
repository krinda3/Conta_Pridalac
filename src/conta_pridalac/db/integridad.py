"""Comprobaciones de integridad contable (semilla de la auditoría del Hito 1).

Cada función devuelve una lista; vacía = sin problemas.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Empresa


def asientos_descuadrados(sesion: Session, ejercicio_id: int) -> list[tuple[str, Decimal]]:
    """Asientos cuya suma de debe no iguala la de haber. Devuelve (identificador, diferencia)."""
    filas = sesion.execute(
        select(Asiento.tipo, Asiento.numero, Asiento.sub, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Apunte, Apunte.asiento_id == Asiento.id)
        .where(Asiento.ejercicio_id == ejercicio_id)
        .group_by(Asiento.id)
    ).all()
    return [
        (f"{t}.{n}" + (f"/{s}" if s else ""), (d or 0) - (h or 0))
        for t, n, s, d, h in filas
        if (d or 0) != (h or 0)
    ]


def apuntes_en_cuentas_de_grupo(sesion: Session, ejercicio_id: int) -> list[int]:
    """Apuntes que usan una cuenta con menos dígitos que las subcuentas de la empresa (solo las subcuentas admiten apuntes)."""
    return list(
        sesion.scalars(
            select(Apunte.id)
            .join(Asiento, Asiento.id == Apunte.asiento_id)
            .join(Cuenta, Cuenta.id == Apunte.cuenta_id)
            .join(Empresa, Empresa.id == Cuenta.empresa_id)
            .where(Asiento.ejercicio_id == ejercicio_id, func.length(Cuenta.codigo) < Empresa.digitos_cuenta)
        )
    )


def huecos_numeracion_diario(sesion: Session, ejercicio_id: int) -> list[int]:
    """Números que faltan en la numeración correlativa del libro diario."""
    numeros = sorted(
        n
        for n in sesion.scalars(
            select(Asiento.numero_diario).where(Asiento.ejercicio_id == ejercicio_id).distinct()
        )
        if n is not None
    )
    if not numeros:
        return []
    presentes = set(numeros)
    return [n for n in range(numeros[0], numeros[-1] + 1) if n not in presentes]
