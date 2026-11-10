"""La pantalla del modelo 390: sale en Liquidaciones, enseña los controles y las casillas, y se exporta como hoja de casillas."""
import re
from test_web_extractos import cliente  # noqa: F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/modelo-390"


def test_el_390_sale_en_liquidaciones_y_la_pantalla_se_abre(cliente):
    inicio = cliente.get("/e/prueba/2026").text
    assert f'href="{BASE}"' in inicio and "390 · Resumen anual del IVA" in inicio
    pagina = cliente.get(BASE)
    assert pagina.status_code == 200 and "Prorrata definitiva" in pagina.text


def test_la_tabla_enseña_los_controles_y_las_casillas(cliente):
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Controles contra los 303" in tabla and "Total bases y cuotas IVA" in tabla and "Resultado régimen general" in tabla and "Total volumen de operaciones" in tabla


def test_la_prorrata_se_anota_y_la_hoja_se_exporta(cliente):
    assert "Porcentaje de prorrata definitivo" in cliente.get(f"{BASE}/tabla", params={"prorrata": "63,58"}).text
    assert "Porcentaje de prorrata definitivo" not in cliente.get(f"{BASE}/tabla").text
    excel = cliente.get(f"{BASE}/exportar.xlsx")
    assert excel.status_code == 200 and excel.content[:2] == b"PK"  # un .xlsx es un zip


def _con_la_ficha_completa(cliente):
    datos = {"nombre": "Empresa de Prueba", "nif": "B12345678", "act_descripcion": ["Servicios técnicos"], "act_codigo": ["A03"], "act_epigrafe": ["8431"],
             "rep_nombre": ["Lopez Garcia, Elena"], "rep_nif": ["00000014Z"], "rep_fecha_poder": ["261011"], "rep_notaria": ["Romero"]}
    r = cliente.post("/empresa/prueba", data=datos, follow_redirects=False)
    assert r.status_code == 303


def test_la_ficha_avisa_de_lo_que_falta_en_la_empresa(cliente):
    ficha = cliente.get(f"{BASE}/f/0").text
    assert "Modelo 390 · ejercicio 2026" in ficha and "Falta la actividad principal" in ficha and "Falta al menos un representante" in ficha
    assert "disabled" in __import__("re").findall(r'<button[^>]*value="generar"[^>]*>', ficha)[0]


def test_guardar_generar_descargar_copiar_y_registrar(cliente):
    import json

    from test_justificante_aeat import pdf_de_la_sede

    _con_la_ficha_completa(cliente)
    assert "Borrador guardado" in cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "guardar", "tipo_presentacion": "normal"}).headers["HX-Trigger"]
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "generar", "tipo_presentacion": "normal"})
    assert "Fichero generado" in r.headers["HX-Trigger"] and "Ver lo que lleva el fichero" in r.text and "LOPEZ GARCIA, ELENA" in r.text
    s = cliente.app.state.config.sesion("prueba")
    try:
        from sqlalchemy import select

        from conta_pridalac.db.modelos import PresentacionAeat

        p = s.scalars(select(PresentacionAeat).where(PresentacionAeat.modelo == "390")).one()
        pid, nombre = p.id, p.fichero_nombre
    finally:
        s.close()
    d = cliente.get(f"{BASE}/{pid}/fichero")
    assert d.status_code == 200 and d.content.startswith(b"<T39002026" + b"0A0000>") and nombre.endswith(".390")
    copia = json.loads(cliente.post(f"{BASE}/{pid}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    assert copia.startswith("Copiado a ") and copia.endswith("_AEAT_390_2026_0A.390")
    pdf = pdf_de_la_sede(modelo="390", registro="202639000790112R", justificante="3906032822903", resultado="", nrc_importe=None, fecha="20-10-2026 a las 12:08:39")
    r = cliente.post(f"{BASE}/guardar", data={"id": "0", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "leído del PDF" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], r.text[:400]
    assert cliente.get(f"{BASE}/{pid}/justificante").content == pdf
