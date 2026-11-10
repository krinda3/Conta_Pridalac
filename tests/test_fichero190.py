"""Fichero del modelo 190: estructura y reproducción byte a byte de los presentados desde el programa anterior."""
from decimal import Decimal
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero190 import Declaracion190, Percepcion190, generar, leer, limpiar

D = Decimal
RAIZ = Path(__file__).resolve().parents[1]
PRESENTADOS = sorted((RAIZ / "AEAT").glob("C000[12]_190_*.190"))  # no están en el repositorio: sin ellos, esos tests no se ejecutan


def declaracion(**kw):
    datos = dict(nif="B12345678", nombre="EMPRESA DE PRUEBA S.L.", ejercicio=2025, contacto_telefono="600111222", contacto_nombre="PEREZ GOMEZ ANA", identificativo="1900012345678",
                 percepciones=[Percepcion190("12345678Z", "PEREZ GOMEZ ANA", "28", "H", "03", D("1904.00"), D("38.08"))])
    datos.update(kw)
    return Declaracion190(**datos)


def test_estructura_y_posiciones():
    t = generar(declaracion())
    r1, r2, resto = t.split("\r\n")
    assert resto == "" and len(r1) == len(r2) == 500
    assert r1[:17] == "11902025B12345678" and r1[57] == "T" and r1[135:144] == "000000001" and r1[144:160] == " 000000000190400" and r1[160:175] == "000000000003808"
    assert r2[:17] == "21902025B12345678" and r2[17:26] == "12345678Z" and r2[26:35] == " " * 9
    assert r2[75:80] == "28H03" and r2[81:94] == "0000000190400" and r2[94:107] == "0000000003808" and len(r2.rstrip()) == 394


def test_leer_devuelve_lo_generado():
    d = declaracion()
    assert leer(generar(d)) == d


def test_sin_percepciones_solo_lleva_el_registro_de_declarante():
    assert len(generar(declaracion(percepciones=[]))) == 502


def test_los_nombres_se_limpian():
    assert limpiar("García Núñez, José") == "GARCIA NUÑEZ, JOSE"


def test_errores():
    with pytest.raises(ErrorContable, match="todavía no está implementada"):
        generar(declaracion(percepciones=[Percepcion190("12345678Z", "X", "28", "A", "01", D("1"), D("0"))]))
    with pytest.raises(ErrorContable, match="no cabe"):
        generar(declaracion(nombre="X" * 41))
    with pytest.raises(ErrorContable, match="identificativo de la anterior"):
        generar(declaracion(sustitutiva=True))
    with pytest.raises(ErrorContable, match="sin signo"):
        generar(declaracion(percepciones=[Percepcion190("12345678Z", "X", "28", "H", "03", D("-1"), D("0"))]))


@pytest.mark.skipif(not PRESENTADOS, reason="no están los ficheros presentados en AEAT/")
@pytest.mark.parametrize("ruta", PRESENTADOS, ids=lambda r: r.name)
def test_reproduce_byte_a_byte_lo_presentado(ruta):
    original = ruta.read_bytes().decode("latin-1")
    assert generar(leer(original)) == original
