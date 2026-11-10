"""Legalización de libros: números de libro, controles, los PDF del diario y del inventario, el DATOS.TXT de Legalia2 y la pantalla."""
import base64
import hashlib
import logging
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from conta_pridalac.db.modelos import Acta, Cuenta, Ejercicio, Empresa, Legalizacion, LibroLegalizacion, MovimientoSocio, Parametro, Socio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import libros_oficiales as lo
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cierre import cerrar_ejercicio
from test_web_auditoria import _sesion, cliente  # noqa: F401 - `cliente` es una fixture

D = Decimal
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", domicilio="CL MAYOR, 1", codigo_postal="28221", poblacion="Majadahonda", provincia="MADRID", registro_provincia="MADRID I",
                registro_tomo="30001", registro_folio="2001", registro_hoja="500001", fecha_constitucion=date(2013, 12, 31), actividad="Cultivo de árboles")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("10000000", "CAPITAL"), ("12900000", "RESULTADOS DEL EJERCICIO"), ("57200001", "BANCO"), ("70000000", "VENTAS"), ("62900000", "GASTOS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.add(Parametro(empresa_id=e.id, clave="PYG", valor="12900000"))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=9, numero=1, fecha=date(2025, 1, 1), concepto="Apertura del ejercicio", subtipo="A", lineas=[LineaAsiento("57200001", D(5000)), LineaAsiento("10000000", D(-5000))])
    grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2025, 2, 10), concepto="Venta", lineas=[LineaAsiento("57200001", D(1210)), LineaAsiento("70000000", D(-1210))])
    grabar_asiento(sesion, ej, tipo=4, numero=2, fecha=date(2025, 8, 5), concepto="Gasto", lineas=[LineaAsiento("62900000", D(300)), LineaAsiento("57200001", D(-300))])
    _socios_y_acta(sesion, e)
    sesion.flush()
    return ej


def _socios_y_acta(sesion, e):
    for orden, (nif, nombre, n) in enumerate((("00000014Z", "Lopez García de Soto, Elena", 3000), ("00000001R", "Gil Navarro, Pedro", 2000)), 1):
        s = Socio(empresa_id=e.id, orden=orden, nif=nif, nombre=nombre, nacionalidad="ESPAÑA", fecha_nacimiento=date(1960, 4, 14), domicilio="Mayor 21", poblacion="Majadahonda", provincia="MADRID")
        s.movimientos.append(MovimientoSocio(fecha=date(2013, 12, 31), tipo="Constitución", participaciones=n, desde=1 if orden == 1 else 3001, hasta=3000 if orden == 1 else 5000, valor_nominal="1.00"))
        sesion.add(s)
    sesion.add(Acta(empresa_id=e.id, numero=1, fecha=date(2025, 3, 31), hora_inicio="18:00", hora_fin="19:00", clase="Ordinaria", organo="Junta General", asistentes="Elena\nJavier",
                    orden_del_dia="1.- Aprobación de cuentas anuales de 2024", resumen="Presentación de las cuentas", acuerdos="Se aprueban las cuentas", votaciones="Todas a favor",
                    presidente_nombre="Elena", presidente_nif="00000014Z", secretario_nombre="Pedro", secretario_nif="00000001R"))


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


def test_los_trimestres_acaban_el_ultimo_dia():
    assert [lo._fin_de_trimestre(date(2025, 1, 1), t) for t in (1, 2, 3, 4)] == [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31)]
    assert lo._fin_de_trimestre(date(2025, 7, 1), 2) == date(2025, 12, 31)


def test_el_ejercicio_abierto_y_la_ficha_incompleta_se_avisan(sesion, ej):
    h = lo.controlar(sesion, ej)
    assert "ejercicio_sin_cerrar" in codigos(h, "ERROR") and {"falta_dato_de_legalia"} <= codigos(h, "AVISO")
    with pytest.raises(ErrorContable, match="no está cerrado"):
        lo.generar_libros(sesion, ej, ".")


