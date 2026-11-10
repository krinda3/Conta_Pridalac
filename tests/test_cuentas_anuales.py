"""Balance y PyG de PYMES: las líneas contra las cifras de los listados oficiales del programa anterior (Empresa A, ejercicio 2025)."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.cuentas_anuales import ACTIVO, PASIVO, PYG, balance_pymes, ejercicio_anterior, pyg_pymes

D = Decimal

# saldos por cuenta de Empresa A a 31/12/2025 (positivo = deudor)
SALDOS_EMPRESA_A_2025 = {
    "20600000": "179.52", "21000000": "61415.50", "21100000": "28810.44", "21200000": "15338.48", "21300000": "7273.77", "21700000": "1987.42", "21800000": "18538.83", "23000000": "2100.00",
    "28100000": "-43812.80", "32100000": "11777.56", "43000001": "8003.99", "47000000": "3008.27", "47200000": "2190.31", "57200001": "10595.01",
    "10000000": "-34580.00", "11800000": "1631.54", "12100000": "187824.91", "41000001": "-3772.88", "47500000": "-38.08", "47700000": "-615.70", "55100000": "-292388.55",
    "70100000": "-16234.69", "74000000": "-2870.48",
    "60000000": "10858.50", "60100000": "4190.86", "60200000": "1360.00", "60700000": "245.00", "62200000": "6797.16", "62300000": "2020.87", "62400000": "170.87", "62500000": "1813.40",
    "62600000": "60.18", "62900000": "4088.90", "63100000": "248.05", "68100000": "674.39", "68200000": "1109.45",
}
# lo que imprime el programa anterior (balance y PyG de PYMES de Empresa A, 2025)
ESPERADO_BALANCE = {
    "A": "91831.16", "A.I": "179.52", "A.II": "91651.64", "B": "35575.14", "B.I": "11777.56", "B.II": "13202.57", "B.II.1": "8003.99", "B.II.1b": "8003.99", "B.II.3": "5198.58", "B.VI": "10595.01",
    "TA": "127406.30", "PN": "-169408.91", "PN.1": "-169408.91", "PN.1.I": "34580.00", "PN.1.I.1": "34580.00", "PN.1.V": "-187824.91", "PN.1.VI": "-1631.54", "PN.1.VII": "-14532.46",
    "PC": "296815.21", "PC.II": "292388.55", "PC.II.3": "292388.55", "PC.IV": "4426.66", "PC.IV.2": "4426.66", "TP": "127406.30",
}
ESPERADO_PYG = {"1": "16234.69", "4": "-16654.36", "5": "2870.48", "7": "-15199.43", "8": "-1783.84", "A": "-14532.46", "B": "0.00", "C": "-14532.46", "D": "-14532.46"}


def montar(sesion, saldos=SALDOS_EMPRESA_A_2025, anio=2025, empresa=None, cuadrar_en="57200001", extras=("12900000",)):
    """Un asiento con los saldos dados; si no cuadran, la diferencia se lleva a `cuadrar_en` (para poder cambiar una cuenta sin rehacer las demás)."""
    e = empresa or Empresa(codigo=1, nombre="Empresa A S.L.", nif="B00000010")
    ej = Ejercicio(anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    saldos = dict(saldos)
    descuadre = sum((D(i) for i in saldos.values()), D("0"))
    if descuadre:
        saldos[cuadrar_en] = str(D(saldos.get(cuadrar_en, "0")) - descuadre)
    for codigo in list(saldos) + list(extras):
        if not sesion.query(Cuenta).filter_by(empresa_id=e.id, codigo=codigo).first():
            sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=f"CUENTA {codigo}"))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=1, sub=0, fecha=date(anio, 6, 30), concepto="saldos del ejercicio", subtipo="M", lineas=[LineaAsiento(c, D(i)) for c, i in saldos.items() if D(i)])
    return ej


@pytest.fixture
def ej(sesion):
    return montar(sesion)


def test_el_balance_coincide_linea_a_linea_con_programa_anterior(sesion, ej):
    b = balance_pymes(sesion, ej)
    obtenido = {l.id: l.importe for l in b.lineas}
    for id_, esperado in ESPERADO_BALANCE.items():
        assert obtenido[id_] == D(esperado), id_
    assert b.sin_asignar == []
    assert len(b.avisos) == 1 and b.avisos[0].startswith("118") and "deudor" in b.avisos[0]  # la 118 de Empresa A tiene saldo deudor: lo normal es acreedor


def test_la_pyg_coincide_linea_a_linea_con_programa_anterior(sesion, ej):
    p = pyg_pymes(sesion, ej)
    obtenido = {l.id: l.importe for l in p.lineas}
    for id_, esperado in ESPERADO_PYG.items():
        assert obtenido[id_] == D(esperado), id_
    assert p.sin_asignar == [] and p.avisos == []


def test_las_lineas_sin_cuentas_salen_en_blanco(sesion, ej):
    obtenido = {l.id: l.importe for l in balance_pymes(sesion, ej).lineas}
    assert obtenido["A.VII"] is None and obtenido["PNC.VI"] is None and obtenido["A.VI"] == D("0.00") and obtenido["PC.VI"] == D("0.00")


def test_la_regularizacion_no_cambia_el_balance_ni_la_pyg(sesion, ej):
    antes = ({l.id: l.importe for l in balance_pymes(sesion, ej).lineas}, {l.id: l.importe for l in pyg_pymes(sesion, ej).lineas})
    resultado = sum((D(i) for c, i in SALDOS_EMPRESA_A_2025.items() if c[0] in "67"), D("0"))
    grabar_asiento(sesion, ej, tipo=4, numero=2, sub=0, fecha=date(2025, 12, 31), concepto="regularización", subtipo="R",
                   lineas=[LineaAsiento(c, -D(i)) for c, i in SALDOS_EMPRESA_A_2025.items() if c[0] in "67"] + [LineaAsiento("12900000", resultado)])
    assert ({l.id: l.importe for l in balance_pymes(sesion, ej).lineas}, {l.id: l.importe for l in pyg_pymes(sesion, ej).lineas}) == antes


def test_una_cuenta_sin_linea_se_ve_y_no_se_pierde(sesion):
    saldos = dict(SALDOS_EMPRESA_A_2025) | {"58000001": "100.00", "10000000": "-34680.00"}  # una cuenta 580 (activos mantenidos para la venta), que el modelo de PYMES no tiene
    b = balance_pymes(sesion, montar(sesion, saldos))
    assert [(c, s) for c, _, s in b.sin_asignar] == [("58000001", D("100.00"))]
    assert b.importe("TA") + D("100.00") == b.importe("TP") == D("127506.30")  # el activo se queda 100 € corto: justo lo que sale en «sin asignar»


def test_un_saldo_de_signo_contrario_se_resta_en_su_linea_y_se_avisa(sesion):
    # como en 2024 de Empresa A: un 410 con saldo deudor de 1.894,18 resta dentro de «Otros acreedores» (el programa anterior) y se avisa de que el PGC lo llevaría al activo
    saldos = dict(SALDOS_EMPRESA_A_2025) | {"41000001": "1894.18"}
    b = balance_pymes(sesion, montar(sesion, saldos))
    assert b.importe("PC.IV.2") == D("-1894.18") + D("38.08") + D("615.70") and any(a.startswith("410") and "deudor" in a for a in b.avisos)
    assert not any(a.startswith("281") for a in b.avisos)  # una amortización acumulada es acreedora por naturaleza
    assert b.importe("TA") == b.importe("TP")


def test_hay_lineas_de_todo_el_modelo(sesion, ej):
    assert len([l for l in ACTIVO + PASIVO if l.total]) >= 7 and [l.id for l in PYG if l.total] == ["A", "B", "C", "D"]
    assert ejercicio_anterior(sesion, ej) is None


@pytest.fixture
def cliente(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
    from conta_pridalac.web.app import crear_app
    from conta_pridalac.web.config import Configuracion

    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa A S.L.", nif="B00000010")
    s.add(e)
    s.flush()
    montar(s, SALDOS_EMPRESA_A_2025, anio=2025, empresa=e)
    montar(s, {"57200001": "1000.00", "10000000": "-1000.00"}, anio=2024, empresa=e, extras=())
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def test_las_dos_pantallas_con_el_ejercicio_anterior(cliente):
    balance = cliente.get("/e/prueba/2025/balance-oficial/tabla").text
    assert "TOTAL ACTIVO (A + B)" in balance and "127.406,30" in balance and "91.651,64" in balance and "1.000,00" in balance  # el anterior, en su columna
    assert "I. Inmovilizado intangible" in balance and "2. (Capital no exigido)" in balance
    pyg = cliente.get("/e/prueba/2025/pyg-oficial/tabla").text
    assert "A) RESULTADO DE EXPLOTACIÓN" in pyg and "-16.654,36" in pyg and "D) RESULTADO DEL EJERCICIO" in pyg and "-14.532,46" in pyg


def test_la_caja_de_listados_en_el_menu(cliente):
    panel = cliente.get("/e/prueba/2025").text
    assert 'data-caja="listados"' in panel and all(f"/{n}" in panel for n in ("balance-oficial", "pyg-oficial", "saldos-acumulados", "estado-cambios-pn", "diario", "mayor"))
    assert 'data-caja="gestion"' in panel and all(f"/{n}" in panel for n in ("gastos-categoria", "facturacion-terceros"))  # los listados de gestión, aparte de los contables


# ------------------------------------------------------------------------------------------------ estado de cambios en el patrimonio neto

SALDOS_EMPRESA_A_2024 = {"10000000": "-34580.00", "11800000": "1631.54", "12100000": "170244.88", "62900000": "17580.03"}  # el resto lo cuadra «montar» en el banco


def test_el_estado_de_cambios_coincide_con_el_listado_de_programa_anterior(sesion):
    from conta_pridalac.servicios.cuentas_anuales import estado_cambios_pn

    e = Empresa(codigo=1, nombre="Empresa A S.L.", nif="B00000010")
    sesion.add(e)
    sesion.flush()
    montar(sesion, SALDOS_EMPRESA_A_2024, anio=2024, empresa=e, extras=())
    ej = montar(sesion, SALDOS_EMPRESA_A_2025, anio=2025, empresa=e, extras=())
    filas = {f.id: f for f in estado_cambios_pn(sesion, ej).filas}
    esperado = {
        "SI": {"capital": "34580.00", "anteriores": "-170244.88", "aportaciones": "-1631.54", "resultado": "-17580.03"},  # saldo final 2024; total −154.876,45
        "IG": {"resultado": "-14532.46"},
        "OS": {},
        "OV": {"anteriores": "-17580.03", "resultado": "17580.03"},  # la aplicación del resultado de 2024
        "SF": {"capital": "34580.00", "anteriores": "-187824.91", "aportaciones": "-1631.54", "resultado": "-14532.46"},  # saldo final 2025; total −169.408,91
    }
    for id_, valores in esperado.items():
        assert {k: v for k, v in filas[id_].valores.items() if v} == {k: D(v) for k, v in valores.items()}, id_
    assert (filas["SI"].suma, filas["SF"].suma, filas["IG"].suma, filas["OV"].suma) == (D("-154876.45"), D("-169408.91"), D("-14532.46"), D("0.00"))
    assert filas["SA"].valores == filas["SI"].valores and filas["AJ1"].valores == {}
    assert filas["SI"].etiqueta == "A) SALDO, FINAL DEL AÑO 2024" and filas["SF"].etiqueta == "C) SALDO, FINAL DEL AÑO 2025"


def test_las_filas_del_estado_suman_hasta_el_saldo_final(sesion):
    from conta_pridalac.servicios.cuentas_anuales import estado_cambios_pn

    ej = montar(sesion)  # sin ejercicio anterior
    estado = estado_cambios_pn(sesion, ej)
    filas = {f.id: f for f in estado.filas}
    assert any("No hay ejercicio 2024" in a for a in estado.avisos) and filas["SI"].suma == D("0.00")
    assert filas["SI"].suma + filas["IG"].suma + filas["OS"].suma + filas["OV"].suma == filas["SF"].suma == D("-169408.91")


def test_la_pantalla_del_estado_de_cambios(cliente):
    estado = cliente.get("/e/prueba/2025/estado-cambios-pn/tabla").text
    assert "A) SALDO, FINAL DEL AÑO 2024" in estado and "C) SALDO, FINAL DEL AÑO 2025" in estado and "III. Otras variaciones del patrimonio neto" in estado
    assert "-169.408,91" in estado and "34.580,00" in estado and "Resultado del ejercicio" in estado
    assert "/estado-cambios-pn" in cliente.get("/e/prueba/2025").text


def test_la_551_va_al_activo_o_al_pasivo_segun_su_signo(sesion):
    # El programa anterior la configura con asterisco: cuenta corriente con socios acreedora = otras deudas a corto plazo; deudora = inversiones financieras a corto plazo
    e = Empresa(codigo=1, nombre="Empresa A S.L.", nif="B00000010")
    sesion.add(e)
    sesion.flush()
    acreedora = balance_pymes(sesion, montar(sesion, anio=2025, empresa=e))
    assert acreedora.importe("PC.II.3") == D("292388.55") and acreedora.importe("B.IV") == D("0.00")
    b = balance_pymes(sesion, montar(sesion, dict(SALDOS_EMPRESA_A_2025) | {"55100000": "10000.00"}, anio=2024, empresa=e, extras=()))
    assert b.importe("B.IV") == D("10000.00") and b.importe("PC.II.3") == D("0.00") and b.importe("TA") == b.importe("TP")
    assert not any(a.startswith("551") for a in b.avisos)  # no es una anomalía: es lo previsto


def test_cuentas_que_faltaban_en_la_primera_version(sesion):
    saldos = dict(SALDOS_EMPRESA_A_2025) | {"54400001": "100.00", "50200001": "-50.00", "50700001": "-50.00"}
    b = balance_pymes(sesion, montar(sesion, saldos))
    assert b.sin_asignar == [] and b.importe("B.II.3") == D("5198.58") + D("100.00") and b.importe("PC.VI") == D("100.00")


def test_deterioros_y_cuentas_del_grupo_59_segun_programa_anterior(sesion):
    saldos = dict(SALDOS_EMPRESA_A_2025) | {"59330001": "500.00", "59430001": "-100.00", "29350001": "-30.00", "20400001": "200.00", "28040001": "-20.00"}
    b = balance_pymes(sesion, montar(sesion, saldos))
    assert b.sin_asignar == [] and b.importe("B.III") == D("400.00") and b.importe("A.V") == D("-30.00") and b.importe("A.I") == D("179.52") + D("200.00") - D("20.00")


def test_la_pyg_asigna_las_cuentas_como_programa_anterior(sesion):
    # cuentas de los desgloses de la configuración del programa anterior, una por línea
    saldos = {"79570001": "-10.00", "64000001": "100.00", "69310001": "5.00", "60900001": "-3.00", "75200001": "-40.00", "76020001": "-7.00", "66100001": "2.00", "76620001": "-1.00", "67000001": "4.00",
              "62300001": "6.00", "65000001": "3.00", "63400001": "1.00"}
    p = pyg_pymes(sesion, montar(sesion, saldos, extras=()))
    obtenido = {l.id: l.importe for l in p.lineas}
    assert p.sin_asignar == []
    assert (obtenido["6"], obtenido["4"], obtenido["5"], obtenido["13b"], obtenido["14"], obtenido["17"], obtenido["11"], obtenido["7"]) == (
        D("-90.00"), D("-2.00"), D("40.00"), D("7.00"), D("-2.00"), D("1.00"), D("-4.00"), D("-10.00"))


def test_la_5525_va_segun_su_signo_y_la_5523_al_grupo(sesion):
    e = Empresa(codigo=1, nombre="Empresa A S.L.", nif="B00000010")
    sesion.add(e)
    sesion.flush()
    base = {"10000000": "-1000.00"}
    deudora = balance_pymes(sesion, montar(sesion, base | {"55250001": "300.00", "55230001": "200.00"}, anio=2024, empresa=e, extras=()))
    assert deudora.importe("B.IV") == D("300.00") and deudora.importe("B.III") == D("200.00") and deudora.importe("PC.II.3") == D("0.00")
    acreedora = balance_pymes(sesion, montar(sesion, base | {"55250001": "-300.00", "55230001": "-200.00"}, anio=2025, empresa=e, extras=()))
    assert acreedora.importe("PC.II.3") == D("300.00") and acreedora.importe("PC.III") == D("200.00") and acreedora.importe("B.IV") == D("0.00")
    assert deudora.sin_asignar == [] and acreedora.sin_asignar == []
