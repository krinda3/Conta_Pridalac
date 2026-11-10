"""Grabar y borrar facturas recibidas y emitidas con sus asientos (docs/pseudocodigo/01_asientos_diario.md §6).

Una factura y sus asientos se graban **juntos o no se graban** (una sola transacción de quien llama). El asiento nunca se
teclea: sale de la factura (`domain.facturas.asientos_de_factura`) y se regenera cada vez que ésta se graba.

`grabar_factura` devuelve **advertencias** (no bloquean, como en MGD/el programa anterior): factura anterior al documento más antiguo,
fechas fuera de orden respecto a la numeración, total que no coincide con la suma de las líneas de IVA, factura del
proveedor repetida. Los errores (`ErrorContable`) sí impiden grabar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from conta_pridalac.servicios.bloqueo import exigir_factura_libre, exigir_fecha_libre
from conta_pridalac.db.modelos import (
    TIPO_EMITIDAS,
    TIPO_RECIBIDAS,
    Asiento,
    Ejercicio,
    Factura,
    FacturaTrimestre,
    Pago,
    Vencimiento,
)
from conta_pridalac.domain.errores import DocumentoConPagos, ErrorContable
from conta_pridalac.domain.facturas import asientos_de_factura, total_esperado
from conta_pridalac.domain.fechas import validar_en_ejercicio
from conta_pridalac.servicios.asientos import LineaAsiento, borrar_asiento, grabar_asiento

CERO = Decimal("0.00")
TIPO_ASIENTO = {"R": TIPO_RECIBIDAS, "E": TIPO_EMITIDAS}


@dataclass
class Duplicada:
    """Otra factura que puede ser la misma que se está grabando. `motivo`: «mismo_tercero» (mismo tercero y número), «mismo_numero» (emitida con un número ya usado en el ejercicio) o «mismo_importe» (mismo número y total con otro tercero)."""

    factura: Factura
    motivo: str


def _con_numero(sesion: Session, empresa_id: int, sentido: str, numero: str, excluir_id: int | None):
    consulta = select(Factura).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(
        Ejercicio.empresa_id == empresa_id, Factura.sentido == sentido, func.upper(func.trim(Factura.numero_factura)) == numero.strip().upper()
    )
    return consulta.where(Factura.id != excluir_id) if excluir_id else consulta


def buscar_posible_duplicada(sesion: Session, ejercicio: Ejercicio, sentido: str, tercero_id: int | None, numero: str | None, total: Decimal | None, excluir_id: int | None = None) -> Duplicada | None:
    """La factura ya grabada que se parece a la que se va a grabar, para avisar antes de duplicarla (`excluir_id`: la que se está editando).

    Por este orden: el mismo tercero con el mismo número (en cualquier ejercicio de la empresa); en las emitidas, el mismo número con otro cliente en el mismo ejercicio (la numeración es propia y no se repite);
    y el mismo número con el mismo total y otro tercero, que casi siempre es la misma factura con el tercero mal elegido.
    """
    if not (numero or "").strip():
        return None
    consulta = _con_numero(sesion, ejercicio.empresa_id, sentido, numero, excluir_id)
    if tercero_id is not None:
        f = sesion.scalars(consulta.where(Factura.tercero_id == tercero_id)).first()
        if f is not None:
            return Duplicada(f, "mismo_tercero")
    if sentido == "E":
        f = sesion.scalars(consulta.where(Factura.ejercicio_id == ejercicio.id)).first()
        if f is not None:
            return Duplicada(f, "mismo_numero")
    if total is not None:
        f = sesion.scalars(consulta.where(Factura.total == total)).first()
        if f is not None:
            return Duplicada(f, "mismo_importe")
    return None


@dataclass
class ResultadoFactura:
    factura: Factura
    asientos: list[Asiento]
    advertencias: list[str] = field(default_factory=list)


def siguiente_numero(sesion: Session, ejercicio: Ejercicio, sentido: str) -> int:
    maximo = sesion.scalar(
        select(func.max(Factura.numero)).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == sentido)
    )
    return (maximo or 0) + 1


def concepto_de(factura: Factura) -> str:
    """`<nº factura>-<tercero>` como el concepto de los asientos del programa anterior; si falta el nº, solo el tercero."""
    nombre = factura.tercero.nombre if factura.tercero is not None else (
        factura.cuenta_tercero.nombre if factura.cuenta_tercero is not None else ""
    )
    return "-".join(p for p in (factura.numero_factura, nombre) if p)[:255]


def advertencias_de(sesion: Session, ejercicio: Ejercicio, factura: Factura) -> list[str]:
    avisos: list[str] = []
    if factura.fecha_factura and factura.fecha_factura > factura.fecha_contable:
        avisos.append(
            f"La fecha de la factura ({factura.fecha_factura:%d/%m/%Y}) es posterior a la fecha contable "
            f"({factura.fecha_contable:%d/%m/%Y})"
        )
    esperado = total_esperado(factura)
    if esperado is not None and esperado != factura.total:
        avisos.append(
            f"El total ({factura.total}) no coincide con base + IVA + recargo + ajustes ({esperado}); "
            f"diferencia {factura.total - esperado}"
        )
    # Orden de fechas respecto a los documentos vecinos por número (MGD `MiraFechaER`)
    anterior = sesion.scalars(
        select(Factura)
        .where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == factura.sentido, Factura.numero < factura.numero)
        .order_by(Factura.numero.desc())
        .limit(1)
    ).first()
    siguiente = sesion.scalars(
        select(Factura)
        .where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == factura.sentido, Factura.numero > factura.numero)
        .order_by(Factura.numero)
        .limit(1)
    ).first()
    if anterior is not None and factura.fecha_contable < anterior.fecha_contable:
        avisos.append(
            f"La fecha ({factura.fecha_contable:%d/%m/%Y}) es anterior a la de la factura nº {anterior.numero} "
            f"({anterior.fecha_contable:%d/%m/%Y})"
        )
    if siguiente is not None and factura.fecha_contable > siguiente.fecha_contable:
        avisos.append(
            f"La fecha ({factura.fecha_contable:%d/%m/%Y}) es posterior a la de la factura nº {siguiente.numero} "
            f"({siguiente.fecha_contable:%d/%m/%Y})"
        )
    if factura.numero_factura and factura.tercero_id:
        repetida = sesion.scalars(
            select(Factura).where(
                Factura.ejercicio_id == ejercicio.id,
                Factura.sentido == factura.sentido,
                Factura.tercero_id == factura.tercero_id,
                Factura.numero_factura == factura.numero_factura,
                Factura.numero != factura.numero,
            )
        ).first()
        if repetida is not None:
            avisos.append(f"Ya existe la factura {factura.numero_factura} de este tercero (documento nº {repetida.numero})")
    return avisos


def grabar_factura(sesion: Session, ejercicio: Ejercicio, factura: Factura, *, solo_cuentas: bool = False) -> ResultadoFactura:
    """Graba (o regraba) la factura y regenera sus asientos. Levanta `ErrorContable` si algo es incorrecto.

    `solo_cuentas`: la factura sólo cambia de tercero o de cuenta de gasto (importes, IVA y fechas quedan igual), así que no altera ningún modelo presentado y se puede regrabar aunque su trimestre
    ya esté presentado. Quien lo use (`servicios/correcciones.py`) es quien garantiza que no cambia nada más.
    """
    if factura.sentido not in TIPO_ASIENTO:
        raise ErrorContable(f"Sentido de factura desconocido: {factura.sentido!r}")
    validar_en_ejercicio(factura.fecha_contable, ejercicio)
    if not solo_cuentas:
        exigir_factura_libre(sesion, ejercicio.empresa_id, factura)  # una factura de un trimestre presentado no se toca
        exigir_fecha_libre(sesion, ejercicio.empresa_id, factura.fecha_contable)
    if factura.cuenta_tercero_id is None and factura.cuenta_tercero is None:
        raise ErrorContable("Falta la cuenta del tercero (cliente o proveedor)")
    if factura.cuenta_contrapartida_id is None and factura.cuenta_contrapartida is None:
        raise ErrorContable("Falta la cuenta de gasto o de ingreso")

    factura.ejercicio_id = ejercicio.id
    if not factura.numero:
        factura.numero = siguiente_numero(sesion, ejercicio, factura.sentido)
    sesion.add(factura)
    sesion.flush()
    sesion.refresh(factura)

    tipo, concepto = TIPO_ASIENTO[factura.sentido], concepto_de(factura)
    grupos = asientos_de_factura(factura)
    asientos: list[Asiento] = []
    for sub, lineas in enumerate(grupos):
        a = grabar_asiento(
            sesion,
            ejercicio,
            tipo=tipo,
            numero=factura.numero,
            sub=sub,
            fecha=factura.fecha_contable,
            concepto=concepto,
            subtipo="M",
            lineas=[LineaAsiento(cuenta, importe) for cuenta, importe in lineas.items()],
        )
        if a is not None:
            asientos.append(a)
    # asientos adicionales que ya no corresponden (se quitó un ajuste que abría un asiento nuevo)
    sub = len(grupos)
    while borrar_asiento(sesion, ejercicio, tipo, factura.numero, sub):
        sub += 1

    return ResultadoFactura(factura, asientos, advertencias_de(sesion, ejercicio, factura))


def eliminar_factura(sesion: Session, ejercicio: Ejercicio, factura: Factura) -> None:
    """Borra la factura, sus asientos, sus vencimientos y sus adjuntos. No si ya tiene cobros o pagos aplicados ni si está en un trimestre presentado."""
    validar_en_ejercicio(factura.fecha_contable, ejercicio)
    exigir_factura_libre(sesion, ejercicio.empresa_id, factura)
    vencimientos = sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == factura.id)).all()
    con_pagos = [
        v for v in vencimientos if sesion.scalar(select(func.count()).select_from(Pago).where(Pago.vencimiento_id == v.id))
    ]
    if con_pagos:
        raise DocumentoConPagos(
            f"La factura nº {factura.numero} tiene {len(con_pagos)} vencimiento(s) con cobros o pagos aplicados; "
            "deshaga primero los movimientos de banco"
        )
    tipo = TIPO_ASIENTO[factura.sentido]
    sub = 0
    while borrar_asiento(sesion, ejercicio, tipo, factura.numero, sub):
        sub += 1
    for v in vencimientos:
        sesion.delete(v)
    sesion.execute(update(FacturaTrimestre).where(FacturaTrimestre.factura_id == factura.id).values(factura_id=None))  # vuelve a estar pendiente en la lista de trabajo del trimestre
    sesion.delete(factura)
    sesion.flush()
