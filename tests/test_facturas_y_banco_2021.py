"""Reglas contables sobre las dos empresas de MGD 2021 (Empresa A y Empresa B).

Cada regla del dominio debe reproducir **exactamente** lo contabilizado en MGD.
"""
from collections import Counter

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.integridad import asientos_descuadrados
from conta_pridalac.db.modelos import Asiento, Factura, MovimientoBanco, Pago
from conta_pridalac.domain.facturas import asientos_de_factura
from conta_pridalac.domain.tesoreria import apuntes_de_movimiento

pytestmark = pytest.mark.datos_reales

# Cifras de las tablas originales
ESPERADO = {
    "empresa_a": {"asientos": 103, "recibidas": 56, "emitidas": 1, "movimientos": 43, "transferencias": 0},
    "empresa_b": {"asientos": 495, "recibidas": 190, "emitidas": 21, "movimientos": 320, "transferencias": 94},
}


def _lineas(asiento: Asiento) -> Counter:
    c: Counter = Counter()
    for ap in asiento.apuntes:
        c[ap.cuenta.codigo] += ap.debe - ap.haber
    return Counter({k: v for k, v in c.items() if v != 0})


def test_volumenes_y_cuadre(sesion, carga_mgd):
    esperado = ESPERADO[carga_mgd.clave]
    assert carga_mgd.asientos == esperado["asientos"]
    assert carga_mgd.movimientos == esperado["movimientos"]
    assert asientos_descuadrados(sesion, carga_mgd.ejercicio_id) == []
    por_sentido = dict(sesion.execute(select(Factura.sentido, func.count()).group_by(Factura.sentido)).all())
    assert por_sentido == {"R": esperado["recibidas"], "E": esperado["emitidas"]}


def test_el_asiento_de_cada_factura_es_el_del_diario(sesion, carga_mgd):
    """Facturas recibidas y emitidas (con ajustes de IRPF cuando los hay): 100 % idénticas al Diario."""
    comprobadas = 0
    for factura in sesion.scalars(select(Factura)):
        tipo = 2 if factura.sentido == "R" else 1
        for sub, esperado in enumerate(asientos_de_factura(factura)):
            asiento = sesion.scalars(
                select(Asiento).where(Asiento.tipo == tipo, Asiento.numero == factura.numero, Asiento.sub == sub)
            ).one()
            assert esperado == _lineas(asiento), f"{factura.sentido} nº {factura.numero}"
        comprobadas += 1
    assert comprobadas == sum(ESPERADO[carga_mgd.clave][k] for k in ("recibidas", "emitidas"))


def test_el_asiento_de_cada_movimiento_de_banco_es_el_del_diario(sesion, carga_mgd):
    """Si las líneas se anulan (lado de entrada de una transferencia) no hay asiento en el Diario."""
    con_asiento = sin_asiento = 0
    for mov in sesion.scalars(select(MovimientoBanco)):
        esperado = apuntes_de_movimiento(sesion, mov)
        asiento = sesion.scalars(select(Asiento).where(Asiento.tipo == 3, Asiento.numero == mov.numero)).one_or_none()
        if esperado:
            assert asiento is not None and esperado == _lineas(asiento), f"movimiento {mov.numero}"
            con_asiento += 1
        else:
            assert asiento is None, f"movimiento {mov.numero} no debería tener asiento"
            sin_asiento += 1
    assert con_asiento + sin_asiento == ESPERADO[carga_mgd.clave]["movimientos"]
    assert sin_asiento == ESPERADO[carga_mgd.clave]["transferencias"] // 2


def test_las_transferencias_entre_bancos_son_parejas_espejo(sesion, carga_mgd):
    """Cada transferencia son dos movimientos que se apuntan entre sí con importes opuestos.

    Un lado de cada pareja lleva como cuenta directa la del **otro** banco y genera el asiento; el otro lado lleva la de su
    **propio** banco, así que sus líneas se anulan y no hay asiento. Normalmente el lado con asiento es el de salida
    (importe negativo): en Empresa B 44 de 47 parejas; en las otras 3 se registró desde el banco que recibe.
    """
    transferencias = sesion.scalars(select(Pago).where(Pago.movimiento_contraparte_id.is_not(None))).all()
    assert len(transferencias) == ESPERADO[carga_mgd.clave]["transferencias"]
    con_asiento_en_salida = 0
    for p in transferencias:
        contraparte = p.movimiento_contraparte
        assert len(contraparte.pagos) == 1 and len(p.movimiento.pagos) == 1
        espejo = contraparte.pagos[0]
        assert espejo.movimiento_contraparte_id == p.movimiento_id
        assert espejo.importe == -p.importe
        assert p.movimiento.banco_id != contraparte.banco_id
        propio, ajeno = p.movimiento.banco.cuenta_id, contraparte.banco.cuenta_id
        assert p.cuenta_directa_id in (propio, ajeno)
        lleva_la_ajena = p.cuenta_directa_id == ajeno
        espejo_lleva_la_ajena = espejo.cuenta_directa_id == propio  # para el espejo, "la ajena" es la de este banco
        assert lleva_la_ajena != espejo_lleva_la_ajena  # exactamente un lado de la pareja genera el asiento
        if lleva_la_ajena and p.importe < 0:
            con_asiento_en_salida += 1
    assert con_asiento_en_salida == (44 if carga_mgd.clave == "empresa_b" else 0)
