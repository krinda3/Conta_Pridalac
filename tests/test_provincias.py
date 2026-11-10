"""Códigos de provincia de la AEAT."""
import pytest

from conta_pridalac.ficheros_aeat.provincias import PROVINCIAS, codigo_de_provincia


def test_la_lista_tiene_las_53_de_la_aeat():
    assert len(PROVINCIAS) == 53 and PROVINCIAS["28"] == "MADRID" and PROVINCIAS["13"] == "CIUDAD REAL"


@pytest.mark.parametrize("cp,nombre,esperado", [
    ("28015", None, "28"), ("13001", "MADRID", "13"), (None, "Ciudad Real", "13"), (None, "CIUDAD REAL", "13"), (None, "Alicante/Alacant", "03"), (None, "VIZCAYA", "48"), (None, "Coruña, A", "15"),
    (None, "La Rioja", "26"), (None, "S.C. Tenerife", "38"), ("99999", "Toledo", "45"), (" ", None, None), ("1300", None, None), (None, "Narnia", None),
])
def test_codigo_de_provincia(cp, nombre, esperado):
    assert codigo_de_provincia(cp, nombre) == esperado