def test_numeros_propuestos(sesion, ej):
    assert lo.numeros_propuestos(sesion, ej.empresa_id, 2025) == {c: (1, None) for _, c, _, _ in lo.LIBROS}
    leg = Legalizacion(empresa_id=ej.empresa_id, anio=2024)
    leg.libros = [LibroLegalizacion(orden=o, clave=c, numero=n) for o, c, n in ((1, "diario", 5), (2, "inventario", 6), (3, "socios", 1), (4, "actas", 2))]
    sesion.add(leg)
    sesion.flush()
    assert lo.numeros_propuestos(sesion, ej.empresa_id, 2025) == {"diario": (6, date(2024, 12, 31)), "inventario": (7, date(2024, 12, 31)), "socios": (1, date(2024, 12, 31)), "actas": (2, date(2024, 12, 31))}


def test_genera_el_diario_y_el_inventario(sesion, ej, tmp_path):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7})
    assert leg.estado == "preparada" and [(l.clave, l.numero, l.fichero_nombre) for l in leg.libros] == [
        ("diario", 6, "DIARIO_006.PDF"), ("inventario", 7, "INV_CUEN_007.PDF"), ("socios", 1, "SOCIOS_001.PDF"), ("actas", 1, "ACTASCON_001.PDF")]
    for libro in leg.libros:
        datos = (tmp_path / libro.fichero_ruta).read_bytes()
        assert datos.startswith(b"%PDF") and libro.sha256_base64 == base64.b64encode(hashlib.sha256(datos).digest()).decode() and libro.paginas == len(PdfReader(tmp_path / libro.fichero_ruta).pages)
    diario = PdfReader(tmp_path / leg.libros[0].fichero_ruta)
    texto = "".join(p.extract_text() for p in diario.pages)
    for esperado in ("Libro de diario Ejercicio 2025", "B12345678", "Prueba S.L.", "Apertura del ejercicio", "REGUL. DE INGRESOS", "ASIENTO DE CIERRE", "Página 1 de"):
        assert esperado in texto, esperado
    socios = "".join(p.extract_text() for p in PdfReader(tmp_path / leg.libros[2].fichero_ruta).pages)
    for esperado in ("Libro Registro de Socios Ejercicio 2025", "00000014Z", "Gil Navarro, Pedro", "31/12/2013", "Constitución", "3.000", "60,00", "Total Capital Social:", "5.000,00", "MADRID I tomo 30001"):
        assert esperado in socios, esperado
    actas = "".join(p.extract_text() for p in PdfReader(tmp_path / leg.libros[3].fichero_ruta).pages)
    for esperado in ("ACTA Nº 1. Reunión Ordinaria de la Junta General", "Siendo las 18:00h del 31/03/2025", "ORDEN DEL DÍA", "Se aprueban las cuentas", "Vº Bº PRESIDENTE", "EL SECRETARIO", "00000014Z"):
        assert esperado in actas, esperado
    inventario = "".join(p.extract_text() for p in PdfReader(tmp_path / leg.libros[1].fichero_ruta).pages)
    for esperado in ("Balance de sumas y saldos inicial Ejercicio 2025", "trimestre 1", "trimestre 4", "inventario Ejercicio 2025", "MEMORIA ANUAL DE LA SOCIEDAD Prueba S.L.", "inscrita en el Registro Mercantil de MADRID I en tomo 30001",
                     "Cultivo de árboles", "5.000,00"):
        assert esperado in inventario, esperado


def test_al_regenerar_con_otro_numero_se_quita_el_pdf_antiguo(sesion, ej, tmp_path):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7})
    antiguo = tmp_path / leg.libros[0].fichero_ruta
    assert antiguo.exists()
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 8})
    assert not antiguo.exists() and (tmp_path / leg.libros[0].fichero_ruta).name == "DIARIO_008.PDF" and leg.libros[1].numero == 7 and len(leg.libros) == 4


def test_las_sumas_y_saldos_por_periodo(sesion, ej):
    inicial, t1, t2, t3, t4, inventario = lo.secciones_de_sumas_y_saldos(sesion, ej)
    assert inicial.totales[:2] == (D("5000.00"), D("5000.00"))
    assert t1.totales[0] == D("6210.00") and t2.totales[0] == D("6210.00") and t3.totales[0] == t4.totales[0] == inventario.totales[0] == D("6510.00")
    cuentas = {f.cuenta for f in inventario.filas}
    assert {"5", "57", "572", "5720", "57200001"} <= cuentas  # grupo, subgrupo, cuenta, subcuenta de 4 dígitos y subcuenta completa


