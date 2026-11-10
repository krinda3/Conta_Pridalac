from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.plantillas import (
    aplicar_plantilla,
    evaluar_texto,
    fecha_de_vencimiento,
    leer_contenido,
    validar_plantilla,
)

D = Decimal

NOMINA = (
    "6400000|SUELDOS Y SALARIOS                                              |C|             0||\r\n"
    "4751000|H.P ACREED- RETENCIONES IRPF  |H|          0|D=25 M= A= PT|\r\n"
    "4760000|S.S. TRABAJADOR                                                 |H|0|D=31 M+1 A=|\r\n"
    "4650000|REMUNERACIONES PTES DE PAGO                                     |H|             0|D=31 M= A=|\r\n"
)


# ------------------------------------------------------------------------------------------ texto


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("NOMINA {mes}/{año}", "NOMINA 3/2026"),
        ("NOMINA {MES}/{AÑO}", "NOMINA 3/2026"),
        ("REGUL. IVA {trimestre} TRIM/{año}", "REGUL. IVA 1 TRIM/2026"),
        ("{cmes} {año}", "marzo 2026"),  # cmes en minúsculas → minúsculas (como MGD)
        ("{Cmes} {año}", "Marzo 2026"),
        ("{CMES}", "MARZO"),
        ("{mes-1}/{año}", "2/2026"),
        ("{año+1}", "2027"),
        ("{mes*2}", "6"),
        ("{cuatrimestre}º cuatrimestre", "1º cuatrimestre"),
        ("{cdia} {dia}", "jueves 5"),
        ("{Cdia}", "Jueves"),
        ("Sin marcas", "Sin marcas"),
        ("Llave {} suelta", "Llave { suelta"),
        ("Sin cerrar {mes", "Sin cerrar mes"),
        ("{algo raro}", "algo raro"),
    ],
)
def test_evaluar_texto(texto, esperado):
    assert evaluar_texto(texto, date(2026, 3, 5)) == esperado


def test_evaluar_texto_no_ejecuta_codigo():
    assert evaluar_texto("{__import__('os')}", date(2026, 3, 5)) == "__import__('os')"


# ------------------------------------------------------------------------------------------ fechas de vencimiento


@pytest.mark.parametrize(
    "modelo, base, esperado",
    [
        ("D= M= A=", date(2026, 3, 5), date(2026, 3, 5)),  # sin cambios
        ("D=25 M= A=", date(2026, 3, 5), date(2026, 3, 25)),
        ("D=25 M= A=", date(2026, 3, 30), date(2026, 4, 25)),  # el día ya ha pasado → mes siguiente
        ("D=25 M= A=", date(2026, 12, 30), date(2027, 1, 25)),
        ("D=31 M+1 A=", date(2026, 1, 15), date(2026, 2, 28)),  # día inexistente → fin de mes (supuesto)
        ("D=31 M= A=", date(2026, 4, 10), date(2026, 4, 30)),
        ("D+30 M= A=", date(2026, 1, 15), date(2026, 2, 14)),
        ("D+0 M+2 A=", date(2026, 11, 20), date(2027, 1, 20)),  # el mes cruza de año
        ("D= M= A+1", date(2026, 3, 5), date(2027, 3, 5)),
        ("D= M=6 A=2030", date(2026, 3, 5), date(2030, 6, 5)),
        ("D=25 M= A= PT", date(2026, 3, 31), date(2026, 4, 25)),  # 25 del primer mes del trimestre siguiente
        ("D=25 M= A= PT", date(2026, 11, 15), date(2027, 1, 25)),
        ("D= M= A= PT", date(2026, 5, 10), date(2026, 7, 1)),
        ("D= M= A= PM", date(2026, 3, 5), date(2026, 3, 11)),  # jueves → próximo miércoles
        ("D= M= A= PM", date(2026, 3, 11), date(2026, 3, 11)),  # ya es miércoles
        ("D= M= A= PL", date(2026, 3, 5), date(2026, 3, 9)),
        ("D=1 M+1 A= DP5,20", date(2026, 3, 1), date(2026, 4, 5)),
        ("D=1 M+1 A= DP12-", date(2026, 3, 1), date(2026, 4, 12)),
        ("D=1 M+1 A= DP-3", date(2026, 3, 1), date(2026, 4, 1)),
        # Particularidad de MGD: el día fijo se compara con el día de la fecha base ya con el mes cambiado,
        # así que `D=1 M+1` desde el día 10 da el día 1 del mes SIGUIENTE al siguiente.
        ("D=1 M+1 A=", date(2026, 3, 10), date(2026, 5, 1)),
    ],
)
def test_fecha_de_vencimiento(modelo, base, esperado):
    assert fecha_de_vencimiento(modelo, base) == esperado


