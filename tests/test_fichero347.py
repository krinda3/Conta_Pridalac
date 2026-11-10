"""Fichero del modelo 347: estructura y reproducción byte a byte de los presentados desde el programa anterior."""
from decimal import Decimal
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero347 import Declarado347, Declaracion347, generar, leer

D = Decimal
RAIZ = Path(__file__).resolve().parents[1]
PRESENTADOS = sorted((RAIZ / "AEAT").glob("C000[12]_347_*.347"))  # no están en el repositorio: sin ellos, esos tests no se ejecutan


def declaracion(**kw):
    datos = dict(nif="B12345678", nombre="EMPRESA DE PRUEBA S.L.", ejercicio=2025, contacto_telefono="600111222", contacto_nombre="PEREZ GOMEZ ANA", identificativo="3470012345678",
                 declarados=[Declarado347("12345678Z", "AGRICULTOR UNO", "13", "A", [D("0"), D("1500.25"), D("0"), D("-100.00")]),
                             Declarado347("B23365448", "BELMO MUEBLES Y HOGAR", "13", "B", [D("0"), D("0"), D("0"), D("503.77")])])
    datos.update(kw)
    return Declaracion347(**datos)


def test_estructura_y_posiciones():
    r1, r2, r3, resto = generar(declaracion()).split("\r\n")
    assert resto == "" and len(r1) == len(r2) == len(r3) == 500
    assert r1[:17] == "13472025B12345678" and r1[57] == "T" and r1[135:144] == "000000002" and r1[144:160] == " 000000000190402" and r1[160:185] == "000000000" + " 000000000000000"
    assert r2[:35] == "23472025B1234567812345678Z" + " " * 9 and r2[75:82] == "D13   A"
    assert r2[82:98] == " 000000000140025" and r2[135:151] == " 000000000000000"  # anual y 1T
    assert r2[167:183] == " 000000000150025" and r2[231:247] == "N000000000010000"
    assert r2[283:305] == " " + "0" * 15 + "0" * 6 and r2[305:] == " " * 195


def test_antes_de_2025_no_lleva_la_zona_de_bdns():
    r2 = generar(declaracion(ejercicio=2024)).split("\r\n")[1]
    assert r2[283:299] == " " + "0" * 15 and r2[299:] == " " * 201


def test_leer_devuelve_lo_generado():
    d = declaracion()
    assert leer(generar(d)) == d


def test_el_anual_es_la_suma_de_los_trimestres_y_el_total_la_de_los_declarados():
    d = declaracion()
    assert [p.anual for p in d.declarados] == [D("1400.25"), D("503.77")] and d.total == D("1904.02")


def test_sin_declarados_solo_lleva_la_cabecera():
    assert len(generar(declaracion(declarados=[]))) == 502


def test_errores():
    with pytest.raises(ErrorContable, match="Clave de operación"):
        generar(declaracion(declarados=[Declarado347("12345678Z", "X", "13", "C")]))
    with pytest.raises(ErrorContable, match="no cabe"):
        generar(declaracion(nombre="X" * 41))
    with pytest.raises(ErrorContable, match="identificativo de la anterior"):
        generar(declaracion(sustitutiva=True))
    with pytest.raises(ErrorContable, match="NIF no válido"):
        generar(declaracion(declarados=[Declarado347("1", "X", "13", "A")]))


@pytest.mark.skipif(not PRESENTADOS, reason="no están los ficheros presentados en AEAT/")
@pytest.mark.parametrize("ruta", PRESENTADOS, ids=lambda r: r.name)
def test_reproduce_byte_a_byte_lo_presentado(ruta):
    original = ruta.read_bytes().decode("latin-1")
    assert generar(leer(original)) == original