def test_memoria_con_y_sin_is_presentado(sesion, ej):
    bloques, avisos = lo.memoria(sesion, ej)
    assert any("resultado contable" in a for a in avisos) and any("34580" not in b.texto and "5000" in b.texto for b in bloques)
    renglones = next(b for b in bloques if b.tipo == "renglon").filas
    assert renglones[0][1] == "910,00" and renglones[-1][1] == "910,00"


def test_datos_txt_de_legalia2_y_precarga_de_la_ficha(sesion, ej):
    texto = "100MADRID\n10101012026\n102PRUEBA S.L.\n105B12345678\n109" + "28\n11228065\n301elena\n302lopez\n304" + "00000014Z\n311elena@example.com\n00101Diario\n001026\n00106abc=\n"
    datos = lo.leer_datos_txt(texto)
    assert datos["109"] == "28" and datos["301"] == "elena" and "001" not in datos and datos["311"] == "elena@example.com"
    puestos = dict(lo.precargar_ficha(ej.empresa, datos))
    assert puestos["presentador_nombre"] == "elena" and puestos["municipio_ine"] == "28065" and ej.empresa.presentador_nif == "00000014Z"
    ej.empresa.presentador_nombre = "Otra"
    assert "presentador_nombre" not in dict(lo.precargar_ficha(ej.empresa, datos)) and ej.empresa.presentador_nombre == "Otra"  # no pisa lo escrito
    with pytest.raises(ErrorContable, match="NIF"):
        lo.precargar_ficha(ej.empresa, {**datos, "105": "B99999999"})


# ---------------------------------------------------------------------------------------------- pantalla

BASE = "/e/prueba/2026/legalizacion-libros"


def _preparar_empresa(cliente):
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    e.nif, e.domicilio, e.codigo_postal, e.poblacion, e.provincia = "B12345678", "CL MAYOR, 1", "28221", "Majadahonda", "MADRID"
    s.scalar(select(Ejercicio)).cerrado = True
    s.commit()
    s.close()


def test_las_pantallas_de_socios_y_de_actas(cliente):
    _preparar_empresa(cliente)
    assert cliente.get("/e/prueba/2026/libro-socios").status_code == 200 and "Libro de socios" in cliente.get("/e/prueba/2026").text and "Libro de actas" in cliente.get("/e/prueba/2026").text
    assert "Todavía no hay socios" in cliente.get("/e/prueba/2026/libro-socios/tabla").text
    r = cliente.post("/e/prueba/2026/libro-socios/guardar", data={
        "id": "nuevo", "nombre": "Lopez, Elena", "nif": "00000014z", "orden": "1", "nacionalidad": "ESPAÑA", "fecha_nacimiento": "14/04/1960", "domicilio": "Mayor 21", "poblacion": "Majadahonda",
        "provincia": "MADRID", "mov_fecha": ["31/12/2013", "", ""], "mov_tipo": ["Constitución", "Constitución", "Constitución"], "mov_concepto": ["", "", ""], "mov_participaciones": ["17.500", "", ""],
        "mov_desde": ["1", "", ""], "mov_hasta": ["17500", "", ""], "mov_nominal": ["6,0101", "1,00", "1,00"]})
    assert r.status_code == 200 and "Lopez, Elena" in r.text
    tabla = cliente.get("/e/prueba/2026/libro-socios/tabla").text
    assert "Lopez, Elena" in tabla and "00000014Z" in tabla and "17500" in tabla.replace(".", "").replace(" ", "") and "100,00 %" in tabla
    s = _sesion(cliente)
    socio = s.scalar(select(Socio))
    assert socio.nif == "00000014Z" and [(m.participaciones, m.valor_nominal) for m in socio.movimientos] == [(17500, "6.0101")]
    s.close()
    mal = cliente.post("/e/prueba/2026/libro-socios/guardar", data={"id": str(socio.id), "nombre": "", "mov_fecha": [""], "mov_tipo": ["Compra"], "mov_concepto": [""], "mov_participaciones": [""], "mov_desde": [""],
                                                                       "mov_hasta": [""], "mov_nominal": [""]})
    assert "Falta el nombre del socio" in mal.text
    # el acta de aprobación de cuentas viene preparada con los socios y el texto habitual
    propuesta = cliente.get("/e/prueba/2026/libro-actas/f/nueva").text
    assert "Lopez, Elena" in propuesta and "Aprobación de las cuentas anuales del ejercicio 2025" in propuesta and "Todas a favor con el 100% de los votos" in propuesta
    r = cliente.post("/e/prueba/2026/libro-actas/guardar", data={"id": "nuevo", "numero": "1", "fecha": "31/03/2026", "hora_inicio": "18:00", "hora_fin": "19:00", "clase": "Ordinaria", "organo": "Junta General",
                                                                  "asistentes": "Lopez, Elena", "orden_del_dia": "1.- Aprobación de cuentas", "acuerdos": "Se aprueban", "presidente_nombre": "Lopez, Elena",
                                                                  "presidente_nif": "00000014Z", "secretario_nombre": "Lopez, Elena", "secretario_nif": "00000014Z"})
    assert r.status_code == 200 and "Acta nº 1" in r.text
    assert "31/03/2026" in cliente.get("/e/prueba/2026/libro-actas/tabla").text


