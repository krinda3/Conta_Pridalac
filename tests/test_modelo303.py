"""Cálculo del modelo 303 desde los libros (casillas, compensación y bolsa de periodos anteriores)."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaIva
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.modelo303 import bolsa_de_periodos_anteriores, calcular_303, compensar, periodo_de_fechas

D = Decimal


def test_los_periodos_son_trimestres():
    assert periodo_de_fechas(2026, 1) == (date(2026, 1, 1), date(2026, 3, 31))
    assert periodo_de_fechas(2026, 4) == (date(2026, 10, 1), date(2026, 12, 31))
    with pytest.raises(ErrorContable):
        periodo_de_fechas(2026, 5)


# Casos reales de las declaraciones presentadas (Empresa B y Empresa A): (resultado del trimestre, periodo, bolsa) → (resultado de la liquidación, casilla 87)
@pytest.mark.parametrize(
    "resultado, periodo, bolsa, esperado",
    [
        (D("-406.25"), 2, D("0"), (D("-406.25"), D("0"))),  # negativo en 1T–3T: se presenta tal cual y la bolsa no cambia
        (D("-3726.83"), 2, D("4948.27"), (D("-3726.83"), D("4948.27"))),  # Empresa A 2023-2T: la 87 es la bolsa de antes
        (D("165.75"), 3, D("406.25"), (D("0"), D("240.50"))),  # Empresa B 2022-3T: positivo, se compensa hasta donde llega la bolsa
        (D("533.87"), 2, D("762.33"), (D("0"), D("228.46"))),  # Empresa B 2024-2T
        (D("810.05"), 2, D("603.79"), (D("206.26"), D("0"))),  # Empresa B 2023-2T: la bolsa se agota
        (D("-1078.32"), 4, D("10241.89"), (D("-11320.21"), D("0"))),  # Empresa A 2023-4T: el 4T arrastra toda la bolsa
        (D("3210.77"), 4, D("500.15"), (D("2710.62"), D("0"))),  # Empresa B 2023-4T
    ],
)
def test_compensacion_como_en_lo_presentado(resultado, periodo, bolsa, esperado):
    assert compensar(resultado, periodo, bolsa) == esperado


@pytest.fixture
def libro(sesion):
    emp = Empresa(codigo=1, nombre="E")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=emp)
    sesion.add_all([emp, ej])
    sesion.flush()
    cuenta = Cuenta(empresa_id=emp.id, codigo="62800000", nombre="G")
    sesion.add(cuenta)
    sesion.flush()

    def factura(sentido, numero, fecha, *lineas, deducible=True, bien=False):
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"F{numero}", total=D("0"),
                    cuenta_tercero_id=cuenta.id, cuenta_contrapartida_id=cuenta.id)
        for base, pct, cuota in lineas:
            f.ivas.append(FacturaIva(base=D(base), pct_iva=D(pct), cuota_iva=D(cuota), deducible=deducible, bien_inversion=bien))
        sesion.add(f)
        sesion.flush()
        return f

    return sesion, ej, factura


def test_calculo_de_un_trimestre(libro):
    sesion, ej, factura = libro
    factura("E", 1, date(2026, 7, 5), ("1000.00", "21", "210.00"), ("500.00", "10", "50.00"))
    factura("E", 2, date(2026, 8, 5), ("100.00", "4", "4.00"), ("300.00", "0", "0.00"))  # la línea al 0 % no va a ninguna casilla
    factura("E", 3, date(2026, 10, 1), ("999.00", "21", "209.79"))  # otro trimestre
    factura("R", 1, date(2026, 7, 9), ("200.00", "21", "42.00"), ("100.00", "10", "10.00"))
    factura("R", 2, date(2026, 9, 30), ("50.00", "21", "10.50"), deducible=False)  # IVA no deducible: fuera
    factura("R", 3, date(2026, 9, 1), ("1000.00", "21", "210.00"), bien=True)  # bien de inversión: casillas 30 y 31
    factura("R", 4, date(2026, 9, 2), ("-20.00", "21", "-4.20"))  # rectificativa: resta de la 28 y 29
    c = calcular_303(sesion, ej, 3)
    assert (c[1], c[3], c[4], c[6], c[7], c[9]) == (D("100.00"), D("4.00"), D("500.00"), D("50.00"), D("1000.00"), D("210.00"))
    assert c[27] == D("264.00")
    assert (c[28], c[29], c[30], c[31]) == (D("280.00"), D("47.80"), D("1000.00"), D("210.00"))
    assert (c[45], c[46], c[64], c[65], c[66]) == (D("257.80"), D("6.20"), D("6.20"), D("100.00"), D("6.20"))
    assert (c[69], c[71], c[87]) == (D("6.20"), D("6.20"), D("0.00"))
    assert [l.casilla for l in c.lineas if l.sentido == "R"].count(29) == 3


def test_rectificacion_de_periodos_anteriores_va_a_la_40_y_41_y_la_prorrata_es_manual(libro):
    sesion, ej, factura = libro
    f = factura("R", 1, date(2026, 5, 3), ("-20.00", "21", "-4.20"))
    factura("R", 2, date(2026, 5, 4), ("1000.00", "21", "210.00"))
    c = calcular_303(sesion, ej, 2, regularizacion_prorrata=D("-50.00"), rectifican={f.id})
    assert (c[40], c[41], c[28], c[29], c[44]) == (D("-20.00"), D("-4.20"), D("1000.00"), D("210.00"), D("-50.00"))
    assert c[45] == D("155.80") and c[46] == D("-155.80") and c[71] == D("-155.80")  # 210 − 4,20 − 50


def test_compensacion_con_lo_presentado_en_los_trimestres_anteriores(libro):
    sesion, ej, factura = libro
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=2, tipo=1, resultado_liquidacion=D("-300.00"), resultado=D("-300.00"), a_compensar=D("100.00")))
    sesion.flush()
    assert bolsa_de_periodos_anteriores(sesion, ej.empresa_id, 2026, 1) == D("0.00")
    assert bolsa_de_periodos_anteriores(sesion, ej.empresa_id, 2026, 3) == D("400.00")  # lo que ya venía (87) más lo negativo del 2T
    factura("E", 1, date(2026, 8, 5), ("1000.00", "21", "210.00"))
    c3 = calcular_303(sesion, ej, 3)
    assert (c3[46], c3[71], c3[87]) == (D("210.00"), D("0.00"), D("190.00"))  # se compensan 210 de los 400
    assert (c3[110], c3[78]) == (D("400.00"), D("210.00"))
    factura("E", 2, date(2026, 11, 5), ("1000.00", "21", "210.00"))
    c4 = calcular_303(sesion, ej, 4, bolsa=D("100.00"))
    assert (c4[46], c4[71], c4[87]) == (D("210.00"), D("110.00"), D("0.00"))
