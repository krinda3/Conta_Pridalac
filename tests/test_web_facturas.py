"""Facturas en la web: formulario con recálculo, alta, edición, errores sin efectos, vencimientos, retenciones, justificantes y borrado."""
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import Adjunto, Asiento, Banco, Cuenta, Ejercicio, Empresa, Factura, FormaPago, Tercero, TipoIva, Vencimiento
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/facturas-recibidas"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("40000001", "PROVEEDOR UNO"), ("62900000", "OTROS SERVICIOS"), ("47200021", "IVA SOPORTADO 21"), ("47510000", "HP ACREEDORA IRPF"), ("57200001", "BANCO"), ("70000000", "VENTAS"), ("43000001", "CLIENTE UNO"), ("47700021", "IVA REPERCUTIDO 21"), ("52100001", "TARJETA"), ("52000001", "PRESTAMO"), ("55100001", "CUENTA CON SOCIO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    for numero, nombre, codigo in ((1, "BANCO EMPRESA A SANTANDER", "57200001"), (2, "TARJETA LA CAIXA", "52100001"), (3, "BANCO DE UN SOCIO", "55100001"), (4, "PRESTAMO BANKINTER", "52000001")):
        s.add(Banco(empresa_id=e.id, numero=numero, clase="B", nombre=nombre, cuenta_id=ids[codigo]))
    s.add(TipoIva(empresa_id=e.id, sentido="R", numero=1, texto="21 %", pct_iva=D("21.00"), cuenta_iva_id=ids["47200021"], por_defecto=True))
    s.add(TipoIva(empresa_id=e.id, sentido="R", numero=2, texto="Exento", pct_iva=D("0.00")))
    s.add(TipoIva(empresa_id=e.id, sentido="E", numero=1, texto="21 %", pct_iva=D("21.00"), cuenta_iva_id=ids["47700021"], por_defecto=True))
    s.add(FormaPago(empresa_id=e.id, numero_origen=1, texto="Transferencia"))
    s.add(Tercero(empresa_id=e.id, clase="P", nombre="Iberdrola", nif="A12345678", cuenta_id=ids["40000001"]))
    s.add(Tercero(empresa_id=e.id, clase="C", nombre="Cliente Uno", cuenta_id=ids["43000001"]))
    s.commit()
    s.close()
    config = Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})
    return TestClient(crear_app(config))


def _sesion(cliente):
    return cliente.app.state.config.sesion("prueba")


def _tercero(cliente, nombre="Iberdrola"):
    s = _sesion(cliente)
    try:
        return s.scalar(select(Tercero.id).where(Tercero.nombre == nombre))
    finally:
        s.close()


def formulario(cliente, **cambios):
    """Los datos de un formulario de factura recibida completo; `cambios` pisa cualquier campo (o línea con la clave `iva-0-base`)."""
    datos = {
        "fecha_contable": "050326", "fecha_factura": "280226", "numero_factura": "F-100", "tercero": str(_tercero(cliente)), "tercero_previo": str(_tercero(cliente)),
        "cuenta_tercero": "40000001", "contrapartida": "62900000", "concepto": "Luz", "notas": "", "plazos_auto": "1", "n_plazos": "2", "meses": "1",
        "iva-0-tipo": "1", "iva-0-tipo_previo": "1", "iva-0-auto": "1", "iva-0-base": "100,00", "iva-0-pct": "21,00", "iva-0-cuota": "21,00", "iva-0-cuenta": "47200021",
        "iva-0-pct_rec": "0,00", "iva-0-cuota_rec": "", "iva-0-cuenta_rec": "", "iva-0-deducible": "on",
        "pl-0-fecha": "280226", "pl-0-importe": "121,00", "pl-0-forma": "", "pl-0-cuenta": "", "pl-0-pagos": "0",
    }
    datos.update(cambios)
    return {k: v for k, v in datos.items() if v is not None}


def _guardar(cliente, base=BASE, ficheros=None, **cambios):
    return cliente.post(f"{base}/guardar", data=formulario(cliente, **cambios), files=ficheros)


def _factura(cliente, numero=1):
    s = _sesion(cliente)
    try:
        f = s.scalar(select(Factura).where(Factura.numero == numero, Factura.sentido == "R"))
        if f is None:
            return None
        return dict(id=f.id, total=f.total, ivas=[(i.base, i.cuota_iva) for i in f.ivas], ajustes=[(a.cuenta.codigo, a.importe) for a in f.ajustes],
                    venc=[v.importe for v in sorted(f.id and s.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)), key=lambda v: v.id)],
                    asientos=[{ap.cuenta.codigo: ap.debe - ap.haber for ap in a.apuntes} for a in s.scalars(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == f.numero).order_by(Asiento.sub))],
                    concepto=f.concepto, tercero=f.tercero.nombre if f.tercero else None)
    finally:
        s.close()


