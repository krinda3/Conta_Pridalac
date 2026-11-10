"""Vencimientos de una factura (docs/pseudocodigo/02_tesoreria.md §1–§4).

Reglas (verificadas con MGD 2021, 267 de 268 facturas; la excepción lleva retención de IRPF):
- Σ vencimientos de la factura = **total + retenciones**: lo que se debe pagar al tercero (el total) más lo que se debe
  ingresar a Hacienda (cada ajuste, en su propio vencimiento con su cuenta). En una factura sin ajustes: Σ = total.
- Signo: a **cobrar** positivo (emitidas), a **pagar** negativo (recibidas). Un abono (total negativo) invierte el signo.
- La fecha puede quedar vacía (pendiente de determinar): MGD tiene 9 vencimientos así.
- `pendiente = importe − Σ pagos` se calcula (`domain.tesoreria.pendiente`), no se guarda.
- Se puede **dividir** un importe en N plazos: cada uno `round(importe / N)` y el primero absorbe la diferencia.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Factura, FormaPago, Pago, Vencimiento
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import DocumentoConPagos, ErrorContable
from conta_pridalac.domain.fechas import validar_en_ejercicio
from conta_pridalac.domain.tesoreria import CERO
from conta_pridalac.domain.amortizacion import suma_meses


@dataclass
class PlazoVencimiento:
    """Un plazo a definir. `importe` va en positivo (o negativo en un abono) con el mismo signo que el total de la factura."""

    importe: Decimal
    fecha: date | None = None
    cuenta: str | None = None  # código de 8 dígitos si el devengo va a una cuenta distinta de la del tercero
    banco: Banco | None = None  # banco previsto
    forma_pago: FormaPago | None = None


def importe_a_vencer(factura: Factura) -> Decimal:
    """Σ que han de sumar los plazos (con el signo del total de la factura)."""
    return factura.total - sum((a.importe for a in factura.ajustes), CERO)


def signo(factura: Factura) -> int:
    return -1 if factura.sentido == "R" else 1


def repartir_en_plazos(importe: Decimal, n: int, primera_fecha: date | None, *, meses_entre: int = 1, **resto) -> list[PlazoVencimiento]:
    """Divide `importe` en `n` plazos iguales. El primero absorbe la diferencia de redondeo (`clVtos.EdicionDividir`)."""
    if n < 1:
        raise ErrorContable("El número de plazos ha de ser al menos 1")
    cada = (dinero(importe) / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    plazos = []
    for i in range(n):
        fecha = suma_meses(primera_fecha, i * meses_entre) if primera_fecha else None
        plazos.append(PlazoVencimiento(importe=cada, fecha=fecha, **resto))
    plazos[0].importe = dinero(importe) - (n - 1) * cada
    return plazos


def plazos_por_defecto(factura: Factura, fecha: date | None = None) -> list[PlazoVencimiento]:
    """Un plazo con el total más uno por cada ajuste (retención), con la cuenta del ajuste."""
    plazos = [PlazoVencimiento(importe=factura.total, fecha=fecha or factura.fecha_factura or factura.fecha_contable)]
    for a in factura.ajustes:
        if a.importe != 0:
            plazos.append(PlazoVencimiento(importe=-a.importe, fecha=fecha or factura.fecha_contable, cuenta=a.cuenta.codigo))
    return plazos


def _cuenta(sesion: Session, ejercicio: Ejercicio, codigo: str) -> Cuenta:
    c = sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == codigo)).one_or_none()
    if c is None:
        raise ErrorContable(f"La cuenta {codigo} no existe en el plan de la empresa")
    return c


def definir_vencimientos(sesion: Session, ejercicio: Ejercicio, factura: Factura, plazos: list[PlazoVencimiento]) -> list[Vencimiento]:
    """Establece los vencimientos de la factura (los crea o reemplaza). Los plazos deben sumar el importe a vencer.

    Los vencimientos que ya tienen pagos no se pueden quitar; sí se pueden modificar (el pendiente se recalcula).
    """
    validar_en_ejercicio(factura.fecha_contable, ejercicio)
    suma = sum((dinero(p.importe) for p in plazos), CERO)
    esperado = importe_a_vencer(factura)
    if suma != esperado:
        raise ErrorContable(
            f"Los vencimientos suman {suma} y la factura exige {esperado} (total {factura.total} + retenciones); diferencia {suma - esperado}"
        )
    if factura.id is None:
        factura.ejercicio_id = ejercicio.id
        sesion.add(factura)
        sesion.flush()

    existentes = sorted(sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == factura.id)), key=lambda v: v.id)
    for sobrante in existentes[len(plazos):]:
        if sobrante.pagos:
            raise DocumentoConPagos(f"El vencimiento del {sobrante.fecha} ya tiene cobros o pagos; no se puede quitar")
        sesion.delete(sobrante)

    resultado: list[Vencimiento] = []
    for i, p in enumerate(plazos):
        v = existentes[i] if i < len(existentes) else Vencimiento(ejercicio_id=ejercicio.id, factura_id=factura.id)
        v.origen_tipo, v.origen_numero = factura.sentido, factura.numero
        v.fecha = p.fecha
        v.importe = signo(factura) * dinero(p.importe)
        v.cuenta_id = _cuenta(sesion, ejercicio, p.cuenta).id if p.cuenta else None
        v.cuenta_defecto_id = factura.cuenta_tercero_id
        v.banco_previsto = p.banco
        v.forma_pago = p.forma_pago
        sesion.add(v)
        resultado.append(v)
    sesion.flush()
    return resultado
