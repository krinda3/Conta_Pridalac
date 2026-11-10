"""Asientos manuales (extras) y plantillas, sobre los datos reales de Empresa A y Empresa B."""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.auditoria import auditar
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Pago, Plantilla, PlantillaLinea, Vencimiento
from conta_pridalac.domain.errores import (
    AsientoDescuadrado,
    CuentaNoAdmiteApuntes,
    DocumentoConPagos,
    EjercicioCerrado,
    ErrorContable,
    FechaFueraDePeriodo,
)
from conta_pridalac.domain.plantillas import evaluar_texto, fecha_de_vencimiento
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.extras import (
    LineaManual,
    crear_desde_plantilla,
    eliminar_extra,
    grabar_extra,
    lineas_de_plantilla,
)
from conta_pridalac.servicios.vencimientos import PlazoVencimiento

D = Decimal
pytestmark = pytest.mark.datos_reales


def _foto(sesion):
    estado = {}
    for a in sesion.scalars(select(Asiento)):
        lineas: Counter = Counter()
        for ap in a.apuntes:
            lineas[ap.cuenta.codigo] += ap.debe - ap.haber
        estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, dict(lineas))
    return estado


def _vencs(sesion):
    return {v.id: (v.origen_tipo, v.origen_numero, v.apunte_id, v.fecha, v.importe) for v in sesion.scalars(select(Vencimiento))}


def _extras(sesion):
    return sesion.scalars(select(Asiento).where(Asiento.tipo.in_((4, 9))).order_by(Asiento.numero)).all()


def _manual(a: Asiento, con_vencimientos: bool, sesion=None) -> list[LineaManual]:
    lineas = []
    for ap in a.apuntes:
        plazos = None
        if con_vencimientos:
            vs = sorted(sesion.scalars(select(Vencimiento).where(Vencimiento.apunte_id == ap.id)), key=lambda v: v.id)
            plazos = [PlazoVencimiento(importe=v.importe, fecha=v.fecha, banco=v.banco_previsto, forma_pago=v.forma_pago) for v in vs]
        lineas.append(LineaManual(ap.cuenta.codigo, "D" if ap.debe else "H", ap.debe or ap.haber, ap.concepto or "", plazos))
    return lineas


def _hallazgos(sesion, ej):
    return Counter(h.codigo for h in auditar(sesion, ej))


# ------------------------------------------------------------------------------ regrabar los extras reales


@pytest.mark.parametrize("con_vencimientos", [False, True])
def test_regrabar_todos_los_extras_reales_no_cambia_nada(sesion, carga_mgd, con_vencimientos):
    """Empresa A: 3 extras · Empresa B: 11 (3 fechados en 2020, que el servicio rechaza). Diario y vencimientos quedan idénticos."""
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes, vencs = _foto(sesion), _vencs(sesion)
    rechazados = grabados = 0
    for a in _extras(sesion):
        lineas = _manual(a, con_vencimientos, sesion)
        if not (ej.fecha_inicio <= a.fecha <= ej.fecha_fin):
            with pytest.raises(FechaFueraDePeriodo):
                grabar_extra(sesion, ej, fecha=a.fecha, texto=a.concepto, lineas=lineas, numero=a.numero, tipo=a.tipo, subtipo=a.subtipo)
            rechazados += 1
        else:
            grabar_extra(sesion, ej, fecha=a.fecha, texto=a.concepto, lineas=lineas, numero=a.numero, tipo=a.tipo, subtipo=a.subtipo)
            grabados += 1
    assert (grabados, rechazados) == ((3, 0) if carga_mgd.clave == "empresa_a" else (8, 3))
    assert _foto(sesion) == antes
    assert _vencs(sesion) == vencs


def test_los_vencimientos_de_extras_cuelgan_de_su_apunte(sesion, carga_mgd):
    vs = sesion.scalars(select(Vencimiento).where(Vencimiento.origen_tipo == "X")).all()
    assert len(vs) == (1 if carga_mgd.clave == "empresa_a" else 18)
    for v in vs:
        assert v.apunte is not None and v.apunte.cuenta_id == v.cuenta_origen_id


