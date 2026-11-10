"""Borrador del 190, controles, fichero, registro con el PDF de la sede y sustitutiva."""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR
from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, PresentacionAeat, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero190 import leer
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.modelo190 import calcular_190
from conta_pridalac.servicios.presentacion190 import controlar_190, crear_borrador, generar_fichero, registrar
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def despues_del_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion190.hoy", lambda: date(2026, 2, 10))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", telefono="600 111 222", representante_nombre="PEREZ GOMEZ ANA", email="ana@prueba.es")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000132", "AGRICULTOR UNO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000132")).one()
    sesion.add(Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", cuenta_id=cuenta.id, provincia_190="13", clave_190="H", subclave_190="03"))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=2, numero=1, sub=0, fecha=date(2025, 2, 3), concepto="compra a agricultor", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62300000", "1000.00"), ("47200000", "120.00"), ("47510000", "-22.40"), ("41000132", "22.40"), ("41000132", "-1120.00"))])
    return ej


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


def test_borrador_y_controles_de_un_ano_con_un_perceptor(sesion, ej):
    p, hallazgos = crear_borrador(sesion, ej)
    assert (p.modelo, p.periodo, p.estado, p.tipo_declaracion, p.resultado) == ("190", "0A", "borrador", "X", D("22.40"))
    assert json.loads(p.casillas)["perceptores"] == [["12345678Z", "AGRICULTOR UNO", "13", "H", "03", "1120.00", "22.40"]]
    assert codigos(hallazgos, ERROR) == set()
    assert codigos(hallazgos, AVISO) == {"111_sin_presentar", "presentacion_fuera_de_plazo"}


def test_faltan_datos_de_la_empresa_y_del_perceptor(sesion, ej):
    ej.empresa.telefono, ej.empresa.representante_nombre = None, " "
    t = sesion.scalars(select(Tercero)).one()
    t.clave_190 = None
    h = controlar_190(sesion, ej, calcular_190(sesion, ej))
    assert {"falta_telefono", "falta_contacto", "perceptor_incompleto"} <= codigos(h, ERROR)
    with pytest.raises(ErrorContable, match="No se puede generar el fichero"):
        p, _ = crear_borrador(sesion, ej)
        generar_fichero(sesion, ej, p, "x")


def test_cuadra_o_no_con_los_111_presentados(sesion, ej):
    for t in (1, 2, 3, 4):
        sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="111", anio=2025, periodo=t, tipo=1, casillas=json.dumps({"8": 1120.0, "9": 22.4}) if t == 1 else "{}"))
    sesion.flush()
    assert "no_cuadra_con_los_111" not in codigos(controlar_190(sesion, ej, calcular_190(sesion, ej)))
    sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.periodo == 2)).one().casillas = json.dumps({"8": 100.0, "9": 2.0})
    h = controlar_190(sesion, ej, calcular_190(sesion, ej))
    assert {"no_cuadra_con_los_111", "no_cuadra_con_los_111_percepciones"} <= codigos(h, AVISO)


def test_genera_el_fichero_con_su_identificativo(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    d = leer(ruta.read_bytes().decode("latin-1"))
    assert p.estado == "generada" and ruta.name == f"{p.id}_PRUEBA_AEAT_190_2025_0A.190" and ruta.stat().st_size == 1004
    assert (d.nif, d.ejercicio, d.contacto_telefono, d.contacto_nombre, d.sustitutiva) == ("B12345678", 2025, "600111222", "PEREZ GOMEZ ANA", False)
    assert d.identificativo.startswith("190") and len(d.identificativo) == 13 and d.email == "ANA@PRUEBA.ES"
    assert [(x.nif, x.provincia + x.clave + x.subclave, x.percepcion, x.retencion) for x in d.percepciones] == [("12345678Z", "13H03", D("1120.00"), D("22.40"))]


def test_si_cambia_la_contabilidad_hay_que_guardar_el_borrador_de_nuevo(sesion, ej, tmp_path):
    p, _ = crear_borrador(sesion, ej)
    grabar_asiento(sesion, ej, tipo=2, numero=2, sub=0, fecha=date(2025, 5, 3), concepto="otra", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62300000", "100.00"), ("47510000", "-2.00"), ("41000132", "2.00"), ("41000132", "-100.00"))])
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, ej, p, tmp_path)


def _presentar(sesion, ej, tmp_path, justificante=None):
    p, _ = crear_borrador(sesion, ej)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    ident = leer(ruta.read_bytes().decode("latin-1")).identificativo
    pdf = pdf_de_la_sede(modelo="190", registro="2025190009950902801851", justificante=justificante or ident, resultado="", nrc_importe=None, fecha="20-01-2026 a las 17:24:37")
    return p, ident, pdf


def test_registrar_con_el_pdf_de_la_sede_y_sustituir(sesion, ej, tmp_path):
    p, ident, pdf = _presentar(sesion, ej, tmp_path)
    registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada" and p.justificante == ident
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej)
    s, hallazgos = crear_borrador(sesion, ej, tipo_presentacion="sustitutiva")
    assert s.tipo_presentacion == "sustitutiva" and s.anterior_id == p.id
    d = leer(generar_fichero(sesion, ej, s, tmp_path).read_bytes().decode("latin-1"))
    assert d.sustitutiva and d.identificativo_anterior == ident and d.identificativo != ident


def test_un_pdf_con_otro_justificante_no_se_registra(sesion, ej, tmp_path):
    p, ident, pdf = _presentar(sesion, ej, tmp_path, justificante="1900000000001")
    with pytest.raises(ErrorContable, match="lleva el " + ident):
        registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "generada"


def test_sin_retenciones_se_puede_presentar_sin_perceptores(sesion, ej, tmp_path):
    for a in list(ej.empresa.ejercicios[0].asientos) if hasattr(ej, "asientos") else []:
        sesion.delete(a)
    ej2 = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=ej.empresa)
    sesion.add(ej2)
    sesion.flush()
    p, h = crear_borrador(sesion, ej2)
    assert "sin_perceptores" in codigos(h, AVISO) and codigos(h, ERROR) == set()
    assert generar_fichero(sesion, ej2, p, tmp_path).stat().st_size == 502
