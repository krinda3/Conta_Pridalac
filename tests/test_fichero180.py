"""Fichero del modelo 180 según el diseño oficial (DR_Mod_180_2023): estructura y posiciones de los dos tipos de registro."""
from decimal import Decimal

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero180 import Declaracion180, Inmueble180, Percepcion180, generar, leer

D = Decimal


def inmueble(**kw):
    datos = dict(situacion="1", catastro="1234567VK1234S0001AB", tipo_via="CL", via="MAYOR", tipo_numeracion="NUM", numero="12", planta="1", puerta="B", complemento="LOCAL 3",
                 municipio="CIUDAD REAL", codigo_municipio="13034", provincia="13", codigo_postal="13001")
    datos.update(kw)
    return Inmueble180(**datos)


def declaracion(**kw):
    datos = dict(nif="G12345678", nombre="ASOCIACIÓN DE PRUEBA", ejercicio=2026, contacto_telefono="926123456", contacto_nombre="JAVIER PRUEBA", identificativo="1801234567890",
                 percepciones=[Percepcion180("12345678Z", "GARCIA LOPEZ ANA", "13", D("12000.00"), D("19.00"), D("2280.00"), inmueble()),
                               Percepcion180("B12345674", "INMUEBLES SL", "28", D("6000.50"), D("19.00"), D("1140.10"), inmueble(situacion="4", catastro="", via="ALCALA", numero="", municipio="MADRID", provincia="28", codigo_postal="28001"))])
    datos.update(kw)
    return Declaracion180(**datos)


def registros(texto):
    return texto.split("\r\n")[:-1]


def test_estructura_de_la_cabecera_posicion_a_posicion():
    t = generar(declaracion())
    cabecera = registros(t)[0]
    assert all(len(r) == 500 for r in registros(t)) and t.endswith("\r\n")
    assert cabecera[0] == "1" and cabecera[1:4] == "180" and cabecera[4:8] == "2026" and cabecera[8:17] == "G12345678"
    assert cabecera[17:57].rstrip() == "ASOCIACION DE PRUEBA" and cabecera[57] == "T" and cabecera[58:67] == "926123456" and cabecera[67:107].rstrip() == "JAVIER PRUEBA"
    assert cabecera[107:120] == "1801234567890" and cabecera[120] == " " and cabecera[121] == " " and cabecera[122:135] == "0" * 13
    assert cabecera[135:144] == "000000002" and cabecera[144] == " "
    assert int(cabecera[145:160]) == 1800050 and int(cabecera[160:175]) == 342010  # 18.000,50 y 3.420,10 € en céntimos
    assert cabecera[175:] == " " * 325


def test_estructura_del_registro_de_arrendador_posicion_a_posicion():
    r = registros(generar(declaracion()))[1]
    assert r[0] == "2" and r[1:4] == "180" and r[4:8] == "2026" and r[8:17] == "G12345678" and r[17:26] == "12345678Z" and r[26:35] == " " * 9
    assert r[35:75].rstrip() == "GARCIA LOPEZ ANA" and r[75:77] == "13" and r[77] == "1" and r[78] == " "
    assert r[79:92] == "0000001200000" and r[92:96] == "1900" and r[96:109] == "0000000228000" and r[109:113] == "0000"
    assert r[113] == "1" and r[114:134] == "1234567VK1234S0001AB" and r[134:139].rstrip() == "CL" and r[139:189].rstrip() == "MAYOR"
    assert r[189:192] == "NUM" and r[192:197].rstrip() == "12" and r[197:200] == " " * 3 and r[209:212].rstrip() == "1" and r[212:215].rstrip() == "B"
    assert r[215:255].rstrip() == "LOCAL 3" and r[255:285] == " " * 30 and r[285:315].rstrip() == "CIUDAD REAL"
    assert r[315:320] == "13034" and r[320:322] == "13" and r[322:327] == "13001" and r[327:] == " " * 173


def test_sin_referencia_catastral_va_a_blancos_y_el_nif_se_ajusta_a_la_derecha():
    r = registros(generar(declaracion(nif="B1234567", percepciones=[Percepcion180("1234567L", "X", "28", D("1"), D("19"), D("0.19"), inmueble(situacion="4", catastro=""))])))
    assert r[1][8:17] == "0B1234567" and r[1][17:26] == "01234567L" and r[1][113] == "4" and r[1][114:134] == " " * 20


def test_leer_devuelve_lo_generado():
    d = leer(generar(declaracion(sustitutiva=True, identificativo_anterior="1800000000001")))
    assert d.sustitutiva and d.identificativo_anterior == "1800000000001" and d.ejercicio == 2026 and len(d.percepciones) == 2
    p = d.percepciones[0]
    assert (p.nif, p.provincia, p.base, p.porcentaje, p.retencion) == ("12345678Z", "13", D("12000.00"), D("19.00"), D("2280.00"))
    assert p.inmueble.catastro == "1234567VK1234S0001AB" and p.inmueble.codigo_municipio == "13034" and p.inmueble.codigo_postal == "13001" and p.inmueble.puerta == "B"
    assert d.percepciones[1].inmueble.situacion == "4" and d.percepciones[1].inmueble.catastro == ""


def test_sin_arrendadores_es_solo_la_cabecera_a_ceros():
    t = generar(declaracion(percepciones=[]))
    assert len(registros(t)) == 1 and registros(t)[0][135:175] == "0" * 9 + " " + "0" * 15 + "0" * 15


@pytest.mark.parametrize("cambios", [
    dict(identificativo="1900000000001"), dict(complementaria=True, sustitutiva=True, identificativo_anterior="1800000000001"), dict(sustitutiva=True), dict(contacto_telefono="12345678X"),
    dict(percepciones=[Percepcion180("1", "X", "13", D("-1"), D("19"), D("1"), inmueble())]), dict(percepciones=[Percepcion180("1", "X", "13", D("1"), D("100"), D("1"), inmueble())]),
    dict(percepciones=[Percepcion180("1", "X", "13", D("1"), D("19"), D("1"), inmueble(situacion=""))]), dict(percepciones=[Percepcion180("1", "X", "AB", D("1"), D("19"), D("1"), inmueble())]),
    dict(percepciones=[Percepcion180("1", "X", "13", D("1"), D("19"), D("1"), inmueble(via="V" * 51))]),
])
def test_datos_incorrectos_se_rechazan(cambios):
    with pytest.raises(ErrorContable):
        generar(declaracion(**cambios))