def test_la_pantalla_de_legalizacion_genera_los_libros(cliente):
    _preparar_empresa(cliente)
    assert cliente.get(BASE).status_code == 200 and "Legalización de libros" in cliente.get("/e/prueba/2026").text
    assert "2026" in cliente.get(f"{BASE}/tabla").text and "Sin preparar" in cliente.get(f"{BASE}/tabla").text
    ficha = cliente.get(f"{BASE}/f/2026").text
    assert "Los cuatro libros" in ficha and "sin generar" in ficha and "No hay socios" in ficha and "No hay ningún acta" in ficha
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    _socios_y_acta(s, e)
    for a in s.scalars(select(Acta)):
        a.fecha = date(2026, 3, 31)
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "generar", "numero_diario": "6", "numero_inventario": "7", "numero_socios": "1", "numero_actas": "2",
                                               "anterior_diario": "31/12/2025", "anterior_inventario": "31/12/2025", "anterior_socios": "", "anterior_actas": "31/12/2025"})
    assert r.status_code == 200 and "DIARIO_006.PDF" in r.text and "INV_CUEN_007.PDF" in r.text and "SOCIOS_001.PDF" in r.text and "ACTASCON_002.PDF" in r.text
    s = _sesion(cliente)
    leg = s.scalar(select(Legalizacion))
    assert leg.anio == 2026 and [l.numero for l in leg.libros] == [6, 7, 1, 2]
    for clave in ("diario", "inventario", "socios", "actas"):
        descarga = cliente.get(f"{BASE}/{leg.id}/libro/{clave}")
        assert descarga.status_code == 200 and descarga.content.startswith(b"%PDF") and descarga.headers["content-type"] == "application/pdf"
    assert cliente.get(f"{BASE}/{leg.id}/libro/otro").status_code == 404
    s.close()
    assert "Preparada" in cliente.get(f"{BASE}/tabla").text


def test_carga_de_socios_desde_json(sesion, ej):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("cargar_socios", Path(__file__).resolve().parents[1] / "tools" / "cargar_socios.py")
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    sesion.execute(Socio.__table__.delete())
    datos = {"nif_empresa": "B12345678", "socios": [{"nif": "00000014Z", "nombre": "Lopez, Elena", "nacimiento": "14/04/1960",
                                                      "movimientos": [{"fecha": "31/12/2013", "participaciones": 500, "valor_nominal": "6.0101"}]}]}
    assert herramienta.cargar(sesion, datos) == ["Lopez, Elena: 500 participaciones"]
    socios, capital = lo.socios_del_libro(sesion, ej.empresa, date(2025, 12, 31))
    assert [(s.nif, s.total_participaciones, s.porcentaje) for s in socios] == [("00000014Z", 500, D("100.00"))] and capital == D("3005.05")  # 500 × 6,0101
    assert herramienta.cargar(sesion, datos) == ["Lopez, Elena: ya estaba"]
    with pytest.raises(ErrorContable, match="NIF"):
        herramienta.cargar(sesion, {**datos, "nif_empresa": "B99999999"})
    assert lo.socios_del_libro(sesion, ej.empresa, date(2010, 1, 1)) == ([], D("0.00"))  # antes de la constitución no había socios