# ------------------------------------------------------------------------------ plantillas reales


def test_las_plantillas_reales_se_cargan_en_8_digitos(sesion, carga_mgd):
    assert carga_mgd.plantillas == (28 if carga_mgd.clave == "empresa_a" else 17)
    for l in sesion.scalars(select(PlantillaLinea)):
        assert len(l.cuenta) == 8 and l.dhc in "DHC"


def _plantilla_con_cuadre_y_vencimientos(sesion):
    for p in sesion.scalars(select(Plantilla).order_by(Plantilla.id)):
        ls = p.lineas
        if sum(1 for l in ls if l.dhc == "C") == 1 and any(l.vencimientos for l in ls):
            existentes = {c for (c,) in sesion.execute(select(Cuenta.codigo))}
            if all(l.cuenta in existentes for l in ls):
                return p
    return None


def test_crear_un_asiento_desde_una_plantilla_con_cuadre_y_vencimientos(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    p = _plantilla_con_cuadre_y_vencimientos(sesion)
    if p is None:
        pytest.skip("esta empresa no tiene una plantilla con línea de cuadre y vencimientos cuyas cuentas existan")
    base, fecha = _hallazgos(sesion, ej), date(2021, 11, 20)
    ultimo_diario = sesion.scalar(select(func.max(Asiento.numero_diario)))
    importes = [D("0") if l.dhc == "C" else D("100.00") for l in p.lineas]

    r = crear_desde_plantilla(sesion, ej, p, fecha, importes)
    a = r.asiento
    assert a.tipo == 4 and a.numero_diario == ultimo_diario + 1 and a.subtipo == "M"
    assert "{" not in a.concepto and a.concepto == evaluar_texto(p.titulo, fecha)
    assert sum(ap.debe for ap in a.apuntes) == sum(ap.haber for ap in a.apuntes) > 0
    # un vencimiento por cada regla de cada línea con importe, con la fecha que da el motor de reglas
    en_el_asiento = {ap.cuenta.codigo for ap in a.apuntes}
    reglas = {l.cuenta: [x.strip() for x in l.vencimientos.split(",") if x.strip()] for l in p.lineas if l.vencimientos and l.cuenta in en_el_asiento}
    assert len(r.vencimientos) == sum(len(v) for v in reglas.values()) > 0
    for v in r.vencimientos:
        regla = reglas[v.apunte.cuenta.codigo]
        assert v.fecha in {fecha_de_vencimiento(x, fecha) for x in regla}
        assert (v.importe < 0) == (v.apunte.haber > 0)
    assert _hallazgos(sesion, ej) == base


def test_la_plantilla_de_prestamo_de_empresa_b(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    p = sesion.scalars(select(Plantilla).where(Plantilla.titulo == "PRESTAMO BANKINTER")).one_or_none()
    if p is None:
        pytest.skip("solo Empresa B tiene la plantilla del préstamo")
    # cuota 1.690,48 = principal 1.500,00 + intereses 190,48
    r = crear_desde_plantilla(sesion, ej, p, date(2021, 5, 19), [D("1690.48"), D("1500.00"), D("190.48")])
    lineas = {ap.cuenta.codigo: ap.debe - ap.haber for ap in r.asiento.apuntes}
    assert lineas == {"52000001": D("-1690.48"), "17000003": D("1500.00"), "66203000": D("190.48")}
    (v,) = r.vencimientos  # la regla "D+ M+ A+" no cambia la fecha
    assert (v.fecha, v.importe, v.apunte.cuenta.codigo) == (date(2021, 5, 19), D("-1690.48"), "52000001")
    assert pendiente(sesion, v) == D("-1690.48")


# ------------------------------------------------------------------------------ errores


def _cuentas(sesion, n=2):
    return [c.codigo for c in sesion.scalars(select(Cuenta).where(func.length(Cuenta.codigo) == 8).limit(n))]


def test_un_asiento_manual_descuadrado_no_se_graba(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    a, b = _cuentas(sesion)
    total = sesion.scalar(select(func.count()).select_from(Asiento))
    with pytest.raises(AsientoDescuadrado, match="no cuadra"):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[LineaManual(a, "D", D("100")), LineaManual(b, "H", D("90"))])
    sesion.rollback()
    assert sesion.scalar(select(func.count()).select_from(Asiento)) == total


def test_cuentas_fechas_y_lineas_invalidas(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    a, b = _cuentas(sesion)
    ok = [LineaManual(a, "D", D("10")), LineaManual(b, "H", D("10"))]
    with pytest.raises(CuentaNoAdmiteApuntes):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[LineaManual("99999999", "D", D("1")), LineaManual(b, "H", D("1"))])
    with pytest.raises(FechaFueraDePeriodo):
        grabar_extra(sesion, ej, fecha=date(2022, 1, 5), texto="X", lineas=ok)
    with pytest.raises(ErrorContable, match="lado"):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[LineaManual(a, "X", D("1"))])
    with pytest.raises(ErrorContable, match="negativo"):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[LineaManual(a, "D", D("-1")), LineaManual(b, "H", D("-1"))])
    with pytest.raises(ErrorContable, match="al menos una línea"):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[])
    with pytest.raises(ErrorContable, match="importe 0"):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[LineaManual(a, "D", D("0")), LineaManual(b, "H", D("0"))])
    ej.cerrado = True
    with pytest.raises(EjercicioCerrado):
        grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=ok)


