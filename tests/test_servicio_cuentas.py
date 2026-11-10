"""Alta, cambio y baja de cuentas y terceros."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Parametro
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cuentas import (
    borrar_cuenta,
    borrar_tercero,
    crear_cuenta,
    crear_tercero,
    modificar_cuenta,
    modificar_tercero,
    usos_de_cuenta,
)

D = Decimal


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    return e, ej


def test_crear_cuenta_valida_codigo_nombre_y_duplicados(sesion, emp):
    e, _ = emp
    c = crear_cuenta(sesion, e.id, " 57200001 ", "  Banco  ")
    assert (c.codigo, c.nombre) == ("57200001", "Banco")
    for codigo, nombre in (("5720001", "x"), ("572000AB", "x"), ("57200001", "otra"), ("57200002", " ")):
        with pytest.raises(ErrorContable):
            crear_cuenta(sesion, e.id, codigo, nombre)


def test_modificar_cuenta_libre_y_en_uso(sesion, emp):
    e, ej = emp
    banco, capital = crear_cuenta(sesion, e.id, "57200001", "Banco"), crear_cuenta(sesion, e.id, "10000000", "Capital")
    grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 2), lineas=[LineaAsiento("57200001", D(5)), LineaAsiento("10000000", D(-5))])
    modificar_cuenta(sesion, banco, nombre="Banco Santander")
    assert banco.nombre == "Banco Santander"
    with pytest.raises(ErrorContable, match="en uso en apunte"):
        modificar_cuenta(sesion, banco, codigo="57200009")
    libre = crear_cuenta(sesion, e.id, "60000001", "Compras")
    modificar_cuenta(sesion, libre, codigo="60000002")
    assert libre.codigo == "60000002"
    with pytest.raises(ErrorContable, match="Ya existe"):
        modificar_cuenta(sesion, libre, codigo=capital.codigo)
    with pytest.raises(ErrorContable):
        modificar_cuenta(sesion, libre, nombre=" ")


def test_borrar_cuenta_detecta_cualquier_uso(sesion, emp):
    e, ej = emp
    a, b = crear_cuenta(sesion, e.id, "57200001", "Banco"), crear_cuenta(sesion, e.id, "10000000", "Capital")
    grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 2), lineas=[LineaAsiento("57200001", D(5)), LineaAsiento("10000000", D(-5))])
    assert usos_de_cuenta(sesion, a) == [("apunte", 1)]
    with pytest.raises(ErrorContable, match="en uso"):
        borrar_cuenta(sesion, a)
    libre = crear_cuenta(sesion, e.id, "60000001", "Compras")
    sesion.add(Parametro(empresa_id=e.id, clave="PYG", valor="60000001"))
    sesion.flush()
    assert usos_de_cuenta(sesion, libre) == [("parametro", 1)]
    with pytest.raises(ErrorContable):
        borrar_cuenta(sesion, libre)
    otra = crear_cuenta(sesion, e.id, "60000009", "Sin uso")
    borrar_cuenta(sesion, otra)
    assert sesion.query(Cuenta).filter_by(codigo="60000009").count() == 0


def test_terceros(sesion, emp):
    e, _ = emp
    crear_cuenta(sesion, e.id, "41000001", "Proveedor")
    t = crear_tercero(sesion, e.id, "P", " Iberdrola ", nif=" a12345678 ", cuenta="41000001")
    assert (t.nombre, t.nif, t.clase) == ("Iberdrola", "A12345678", "P") and t.cuenta_id
    with pytest.raises(ErrorContable, match="No existe la cuenta"):
        crear_tercero(sesion, e.id, "C", "X", cuenta="43000009")
    with pytest.raises(ErrorContable):
        crear_tercero(sesion, e.id, "Z", "X")
    with pytest.raises(ErrorContable):
        crear_tercero(sesion, e.id, "C", " ")
    modificar_tercero(sesion, t, "P", "Iberdrola SA", comercial="Luz", cuenta="")
    assert (t.nombre, t.comercial, t.cuenta_id) == ("Iberdrola SA", "Luz", None)
    borrar_tercero(sesion, t)


def test_el_tercero_nuevo_sin_cuenta_recibe_la_siguiente_libre(sesion, emp):
    from conta_pridalac.servicios.cuentas import siguiente_cuenta_libre

    e, _ = emp
    assert siguiente_cuenta_libre(sesion, e.id, "400") == "40000001"
    a = crear_tercero(sesion, e.id, "P", "Iberdrola")
    b = crear_tercero(sesion, e.id, "P", "Endesa")
    assert (a.cuenta_id, b.cuenta_id) != (None, None)
    codigos = {c.codigo: c.nombre for c in sesion.query(Cuenta)}
    assert codigos == {"40000001": "IBERDROLA", "40000002": "ENDESA"}
    c = crear_tercero(sesion, e.id, "C", "Cliente Uno")
    assert sesion.get(Cuenta, c.cuenta_id).codigo == "43000001"
    # se continúa tras la mayor existente (aunque haya huecos), y se puede elegir otro grupo
    crear_cuenta(sesion, e.id, "41008123", "ACREEDOR VIEJO")
    d = crear_tercero(sesion, e.id, "P", "Notario", grupo_cuenta="410")
    assert sesion.get(Cuenta, d.cuenta_id).codigo == "41008124"
    # con una cuenta indicada no se crea otra; sin nombre o con clase inválida no se crea nada
    n = sesion.query(Cuenta).count()
    crear_tercero(sesion, e.id, "P", "Con cuenta", cuenta="40000001")
    assert sesion.query(Cuenta).count() == n
    for clase, nombre in (("Z", "X"), ("P", " ")):
        with pytest.raises(ErrorContable):
            crear_tercero(sesion, e.id, clase, nombre)
    assert sesion.query(Cuenta).count() == n
    with pytest.raises(ErrorContable, match="3 dígitos"):
        siguiente_cuenta_libre(sesion, e.id, "4000")


def test_un_grupo_agotado_avisa(sesion, emp):
    from conta_pridalac.servicios.cuentas import siguiente_cuenta_libre

    e, _ = emp
    crear_cuenta(sesion, e.id, "40099999", "LA ÚLTIMA")
    with pytest.raises(ErrorContable, match="no tiene más cuentas libres"):
        siguiente_cuenta_libre(sesion, e.id, "400")