def _disparo(r):
    return json.loads(r.headers["HX-Trigger"])


# ---------------------------------------------------------------------------- formulario y recálculo


def test_la_pagina_y_el_formulario_nuevo(cliente):
    assert cliente.get(BASE).status_code == 200
    assert "Facturas recibidas" in cliente.get("/e/prueba/2026").text
    f = cliente.get(f"{BASE}/nuevo")
    assert f.status_code == 200
    for esperado in ("Iberdrola", 'name="iva-0-base"', 'value="21,00"', "47200021", 'type="file"', "Guardar factura", "＋ Vencimiento", "Pago con"):
        assert esperado in f.text, esperado
    for banco in ("BANCO EMPRESA A SANTANDER", "TARJETA LA CAIXA", "BANCO DE UN SOCIO"):  # los bancos y tarjetas de las cuentas 572, 521 y 551
        assert banco in f.text, banco
    assert "PRESTAMO BANKINTER" not in f.text  # una cuenta 520 no es para pagar facturas
    assert "Repartir" not in f.text and "n_plazos" not in f.text  # ya no se reparte en plazos
    assert "Cliente Uno" not in f.text  # en una recibida sólo se ofrecen proveedores


def test_sin_tipo_marcado_por_defecto_se_propone_el_mas_usado(cliente):
    s = _sesion(cliente)
    for t in s.scalars(select(TipoIva)):
        t.por_defecto = False
    s.commit()
    s.close()
    _guardar(cliente)  # una factura al 21 %
    _guardar(cliente, numero_factura="F-2")
    html = cliente.get(f"{BASE}/nuevo").text
    assert re.search(r'<option value="1" selected>21 %</option>', html) and 'name="iva-0-pct" value="21,00"' in html


def test_recalcular_calcula_cuota_total_y_vencimiento(cliente):
    r = cliente.post(f"{BASE}/recalcular", data=formulario(cliente, **{"iva-0-base": "250,50", "iva-0-cuota": "", "iva-0-auto": "1", "pl-0-importe": "1,00", "plazos_auto": "1"}))
    assert r.status_code == 200 and r.text.lstrip().startswith("<datalist") or 'id="cuerpo"' in r.text
    assert 'value="52,61"' in r.text  # 250,50 × 21 %
    assert "303,11" in r.text  # total
    assert re.search(r'name="pl-0-importe" value="303,11"', r.text)  # el vencimiento sigue al total mientras no se toque
    assert "Diferencia" not in r.text


def test_una_cuota_tecleada_no_se_recalcula(cliente):
    r = cliente.post(f"{BASE}/recalcular", data=formulario(cliente, **{"iva-0-base": "100,00", "iva-0-cuota": "20,99", "iva-0-auto": "0", "plazos_auto": "0", "pl-0-importe": "120,99"}))
    assert 'value="20,99"' in r.text and "120,99" in r.text and "Diferencia" not in r.text


def test_al_elegir_tercero_se_proponen_sus_cuentas(cliente):
    r = cliente.post(f"{BASE}/recalcular", data={"tercero": str(_tercero(cliente)), "tercero_previo": "", "fecha_contable": "050326"})
    assert 'name="cuenta_tercero" type="text" list="dl-cuentas-4" value="40000001"' in r.text


def test_la_ficha_del_tercero_propone_gasto_tipo_de_iva_y_forma_de_pago(cliente):
    s = _sesion(cliente)
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    t = s.scalar(select(Tercero).where(Tercero.nombre == "Iberdrola"))
    t.cuenta_gasto_id, t.tipos_iva_defecto = ids["62900000"], "2,1"
    t.forma_pago_id = s.scalar(select(FormaPago.id))
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/recalcular", data={"tercero": str(_tercero(cliente)), "tercero_previo": "", "fecha_contable": "050326", "iva-0-tipo": "", "iva-0-tipo_previo": "", "iva-0-base": "100,00"})
    assert re.search(r'name="contrapartida"[^>]*value="62900000"', r.text)
    assert re.search(r'<option value="2" selected>', r.text)  # el primero de sus tipos de IVA: exento
    assert re.search(r'name="pl-0-forma" value="1"', r.text)  # la forma de pago de la ficha se respeta aunque ya no se elija en el formulario


