"""Formato del fichero del modelo 200: el diseño cubre cada página sin huecos, los campos se leen y se escriben como los escribe la AEAT, y los `.200` presentados de 2025 se reproducen byte a byte."""
from decimal import Decimal
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero200 as f200
from conta_pridalac.ficheros_aeat.fichero200 import Fichero200, Pagina

D = Decimal
AEAT = Path(__file__).resolve().parents[1] / "AEAT"  # los ficheros reales no están en el repositorio


def test_el_diseno_cubre_cada_pagina_sin_huecos_ni_solapes():
    assert len(f200.DISENO["paginas"]) == 41
    for codigo, p in f200.DISENO["paginas"].items():
        fin = 1
        for c in sorted(p["campos"], key=lambda c: c["pos"]):
            assert c["pos"] == fin, f"página {codigo}: el campo {c['n']} empieza en {c['pos']} y debía hacerlo en {fin}"
            fin += c["lon"]
        assert fin - 1 == f200.longitud_de_pagina(codigo)


def test_una_pagina_nueva_lleva_sus_constantes_y_el_resto_en_blanco_o_cero():
    p = Pagina.nueva("14000")
    texto = p.escribir()
    assert texto.startswith("<T20014000>") and texto.endswith("</T20014000>") and len(texto) == f200.longitud_de_pagina("14000") == 1180
    assert p.importe(p.n_de_casilla(552)) == 0 and not p.complementaria
    assert Pagina.nueva("02B00", complementaria=True).complementaria


def test_los_importes_se_escriben_en_centimos_con_la_n_de_los_negativos():
    p = Pagina.nueva("14000")
    n = p.n_de_casilla(552)
    p.poner_importe(n, D("-14532.46"))
    assert p.valores[n] == "N0000000001453246" and p.importe(n) == D("-14532.46")
    p.poner_importe(n, D("1038.90"))
    assert p.valores[n] == "00000000000103890" and p.importe(n) == D("1038.90")
    n_num = p.n_de_casilla(562)  # la cuota íntegra es un `Num`: sin signo
    p.poner_importe(n_num, D("259.73"))
    assert p.valores[n_num] == "00000000000025973" and p.importe(n_num) == D("259.73")
    with pytest.raises(ErrorContable, match="no admite negativos"):
        p.poner_importe(n_num, D("-1"))


def test_los_textos_se_alinean_a_la_izquierda_y_se_validan():
    p = Pagina.nueva("01000")
    p.poner_texto(7, "B00000010")
    assert p.valores[7] == "B00000010" and p.texto(7) == "B00000010"
    p.poner_texto(8, "EMPRESA A S.L.")
    assert p.valores[8] == "EMPRESA A S.L.".ljust(80)
    with pytest.raises(ErrorContable, match="demasiado largo"):
        p.poner_texto(7, "B" * 10)
    with pytest.raises(ErrorContable, match="no es de texto"):
        p.poner_texto(9, "2025")
    with pytest.raises(ErrorContable, match="caracteres que el fichero no admite"):
        p.poner_texto(8, "ÑANDÚ€")  # el euro no está en ISO-8859-1


def test_una_casilla_repetida_o_inexistente_se_avisa():
    p = Pagina.nueva("14000")
    with pytest.raises(ErrorContable, match="no está"):
        p.n_de_casilla(99999)
    assert p.n_de_casilla("00552") == p.n_de_casilla(552)


def test_un_fichero_escrito_se_lee_igual():
    fichero = Fichero200(version_programa="1.0", nif_desarrollador="B12345674")
    p1 = Pagina.nueva("01000")
    p1.poner_texto(7, "B00000010")
    p14 = Pagina.nueva("14000")
    p14.poner_importe(p14.n_de_casilla(552), D("-14532.46"))
    fichero.paginas = [p1, Pagina.nueva("02000"), p14, Pagina.nueva("DID00")]
    texto = fichero.escribir()
    assert texto.startswith("<T200020250A0000><AUX>") and texto.endswith("</T200020250A0000>") and "\n" not in texto
    leido = Fichero200.leer(texto)
    assert [p.codigo for p in leido.paginas] == ["01000", "02000", "14000", "DID00"] and leido.version_programa == "1.0" and leido.nif_desarrollador == "B12345674"
    assert leido.paginas[2].importe(leido.paginas[2].n_de_casilla(552)) == D("-14532.46")
    assert leido.escribir() == texto


def test_las_paginas_van_en_el_orden_del_diseno():
    f = Fichero200(paginas=[Pagina.nueva("14000"), Pagina.nueva("01000")])
    with pytest.raises(ErrorContable, match="fuera del orden"):
        f.escribir()
    assert f200.paginas_del_diseno()[:4] == ["01000", "01B00", "02000", "02B00"] and f200.paginas_del_diseno()[-1] == "DID00"


def test_un_fichero_de_otro_ejercicio_no_se_lee_con_este_diseno():
    with pytest.raises(ErrorContable, match="ejercicio 2024"):
        Fichero200.leer("<T200020240A0000><AUX>" + " " * (f200.LONGITUD_CABECERA - 28) + "</AUX></T200020240A0000>")
    with pytest.raises(ErrorContable, match="No es un fichero del modelo 200"):
        Fichero200.leer("hola")
    with pytest.raises(ErrorContable, match="no es de este ejercicio"):
        Pagina.leer("01000", "<T20001000>")


@pytest.mark.datos_reales
@pytest.mark.parametrize("nombre", ["C0001_200_2025.200", "C0002_200_2025.200"])
def test_los_200_presentados_de_2025_se_reproducen_byte_a_byte(nombre):
    ruta = AEAT / nombre
    if not ruta.exists():
        pytest.skip(f"No está {ruta}")
    texto = ruta.read_bytes().decode(f200.CODIFICACION)
    fichero = Fichero200.leer(texto)
    assert fichero.escribir() == texto
    codigos = [p.codigo for p in fichero.paginas]
    assert codigos == sorted(codigos, key=f200.ORDEN.__getitem__) and codigos[0] == "01000" and codigos[-1] == "DID00"
    # los importes se leen con su signo: base imponible [00552] de cada empresa
    p14 = next(p for p in fichero.paginas if p.codigo == "14000")
    assert p14.importe(p14.n_de_casilla(552)) == {"C0001": D("1038.90"), "C0002": D("-14532.46")}[nombre[:5]]
