"""Modelo 202: fichero (contra los ficheros reales del programa anterior), lectura del IS presentado, borrador, controles, registro de la presentación y pantalla."""
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio, Empresa, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero202
from conta_pridalac.ficheros_aeat.fichero202 import Declaracion202, datos_del_fichero, generar, pago
from conta_pridalac.servicios import impuesto_sociedades as isoc
from conta_pridalac.servicios.entorno import marcar_ensayo
from conta_pridalac.servicios.presentacion202 import calcular_202, controlar_202, crear_borrador, generar_fichero
from conta_pridalac.servicios.presentacion303 import registrar_presentacion
from test_justificante_aeat import pdf_de_la_sede
from test_web_auditoria import _sesion, cliente  # noqa: F401 - `cliente` es una fixture

D = Decimal
IBAN = "ES9121000418450200051332"


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


@pytest.fixture(autouse=True)
def en_el_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion202.hoy", lambda: date(2026, 12, 10))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", iban=IBAN)
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for anio, cuota in ((2024, "755.55"), (2025, "259.73")):
        sesion.add(DeclaracionPresentada(empresa_id=e.id, modelo="200", anio=anio, periodo=0, tipo=1, casillas=json.dumps({"562": cuota, "592": cuota, "1766": "0"})))
    sesion.flush()
    return ej


# ---------------------------------------------------------------------------------------------- fichero

def test_el_pago_es_el_18_por_ciento_de_la_base():
    assert pago(D("259.73")) == D("46.75") and pago(D("755.55")) == D("136.00") and pago(D("1203.79")) == D("216.68") and pago(D("-5")) == D("0.00")


def test_un_fichero_de_resultado_cero_y_otro_con_domiciliacion():
    cero = generar(Declaracion202(nif="B00000010", nombre="Empresa A S.L.", ejercicio=2026, periodo=2, inicio=date(2026, 1, 1), base=D("0"), a_ingresar=D("0"), tipo="N"))
    assert len(cero) == 328 + 700 + 900 + 18 and cero.startswith("<T202020262P0000><AUX>") and cero.endswith("</T20202000></T202020262P0000>")
    d = datos_del_fichero(cero)
    assert (d["tipo"], d["periodo"], d["ejercicio"], d["base"], d["a_ingresar"], d["modalidad"], d["iban"]) == ("N", 2, 2026, 0, 0, "A", "")
    u = datos_del_fichero(generar(Declaracion202(nif="B00000020", nombre="Empresa B S.L.", ejercicio=2026, periodo=3, inicio=date(2026, 1, 1), base=D("259.73"), a_ingresar=D("46.75"), tipo="U", iban=IBAN)))
    assert (u["tipo"], u["base"], u["a_ingresar"], u["iban"], u["tipo_gravamen"], u["inicio"]) == ("U", D("259.73"), D("46.75"), IBAN, "25", date(2026, 1, 1))


@pytest.mark.parametrize("campos, mensaje", [
    (dict(tipo="N", a_ingresar=D("1")), "no puede tener importe"), (dict(tipo="U", a_ingresar=D("0")), "tipo N"), (dict(tipo="U", a_ingresar=D("5"), iban=""), "IBAN"),
    (dict(tipo="I", a_ingresar=D("5"), complementaria=True), "justificante"), (dict(tipo="I", a_ingresar=D("5"), periodo=4), "tres pagos"),
])
def test_los_ficheros_incoherentes_se_rechazan(campos, mensaje):
    base = dict(nif="B1", nombre="X", ejercicio=2026, periodo=1, inicio=date(2026, 1, 1), base=D("10"), a_ingresar=D("1.8"), tipo="I")
    with pytest.raises(ErrorContable, match=mensaje):
        generar(Declaracion202(**{**base, **campos}))


def test_el_fichero_reproduce_byte_a_byte_los_202_reales_de_programa_anterior():
    import glob
    from pathlib import Path

    ficheros = sorted(glob.glob(str(Path(__file__).resolve().parents[1] / "AEAT" / "C000[12]_202_202[56]_[123]P.202")))
    if not ficheros:
        pytest.skip("No están los 202 del programa anterior en AEAT/")
    comprobados = 0
    for ruta in ficheros:
        t = Path(ruta).read_bytes().decode("latin-1")
        d, p1 = datos_del_fichero(t), fichero202.leer(t)["01000"]
        if d["tipo"] not in fichero202.TIPOS_DECLARACION or d["inicio"] is None:
            continue  # el 3P de 2026 de Empresa A es un fichero vacío
        nuevo = generar(Declaracion202(nif=d["nif"], nombre=d["nombre"], ejercicio=d["ejercicio"], periodo=d["periodo"], inicio=d["inicio"], base=d["base"], a_ingresar=d["a_ingresar"], tipo=d["tipo"],
                                       tipo_gravamen=d["tipo_gravamen"], cifra_menor_1m=p1[130] == "X", cnae=p1[118] if p1[118].strip("0 ") else "", iban=d["iban"], version_programa=t[92:96], nif_desarrollador=t[100:109]))
        assert nuevo == t, ruta
        comprobados += 1
    assert comprobados >= 8