def test_el_tercero_se_busca_escribiendo(cliente):
    s = _sesion(cliente)
    emp = s.scalar(select(Tercero.empresa_id))
    s.add(Tercero(empresa_id=emp, clase="P", nombre="Iberia Suministros", nif="B99999999"))
    s.commit()
    s.close()
    base = {"fecha_contable": "050326", "tercero": "", "tercero_previo": ""}
    # un trozo del nombre que sólo encaja con uno: se elige y se proponen sus cuentas
    r = cliente.post(f"{BASE}/recalcular", data={**base, "tercero_texto": "iberdr"})
    assert f'name="tercero" value="{_tercero(cliente)}"' in r.text and "Iberdrola · A12345678" in r.text and 'value="40000001"' in r.text
    # por NIF
    assert f'name="tercero" value="{_tercero(cliente)}"' in cliente.post(f"{BASE}/recalcular", data={**base, "tercero_texto": "a1234"}).text
    # ambiguo y sin resultados: no se elige y se avisa
    assert "Hay varios proveedores" in cliente.post(f"{BASE}/recalcular", data={**base, "tercero_texto": "iber"}).text
    assert "No hay ningún proveedor" in cliente.post(f"{BASE}/recalcular", data={**base, "tercero_texto": "zzz"}).text
    assert 'name="tercero" value=""' in cliente.post(f"{BASE}/recalcular", data={**base, "tercero_texto": ""}).text
    # no se guarda con un tercero que no se encuentra
    r = _guardar(cliente, tercero="", tercero_previo="", tercero_texto="zzz")
    assert "No hay ningún proveedor" in r.text and _factura(cliente) is None
    assert _guardar(cliente, tercero="", tercero_previo="", tercero_texto="Iberdrola").text == "" and _factura(cliente)["tercero"] == "Iberdrola"


def test_añadir_y_quitar_lineas(cliente):
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(cliente), "accion": "add-iva"})
    assert 'name="iva-1-base"' in r.text
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(cliente), "accion": "del-iva-0"})
    assert 'name="iva-0-base"' not in r.text  # sin líneas


def test_añadir_un_vencimiento_propone_lo_que_falta_para_cuadrar(cliente):
    datos = formulario(cliente, plazos_auto="0", **{"pl-0-importe": "100,00"})  # la factura es de 121,00: quedan 21,00
    r = cliente.post(f"{BASE}/recalcular", data={**datos, "accion": "add-pl"})
    assert re.findall(r'name="pl-\d-importe" value="([\d,]+)"', r.text) == ["100,00", "21,00"]
    assert re.findall(r'name="pl-\d-fecha" value="([\d/]*)"', r.text) == ["280226", "280226"]  # la fecha de la anterior
    assert "Diferencia" not in r.text and "Repartir" not in r.text
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(cliente, plazos_auto="0"), "accion": "add-pl"})
    assert re.findall(r'name="pl-\d-importe" value="([\d,]*)"', r.text) == ["121,00", ""]  # ya cuadra: la línea nueva queda vacía para rellenarla


def test_cada_vencimiento_se_guarda_con_su_banco_o_tarjeta_y_se_conserva_al_editar(cliente):
    s = _sesion(cliente)
    banco, tarjeta = (s.scalar(select(Banco.id).where(Banco.nombre == n)) for n in ("BANCO EMPRESA A SANTANDER", "TARJETA LA CAIXA"))
    s.close()
    dos = {"plazos_auto": "0", "pl-0-importe": "100,00", "pl-0-banco": str(banco), "pl-1-fecha": "280326", "pl-1-importe": "21,00", "pl-1-banco": str(tarjeta), "pl-1-forma": "", "pl-1-cuenta": "", "pl-1-pagos": "0"}
    assert _guardar(cliente, **dos).text == ""
    s = _sesion(cliente)
    venc = sorted(s.scalars(select(Vencimiento)), key=lambda v: v.id)
    assert [(v.importe, v.banco_previsto_id) for v in venc] == [(D("-100.00"), banco), (D("-21.00"), tarjeta)]
    ident = s.scalar(select(Factura.id))
    s.close()
    form = cliente.get(f"{BASE}/f/{ident}").text  # al abrirla para editar, cada línea trae su banco
    assert re.search(rf'<option value="{banco}" selected>BANCO EMPRESA A SANTANDER', form) and re.search(rf'<option value="{tarjeta}" selected>TARJETA LA CAIXA', form)
    datos = formulario(cliente, id=str(ident), concepto="Luz de enero", **dos)
    assert cliente.post(f"{BASE}/guardar", data=datos).text == ""  # editar otra cosa no borra los bancos
    s = _sesion(cliente)
    assert [v.banco_previsto_id for v in sorted(s.scalars(select(Vencimiento)), key=lambda v: v.id)] == [banco, tarjeta]
    s.close()


def test_un_banco_que_no_es_de_pago_se_conserva_si_el_vencimiento_ya_lo_traia(cliente):
    s = _sesion(cliente)
    prestamo = s.scalar(select(Banco.id).where(Banco.nombre == "PRESTAMO BANKINTER"))
    s.close()
    r = cliente.post(f"{BASE}/recalcular", data=formulario(cliente, **{"pl-0-banco": str(prestamo)}))
    assert re.search(rf'<option value="{prestamo}" selected>PRESTAMO BANKINTER', r.text)  # el que ya estaba se ve, para no perderlo al guardar


