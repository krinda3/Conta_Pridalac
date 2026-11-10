"""Carga de la BBDD 2021 de Empresa A (empresa 011) y comprobaciones de integridad.

Se omite si los datos no están. Las cifras esperadas salen de las tablas originales (ver docs/pseudocodigo/01).
"""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.integridad import (
    apuntes_en_cuentas_de_grupo,
    asientos_descuadrados,
    huecos_numeracion_diario,
)
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Factura, FacturaAjuste, FacturaIva
from conta_pridalac.migracion.mgd import cargar_mgd

pytestmark = pytest.mark.datos_reales


@pytest.fixture
def carga(sesion, carpeta_mgd_2021):
    res = cargar_mgd(sesion, carpeta_mgd_2021, codigo_empresa=11, nombre_empresa="Empresa A", anio=2021)
    sesion.commit()
    return res


def test_volumenes(carga):
    assert carga.cuentas == 759
    assert carga.terceros == 3 + 102
    assert carga.asientos == 103
    assert carga.apuntes == 391 - 103  # 391 líneas en Diario, 103 son cabeceras sin cuenta
    assert carga.facturas == 56 + 1
    assert carga.avisos == []


def test_el_diario_cuadra(sesion, carga):
    assert asientos_descuadrados(sesion, carga.ejercicio_id) == []
    debe, haber = sesion.execute(
        select(func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == carga.ejercicio_id)
    ).one()
    assert debe == haber


def test_todo_apunte_va_a_una_subcuenta(sesion, carga):
    assert apuntes_en_cuentas_de_grupo(sesion, carga.ejercicio_id) == []
    assert not sesion.scalars(select(Cuenta).where(func.length(Cuenta.codigo) != 8)).all()


def test_numeracion_del_diario(sesion, carga):
    """MGD deja huecos en la numeración (103 asientos, hasta el 106): se conservan, no se rellenan."""
    maximo = sesion.scalar(select(func.max(Asiento.numero_diario)).where(Asiento.ejercicio_id == carga.ejercicio_id))
    assert maximo == 106
    assert len(huecos_numeracion_diario(sesion, carga.ejercicio_id)) == 106 - 103


def test_tipos_de_asiento(sesion, carga):
    cuentas = dict(
        sesion.execute(
            select(Asiento.tipo, func.count()).where(Asiento.ejercicio_id == carga.ejercicio_id).group_by(Asiento.tipo)
        ).all()
    )
    assert set(cuentas) <= {1, 2, 3, 4, 9}
    assert sum(cuentas.values()) == 103


def test_el_asiento_de_apertura_es_el_numero_1(sesion, carga):
    apertura = sesion.scalars(
        select(Asiento).where(Asiento.ejercicio_id == carga.ejercicio_id, Asiento.subtipo == "A")
    ).one()
    assert apertura.numero_diario == 1
    assert apertura.tipo == 9
    assert str(apertura.fecha) == "2021-01-01"


def test_facturas_iva_y_ajustes(sesion, carga):
    assert sesion.scalar(select(func.count()).select_from(FacturaIva)) == 57
    ajuste = sesion.scalars(select(FacturaAjuste)).one()
    assert ajuste.importe == Decimal("-108.75")
    assert ajuste.factura.sentido == "R" and ajuste.factura.numero == 23
    # el total de cada factura recibida es el que trae MGD
    recibida = sesion.scalars(select(Factura).where(Factura.sentido == "R", Factura.numero == 1)).one()
    assert recibida.total == Decimal("539.00")
