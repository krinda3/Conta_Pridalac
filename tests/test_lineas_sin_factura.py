"""Líneas del extracto sin factura: tickets de la tarjeta, liquidación, pagos del socio…"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from conta_pridalac.db.modelos import Banco, Cuenta, Extracto, ExtractoLinea, Factura, MovimientoBanco, ReglaLinea, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.lineas_sin_factura import CUENTA, TICKET, Regla, aplicar, patron, preparar, propuestas, recordar, reglas_aprendidas
from test_trimestre import _saldo, contab  # noqa: F401 - contab es una fixture

D = Decimal


@pytest.fixture
def entorno(contab):
    sesion, ej, almacen = contab
    cuentas = {k: Cuenta(empresa_id=ej.empresa_id, codigo=k, nombre=n) for k, n in (("52100001", "TARJETA PTE PAGO"), ("55100000", "CUENTA CORRIENTE CON SOCIOS"), ("41090001", "TICKETS APARCAMIENTO"),
                                                                                         ("62900011", "GASTOS DE VIAJE LOCOMOCION"))}
    sesion.add_all(cuentas.values())
    sesion.flush()
    tarjeta = Banco(empresa_id=ej.empresa_id, numero=2, clase="B", nombre="TARJETA", cuenta_id=cuentas["52100001"].id)
    parking = Tercero(empresa_id=ej.empresa_id, clase="P", nombre="TICKETS APARCAMIENTO", nif="VARIOSPARKING", cuenta_id=cuentas["41090001"].id, cuenta_gasto_id=cuentas["62900011"].id)
    sesion.add_all([tarjeta, parking])
    sesion.flush()
    return sesion, ej, almacen, cuentas, tarjeta, parking


def linea(sesion, ej, banco, texto, importe, dia, mas=""):
    extracto = sesion.scalar(select(Extracto).where(Extracto.banco_id == banco.id)) or Extracto(empresa_id=ej.empresa_id, banco_id=banco.id, fichero="x.xlsx", huella=f"h{banco.id}", formato="bbva")
    sesion.add(extracto)
    sesion.flush()
    n = len(list(sesion.scalars(select(ExtractoLinea)))) + 1
    l = ExtractoLinea(extracto_id=extracto.id, empresa_id=ej.empresa_id, banco_id=banco.id, orden=n, fecha=date(2026, 9, dia), texto=texto, mas_datos=mas, importe=D(str(importe)), clave=f"k{n}")
    sesion.add(l)
    sesion.flush()
    return l


def test_el_concepto_se_reduce_a_sus_palabras_sin_cifras():
    assert patron("SEITT AP41") == patron("SEITT R2") == "seitt"
    assert patron("TAXI LICENCIA 05962") == "taxi licencia" and patron("V.NEGOCIOS CRED.") == "v negocios cred" and patron("************1052") == ""


def test_una_linea_se_lleva_a_una_cuenta_directa_con_su_fecha_y_su_importe(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    banco = sesion.scalars(select(Banco).where(Banco.nombre == "BANCO")).one()
    l = linea(sesion, ej, banco, "ADESLAS MADRID", -447.29, 3)
    recordar(sesion, ej.empresa_id, l, CUENTA, cuenta=cuentas["55100000"])
    p, = propuestas(sesion, ej.empresa_id, [l])
    assert p.regla.tratamiento == CUENTA and p.regla.describir() == "A la cuenta 55100000 CUENTA CORRIENTE CON SOCIOS"
    prep = preparar(sesion, ej, [p])
    r = aplicar(sesion, almacen, ej, prep.aplicables)
    m = sesion.scalars(select(MovimientoBanco)).one()
    assert (r.movimientos, r.tickets, m.fecha, m.texto, l.movimiento_id) == (1, 0, date(2026, 9, 3), "ADESLAS MADRID", m.id)
    assert (_saldo(sesion, "57200001"), _saldo(sesion, "55100000")) == (D("-447.29"), D("447.29"))


def test_un_ticket_es_una_factura_sin_iva_del_proveedor_generico_pagada_por_la_linea(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    a, b = linea(sesion, ej, tarjeta, "HOTEL PALACE", -19, 22), linea(sesion, ej, tarjeta, "HOTEL PALACE", -26.75, 22)
    recordar(sesion, ej.empresa_id, a, TICKET, tercero=parking)
    prep = preparar(sesion, ej, propuestas(sesion, ej.empresa_id, [a, b]))
    r = aplicar(sesion, almacen, ej, prep.aplicables)
    assert (r.tickets, r.movimientos) == (2, 0)
    facturas = {f.numero_factura: f for f in sesion.scalars(select(Factura))}
    assert sorted(facturas) == ["TARJ-260922-1", "TARJ-260922-2"]
    f = facturas["TARJ-260922-1"]
    assert (f.tercero.nombre, f.total, f.cuenta_contrapartida.codigo, f.fecha_contable, [(i.base, i.pct_iva, i.cuota_iva) for i in f.ivas]) == ("TICKETS APARCAMIENTO", D("19.00"), "62900011", date(2026, 9, 22), [(D("15.70"), D("21.00"), D("3.30"))])
    assert (_saldo(sesion, "52100001"), _saldo(sesion, "62900011"), _saldo(sesion, "47200000")) == (D("-45.75"), D("37.81"), D("7.94"))  # el importe lleva el IVA al 21 % incluido
    assert a.movimiento_id is not None and b.movimiento_id is not None and a.movimiento_id != b.movimiento_id
    c = linea(sesion, ej, tarjeta, "HOTEL PALACE", -10, 22)  # otro ticket del mismo día: sigue la numeración
    aplicar(sesion, almacen, ej, preparar(sesion, ej, propuestas(sesion, ej.empresa_id, [c])).aplicables)
    assert "TARJ-260922-3" in {f.numero_factura for f in sesion.scalars(select(Factura))}


def test_las_reglas_se_aprenden_de_la_contabilidad_anterior(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    banco = sesion.scalars(select(Banco).where(Banco.nombre == "BANCO")).one()
    historia = [linea(sesion, ej, banco, f"ADESLAS MADRID {i}", -17.97, 3 + i) for i in range(3)] + [linea(sesion, ej, tarjeta, f"HOTEL PALACE {i}", -10, 10 + i) for i in range(3)]
    for l in historia:
        recordar(sesion, ej.empresa_id, l, CUENTA if "ADESLAS" in l.texto else TICKET, cuenta=cuentas["55100000"] if "ADESLAS" in l.texto else None, tercero=None if "ADESLAS" in l.texto else parking)
    aplicar(sesion, almacen, ej, preparar(sesion, ej, propuestas(sesion, ej.empresa_id, historia)).aplicables)
    sesion.execute(delete(ReglaLinea))  # sin reglas manuales: sólo lo aprendido
    nuevas = [linea(sesion, ej, banco, "ADESLAS MADRID", -17.97, 20), linea(sesion, ej, tarjeta, "HOTEL PALACE", -30, 21), linea(sesion, ej, banco, "ALGO NUNCA VISTO", -5, 22), linea(sesion, ej, banco, "ADESLAS MADRID", 17.97, 23)]
    aprendidas = reglas_aprendidas(sesion, ej.empresa_id)
    assert aprendidas[("adeslas madrid", -1)].cuenta.codigo == "55100000" and aprendidas[("adeslas madrid", -1)].veces == 3 and aprendidas[("hotel palace", -1)].tercero.nombre == "TICKETS APARCAMIENTO"
    p = propuestas(sesion, ej.empresa_id, nuevas)
    assert [(x.regla.tratamiento if x.regla else None, x.regla.origen if x.regla else None) for x in p] == [(CUENTA, "aprendida"), (TICKET, "aprendida"), (None, None), (None, None)]  # lo desconocido y el abono del mismo concepto (el signo cuenta) no tienen regla


def test_un_descuento_se_contabiliza_como_un_abono_del_ticket_con_el_iva_en_negativo(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    gasto = cuentas["62900011"]
    consumo = linea(sesion, ej, tarjeta, "SOLRED", -100, 20)
    descuento = linea(sesion, ej, tarjeta, "DESCUENTO EXTRA SOLRED", 4.69, 30)
    P = type("P", (), {})
    pc, pd = P(), P()
    pc.linea, pc.regla, pd.linea, pd.regla = consumo, Regla(TICKET, tercero=parking, gasto=gasto), descuento, Regla(TICKET, tercero=parking, gasto=gasto)
    r = aplicar(sesion, almacen, ej, [pc, pd])
    assert r.tickets == 2
    abono = next(f for f in sesion.scalars(select(Factura)) if f.numero_factura == "TARJ-260930-1")
    assert (abono.total, [(i.base, i.cuota_iva) for i in abono.ivas]) == (D("-4.69"), [(D("-3.88"), D("-0.81"))])
    assert (_saldo(sesion, "52100001"), _saldo(sesion, "62900011"), _saldo(sesion, "47200000")) == (D("-95.31"), D("78.76"), D("16.55"))  # 100 − 4,69 pagados; el gasto y el IVA bajan con el abono


def test_nada_va_a_la_cuenta_de_su_propio_banco(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    cargo = linea(sesion, ej, tarjeta, "TAXI", -5, 30)
    prep = preparar(sesion, ej, [type("P", (), {"linea": cargo, "regla": Regla(CUENTA, cuenta=cuentas["52100001"])})()])
    assert prep.aplicables == [] and "su propio banco" in prep.omitidas[0][1]


def test_se_aplica_todo_o_nada(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    banco = sesion.scalars(select(Banco).where(Banco.nombre == "BANCO")).one()
    buena, mala = linea(sesion, ej, banco, "ADESLAS", -10, 3), linea(sesion, ej, tarjeta, "TAXI", -5, 4)
    P = type("P", (), {})
    pb, pm = P(), P()
    pb.linea, pb.regla, pm.linea, pm.regla = buena, Regla(CUENTA, cuenta=cuentas["55100000"]), mala, Regla(CUENTA, cuenta=cuentas["52100001"])  # la segunda va a la cuenta de su propio banco
    with pytest.raises(ErrorContable, match="su propio banco"):
        aplicar(sesion, almacen, ej, [pb, pm])
    assert buena.movimiento_id is None and not list(sesion.scalars(select(MovimientoBanco)))  # la buena tampoco se contabilizó


def test_las_cuentas_del_socio_y_de_la_tarjeta_tambien_se_aprenden_aunque_sean_bancos_en_conta(entorno):
    sesion, ej, almacen, cuentas, tarjeta, parking = entorno
    banco = sesion.scalars(select(Banco).where(Banco.nombre == "BANCO")).one()
    socio = Banco(empresa_id=ej.empresa_id, numero=3, clase="B", nombre="SOCIOS", cuenta_id=cuentas["55100000"].id)  # en Conta la cuenta del socio es un «banco»
    sesion.add(socio)
    sesion.flush()
    historia = [linea(sesion, ej, banco, f"MAPFRE VIDA {i}", -185.11, 2 + i) for i in range(2)]
    for l in historia:
        recordar(sesion, ej.empresa_id, l, CUENTA, cuenta=cuentas["55100000"])
    aplicar(sesion, almacen, ej, preparar(sesion, ej, propuestas(sesion, ej.empresa_id, historia)).aplicables)
    assert reglas_aprendidas(sesion, ej.empresa_id)[("mapfre vida", -1)].cuenta.codigo == "55100000"