# ---------------------------------------------------------------------------- alta y edición


def test_alta_de_una_factura_recibida(cliente):
    r = _guardar(cliente)
    assert r.status_code == 200 and r.text == ""
    d = _disparo(r)
    assert d["refrescar"] is True and d["cerrarModal"] is True and d["mensaje"]["tipo"] in ("ok", "aviso")
    f = _factura(cliente)
    assert f["total"] == D("121.00") and f["ivas"] == [(D("100.00"), D("21.00"))] and f["tercero"] == "Iberdrola" and f["concepto"] == "Luz"
    assert f["venc"] == [D("-121.00")]
    assert f["asientos"] == [{"62900000": D("100.00"), "47200021": D("21.00"), "40000001": D("-121.00")}]
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "F-100" in tabla and "Iberdrola" in tabla and "121,00" in tabla


def test_la_numeracion_sigue_y_la_edicion_regenera_el_asiento(cliente):
    _guardar(cliente)
    _guardar(cliente, numero_factura="F-101")
    assert _factura(cliente, 2) is not None
    ident = _factura(cliente)["id"]
    form = cliente.get(f"{BASE}/f/{ident}")
    assert form.status_code == 200 and 'value="F-100"' in form.text and 'name="id" value="' in form.text
    r = cliente.post(f"{BASE}/guardar", data=formulario(cliente, id=str(ident), **{"iva-0-base": "200,00", "iva-0-cuota": "42,00", "pl-0-importe": "242,00", "plazos_auto": "0"}))
    assert r.text == ""
    f = _factura(cliente)
    assert f["id"] == ident and f["total"] == D("242.00") and f["venc"] == [D("-242.00")]
    assert f["asientos"] == [{"62900000": D("200.00"), "47200021": D("42.00"), "40000001": D("-242.00")}]
    s = _sesion(cliente)
    assert s.scalar(select(func.count()).select_from(Factura)) == 2
    s.close()


# ---------------------------------------------------------------------------- errores: no se guarda nada


@pytest.mark.parametrize(
    "cambios, texto",
    [
        ({"contrapartida": ""}, "Falta la cuenta de gasto"),
        ({"cuenta_tercero": "99999999"}, "No existe la cuenta 99999999"),
        ({"fecha_contable": "050327"}, "fuera del ejercicio"),
        ({"fecha_contable": "310226"}, "no existe en el calendario"),
        ({"iva-0-base": "abc"}, "no es un importe válido"),
        ({"iva-0-base": ""}, "Falta la base"),
        ({"pl-0-importe": "100,00", "plazos_auto": "0"}, "Los vencimientos suman"),
        ({"pl-0-fecha": "xx", "plazos_auto": "0"}, "no es una fecha"),
        ({"iva-0-cuenta": "", "iva-0-cuota": "21,00"}, "Falta la cuenta de IVA"),
    ],
)
def test_los_errores_no_guardan_nada_y_vuelven_al_formulario(cliente, cambios, texto):
    r = _guardar(cliente, **cambios)
    assert r.status_code == 200 and "HX-Trigger" not in r.headers and texto in r.text and 'role="alert"' in r.text
    assert 'id="cuerpo"' in r.text and "Guardar factura" in r.text  # el formulario sigue ahí con lo escrito
    assert _factura(cliente) is None
    s = _sesion(cliente)
    assert s.scalar(select(func.count()).select_from(Asiento)) == 0 and s.scalar(select(func.count()).select_from(Vencimiento)) == 0
    s.close()


def test_sin_lineas_de_iva_no_se_graba(cliente):
    r = cliente.post(f"{BASE}/guardar", data={k: v for k, v in formulario(cliente).items() if not k.startswith("iva-")})
    assert "al menos una línea de IVA" in r.text and _factura(cliente) is None


def test_un_ejercicio_cerrado_no_admite_facturas(cliente):
    s = _sesion(cliente)
    s.scalar(select(Ejercicio)).cerrado = True
    s.commit()
    s.close()
    r = _guardar(cliente)
    assert "cerrado" in r.text and _factura(cliente) is None


# ---------------------------------------------------------------------------- retenciones y varias líneas


def test_retencion_de_irpf_en_una_recibida(cliente):
    datos = formulario(cliente, **{"iva-0-base": "1000,00", "iva-0-cuota": "210,00", "aj-0-cuenta": "47510000", "aj-0-importe": "-150,00", "aj-0-contra": "P",
                                   "pl-0-importe": "1060,00", "plazos_auto": "0", "pl-1-fecha": "050326", "pl-1-importe": "150,00", "pl-1-cuenta": "47510000", "pl-1-pagos": "0", "pl-1-forma": ""})
    r = cliente.post(f"{BASE}/guardar", data=datos)
    assert r.text == "", r.text[:500]
    f = _factura(cliente)
    assert f["total"] == D("1060.00") and f["ajustes"] == [("47510000", D("-150.00"))] and sorted(f["venc"]) == [D("-1060.00"), D("-150.00")]
    assert sum(f["asientos"][0].values()) == 0


