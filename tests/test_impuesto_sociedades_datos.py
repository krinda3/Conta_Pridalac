"""Datos del IS: guardado, correcciones automáticas (multas), tipo de gravamen por regla, cuota por tramos y bases imponibles negativas."""
import json
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, Ejercicio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from test_libros_oficiales import ej  # noqa: F401 - es una fixture

D = Decimal


def _gasto(sesion, ej, cuenta, importe, n, nombre="GASTO"):
    if not sesion.query(Cuenta).filter_by(empresa_id=ej.empresa_id, codigo=cuenta).first():
        sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=cuenta, nombre=nombre))
        sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=n, fecha=date(2025, 9, 1), concepto="Gasto", lineas=[LineaAsiento(cuenta, D(importe)), LineaAsiento("57200001", -D(importe))])


def test_los_datos_se_guardan_y_se_leen_igual(sesion, ej):
    assert isd.datos_del_ejercicio(sesion, ej) == isd.DatosIS()
    datos = isd.DatosIS(marcas=[66, 6], forzar_25=True, personal_fijo=1, firmante_nif="00000014Z", retenciones={"capital_mobiliario": D("12.34")}, intereses_demora=D("5"),
                        correcciones=[isd.Correccion("Donación", aumento=D("100"), permanente=False)])
    isd.guardar_datos(sesion, ej, datos)
    leidos = isd.datos_del_ejercicio(sesion, ej)
    assert leidos.marcas == [66, 6] and leidos.forzar_25 and leidos.patrimonial and leidos.retenciones == {"capital_mobiliario": D("12.34")} and leidos.intereses_demora == D("5.00")
    assert leidos.correcciones == [isd.Correccion("Donación", aumento=D("100.00"), disminucion=D("0.00"), permanente=False)]
    isd.guardar_datos(sesion, ej, leidos)  # segunda vez: actualiza, no duplica
    assert isd.datos_del_ejercicio(sesion, ej).marcas == [66, 6]


def test_se_rechazan_los_datos_invalidos(sesion, ej):
    with pytest.raises(ErrorContable, match="no existen en el modelo 200: 99999"):
        isd.guardar_datos(sesion, ej, isd.DatosIS(marcas=[99999]))
    with pytest.raises(ErrorContable, match="necesita un concepto"):
        isd.guardar_datos(sesion, ej, isd.DatosIS(correcciones=[isd.Correccion(" ", aumento=D(1))]))
    with pytest.raises(ErrorContable, match="importe negativo"):
        isd.guardar_datos(sesion, ej, isd.DatosIS(correcciones=[isd.Correccion("x", aumento=D(-1))]))
    with pytest.raises(ErrorContable, match="Tipos de retención desconocidos"):
        isd.guardar_datos(sesion, ej, isd.DatosIS(retenciones={"inventada": D(1)}))


def test_los_caracteres_salen_del_diseno_del_modelo():
    carac = dict(isd.caracteres_disponibles())
    assert carac[66] == "Entidad patrimonial" and carac[27].startswith("Base imponible negativa o cero") and 88 in carac and len(carac) == 74


def test_resultado_y_cifra_de_negocios_salen_de_la_contabilidad(sesion, ej):
    # fixture: venta 1.210 y gasto 300
    assert isd.cifra_de_negocios(sesion, ej) == D(1210) and isd.resultado_contable(sesion, ej) == D(910)


def test_las_multas_se_suman_como_correccion_permanente_sin_tocar_la_contabilidad(sesion, ej):
    _gasto(sesion, ej, "67800005", 250, 3, "MULTAS Y SANCIONES")
    _gasto(sesion, ej, "63000000", 40, 4, "IMPUESTO CORRIENTE")
    auto = isd.correcciones_automaticas(sesion, ej)
    assert [(c.concepto, c.aumento, c.disminucion, c.permanente, c.automatica) for c in auto] == [
        ("Gasto no deducible: 67800005 MULTAS Y SANCIONES", D(250), D(0), True, True), ("Impuesto sobre Sociedades: 63000000 IMPUESTO CORRIENTE", D(40), D(0), True, True)]
    assert isd.total_correcciones(auto) == (D(290), D(0)) and isd.resultado_contable(sesion, ej) == D(910 - 290)  # el resultado contable no cambia: las multas siguen siendo gasto
    isd.guardar_prefijos(sesion, ej.empresa_id, isd.PARAM_NO_DEDUCIBLES, "67800000")  # solo esa cuenta
    assert [c.concepto for c in isd.correcciones_automaticas(sesion, ej)] == ["Impuesto sobre Sociedades: 63000000 IMPUESTO CORRIENTE"]
    with pytest.raises(ErrorContable, match="por su código"):
        isd.guardar_prefijos(sesion, ej.empresa_id, isd.PARAM_NO_DEDUCIBLES, "multas")


