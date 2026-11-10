"""Reglas de tesorería (docs/pseudocodigo/02_tesoreria.md), verificadas con MGD 2021."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    BANCO_REMESAS,
    Banco,
    Cuenta,
    MovimientoBanco,
    Pago,
    Parametro,
    Vencimiento,
)

CERO = Decimal("0.00")


def pendiente(sesion: Session, vencimiento: Vencimiento) -> Decimal:
    """Pendiente de un vencimiento = importe − Σ pagos (se calcula, no se guarda)."""
    pagado = sesion.scalar(select(func.sum(Pago.importe)).where(Pago.vencimiento_id == vencimiento.id))
    return vencimiento.importe - (pagado or CERO)


def cuenta_efectiva(vencimiento: Vencimiento) -> Cuenta | None:
    """Cuenta en la que se devenga el vencimiento (regla §2 del pseudocódigo)."""
    if vencimiento.cuenta is not None:
        return vencimiento.cuenta
    if vencimiento.origen_tipo == "B":
        return vencimiento.cuenta_defecto
    if vencimiento.factura is not None and vencimiento.factura.cuenta_tercero is not None:
        return vencimiento.factura.cuenta_tercero
    return vencimiento.cuenta_origen or vencimiento.cuenta_defecto


def cuenta_pendiente_de_aplicar(sesion: Session, empresa_id: int) -> str:
    valor = sesion.scalar(
        select(Parametro.valor).where(Parametro.empresa_id == empresa_id, Parametro.clave == "PTE_APLIC")
    )
    if not valor or not valor.strip():
        raise ValueError("Falta el parámetro PTE_APLIC (cuenta de partidas pendientes de aplicar)")
    return valor.strip()


def apuntes_de_movimiento(sesion: Session, movimiento: MovimientoBanco) -> Counter:
    """Asiento que corresponde a un movimiento de banco: {código de cuenta (8 dígitos): importe con signo}.

    Positivo = debe. Las líneas de la misma cuenta se agrupan (parámetro NO_REDUCE_APUNTES = 'N').
    """
    pagos = movimiento.pagos
    banco: Banco = movimiento.banco
    resultado: Counter = Counter()
    if not pagos:
        return resultado

    total = sum((p.importe for p in pagos), CERO)
    if banco.clase == BANCO_REMESAS:
        cuenta_banco = pagos[0].cuenta_directa  # la remesa va contra la cuenta de destino del primer pago
    else:
        cuenta_banco = banco.cuenta
    if total != 0:
        resultado[cuenta_banco.codigo] += total

    pte_aplicar: str | None = None
    for p in pagos:
        if p.vencimiento is not None:
            codigo = cuenta_efectiva(p.vencimiento).codigo
        elif p.cuenta_directa is not None:
            codigo = p.cuenta_directa.codigo
        else:
            if pte_aplicar is None:
                pte_aplicar = cuenta_pendiente_de_aplicar(sesion, banco.empresa_id)
            codigo = pte_aplicar
        resultado[codigo] -= p.importe
    return Counter({c: v for c, v in resultado.items() if v != 0})


def saldos_corridos(sesion: Session, banco: Banco) -> list[tuple[MovimientoBanco, Decimal]]:
    """Saldo acumulado tras cada movimiento (orden fecha, clave, número). Parte de 0, sin el saldo inicial."""
    movimientos = sesion.scalars(
        select(MovimientoBanco)
        .where(MovimientoBanco.banco_id == banco.id)
        .order_by(MovimientoBanco.fecha, MovimientoBanco.clave, MovimientoBanco.numero)
    ).all()
    saldo, salida = CERO, []
    for m in movimientos:
        saldo += sum((p.importe for p in m.pagos), CERO)
        salida.append((m, saldo))
    return salida
