"""Servicio de bienes de inversión: alta, cuadro, amortización contable, deshacer y baja."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import ERROR, auditar
from conta_pridalac.db.modelos import Apunte, Asiento, BienInversion, Cuenta, Ejercicio, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.bienes import (
    alta_bien,
    amortizar_ejercicio,
    asiento_de_baja,
    amortizar_periodo,
    anular_baja,
    borrar_bien,
    modificar_ficha,
    dar_de_baja,
    deshacer_amortizacion,
    deshacer_asiento_de_baja,
    periodos_pendientes,
    regenerar_cuadro,
)
from conta_pridalac.servicios.cierre import saldos_del_ejercicio

D = Decimal


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ejs = [Ejercicio(anio=a, fecha_inicio=date(a, 1, 1), fecha_fin=date(a, 12, 31), empresa=e) for a in (2026, 2027)]
    sesion.add_all([e, *ejs])
    sesion.flush()
    for codigo, nombre in (("21800000", "ELEMENTOS DE TRANSPORTE"), ("28180000", "AMORT. ACUM. TRANSPORTE"), ("68100000", "AMORTIZACION DEL INMOVILIZADO"),
                           ("67100000", "PERDIDAS DEL INMOVILIZADO"), ("77100000", "BENEFICIOS DEL INMOVILIZADO"), ("57200001", "BANCO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return e, ejs


def _alta(sesion, e, **kw):
    datos = dict(descripcion="FURGONETA", precio_compra=D("5000"), fecha_funcionamiento=date(2026, 1, 1), cuenta_inmovilizado="21800000",
                 cuenta_amortizacion="28180000", cuenta_dotacion="68100000", periodos_vida=5)
    datos.update(kw)
    return alta_bien(sesion, e.id, **datos)


def test_alta_genera_el_cuadro(sesion, emp):
    e, _ = emp
    b = _alta(sesion, e)
    assert b.codigo == 1 and [a.anio for a in b.amortizaciones] == [2026, 2027, 2028, 2029, 2030]
    assert all(a.importe_previsto == D("1000.00") and a.importe_contable is None for a in b.amortizaciones)
    assert _alta(sesion, e, descripcion="OTRA").codigo == 2


def test_alta_con_inicio_a_mitad_de_anio_prorratea(sesion, emp):
    e, _ = emp
    b = _alta(sesion, e, fecha_funcionamiento=date(2026, 7, 1))
    primero = b.amortizaciones[0]
    assert (primero.desde, primero.hasta) == (date(2026, 7, 1), date(2026, 12, 31)) and primero.importe_previsto == D("504.11")
    assert sum(a.importe_previsto for a in b.amortizaciones) == D("5000.00")


@pytest.mark.parametrize(
    "cambio",
    [{"precio_compra": D("0")}, {"periodos_vida": None}, {"cuenta_dotacion": "99999999"}, {"descripcion": " "}],
)
def test_alta_valida_la_ficha(sesion, emp, cambio):
    with pytest.raises(ErrorContable):
        _alta(sesion, emp[0], **cambio)


def test_amortizar_el_ejercicio_contabiliza_y_no_duplica(sesion, emp):
    e, (ej26, ej27) = emp
    _alta(sesion, e)
    _alta(sesion, e, descripcion="ORDENADOR", precio_compra=D("1200"), periodos_vida=4)
    r = amortizar_ejercicio(sesion, ej26)
    assert len(r.amortizados) == 2 and r.total == D("1300.00")
    asientos = sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ej26.id)).all()
    assert {(a.tipo, a.subtipo, a.fecha) for a in asientos} == {(9, "Q", date(2026, 12, 31))}
    saldos = saldos_del_ejercicio(sesion, ej26)
    assert saldos == {"68100000": D("1300.00"), "28180000": D("-1300.00")}
    assert amortizar_ejercicio(sesion, ej26).amortizados == []  # nada que repetir
    assert len(amortizar_ejercicio(sesion, ej27).amortizados) == 2
    assert not [h for h in auditar(sesion, ej26) if h.gravedad == ERROR]


def test_amortizar_un_periodo_dos_veces_da_error(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    with pytest.raises(ErrorContable):
        amortizar_periodo(sesion, ej26, b.amortizaciones[0])


def test_no_amortiza_en_un_ejercicio_cerrado(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    ej26.cerrado = True
    with pytest.raises(ErrorContable):
        amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    assert b.amortizaciones[0].importe_contable is None


def test_deshacer_deja_el_periodo_pendiente(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    p = amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    deshacer_amortizacion(sesion, ej26, p)
    assert p.importe_contable is None and p.asiento_id is None
    assert sesion.scalars(select(Asiento)).all() == []
    assert periodos_pendientes(sesion, ej26) == [p]
    with pytest.raises(ErrorContable):
        deshacer_amortizacion(sesion, ej26, p)


def test_regenerar_conserva_lo_amortizado_y_protege_el_cuadro(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    b.periodos_vida = 10  # misma fecha de inicio: el primer periodo sigue existiendo
    regenerar_cuadro(sesion, b)
    assert len(b.amortizaciones) == 10 and b.amortizaciones[0].importe_contable == D("1000.00")
    assert b.amortizaciones[0].importe_previsto == D("500.00")  # lo previsto se actualiza, lo realizado no
    b.fecha_funcionamiento = date(2026, 3, 1)
    with pytest.raises(ErrorContable):
        regenerar_cuadro(sesion, b)


def test_baja_acorta_el_cuadro(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    dar_de_baja(sesion, b, date(2027, 6, 30), "VENTA")
    assert [a.anio for a in b.amortizaciones] == [2026, 2027]
    assert b.amortizaciones[1].hasta == date(2027, 6, 30) and b.amortizaciones[1].importe_previsto == D("495.89")
    with pytest.raises(ErrorContable):
        dar_de_baja(sesion, b, date(2027, 7, 1))


def test_baja_anterior_a_lo_amortizado_se_rechaza(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    with pytest.raises(ErrorContable):
        dar_de_baja(sesion, b, date(2026, 6, 30))


def test_no_amortizar_en_el_ejercicio_de_baja(sesion, emp):
    e, (ej26, ej27) = emp
    b = _alta(sesion, e)
    dar_de_baja(sesion, b, date(2027, 6, 30), "ROBO", no_amortizar_en_baja=True)
    amortizar_ejercicio(sesion, ej26)
    r = amortizar_ejercicio(sesion, ej27)
    assert r.amortizados == [] and len(r.omitidos) == 1


def _bien_dado_de_baja(sesion, e, ej26, ej27, **kw):
    b = _alta(sesion, e, **kw)
    amortizar_ejercicio(sesion, ej26)
    dar_de_baja(sesion, b, date(2027, 6, 30), "VENTA")
    amortizar_ejercicio(sesion, ej27)
    return b


def test_baja_sin_venta_lleva_el_resto_a_perdidas(sesion, emp):
    e, (ej26, ej27) = emp
    b = _bien_dado_de_baja(sesion, e, ej26, ej27)
    r = asiento_de_baja(sesion, ej27, b)
    assert (r.amortizacion_acumulada, r.valor_neto, r.resultado) == (D("1495.89"), D("3504.11"), D("-3504.11"))
    lineas = {ap.cuenta.codigo: (ap.debe, ap.haber) for ap in r.asiento.apuntes}
    assert lineas == {"21800000": (D("0"), D("5000.00")), "28180000": (D("1495.89"), D("0")), "67100000": (D("3504.11"), D("0"))}
    assert (r.asiento.tipo, r.asiento.subtipo, r.asiento.fecha) == (9, "B", date(2027, 6, 30)) and b.asiento_baja_id == r.asiento.id
    saldos = saldos_del_ejercicio(sesion, ej27)
    assert sum(saldos.values(), D("0")) == 0 and saldos["21800000"] == D("-5000.00")


def test_baja_con_venta_con_beneficio(sesion, emp):
    e, (ej26, ej27) = emp
    b = _bien_dado_de_baja(sesion, e, ej26, ej27)
    r = asiento_de_baja(sesion, ej27, b, precio_venta=D("4000"), cuenta_cobro="57200001")
    assert r.resultado == D("495.89")
    lineas = {ap.cuenta.codigo: (ap.debe, ap.haber) for ap in r.asiento.apuntes}
    assert lineas["57200001"] == (D("4000.00"), D("0")) and lineas["77100000"] == (D("0"), D("495.89"))
    assert not [h for h in auditar(sesion, ej27) if h.gravedad == ERROR]


def test_baja_con_venta_justo_al_valor_neto_no_deja_resultado(sesion, emp):
    e, (ej26, ej27) = emp
    b = _bien_dado_de_baja(sesion, e, ej26, ej27)
    r = asiento_de_baja(sesion, ej27, b, precio_venta=D("3504.11"), cuenta_cobro="57200001")
    assert r.resultado == 0 and {ap.cuenta.codigo for ap in r.asiento.apuntes} == {"21800000", "28180000", "57200001"}


def test_baja_exige_fecha_amortizacion_previa_y_no_se_repite(sesion, emp):
    e, (ej26, ej27) = emp
    b = _alta(sesion, e)
    with pytest.raises(ErrorContable, match="no tiene fecha de baja"):
        asiento_de_baja(sesion, ej27, b)
    dar_de_baja(sesion, b, date(2027, 6, 30))
    with pytest.raises(ErrorContable, match="Faltan por amortizar"):
        asiento_de_baja(sesion, ej27, b)
    amortizar_ejercicio(sesion, ej26)
    amortizar_ejercicio(sesion, ej27)
    with pytest.raises(ErrorContable, match="cuenta en la que se cobra"):
        asiento_de_baja(sesion, ej27, b, precio_venta=D("100"))
    with pytest.raises(ErrorContable, match="negativo"):
        asiento_de_baja(sesion, ej27, b, precio_venta=D("-1"))
    asiento_de_baja(sesion, ej27, b)
    with pytest.raises(ErrorContable, match="ya tiene"):
        asiento_de_baja(sesion, ej27, b)


def test_baja_en_el_ejercicio_de_baja_sin_amortizarlo(sesion, emp):
    e, (ej26, ej27) = emp
    b = _alta(sesion, e)
    amortizar_ejercicio(sesion, ej26)
    dar_de_baja(sesion, b, date(2027, 6, 30), no_amortizar_en_baja=True)
    r = asiento_de_baja(sesion, ej27, b)
    assert r.amortizacion_acumulada == D("1000.00") and r.resultado == D("-4000.00")


def test_deshacer_el_asiento_de_baja(sesion, emp):
    e, (ej26, ej27) = emp
    b = _bien_dado_de_baja(sesion, e, ej26, ej27)
    r = asiento_de_baja(sesion, ej27, b)
    deshacer_asiento_de_baja(sesion, ej27, b)
    assert b.asiento_baja_id is None and sesion.get(Asiento, r.asiento.id) is None
    with pytest.raises(ErrorContable):
        deshacer_asiento_de_baja(sesion, ej27, b)
    asiento_de_baja(sesion, ej27, b)  # se puede volver a hacer


def test_modificar_la_ficha_rehace_el_cuadro(sesion, emp):
    e, _ = emp
    b = _alta(sesion, e)
    modificar_ficha(sesion, b, descripcion="FURGONETA BLANCA", periodos_vida=10, precio_compra=D("6000"))
    assert b.descripcion == "FURGONETA BLANCA" and len(b.amortizaciones) == 10 and b.amortizaciones[0].importe_previsto == D("600.00")
    modificar_ficha(sesion, b, cuenta_dotacion="68100000")
    with pytest.raises(ErrorContable, match="No existe la cuenta"):
        modificar_ficha(sesion, b, cuenta_dotacion="99999999")
    with pytest.raises(ErrorContable, match="descripción"):
        modificar_ficha(sesion, b, descripcion=" ")
    assert b.descripcion == "FURGONETA BLANCA" and b.cuenta_dotacion.codigo == "68100000"  # un cambio inválido no deja la ficha a medias


def test_un_cambio_descriptivo_no_toca_el_cuadro_ni_sus_ajustes_manuales(sesion, emp):
    e, _ = emp
    b = _alta(sesion, e)
    b.amortizaciones[0].importe_previsto = D("1234.56")  # un ajuste a mano del cuadro, como los de MGD
    sesion.flush()
    modificar_ficha(sesion, b, descripcion="OTRA", notas="x", precio_compra=D("5000"), periodos_vida=5)  # los mismos valores económicos
    assert b.descripcion == "OTRA" and b.amortizaciones[0].importe_previsto == D("1234.56") and len(b.amortizaciones) == 5
    modificar_ficha(sesion, b, precio_compra=D("6000"))  # un cambio económico sí rehace el cuadro
    assert b.amortizaciones[0].importe_previsto == D("1200.00")


def test_con_periodos_amortizados_solo_se_cambian_los_datos_descriptivos(sesion, emp):
    e, (ej26, _) = emp
    b = _alta(sesion, e)
    amortizar_periodo(sesion, ej26, b.amortizaciones[0])
    modificar_ficha(sesion, b, descripcion="OTRA DESCRIPCION", notas="revisado")
    assert b.descripcion == "OTRA DESCRIPCION"
    modificar_ficha(sesion, b, precio_compra=D("5000"))  # el mismo valor no es un cambio
    for cambio in ({"precio_compra": D("6000")}, {"periodos_vida": 10}, {"cuenta_amortizacion": "68100000"}, {"fecha_funcionamiento": date(2026, 2, 1)}):
        with pytest.raises(ErrorContable, match="deshágalos primero"):
            modificar_ficha(sesion, b, **cambio)
    assert b.precio_compra == D("5000.00") and b.periodos_vida == 5


def test_anular_la_baja_y_borrar_un_bien(sesion, emp):
    e, (ej26, ej27) = emp
    b = _alta(sesion, e)
    with pytest.raises(ErrorContable, match="no está dado de baja"):
        anular_baja(sesion, b)
    dar_de_baja(sesion, b, date(2027, 6, 30), "VENTA")
    assert len(b.amortizaciones) == 2
    anular_baja(sesion, b)
    assert b.fecha_baja is None and len(b.amortizaciones) == 5
    dar_de_baja(sesion, b, date(2027, 6, 30))
    amortizar_ejercicio(sesion, ej26)
    amortizar_ejercicio(sesion, ej27)
    asiento_de_baja(sesion, ej27, b)
    with pytest.raises(ErrorContable, match="Deshaga primero el asiento de baja"):
        anular_baja(sesion, b)
    with pytest.raises(ErrorContable, match="amortizado"):
        borrar_bien(sesion, b)
    libre = _alta(sesion, e, descripcion="LIBRE")
    borrar_bien(sesion, libre)
    assert sesion.scalars(select(BienInversion).where(BienInversion.descripcion == "LIBRE")).first() is None


@pytest.mark.datos_reales
def test_amortizar_2021_con_los_bienes_reales(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes = len(sesion.scalars(select(Asiento)).all())
    errores_antes = sorted(h.mensaje for h in auditar(sesion, ej) if h.gravedad == ERROR)
    pendientes = periodos_pendientes(sesion, ej)
    previsto = sum((p.importe_previsto for p in pendientes), D("0.00"))
    r = amortizar_ejercicio(sesion, ej)
    assert len(r.amortizados) == len(pendientes) and r.total == previsto
    assert len(sesion.scalars(select(Asiento)).all()) == antes + len(pendientes)
    assert periodos_pendientes(sesion, ej) == []
    if pendientes:  # cada asiento cuadra y usa las cuentas del bien
        for p in r.amortizados:
            a = sesion.get(Asiento, p.asiento_id)
            assert sum(ap.debe for ap in a.apuntes) == sum(ap.haber for ap in a.apuntes) == p.importe_contable
    # amortizar no introduce errores de integridad nuevos (los que ya traen los datos de MGD se conservan)
    assert sorted(h.mensaje for h in auditar(sesion, ej) if h.gravedad == ERROR) == errores_antes


@pytest.mark.datos_reales
def test_la_amortizacion_2021_cuadra_con_la_apertura_2022_de_programa_anterior(sesion, carga_mgd):
    """Amortización acumulada (grupo 28) de la apertura de 2022 del programa anterior = la de la apertura 2021 de MGD + lo amortizado en 2021.

    Empresa B cuadra al céntimo. En Empresa A el programa anterior añadió 343,56 € de amortización de las naves, un bien que no estaba en
    la tabla de bienes de MGD (sale del Excel de bienes).
    """
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "tools"))
    from leer_diario_programa_anterior_pdf import leer

    fichero, ident, extra = {"empresa_a": ("EMPRESA A Asientos automaticos año 2022.pdf", "9.1", D("343.56")),
                             "empresa_b": ("EMPRESA B Asientos automaticos año 2022.pdf", "9.3", D("0.00"))}[carga_mgd.clave]
    ruta = raiz / "docs" / "Exportaciones del programa anterior" / fichero
    if not ruta.exists():
        pytest.skip(f"No está {ruta.name}")
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    apertura_2021 = sum(
        (ap.haber - ap.debe for ap in sesion.scalars(select(Apunte).join(Asiento).where(Asiento.subtipo == "A")) if ap.cuenta.codigo.startswith("28")),
        D("0.00"),
    )
    amortizado = amortizar_ejercicio(sesion, ej).total
    programa_anterior = -sum((v for c, v in {a.id: a for a in leer(str(ruta))}[ident].saldos.items() if c.startswith("28")), D("0.00"))
    assert apertura_2021 + amortizado + extra == programa_anterior


# ---- la auditoría compara la dotación de cada año con el cuadro (no el histórico anterior a Conta)


def _avisos_de_amortizacion(sesion, ej):
    return [h for h in auditar(sesion, ej) if h.codigo == "amortizacion_del_ejercicio"]


def test_la_auditoria_de_la_amortizacion_compara_la_dotacion_del_ejercicio_con_el_cuadro(sesion, emp, monkeypatch):
    e, (ej26, _) = emp
    _alta(sesion, e)  # 5.000 € a 5 años: 1.000 € en 2026
    monkeypatch.setattr("conta_pridalac.auditoria.hoy", lambda: date(2026, 10, 30))  # el ejercicio 2026 no ha terminado
    assert _avisos_de_amortizacion(sesion, ej26) == []  # sin dotar todavía: lo normal, se hace al cierre
    amortizar_ejercicio(sesion, ej26)
    assert _avisos_de_amortizacion(sesion, ej26) == []  # dotado como dice el cuadro
    monkeypatch.setattr("conta_pridalac.auditoria.hoy", lambda: date(2027, 1, 15))
    assert _avisos_de_amortizacion(sesion, ej26) == []  # y terminado el año sigue cuadrando


def test_un_ejercicio_terminado_sin_dotar_o_dotado_de_mas_avisa(sesion, emp, monkeypatch):
    e, (ej26, _) = emp
    _alta(sesion, e)
    monkeypatch.setattr("conta_pridalac.auditoria.hoy", lambda: date(2026, 10, 30))
    ej26.cerrado = True  # terminado: la dotación que falta ya es un aviso
    sin_dotar = _avisos_de_amortizacion(sesion, ej26)
    assert len(sin_dotar) == 1 and "28180000" in sin_dotar[0].mensaje and "amortización contabilizada en 2026 = 0" in sin_dotar[0].mensaje and "= 1000.00" in sin_dotar[0].mensaje
    ej26.cerrado = False
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
    grabar_asiento(sesion, ej26, tipo=4, numero=90, fecha=date(2026, 6, 30), lineas=[LineaAsiento("68100000", D("1500.00")), LineaAsiento("28180000", D("-1500.00"))])  # dotado de más, aunque el año no ha terminado
    de_mas = _avisos_de_amortizacion(sesion, ej26)
    assert len(de_mas) == 1 and "= 1500.00" in de_mas[0].mensaje


def test_lo_anterior_a_la_primera_apertura_no_se_compara(sesion, emp, monkeypatch):
    e, (ej26, ej27) = emp
    _alta(sesion, e)
    amortizar_ejercicio(sesion, ej26)
    monkeypatch.setattr("conta_pridalac.auditoria.hoy", lambda: date(2026, 10, 30))
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
    # una apertura con amortización acumulada que no tiene nada que ver con el cuadro (la que trajo el programa anterior): no es un aviso
    grabar_asiento(sesion, ej27, tipo=1, numero=1, fecha=date(2027, 1, 1), subtipo="A", lineas=[LineaAsiento("21800000", D("5000.00")), LineaAsiento("28180000", D("-3333.33")), LineaAsiento("57200001", D("-1666.67"))])
    assert _avisos_de_amortizacion(sesion, ej27) == []