def test_el_tipo_de_gravamen_sigue_las_reglas_y_se_puede_forzar(sesion, ej):
    e25, e26 = ej, Ejercicio(empresa_id=ej.empresa_id, anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31))
    micro = isd.tipo_de_gravamen(isd.DatosIS(), e25, D("31737.30"))
    assert (micro.campo, micro.marcar_00088, micro.tipos) == ("2122", True, (D(21), D(22)))
    assert isd.tipo_de_gravamen(isd.DatosIS(), e26, D(100)).campo == "1921"
    assert isd.tipo_de_gravamen(isd.DatosIS(marcas=[66]), e25, D(100)).campo == "2500"  # patrimonial (Empresa B)
    assert isd.tipo_de_gravamen(isd.DatosIS(forzar_25=True), e25, D(100)).campo == "2500"
    assert isd.tipo_de_gravamen(isd.DatosIS(), e25, D(1_000_000)).campo == "2500" and isd.tipo_de_gravamen(isd.DatosIS(), e25, None).campo == "2500"
    antiguo = Ejercicio(empresa_id=ej.empresa_id, anio=2024, fecha_inicio=date(2024, 1, 1), fecha_fin=date(2024, 12, 31))
    assert "No hay regla" in isd.tipo_de_gravamen(isd.DatosIS(), antiguo, D(100)).motivo
    assert "patrimonial" in isd.tipo_de_gravamen(isd.DatosIS(marcas=[66]), e25, D(1)).motivo


def test_la_cuota_se_calcula_por_tramos():
    micro, general = isd.TipoGravamen("2122", True, ""), isd.TipoGravamen("2500", False, "")
    assert isd.cuota_integra(D("1038.90"), general) == D("259.73") and isd.cuota_integra(D("1038.90"), micro) == D("218.17")  # el caso de Empresa B 2025
    assert isd.cuota_integra(D("60000"), micro) == D("10500.00") + D("2200.00") and isd.cuota_integra(D("-14532.46"), micro) == 0


def test_limite_y_reparto_de_la_compensacion_de_bases_negativas():
    assert isd.limite_de_compensacion(D(1000), D(500000)) == D(1000)  # hasta 1 M€ siempre se puede compensar entera la base and isd.limite_de_compensacion(D("2000000"), D(500000)) == D("1400000.00")
    assert isd.limite_de_compensacion(D("1500000"), D(500000)) == D("1050000.00") and isd.limite_de_compensacion(D("1500000"), D(30_000_000)) == D("1000000")  # 50 % = 750.000 < 1 M€
    assert isd.limite_de_compensacion(D(500000), D(70_000_000)) == D(500000) and isd.limite_de_compensacion(D(-5), D(0)) == 0
    assert isd.compensar([(2016, D(100)), (2014, D(50)), (2020, D(300))], D(200)) == [(2014, D(50)), (2016, D(100)), (2020, D(50))]
    assert isd.compensar([(2014, D(50))], D(0)) == []


def test_las_bases_negativas_se_guardan_y_suman(sesion, ej):
    e = ej.empresa_id
    for anio, base in ((2014, "4161.28"), (2015, "9666.40"), (2025, "14532.46")):
        isd.guardar_base_negativa(sesion, e, anio, D(base))
    isd.guardar_base_negativa(sesion, e, 2016, D("15094.21"), D("1000"))
    isd.guardar_base_negativa(sesion, e, 2017, D("16707.27"), pendiente_manual=D("100"))
    assert [b.anio for b in isd.bases_negativas(sesion, e)] == [2014, 2015, 2016, 2017, 2025]
    assert isd.pendiente_hasta(sesion, e, 2025) == D("4161.28") + D("9666.40") + D("14094.21") + D("100.00") and isd.pendiente_hasta(sesion, e, 2026) == isd.pendiente_hasta(sesion, e, 2025) + D("14532.46")
    isd.guardar_base_negativa(sesion, e, 2014, D("5000"))  # actualiza
    assert len(isd.bases_negativas(sesion, e)) == 5
    with pytest.raises(ErrorContable, match="más de lo generado"):
        isd.guardar_base_negativa(sesion, e, 2018, D(10), D(20))
    with pytest.raises(ErrorContable, match="en positivo"):
        isd.guardar_base_negativa(sesion, e, 2018, D(-10))


