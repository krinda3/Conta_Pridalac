"""Borrador del 115, controles, fichero, complementaria y registro con el PDF de la sede."""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero115 import casillas_de, leer
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.presentacion115 import crear_borrador, generar_fichero, lo_anterior
from conta_pridalac.servicios.presentacion303 import hay_errores, registrar_presentacion
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))
    monkeypatch.setattr("conta_pridalac.servicios.presentacion115.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Asociación de Prueba", nif="G12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000001", "CASERO UNO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000001")).one()
    sesion.add(Tercero(empresa_id=e.id, clase="P", nombre="CASERO UNO", nif="12345678Z", cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def alquiler(sesion, ej, fecha, renta="1000.00", iva="210.00", retencion="190.00", numero=1):
    total = D(renta) + D(iva) - D(retencion)
    return grabar_asiento(sesion, ej, tipo=2, numero=numero, sub=0, fecha=fecha, concepto="alquiler del local", subtipo="M",
                          lineas=[LineaAsiento(c, D(i)) for c, i in (("62100000", renta), ("47200000", iva), ("47510000", f"-{retencion}"), ("41000001", f"-{total}"))])


def test_trimestre_sin_alquileres_se_presenta_sin_actividad(sesion, ej, tmp_path):
    p, h = crear_borrador(sesion, ej, 1, usuario="javier")
    assert not hay_errores(h) and p.tipo_declaracion == "N" and p.resultado == D("0.00") and p.modelo == "115" and p.periodo == "1T"
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    t = ruta.read_text(encoding="latin-1")
    assert len(t) == 846 and leer(t)[6] == "N" and casillas_de(t) == {} and p.fichero_nombre == "ASOCIACION_DE_PRUEBA_AEAT_115_2026_1T.115" or p.fichero_nombre.endswith("_AEAT_115_2026_1T.115")
    assert p.diseno_version == "DR115e15v13" and p.estado == "generada"


def test_con_alquiler_se_domicilia_y_el_fichero_lleva_las_casillas_y_el_iban(sesion, ej, tmp_path):
    alquiler(sesion, ej, date(2026, 11, 2))
    p, h = crear_borrador(sesion, ej, 4)
    assert p.tipo_declaracion == "U" and p.resultado == D("190.00") and not hay_errores(h)
    t = generar_fichero(sesion, ej, p, tmp_path).read_text(encoding="latin-1")
    assert leer(t)[6] == "U" and leer(t)[19].strip() == "ES9121000418450200051332" and casillas_de(t) == {1: D("1"), 2: D("1000.00"), 3: D("190.00"), 5: D("190.00")}


def test_complementaria_resta_lo_presentado(sesion, ej, tmp_path):
    alquiler(sesion, ej, date(2026, 2, 3))
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="115", anio=2026, periodo=1, tipo=1, justificante="1156996603852", resultado=D("100.00"), casillas=json.dumps({"5": 100.0})))
    sesion.flush()
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 1)
    previa, anterior = lo_anterior(sesion, ej.empresa_id, 2026, 1, "complementaria")
    assert previa.justificante == "1156996603852" and anterior == D("100.00")
    p, h = crear_borrador(sesion, ej, 1, tipo_presentacion="complementaria")
    c = json.loads(p.casillas)
    assert not hay_errores(h) and (c["3"], c["4"], c["5"]) == ("190.00", "100.00", "90.00") and p.resultado == D("90.00")
    t = generar_fichero(sesion, ej, p, tmp_path).read_text(encoding="latin-1")
    assert leer(t)[17] == "X" and leer(t)[18] == "1156996603852" and casillas_de(t)[4] == D("100.00")


def test_una_complementaria_que_ingresaria_de_menos_no_se_admite(sesion, ej):
    alquiler(sesion, ej, date(2026, 2, 3))
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="115", anio=2026, periodo=1, tipo=1, justificante="1156996603852", resultado=D("500.00"), casillas=json.dumps({"5": 500.0})))
    sesion.flush()
    assert "complementaria_con_menos_retenciones" in {x.codigo for x in crear_borrador(sesion, ej, 1, tipo_presentacion="complementaria")[1] if x.gravedad == ERROR}
    with pytest.raises(ErrorContable, match="No hay un 115"):
        crear_borrador(sesion, ej, 2, tipo_presentacion="complementaria")


def test_si_cambian_los_asientos_no_se_genera_con_el_borrador_viejo(sesion, ej, tmp_path):
    alquiler(sesion, ej, date(2026, 11, 2))
    p, _ = crear_borrador(sesion, ej, 4)
    alquiler(sesion, ej, date(2026, 11, 20), numero=2)
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, ej, p, tmp_path)


def test_registrar_la_presentacion_con_el_pdf_de_la_sede(sesion, ej, tmp_path):
    alquiler(sesion, ej, date(2026, 11, 2))
    p, _ = crear_borrador(sesion, ej, 4)
    generar_fichero(sesion, ej, p, tmp_path)
    pdf = pdf_de_la_sede(modelo="115", registro="202611500790771G", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="14-01-2026 a las 10:00:00")
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf, usuario="javier")
    assert p.estado == "presentada" and p.justificante and p.csv
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 4)
