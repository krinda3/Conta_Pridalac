"""Borrador del 180, controles, fichero, registro con el PDF de la sede y sustitutiva."""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR
from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero180 import leer
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.modelo180 import calcular_180
from conta_pridalac.servicios.presentacion180 import controlar_180, crear_borrador, generar_fichero, registrar
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def despues_del_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion180.hoy", lambda: date(2026, 2, 10))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", telefono="600 111 222", representante_nombre="PEREZ GOMEZ ANA")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000001", "CASERO UNO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000001")).one()
    sesion.add(Tercero(empresa_id=e.id, clase="P", nombre="CASERO UNO", nif="12345678Z", cuenta_id=cuenta.id, provincia_190="13", inmueble_situacion="1", inmueble_catastro="1234567VK1234S0001AB",
                       inmueble_tipo_via="CL", inmueble_via="MAYOR", inmueble_numero="12", inmueble_municipio="CIUDAD REAL", inmueble_codigo_municipio="13034", inmueble_provincia="13",
                       inmueble_codigo_postal="13001"))
    sesion.flush()
    for i, mes in enumerate((2, 5), start=1):
        grabar_asiento(sesion, ej, tipo=2, numero=i, sub=0, fecha=date(2025, mes, 3), concepto="alquiler del local", subtipo="M",
                       lineas=[LineaAsiento(c, D(v)) for c, v in (("62100000", "1000.00"), ("47510000", "-190.00"), ("41000001", "-810.00"))])
    return ej


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


def test_borrador_y_controles_de_un_ano_con_un_arrendador(sesion, ej):
    p, hallazgos = crear_borrador(sesion, ej)
    assert (p.modelo, p.periodo, p.estado, p.tipo_declaracion, p.resultado) == ("180", "0A", "borrador", "X", D("380.00"))
    c = json.loads(p.casillas)
    assert c["arrendadores"][0][:6] == ["12345678Z", "CASERO UNO", "13", "2000.00", "19.00", "380.00"] and c["bases"] == "2000.00" and c["retenciones"] == "380.00"
    assert codigos(hallazgos, ERROR) == set()
    assert codigos(hallazgos, AVISO) == {"115_sin_presentar", "presentacion_fuera_de_plazo"}


def test_faltan_datos_de_la_empresa_y_del_arrendador(sesion, ej):
    ej.empresa.telefono, ej.empresa.representante_nombre = None, " "
    sesion.scalars(select(Tercero)).one().inmueble_catastro = None
    h = controlar_180(sesion, ej, calcular_180(sesion, ej))
    assert {"falta_telefono", "falta_contacto", "arrendador_incompleto"} <= codigos(h, ERROR)
    with pytest.raises(ErrorContable, match="No se puede generar el fichero"):
        p, _ = crear_borrador(sesion, ej)
        generar_fichero(sesion, ej, p, "x")


def test_los_datos_que_solo_conviene_completar_son_un_aviso(sesion, ej):
    t = sesion.scalars(select(Tercero)).one()
    t.inmueble_tipo_via = t.inmueble_codigo_municipio = None
    h = controlar_180(sesion, ej, calcular_180(sesion, ej))
    assert "arrendador_con_datos_por_completar" in codigos(h, AVISO) and "arrendador_incompleto" not in codigos(h)


def test_cuadra_o_no_con_los_115_presentados(sesion, ej):
    for t in (1, 2, 3, 4):
        sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="115", anio=2025, periodo=t, tipo=1, casillas=json.dumps({"2": 1000.0, "3": 190.0}) if t in (1, 2) else "{}"))
    sesion.flush()
    assert "no_cuadra_con_los_115" not in codigos(controlar_180(sesion, ej, calcular_180(sesion, ej)))
    sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.periodo == 3)).one().casillas = json.dumps({"2": 100.0, "3": 19.0})
    h = controlar_180(sesion, ej, calcular_180(sesion, ej))
    assert {"no_cuadra_con_los_115", "no_cuadra_con_los_115_bases"} <= codigos(h, AVISO)


def test_genera_el_fichero_con_su_identificativo(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    d = leer(ruta.read_bytes().decode("latin-1"))
    assert p.estado == "generada" and ruta.name == f"{p.id}_PRUEBA_AEAT_180_2025_0A.180" and ruta.stat().st_size == 1004
    assert (d.nif, d.ejercicio, d.contacto_telefono, d.contacto_nombre, d.sustitutiva) == ("B12345678", 2025, "600111222", "PEREZ GOMEZ ANA", False)
    assert d.identificativo.startswith("180") and len(d.identificativo) == 13
    a = d.percepciones[0]
    assert (a.nif, a.provincia, a.base, a.porcentaje, a.retencion) == ("12345678Z", "13", D("2000.00"), D("19.00"), D("380.00"))
    assert (a.inmueble.situacion, a.inmueble.catastro, a.inmueble.via, a.inmueble.codigo_postal) == ("1", "1234567VK1234S0001AB", "MAYOR", "13001")


def test_si_cambia_la_contabilidad_o_la_ficha_hay_que_guardar_el_borrador_de_nuevo(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej)
    sesion.scalars(select(Tercero)).one().inmueble_via = "OTRA CALLE"
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, ej, p, tmp_path)


def _presentar(sesion, ej, tmp_path, justificante=None):
    p, _ = crear_borrador(sesion, ej)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    ident = leer(ruta.read_bytes().decode("latin-1")).identificativo
    pdf = pdf_de_la_sede(modelo="180", registro="2025180009950902801851", justificante=justificante or ident, resultado="", nrc_importe=None, fecha="20-01-2026 a las 17:24:37")
    return p, ident, pdf


def test_registrar_con_el_pdf_de_la_sede_y_sustituir(sesion, ej, tmp_path):
    p, ident, pdf = _presentar(sesion, ej, tmp_path)
    registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada" and p.justificante == ident
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej)
    s, _ = crear_borrador(sesion, ej, tipo_presentacion="sustitutiva")
    assert s.tipo_presentacion == "sustitutiva" and s.anterior_id == p.id
    d = leer(generar_fichero(sesion, ej, s, tmp_path).read_bytes().decode("latin-1"))
    assert d.sustitutiva and d.identificativo_anterior == ident and d.identificativo != ident


def test_un_pdf_con_otro_justificante_no_se_registra(sesion, ej, tmp_path):
    p, ident, pdf = _presentar(sesion, ej, tmp_path, justificante="1800000000001")
    with pytest.raises(ErrorContable, match="lleva el " + ident):
        registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "generada"


def test_sin_alquileres_se_puede_presentar_sin_arrendadores(sesion, ej, tmp_path):
    ej2 = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=ej.empresa)
    sesion.add(ej2)
    sesion.flush()
    p, h = crear_borrador(sesion, ej2)
    assert "sin_arrendadores" in codigos(h, AVISO) and codigos(h, ERROR) == set()
    assert generar_fichero(sesion, ej2, p, tmp_path).stat().st_size == 502
