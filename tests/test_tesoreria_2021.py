"""Tesorería de la BBDD 2021 de Empresa A: las reglas reproducen lo contabilizado en MGD.

Equivale a `tools/validar_tesoreria.py` pero sobre el modelo nuevo (esquema + cargador + dominio).
"""
from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.modelos import (
    Apunte,
    Asiento,
    Banco,
    MovimientoBanco,
    Pago,
    Vencimiento,
)
from conta_pridalac.domain.tesoreria import apuntes_de_movimiento, pendiente, saldos_corridos
from conta_pridalac.migracion.mgd import cargar_mgd

pytestmark = pytest.mark.datos_reales


@pytest.fixture
def carga(sesion, carpeta_mgd_2021):
    res = cargar_mgd(sesion, carpeta_mgd_2021, codigo_empresa=11, nombre_empresa="Empresa A", anio=2021)
    sesion.commit()
    return res


def test_volumenes(carga):
    # 4 bancos (3 reales + compensación), 59 vencimientos, 43 movimientos, 43 pagos (38 con vencimiento, 3 directos, 2 pendientes)
    assert (carga.bancos, carga.vencimientos, carga.movimientos, carga.pagos) == (4, 59, 43, 43)
    assert carga.avisos == []


def test_el_pendiente_calculado_coincide_con_el_de_mgd(sesion, carga, carpeta_mgd_2021):
    from conta_pridalac.migracion.mgd import leer_dbf

    esperado = {v["NUMERO"]: Decimal(str(round(v["PENDIENTE"] or 0, 2))) for v in leer_dbf(carpeta_mgd_2021, "Vtos")}
    for v in sesion.scalars(select(Vencimiento)):
        assert pendiente(sesion, v) == esperado[v.numero_origen_mgd], v.numero_origen_mgd


def test_los_saldos_corridos_coinciden_con_el_saldo_nuevo(sesion, carga, carpeta_mgd_2021):
    from conta_pridalac.migracion.mgd import leer_dbf

    saldo_nue = {m["NUMERO"]: Decimal(str(round(m["SALDONUE"] or 0, 2))) for m in leer_dbf(carpeta_mgd_2021, "Movbanco")}
    comprobados = 0
    for banco in sesion.scalars(select(Banco)):
        for mov, saldo in saldos_corridos(sesion, banco):
            assert saldo == saldo_nue[mov.numero]
            comprobados += 1
    assert comprobados == 43


def test_saldo_contable_del_banco_es_saldo_inicial_mas_movimientos(sesion, carga):
    """Invariante de auditoría: saldo en el Diario de la cuenta del banco = saldo inicial + Σ movimientos."""
    for banco in sesion.scalars(select(Banco).where(Banco.clase == "B")):
        movs = sum(
            (p.importe for m in sesion.scalars(select(MovimientoBanco).where(MovimientoBanco.banco_id == banco.id)) for p in m.pagos),
            Decimal("0.00"),
        )
        debe, haber = sesion.execute(
            select(func.coalesce(func.sum(Apunte.debe), 0), func.coalesce(func.sum(Apunte.haber), 0)).where(
                Apunte.cuenta_id == banco.cuenta_id
            )
        ).one()
        assert Decimal(debe) - Decimal(haber) == banco.saldo_inicial + movs, banco.nombre


def test_el_asiento_regenerado_de_cada_movimiento_es_el_del_diario(sesion, carga):
    """Regla de oro (43/43): ListaPagos.Asiento reproduce las líneas tipo 3 del Diario."""
    for mov in sesion.scalars(select(MovimientoBanco)):
        esperado = apuntes_de_movimiento(sesion, mov)
        asiento = sesion.scalars(
            select(Asiento).where(Asiento.tipo == 3, Asiento.numero == mov.numero, Asiento.sub == 0)
        ).one()
        real = Counter()
        for ap in asiento.apuntes:
            real[ap.cuenta.codigo] += ap.debe - ap.haber
        real = Counter({c: v for c, v in real.items() if v != 0})
        assert esperado == real, f"movimiento {mov.numero}"


def test_hay_pagos_directos_y_pendientes_de_aplicar(sesion, carga):
    directos = sesion.scalar(
        select(func.count()).select_from(Pago).where(Pago.vencimiento_id.is_(None), Pago.cuenta_directa_id.is_not(None))
    )
    pendientes = sesion.scalar(
        select(func.count()).select_from(Pago).where(Pago.vencimiento_id.is_(None), Pago.cuenta_directa_id.is_(None))
    )
    assert (directos, pendientes) == (3, 2)
