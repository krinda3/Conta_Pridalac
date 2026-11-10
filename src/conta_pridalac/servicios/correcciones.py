"""Corregir el proveedor y la cuenta de gasto de facturas ya contabilizadas, sin tocar importes, IVA ni fechas.

Una factura mal clasificada (un recibo de gas que está como agua, una gasolinera como gas) se corrige cambiando su tercero y su cuenta de gasto. Como el IVA, el total y las fechas no cambian, no se altera
ningún 303 presentado y se permite aunque el trimestre ya esté presentado; el ejercicio, eso sí, tiene que estar abierto. Se regeneran el asiento de la factura y los de los movimientos de banco que la pagan.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Factura, Pago, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.tesoreria import regenerar_asiento


def cambiar_proveedor_y_gasto(sesion: Session, ejercicio: Ejercicio, factura: Factura, *, tercero: Tercero | None = None, gasto: Cuenta | None = None) -> bool:
    """Devuelve `True` si ha cambiado algo. No hace commit."""
    if ejercicio.cerrado:
        raise ErrorContable(f"El ejercicio {ejercicio.anio} está cerrado: la factura {factura.numero_factura} no se toca")
    if factura.sentido != "R":
        raise ErrorContable("De momento sólo se corrigen facturas recibidas")
    cuenta_anterior = factura.cuenta_tercero_id
    cambia_tercero = tercero is not None and (tercero.id != factura.tercero_id or tercero.cuenta_id != factura.cuenta_tercero_id)
    cambia_gasto = gasto is not None and gasto.id != factura.cuenta_contrapartida_id
    if not cambia_tercero and not cambia_gasto:
        return False
    if cambia_tercero:
        if tercero.cuenta_id is None:
            raise ErrorContable(f"«{tercero.nombre}» no tiene subcuenta contable")
        factura.tercero_id, factura.cuenta_tercero_id = tercero.id, tercero.cuenta_id
        factura.tercero, factura.cuenta_tercero = tercero, sesion.get(Cuenta, tercero.cuenta_id)
    if cambia_gasto:
        factura.cuenta_contrapartida_id, factura.cuenta_contrapartida = gasto.id, gasto
    vencimientos = list(sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == factura.id)))
    for v in vencimientos:
        if cambia_tercero and v.cuenta_id == cuenta_anterior:  # un devengo explícito en la cuenta del proveedor anterior pasa al nuevo
            v.cuenta_id = factura.cuenta_tercero_id
    grabar_factura(sesion, ejercicio, factura, solo_cuentas=True)
    sesion.flush()
    if cambia_tercero:  # los pagos cargan la cuenta del proveedor: sus asientos se rehacen
        for movimiento in {p.movimiento for p in sesion.scalars(select(Pago).where(Pago.vencimiento_id.in_([v.id for v in vencimientos])))} if vencimientos else ():
            regenerar_asiento(sesion, ejercicio, movimiento)
    return True
