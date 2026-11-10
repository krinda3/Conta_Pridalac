"""Importación de facturas desde Excel por la web: formulario → vista previa → importación."""
import re
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Empresa, Factura, MovimientoBanco, Tercero, TipoIva
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/facturas-recibidas"
CABECERA = ["Nombre archivo", "Empresa", "CIF", "Fecha factura", "Num. factura", "Base imponible", "% IVA", "Monto IVA", "Monto total", "Ruta completa", "Fecha Contable",
            "% IVA 2", "Monto IVA 2", "% IVA 3", "Monto IVA 3", "Fecha Pago", "Concepto Pago", "Subcuenta de Pago", "Desc. Subcuenta"]


def excel(filas) -> bytes:
    libro = Workbook()
    libro.active.append(CABECERA)
    for f in filas:
        libro.active.append(f)
    sal = BytesIO()
    libro.save(sal)
    return sal.getvalue()


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    emp = Empresa(codigo=2, nombre="Empresa de Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=emp)
    s.add_all([emp, ej])
    s.flush()
    c = {k: Cuenta(empresa_id=emp.id, codigo=k, nombre=k) for k in ("41000001", "62800000", "62900000", "47200000", "55100002")}
    s.add_all(c.values())
    s.flush()
    s.add(TipoIva(empresa_id=emp.id, sentido="R", numero=1, texto="General", pct_iva=D("21.00"), cuenta_iva_id=c["47200000"].id, por_defecto=True))
    s.add(Tercero(empresa_id=emp.id, clase="P", nombre="PROVEEDOR UNO", nif="B13521992", cuenta_id=c["41000001"].id, cuenta_gasto_id=c["62800000"].id))
    s.add(Banco(empresa_id=emp.id, numero=1, clase="B", nombre="Banco Javier", cuenta_id=c["55100002"].id))
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _filas():
    return excel([
        ["", "PROVEEDOR UNO", "B-13521992", "21/07/2026", "A-1", 100, 21, 21, 121, "", "30/09/2026", None, None, None, None, "22/07/2026", "Pago A-1", "55100002", ""],
        ["", "NUEVO SA", "A99999999", "03/07/2026", "N-1", 50, 21, 10.5, 60.5, "", "30/09/2026", None, None, None, None, None, None, None, ""],
    ])


def test_el_listado_ofrece_importar_y_el_formulario_se_abre(cliente):
    assert "Importar Excel" in cliente.get(BASE).text
    assert "Importar Excel" not in cliente.get("/e/prueba/2026/movimientos").text
    f = cliente.get(f"{BASE}/importar")
    assert f.status_code == 200 and 'type="file"' in f.text and "Ver qué se importaría" in f.text
    assert cliente.get("/e/prueba/2026/movimientos/importar").status_code == 404


def test_vista_previa_e_importacion(cliente):
    vista = cliente.post(f"{BASE}/importar", files={"fichero": ("conciliacion.xlsx", _filas(), "application/vnd.ms-excel")})
    assert vista.status_code == 200 and "Importar desde «conciliacion.xlsx»" in vista.text and "Importar 2 facturas" in vista.text
    assert "Se creará el proveedor" in vista.text and 'name="gasto_A99999999"' in vista.text and "Banco Javier" in vista.text
    token = re.search(r'name="token" value="([^"]+)"', vista.text).group(1)
    # la vista previa no ha grabado nada
    s = cliente.app.state.config.sesion("prueba")
    assert s.scalar(select(Factura.id)) is None
    s.close()
    r = cliente.post(f"{BASE}/importar", data={"paso": "confirmar", "token": token, "gasto_A99999999": "62900000"})
    assert r.status_code == 200 and "Importación terminada" in r.text and "NUEVO SA (41000002)" in r.text
    s = cliente.app.state.config.sesion("prueba")
    facturas = s.scalars(select(Factura).order_by(Factura.numero)).all()
    assert [(f.numero_factura, f.total) for f in facturas] == [("N-1", D("60.50")), ("A-1", D("121.00"))]
    assert facturas[0].cuenta_contrapartida.codigo == "62900000" and len(s.scalars(select(MovimientoBanco)).all()) == 1
    s.close()
    # la vista previa se gasta: confirmar otra vez no repite nada; y un Excel igual sale todo duplicado
    assert "caducado" in cliente.post(f"{BASE}/importar", data={"paso": "confirmar", "token": token}).text
    otra = cliente.post(f"{BASE}/importar", files={"fichero": ("c.xlsx", _filas(), "application/vnd.ms-excel")})
    assert "Importar 0 facturas" in otra.text and otra.text.count("<strong>Ya existe</strong>") == 2 and "disabled" in otra.text


def test_errores_del_fichero(cliente):
    assert "Elija el fichero" in cliente.post(f"{BASE}/importar", data={}).text
    mal = cliente.post(f"{BASE}/importar", files={"fichero": ("x.xlsx", b"no es un excel", "application/vnd.ms-excel")})
    assert "No se puede abrir el Excel" in mal.text and 'type="file"' in mal.text
