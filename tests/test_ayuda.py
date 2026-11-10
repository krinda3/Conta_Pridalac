"""La ayuda: convertidor de Markdown (seguro), buscador, partes generadas por el programa, enlaces internos que no se rompen y pantallas."""
import re

import pytest

from conta_pridalac.web import ayuda as ay
from test_web_auditoria import cliente  # noqa: F401 - es una fixture


def _html(md, **kw):
    return ay.a_html(md, **kw)[0]


def test_el_markdown_basico_se_convierte_y_el_html_se_escapa():
    h = _html("## Título uno\n\nTexto con **negrita**, *cursiva* y `código <b>`.\n\n- uno\n- dos\n\n1. primero\n2. segundo\n")
    assert '<h2 id="titulo-uno">Título uno</h2>' in h and "<strong>negrita</strong>" in h and "<em>cursiva</em>" in h and "<code>código &lt;b&gt;</code>" in h
    assert "<ul><li>uno</li><li>dos</li></ul>" in h and "<ol><li>primero</li><li>segundo</li></ol>" in h
    peligro = _html("<script>alert(1)</script> y [x](javascript:alert(1)) y [y](tema:a#b)")
    assert "<script>" not in peligro and "javascript:" not in peligro and 'href="/ayuda/a#b"' in peligro  # lo no reconocido pierde el enlace


def test_tablas_citas_codigo_y_continuacion_de_listas():
    h = _html("| A | B |\n|---|---|\n| 1 | **2** |\n\n> **Importante:** ojo\n\n```\nx < y\n```\n\n- uno que sigue\n  en otra línea\n- dos\n")
    assert "<th>A</th>" in h and "<td><strong>2</strong></td>" in h and 'class="aviso warning"' in h and "<pre><code>x &lt; y</code></pre>" in h
    assert "<li>uno que sigue en otra línea</li>" in h


def test_los_enlaces_a_pantallas_solo_existen_dentro_de_una_empresa():
    dentro = _html("[la lista](pantalla:modelo-303)", base_ayuda="/e/x/2026/ayuda", base_pantallas="/e/x/2026")
    fuera = _html("[la lista](pantalla:modelo-303)")
    assert 'href="/e/x/2026/modelo-303"' in dentro and "href" not in fuera and "la lista" in fuera


def test_el_indice_de_titulos_y_los_anclas_repetidos():
    html, indice = ay.a_html("# T\n\n## Uno\n\n### Sub\n\n## Uno\n")
    assert [(n, a) for n, a, _ in indice] == [(2, "uno"), (3, "sub"), (2, "uno-2")] and 'id="uno-2"' in html


def test_el_buscador_ignora_mayusculas_y_acentos_y_pide_todas_las_palabras():
    textos = [ay.Tema("a", "Tema A", "# Tema A\n\n## Pagos del trimestre\n\nLos pagos se concilian con el extracto.\n\n## Otra cosa\n\nNada de esto.\n"), ay.Tema("b", "Tema B", "# Tema B\n\n## Cierre\n\nEl cierre del ejercicio.\n")]
    r = ay.buscar("CONCILIAN extracto", textos)
    assert [(x["slug"], x["apartado"], x["ancla"]) for x in r] == [("a", "Pagos del trimestre", "pagos-del-trimestre")] and "concilian" in r[0]["extracto"]
    assert ay.buscar("ejercicio cierre", textos)[0]["slug"] == "b" and ay.buscar("zzz", textos) == [] and ay.buscar("", textos) == [] and ay.buscar("a", textos) == []


def test_todos_los_temas_tienen_titulo_y_los_enlaces_internos_apuntan_a_un_apartado_que_existe():
    assert len(ay.temas()) >= 2
    anclas = {}
    for t in ay.temas():
        assert t.titulo and t.texto.startswith("# "), t.slug
        anclas[t.slug] = {a for _, a, _ in ay.a_html(t.texto)[1]}
    rotos = []
    for t in ay.temas():
        for destino in re.findall(r"\]\(tema:([^)\s]+)\)", t.texto):
            slug, _, ancla = destino.partition("#")
            if slug not in anclas or (ancla and ancla not in anclas[slug]):
                rotos.append(f"{t.slug} → {destino}")
    assert rotos == []


def test_las_pantallas_citadas_en_la_ayuda_existen_en_el_programa():
    from conta_pridalac.web.definiciones import todos_los_listados

    existentes = set(todos_los_listados()) | set(ay.PANTALLAS_GLOBALES)   # Programa y Normativa no son de una empresa: cuelgan de la pantalla de empresas
    citadas = {n for t in ay.temas() for n in re.findall(r"\]\(pantalla:([^)\s]+)\)", t.texto)}
    assert citadas - existentes == set()


def test_los_enlaces_a_programa_y_normativa_sirven_dentro_y_fuera_de_una_empresa(cliente):
    assert ay._enlace("pantalla:programa", "/ayuda", None) == "/programa" and ay._enlace("pantalla:normativa", "/ayuda", "/e/prueba/2026") == "/normativa"
    assert ay._enlace("pantalla:modelo-303", "/ayuda", None) is None                    # las demás siguen necesitando una empresa
    assert 'href="/programa"' in cliente.get("/ayuda/cierre").text and 'href="/normativa"' in cliente.get("/e/prueba/2026/ayuda/cierre").text


