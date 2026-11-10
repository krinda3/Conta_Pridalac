"""Servicio de facturas: crear, regrabar sin cambios y borrar, sobre los datos reales de las dos empresas."""
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.integridad import asientos_descuadrados
from conta_pridalac.db.modelos import Asiento, Cuenta, Ejercicio, Factura, FacturaIva, Pago, Tercero, Vencimiento
from conta_pridalac.domain.errores import DocumentoConPagos, EjercicioCerrado, ErrorContable, FechaFueraDePeriodo
from conta_pridalac.servicios.facturas import eliminar_factura, grabar_factura

D = Decimal
pytestmark = pytest.mark.datos_reales


def _foto(sesion) -> dict:
    """Estado del Diario: {(tipo, numero, sub): (numero_diario, fecha, {cuenta: importe})}."""
    estado = {}
    for a in sesion.scalars(select(Asiento)):
        lineas: Counter = Counter()
        for ap in a.apuntes:
            lineas[ap.cuenta.codigo] += ap.debe - ap.haber
        estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, dict(lineas))
    return estado


def _modelo_con_iva(sesion):
    """Una factura recibida real cuya primera línea de IVA tiene cuenta de IVA (21 % en el caso habitual)."""
    return sesion.scalars(
        select(Factura)
        .join(FacturaIva)
        .where(Factura.sentido == "R", FacturaIva.cuenta_iva_id.is_not(None), FacturaIva.cuota_iva > 0)
        .order_by(Factura.numero)
    ).first()


def test_regrabar_todas_las_facturas_deja_el_diario_exactamente_igual(sesion, carga_mgd):
    """Prueba de regresión con datos reales: regenerar los asientos de cada factura no cambia nada."""
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    antes = _foto(sesion)
    for factura in sesion.scalars(select(Factura)).all():
        grabar_factura(sesion, ej, factura)
    assert _foto(sesion) == antes
    assert asientos_descuadrados(sesion, ej.id) == []


