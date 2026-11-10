"""Fichero del modelo 111 según el diseño oficial: estructura y reproducción byte a byte de los presentados."""
import glob
from decimal import Decimal
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero111 import Declaracion111, casillas_de, generar, leer

D = Decimal
RAIZ = Path(__file__).resolve().parents[1]


def declaracion(**kw):
    datos = dict(nif="B12345678", nombre="EMPRESA DE PRUEBA S.L.", ejercicio=2026, periodo="4T", tipo="U", iban="ES9121000418450200051332",
                 casillas={7: D("2"), 8: D("1500.00"), 9: D("30.00"), 28: D("30.00"), 30: D("30.00")})
    datos.update(kw)
    return Declaracion111(**datos)


def test_estructura_y_posiciones():
    t = generar(declaracion())
    assert len(t) == 1346 and t.startswith("<T111020264T0000><AUX>") and t.endswith("</T11101000></T111020264T0000>")
    campos = leer(t)
    assert campos[6] == "U" and campos[7] == "B12345678" and campos[10] == "2026" and campos[11] == "4T"
    assert campos[18] == "00000002" and campos[19] == "00000000000150000" and campos[20] == "00000000000003000" and campos[41] == "00000000000003000"
    assert campos[45].strip() == "ES9121000418450200051332" and campos[42] == " "
    assert casillas_de(t) == {7: D("2"), 8: D("1500.00"), 9: D("30.00"), 28: D("30.00"), 30: D("30.00")}


def test_sin_actividad_va_toda_a_cero_y_sin_iban():
    t = generar(declaracion(tipo="N", casillas={}, iban="IGNORADO"))
    assert casillas_de(t) == {} and leer(t)[45] == " " * 34 and leer(t)[6] == "N"


def test_resultado_de_anteriores_declaraciones_admite_signo():
    t = generar(declaracion(casillas={28: D("30.00"), 29: D("-10.00"), 30: D("40.00")}))
    assert leer(t)[40] == "N0000000000001000" and casillas_de(t)[29] == D("-10.00")


def test_complementaria_lleva_el_justificante_anterior():
    t = generar(declaracion(complementaria=True, justificante_anterior="3037084443540"))
    assert leer(t)[42] == "X" and leer(t)[43] == "3037084443540"
    with pytest.raises(ErrorContable, match="justificante"):
        generar(declaracion(complementaria=True))


@pytest.mark.parametrize("cambios", [dict(tipo="Z"), dict(iban=""), dict(casillas={99: D("1")}), dict(casillas={7: D("-1")}), dict(nombre="X" * 61)])
def test_datos_incorrectos_se_rechazan(cambios):
    with pytest.raises(ErrorContable):
        generar(declaracion(**cambios))


@pytest.mark.parametrize("ruta", sorted(glob.glob(str(RAIZ / "AEAT" / "C000[12]_111_*.111"))) or [None])
def test_reproduce_byte_a_byte_los_ficheros_presentados(ruta):
    if ruta is None:
        pytest.skip("no están los ficheros de AEAT/ (no se versionan)")
    texto = Path(ruta).read_text(encoding="latin-1")
    c = leer(texto)
    d = Declaracion111(
        nif=c[7].strip(), nombre=c[8].strip(), ejercicio=int(c[10]), periodo=c[11], tipo=c[6], casillas=casillas_de(texto), iban=c[45].strip(),
        version_programa=texto[92:96].strip(), nif_desarrollador=texto[100:109].strip(),
    )
    assert generar(d) == texto