# ---------------------------------------------------------------------------------------------- IS presentado

def _fichero_200(casillas: dict[int, int], ejercicio=2025, nif="B12345678") -> str:
    """Un .200 mínimo: la cabecera, la identificación y las páginas 14 y 14B con las casillas que se piden (en céntimos)."""
    def poner(pagina, pos, lon, valor):
        texto = f"N{abs(valor):0{lon - 1}d}" if valor < 0 else f"{valor:0{lon}d}"
        return pagina[: pos - 1] + texto + pagina[pos - 1 + lon:]

    ident = ("<T20001000>" + "  " + nif.ljust(9) + "EMPRESA DE PRUEBA".ljust(60)).ljust(1100 - 12) + "</T20001000>"
    p14 = ("<T20014000>" + "0" * 2000)[:1990] + "</T20014000>"
    p14b = ("<T20014B00>" + "0" * 1700)[:1690] + "</T20014B00>"
    for casilla, (etiqueta, pos, lon, _) in isoc.CASILLAS_200_2025.items():
        if casilla in casillas:
            if etiqueta == "14000":
                p14 = poner(p14, pos, lon, casillas[casilla])
            else:
                p14b = poner(p14b, pos, lon, casillas[casilla])
    return f"<T2000{ejercicio}0A0000><AUX>" + " " * 311 + "</AUX>" + ident + p14 + p14b + f"</T2000{ejercicio}0A0000>"


def test_lee_la_cuota_y_las_retenciones_de_un_200():
    d = isoc.leer_200(_fichero_200({552: 103890, 562: 25973, 592: 25973, 1766: 1000, 621: -22895}))
    assert (d.ejercicio, d.nif, d.nombre) == (2025, "B12345678", "EMPRESA DE PRUEBA")
    assert d.casillas[562] == D("259.73") and d.casillas[1766] == D("10.00") and d.casillas[621] == D("-228.95") and d.casillas[552] == D("1038.90")
    assert d.base_del_202 == D("249.73")


def test_un_200_de_un_ejercicio_sin_diseno_cargado_no_se_lee():
    with pytest.raises(ErrorContable, match="ejercicio 2026"):
        isoc.leer_200(_fichero_200({562: 1}, ejercicio=2026))


def test_se_importa_un_200_y_queda_como_is_de_referencia(sesion, ej):
    sesion.execute(DeclaracionPresentada.__table__.delete())
    estado, d = isoc.importar(sesion, _fichero_200({562: 25973, 592: 25973}), "x.200")
    assert estado == "nueva" and (d.modelo, d.anio, d.periodo) == ("200", 2025, 0) and isoc.base_de(d) == D("259.73")
    assert isoc.is_de_referencia(sesion, ej.empresa_id, 2026, 3) is d


def test_la_base_del_202_es_la_cuota_liquida_menos_las_retenciones():
    assert isoc.IS(2025, "", "", {562: D("259.73"), 592: D("259.73")}).base_del_202 == D("259.73")
    assert isoc.IS(2025, "", "", {562: D("300"), 592: D("259.73"), 1766: D("100")}).base_del_202 == D("159.73")
    assert isoc.IS(2025, "", "", {562: D("50"), 592: D("50"), 1766: D("100")}).base_del_202 == D("0")  # nunca negativa
    assert isoc.IS(2025, "", "", {552: D("-14532.46")}).base_del_202 == D("0")


def test_el_is_de_referencia_depende_del_periodo(sesion, ej):
    assert [isoc.is_de_referencia(sesion, ej.empresa_id, 2026, p).anio for p in (1, 2, 3)] == [2024, 2025, 2025]
    assert isoc.is_de_referencia(sesion, ej.empresa_id, 2027, 1).anio == 2025 and isoc.is_de_referencia(sesion, ej.empresa_id, 2028, 1) is None