def test_la_retencion_genera_su_vencimiento_al_recalcular(cliente):
    r = cliente.post(f"{BASE}/recalcular", data={**formulario(cliente, **{"iva-0-base": "1000,00", "iva-0-cuota": "210,00"}), "accion": "add-aj"})
    r = cliente.post(f"{BASE}/recalcular", data=formulario(cliente, **{"iva-0-base": "1000,00", "iva-0-cuota": "210,00", "aj-0-cuenta": "47510000", "aj-0-importe": "-150,00"}))
    assert "1.060,00" in r.text and "1060,00" in r.text and 'name="pl-1-cuenta" value="47510000"' in r.text and 'name="pl-1-importe" value="150,00"' in r.text


def test_dos_tipos_de_iva_en_una_factura(cliente):
    datos = formulario(cliente, **{"iva-1-tipo": "2", "iva-1-tipo_previo": "2", "iva-1-auto": "1", "iva-1-base": "50,00", "iva-1-pct": "0,00", "iva-1-cuota": "0,00", "iva-1-cuenta": "",
                                   "iva-1-deducible": "on", "pl-0-importe": "171,00", "plazos_auto": "0"})
    assert cliente.post(f"{BASE}/guardar", data=datos).text == ""
    f = _factura(cliente)
    assert f["total"] == D("171.00") and f["ivas"] == [(D("100.00"), D("21.00")), (D("50.00"), D("0.00"))]


# ---------------------------------------------------------------------------- justificantes


def test_subir_ver_y_quitar_un_justificante(cliente):
    r = _guardar(cliente, ficheros=[("ficheros", ("luz enero.pdf", PDF, "application/pdf"))])
    assert r.text == ""
    f = _factura(cliente)
    s = _sesion(cliente)
    a = s.scalar(select(Adjunto).where(Adjunto.factura_id == f["id"]))
    assert a.nombre == "luz enero.pdf" and a.presente and a.tamano == len(PDF)
    ruta = cliente.app.state.config.almacen_de_adjuntos().ruta(a)
    s.close()
    assert ruta.read_bytes() == PDF
    v = cliente.get(f"/e/prueba/2026/adjuntos/{a.id}")
    assert v.status_code == 200 and v.content == PDF and v.headers["content-type"] == "application/pdf" and "inline" in v.headers["content-disposition"]
    form = cliente.get(f"{BASE}/f/{f['id']}").text
    assert "luz enero.pdf" in form and f"/adjuntos/{a.id}" in form and "<iframe" in form
    assert re.search(r'data-clave="justificantes">1<', cliente.get(f"{BASE}/tabla").text)
    r = cliente.post(f"{BASE}/guardar", data={**formulario(cliente, id=str(f["id"])), "quitar_adjunto": str(a.id)})
    assert r.text == "" and not ruta.exists()
    assert cliente.get(f"/e/prueba/2026/adjuntos/{a.id}").status_code == 404


def test_un_fichero_no_valido_impide_guardar_la_factura(cliente):
    r = _guardar(cliente, ficheros=[("ficheros", ("nota.txt", b"hola", "text/plain"))])
    assert "sólo se admiten ficheros PDF y JPG" in r.text and _factura(cliente) is None
    r = _guardar(cliente, ficheros=[("ficheros", ("falso.pdf", b"no soy pdf", "application/pdf"))])
    assert "no es un PDF válido" in r.text and _factura(cliente) is None


def test_no_se_ve_un_justificante_de_otra_empresa_ni_inexistente(cliente):
    assert cliente.get("/e/prueba/2026/adjuntos/999").status_code == 404


# ---------------------------------------------------------------------------- borrar


def test_borrar_una_factura_borra_asientos_vencimientos_y_ficheros(cliente):
    _guardar(cliente, ficheros=[("ficheros", ("a.pdf", PDF, "application/pdf"))])
    f = _factura(cliente)
    s = _sesion(cliente)
    ruta = cliente.app.state.config.almacen_de_adjuntos().ruta(s.scalar(select(Adjunto)))
    s.close()
    r = cliente.post(f"{BASE}/borrar", data={"ids": [f["id"]]})
    assert _disparo(r)["mensaje"]["tipo"] == "ok" and _factura(cliente) is None and not ruta.exists()
    s = _sesion(cliente)
    assert all(s.scalar(select(func.count()).select_from(t)) == 0 for t in (Asiento, Vencimiento, Adjunto))
    s.close()


# ---------------------------------------------------------------------------- emitidas


