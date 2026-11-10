from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR, auditar, hay_errores
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaIva
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.facturas import grabar_factura

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62900000", "OTROS SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("41000186", "IDV"), ("57200001", "BANCO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return ej


def _cuenta(sesion, codigo):
    return sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()


def _factura_correcta(sesion, ej, numero_factura="A-1"):
    f = Factura(
        sentido="R", fecha_contable=date(2026, 9, 30), fecha_factura=date(2026, 9, 8), numero_factura=numero_factura,
        cuenta_tercero_id=_cuenta(sesion, "41000186").id, cuenta_contrapartida_id=_cuenta(sesion, "62900000").id,
        total=D("36.77"),
    )
    f.ivas.append(FacturaIva(base=D("30.38"), pct_iva=D("21.00"), cuota_iva=D("6.39"), cuenta_iva_id=_cuenta(sesion, "47200000").id))
    return grabar_factura(sesion, ej, f).factura


def codigos(hallazgos):
    return Counter(h.codigo for h in hallazgos)


def test_una_contabilidad_correcta_no_tiene_hallazgos(sesion, ej):
    _factura_correcta(sesion, ej)
    assert auditar(sesion, ej) == []


def test_detecta_un_asiento_descuadrado_creado_a_traves_de_la_base_de_datos(sesion, ej):
    """Aunque el servicio lo impide, la auditoría debe cazarlo si llega por otra vía (importación, SQL…)."""
    a = Asiento(ejercicio_id=ej.id, tipo=4, numero=1, fecha=date(2026, 1, 5), numero_diario=1)
    a.apuntes.append(Apunte(orden=1, cuenta_id=_cuenta(sesion, "62900000").id, debe=D("30.38")))
    a.apuntes.append(Apunte(orden=2, cuenta_id=_cuenta(sesion, "41000186").id, haber=D("34.56")))
    sesion.add(a)
    sesion.flush()
    h = auditar(sesion, ej)
    assert codigos(h)["asiento_descuadrado"] == 1 and hay_errores(h)
    assert "-4.18" in next(x for x in h if x.codigo == "asiento_descuadrado").mensaje


def test_detecta_asiento_fuera_del_ejercicio_y_factura_sin_asiento(sesion, ej):
    f = _factura_correcta(sesion, ej)
    sesion.delete(sesion.scalars(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == f.numero)).one())
    sesion.flush()
    grabar = Asiento(ejercicio_id=ej.id, tipo=4, numero=9, fecha=date(2025, 12, 31), numero_diario=7)
    grabar.apuntes.append(Apunte(orden=1, cuenta_id=_cuenta(sesion, "62900000").id, debe=D("1")))
    grabar.apuntes.append(Apunte(orden=2, cuenta_id=_cuenta(sesion, "41000186").id, haber=D("1")))
    sesion.add(grabar)
    sesion.flush()
    c = codigos(auditar(sesion, ej))
    assert c["factura_sin_asiento"] == 1 and c["asiento_fuera_del_ejercicio"] == 1


def test_detecta_el_asiento_que_no_coincide_con_su_factura(sesion, ej):
    f = _factura_correcta(sesion, ej)
    a = sesion.scalars(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == f.numero)).one()
    gasto = next(ap for ap in a.apuntes if ap.cuenta.codigo == "62900000")
    gasto.debe += D("10.00")
    proveedor = next(ap for ap in a.apuntes if ap.cuenta.codigo == "41000186")
    proveedor.haber += D("10.00")  # sigue cuadrando, pero ya no es el asiento de la factura
    sesion.flush()
    c = codigos(auditar(sesion, ej))
    assert c["asiento_distinto_del_regenerado"] == 1 and "asiento_descuadrado" not in c


def test_detecta_un_asiento_huerfano_y_huecos_en_el_diario(sesion, ej):
    _factura_correcta(sesion, ej)
    grabar_asiento(sesion, ej, tipo=2, numero=77, fecha=date(2026, 2, 1), lineas=[LineaAsiento("62900000", D("5")), LineaAsiento("41000186", D("-5"))])
    sesion.scalars(select(Asiento).where(Asiento.numero == 77)).one().numero_diario = 5
    sesion.flush()
    c = codigos(auditar(sesion, ej))
    assert c["asiento_sin_documento"] == 1 and c["hueco_en_el_diario"] == 1


def test_saldos_de_terceros_con_signo_raro_con_el_importe_correcto(sesion, ej):
    """Regresión: el importe del mensaje es el real (58,85 €), no céntimos (5885)."""
    sesion.add_all([Cuenta(empresa_id=ej.empresa_id, codigo="43000001", nombre="CLIENTE X")])
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 2, 1), agrupar=False, lineas=[
        LineaAsiento("62900000", D("58.85")), LineaAsiento("43000001", D("-58.85")),   # cliente con saldo acreedor
        LineaAsiento("41000186", D("58.85")), LineaAsiento("57200001", D("-58.85")),   # proveedor con saldo deudor
    ])
    mensajes = {h.referencia: h.mensaje for h in auditar(sesion, ej) if h.codigo == "saldo_con_signo_raro"}
    assert "saldo acreedor -58.85" in mensajes["43000001"]
    assert "saldo deudor 58.85" in mensajes["41000186"]


def test_el_total_incoherente_es_un_aviso_no_un_error(sesion, ej):
    f = _factura_correcta(sesion, ej)
    f.total = D("40.95")  # el caso de la ITV del programa anterior: 4,18 € de tasa fuera de base e IVA
    sesion.flush()
    h = [x for x in auditar(sesion, ej) if x.codigo == "total_incoherente"]
    assert len(h) == 1 and h[0].gravedad == AVISO and "36.77" in h[0].mensaje


# ---- Datos reales: hallazgos conocidos de cada empresa ---------------------------------------------------

CONOCIDOS = {
    "empresa_a": Counter(
        amortizacion_del_ejercicio=5,  # la copia de MGD es de 2021 antes de dotar la amortización: 5 cuentas sin su dotación del año
        hueco_en_el_diario=1,  # asientos 18, 98 y 100 borrados
        justificante_ausente=7,
        saldo_con_signo_raro=1,  # proveedor FACTOR HUMUS con saldo deudor
        liquidacion_iva_desactualizada=1,  # 2.º trimestre: 18,87 € de IVA soportado contabilizado después de liquidar
    ),
    "empresa_b": Counter(
        amortizacion_del_ejercicio=1,  # el edificio: la dotación de 2021 (9.217,41 €) sin contabilizar en la copia de MGD
        asiento_fuera_del_ejercicio=6,  # movimientos y extras de oct-dic 2020 dentro de la empresa 2021
        hueco_en_el_diario=1,
        justificante_ausente=18,
        saldo_con_signo_raro=1,  # proveedor HACIENDA SANCIONES con saldo deudor
        liquidacion_iva_desactualizada=1,  # 1.er trimestre: 337,90 € de IVA soportado contabilizado después de liquidar
    ),
}


@pytest.mark.datos_reales
def test_hallazgos_conocidos_de_las_empresas_reales(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    assert codigos(auditar(sesion, ej)) == CONOCIDOS[carga_mgd.clave]


@pytest.mark.datos_reales
def test_solo_empresa_b_tiene_errores_y_son_las_fechas_de_2020(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    errores = [h for h in auditar(sesion, ej) if h.gravedad == ERROR]
    if carga_mgd.clave == "empresa_a":
        assert errores == []
    else:
        assert {h.codigo for h in errores} == {"asiento_fuera_del_ejercicio"}
        assert {h.referencia for h in errores} == {"3.81", "3.82", "3.103", "4.6", "4.7", "4.8"}
