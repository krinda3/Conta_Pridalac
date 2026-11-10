from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from conta_pridalac.db.integridad import asientos_descuadrados, huecos_numeracion_diario
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa
from conta_pridalac.db.tipos import dinero
from conta_pridalac.migracion.cuentas import cuenta_8


def test_dinero_no_arrastra_ruido_de_float():
    assert dinero(0.1 + 0.2) == Decimal("0.30")
    assert dinero(1631.54) == Decimal("1631.54")
    assert dinero(None) == Decimal("0.00")
    assert dinero("") == Decimal("0.00")


@pytest.mark.parametrize(
    "mgd, esperado",
    [("1210002", "12100002"), ("1000000", "10000000"), ("5720001", "57200001"), ("12100002", "12100002"), ("", "")],
)
def test_cuenta_8(mgd, esperado):
    assert cuenta_8(mgd) == esperado


@pytest.mark.parametrize("mal", ["123", "abcdefg", "123456789"])
def test_cuenta_8_rechaza_longitudes_raras(mal):
    with pytest.raises(ValueError):
        cuenta_8(mal)


def _base(sesion):
    e = Empresa(codigo=99, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    gasto = Cuenta(empresa_id=e.id, codigo="62900000", nombre="OTROS SERVICIOS")
    prov = Cuenta(empresa_id=e.id, codigo="41000186", nombre="IDV")
    sesion.add_all([gasto, prov])
    sesion.flush()
    return ej, gasto, prov


def _asiento(sesion, ej, numero, lineas):
    a = Asiento(ejercicio_id=ej.id, tipo=2, numero=numero, fecha=date(2026, 9, 30))
    for i, (cuenta, debe, haber) in enumerate(lineas, start=1):
        a.apuntes.append(Apunte(orden=i, cuenta_id=cuenta.id, debe=Decimal(debe), haber=Decimal(haber)))
    sesion.add(a)
    sesion.flush()
    return a


def test_asiento_cuadrado_no_se_reporta(sesion):
    ej, gasto, prov = _base(sesion)
    _asiento(sesion, ej, 1, [(gasto, "100.00", "0"), (prov, "0", "100.00")])
    assert asientos_descuadrados(sesion, ej.id) == []


def test_detecta_el_descuadre_de_la_factura_2_194(sesion):
    """Caso real del programa anterior: 30,38 + 6,39 al debe y 40,95 al haber → descuadre de 4,18 €."""
    ej, gasto, prov = _base(sesion)
    _asiento(sesion, ej, 194, [(gasto, "30.38", "0"), (gasto, "6.39", "0"), (prov, "0", "40.95")])
    assert asientos_descuadrados(sesion, ej.id) == [("2.194", Decimal("-4.18"))]


def test_apunte_no_puede_tener_debe_y_haber(sesion):
    ej, gasto, _ = _base(sesion)
    with pytest.raises(IntegrityError):
        _asiento(sesion, ej, 1, [(gasto, "1.00", "1.00")])


def test_apunte_no_admite_importes_negativos(sesion):
    ej, gasto, _ = _base(sesion)
    with pytest.raises(IntegrityError):
        _asiento(sesion, ej, 1, [(gasto, "-1.00", "0")])


def test_asiento_unico_por_ejercicio_tipo_numero(sesion):
    ej, gasto, prov = _base(sesion)
    _asiento(sesion, ej, 1, [(gasto, "1", "0"), (prov, "0", "1")])
    with pytest.raises(IntegrityError):
        _asiento(sesion, ej, 1, [(gasto, "2", "0"), (prov, "0", "2")])


def test_huecos_en_el_diario(sesion):
    ej, gasto, prov = _base(sesion)
    for n, nd in ((1, 1), (2, 2), (3, 4)):
        a = _asiento(sesion, ej, n, [(gasto, "1", "0"), (prov, "0", "1")])
        a.numero_diario = nd
    sesion.flush()
    assert huecos_numeracion_diario(sesion, ej.id) == [3]