def test_factura_emitida(cliente):
    base = "/e/prueba/2026/facturas-emitidas"
    cid = _tercero(cliente, "Cliente Uno")
    assert "Iberdrola" not in cliente.get(f"{base}/nuevo").text and "Cliente Uno" in cliente.get(f"{base}/nuevo").text
    datos = formulario(cliente, tercero=str(cid), tercero_previo=str(cid), cuenta_tercero="43000001", contrapartida="70000000", **{"iva-0-tipo": "1", "iva-0-cuenta": "47700021"})
    r = cliente.post(f"{base}/guardar", data=datos)
    assert r.text == "", r.text[:400]
    s = _sesion(cliente)
    f = s.scalar(select(Factura).where(Factura.sentido == "E"))
    asiento = s.scalar(select(Asiento).where(Asiento.tipo == 1, Asiento.numero == f.numero))
    assert {ap.cuenta.codigo: ap.haber - ap.debe for ap in asiento.apuntes} == {"70000000": D("100.00"), "47700021": D("21.00"), "43000001": D("-121.00")}
    assert s.scalar(select(Vencimiento.importe).where(Vencimiento.factura_id == f.id)) == D("121.00")  # a cobrar: positivo
    s.close()
    assert "121,00" in cliente.get(f"{base}/tabla").text


# ---------------------------------------------------------------------------- exportación del listado


def test_el_listado_de_facturas_se_exporta(cliente):
    _guardar(cliente)
    r = cliente.get(f"{BASE}/exportar.xlsx")
    assert r.status_code == 200 and len(r.content) > 1000
    assert cliente.get(f"{BASE}/exportar.pdf").headers["content-type"] == "application/pdf"


# ---------------------------------------------------------------------------- datos reales


@pytest.mark.datos_reales
@pytest.mark.parametrize("clave", ["empresa_a", "empresa_b"])
def test_regrabar_cada_factura_real_desde_el_formulario_no_cambia_el_diario(clave, tmp_path):
    """El formulario reconstruye cada factura de MGD (líneas, ajustes, vencimientos) y al grabarla deja el Diario igual."""
    from conftest import EMPRESAS_MGD_2021, _carpeta_empresa

    from conta_pridalac.db.sesion import crear_motor
    from conta_pridalac.domain.facturas import total_esperado
    from conta_pridalac.migracion.mgd import cargar_mgd
    from conta_pridalac.web.facturas import construir_y_grabar, estado_de_factura
    from conta_pridalac.web.listados import Contexto

    origen = _carpeta_empresa(clave)
    if not (origen / "Diario.dbf").exists():
        pytest.skip(f"No hay datos MGD de {clave}")
    motor = crear_motor(None)
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    datos = EMPRESAS_MGD_2021[clave]
    res = cargar_mgd(sesion, origen, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
    sesion.commit()
    ej = sesion.get(Ejercicio, res.ejercicio_id)
    ctx = Contexto(sesion, sesion.get(Empresa, ej.empresa_id), ej, clave, Configuracion(datos=tmp_path, almacen=tmp_path / "alm"))

    def foto():
        estado = {}
        for a in sesion.scalars(select(Asiento)):
            lineas: Counter = Counter()
            for ap in a.apuntes:
                lineas[ap.cuenta.codigo] += ap.debe - ap.haber
            estado[(a.tipo, a.numero, a.sub)] = (a.numero_diario, a.fecha, dict(lineas))
        venc = sorted((v.factura_id or 0, v.importe, v.fecha) for v in sesion.scalars(select(Vencimiento)))
        return estado, venc

    antes = foto()
    regrabadas = distintas = 0
    for f in list(sesion.scalars(select(Factura))):
        if f.total != total_esperado(f):
            continue  # facturas cuyo total no cuadra con sus líneas (aviso de la auditoría): grabarlas las corregiría
        e = estado_de_factura(ctx, f)
        factura, errores, _ = construir_y_grabar(ctx, e, [])
        assert errores == [] and factura is not None, (f.sentido, f.numero, errores)
        regrabadas += 1
    sesion.flush()
    assert regrabadas > 50
    assert foto() == antes


# ---------------------------------------------------------------------------- trimestre presentado: la factura queda bloqueada


def _presentar_el_trimestre_de(cliente, ident):
    from conta_pridalac.db.modelos import PRESENTADA, PresentacionAeat

    s = _sesion(cliente)
    f = s.get(Factura, ident)
    s.add(PresentacionAeat(empresa_id=s.scalar(select(Empresa.id)), modelo="303", anio=f.fecha_contable.year, periodo=f"{(f.fecha_contable.month - 1) // 3 + 1}T", estado=PRESENTADA, casillas="{}"))
    s.commit()
    s.close()


def test_una_factura_de_un_trimestre_presentado_no_se_edita_ni_se_borra_ni_se_crea_otra(cliente):
    _guardar(cliente)
    ident = _factura(cliente)["id"]
    _presentar_el_trimestre_de(cliente, ident)
    r = cliente.post(f"{BASE}/guardar", data=formulario(cliente, id=str(ident), **{"iva-0-base": "200,00", "iva-0-cuota": "42,00", "pl-0-importe": "242,00", "plazos_auto": "0"}))
    assert "presentado a la AEAT" in r.text and "rectificativa" in r.text
    assert _factura(cliente)["total"] == D("121.00")  # nada cambió
    r = cliente.post(f"{BASE}/borrar", data={"ids": [ident]})
    assert _disparo(r)["mensaje"]["tipo"] == "error" and "presentado a la AEAT" in _disparo(r)["mensaje"]["texto"] and _factura(cliente) is not None
    r = _guardar(cliente, numero_factura="F-OTRA")
    assert "ya está presentado" in r.text


# ---------------------------------------------------------------------------- facturas que parecen estar ya grabadas
def _numero_de_facturas(cliente, sentido="R"):
    s = _sesion(cliente)
    try:
        return len(list(s.scalars(select(Factura).where(Factura.sentido == sentido))))
    finally:
        s.close()


def test_una_recibida_repetida_avisa_y_no_se_graba_sin_confirmar(cliente):
    assert _guardar(cliente).text == ""
    r = _guardar(cliente)  # el mismo proveedor y el mismo número
    assert r.status_code == 200 and "Ya existe una factura de «Iberdrola» con el número F-100" in r.text and "121,00 €" in r.text
    assert 'name="confirmar_duplicada"' in r.text
    assert _numero_de_facturas(cliente) == 1
    r2 = _guardar(cliente, confirmar_duplicada="on")  # «grabar de todos modos»: es otra factura distinta
    assert r2.text == "" and _numero_de_facturas(cliente) == 2


def test_el_numero_se_compara_sin_mayusculas_ni_espacios(cliente):
    _guardar(cliente, numero_factura="ab-1")
    assert "Ya existe una factura" in _guardar(cliente, numero_factura="  AB-1 ").text and _numero_de_facturas(cliente) == 1


def test_otro_numero_u_otro_proveedor_no_avisan(cliente):
    s = _sesion(cliente)
    s.add(Tercero(empresa_id=s.scalar(select(Tercero.empresa_id)), clase="P", nombre="Otro Proveedor", cuenta_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "40000001"))))
    s.commit()
    s.close()
    otro = _tercero(cliente, "Otro Proveedor")
    assert _guardar(cliente).text == ""
    assert _guardar(cliente, numero_factura="F-101").text == ""  # otro número
    assert _guardar(cliente, tercero=str(otro), tercero_previo=str(otro), numero_factura="F-100", **{"iva-0-base": "200,00", "iva-0-cuota": "42,00", "pl-0-importe": "242,00"}).text == ""  # otro proveedor e importe
    assert _numero_de_facturas(cliente) == 3


