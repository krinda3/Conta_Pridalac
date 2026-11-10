"""Facturación por cliente o proveedor: servicio y pantalla."""
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Ejercicio, Empresa, Factura, FacturaIva, Tercero
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.facturacion_terceros import facturacion_por_tercero
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal


def montar(sesion):
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    agricultor = Tercero(empresa_id=e.id, clase="P", nombre="AGRICULTOR UNO", nif="12345678Z")
    cliente = Tercero(empresa_id=e.id, clase="C", nombre="CLIENTE DOS", nif="B23365448")
    sesion.add_all([agricultor, cliente])
    sesion.flush()

    def factura(sentido, numero, fecha, t, base, pct="21", retencion="0"):
        base = D(base)
        cuota = (base * D(pct) / 100).quantize(D("0.01"))
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"F-{numero}", tercero_id=t.id if t else None,
                    total=base + cuota - D(retencion))
        f.ivas.append(FacturaIva(base=base, pct_iva=D(pct), cuota_iva=cuota))
        sesion.add(f)

    factura("R", 1, date(2025, 2, 3), agricultor, "1000.00", retencion="20.00")
    factura("R", 2, date(2025, 11, 3), agricultor, "500.00")
    factura("E", 1, date(2025, 5, 3), cliente, "4000.00")
    factura("R", 3, date(2025, 6, 1), None, "100.00")
    sesion.flush()
    return ej


def test_agrupa_por_tercero_y_sentido_de_mayor_a_menor(sesion):
    ej = montar(sesion)
    g = facturacion_por_tercero(sesion, ej)
    assert [(x.nombre, x.sentido, len(x.facturas), x.base, x.iva, x.total_con_iva, x.neto) for x in g] == [
        ("CLIENTE DOS", "E", 1, D("4000.00"), D("840.00"), D("4840.00"), D("4840.00")),
        ("AGRICULTOR UNO", "R", 2, D("1500.00"), D("315.00"), D("1815.00"), D("1795.00")),  # el neto descuenta la retención de 20 €
        ("(sin tercero)", "R", 1, D("100.00"), D("21.00"), D("121.00"), D("121.00")),
    ]


def test_rango_de_fechas_sentido_texto_y_minimo(sesion):
    ej = montar(sesion)
    assert [(x.nombre, len(x.facturas)) for x in facturacion_por_tercero(sesion, ej, desde=date(2025, 6, 1))] == [("AGRICULTOR UNO", 1), ("(sin tercero)", 1)]  # la factura al cliente es de mayo
    assert [x.nombre for x in facturacion_por_tercero(sesion, ej, hasta=date(2025, 3, 31))] == ["AGRICULTOR UNO"]
    assert [x.nombre for x in facturacion_por_tercero(sesion, ej, sentido="E")] == ["CLIENTE DOS"]
    assert [x.nombre for x in facturacion_por_tercero(sesion, ej, texto="b2336")] == ["CLIENTE DOS"] and [x.nombre for x in facturacion_por_tercero(sesion, ej, texto="uno")] == ["AGRICULTOR UNO"]
    assert [x.nombre for x in facturacion_por_tercero(sesion, ej, minimo=D("3005.06"))] == ["CLIENTE DOS"]


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


def test_la_pantalla_y_su_menu(cliente):
    assert "/facturacion-terceros" in cliente.get("/e/prueba/2025").text
    tabla = cliente.get("/e/prueba/2025/facturacion-terceros/tabla").text
    assert "CLIENTE DOS" in tabla and "AGRICULTOR UNO" in tabla and "4.840,00" in tabla and "3 filas" in tabla
    solo = cliente.get("/e/prueba/2025/facturacion-terceros/tabla", params={"sentido": "E"}).text
    assert "CLIENTE DOS" in solo and "AGRICULTOR UNO" not in solo
    rango = cliente.get("/e/prueba/2025/facturacion-terceros/tabla", params={"hasta": "31/03/2025"}).text
    assert "AGRICULTOR UNO" in rango and "CLIENTE DOS" not in rango


def test_el_detalle_enseña_las_facturas_del_mismo_rango(cliente):
    tabla = cliente.get("/e/prueba/2025/facturacion-terceros/tabla", params={"hasta": "31/03/2025"}).text
    id_ = re.search(r'data-id="([^"]+)"', tabla).group(1)
    detalle = cliente.get(f"/e/prueba/2025/facturacion-terceros/f/{id_}")
    assert detalle.status_code == 200 and "F-1" in detalle.text and "F-2" not in detalle.text and "AGRICULTOR UNO" in detalle.text
    completo = cliente.get("/e/prueba/2025/facturacion-terceros/tabla").text
    id_completo = next(i for i in re.findall(r'data-id="([^"]+)"', completo) if i.startswith("R:t"))
    assert "F-2" in cliente.get(f"/e/prueba/2025/facturacion-terceros/f/{id_completo}").text
    assert cliente.get("/e/prueba/2025/facturacion-terceros/f/R:t999||").status_code == 404
