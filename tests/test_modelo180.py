"""Cálculo del 180 desde los libros (suma de los cuatro 115 por arrendador), datos del inmueble en la ficha y validación de esa ficha."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cuentas import modificar_tercero
from conta_pridalac.servicios.modelo180 import calcular_180

D = Decimal
INMUEBLE = dict(inmueble_situacion="1", inmueble_catastro="1234567VK1234S0001AB", inmueble_tipo_via="CL", inmueble_via="MAYOR", inmueble_numero="12", inmueble_municipio="CIUDAD REAL",
                inmueble_codigo_municipio="13034", inmueble_provincia="13", inmueble_codigo_postal="13001")


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Asociación S.L.", nif="G12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62100000", "ARRENDAMIENTOS"), ("47200000", "IVA SOPORTADO"), ("47510000", "H.P. ACREEDORA POR RETENCIONES"), ("41000001", "CASERO UNO"), ("41000002", "CASERO DOS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    for codigo, nif in (("41000001", "12345678Z"), ("41000002", None)):
        cuenta = sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()
        sesion.add(Tercero(empresa_id=e.id, clase="P", nombre=cuenta.nombre, nif=nif, cuenta_id=cuenta.id))
    sesion.flush()
    return ej


def alquiler(sesion, ej, fecha, cuenta, renta, retencion, numero):
    total = D(renta) - D(retencion)
    return grabar_asiento(sesion, ej, tipo=2, numero=numero, sub=0, fecha=fecha, concepto="alquiler", subtipo="M",
                          lineas=[LineaAsiento(c, D(i)) for c, i in (("62100000", renta), ("47510000", f"-{retencion}"), (cuenta, f"-{total}"))])


def ficha(sesion, codigo):
    return sesion.scalars(select(Tercero).join(Cuenta, Tercero.cuenta_id == Cuenta.id).where(Cuenta.codigo == codigo)).one()


def test_un_ano_sin_alquileres_no_tiene_arrendadores(sesion, ej):
    c = calcular_180(sesion, ej)
    assert c.arrendadores == [] and c.bases == 0 and c.retenciones == 0 and c.avisos == []


def test_suma_los_cuatro_trimestres_por_arrendador(sesion, ej):
    for i, (mes, renta, ret) in enumerate(((2, "1000.00", "190.00"), (5, "1000.00", "190.00"), (11, "1100.00", "209.00")), start=1):
        alquiler(sesion, ej, date(2025, mes, 2), "41000001", renta, ret, i)
    alquiler(sesion, ej, date(2025, 11, 3), "41000002", "500.00", "95.00", 9)
    c = calcular_180(sesion, ej)
    dos, uno = c.arrendadores  # el que no tiene NIF va primero
    assert (uno.nif, uno.base, uno.retencion, uno.porcentaje, len(uno.asientos)) == ("12345678Z", D("3100.00"), D("589.00"), D("19.00"), 3)
    assert (dos.base, dos.retencion) == (D("500.00"), D("95.00")) and c.bases == D("3600.00") and c.retenciones == D("684.00")


def test_el_porcentaje_es_el_ultimo_del_ano(sesion, ej):
    alquiler(sesion, ej, date(2025, 2, 2), "41000001", "1000.00", "190.00", 1)
    alquiler(sesion, ej, date(2025, 11, 2), "41000001", "1000.00", "150.00", 2)
    c = calcular_180(sesion, ej)
    assert c.arrendadores[0].porcentaje == D("15.00") and any("15.00 %" in a for a in c.avisos)


def test_los_datos_que_faltan_en_la_ficha_se_senalan(sesion, ej):
    alquiler(sesion, ej, date(2025, 2, 2), "41000001", "1000.00", "190.00", 1)
    alquiler(sesion, ej, date(2025, 2, 3), "41000002", "500.00", "95.00", 2)
    dos, uno = calcular_180(sesion, ej).arrendadores  # el que no tiene NIF va primero
    assert dos.faltan[:3] == ["NIF", "provincia del arrendador", "situación del inmueble"] and "nombre de la vía" in dos.faltan
    assert uno.faltan == ["provincia del arrendador", "situación del inmueble", "nombre de la vía", "municipio", "provincia del inmueble", "código postal del inmueble"]
    modificar_tercero(sesion, ficha(sesion, "41000001"), "P", "CASERO UNO", nif="12345678Z", cuenta="41000001", provincia_190="13", **INMUEBLE)
    uno = next(a for a in calcular_180(sesion, ej).arrendadores if a.cuenta == "41000001")
    assert uno.faltan == [] and uno.conviene == [] and uno.inmueble.catastro == "1234567VK1234S0001AB" and uno.provincia == "13"


def test_sin_referencia_catastral_solo_se_exige_con_las_situaciones_1_a_3(sesion, ej):
    alquiler(sesion, ej, date(2025, 2, 2), "41000001", "1000.00", "190.00", 1)
    datos = {**INMUEBLE, "inmueble_catastro": ""}
    modificar_tercero(sesion, ficha(sesion, "41000001"), "P", "CASERO UNO", nif="12345678Z", cuenta="41000001", provincia_190="13", **datos)
    assert calcular_180(sesion, ej).arrendadores[0].faltan == ["referencia catastral"]
    modificar_tercero(sesion, ficha(sesion, "41000001"), "P", "CASERO UNO", nif="12345678Z", cuenta="41000001", inmueble_situacion="4")
    assert calcular_180(sesion, ej).arrendadores[0].faltan == []


def test_la_ficha_guarda_en_mayusculas_y_valida_el_inmueble(sesion, ej):
    t = ficha(sesion, "41000001")
    modificar_tercero(sesion, t, "P", "CASERO UNO", nif="12345678Z", cuenta="41000001", inmueble_via="calle mayor", inmueble_catastro="1234567vk1234s0001ab")
    assert (t.inmueble_via, t.inmueble_catastro) == ("CALLE MAYOR", "1234567VK1234S0001AB")
    for campo, valor, mensaje in (("inmueble_situacion", "5", "1, 2, 3 o 4"), ("inmueble_provincia", "1", "2 cifras"), ("inmueble_codigo_postal", "1300", "5 cifras"),
                                  ("inmueble_codigo_municipio", "ab123", "5 cifras"), ("inmueble_catastro", "123 456", "14 a 20")):
        with pytest.raises(ErrorContable, match=mensaje):
            modificar_tercero(sesion, t, "P", "CASERO UNO", nif="12345678Z", cuenta="41000001", **{campo: valor})