def test_el_precalculo_encadena_resultado_correcciones_compensacion_y_cuota(sesion, ej):
    _gasto(sesion, ej, "67800005", 100, 3, "MULTAS Y SANCIONES")  # el resultado baja a 810 y la multa se suma de nuevo
    e = ej.empresa_id
    isd.guardar_base_negativa(sesion, e, 2024, D("500"))
    p = isd.precalculo(sesion, ej)
    assert (p.resultado, p.aumentos, p.base_previa, p.cifra_anterior) == (D(810), D(100), D(910), None)  # sin ejercicio anterior no hay cifra: tipo general
    assert (p.compensacion, p.base_imponible, p.tipo.campo, p.cuota_integra, p.bases_pendientes) == (D(500), D(410), "2500", D("102.50"), D(500)) and p.compensaciones == [(2024, D(500))]
    p2 = isd.precalculo(sesion, ej, isd.DatosIS(compensar_bases_negativas=False, correcciones=[isd.Correccion("Otra", disminucion=D(10), permanente=False)]))
    assert (p2.compensacion, p2.base_imponible, p2.disminuciones) == (D(0), D(900), D(10))
    # con pérdidas no hay cuota y la base negativa generada es lo que se arrastra
    _gasto(sesion, ej, "62900000", 5000, 4)
    p3 = isd.precalculo(sesion, ej)
    assert p3.base_previa < 0 and p3.compensacion == 0 and p3.cuota_integra == 0 and p3.base_negativa_generada == -p3.base_imponible > 0


# ------------------------------------------------------------------------------------------------ la pantalla

from sqlalchemy import select  # noqa: E402

from conta_pridalac.db.modelos import BaseNegativa, ImpuestoSociedades  # noqa: E402
from test_web_auditoria import _sesion, cliente  # noqa: E402,F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/modelo-200"


def test_la_pantalla_guarda_los_datos_y_enseña_el_calculo(cliente):
    assert cliente.get(BASE).status_code == 200 and "Impuesto sobre Sociedades" in cliente.get("/e/prueba/2026").text
    assert "Ejercicio abierto" in cliente.get(f"{BASE}/tabla").text
    ficha = cliente.get(f"{BASE}/f/2026").text
    assert "Cálculo de la base imponible" in ficha and "Caracteres de la declaración" in ficha and "Bases imponibles negativas" in ficha and "00066" in ficha
    r = cliente.post(f"{BASE}/guardar", data={
        "id": "2026", "accion": "guardar", "compensar": "1", "car_66": "1", "personal_fijo": "0", "firmante_nif": "00000014z", "firmante_nombre": "Lopez, Elena", "ret_premios": "1.234,50",
        "corr_0_concepto": "Donación sin derecho a deducción", "corr_0_aumento": "100,00", "corr_0_perm": "1", "no_deducibles": "678", "cuentas_impuesto": "630",
        "bn_0_anio": "2024", "bn_0_base": "500,00", "bn_0_aplicado": "0", "bn_1_anio": "2023", "bn_1_base": "300,25"})
    assert r.status_code == 200 and "guardados" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"] and "Donación sin derecho a deducción" in r.text
    s = _sesion(cliente)
    datos = isd.DatosIS.de_json(s.scalar(select(ImpuestoSociedades)).datos)
    assert datos.marcas == [66] and datos.patrimonial and datos.firmante_nif == "00000014Z" and datos.retenciones == {"premios": D("1234.50")} and datos.correcciones[0].aumento == D("100.00")
    assert [(b.anio, b.base) for b in s.scalars(select(BaseNegativa).order_by(BaseNegativa.anio))] == [(2023, D("300.25")), (2024, D("500.00"))]
    # un año sin importe se borra; un dato mal escrito no guarda nada y lo dice
    cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "guardar", "compensar": "1", "bn_0_anio": "2023", "bn_0_base": ""})
    assert [b.anio for b in _sesion(cliente).scalars(select(BaseNegativa))] == [2024]
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "guardar", "ret_otros": "mucho"})
    assert "no es un importe válido" in r.text
