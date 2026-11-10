"""Fichero del modelo 115 según el diseño oficial (DR115e15v13): estructura y posiciones."""
from decimal import Decimal

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero115 import DISENO, Declaracion115, casillas_de, contenido_legible, generar, leer

D = Decimal


def declaracion(**kw):
    datos = dict(nif="G12345678", nombre="ASOCIACION DE PRUEBA", ejercicio=2026, periodo="4T", tipo="U", iban="ES9121000418450200051332",
                 casillas={1: D("2"), 2: D("1500.00"), 3: D("285.00"), 5: D("285.00")})
    datos.update(kw)
    return Declaracion115(**datos)


def test_el_diseno_tiene_500_posiciones_y_las_cinco_casillas():
    assert DISENO[-1]["pos"] + DISENO[-1]["lon"] - 1 == 500
    assert {c["casilla"] for c in DISENO if c["casilla"]} == {1, 2, 3, 4, 5}


def test_estructura_y_posiciones():
    t = generar(declaracion())
    assert len(t) == 846 and t.startswith("<T115020264T0000><AUX>") and t.endswith("</T11501000></T115020264T0000>")
    campos = leer(t)
    assert campos[6] == "U" and campos[7] == "G12345678" and campos[10] == "2026" and campos[11] == "4T"
    assert campos[12] == "000000000000002" and campos[13] == "00000000000150000" and campos[14] == "00000000000028500" and campos[16] == "00000000000028500"
    assert campos[19].strip() == "ES9121000418450200051332" and campos[17] == " "
    assert casillas_de(t) == {1: D("2"), 2: D("1500.00"), 3: D("285.00"), 5: D("285.00")}


def test_sin_actividad_va_toda_a_cero_y_sin_iban():
    t = generar(declaracion(tipo="N", casillas={}, iban="IGNORADO"))
    assert casillas_de(t) == {} and leer(t)[19] == " " * 34 and leer(t)[6] == "N"


def test_complementaria_lleva_el_justificante_anterior():
    t = generar(declaracion(complementaria=True, justificante_anterior="1157084443540", casillas={3: D("100.00"), 4: D("40.00"), 5: D("60.00")}))
    assert leer(t)[17] == "X" and leer(t)[18] == "1157084443540" and casillas_de(t)[4] == D("40.00")
    with pytest.raises(ErrorContable, match="justificante"):
        generar(declaracion(complementaria=True))


@pytest.mark.parametrize("cambios", [dict(tipo="Z"), dict(iban=""), dict(casillas={99: D("1")}), dict(casillas={1: D("-1")}), dict(nombre="X" * 61)])
def test_datos_incorrectos_se_rechazan(cambios):
    with pytest.raises(ErrorContable):
        generar(declaracion(**cambios))


def test_contenido_legible():
    datos, casillas = contenido_legible(generar(declaracion()))
    assert ("NIF", "G12345678") in datos and casillas[3] == D("285.00")
