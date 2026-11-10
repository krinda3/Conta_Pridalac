"""Borrador del 347, controles, fichero, registro con el PDF de la sede y sustitutiva."""
import json
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.auditoria import AVISO, ERROR
from conta_pridalac.db.modelos import Ejercicio, Empresa, Factura, FacturaIva, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero347 import leer
from conta_pridalac.servicios.modelo347 import calcular_347
from conta_pridalac.servicios.presentacion347 import controlar_347, crear_borrador, generar_fichero, registrar
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def despues_del_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion347.hoy", lambda: date(2026, 3, 10))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", telefono="600 111 222", representante_nombre="PEREZ GOMEZ ANA")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    return ej


def tercero(sesion, ej, nombre="AGRICULTOR UNO", nif="12345678Z", cp="13001", **kw):
    t = Tercero(empresa_id=ej.empresa_id, clase="P", nombre=nombre, nif=nif, codigo_postal=cp, **kw)
    sesion.add(t)
    sesion.flush()
    return t


def factura(sesion, ej, t, numero, fecha, base, sentido="R"):
    base = D(base)
    cuota = (base * D("0.21")).quantize(D("0.01"))
    f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, tercero_id=t.id, total=base + cuota)
    f.ivas.append(FacturaIva(base=base, pct_iva=D("21"), cuota_iva=cuota))
    sesion.add(f)
    sesion.flush()


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


@pytest.fixture
def con_operaciones(sesion, ej):
    t = tercero(sesion, ej)
    factura(sesion, ej, t, 1, date(2025, 2, 3), "2000.00")
    factura(sesion, ej, t, 2, date(2025, 11, 3), "1000.00")
    return ej


def test_borrador_y_controles(sesion, con_operaciones):
    p, hallazgos = crear_borrador(sesion, con_operaciones)
    assert (p.modelo, p.periodo, p.estado, p.tipo_declaracion, p.resultado) == ("347", "0A", "borrador", "X", D("3630.00"))
    assert json.loads(p.casillas)["declarados"] == [["A", "12345678Z", "AGRICULTOR UNO", "13", ["2420.00", "0.00", "0.00", "1210.00"]]]
    assert codigos(hallazgos, ERROR) == set() and codigos(hallazgos, AVISO) == {"presentacion_fuera_de_plazo"}


def test_fuera_de_plazo_avisa(sesion, con_operaciones, monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion347.hoy", lambda: date(2026, 3, 3))
    assert "presentacion_fuera_de_plazo" in codigos(controlar_347(sesion, con_operaciones, calcular_347(sesion, con_operaciones)), AVISO)
    monkeypatch.setattr("conta_pridalac.servicios.presentacion347.hoy", lambda: date(2026, 3, 2))  # el plazo de 2025 termina el 2 de marzo de 2026
    assert "presentacion_fuera_de_plazo" not in codigos(controlar_347(sesion, con_operaciones, calcular_347(sesion, con_operaciones)))


def test_faltan_datos_de_la_empresa_y_de_los_terceros(sesion, ej):
    ej.empresa.telefono, ej.empresa.representante_nombre = None, " "
    sin_provincia = tercero(sesion, ej, "SIN PROVINCIA", "44444444A", cp=None)
    sin_nif = tercero(sesion, ej, "SIN NIF", None)
    factura(sesion, ej, sin_provincia, 1, date(2025, 3, 1), "5000.00")
    factura(sesion, ej, sin_nif, 2, date(2025, 3, 1), "5000.00")
    h = controlar_347(sesion, ej, calcular_347(sesion, ej))
    assert {"falta_telefono", "falta_contacto", "declarado_sin_provincia", "operado_sin_nif"} <= codigos(h, ERROR)
    p, _ = crear_borrador(sesion, ej)
    with pytest.raises(ErrorContable, match="No se puede generar el fichero"):
        generar_fichero(sesion, ej, p, "x")


def test_un_abono_deja_un_trimestre_negativo_y_avisa(sesion, ej):
    t = tercero(sesion, ej)
    factura(sesion, ej, t, 1, date(2025, 2, 3), "5000.00")
    factura(sesion, ej, t, 2, date(2025, 11, 3), "-100.00")
    assert "trimestre_negativo" in codigos(controlar_347(sesion, ej, calcular_347(sesion, ej)), AVISO)


def test_genera_el_fichero_con_su_identificativo(sesion, con_operaciones, tmp_path):
    p, _ = crear_borrador(sesion, con_operaciones)
    ruta = generar_fichero(sesion, con_operaciones, p, tmp_path)
    d = leer(ruta.read_bytes().decode("latin-1"))
    assert p.estado == "generada" and ruta.name == f"{p.id}_PRUEBA_AEAT_347_2025_0A.347" and ruta.stat().st_size == 1004
    assert (d.nif, d.ejercicio, d.contacto_telefono, d.contacto_nombre, d.sustitutiva) == ("B12345678", 2025, "600111222", "PEREZ GOMEZ ANA", False)
    assert d.identificativo.startswith("347") and len(d.identificativo) == 13
    assert [(x.clave, x.nif, x.provincia, x.trimestres) for x in d.declarados] == [("A", "12345678Z", "13", [D("2420.00"), D("0"), D("0"), D("1210.00")])]


def test_si_cambian_las_facturas_hay_que_guardar_el_borrador_de_nuevo(sesion, con_operaciones, tmp_path):
    p, _ = crear_borrador(sesion, con_operaciones)
    factura(sesion, con_operaciones, sesion.query(Tercero).one(), 3, date(2025, 6, 1), "100.00")
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, con_operaciones, p, tmp_path)


def _presentar(sesion, ej, tmp_path, justificante=None):
    p, _ = crear_borrador(sesion, ej)
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    ident = leer(ruta.read_bytes().decode("latin-1")).identificativo
    pdf = pdf_de_la_sede(modelo="347", registro="2025347009790900508614", justificante=justificante or ident, resultado="", nrc_importe=None, fecha="02-03-2026 a las 17:24:37")
    return p, ident, pdf


def test_registrar_con_el_pdf_de_la_sede_y_sustituir(sesion, con_operaciones, tmp_path):
    p, ident, pdf = _presentar(sesion, con_operaciones, tmp_path)
    registrar(sesion, con_operaciones, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada" and p.justificante == ident
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, con_operaciones)
    s, _ = crear_borrador(sesion, con_operaciones, tipo_presentacion="sustitutiva")
    assert s.tipo_presentacion == "sustitutiva" and s.anterior_id == p.id
    d = leer(generar_fichero(sesion, con_operaciones, s, tmp_path).read_bytes().decode("latin-1"))
    assert d.sustitutiva and d.identificativo_anterior == ident and d.identificativo != ident


def test_un_pdf_con_otro_justificante_no_se_registra(sesion, con_operaciones, tmp_path):
    p, ident, pdf = _presentar(sesion, con_operaciones, tmp_path, justificante="3470000000001")
    with pytest.raises(ErrorContable, match="lleva el " + ident):
        registrar(sesion, con_operaciones, p, tmp_path, pdf=pdf)
    assert p.estado == "generada"


def test_sin_operaciones_se_puede_presentar_sin_declarados(sesion, ej, tmp_path):
    p, h = crear_borrador(sesion, ej)
    assert "sin_declarados" in codigos(h, AVISO) and codigos(h, ERROR) == set()
    assert generar_fichero(sesion, ej, p, tmp_path).stat().st_size == 502
