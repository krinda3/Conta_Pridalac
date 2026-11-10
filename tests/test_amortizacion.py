from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Apunte, Asiento, BienInversion
from conta_pridalac.domain.amortizacion import generar_cuadro, suma_meses
from conta_pridalac.migracion.mgd import cargar_mgd, parsear_cuadro_mgd


def test_suma_meses_ajusta_fin_de_mes():
    assert suma_meses(date(2021, 1, 31), 1) == date(2021, 2, 28)
    assert suma_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert suma_meses(date(2014, 4, 15), 12 * 25) == date(2039, 4, 15)
    assert suma_meses(date(2021, 1, 1), -1) == date(2020, 12, 1)


def test_cuadro_de_un_bien_de_25_anios():
    """Terreno adaptado: 1.100 €, 25 años, desde el 15/04/2014 → 31,46 el primer año (261/365 de 44) y 44 después."""
    c = generar_cuadro(date(2014, 4, 15), Decimal("1100"), Decimal("0"), 25, 12)
    assert (c[0].desde, c[0].hasta, c[0].previsto) == (date(2014, 4, 15), date(2014, 12, 31), Decimal("31.46"))
    assert all(p.previsto == Decimal("44.00") for p in c[1:-1])
    assert c[-1].hasta == date(2039, 4, 14)
    assert sum(p.previsto for p in c) == Decimal("1100")


def test_el_cuadro_es_continuo_y_suma_el_importe_neto():
    c = generar_cuadro(date(2016, 3, 10), Decimal("1100"), Decimal("100"), 10, 12)
    for anterior, siguiente in zip(c, c[1:]):
        assert (siguiente.desde - anterior.hasta).days == 1
    assert sum(p.previsto for p in c) == Decimal("1000")


@pytest.mark.parametrize("coste, vida", [("0", 5), ("100", 0)])
def test_cuadro_rechaza_datos_invalidos(coste, vida):
    with pytest.raises(ValueError):
        generar_cuadro(date(2020, 1, 1), Decimal(coste), Decimal("0"), vida, 12)


def test_parsear_cuadro():
    texto = "2014·15/04/14·31/12/14·31,46·M·31,46\r\n2015·01/01/15·31/12/15·1.044,00·M·0,00"
    filas = parsear_cuadro_mgd(texto)
    assert filas[0] == (2014, date(2014, 4, 15), date(2014, 12, 31), Decimal("31.46"), "M", "31,46")
    assert filas[1][3] == Decimal("1044.00")
    assert parsear_cuadro_mgd("") == [] and parsear_cuadro_mgd(None) == []


# ---- Con datos reales (MGD 2021) --------------------------------------------------------------------------


@pytest.fixture
def carga(sesion, carpeta_mgd_2021):
    res = cargar_mgd(sesion, carpeta_mgd_2021, codigo_empresa=11, nombre_empresa="Empresa A", anio=2021)
    sesion.commit()
    return res


@pytest.mark.datos_reales
def test_los_22_cuadros_de_mgd_se_regeneran_identicos(sesion, carga):
    bienes = sesion.scalars(select(BienInversion)).all()
    assert carga.bienes == len(bienes) == 22
    for b in bienes:
        generado = generar_cuadro(
            b.fecha_funcionamiento,
            b.precio_compra,
            b.valor_residual,
            b.periodos_vida or 0,
            b.meses_periodo,
            b.coeficiente_pct or Decimal("0"),
            b.fecha_baja,
        )
        guardado = [(a.desde, a.hasta, a.importe_previsto) for a in b.amortizaciones]
        assert [(p.desde, p.hasta, p.previsto) for p in generado] == guardado, b.descripcion


@pytest.mark.datos_reales
def test_amortizacion_acumulada_a_2020_cuadra_con_la_apertura_salvo_el_tractor(sesion, carga):
    """Σ amortizado hasta 2020 por cuenta de amortización acumulada = saldo de apertura de 2021.

    Excepción conocida de los datos: el tractor (28130001, MGD 2813001; el mismo código que en la apertura de 2022 del programa anterior) tiene 110,00 € más en la contabilidad que en el cuadro
    (un año de amortización sin reflejar en el cuadro). Es el tipo de incoherencia que debe detectar la auditoría.
    """
    del carga
    por_cuenta: dict[str, Decimal] = defaultdict(Decimal)
    for b in sesion.scalars(select(BienInversion)):
        por_cuenta[b.cuenta_amortizacion.codigo] += sum(
            (a.importe_contable for a in b.amortizaciones if a.anio <= 2020 and a.importe_contable), Decimal("0")
        )
    apertura: dict[str, Decimal] = defaultdict(Decimal)
    for ap in sesion.scalars(select(Apunte).join(Asiento).where(Asiento.subtipo == "A")):
        apertura[ap.cuenta.codigo] += ap.haber - ap.debe
    distintas = {c: apertura[c] - v for c, v in por_cuenta.items() if apertura[c] != v}
    assert distintas == {"28130001": Decimal("110.00")}
    assert len(por_cuenta) == 8
