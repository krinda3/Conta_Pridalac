"""Las facturas de un trimestre presentado (303) no se modifican, no se borran y no se crean con fecha de ese trimestre."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import PRESENTADA, Cuenta, DeclaracionLinea, DeclaracionPresentada, Ejercicio, Empresa, Factura, FacturaIva, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.bloqueo import trimestre_presentado
from conta_pridalac.servicios.facturas import eliminar_factura, grabar_factura

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62900000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("41000186", "PROVEEDOR")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return ej


def _cuenta(sesion, codigo):
    return sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()


def recibida(sesion, ej, fecha, base="100.00", cuota="21.00"):
    f = Factura(sentido="R", fecha_contable=fecha, fecha_factura=fecha, numero_factura="A-1", cuenta_tercero_id=_cuenta(sesion, "41000186").id,
                cuenta_contrapartida_id=_cuenta(sesion, "62900000").id, total=D(base) + D(cuota))
    f.ivas.append(FacturaIva(base=D(base), pct_iva=D("21.00"), cuota_iva=D(cuota), cuenta_iva_id=_cuenta(sesion, "47200000").id))
    return grabar_factura(sesion, ej, f).factura


def presentar(sesion, ej, periodo):
    sesion.add(PresentacionAeat(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=f"{periodo}T", estado=PRESENTADA, casillas="{}"))
    sesion.flush()


def test_sin_presentar_todo_se_puede_tocar(sesion, ej):
    f = recibida(sesion, ej, date(2026, 2, 10))
    f.total = D("130.00")
    grabar_factura(sesion, ej, f)
    eliminar_factura(sesion, ej, f)


def test_una_factura_ya_grabada_de_un_trimestre_presentado_no_se_modifica_ni_se_borra(sesion, ej):
    f = recibida(sesion, ej, date(2026, 2, 10))
    presentar(sesion, ej, 1)
    f.total = D("130.00")
    with pytest.raises(ErrorContable, match="ya está incluida en el 303 del 1T 2026.*rectificativa"):
        grabar_factura(sesion, ej, f)
    sesion.expire(f)
    with pytest.raises(ErrorContable, match="no se puede modificar ni borrar"):
        eliminar_factura(sesion, ej, f)


def test_no_se_graban_facturas_nuevas_con_fecha_de_un_trimestre_presentado(sesion, ej):
    presentar(sesion, ej, 1)
    with pytest.raises(ErrorContable, match="1T 2026 ya está presentado.*fecha de hoy"):
        recibida(sesion, ej, date(2026, 3, 31))
    assert recibida(sesion, ej, date(2026, 4, 1)).numero  # el trimestre siguiente sigue libre


def test_la_rectificativa_con_fecha_actual_si_se_puede(sesion, ej):
    original = recibida(sesion, ej, date(2026, 2, 10))
    presentar(sesion, ej, 1)
    contraria = recibida(sesion, ej, date(2026, 5, 3), base="-100.00", cuota="-21.00")
    assert contraria.total == D("-121.00") and original.id != contraria.id
    nueva = recibida(sesion, ej, date(2026, 5, 3), base="110.00", cuota="23.10")
    assert nueva.id


def test_lo_importado_de_programa_anterior_tambien_bloquea(sesion, ej):
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=2, tipo=1, casillas="{}"))
    sesion.flush()
    assert trimestre_presentado(sesion, ej.empresa_id, date(2026, 6, 30)) == "2T 2026" and trimestre_presentado(sesion, ej.empresa_id, date(2026, 7, 1)) is None
    with pytest.raises(ErrorContable):
        recibida(sesion, ej, date(2026, 5, 5))


def test_una_factura_declarada_en_otro_trimestre_tambien_se_bloquea(sesion, ej):
    """Una factura contabilizada en el 1T pero incluida (por un desajuste de fechas) en el 303 del 2T presentado."""
    f = recibida(sesion, ej, date(2026, 2, 10))
    d = DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=2, tipo=1, casillas="{}")
    d.lineas.append(DeclaracionLinea(factura_id=f.id, casilla="29"))
    sesion.add(d)
    sesion.flush()
    f.total = D("130.00")
    with pytest.raises(ErrorContable, match="303 del 2T 2026"):
        grabar_factura(sesion, ej, f)
