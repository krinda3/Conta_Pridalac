"""Los dígitos de las subcuentas son un dato de la empresa (8 por defecto): se elige al crearla y todo lo demás se ajusta a él."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from conta_pridalac.db.integridad import apuntes_en_cuentas_de_grupo
from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.domain.errores import CuentaNoAdmiteApuntes, ErrorContable
from conta_pridalac.migracion.cuentas import ajustar_cuenta, cuenta_8
from conta_pridalac.migracion.mgd import cargar_mgd, digitos_del_plan
from conta_pridalac.servicios import cuentas as svc
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.informes import balance_sumas_y_saldos
from conta_pridalac.servicios.modelo111 import calcular_111

D = Decimal


def codigo(grupo: str, n: int, numero: int = 0) -> str:
    """La subcuenta `numero` de un grupo en una empresa de `n` dígitos: `572` y 1 → `5720001` con 7 dígitos."""
    return grupo + str(numero).rjust(n - len(grupo), "0")


@pytest.fixture(params=[6, 7, 9, 10])
def ej(request, sesion):
    n = request.param
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", digitos_cuenta=n)
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for g, nombre in (("572", "BANCOS"), ("472", "IVA SOPORTADO"), ("475", "H.P. ACREEDORA"), ("629", "OTROS SERVICIOS"), ("400", "PROVEEDORES")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=g, nombre=f"{nombre} (grupo)"))  # una cuenta de grupo: no admite apuntes
    for g, k, nombre in (("572", 1, "BANCO"), ("472", 0, "IVA SOPORTADO"), ("629", 0, "OTROS SERVICIOS"), ("400", 1, "PROVEEDOR UNO")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo(g, n, k), nombre=nombre))
    sesion.flush()
    return ej


def test_la_empresa_nueva_tiene_8_digitos_por_defecto(sesion):
    e = Empresa(codigo=5, nombre="Otra")
    sesion.add(e)
    sesion.flush()
    assert e.digitos_cuenta == 8


def test_una_subcuenta_tiene_los_digitos_de_la_empresa(sesion, ej):
    n = ej.empresa.digitos_cuenta
    nueva = svc.crear_cuenta(sesion, ej.empresa_id, codigo("570", n, 1), "CAJA")
    assert nueva.es_subcuenta and not sesion.scalars(select(Cuenta).where(Cuenta.codigo == "572")).one().es_subcuenta
    for mal in (codigo("570", n + 1, 2), codigo("570", n - 1, 2), "57A" + "0" * (n - 3)):
        with pytest.raises(ErrorContable, match=f"{n} dígitos"):
            svc.crear_cuenta(sesion, ej.empresa_id, mal, "X")


def test_la_siguiente_cuenta_libre_del_grupo_tiene_los_digitos_de_la_empresa(sesion, ej):
    n = ej.empresa.digitos_cuenta
    assert svc.siguiente_cuenta_libre(sesion, ej.empresa_id, "430") == codigo("430", n, 1)
    assert svc.siguiente_cuenta_libre(sesion, ej.empresa_id, "400") == codigo("400", n, 2)  # ya existe la 1
    t = svc.crear_tercero(sesion, ej.empresa_id, "P", "Nuevo proveedor")
    assert sesion.get(Cuenta, t.cuenta_id).codigo == codigo("400", n, 2)


def test_solo_las_subcuentas_admiten_apuntes(sesion, ej):
    n = ej.empresa.digitos_cuenta
    banco, gasto = codigo("572", n, 1), codigo("629", n)
    a = grabar_asiento(sesion, ej, tipo=4, numero=1, sub=0, fecha=date(2026, 3, 1), concepto="prueba", subtipo=None, lineas=[LineaAsiento(gasto, D("10.00")), LineaAsiento(banco, D("-10.00"))])
    assert len(a.apuntes) == 2
    with pytest.raises(CuentaNoAdmiteApuntes, match="de grupo"):
        grabar_asiento(sesion, ej, tipo=4, numero=2, sub=0, fecha=date(2026, 3, 1), concepto="prueba", subtipo=None, lineas=[LineaAsiento("572", D("10.00")), LineaAsiento(gasto, D("-10.00"))])
    assert apuntes_en_cuentas_de_grupo(sesion, ej.id) == []


def test_la_auditoria_de_integridad_detecta_un_apunte_en_una_cuenta_de_menos_digitos(sesion, ej):
    n = ej.empresa.digitos_cuenta
    a = grabar_asiento(sesion, ej, tipo=4, numero=1, sub=0, fecha=date(2026, 3, 1), concepto="prueba", subtipo=None, lineas=[LineaAsiento(codigo("629", n), D("10.00")), LineaAsiento(codigo("572", n, 1), D("-10.00"))])
    grupo = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "629")).one()
    a.apuntes[0].cuenta_id = grupo.id  # lo que no deja hacer el programa, pero podría venir de una base mal importada
    sesion.flush()
    assert apuntes_en_cuentas_de_grupo(sesion, ej.id) == [a.apuntes[0].id]


def test_el_balance_agrupa_por_subcuenta_con_los_digitos_de_la_empresa(sesion, ej):
    n = ej.empresa.digitos_cuenta
    grabar_asiento(sesion, ej, tipo=4, numero=1, sub=0, fecha=date(2026, 3, 1), concepto="prueba", subtipo=None,
                   lineas=[LineaAsiento(codigo("629", n), D("100.00")), LineaAsiento(codigo("572", n, 1), D("-100.00"))])
    completo = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ej).filas}
    assert set(completo) == {codigo("629", n), codigo("572", n, 1)} and all(len(c) == n for c in completo)
    por_cuentas = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ej, nivel=3).filas}
    assert set(por_cuentas) == {"629", "572"}


def test_las_cuentas_por_defecto_se_ajustan_a_los_digitos():
    assert svc.cuenta_estandar("47200000", 7) == "4720000" and svc.cuenta_estandar("62900000", 9) == "629000000" and svc.cuenta_estandar("67100000", 8) == "67100000"


def test_el_modelo_111_calcula_con_cualquier_longitud_de_cuenta(sesion, ej):
    n = ej.empresa.digitos_cuenta
    retenciones, proveedor = codigo("4751", n), codigo("400", n, 1)
    sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=retenciones, nombre="H.P. ACREEDORA POR RETENCIONES"))
    sesion.flush()
    cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == proveedor)).one()
    sesion.add(Tercero(empresa_id=ej.empresa_id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z", cuenta_id=cuenta.id))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=2, numero=1, sub=0, fecha=date(2026, 11, 2), concepto="compra a agricultor", subtipo=None,
                   lineas=[LineaAsiento(codigo("629", n), D("865.22")), LineaAsiento(codigo("472", n), D("103.83")), LineaAsiento(retenciones, D("-19.38")),
                           LineaAsiento(proveedor, D("19.38")), LineaAsiento(proveedor, D("-969.05"))])
    c = calcular_111(sesion, ej, 4)
    assert c.casillas[30] == D("19.38")  # la 4751 se reconoce por su prefijo, no por su longitud


# ---------------------------------------------------------------- la migración desde MGD respeta los dígitos del plan


def test_ajustar_cuenta():
    assert ajustar_cuenta("5720001", 7) == "5720001"  # los mismos dígitos: no se toca
    assert ajustar_cuenta("5720001", 8, 3) == "57200001"
    assert ajustar_cuenta("", 7) == ""
    for mal in ("57200", "572000011", "57A000"):
        with pytest.raises(ValueError):
            ajustar_cuenta(mal, 7)
    assert cuenta_8("5720001") == "57200001"  # el comportamiento de siempre para Empresa A y Empresa B


def test_una_empresa_nueva_de_mgd_conserva_los_digitos_de_su_plan(sesion, carpeta_mgd_2021):
    assert digitos_del_plan(carpeta_mgd_2021) == 7
    r = cargar_mgd(sesion, carpeta_mgd_2021, codigo_empresa=99, nombre_empresa="Empresa de un amigo", anio=2021)
    empresa = sesion.get(Empresa, r.empresa_id)
    assert empresa.digitos_cuenta == 7
    longitudes = set(sesion.scalars(select(func.length(Cuenta.codigo)).where(Cuenta.empresa_id == empresa.id)))
    assert longitudes == {7}
    assert r.asientos > 0 and not apuntes_en_cuentas_de_grupo(sesion, r.ejercicio_id)
    debe, haber = sesion.execute(select(func.sum(Apunte.debe), func.sum(Apunte.haber)).join(Asiento, Asiento.id == Apunte.asiento_id).where(Asiento.ejercicio_id == r.ejercicio_id)).one()
    assert debe == haber


def test_empresa_a_y_empresa_b_siguen_pasando_a_8_digitos(sesion, carpeta_mgd_2021):
    r = cargar_mgd(sesion, carpeta_mgd_2021, codigo_empresa=11, nombre_empresa="Empresa A", anio=2021)
    assert sesion.get(Empresa, r.empresa_id).digitos_cuenta == 8
    assert set(sesion.scalars(select(func.length(Cuenta.codigo)).where(Cuenta.empresa_id == r.empresa_id))) == {8}


def test_una_base_anterior_gana_la_columna_con_8_digitos(tmp_path):
    from sqlalchemy import text

    from conta_pridalac.db.sesion import actualizar_esquema, crear_esquema, crear_motor, nueva_sesion

    motor = crear_motor(tmp_path / "vieja.sqlite")
    crear_esquema(motor)
    with motor.begin() as c:  # una base de antes de que la empresa tuviera dígitos de cuenta
        c.execute(text("INSERT INTO empresa (id, codigo, nombre) VALUES (1, 1, 'Antigua')"))
        c.execute(text("ALTER TABLE empresa DROP COLUMN digitos_cuenta"))
    assert "empresa.digitos_cuenta" in actualizar_esquema(motor)
    assert nueva_sesion(motor).get(Empresa, 1).digitos_cuenta == 8
