"""Borrador del 111, controles, fichero, registro con el PDF de la sede y pago."""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR
from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, PresentacionAeat, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero111 import casillas_de, leer
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.presentacion111 import controlar_111, crear_borrador, generar_fichero, lo_anterior, pago_del_periodo
from conta_pridalac.servicios.presentacion303 import hay_errores, registrar_presentacion
from conta_pridalac.servicios.modelo111 import calcular_111
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000132", "AGRICULTOR UNO"), ("57200001", "BANCO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000132")).one()
    sesion.add(Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def compra(sesion, ej, fecha, base="1000.00", iva="120.00", retencion="22.40", numero=1):
    total = D(base) + D(iva)
    return grabar_asiento(sesion, ej, tipo=2, numero=numero, sub=0, fecha=fecha, concepto="compra a agricultor", subtipo="M",
                          lineas=[LineaAsiento(c, D(i)) for c, i in (("62300000", base), ("47200000", iva), ("47510000", f"-{retencion}"), ("41000132", retencion), ("41000132", f"-{total}"))])


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


def test_trimestre_sin_retenciones_se_presenta_sin_actividad(sesion, ej, tmp_path):
    p, h = crear_borrador(sesion, ej, 1, usuario="javier")
    assert not hay_errores(h) and h == [] and p.tipo_declaracion == "N" and p.resultado == D("0.00") and p.modelo == "111" and p.periodo == "1T"
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    t = ruta.read_text(encoding="latin-1")
    assert len(t) == 1346 and leer(t)[6] == "N" and casillas_de(t) == {} and ruta.name == f"{p.id}_PRUEBA_AEAT_111_2026_1T.111" and p.fichero_nombre == "PRUEBA_AEAT_111_2026_1T.111"
    assert [e.evento for e in p.eventos] == ["creada", "fichero_generado"] and p.diseno_version == "DR111e16v18" and p.estado == "generada"


def test_con_retenciones_se_domicilia_y_el_fichero_lleva_las_casillas_y_el_iban(sesion, ej, tmp_path):
    compra(sesion, ej, date(2026, 11, 2))
    p, h = crear_borrador(sesion, ej, 4)
    assert p.tipo_declaracion == "U" and p.resultado == D("22.40") and not hay_errores(h)
    t = generar_fichero(sesion, ej, p, tmp_path).read_text(encoding="latin-1")
    assert leer(t)[6] == "U" and leer(t)[45].strip() == "ES9121000418450200051332" and casillas_de(t) == {7: D("1"), 8: D("1120.00"), 9: D("22.40"), 28: D("22.40"), 30: D("22.40")}


def test_los_controles_de_plazo_y_de_pago(sesion, ej, monkeypatch):
    compra(sesion, ej, date(2026, 11, 2))
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2027, 1, 16))  # el 4T se domicilia hasta el 15 de enero (estimado para 2026)
    p, h = crear_borrador(sesion, ej, 4)
    assert codigos(h, AVISO) >= {"domiciliacion_fuera_de_plazo"} and not hay_errores(h)  # estimado: sólo aviso
    ej.empresa.iban = None
    assert codigos(crear_borrador(sesion, ej, 4)[1], ERROR) == {"domiciliacion_sin_iban"}
    ej.empresa.iban = "ES9121000418450200051332"
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2026, 4, 16))  # el 1T 2026 sí tiene el plazo publicado
    compra(sesion, ej, date(2026, 2, 3), numero=2)
    assert codigos(crear_borrador(sesion, ej, 1)[1], ERROR) == {"domiciliacion_fuera_de_plazo"}
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2026, 4, 21))
    assert codigos(crear_borrador(sesion, ej, 1, domiciliar=False)[1]) >= {"presentacion_fuera_de_plazo", "nrc_pendiente"}
    assert codigos(crear_borrador(sesion, ej, 1, domiciliar=False, nrc="corto")[1], ERROR) == {"nrc_no_valido"}
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc="3036479211552SFK8Y016Y")
    assert not hay_errores(h) and p.tipo_declaracion == "I" and p.nrc_importe == D("22.40")
    compra(sesion, ej, date(2026, 2, 4), numero=3)  # cambia el importe: el NRC ya no vale
    assert codigos(crear_borrador(sesion, ej, 1, domiciliar=False, nrc="3036479211552SFK8Y016Y")[1], ERROR) == {"nrc_de_otro_importe"}