def test_importa_un_202_presentado_una_sola_vez(sesion, ej):
    texto = generar(Declaracion202(nif="B12345678", nombre="Prueba", ejercicio=2026, periodo=1, inicio=date(2026, 1, 1), base=D("755.55"), a_ingresar=D("136.00"), tipo="U", iban=IBAN))
    estado, d = isoc.importar(sesion, texto, "x.202", date(2026, 4, 14))
    assert estado == "nueva" and (d.modelo, d.anio, d.periodo, d.resultado) == ("202", 2026, 1, D("136.00")) and json.loads(d.casillas) == {"1": "755.55", "3": "136.00"}
    assert isoc.importar(sesion, texto, "x.202")[0] == "ya estaba"
    otro = generar(Declaracion202(nif="B12345678", nombre="Prueba", ejercicio=2026, periodo=1, inicio=date(2026, 1, 1), base=D("1"), a_ingresar=D("0.18"), tipo="U", iban=IBAN))
    with pytest.raises(ErrorContable, match="otras cifras"):
        isoc.importar(sesion, otro, "y.202")
    ajeno = generar(Declaracion202(nif="B99999999", nombre="Otra", ejercicio=2026, periodo=1, inicio=date(2026, 1, 1), base=D("0"), a_ingresar=D("0"), tipo="N"))
    with pytest.raises(ErrorContable, match="ninguna empresa"):
        isoc.importar(sesion, ajeno, "z.202")


# ---------------------------------------------------------------------------------------------- borrador, fichero y registro

def test_calculo_de_cada_pago(sesion, ej):
    c1, c2, c3 = (calcular_202(sesion, ej, p) for p in (1, 2, 3))
    assert [(c.anio_is, c.base, c.pago) for c in (c1, c2, c3)] == [(2024, D("755.55"), D("136.00")), (2025, D("259.73"), D("46.75")), (2025, D("259.73"), D("46.75"))]


def test_sin_el_is_de_referencia_no_se_puede_preparar(sesion, ej):
    sesion.execute(DeclaracionPresentada.__table__.delete())
    h = controlar_202(sesion, ej, 3, calcular_202(sesion, ej, 3))
    assert "falta_el_is_de_referencia" in codigos(h, "ERROR")
    with pytest.raises(ErrorContable, match="Impuesto sobre Sociedades de 2025"):
        crear_borrador(sesion, ej, 3)


def test_borrador_fichero_y_registro_de_la_presentacion(sesion, ej, tmp_path):
    p, hallazgos = crear_borrador(sesion, ej, 3)
    assert not codigos(hallazgos, "ERROR") and (p.periodo, p.tipo_declaracion, p.resultado, p.estado) == ("3P", "U", D("46.75"), "borrador")
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    assert p.estado == "generada" and p.fichero_nombre == "PRUEBA_AEAT_202_2026_3P.202" and p.diseno_version == fichero202.DISENO_VERSION
    d = datos_del_fichero(ruta.read_bytes().decode("latin-1"))
    assert (d["tipo"], d["base"], d["a_ingresar"], d["iban"], d["periodo"]) == ("U", D("259.73"), D("46.75"), IBAN, 3)
    pdf = pdf_de_la_sede(modelo="202", registro="202620200790112R", justificante="2026202000123", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="20-10-2026 a las 12:08:39")
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada" and p.justificante == "2026202000123"
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 3)


def test_si_el_resultado_es_cero_el_fichero_va_como_negativa(sesion, ej, tmp_path):
    for d in sesion.scalars(select(DeclaracionPresentada)):
        d.casillas = json.dumps({"562": "0", "592": "0"})
    sesion.flush()
    p, _ = crear_borrador(sesion, ej, 3)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    assert p.tipo_declaracion == "N" and datos_del_fichero(ruta.read_bytes().decode("latin-1"))["tipo"] == "N"
    pdf = pdf_de_la_sede(modelo="202", registro="202620200790113R", justificante="2026202000124", resultado="NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO", nrc_importe=None, fecha="20-10-2026 a las 12:08:39")
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada"


def test_la_complementaria_resta_lo_ya_ingresado(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej, 3)
    generar_fichero(sesion, ej, p, tmp_path)
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede(modelo="202", registro="202620200790112R", justificante="2026202000123", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None,
                                                                       fecha="20-10-2026 a las 12:08:39"))
    for d in sesion.scalars(select(DeclaracionPresentada)):
        d.casillas = json.dumps({"562": "400.00", "592": "400.00"}) if d.anio == 2025 else d.casillas
    sesion.flush()
    c, h = crear_borrador(sesion, ej, 3, tipo_presentacion="complementaria")
    assert (c.resultado, c.anterior_id) == (D("25.25"), p.id)  # 72,00 - 46,75
    d = datos_del_fichero(generar_fichero(sesion, ej, c, tmp_path).read_bytes().decode("latin-1"))
    assert d["complementaria"] and d["resultado_anterior"] == D("46.75") and d["a_ingresar"] == D("25.25") and d["base"] == D("400.00")


def test_una_copia_de_ensayo_no_genera_el_202(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej, 3)
    marcar_ensayo(sesion, ej.empresa_id)
    with pytest.raises(ErrorContable, match="copia de ensayo"):
        generar_fichero(sesion, ej, p, tmp_path)