# ---------------------------------------------------------------------------------------------- el ZIP para Legalia2

def _ficha_completa(e):
    e.telefono, e.municipio_ine, e.provincia_ine, e.codigo_irus = "600 00 00 00", "28065", "28", "1000000000001"
    e.presentador_nombre, e.presentador_apellido1, e.presentador_apellido2, e.presentador_nif = "elena", "lopez", "garcia de soto", "00000014Z"
    e.presentador_domicilio, e.presentador_poblacion, e.presentador_cp, e.presentador_telefono, e.presentador_email = "MAYOR Nº 21", "Majadahonda", "28221", "600000000", "elena@example.com"


def test_sin_los_datos_de_la_ficha_se_generan_los_pdf_pero_no_el_zip(sesion, ej, tmp_path):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    leg = lo.generar_libros(sesion, ej, tmp_path)
    assert len([l for l in leg.libros if l.fichero_ruta]) == 4 and leg.zip_ruta is None
    assert "código INE del municipio" in lo.datos_que_faltan_para_el_zip(ej.empresa)
    with pytest.raises(ErrorContable, match="Faltan datos"):
        lo.preparar_zip(leg, ej, tmp_path)


def test_el_zip_lleva_los_cuatro_libros_y_los_dos_ficheros_de_legalia2(sesion, ej, tmp_path):
    import zipfile

    _ficha_completa(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7, "socios": 1, "actas": 2}, anteriores={"diario": date(2024, 12, 31), "inventario": date(2024, 12, 31), "socios": None, "actas": date(2024, 12, 31)})
    assert leg.zip_nombre == "LL28025B12345678.ZIP" and leg.fecha_presentacion == date.today()
    z = zipfile.ZipFile(tmp_path / leg.zip_ruta)
    assert sorted(z.namelist()) == ["ACTASCON_002.PDF", "DATOS.TXT", "DESC.TXT", "DIARIO_006.PDF", "INV_CUEN_007.PDF", "NOMBRES.TXT", "SOCIOS_001.PDF"]
    assert z.read("DESC.TXT") == b"B12345678\r\nIRUS= 1000000000001\r\n"  # el IRUS de la ficha, completo
    assert z.read("NOMBRES.TXT") == b"DIARIO_006.PDF\r\nINV_CUEN_007.PDF\r\nSOCIOS_001.PDF\r\nACTASCON_002.PDF\r\n"
    lineas = z.read("DATOS.TXT").decode("latin-1").split("\r\n")
    hoy = date.today().strftime("%d%m%Y")
    assert lineas[:26] == ["100MADRID", f"101{hoy}", "102Prueba S.L.", "105B12345678", "106CL MAYOR, 1", "107MAJADAHONDA", "10828221", "10928", "111600000000", "11228065", "20130001", "2042001",
                          "205REGISTRO MERCANTIL", "206500001", "301elena", "302lopez", "303garcia de soto", "30400000014Z", "305MAYOR Nº 21", "306Majadahonda", "30728221", "30828", "310600000000",
                          "311elena@example.com", "401NO", "5014"]
    assert lineas[26:31] == ["00101Diario", "001026", "0010301012025", "0010431122025", "0010531122024"] and lineas[31].startswith("00106")
    # el libro de socios no lleva fecha anterior (primera vez): sin línea 00305
    socios = lineas[lineas.index("00301Libro registro de socios"):]
    assert socios[:5] == ["00301Libro registro de socios", "003021", "0030301012025", "0030431122025", socios[4]] and socios[4].startswith("00306")
    actas = lineas[lineas.index("00401Libro registro de actas"):]
    assert actas[:6] == ["00401Libro registro de actas", "004022", "0040301012025", "0040431122025", "0040531122024", actas[5]] and actas[5].startswith("00406")
    for libro in leg.libros:  # la huella de cada libro es la del PDF que va dentro
        assert f"00{libro.orden}06{libro.sha256_base64}" in lineas
        assert hashlib.sha256(z.read(libro.fichero_nombre)).digest() == base64.b64decode(libro.sha256_base64)


