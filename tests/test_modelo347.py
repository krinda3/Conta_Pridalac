"""Cálculo del 347: operaciones con IVA por tercero y trimestre, umbral de 3.005,06 € y claves A y B."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Ejercicio, Empresa, Factura, FacturaIva, Tercero
from conta_pridalac.servicios.modelo347 import UMBRAL, calcular_347

D = Decimal


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    return ej


def tercero(sesion, ej, nombre, nif, clase="P", cp="13001", **kw):
    t = Tercero(empresa_id=ej.empresa_id, clase=clase, nombre=nombre, nif=nif, codigo_postal=cp, **kw)
    sesion.add(t)
    sesion.flush()
    return t


def factura(sesion, ej, t, sentido, numero, fecha, base, iva_pct=21, factura_fecha=None):
    base = D(base)
    cuota = (base * D(iva_pct) / 100).quantize(D("0.01"))
    f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=factura_fecha or fecha, tercero_id=t.id if t else None, total=base + cuota)
    f.ivas.append(FacturaIva(base=base, pct_iva=D(iva_pct), cuota_iva=cuota))
    sesion.add(f)
    sesion.flush()
    return f


def test_suma_con_iva_por_trimestre_y_clave(sesion, ej):
    t = tercero(sesion, ej, "AGRICULTOR UNO", "12345678Z")
    factura(sesion, ej, t, "R", 1, date(2025, 2, 3), "1000.00")
    factura(sesion, ej, t, "R", 2, date(2025, 11, 20), "2000.00")
    factura(sesion, ej, t, "E", 1, date(2025, 5, 1), "4000.00")
    c = calcular_347(sesion, ej)
    assert [(d.clave, d.nif, d.provincia, d.trimestres, d.anual) for d in c.declarados] == [
        ("A", "12345678Z", "13", [D("1210.00"), D("0.00"), D("0.00"), D("2420.00")], D("3630.00")),
        ("B", "12345678Z", "13", [D("0.00"), D("4840.00"), D("0.00"), D("0.00")], D("4840.00")),
    ]
    assert c.total == D("8470.00") and c.avisos == []


def test_el_umbral_es_sobre_el_total_anual_con_iva(sesion, ej):
    t = tercero(sesion, ej, "JUSTO POR DEBAJO", "11111111H")
    u = tercero(sesion, ej, "JUSTO POR ENCIMA", "22222222J")
    factura(sesion, ej, t, "R", 1, date(2025, 3, 1), "2483.52")  # con IVA 3.005,06: no supera el umbral (hace falta que lo supere)
    factura(sesion, ej, u, "R", 2, date(2025, 3, 1), "2483.53")  # 3.005,07
    c = calcular_347(sesion, ej)
    assert t.nombre in [d.nombre for d in c.por_debajo] and [d.nombre for d in c.declarados] == ["JUSTO POR ENCIMA"] and UMBRAL == D("3005.06")


def test_las_rectificativas_restan_y_se_junta_por_nif(sesion, ej):
    a = tercero(sesion, ej, "PROVEEDOR UNO", "12345678Z")
    b = tercero(sesion, ej, "PROVEEDOR UNO (otra ficha)", "12345678Z")  # el mismo NIF en dos fichas: es el mismo declarado
    factura(sesion, ej, a, "R", 1, date(2025, 1, 10), "3000.00")
    factura(sesion, ej, b, "R", 2, date(2025, 1, 20), "1000.00")
    factura(sesion, ej, a, "R", 3, date(2025, 2, 1), "-500.00")
    c = calcular_347(sesion, ej)
    assert len(c.declarados) == 1 and c.declarados[0].trimestres[0] == D("4235.00") and len(c.declarados[0].facturas) == 3


def test_el_trimestre_sale_de_la_fecha_contable(sesion, ej):
    t = tercero(sesion, ej, "AGRICULTOR UNO", "12345678Z")
    factura(sesion, ej, t, "R", 1, date(2025, 4, 2), "3000.00", factura_fecha=date(2025, 3, 28))
    assert calcular_347(sesion, ej).declarados[0].trimestres == [D("0.00"), D("3630.00"), D("0.00"), D("0.00")]
    assert calcular_347(sesion, ej, fecha_del_trimestre="factura").declarados[0].trimestres == [D("3630.00"), D("0.00"), D("0.00"), D("0.00")]


def test_omite_los_marcados_y_avisa_de_lo_que_falta(sesion, ej):
    excluido = tercero(sesion, ej, "EXCLUIDO", "33333333P", no_incluir_347=True)
    sin_nif = tercero(sesion, ej, "SIN NIF", None)
    sin_cp = tercero(sesion, ej, "SIN CODIGO POSTAL", "44444444A", cp=None)
    for i, t in enumerate((excluido, sin_nif, sin_cp), 1):
        factura(sesion, ej, t, "R", i, date(2025, 6, 1), "5000.00")
    c = calcular_347(sesion, ej)
    assert [d.nombre for d in c.declarados] == ["SIN CODIGO POSTAL"]
    assert any("SIN NIF" in a and "no tiene NIF" in a for a in c.avisos) and any("SIN CODIGO POSTAL" in a and "provincia" in a for a in c.avisos)


def test_la_provincia_sale_del_codigo_postal_o_del_nombre(sesion, ej):
    t = tercero(sesion, ej, "SIN CP PERO CON PROVINCIA", "44444444A", cp=None, provincia="Ciudad Real")
    factura(sesion, ej, t, "R", 1, date(2025, 6, 1), "5000.00")
    c = calcular_347(sesion, ej)
    assert c.declarados[0].provincia == "13" and c.avisos == []