@pytest.mark.parametrize("modelo", ["", "D=25", "D=25 M="])
def test_regla_incompleta_no_da_fecha(modelo):
    assert fecha_de_vencimiento(modelo, date(2026, 3, 5)) is None


# ------------------------------------------------------------------------------------------ plantillas


def test_leer_la_plantilla_de_nominas_de_mgd():
    lineas = leer_contenido(NOMINA)
    assert [(l.cuenta, l.dhc, l.importe) for l in lineas] == [
        ("6400000", "C", D("0")), ("4751000", "H", D("0")), ("4760000", "H", D("0")), ("4650000", "H", D("0"))
    ]
    assert lineas[1].ayuda == "H.P ACREED- RETENCIONES IRPF" and lineas[1].vencimientos == ["D=25 M= A= PT"]
    assert lineas[0].vencimientos == []


def test_importes_de_muestra_con_coma_y_miles():
    (l,) = leer_contenido("1000000|CAPITAL|H|1.234,50||")
    assert l.importe == D("1234.50")


def test_la_linea_de_cuadre_se_calcula():
    """Nómina: 1.500 bruto = 150 IRPF + 90 S.S. trabajador + 1.260 líquido; el gasto sale como cuadre por el Debe."""
    lineas = leer_contenido(NOMINA)
    r = aplicar_plantilla(lineas, [D("0"), D("150"), D("90"), D("1260")])
    assert [(x.cuenta, x.dh, x.importe) for x in r] == [
        ("6400000", "D", D("1500.00")), ("4751000", "H", D("150.00")), ("4760000", "H", D("90.00")), ("4650000", "H", D("1260.00"))
    ]
    assert sum(x.importe for x in r if x.dh == "D") == sum(x.importe for x in r if x.dh == "H")
    assert r[1].vencimientos == ("D=25 M= A= PT",)


def test_el_cuadre_sale_por_el_haber_si_sobra_debe():
    lineas = leer_contenido("5720000|BANCO|D|0||\r\n1000000|CAPITAL|C|0||")
    (banco, capital) = aplicar_plantilla(lineas, [D("500"), D("0")])
    assert (banco.dh, capital.dh, capital.importe) == ("D", "H", D("500.00"))


def test_importe_negativo_cambia_de_lado_y_el_cero_se_omite():
    lineas = leer_contenido("6290000|GASTO|D|0||\r\n4100001|PROVEEDOR|H|0||\r\n4720000|IVA|D|0||")
    r = aplicar_plantilla(lineas, [D("-100"), D("-100"), D("0")])
    assert [(x.cuenta, x.dh, x.importe) for x in r] == [("6290000", "H", D("100.00")), ("4100001", "D", D("100.00"))]


def test_no_mas_de_una_linea_de_cuadre():
    lineas = leer_contenido("1|A|C|0||\r\n2|B|C|0||")
    with pytest.raises(ErrorContable, match="2 apuntes de cuadre"):
        validar_plantilla(lineas)
    with pytest.raises(ErrorContable):
        validar_plantilla([])


def test_tipo_de_linea_invalido_y_numero_de_importes():
    with pytest.raises(ErrorContable, match="D, H o C"):
        leer_contenido("1000000|CAPITAL|X|0||")
    with pytest.raises(ErrorContable, match="2 líneas"):
        aplicar_plantilla(leer_contenido("1|A|D|0||\r\n2|B|C|0||"), [D("1")])