def test_un_trimestre_presentado_solo_admite_una_complementaria(sesion, ej, tmp_path):
    compra(sesion, ej, date(2026, 2, 3))
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="111", anio=2026, periodo=1, tipo=1, justificante="1116996603852", resultado=D("10.00"), casillas=json.dumps({"30": 10.0})))
    sesion.flush()
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 1)
    assert lo_anterior(sesion, ej.empresa_id, 2026, 1, "normal") == (None, None)
    previa, anterior = lo_anterior(sesion, ej.empresa_id, 2026, 1, "complementaria")
    assert previa.justificante == "1116996603852" and anterior == D("10.00")
    p, h = crear_borrador(sesion, ej, 1, tipo_presentacion="complementaria")
    c = json.loads(p.casillas)
    assert not hay_errores(h) and (c["28"], c["29"], c["30"]) == ("22.40", "-10.00", "12.40") and p.resultado == D("12.40")
    t = generar_fichero(sesion, ej, p, tmp_path).read_text(encoding="latin-1")
    assert leer(t)[42] == "X" and leer(t)[43] == "1116996603852" and p.fichero_nombre == "PRUEBA_AEAT_111_2026_1T_complementaria.111" and casillas_de(t)[29] == D("-10.00")


def test_una_complementaria_que_ingresaria_de_menos_no_se_admite(sesion, ej):
    compra(sesion, ej, date(2026, 2, 3))
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="111", anio=2026, periodo=1, tipo=1, justificante="1116996603852", resultado=D("50.00"), casillas=json.dumps({"30": 50.0})))
    sesion.flush()
    assert "complementaria_con_menos_retenciones" in codigos(crear_borrador(sesion, ej, 1, tipo_presentacion="complementaria")[1], ERROR)
    with pytest.raises(ErrorContable, match="No hay un 111"):
        crear_borrador(sesion, ej, 2, tipo_presentacion="complementaria")


def test_si_cambian_los_asientos_no_se_genera_con_el_borrador_viejo(sesion, ej, tmp_path):
    compra(sesion, ej, date(2026, 11, 2))
    p, _ = crear_borrador(sesion, ej, 4)
    compra(sesion, ej, date(2026, 11, 20), numero=2)
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, ej, p, tmp_path)


def test_registrar_la_presentacion_con_el_pdf_de_la_sede(sesion, ej, tmp_path):
    compra(sesion, ej, date(2026, 11, 2))
    p, _ = crear_borrador(sesion, ej, 4)
    generar_fichero(sesion, ej, p, tmp_path)
    pdf = pdf_de_la_sede(modelo="111", registro="202611100790771G", resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="14-01-2026 a las 10:00:00")
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf, usuario="javier")
    assert p.estado == "presentada" and p.justificante == "3036479211552" and p.csv == "CKRKN4WXFTXCU8QT"
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 4)
    otro = pdf_de_la_sede(modelo="303", registro="202630300790771G")
    q, _ = crear_borrador(sesion, ej, 3)
    generar_fichero(sesion, ej, q, tmp_path)
    with pytest.raises(ErrorContable, match="del modelo 303"):
        registrar_presentacion(sesion, ej, q, tmp_path, pdf=otro)  # un PDF de otro modelo no se acepta


def test_el_pago_se_ve_en_la_contabilidad(sesion, ej):
    compra(sesion, ej, date(2026, 11, 2))
    calculo = calcular_111(sesion, ej, 4)
    assert pago_del_periodo(sesion, ej, 4, D("0")) is None
    sin_pagar = pago_del_periodo(sesion, ej, 4, calculo[30])
    assert sin_pagar.pagado == D("0.00") and sin_pagar.pendiente == D("22.40") and sin_pagar.pagos == []
    grabar_asiento(sesion, ej, tipo=4, numero=9, sub=0, fecha=date(2026, 12, 31), concepto="otro", lineas=[LineaAsiento("47510000", D("5.00")), LineaAsiento("57200001", D("-5.00"))])  # dentro del trimestre: no cuenta
    assert pago_del_periodo(sesion, ej, 4, calculo[30]).pagado == D("0.00")
    siguiente = Ejercicio(anio=2027, fecha_inicio=date(2027, 1, 1), fecha_fin=date(2027, 12, 31), empresa=ej.empresa)
    sesion.add(siguiente)
    sesion.flush()
    grabar_asiento(sesion, siguiente, tipo=3, numero=1, sub=0, fecha=date(2027, 1, 20), concepto="HACIENDA PÚBLICA, ACREEDORA POR RETENCIONES PRACTICADAS",
                   lineas=[LineaAsiento("47510000", D("22.40")), LineaAsiento("57200001", D("-22.40"))])
    pagado = pago_del_periodo(sesion, ej, 4, calculo[30])
    assert pagado.pagado == D("22.40") and pagado.pendiente == D("0.00") and pagado.pagos[0][0] == date(2027, 1, 20)


def test_el_mensaje_de_un_trimestre_presentado_es_el_que_bloquea_y_no_otro_error(sesion, ej, monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion111.hoy", lambda: date(2026, 4, 16))  # además el plazo de domiciliar ya pasó
    compra(sesion, ej, date(2026, 2, 3))
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="111", anio=2026, periodo=1, tipo=1, justificante="1116996603852", resultado=D("22.40"), casillas=json.dumps({"30": 22.4})))
    sesion.flush()
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 1)
