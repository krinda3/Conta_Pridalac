"""Vigilancia de los plazos de los modelos 303, 111 y 190: aviso a dos meses, error en la última semana y al vencer."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR, auditar
from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaIva, PresentacionAeat, Tercero
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.vigilancia import plazos_de_la_empresa, plazos_de_modelos

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62300000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. RETENCIONES"), ("41000132", "AGRICULTOR UNO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000132")).one()
    sesion.add(Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def con_retenciones(sesion, ej):
    grabar_asiento(sesion, ej, tipo=2, numero=1, sub=0, fecha=date(2026, 2, 3), concepto="compra", subtipo="M",
                   lineas=[LineaAsiento(c, D(i)) for c, i in (("62300000", "1000.00"), ("47200000", "120.00"), ("47510000", "-22.40"), ("41000132", "22.40"), ("41000132", "-1120.00"))])


def presentar(sesion, ej, modelo, periodo):
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo=modelo, anio=ej.anio, periodo=periodo, tipo=1, casillas="{}"))
    sesion.flush()


def resumen(h):
    return sorted((x.codigo, x.gravedad, x.referencia) for x in h)


def test_sin_aviso_hasta_dos_meses_antes(sesion, ej):
    assert plazos_de_modelos(sesion, ej, date(2026, 2, 18)) == []  # el 1T vence el 20 de abril: el aviso empieza el 19 de febrero


def test_aviso_a_dos_meses(sesion, ej):
    h = plazos_de_modelos(sesion, ej, date(2026, 2, 19))
    assert resumen(h) == [("plazo_modelo_proximo", AVISO, "111 1T 2026"), ("plazo_modelo_proximo", AVISO, "303 1T 2026")]
    assert "vence el 20/04/2026" in h[0].mensaje and "sin empezar" in h[0].mensaje and "Para domiciliar el pago, hasta el 15/04/2026" in h[0].mensaje


def test_error_la_ultima_semana_y_el_ultimo_dia(sesion, ej):
    assert {x.gravedad for x in plazos_de_modelos(sesion, ej, date(2026, 4, 13))} == {ERROR}
    h = plazos_de_modelos(sesion, ej, date(2026, 4, 12))
    assert {x.codigo for x in h} == {"plazo_modelo_proximo"}  # quedan 8 días
    ultimo = plazos_de_modelos(sesion, ej, date(2026, 4, 20))
    assert {x.codigo for x in ultimo} == {"plazo_modelo_ultima_semana"} and "vence hoy" in ultimo[0].mensaje


def test_error_al_vencer_el_plazo(sesion, ej):
    h = plazos_de_modelos(sesion, ej, date(2026, 4, 22))
    assert resumen(h) == [("plazo_modelo_vencido", ERROR, "111 1T 2026"), ("plazo_modelo_vencido", ERROR, "303 1T 2026")]
    assert "NO está presentado" in h[0].mensaje and "directamente en la sede" in h[0].mensaje and "hace 2 día(s)" in h[0].mensaje


def test_lo_presentado_no_avisa(sesion, ej):
    presentar(sesion, ej, "303", 1)
    presentar(sesion, ej, "111", 1)
    assert plazos_de_modelos(sesion, ej, date(2026, 4, 22)) == []
    assert {x.referencia for x in plazos_de_modelos(sesion, ej, date(2026, 7, 22))} == {"303 2T 2026", "111 2T 2026"}


def test_dice_si_hay_borrador_o_fichero_generado(sesion, ej):
    sesion.add(PresentacionAeat(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo="1T", estado="generada"))
    sesion.add(PresentacionAeat(empresa_id=ej.empresa_id, modelo="111", anio=2026, periodo="1T", estado="borrador"))
    sesion.flush()
    mensajes = {x.referencia: x.mensaje for x in plazos_de_modelos(sesion, ej, date(2026, 4, 22))}
    assert "fichero generado pero sin registrar" in mensajes["303 1T 2026"] and "con un borrador" in mensajes["111 1T 2026"]


def test_el_190_solo_si_hubo_retenciones(sesion, ej):
    assert not any(x.referencia.startswith("190") for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)))
    con_retenciones(sesion, ej)
    h = [x for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)) if x.referencia.startswith("190")]
    assert [(x.codigo, x.gravedad) for x in h] == [("plazo_modelo_vencido", ERROR)] and "01/02/2027" in h[0].mensaje  # el 31 de enero de 2027 es domingo
    presentar(sesion, ej, "190", 0)
    assert not any(x.referencia.startswith("190") for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)))


def test_el_4t_y_el_190_del_ano_pasado_avisan_desde_el_ejercicio_siguiente(sesion, ej):
    con_retenciones(sesion, ej)
    for modelo, p in (("303", 1), ("303", 2), ("303", 3), ("111", 1), ("111", 2), ("111", 3), ("202", 3)):
        presentar(sesion, ej, modelo, p)
    ej27 = Ejercicio(anio=2027, fecha_inicio=date(2027, 1, 1), fecha_fin=date(2027, 12, 31), empresa=ej.empresa)
    sesion.add(ej27)
    sesion.flush()
    h = plazos_de_la_empresa(sesion, [ej, ej27], date(2027, 1, 15))
    assert resumen(h) == [("plazo_modelo_proximo", AVISO, "190 ejercicio 2026"), ("plazo_modelo_proximo", AVISO, "303 4T 2026"), ("plazo_modelo_ultima_semana", ERROR, "111 4T 2026")]
    assert [x.gravedad for x in h] == [ERROR, AVISO, AVISO]  # los errores van primero


def test_la_auditoria_solo_los_incluye_si_se_pide(sesion, ej, monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.hoy", lambda: date(2026, 4, 22))
    assert auditar(sesion, ej) == []
    assert {h.codigo for h in auditar(sesion, ej, con_plazos=True)} == {"plazo_modelo_vencido"}


def test_el_347_solo_si_alguien_supera_el_umbral(sesion, ej):
    tercero = sesion.scalars(select(Tercero)).one()
    tercero.codigo_postal = "13001"
    assert not any(x.referencia.startswith("347") for x in plazos_de_modelos(sesion, ej, date(2027, 3, 5)))
    f = Factura(ejercicio_id=ej.id, sentido="R", numero=1, fecha_contable=date(2026, 5, 1), fecha_factura=date(2026, 5, 1), tercero_id=tercero.id, total=D("3630.00"))
    f.ivas.append(FacturaIva(base=D("3000.00"), pct_iva=D("21"), cuota_iva=D("630.00")))
    sesion.add(f)
    sesion.flush()
    h = [x for x in plazos_de_modelos(sesion, ej, date(2027, 3, 5)) if x.referencia.startswith("347")]
    assert [(x.codigo, x.gravedad) for x in h] == [("plazo_modelo_vencido", ERROR)] and "01/03/2027" in h[0].mensaje  # el 28 de febrero de 2027 es domingo
    presentar(sesion, ej, "347", 0)
    assert not any(x.referencia.startswith("347") for x in plazos_de_modelos(sesion, ej, date(2027, 3, 5)))


def test_el_390_solo_si_hubo_iva_y_desde_2026(sesion, ej):
    tercero = sesion.scalars(select(Tercero)).one()
    assert not any(x.referencia.startswith("390") for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)))
    f = Factura(ejercicio_id=ej.id, sentido="E", numero=1, fecha_contable=date(2026, 5, 1), fecha_factura=date(2026, 5, 1), tercero_id=tercero.id, total=D("121.00"))
    f.ivas.append(FacturaIva(base=D("100.00"), pct_iva=D("21"), cuota_iva=D("21.00")))
    sesion.add(f)
    sesion.flush()
    h = [x for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)) if x.referencia.startswith("390")]
    assert [(x.codigo, x.gravedad) for x in h] == [("plazo_modelo_vencido", ERROR)] and "01/02/2027" in h[0].mensaje  # el 30 de enero de 2027 es sábado
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="390", anio=2026, periodo=0, tipo=1, casillas="{}"))
    sesion.flush()
    assert not any(x.referencia.startswith("390") for x in plazos_de_modelos(sesion, ej, date(2027, 2, 3)))
    ej25 = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=ej.empresa)
    sesion.add(ej25)
    sesion.flush()
    g = Factura(ejercicio_id=ej25.id, sentido="E", numero=1, fecha_contable=date(2025, 5, 1), fecha_factura=date(2025, 5, 1), tercero_id=tercero.id, total=D("121.00"))
    g.ivas.append(FacturaIva(base=D("100.00"), pct_iva=D("21"), cuota_iva=D("21.00")))
    sesion.add(g)
    sesion.flush()
    assert not any(x.referencia.startswith("390") for x in plazos_de_modelos(sesion, ej25, date(2026, 2, 3)))  # los 390 anteriores a Conta no se juzgan


def test_el_202_avisa_desde_el_3p_de_2026_y_lo_anterior_no_se_juzga(sesion, ej):
    def del_202(dia):
        return [h for h in plazos_de_modelos(sesion, ej, dia) if h.referencia.startswith("202")]

    assert del_202(date(2026, 10, 20)) == []  # el 3P vence el 21 de diciembre (el 20 es domingo): el aviso empieza dos meses antes
    h = del_202(date(2026, 11, 1))
    assert resumen(h) == [("plazo_modelo_proximo", AVISO, "202 3P 2026")] and "domiciliar" in h[0].mensaje
    assert del_202(date(2026, 12, 18))[0].gravedad == ERROR  # la última semana
    presentar(sesion, ej, "202", 3)
    assert del_202(date(2026, 12, 18)) == []
