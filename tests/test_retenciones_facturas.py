"""Facturas recibidas con la retención de IRPF sólo en el asiento: se les anota el ajuste que falta y el asiento regenerado coincide."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac import auditoria
from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaAjuste, FacturaIva, Tercero
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.retenciones_facturas import reparar

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62300000", "SERVICIOS PROFESIONALES"), ("47200000", "IVA SOPORTADO"), ("47510000", "HP RETENCIONES"), ("41000132", "PROVEEDOR")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return ej


def _factura_con_retencion(sesion, ej):
    c = {x.codigo: x for x in sesion.scalars(select(Cuenta))}
    sesion.add(Tercero(empresa_id=ej.empresa_id, clase="P", nombre="Agricultor", cuenta_id=c["41000132"].id))
    sesion.flush()
    f = Factura(ejercicio_id=ej.id, sentido="R", numero=127, fecha_contable=date(2025, 11, 10), fecha_factura=date(2025, 11, 10), numero_factura="15", total=D("1865.92"),
                cuenta_tercero_id=c["41000132"].id, cuenta_contrapartida_id=c["62300000"].id)
    f.ivas.append(FacturaIva(base=D("1700.00"), pct_iva=D("12"), cuota_iva=D("204.00"), deducible=True, cuenta_iva_id=c["47200000"].id))
    f.ajustes.append(FacturaAjuste(orden=0, cuenta_id=c["47510000"].id, importe=D("-38.08"), contra="G"))
    sesion.add(f)
    grabar_factura(sesion, ej, f)
    sesion.flush()
    return f


def _sin_el_ajuste(sesion, f):
    """Como llegó de la contabilidad anterior: el asiento lleva la retención y la factura no."""
    for a in list(f.ajustes):
        f.ajustes.remove(a)
        sesion.delete(a)
    sesion.flush()


def test_la_factura_sin_su_ajuste_da_error_y_el_arreglo_lo_quita(sesion, ej):
    f = _factura_con_retencion(sesion, ej)
    assert "asiento_distinto_del_regenerado" not in {h.codigo for h in auditoria.auditar(sesion, ej)}
    _sin_el_ajuste(sesion, f)
    assert "asiento_distinto_del_regenerado" in {h.codigo for h in auditoria.auditar(sesion, ej)}
    (r,) = reparar(sesion, ej)
    assert (r.factura, r.cuenta, r.importe, r.resultado) == ("R 127", "47510000", D("-38.08"), "añadido")
    sesion.refresh(f)
    assert [(a.cuenta.codigo, a.importe, a.contra) for a in f.ajustes] == [("47510000", D("-38.08"), "G")]
    assert not {h.codigo for h in auditoria.auditar(sesion, ej) if h.gravedad == "ERROR"}
    assert reparar(sesion, ej) == []  # ya está: no se duplica


def test_no_toca_lo_que_no_es_una_retencion(sesion, ej):
    f = _factura_con_retencion(sesion, ej)
    _sin_el_ajuste(sesion, f)
    a = sesion.scalar(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == 127))
    gasto = next(ap for ap in a.apuntes if ap.cuenta.codigo == "62300000")
    gasto.debe += D("1.00")
    ajeno = next(ap for ap in a.apuntes if ap.cuenta.codigo == "41000132" and ap.haber)
    ajeno.haber += D("1.00")
    sesion.flush()
    (r,) = reparar(sesion, ej)
    assert r.resultado == "con el ajuste el asiento sigue sin coincidir"
    sesion.refresh(f)
    assert f.ajustes == []