def test_crear_una_factura_recibida_nueva(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    modelo = _modelo_con_iva(sesion)
    iva = next(i for i in modelo.ivas if i.cuenta_iva_id)
    ultimo_diario = max(n for (n, _, _) in _foto(sesion).values())
    ultimo_numero = sesion.scalar(select(func.max(Factura.numero)).where(Factura.sentido == "R"))

    nueva = Factura(
        sentido="R",
        fecha_contable=date(2021, 12, 15),
        fecha_factura=date(2021, 12, 10),
        numero_factura="NUEVA-1",
        tercero_id=modelo.tercero_id,
        cuenta_tercero_id=modelo.cuenta_tercero_id,
        cuenta_contrapartida_id=modelo.cuenta_contrapartida_id,
        total=D("121.00"),
    )
    nueva.ivas.append(FacturaIva(base=D("100.00"), pct_iva=D("21.00"), cuota_iva=D("21.00"), cuenta_iva_id=iva.cuenta_iva_id, deducible=True))
    res = grabar_factura(sesion, ej, nueva)

    assert nueva.numero == ultimo_numero + 1
    assert len(res.asientos) == 1 and res.asientos[0].numero_diario == ultimo_diario + 1
    lineas = {ap.cuenta_id: ap.debe - ap.haber for ap in res.asientos[0].apuntes}
    assert lineas[nueva.cuenta_contrapartida_id] == D("100.00")
    assert lineas[iva.cuenta_iva_id] == D("21.00")
    assert lineas[nueva.cuenta_tercero_id] == D("-121.00")
    assert res.advertencias == []
    assert asientos_descuadrados(sesion, ej.id) == []


def test_las_advertencias_no_bloquean(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    modelo = _modelo_con_iva(sesion)
    f = Factura(
        sentido="R", fecha_contable=date(2021, 1, 2), fecha_factura=date(2021, 3, 1),  # factura posterior al asiento
        numero_factura="X", cuenta_tercero_id=modelo.cuenta_tercero_id, cuenta_contrapartida_id=modelo.cuenta_contrapartida_id,
        total=D("100.00"),
    )
    f.ivas.append(FacturaIva(base=D("50.00"), pct_iva=D("21.00"), cuota_iva=D("10.50"), cuenta_iva_id=next(i.cuenta_iva_id for i in modelo.ivas if i.cuenta_iva_id)))
    res = grabar_factura(sesion, ej, f)
    texto = " | ".join(res.advertencias)
    assert "posterior a la fecha contable" in texto
    assert "no coincide con base + IVA + recargo" in texto
    assert "es posterior" in texto or "es anterior" in texto  # fuera de orden respecto a los vecinos por número
    assert res.asientos  # se grabó igualmente


def test_fecha_fuera_de_ejercicio_o_ejercicio_cerrado_no_graban_nada(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    modelo = sesion.scalars(select(Factura).where(Factura.sentido == "R")).first()
    antes = _foto(sesion)
    total_facturas = sesion.scalar(select(func.count()).select_from(Factura))

    def nueva(fecha):
        return Factura(sentido="R", fecha_contable=fecha, cuenta_tercero_id=modelo.cuenta_tercero_id,
                       cuenta_contrapartida_id=modelo.cuenta_contrapartida_id, total=D("10.00"))

    with pytest.raises(FechaFueraDePeriodo):
        grabar_factura(sesion, ej, nueva(date(2022, 1, 1)))
    ej.cerrado = True
    with pytest.raises(EjercicioCerrado):
        grabar_factura(sesion, ej, nueva(date(2021, 6, 1)))
    ej.cerrado = False
    sesion.rollback()
    assert _foto(sesion) == antes
    assert sesion.scalar(select(func.count()).select_from(Factura)) == total_facturas


def test_faltan_cuentas(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    with pytest.raises(ErrorContable, match="cuenta del tercero"):
        grabar_factura(sesion, ej, Factura(sentido="R", fecha_contable=date(2021, 6, 1), total=D("1")))


def test_no_se_borra_una_factura_con_pagos_pero_si_una_sin_ellos(sesion, carga_mgd):
    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    con_pagos = sesion.scalars(
        select(Factura).join(Vencimiento, Vencimiento.factura_id == Factura.id).join(Pago, Pago.vencimiento_id == Vencimiento.id)
    ).first()
    with pytest.raises(DocumentoConPagos):
        eliminar_factura(sesion, ej, con_pagos)

    modelo = sesion.scalars(select(Factura).where(Factura.sentido == "R")).first()
    f = Factura(sentido="R", fecha_contable=date(2021, 12, 20), cuenta_tercero_id=modelo.cuenta_tercero_id,
                cuenta_contrapartida_id=modelo.cuenta_contrapartida_id, total=D("10.00"))
    res = grabar_factura(sesion, ej, f)
    numero = f.numero
    eliminar_factura(sesion, ej, f)
    assert sesion.scalars(select(Factura).where(Factura.sentido == "R", Factura.numero == numero)).first() is None
    assert sesion.scalars(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == numero)).first() is None
    assert res.asientos  # el asiento existió antes de borrarse


def test_aplicar_correcciones_es_idempotente(sesion):
    """La herramienta de correcciones añade una línea exenta, regenera el asiento y no se aplica dos veces."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from aplicar_correcciones import aplicar

    from sqlalchemy import select
    from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Factura, FacturaIva
    from conta_pridalac.servicios.facturas import grabar_factura

    emp = Empresa(codigo=1, nombre="E")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=emp)
    sesion.add_all([emp, ej])
    sesion.flush()
    ctas = {c: Cuenta(empresa_id=emp.id, codigo=c, nombre=c) for c in ("40000001", "62800000", "47200000")}
    sesion.add_all(ctas.values())
    sesion.flush()
    f = Factura(ejercicio_id=ej.id, sentido="R", numero=1, fecha_contable=date(2026, 3, 1), fecha_factura=date(2026, 3, 1), numero_factura="F1", total=Decimal("144.53"),
                cuenta_tercero_id=ctas["40000001"].id, cuenta_contrapartida_id=ctas["62800000"].id,
                ivas=[FacturaIva(base=Decimal("107.00"), pct_iva=Decimal("21.00"), cuota_iva=Decimal("22.47"), cuenta_iva_id=ctas["47200000"].id)])
    grabar_factura(sesion, ej, f)
    c = {"ejercicio": 2026, "sentido": "R", "numero": 1, "exento": 15.06, "motivo": "compra de dispositivos a plazos"}
    assert "base+IVA 129.47" in aplicar(sesion, c)
    a = sesion.scalars(select(Asiento).where(Asiento.numero == 1, Asiento.tipo == 2)).one()
    assert sorted((ap.cuenta.codigo, ap.debe, ap.haber) for ap in a.apuntes) == [("40000001", Decimal("0.00"), Decimal("144.53")), ("47200000", Decimal("22.47"), Decimal("0.00")), ("62800000", Decimal("122.06"), Decimal("0.00"))]
    assert aplicar(sesion, c) is None and len(f.ivas) == 2 and f.notas.count("Corrección:") == 1  # la segunda vez no hace nada