def test_una_plantilla_con_una_cuenta_sin_crear_no_se_puede_usar(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    a, _ = _cuentas(sesion)
    p = Plantilla(empresa_id=ej.empresa_id, titulo="MALA {año}", lineas=[
        PlantillaLinea(orden=1, cuenta=a, dhc="D", ayuda="x"), PlantillaLinea(orden=2, cuenta="11111111", dhc="C", ayuda="y")])
    sesion.add(p)
    sesion.flush()
    with pytest.raises(ErrorContable, match="11111111 no está creada"):
        crear_desde_plantilla(sesion, ej, p, date(2021, 6, 1), [D("5"), D("0")])


def test_advertencia_si_los_vencimientos_no_suman_el_apunte(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    a, b = _cuentas(sesion)
    r = grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[
        LineaManual(a, "D", D("100"), vencimientos=[PlazoVencimiento(D("40"), date(2021, 7, 1))]), LineaManual(b, "H", D("100"))])
    assert any("suman 40.00 y el apunte es de 100.00" in x for x in r.advertencias)


# ------------------------------------------------------------------------------ borrar


def test_no_se_borra_un_extra_con_vencimientos_pagados_pero_si_uno_nuevo(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    pagado = sesion.scalars(select(Asiento).join(Apunte).join(Vencimiento, Vencimiento.apunte_id == Apunte.id).join(Pago, Pago.vencimiento_id == Vencimiento.id)).first()
    with pytest.raises(DocumentoConPagos):
        eliminar_extra(sesion, ej, pagado)

    a, b = _cuentas(sesion)
    r = grabar_extra(sesion, ej, fecha=date(2021, 6, 1), texto="X", lineas=[
        LineaManual(a, "D", D("10"), vencimientos=[PlazoVencimiento(D("10"), date(2021, 7, 1))]), LineaManual(b, "H", D("10"))])
    nuevos = sesion.scalar(select(func.count()).select_from(Vencimiento))
    eliminar_extra(sesion, ej, r.asiento)
    assert sesion.scalar(select(func.count()).select_from(Vencimiento)) == nuevos - 1
    assert sesion.scalars(select(Asiento).where(Asiento.tipo == 4, Asiento.numero == r.asiento.numero)).first() is None

