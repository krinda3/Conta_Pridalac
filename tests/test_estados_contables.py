"""Saldos acumulados, balance de situación y pérdidas y ganancias de gestión."""
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.estados_contables import balance_de_situacion, cuenta_de_perdidas_y_ganancias, saldos_acumulados
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
CUENTAS = (("10000000", "CAPITAL"), ("40000001", "PROVEEDOR UNO"), ("43000001", "CLIENTE UNO"), ("47200000", "IVA SOPORTADO"), ("47700000", "IVA REPERCUTIDO"),
           ("57200001", "BANCO"), ("62300000", "SERVICIOS"), ("70000000", "VENTAS"))


def montar(sesion):
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in CUENTAS:
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()

    def asiento(numero, fecha, *lineas, subtipo="M"):
        grabar_asiento(sesion, ej, tipo=4, numero=numero, sub=0, fecha=fecha, concepto="prueba", subtipo=subtipo, lineas=[LineaAsiento(c, D(i)) for c, i in lineas])

    asiento(1, date(2025, 1, 10), ("57200001", "10000.00"), ("10000000", "-10000.00"))
    asiento(2, date(2025, 2, 5), ("62300000", "1000.00"), ("47200000", "210.00"), ("40000001", "-1210.00"))
    asiento(3, date(2025, 3, 15), ("43000001", "2420.00"), ("70000000", "-2000.00"), ("47700000", "-420.00"))
    asiento(4, date(2025, 3, 20), ("40000001", "1210.00"), ("57200001", "-1210.00"))
    asiento(5, date(2025, 12, 31), ("70000000", "2000.00"), ("62300000", "-1000.00"), ("10000000", "-1000.00"), subtipo="R")  # regularización: sin incluirla no cuenta
    return ej


@pytest.fixture
def ej(sesion):
    return montar(sesion)


def por_cuenta(lista):
    return {x.cuenta: x for x in lista}


def test_saldos_acumulados_de_un_mes(sesion, ej):
    f = por_cuenta(saldos_acumulados(sesion, ej, 3, nivel=8))
    assert (f["57200001"].anterior, f["57200001"].debe, f["57200001"].haber, f["57200001"].acumulado) == (D("10000.00"), D("0.00"), D("1210.00"), D("8790.00"))
    assert (f["40000001"].anterior, f["40000001"].acumulado, f["40000001"].deudor, f["40000001"].acreedor) == (D("-1210.00"), D("0.00"), D("0.00"), D("0.00"))
    assert f["43000001"].deudor == D("2420.00") and f["70000000"].acreedor == D("2000.00") and f["10000000"].acreedor == D("10000.00")
    assert saldos_acumulados(sesion, ej, 1)[0].anterior == D("0.00")
    assert "70000000" not in por_cuenta(saldos_acumulados(sesion, ej, 1))  # en enero todavía no hay ventas
    assert por_cuenta(saldos_acumulados(sesion, ej, 12, nivel=2))["57"].acumulado == D("8790.00")


def test_los_saldos_acumulados_excluyen_el_cierre_salvo_que_se_pida(sesion, ej):
    assert por_cuenta(saldos_acumulados(sesion, ej, 12))["70000000"].acreedor == D("2000.00")
    assert por_cuenta(saldos_acumulados(sesion, ej, 12, incluir_cierre=True))["70000000"].acumulado == D("0.00")
    with pytest.raises(ValueError):
        saldos_acumulados(sesion, ej, 13)


def test_perdidas_y_ganancias_por_subgrupo_y_por_cuenta(sesion, ej):
    lineas = cuenta_de_perdidas_y_ganancias(sesion, ej)
    assert [(l.tipo, l.codigo, l.importe) for l in lineas] == [
        ("titulo", "7", None), ("cuenta", "70", D("2000.00")), ("subtotal", "7", D("2000.00")),
        ("titulo", "6", None), ("cuenta", "62", D("1000.00")), ("subtotal", "6", D("1000.00")), ("total", "", D("1000.00"))]
    assert [l.codigo for l in cuenta_de_perdidas_y_ganancias(sesion, ej, nivel=3) if l.tipo == "cuenta"] == ["700", "623"]
    assert cuenta_de_perdidas_y_ganancias(sesion, ej, hasta=date(2025, 2, 28))[-1].importe == D("-1000.00")  # sólo el gasto de febrero
    assert cuenta_de_perdidas_y_ganancias(sesion, ej, incluir_cierre=True)[-1].importe == D("0.00")  # con la regularización, los ingresos y los gastos quedan a cero


def test_balance_de_situacion_cuadra_y_reparte_por_signo(sesion, ej):
    lineas = balance_de_situacion(sesion, ej)
    cuentas = {l.codigo: l.importe for l in lineas if l.tipo == "cuenta" and l.codigo}
    assert cuentas == {"430": D("2420.00"), "472": D("210.00"), "572": D("8790.00"), "100": D("10000.00"), "477": D("420.00")}  # el proveedor ya está pagado: saldo cero
    totales = [l for l in lineas if l.tipo == "total"]
    assert [t.importe for t in totales] == [D("11420.00"), D("11420.00")]
    assert next(l for l in lineas if l.nombre.startswith("Resultado")).importe == D("1000.00") and lineas[-1].importe == D("0.00")


def test_el_balance_cuadra_en_cualquier_rango(sesion, ej):
    for desde, hasta in ((None, date(2025, 2, 28)), (date(2025, 3, 1), None), (date(2025, 2, 1), date(2025, 3, 16))):
        assert balance_de_situacion(sesion, ej, desde=desde, hasta=hasta)[-1].importe == D("0.00")


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    montar(s)
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def test_las_tres_pantallas(cliente):
    menu = cliente.get("/e/prueba/2025").text
    assert all(f"/{n}" in menu for n in ("saldos-acumulados", "balance-situacion", "perdidas-ganancias"))
    saldos = cliente.get("/e/prueba/2025/saldos-acumulados/tabla", params={"mes": "3", "nivel": "12"}).text
    assert "BANCO" in saldos and "8.790,00" in saldos
    from types import SimpleNamespace

    from conta_pridalac.web.estados import ListadoSaldosAcumulados

    ctx = SimpleNamespace(empresa=SimpleNamespace(nombre="Empresa de Prueba"), ejercicio=SimpleNamespace(anio=2025))
    assert ListadoSaldosAcumulados().subtitulo(ctx, {"mes": "3"}) == "Empresa de Prueba · ejercicio 2025 · acumulado a fin de marzo"  # sale en el encabezado de lo exportado
    pyg = cliente.get("/e/prueba/2025/perdidas-ganancias/tabla").text
    assert "RESULTADO" in pyg and "1.000,00" in pyg and "2.000,00" in pyg
    balance = cliente.get("/e/prueba/2025/balance-situacion/tabla").text
    assert "TOTAL ACTIVO" in balance and "11.420,00" in balance and "cero si la contabilidad cuadra" in balance
    assert re.search(r"Resultado del ejercicio", balance)
