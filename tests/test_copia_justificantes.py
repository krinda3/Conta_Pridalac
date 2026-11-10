"""Copia de los justificantes de Hacienda a la carpeta de la empresa: nombres, carpeta por año y qué hacer si ya existe."""
from conta_pridalac.db.modelos import Empresa
from conta_pridalac.servicios import copia_justificantes as c


def empresa(carpeta=None, corto="EMPRESA B"):
    return Empresa(id=1, codigo=1, nombre="EMPRESA B S.L.", nombre_corto=corto, carpeta_justificantes=carpeta)


def test_los_nombres_siguen_la_costumbre_de_la_carpeta_de_hacienda():
    e = empresa()
    assert c.nombre_de(e, "303", 2026, "3T") == "EMPRESA B AEAT Mod 303 3T 2026.pdf"
    assert c.nombre_de(e, "303", 2026, 3) == "EMPRESA B AEAT Mod 303 3T 2026.pdf"  # los importados del programa anterior traen el trimestre como número
    assert c.nombre_de(e, "303", 2025, "4T", "rectificativa") == "EMPRESA B AEAT Mod 303 4T 2025 rectificativa.pdf"
    assert c.nombre_de(e, "111", 2026, "1T", "complementaria") == "EMPRESA B AEAT Mod 111 1T 2026 complementaria.pdf"
    for modelo in ("190", "347", "390", "200"):  # los anuales sólo llevan el año, aunque el periodo sea «0A»
        assert c.nombre_de(e, modelo, 2026, "0A") == f"EMPRESA B AEAT Mod {modelo} 2026.pdf"
    assert c.nombre_de(empresa(corto=None), "303", 2026, "1T").startswith("EMPRESA B AEAT")  # sin nombre corto, la razón social sin S.L.


def test_la_carpeta_lleva_el_año(tmp_path):
    assert c.carpeta_de(empresa(str(tmp_path / "Hacienda {año}")), 2026) == tmp_path / "Hacienda 2026"
    assert c.carpeta_de(empresa('"' + str(tmp_path / "AEAT {año}") + '"'), 2025).name == "AEAT 2025"  # con comillas, como se copia desde el Explorador
    assert c.carpeta_de(empresa(), 2026) is None and c.carpeta_de(empresa("   "), 2026) is None


def test_copiar_crea_la_carpeta_no_repite_y_no_pisa_lo_distinto(tmp_path):
    e = empresa(str(tmp_path / "OneDrive" / "Hacienda {año}"))
    primera = c.copiar_pdf(e, 2026, "EMPRESA B AEAT Mod 303 1T 2026.pdf", b"%PDF-uno")
    assert primera.estado == c.COPIADO and primera.destino.read_bytes() == b"%PDF-uno"
    assert c.copiar_pdf(e, 2026, "EMPRESA B AEAT Mod 303 1T 2026.pdf", b"%PDF-uno").estado == c.IGUAL
    otra = c.copiar_pdf(e, 2026, "EMPRESA B AEAT Mod 303 1T 2026.pdf", b"%PDF-dos")
    assert otra.estado == c.CON_SUFIJO and otra.destino.name == "EMPRESA B AEAT Mod 303 1T 2026 (2).pdf" and primera.destino.read_bytes() == b"%PDF-uno"  # lo que había no se toca
    assert c.copiar_pdf(e, 2026, "EMPRESA B AEAT Mod 303 1T 2026.pdf", b"%PDF-dos").estado == c.IGUAL  # y repetir la segunda tampoco crea una tercera


def test_sin_carpeta_o_con_una_carpeta_imposible_no_lanza(tmp_path):
    assert c.copiar_pdf(empresa(), 2026, "x.pdf", b"%PDF").estado == c.SIN_CARPETA
    (tmp_path / "fichero").write_text("x")
    assert c.copiar_pdf(empresa(str(tmp_path / "fichero" / "{año}")), 2026, "x.pdf", b"%PDF").estado == c.FALLO