def test_las_pantallas_de_la_ayuda_dentro_y_fuera_de_la_empresa(cliente):
    fuera = cliente.get("/ayuda")
    assert fuera.status_code == 200 and "Ayuda de Conta Pridalac" in fuera.text and "Primeros pasos" in fuera.text
    dentro = cliente.get("/e/prueba/2026/ayuda/pantallas")
    assert dentro.status_code == 200 and 'href="/e/prueba/2026/modelo-303"' in dentro.text and "303 · IVA" in dentro.text  # el menú generado, con enlaces
    assert "Las pantallas del programa" in cliente.get("/ayuda/pantallas").text and 'href="/e/prueba/2026/modelo-303"' not in cliente.get("/ayuda/pantallas").text
    assert cliente.get("/ayuda/no-existe").status_code == 404
    busqueda = cliente.get("/ayuda?q=certificado")
    assert busqueda.status_code == 200 and "Resultados para" in busqueda.text and "Primeros pasos" in busqueda.text
    assert "No hay nada sobre" in cliente.get("/ayuda?q=zzzzqq").text


def test_el_boton_de_ayuda_lleva_al_tema_de_la_pantalla(cliente):
    assert 'href="/e/prueba/2026/ayuda"' in cliente.get("/e/prueba/2026").text  # el inicio de la empresa: el índice
    assert 'href="/e/prueba/2026/ayuda/facturas"' in cliente.get("/e/prueba/2026/facturas-recibidas").text if ay.tema("facturas") else True
    assert 'id="ayuda"' in cliente.get("/").text and 'href="/ayuda"' in cliente.get("/").text


# ------------------------------------------------------------------------------------------------ plantillas de Excel

from datetime import date  # noqa: E402
from io import BytesIO  # noqa: E402

from openpyxl import load_workbook  # noqa: E402

from conta_pridalac.servicios import plantillas_excel as pe  # noqa: E402
from conta_pridalac.servicios import trimestre as tri  # noqa: E402
from conta_pridalac.servicios.extractos import _clave_de_texto  # noqa: E402


def _cabeceras(contenido):
    libro = load_workbook(BytesIO(contenido))
    return [c.value for c in libro.worksheets[0][1] if c.value], libro


def test_la_plantilla_de_recibidas_tiene_todas_las_columnas_que_lee_el_programa_y_se_carga():
    contenido, nombre = pe.plantilla("recibidas")
    cabeceras, libro = _cabeceras(contenido)
    claves = {_clave_de_texto(c) for c in cabeceras}
    assert nombre == "plantilla_recibidas.xlsx" and libro.sheetnames[1] == "Instrucciones"
    assert {v for k, v in tri.COLUMNAS.items() if not k.startswith("pago_")} <= claves  # todo lo que lee (menos los datos de pago de Verifactu)
    hoja = libro.worksheets[0]
    hoja.append(["Proveedor Prueba S.L.", "B12345678", date(2026, 7, 10), "A-77", "100.00", "21", "21.00", "121.00"])
    salida = BytesIO()
    libro.save(salida)
    filas = tri.leer_recibidas_verifactu(salida.getvalue())
    assert len(filas) == 1 and filas[0]["nombre"] == "Proveedor Prueba S.L." and filas[0]["numero_factura"] == "A-77" and str(filas[0]["total"]) == "121.00"


def test_la_plantilla_de_emitidas_tiene_las_columnas_del_lector_y_se_carga():
    contenido, _ = pe.plantilla("emitidas")
    cabeceras, libro = _cabeceras(contenido)
    claves = {_clave_de_texto(c) for c in cabeceras}
    assert all(any(n in claves for n in nombres) for nombres in tri.COLUMNAS_EMITIDAS.values())
    libro.worksheets[0].append(["2026/15", date(2026, 7, 10), "B00000010", "Cliente S.L.", "B11111111", "100.00", "21", "21.00", "121.00", "Enviada"])
    salida = BytesIO()
    libro.save(salida)
    filas = tri.leer_emitidas_verifactu(salida.getvalue())
    assert len(filas) == 1 and filas[0]["numero"] == "2026/15" and filas[0]["nombre"] == "Cliente S.L." and str(filas[0]["total"]) == "121.00"
    with pytest.raises(ValueError):
        pe.plantilla("otra")


def test_la_pantalla_ofrece_la_plantilla_y_la_ruta_la_descarga(cliente):
    r = cliente.get("/e/prueba/2026/plantilla-excel/recibidas")
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"] and "plantilla_recibidas.xlsx" in r.headers["content-disposition"] and r.content[:2] == b"PK"
    assert cliente.get("/e/prueba/2026/plantilla-excel/emitidas").status_code == 200 and cliente.get("/e/prueba/2026/plantilla-excel/otra").status_code == 404
    dialogo = cliente.get("/e/prueba/2026/conciliacion/accion/cargar").text
    assert "plantilla-excel/recibidas" in dialogo and "ayuda/facturas#plantillas-de-excel" in dialogo
    assert "plantilla-excel/emitidas" in cliente.get("/e/prueba/2026/emitidas-trimestre/accion/cargar").text


def test_ninguna_pagina_de_la_ayuda_deja_restos_de_markdown_y_la_auditoria_sale_completa(cliente):
    from conta_pridalac.web.auditoria import CATALOGO

    for t in ay.temas():
        for base in ("/ayuda", "/e/prueba/2026/ayuda"):
            r = cliente.get(f"{base}/{t.slug}")
            assert r.status_code == 200, (base, t.slug)
            cuerpo = r.text.split('<article class="ayuda-texto">', 1)[1].split("</article>", 1)[0]
            for resto in ("@@", "**", "](", "\n- ", "| ---"):
                assert resto not in cuerpo, (t.slug, resto, cuerpo[max(0, cuerpo.index(resto) - 60):cuerpo.index(resto) + 60])
    cierre = cliente.get("/ayuda/cierre").text
    assert all(titulo in cierre for titulo, _, _, _ in CATALOGO.values())  # cada aviso de la auditoría está explicado en la ayuda