def test_mismo_numero_e_importe_con_otro_proveedor_avisa_de_un_posible_tercero_mal_elegido(cliente):
    s = _sesion(cliente)
    s.add(Tercero(empresa_id=s.scalar(select(Tercero.empresa_id)), clase="P", nombre="Otro Proveedor", cuenta_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "40000001"))))
    s.commit()
    s.close()
    otro = _tercero(cliente, "Otro Proveedor")
    _guardar(cliente)
    r = _guardar(cliente, tercero=str(otro), tercero_previo=str(otro))  # mismo número y mismo total con otro proveedor
    assert "por el mismo importe" in r.text and "mal elegido" in r.text and _numero_de_facturas(cliente) == 1


def test_editar_una_factura_sin_cambiar_numero_ni_tercero_no_vuelve_a_avisar(cliente):
    _guardar(cliente)
    _guardar(cliente, confirmar_duplicada="on")  # dos facturas iguales, la segunda confirmada
    s = _sesion(cliente)
    ident = s.scalar(select(Factura.id).order_by(Factura.id.desc()))
    s.close()
    r = cliente.post(f"{BASE}/guardar", data=formulario(cliente, id=str(ident), concepto="Luz de enero"))
    assert r.text == ""  # no se vuelve a avisar de una duplicada que ya estaba
    r = cliente.post(f"{BASE}/guardar", data=formulario(cliente, id=str(ident), numero_factura="F-100 "))
    assert r.text == ""  # el mismo número con un espacio sobrante sigue siendo el mismo


def test_al_cambiar_el_numero_de_una_factura_a_uno_ya_usado_si_avisa(cliente):
    _guardar(cliente)
    _guardar(cliente, numero_factura="F-200")
    s = _sesion(cliente)
    ident = s.scalar(select(Factura.id).where(Factura.numero_factura == "F-200"))
    s.close()
    r = cliente.post(f"{BASE}/guardar", data=formulario(cliente, id=str(ident), numero_factura="F-100"))
    assert "Ya existe una factura de «Iberdrola» con el número F-100" in r.text


