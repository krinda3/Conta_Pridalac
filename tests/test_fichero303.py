"""Fichero del modelo 303 según el diseño oficial de la AEAT (2026)."""
import glob
from decimal import Decimal
from pathlib import Path

import pytest

from conta_pridalac.ficheros_aeat import fichero303 as F
from conta_pridalac.ficheros_aeat.fichero303 import Declaracion303, generar, leer, tipo_de_declaracion
from conta_pridalac.domain.errores import ErrorContable

D = Decimal
RAIZ = Path(__file__).resolve().parents[1]


def declaracion(periodo="2T", **kw):
    datos = dict(nif="B12345678", nombre="EMPRESA DE PRUEBA S.L.", ejercicio=2026, periodo=periodo, tipo="U", iban="ES9121000418450200051332",
                 casillas={7: D("1000.00"), 9: D("210.00"), 27: D("210.00"), 28: D("500.00"), 29: D("105.00"), 45: D("105.00"), 46: D("105.00"), 64: D("105.00"),
                           65: D("100.00"), 66: D("105.00"), 69: D("105.00"), 71: D("105.00")})
    datos.update(kw)
    return Declaracion303(**datos)


def test_las_paginas_miden_lo_que_dice_el_diseno_y_cada_casilla_va_a_su_sitio():
    t = generar(declaracion())
    assert len(t) == 3767  # 346 (cabecera y cierre) + 1581 + 1017 + 823
    assert t.startswith("<T303020262T0000><AUX>") and t.endswith("</T303DID00></T303020262T0000>")
    p1, p3 = leer(t)["01000"], leer(t)["03000"]
    assert p1[14] == "B12345678" and p1[107] == "2T" and p1[103] == "2026" and p1[13] == "U"
    assert p1[326] == "00000000000100000" and p1[343] == "02100" and p1[348] == "00000000000021000"  # casillas 7, 8 (tipo fijo) y 9
    assert p3[216] == "10000"  # casilla 65: 100,00 %
    assert leer(t)["DID00"][23].strip() == "ES9121000418450200051332"


def test_el_4t_lleva_la_pagina_4():
    assert len(generar(declaracion("4T"))) == 3767 + 998
    assert "<T30304000>" in generar(declaracion("4T")) and "<T30304000>" not in generar(declaracion("3T"))


def test_negativos_con_n_al_principio():
    t = generar(declaracion(tipo="C", iban="", casillas={46: D("-155.27"), 71: D("-155.27")}))
    assert leer(t)["01000"][1019] == "N0000000000015527"
    assert leer(t)["03000"][408] == "N0000000000015527"


def test_casilla_que_no_existe_o_tipo_desconocido_se_rechazan():
    with pytest.raises(ErrorContable):
        generar(declaracion(casillas={999: D("1")}))
    with pytest.raises(ErrorContable):
        generar(declaracion(tipo="Z"))
    with pytest.raises(ErrorContable):
        generar(declaracion(nombre="X" * 81))


def test_tipo_de_declaracion():
    assert tipo_de_declaracion(D("-5"), domiciliar=True) == "C"
    assert tipo_de_declaracion(D("0"), domiciliar=True) == "N"
    assert tipo_de_declaracion(D("5"), domiciliar=True) == "U"
    assert tipo_de_declaracion(D("5"), domiciliar=False) == "I"


def _casillas_de(texto):
    out = {}
    for pagina, valores in leer(texto).items():
        for c in F.DISENO[F.PAGINAS[pagina]]:
            if c["casilla"] and c["tipo"].upper() in ("NUM", "N") and "Tipo %" not in c["desc"]:
                v = valores[c["pos"]]
                n = D(v.replace("N", "0")) / 100
                if n:
                    out[c["casilla"]] = -n if v.startswith("N") else n
    return out


@pytest.mark.parametrize("ruta", sorted(glob.glob(str(RAIZ / "AEAT" / "C000[12]_303_2026_*.303"))) or [None])
def test_reproduce_byte_a_byte_los_ficheros_presentados_en_2026(ruta):
    if ruta is None:
        pytest.skip("no están los ficheros de AEAT/ (no se versionan)")
    texto = Path(ruta).read_text(encoding="latin-1")
    p = leer(texto)
    d = Declaracion303(
        nif=p["01000"][14].strip(), nombre=p["01000"][23].strip(), ejercicio=int(p["01000"][103]), periodo=p["01000"][107], tipo=p["01000"][13],
        casillas=_casillas_de(texto), iban=p["DID00"][23].strip(), sepa=p["DID00"][194], version_programa=texto[92:96].strip(), nif_desarrollador=texto[100:109].strip(),
    )
    assert generar(d) == texto


def test_contenido_legible_de_un_fichero_generado():
    from conta_pridalac.ficheros_aeat.fichero303 import contenido_legible

    d = declaracion("2T", rectificativa=True, justificante_anterior="3037084443540", casillas={**declaracion().casillas, 70: D("100.00"), 111: D("20.00"), 71: D("-20.00")})
    datos, casillas = contenido_legible(generar(d))
    assert dict(datos)["Tipo de declaración"] == "U" and dict(datos)["Justificante de la anterior"] == "3037084443540" and dict(datos)["NIF"] == "B12345678"
    assert dict(datos)["Ejercicio y periodo"] == "2026 2T" and dict(datos)["IBAN"] == "ES9121000418450200051332"
    assert casillas[7] == D("1000.00") and casillas[70] == D("100.00") and casillas[111] == D("20.00") and casillas[71] == D("-20.00") and 2 not in casillas
