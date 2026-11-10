from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.integridad import asientos_descuadrados
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa
from conta_pridalac.domain.errores import (
    AsientoDescuadrado,
    CuentaNoAdmiteApuntes,
    EjercicioCerrado,
    FechaFueraDePeriodo,
)
from conta_pridalac.servicios.asientos import LineaAsiento, borrar_asiento, buscar_asiento, grabar_asiento, reducir

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62900000", "OTROS SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("41000186", "IDV"), ("57200001", "BANCO"), ("621", "ARRENDAMIENTOS (grupo)")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return ej


def factura_itv(importe_tasa="4.18"):
    return [
        LineaAsiento("62900000", D("30.38")),
        LineaAsiento("62900000", D(importe_tasa)),
        LineaAsiento("47200000", D("6.39")),
        LineaAsiento("41000186", D("-40.95")),
    ]


def test_reducir_agrupa_por_cuenta_y_quita_ceros():
    lineas = reducir(
        [LineaAsiento("A", D("10")), LineaAsiento("B", D("-10")), LineaAsiento("A", D("5")), LineaAsiento("B", D("-5")), LineaAsiento("C", D("0"))]
    )
    assert [(l.cuenta, l.importe) for l in lineas] == [("A", D("15.00")), ("B", D("-15.00"))]


def test_graba_un_asiento_cuadrado_con_debe_antes_que_haber(sesion, ej):
    a = grabar_asiento(sesion, ej, tipo=2, numero=194, fecha=date(2026, 9, 30), lineas=factura_itv(), concepto="ITV")
    assert a.numero_diario == 1
    assert [(ap.cuenta.codigo, ap.debe, ap.haber) for ap in a.apuntes] == [
        ("62900000", D("34.56"), D("0.00")),  # 30,38 + 4,18 agrupados
        ("47200000", D("6.39"), D("0.00")),
        ("41000186", D("0.00"), D("40.95")),
    ]
    assert asientos_descuadrados(sesion, ej.id) == []


def test_no_graba_el_asiento_descuadrado_de_la_factura_2_194(sesion, ej):
    """El caso real del programa anterior: la tasa de 4,18 € sin imputar deja el asiento descuadrado → aquí no se puede grabar."""
    lineas = [LineaAsiento("62900000", D("30.38")), LineaAsiento("47200000", D("6.39")), LineaAsiento("41000186", D("-40.95"))]
    with pytest.raises(AsientoDescuadrado, match="diferencia -4.18"):
        grabar_asiento(sesion, ej, tipo=2, numero=194, fecha=date(2026, 9, 30), lineas=lineas)
    assert buscar_asiento(sesion, ej, 2, 194) is None


def test_rechaza_cuentas_inexistentes_y_de_grupo(sesion, ej):
    with pytest.raises(CuentaNoAdmiteApuntes, match="no existe"):
        grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("99999999", D("1")), LineaAsiento("57200001", D("-1"))])
    with pytest.raises(CuentaNoAdmiteApuntes, match="de grupo"):
        grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("621", D("1")), LineaAsiento("57200001", D("-1"))])


def test_rechaza_fecha_fuera_de_ejercicio_y_ejercicio_cerrado(sesion, ej):
    with pytest.raises(FechaFueraDePeriodo):
        grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2025, 12, 31), lineas=factura_itv())
    ej.cerrado = True
    with pytest.raises(EjercicioCerrado):
        grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 5), lineas=factura_itv())


def test_grabar_dos_veces_es_idempotente_y_conserva_el_numero_de_diario_y_los_textos(sesion, ej):
    grabar_asiento(sesion, ej, tipo=2, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D("10"), "gasto A", "F-1"), LineaAsiento("41000186", D("-10"))])
    segundo = grabar_asiento(sesion, ej, tipo=2, numero=2, fecha=date(2026, 1, 6), lineas=[LineaAsiento("62900000", D("20")), LineaAsiento("41000186", D("-20"))])
    assert segundo.numero_diario == 2
    # se regenera el primero con otros importes: mismo número de diario y mismos textos por cuenta
    primero = grabar_asiento(sesion, ej, tipo=2, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D("12")), LineaAsiento("41000186", D("-12"))])
    assert primero.numero_diario == 1
    gasto = next(a for a in primero.apuntes if a.cuenta.codigo == "62900000")
    assert (gasto.debe, gasto.concepto, gasto.documento) == (D("12.00"), "gasto A", "F-1")
    assert len(sesion.scalars(select(Asiento)).all()) == 2
    assert len(sesion.scalars(select(Apunte)).all()) == 4


def test_un_asiento_que_se_reduce_a_cero_se_borra(sesion, ej):
    grabar_asiento(sesion, ej, tipo=2, numero=1, fecha=date(2026, 1, 5), lineas=factura_itv())
    assert grabar_asiento(sesion, ej, tipo=2, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D("0"))]) is None
    assert buscar_asiento(sesion, ej, 2, 1) is None


def test_el_numero_de_diario_no_se_recompacta_al_borrar(sesion, ej):
    for n in (1, 2, 3):
        grabar_asiento(sesion, ej, tipo=2, numero=n, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D("1")), LineaAsiento("41000186", D("-1"))])
    assert borrar_asiento(sesion, ej, 2, 2)
    nuevo = grabar_asiento(sesion, ej, tipo=2, numero=4, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D("1")), LineaAsiento("41000186", D("-1"))])
    assert nuevo.numero_diario == 4  # el hueco del 2 se queda como hueco
    assert not borrar_asiento(sesion, ej, 2, 99)


def test_agrupar_false_respeta_las_lineas_de_un_asiento_manual(sesion, ej):
    a = grabar_asiento(
        sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 5), agrupar=False,
        lineas=[LineaAsiento("62900000", D("5")), LineaAsiento("62900000", D("5")), LineaAsiento("41000186", D("-10"))],
    )
    assert len(a.apuntes) == 3