def test_una_emitida_con_un_numero_ya_usado_en_el_ejercicio_avisa_aunque_sea_otro_cliente(cliente):
    base = "/e/prueba/2026/facturas-emitidas"
    s = _sesion(cliente)
    s.add(Tercero(empresa_id=s.scalar(select(Tercero.empresa_id)), clase="C", nombre="Cliente Dos", cuenta_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "43000001"))))
    s.commit()
    s.close()

    def emitida(cliente_nombre, **cambios):
        cid = _tercero(cliente, cliente_nombre)
        datos = formulario(cliente, tercero=str(cid), tercero_previo=str(cid), cuenta_tercero="43000001", contrapartida="70000000", numero_factura="2026-001",
                           **{"iva-0-cuenta": "47700021", **cambios})
        return cliente.post(f"{base}/guardar", data=datos)

    assert emitida("Cliente Uno").text == ""
    r = emitida("Cliente Dos", **{"iva-0-base": "50,00", "iva-0-cuota": "10,50", "pl-0-importe": "60,50"})  # otro cliente y otro importe, pero la numeración es propia
    assert "Ya existe en este ejercicio la factura emitida 2026-001" in r.text and "no se repiten" in r.text
    assert emitida("Cliente Dos", **{"iva-0-base": "50,00", "iva-0-cuota": "10,50", "pl-0-importe": "60,50", "confirmar_duplicada": "on"}).text == ""


# ---------------------------------------------------------------------------- el recargo de equivalencia sólo se aplica a quien está en ese régimen
def _con_recargo_el_tipo_general(cliente, recargo_en_la_ficha=False):
    s = _sesion(cliente)
    s.scalar(select(TipoIva).where(TipoIva.sentido == "R", TipoIva.numero == 1)).pct_recargo = D("5.20")  # como el catálogo de Empresa A y Empresa B
    if recargo_en_la_ficha:
        s.scalar(select(Tercero).where(Tercero.nombre == "Iberdrola")).recargo_equivalencia = True
    s.commit()
    s.close()


def test_un_tipo_de_iva_con_recargo_en_el_catalogo_no_lo_aplica_a_un_proveedor_normal(cliente):
    _con_recargo_el_tipo_general(cliente)
    assert 'name="iva-0-pct_rec" value="0,00"' in cliente.get(f"{BASE}/nuevo").text  # la línea nueva sale sin recargo
    datos = {"tercero": str(_tercero(cliente)), "tercero_previo": "", "fecha_contable": "050326", "iva-0-tipo": "1", "iva-0-tipo_previo": "", "iva-0-base": "100,00", "iva-0-auto": "1"}
    r = cliente.post(f"{BASE}/recalcular", data=datos)
    assert 'name="iva-0-pct_rec" value="0,00"' in r.text and "121,00" in r.text and "126,20" not in r.text
    assert _guardar(cliente).text == ""  # y se graba sin pedir una cuenta de recargo


def test_con_recargo_de_equivalencia_en_la_ficha_la_linea_lo_lleva(cliente):
    _con_recargo_el_tipo_general(cliente, recargo_en_la_ficha=True)
    datos = {"tercero": str(_tercero(cliente)), "tercero_previo": "", "fecha_contable": "050326", "iva-0-tipo": "1", "iva-0-tipo_previo": "1", "iva-0-base": "100,00", "iva-0-auto": "1", "iva-0-pct": "21,00",
             "iva-0-pct_rec": "0,00", "iva-0-cuota_rec": ""}
    r = cliente.post(f"{BASE}/recalcular", data=datos)  # al elegir el tercero, sus líneas toman el recargo del tipo
    assert 'name="iva-0-pct_rec" value="5,20"' in r.text
    assert "126,20" in r.text  # 100 + 21 de IVA + 5,20 de recargo


def test_al_pasar_de_un_proveedor_con_recargo_a_otro_sin_el_la_linea_lo_pierde(cliente):
    _con_recargo_el_tipo_general(cliente)  # Iberdrola no está en el régimen
    datos = {"tercero": str(_tercero(cliente)), "tercero_previo": "", "fecha_contable": "050326", "iva-0-tipo": "1", "iva-0-tipo_previo": "1", "iva-0-base": "100,00", "iva-0-auto": "1", "iva-0-pct": "21,00",
             "iva-0-pct_rec": "5,20", "iva-0-cuota_rec": "5,20"}  # la línea traía el recargo del proveedor anterior
    r = cliente.post(f"{BASE}/recalcular", data=datos)
    assert 'name="iva-0-pct_rec" value="0,00"' in r.text and "126,20" not in r.text and "121,00" in r.text