def test_el_borrador_se_invalida_si_cambia_el_is_de_referencia(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej, 3)
    for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.anio == 2025)):
        d.casillas = json.dumps({"562": "999.00", "592": "999.00"})
    sesion.flush()
    with pytest.raises(ErrorContable, match="guarde el borrador"):
        generar_fichero(sesion, ej, p, tmp_path)


# ---------------------------------------------------------------------------------------------- pantalla

BASE = "/e/prueba/2026/modelo-202"


def _preparar_web(cliente):
    s = _sesion(cliente)
    e = s.scalar(select(Empresa))
    e.nif, e.iban = "B12345678", IBAN
    ej = s.scalar(select(Ejercicio))
    ej.fecha_inicio = date(2026, 1, 1)
    for anio, cuota in ((2024, "755.55"), (2025, "259.73")):
        s.add(DeclaracionPresentada(empresa_id=e.id, modelo="200", anio=anio, periodo=0, tipo=1, casillas=json.dumps({"562": cuota, "592": cuota})))
    s.commit()
    s.close()


def test_la_pantalla_del_202(cliente, monkeypatch):
    _preparar_web(cliente)
    assert cliente.get(BASE).status_code == 200 and "202 · Pago fraccionado" in cliente.get("/e/prueba/2026").text
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "1P · abril 2026" in tabla and "3P · diciembre 2026" in tabla and "IS 2024" in tabla and "IS 2025" in tabla
    ficha = cliente.get(f"{BASE}/f/3").text
    for esperado in ("Modelo 202 · 3P · diciembre 2026", "Base del pago [01]", "259,73", "46,75", "Sin errores ni avisos"):
        assert esperado in ficha, esperado
    assert "755,55" in cliente.get(f"{BASE}/f/1").text and "136,00" in cliente.get(f"{BASE}/f/1").text
    assert "El 202 tiene tres pagos fraccionados" in cliente.get(f"{BASE}/f/4").text


def test_guardar_y_generar_desde_la_pantalla(cliente, monkeypatch):
    _preparar_web(cliente)
    r = cliente.post(f"{BASE}/guardar", data={"id": "3", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion", "nrc": ""})
    assert r.status_code == 200 and "Fichero generado" in r.text and "EMPRESA_DE_PRUEBA_AEAT_202_2026_3P.202" in r.text and "Presentar en la sede de la AEAT" in r.text
    s = _sesion(cliente)
    p = s.scalar(select(PresentacionAeat).where(PresentacionAeat.modelo == "202"))
    assert (p.estado, p.periodo, p.resultado, p.tipo_declaracion) == ("generada", "3P", D("46.75"), "U")
    descarga = cliente.get(f"{BASE}/{p.id}/fichero")
    assert descarga.status_code == 200 and datos_del_fichero(descarga.content.decode("latin-1"))["a_ingresar"] == D("46.75")
    s.close()
    # el 1P ya pasó el plazo de domiciliar: se puede guardar el borrador, pero no generar el fichero
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion", "nrc": ""})
    assert "domiciliar terminó" in r.text and "Generar el fichero</button>" in r.text
    s = _sesion(cliente)
    assert s.scalar(select(PresentacionAeat.estado).where(PresentacionAeat.modelo == "202", PresentacionAeat.periodo == "1P")) == "borrador"
    s.close()


def test_un_202_incompleto_no_se_toma_por_presentado(sesion, ej):
    """El programa anterior dejó un 202 del 3P de 2026 generado en enero de 2026, sin fecha de inicio ni tipo de gravamen: no es una declaración."""
    texto = generar(Declaracion202(nif="B12345678", nombre="Prueba", ejercicio=2026, periodo=3, inicio=date(2026, 1, 1), base=D("0"), a_ingresar=D("0"), tipo="N"))
    incompleto = texto[:328 + 109] + "00000000" + texto[328 + 117:]  # fecha de inicio a ceros
    incompleto = incompleto[:328 + 131] + " " * 15 + incompleto[328 + 146:]  # sin tipo de gravamen
    with pytest.raises(ErrorContable, match="incompleto"):
        isoc.importar(sesion, incompleto, "3P.202")
    assert datos_del_fichero(incompleto)["inicio"] is None


def test_se_puede_quitar_una_declaracion_importada_por_error(sesion, ej):
    isoc.importar(sesion, generar(Declaracion202(nif="B12345678", nombre="Prueba", ejercicio=2026, periodo=1, inicio=date(2026, 1, 1), base=D("755.55"), a_ingresar=D("136.00"), tipo="U", iban=IBAN)), "x.202")
    assert isoc.quitar_importada(sesion, ej.empresa_id, "202", 2026, 1) == 1 and isoc.quitar_importada(sesion, ej.empresa_id, "202", 2026, 1) == 0
    assert sesion.scalar(select(DeclaracionPresentada).where(DeclaracionPresentada.modelo == "202")) is None