def test_la_pantalla_da_el_zip_y_lo_copia_a_descargas(cliente):
    _preparar_empresa(cliente)
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    _ficha_completa(e)
    e.registro_provincia, e.registro_tomo, e.registro_folio, e.registro_hoja = "MADRID I", "30001", "2001", "500001"
    _socios_y_acta(s, e)
    for a in s.scalars(select(Acta)):
        a.fecha = date(2026, 3, 31)
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "generar", "numero_diario": "6", "numero_inventario": "7", "numero_socios": "1", "numero_actas": "2",
                                               "anterior_diario": "31/12/2025", "anterior_inventario": "31/12/2025", "anterior_socios": "", "anterior_actas": "31/12/2025"})
    assert r.status_code == 200 and "LL28026B12345678.ZIP" in r.text and "Copiar el ZIP a" in r.text
    s = _sesion(cliente)
    leg = s.scalar(select(Legalizacion))
    descarga = cliente.get(f"{BASE}/{leg.id}/libro/zip")
    assert descarga.status_code == 200 and descarga.content.startswith(b"PK") and descarga.headers["content-type"] == "application/zip"
    s.close()
    cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "copiar_zip"})
    assert (cliente.app.state.config.descargas / "LL28026B12345678.ZIP").is_file()


def test_un_libro_que_no_es_el_primero_necesita_la_fecha_de_su_legalizacion_anterior(sesion, ej, tmp_path):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    with pytest.raises(ErrorContable, match="no es el primero.*Legalia2 lo exige"):
        lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7, "socios": 1, "actas": 2}, anteriores={"diario": None, "inventario": None, "socios": None, "actas": None})
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7, "socios": 1, "actas": 2})  # sin pedir fechas, los que no son el primero salen con el fin del año anterior
    assert [(l.clave, l.fecha_ejercicio_anterior) for l in leg.libros] == [("diario", date(2024, 12, 31)), ("inventario", date(2024, 12, 31)), ("socios", None), ("actas", date(2024, 12, 31))]


# ---------------------------------------------------------------------------------------------- el envío al Registro y su plazo

def _pdf_acuse(referencia="B123456782025", fecha="08/04/2026", entrada="2026 / 3 / 623888"):
    """Un PDF con el mismo texto que el «Acuse de recibo» real del Registro Mercantil."""
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, linea in enumerate(["ACUSE DE RECIBO", "Identificador", "WEB34833746", "Referencia del documento", referencia, "Enviado por", "EMPRESA A007", "NIF", "00000014Z", "Recibido en", "MADRID",
                               "Número de entrada", entrada, "Fecha", f"{fecha} 19:39:22", "D./Dña.", "00000014Z MARIA ELENA LOPEZ (R: B12345678)"]):
        c.drawString(50, 800 - 16 * i, linea)
    c.save()
    return buf.getvalue()


def test_lee_el_acuse_de_recibo():
    assert lo.leer_acuse(_pdf_acuse()) == {"identificador": "WEB34833746", "referencia": "B123456782025", "entrada": "2026 / 3 / 623888", "fecha": date(2026, 4, 8)}
    with pytest.raises(ErrorContable, match="no es un «Acuse de recibo»"):
        lo.leer_acuse(__import__("test_justificante_aeat").pdf_de_la_sede())


def test_registrar_el_envio_con_el_acuse(sesion, ej, tmp_path):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    leg = lo.generar_libros(sesion, ej, tmp_path, numeros={"diario": 6, "inventario": 7, "socios": 1, "actas": 2})
    leg = lo.registrar_envio(sesion, ej, tmp_path, pdf=_pdf_acuse())
    assert (leg.estado, leg.enviada_en, leg.referencia, leg.numero_entrada) == ("enviada", date(2026, 4, 8), "B123456782025", "2026 / 3 / 623888")
    assert (tmp_path / leg.acuse_ruta).read_bytes().startswith(b"%PDF") and leg.acuse_ruta.endswith("B123456782025_Acuse_Entrada.pdf")
    with pytest.raises(ErrorContable, match="ya constan enviados"):
        lo.generar_libros(sesion, ej, tmp_path)  # lo enviado no se vuelve a generar


