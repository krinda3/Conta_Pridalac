"""Registrar como presentada una declaración a partir sólo del PDF de la sede."""
from datetime import date

import pytest

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.migracion.declaraciones_pdf import importar_declaracion_desde_pdf
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos
from conta_pridalac.servicios.presentacion303 import presentada_del_periodo
from test_justificante_aeat import pdf_de_la_sede


@pytest.fixture
def empresa(sesion):
    e = Empresa(codigo=2, nombre="Prueba S.L.", nif="B12345678")
    sesion.add(e)
    sesion.flush()
    return e


def pdf(tmp_path, nombre="sede.pdf", **kw):
    ruta = tmp_path / nombre
    ruta.write_bytes(pdf_de_la_sede(**kw))
    return ruta


def test_registra_el_303_con_su_justificante_fecha_y_pdf(sesion, empresa, tmp_path):
    almacen = AlmacenAdjuntos(tmp_path / "alm")
    d = importar_declaracion_desde_pdf(sesion, almacen, empresa, "303", 2025, 4, pdf(tmp_path, registro="202530390321543K", justificante="3036978507430", fecha="12-01-2026 a las 14:49:20"))
    assert (d.justificante, d.fecha_emision, d.periodo, d.tipo, d.casillas) == ("3036978507430", date(2026, 1, 12), 4, 1, "{}")
    assert (almacen.raiz / d.pdf_ruta).is_file() and d.pdf_ruta.startswith("002/2025/D/")
    assert presentada_del_periodo(sesion, empresa.id, 2025, 4, "303") is d


def test_una_complementaria_es_otro_tipo_y_no_repite(sesion, empresa, tmp_path):
    almacen = AlmacenAdjuntos(tmp_path / "alm")
    importar_declaracion_desde_pdf(sesion, almacen, empresa, "303", 2025, 4, pdf(tmp_path, registro="202530390321543K"))
    importar_declaracion_desde_pdf(sesion, almacen, empresa, "303", 2025, 4, pdf(tmp_path, "c.pdf", registro="202530390321544K", justificante="3036946304384"), tipo=2)
    with pytest.raises(ErrorContable, match="ya consta"):
        importar_declaracion_desde_pdf(sesion, almacen, empresa, "303", 2025, 4, pdf(tmp_path, registro="202530390321543K"))


@pytest.mark.parametrize("kw,mensaje", [
    (dict(modelo="111", registro="202511100790771G"), "del modelo 111"),
    (dict(registro="202430300790771G"), "otro ejercicio"),
])
def test_rechaza_un_pdf_de_otro_modelo_o_ejercicio(sesion, empresa, tmp_path, kw, mensaje):
    with pytest.raises(ErrorContable, match=mensaje):
        importar_declaracion_desde_pdf(sesion, AlmacenAdjuntos(tmp_path / "alm"), empresa, "303", 2025, 4, pdf(tmp_path, **kw))


def test_un_pdf_que_no_se_lee_se_enlaza_sin_datos(sesion, empresa, tmp_path):
    ilegible = tmp_path / "copia.pdf"
    ilegible.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    d = importar_declaracion_desde_pdf(sesion, AlmacenAdjuntos(tmp_path / "alm"), empresa, "111", 2022, 1, ilegible)
    assert d.justificante is None and d.fecha_emision is None and d.pdf_nombre == "copia.pdf"
    assert presentada_del_periodo(sesion, empresa.id, 2022, 1, "111") is d


def test_otro_nif_no_se_acepta(sesion, empresa, tmp_path):
    empresa.nif = "B99999999"
    with pytest.raises(ErrorContable, match="NIF"):
        importar_declaracion_desde_pdf(sesion, AlmacenAdjuntos(tmp_path / "alm"), empresa, "303", 2025, 4, pdf(tmp_path, registro="202530390321543K"))


def pdf_formato_antiguo(tmp_path):
    """El justificante de la sede de 2022: todas las etiquetas juntas y después los valores."""
    from reportlab.pdfgen import canvas

    ruta = tmp_path / "antiguo.pdf"
    c = canvas.Canvas(str(ruta))
    lineas = ["INFORMACIÓN DE LA PRESENTACIÓN DE LA", "DECLARACIÓN", "MODELO", "Registro", "Presentación realizada el", "Expediente/Referencia (nº registro asignado):", "Código Seguro de Verificación:",
              "Presentador", "NIF Presentador:", "En calidad de:", "Número de justificante:", "111", "17-07-2022 a las 11:19:04", "202211100790574N", "P6WH8PA3LYRPAZG2", "B12345678", "PRUEBA SL", "Titular",
              "Presentación por Internet", "1113002648414", "NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO"]
    for i, linea in enumerate(lineas):
        c.drawString(50, 800 - 18 * i, linea)
    c.save()
    return ruta


def test_lee_el_formato_antiguo_de_la_sede(tmp_path):
    from datetime import datetime

    from conta_pridalac.servicios.justificante_aeat import leer_justificante

    j = leer_justificante(pdf_formato_antiguo(tmp_path).read_bytes())
    assert (j.modelo, j.justificante, j.csv, j.registro, j.resultado, j.nif_presentador) == ("111", "1113002648414", "P6WH8PA3LYRPAZG2", "202211100790574N", "N", "B12345678")
    assert j.momento == datetime(2022, 7, 17, 11, 19, 4)


def test_importa_el_2t_de_2022_desde_el_formato_antiguo(sesion, empresa, tmp_path):
    d = importar_declaracion_desde_pdf(sesion, AlmacenAdjuntos(tmp_path / "alm"), empresa, "111", 2022, 2, pdf_formato_antiguo(tmp_path))
    assert (d.justificante, d.fecha_emision, d.periodo) == ("1113002648414", date(2022, 7, 17), 2)
