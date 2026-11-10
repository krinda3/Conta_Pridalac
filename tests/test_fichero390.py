from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero390 as f

LARGOS = {"01000": 1188, "02000": 1806, "02B00": 531, "03000": 1840, "04000": 854, "06000": 862, "07000": 781}

# 390 de 2025 de Empresa A, tal como se presentó
EMPRESA_A = {1: "16234.69", 2: "649.39", 33: "16234.69", 34: "649.39", 47: "649.39", 603: "6282.50", 604: "628.26", 605: "20794.61", 606: "4366.90",
         64: "5232.27", 65: "-4582.88", 84: "-4582.88", 86: "-4582.88", 97: "4582.88", 99: "16234.69", 108: "16234.69"}


def _declaracion(**cambios):
    casillas = {k: Decimal(v) for k, v in EMPRESA_A.items()}
    base = dict(nif="B00000010", nombre="Empresa A, S.L.", ejercicio=2025, casillas=casillas,
                actividades=[f.Actividad390("Cultivo de otros árboles, arbustos frutales", "b04")],
                representantes=[f.Representante390("Lopez Garcia de Soto, Elena", "00000014Z", date(2013, 12, 27), "Perez Ortega"),
                                f.Representante390("Gil Navarro, Pedro Jose", "00000001R", date(2013, 12, 27), "Perez Ortega")])
    base.update(cambios)
    return f.Declaracion390(**base)


def _trozo(texto, pagina):
    inicio = texto.index(f"<T390{pagina}>")
    return texto[inicio : texto.index(f"</T390{pagina}>", inicio) + len(f"</T390{pagina}>")]


def test_el_fichero_lleva_las_paginas_con_su_longitud_y_las_casillas_se_leen_de_vuelta():
    texto = f.generar(_declaracion())
    assert texto.startswith("<T39002025" + "0A0000><AUX>") and texto.endswith("</T39002025" + "0A0000>")
    assert texto.index("<T39001000>") == 328  # la cabecera ocupa 328 posiciones
    for pagina, largo in LARGOS.items():
        assert len(_trozo(texto, pagina)) == largo, pagina
    assert "<T39005000>" not in texto and "<T39008000>" not in texto  # sin régimen simplificado ni deducciones diferenciadas
    assert f.casillas_del_fichero(texto) == {k: Decimal(v) for k, v in sorted(EMPRESA_A.items())}


def test_las_casillas_se_colocan_por_su_numero_y_los_negativos_llevan_n():
    texto = f.generar(f.desde_calculo(_empresa(), _calculo()))
    leidas = f.casillas_del_fichero(texto)
    assert leidas[65] == Decimal("-4582.88") and leidas[97] == Decimal("4582.88") and leidas[605] == Decimal("20794.61")
    assert leidas[87] == Decimal("100") and leidas[92] == Decimal("-4582.88") and leidas[94] == Decimal("-4582.88")
    p4 = f.leer(texto)["04000"]
    assert p4[676] == "N" + "458288".rjust(16, "0")  # casilla 65, negativa


def test_la_identificacion_lleva_actividad_y_representantes_sin_acentos():
    texto = f.generar(_declaracion())
    p1 = f.leer(texto)["01000"]
    assert p1[14].strip() == "B00000010" and p1[23].strip() == "EMPRESA A, S.L." and p1[103] == "2025"
    assert p1[149].strip() == "CULTIVO DE OTROS ARBOLES, ARBUSTOS FRUTAL"[:40] and p1[189].strip() == "B04" and p1[192].strip() == ""
    assert p1[431] == "0" and p1[120] == "0" and p1[130] == "2" and p1[131] == "2" and p1[132] == "2" and p1[133] == "2" and p1[134] == "0"
    assert (p1[646].strip(), p1[726], p1[735], p1[743].strip()) == ("LOPEZ GARCIA DE SOTO, ELENA", "00000014Z", "27122013", "PEREZ ORTEGA")
    assert (p1[755].strip(), p1[835]) == ("GIL NAVARRO, PEDRO JOSE", "00000001R")
    assert p1[864].strip() == "" and p1[953] == "00000000"  # sin tercer representante


def test_una_casilla_sin_sitio_en_las_paginas_se_rechaza():
    with pytest.raises(ErrorContable, match="no caben"):
        f.generar(_declaracion(casillas={9999: Decimal("1")}))


def test_faltan_actividad_o_representantes():
    with pytest.raises(ErrorContable, match="actividad"):
        f.generar(_declaracion(actividades=[]))
    with pytest.raises(ErrorContable, match="representante"):
        f.generar(_declaracion(representantes=[]))


def test_la_sustitutiva_pide_el_justificante():
    with pytest.raises(ErrorContable, match="justificante"):
        f.generar(_declaracion(sustitutiva=True))
    p1 = f.leer(f.generar(_declaracion(sustitutiva=True, justificante_anterior="3906978400805")))["01000"]
    assert p1[134] == "1" and p1[136] == "3906978400805"


def test_las_paginas_opcionales_salen_si_hay_casillas_suyas():
    texto = f.generar(_declaracion(casillas={139: Decimal("10"), 155: Decimal("2")}))
    assert "<T39008000>" in texto and "<T39005000>" not in texto


class _Calculo:
    anio = 2025
    casillas = {k: Decimal(v) for k, v in EMPRESA_A.items()}


def _calculo():
    return _Calculo()


class _Actividad:
    descripcion, codigo, epigrafe = "Cultivo de frutales", "B04", None


class _Representante:
    nombre, nif, fecha_poder, notaria = "Elena", "00000014Z", date(2013, 12, 27), None


class _Empresa:
    nif, nombre = "B00000010", "Empresa A, S.L."
    actividades, representantes = [_Actividad()], [_Representante()]


def _empresa():
    return _Empresa()


def test_la_marca_del_347_se_pone_si_se_pide():
    assert f.leer(f.generar(_declaracion(declara_347=True)))["01000"][431] == "1"