def test_el_acuse_de_otro_ejercicio_o_el_futuro_no_valen(sesion, ej, tmp_path):
    with pytest.raises(ErrorContable, match="otro ejercicio o de otra empresa"):
        lo.registrar_envio(sesion, ej, tmp_path, pdf=_pdf_acuse(referencia="B123456782024"))
    with pytest.raises(ErrorContable, match="Falta la fecha"):
        lo.registrar_envio(sesion, ej, tmp_path)
    with pytest.raises(ErrorContable, match="futura"):
        lo.registrar_envio(sesion, ej, tmp_path, fecha=date(2999, 1, 1))
    leg = lo.registrar_envio(sesion, ej, tmp_path, fecha=date(2026, 4, 8), referencia="B123456782025")  # sin PDF, tecleado
    assert leg.estado == "enviada" and leg.acuse_ruta is None


def test_el_plazo_de_los_libros_avisa_y_se_calla_al_registrar_el_envio(sesion, ej, monkeypatch):
    from conta_pridalac.servicios.vigilancia import plazos_de_modelos

    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.PRIMER_EJERCICIO_LIBROS", 2025)

    def de_los_libros(dia):
        return [h for h in plazos_de_modelos(sesion, ej, dia) if h.referencia == "libros 2025"]

    assert de_los_libros(date(2026, 2, 28)) == []  # el plazo acaba el 30 de abril: el aviso empieza dos meses antes
    (h,) = de_los_libros(date(2026, 3, 1))
    assert (h.codigo, h.gravedad) == ("plazo_libros_proximo", "AVISO") and "30/04/2026" in h.mensaje and "sin empezar" in h.mensaje
    assert de_los_libros(date(2026, 4, 24))[0].codigo == "plazo_libros_ultima_semana"
    (h,) = de_los_libros(date(2026, 5, 4))
    assert h.codigo == "plazo_libros_vencido" and "hace 4 día(s)" in h.mensaje
    lo.registrar_envio(sesion, ej, ".", fecha=date(2026, 4, 8), referencia="B123456782025")
    assert de_los_libros(date(2026, 5, 4)) == []


def test_el_asistente_del_1t_pide_legalizar_los_libros_del_ano_anterior(sesion, ej, monkeypatch, tmp_path):
    from conta_pridalac.servicios import asistente_trimestre as asistente

    monkeypatch.setattr("conta_pridalac.servicios.asistente_trimestre.PRIMER_EJERCICIO_LIBROS", 2025)
    ej26 = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=ej.empresa)
    sesion.add(ej26)
    sesion.flush()

    def paso(periodo):
        return [p for p in asistente.pasos(sesion, ej.empresa, ej26, periodo, "Sin presentar", "Sin presentar") if "Legalizar los libros" in p.titulo]

    assert paso((date(2026, 4, 1), date(2026, 6, 30))) == []  # sólo en el primer trimestre
    (p,) = paso((date(2026, 1, 1), date(2026, 3, 31)))
    assert (p.estado, p.pantalla) == ("pendiente", "legalizacion-libros") and "libros de 2025" in p.titulo and "sin preparar" in p.detalle
    lo.registrar_envio(sesion, ej, tmp_path, fecha=date(2026, 4, 8), referencia="B123456782025")
    (p,) = paso((date(2026, 1, 1), date(2026, 3, 31)))
    assert p.estado == "hecho" and "08/04/2026" in p.detalle


def test_la_pantalla_registra_el_envio_con_el_acuse(cliente):
    _preparar_empresa(cliente)
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "registrar_envio"}, files={"acuse": ("acuse.pdf", _pdf_acuse(referencia="B123456782026", fecha="08/04/2026"), "application/pdf")})
    assert r.status_code == 200 and "Enviada el" in r.text and "08/04/2026" in r.text and "Ver el acuse (PDF)" in r.text
    s = _sesion(cliente)
    leg = s.scalar(select(Legalizacion))
    assert leg.estado == "enviada" and leg.numero_entrada == "2026 / 3 / 623888"
    descarga = cliente.get(f"{BASE}/{leg.id}/libro/acuse")
    assert descarga.status_code == 200 and descarga.content.startswith(b"%PDF")
    s.close()
    assert "Enviada al Registro" in cliente.get(f"{BASE}/tabla").text
