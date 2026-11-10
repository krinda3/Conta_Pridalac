"""Modelo 303 en la web: listado de trimestres, ficha con controles, borrador, fichero y descarga."""
import json
import os
import re
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from conta_pridalac.db.modelos import PRESENTADA, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, Parametro, PresentacionAeat, Tercero, Vencimiento
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.tesoreria import crear_banco, pagar_vencimiento
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

D = Decimal
BASE = "/e/prueba/2026/modelo-303"


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    """Los tests no dependen del día en que se ejecutan: «hoy» es anterior a cualquier plazo de 2026."""
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def cliente(tmp_path):
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=11, nombre="Empresa de Prueba", nif="B12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    s.add_all([e, ej])
    s.flush()
    for codigo, nombre in (("47200021", "IVA SOPORTADO 21"), ("47700021", "IVA REPERCUTIDO 21"), ("40000001", "PROVEEDOR"), ("43000001", "CLIENTE"), ("62900000", "GASTOS"), ("70000000", "VENTAS"), ("47000000", "HP DEUDORA IVA"), ("47500000", "HP ACREEDORA IVA"), ("57200001", "BANCO")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.add_all([Parametro(empresa_id=e.id, clave="IVA_DEBE", valor="47000000"), Parametro(empresa_id=e.id, clave="IVA_HABER", valor="47500000")])
    s.flush()
    ids = {c.codigo: c.id for c in s.scalars(select(Cuenta))}
    s.add_all([Tercero(empresa_id=e.id, clase="P", nombre="Proveedor", cuenta_id=ids["40000001"]), Tercero(empresa_id=e.id, clase="C", nombre="Cliente", cuenta_id=ids["43000001"])])
    s.flush()
    for sentido, numero, fecha, base in (("R", 1, date(2026, 2, 10), D("1000")), ("E", 1, date(2026, 2, 20), D("2000"))):
        recibida = sentido == "R"
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"{sentido}{numero}", total=base * D("1.21"),
                    tercero_id=s.scalar(select(Tercero.id).where(Tercero.clase == ("P" if recibida else "C"))), cuenta_tercero_id=ids["40000001" if recibida else "43000001"],
                    cuenta_contrapartida_id=ids["62900000" if recibida else "70000000"],
                    ivas=[FacturaIva(base=base, pct_iva=D("21.00"), cuota_iva=base * D("0.21"), cuenta_iva_id=ids["47200021" if recibida else "47700021"])])
        grabar_factura(s, ej, f)
    s.commit()
    s.close()
    return TestClient(crear_app(Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={"prueba": motor})))


def _presentaciones(cliente):
    s = cliente.app.state.config.sesion("prueba")
    try:
        return list(s.scalars(select(PresentacionAeat).order_by(PresentacionAeat.id)))
    finally:
        s.close()


def _boton(html, valor):
    return re.findall(r'<button[^>]*value="' + valor + r'"[^>]*>', html)[0]


def test_listado_de_trimestres_y_enlace_en_el_panel(cliente):
    assert "/modelo-303" in cliente.get("/e/prueba/2026").text
    assert cliente.get(BASE).status_code == 200
    html = cliente.get(f"{BASE}/tabla").text
    assert "1T 2026" in html and "4T 2026" in html and "4 filas" in html and html.count("Sin presentar") == 4


def test_ficha_con_casillas_controles_y_desglose(cliente):
    html = cliente.get(f"{BASE}/f/1").text
    assert "Modelo 303 · 1T 2026" in html and "Sin presentar" in html
    assert "420,00" in html and "210,00" in html  # devengado 2000 × 21 % y deducible 1000 × 21 %
    assert "facturas recibidas del periodo no tienen justificante" in html and "Desglose por factura" in html
    assert "disabled" not in _boton(html, "generar")


@pytest.mark.parametrize("id", ["0", "5", "x"])
def test_periodos_no_validos(cliente, id):
    assert cliente.get(f"{BASE}/f/{id}").status_code == 404


def test_guardar_borrador_y_generar_el_fichero_y_descargarlo(cliente):
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"})
    assert "Borrador guardado" in r.headers["HX-Trigger"]
    p = _presentaciones(cliente)
    assert len(p) == 1 and p[0].estado == "borrador" and p[0].resultado == D("210.00")
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"})
    assert "Fichero generado: EMPRESA_DE_PRUEBA_AEAT_303_2026_1T.303" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]
    p = _presentaciones(cliente)
    assert len(p) == 1 and p[0].estado == "generada" and p[0].diseno_version == "DR303e26v101"
    assert f"/modelo-303/{p[0].id}/fichero" in r.text and "Historial" in r.text
    d = cliente.get(f"{BASE}/{p[0].id}/fichero")
    assert d.status_code == 200 and len(d.content) == 3767 and d.content.startswith(b"<T303020261T0000>")
    assert "attachment" in d.headers["content-disposition"]
    assert "Fichero generado" in cliente.get(f"{BASE}/tabla").text
    assert cliente.get(f"{BASE}/99999/fichero").status_code == 404


def test_con_errores_se_guarda_el_borrador_pero_no_se_genera(cliente):
    s = cliente.app.state.config.sesion("prueba")
    s.scalars(select(Empresa)).first().iban = None
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"})
    assert "IBAN" in r.text and 'role="alert"' in r.text
    p = _presentaciones(cliente)
    assert len(p) == 1 and p[0].estado == "borrador" and not p[0].fichero_ruta  # el borrador se conserva
    assert "disabled" in _boton(cliente.get(f"{BASE}/f/1").text, "generar")


def test_un_trimestre_presentado_solo_admite_rectificativa(cliente):
    s = cliente.app.state.config.sesion("prueba")
    s.add(PresentacionAeat(empresa_id=s.scalars(select(Empresa)).first().id, modelo="303", anio=2026, periodo="1T", estado=PRESENTADA, casillas="{}", resultado=D("210.00")))
    s.commit()
    s.close()
    assert "Presentado" in cliente.get(f"{BASE}/tabla").text
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "ya está presentado" in ficha and '<option value="rectificativa" selected>' in ficha
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal"})
    assert "ya está presentado" in r.text and len(_presentaciones(cliente)) == 1


def test_importe_de_prorrata_no_valido(cliente):
    r = cliente.post(f"{BASE}/guardar", data={"id": "4", "accion": "ver", "prorrata": "abc", "tipo_presentacion": "normal"})
    assert "no es un importe válido" in r.text


def test_la_ficha_ensena_plazos_y_se_guarda_el_pago_con_nrc(cliente):
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "15/04/2026" in ficha and "20/04/2026" in ficha and "Todavía no hay liquidación" in ficha
    nrc = "3036479211552SFK8Y016Y"
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "nrc", "nrc": nrc.lower()})
    assert "Fichero generado" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]
    p = _presentaciones(cliente)[0]
    assert p.nrc == nrc and p.tipo_declaracion == "I" and not p.domiciliar
    assert nrc in cliente.get(f"{BASE}/f/1").text


def test_el_pago_enlaza_con_el_vencimiento_y_el_movimiento_de_banco(cliente):
    from conta_pridalac.servicios.iva import liquidar_iva

    s = cliente.app.state.config.sesion("prueba")
    try:
        ej = s.scalar(select(Ejercicio))
        liq, _ = liquidar_iva(s, ej, date(2026, 3, 31))
        assert liq.a_pagar > 0
        s.commit()
    finally:
        s.close()
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "a pagar 210,00" in ficha and "pendiente 210,00" in ficha
    s = cliente.app.state.config.sesion("prueba")
    try:
        ej = s.scalar(select(Ejercicio))
        banco = crear_banco(s, ej.empresa_id, "Banco", "57200001")
        pagar_vencimiento(s, ej, s.scalar(select(Vencimiento).where(Vencimiento.origen_tipo == "X")), banco, date(2026, 4, 15))
        s.commit()
    finally:
        s.close()
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "<strong>pagado</strong>" in ficha and "15/04/2026" in ficha and "210,00" in ficha


def test_con_nrc_la_ficha_da_los_datos_para_pagar_y_avisa_si_cambia_el_importe(cliente):
    ficha = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "ver", "tipo_presentacion": "normal", "forma_pago": "nrc"}).text
    assert "Datos para obtener el NRC" in ficha and "B12345678" in ficha and "210,00 €" in ficha
    nrc = "3036479211552SFK8Y016Y"
    cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal", "forma_pago": "nrc", "nrc": nrc})
    s = cliente.app.state.config.sesion("prueba")
    try:
        ej = s.scalar(select(Ejercicio))
        f = Factura(ejercicio_id=ej.id, sentido="E", numero=2, fecha_contable=date(2026, 3, 1), fecha_factura=date(2026, 3, 1), numero_factura="E2", total=D("121"),
                    tercero_id=s.scalar(select(Tercero.id).where(Tercero.clase == "C")), cuenta_tercero_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "43000001")),
                    cuenta_contrapartida_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "70000000")),
                    ivas=[FacturaIva(base=D("100"), pct_iva=D("21.00"), cuota_iva=D("21.00"), cuenta_iva_id=s.scalar(select(Cuenta.id).where(Cuenta.codigo == "47700021")))])
        grabar_factura(s, ej, f)
        s.commit()
    finally:
        s.close()
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "El NRC se anotó cuando el resultado era 210.00 y ahora es 231.00" in ficha
    assert "disabled" in _boton(ficha, "generar")


# ---------------------------------------------------------------------------------------------- plan B: presentar en la sede y registrar el justificante

PDF = b"%PDF-1.4 justificante de prueba"
REGISTRO = {"id": "1", "accion": "registrar", "justificante": "3037084443540", "csv": "abcd1234efgh5678", "fecha_presentacion": "2026-04-14", "hora_presentacion": "10:30"}


def _generar(cliente, **extra):
    datos = {"id": "1", "accion": "generar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion", **extra}
    r = cliente.post(f"{BASE}/guardar", data=datos)
    assert "Fichero generado" in r.headers["HX-Trigger"], r.text[:300]
    return r


def test_con_el_fichero_generado_la_ficha_guia_la_presentacion_en_la_sede(cliente):
    assert "Presentar en la sede" not in cliente.get(f"{BASE}/f/1").text
    r = _generar(cliente)
    assert "Presentar en la sede de la AEAT" in r.text and "sede.agenciatributaria.gob.es" in r.text
    assert "U · Domiciliación" in r.text and "B12345678" in r.text and "casilla 71" in r.text and "ES9121000418450200051332" in r.text
    assert 'value="registrar"' in r.text and "hx-encoding=\"multipart/form-data\"" in r.text


def test_registrar_la_presentacion_guarda_justificante_y_bloquea_el_trimestre(cliente):
    _generar(cliente)
    r = cliente.post(f"{BASE}/guardar", data=REGISTRO, files={"pdf": ("justificante.pdf", PDF, "application/pdf")})
    assert "Presentación registrada: justificante 3037084443540" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]
    p = _presentaciones(cliente)[0]
    assert p.estado == "presentada" and p.csv == "ABCD1234EFGH5678" and p.presentada_en.strftime("%Y-%m-%d %H:%M") == "2026-04-14 10:30" and p.respuesta_sha256
    ficha = r.text
    assert "Presentación registrada" in ficha and "3037084443540" in ficha and "ya está presentado" in ficha and "Presentar en la sede de la AEAT" not in ficha
    j = cliente.get(f"{BASE}/{p.id}/justificante")
    assert j.status_code == 200 and j.content == PDF and j.headers["content-type"] == "application/pdf"
    assert cliente.get(f"{BASE}/99999/justificante").status_code == 404
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Presentado" in tabla and "3037084443540" in tabla
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal"})
    assert "ya está presentado" in r.text and len(_presentaciones(cliente)) == 1


def test_registrar_sin_datos_validos_muestra_el_error_y_no_cambia_nada(cliente):
    _generar(cliente)
    r = cliente.post(f"{BASE}/guardar", data={**REGISTRO, "justificante": "12"}, files={"pdf": ("j.pdf", PDF, "application/pdf")})
    assert "13 dígitos" in r.text and 'role="alert"' in r.text
    r = cliente.post(f"{BASE}/guardar", data=REGISTRO)  # sin PDF
    assert "PDF" in r.text
    r = cliente.post(f"{BASE}/guardar", data={**REGISTRO, "fecha_presentacion": ""}, files={"pdf": ("j.pdf", PDF, "application/pdf")})
    assert "No se reconoce el PDF" in r.text  # un PDF ilegible sin los datos tecleados
    assert _presentaciones(cliente)[0].estado == "generada"


def test_marcar_rechazada_permite_preparar_otro_borrador(cliente):
    _generar(cliente)
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "rechazar", "motivo": ""})
    assert "motivo" in r.text
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "rechazar", "motivo": "Error 12: IBAN no válido"})
    assert "Marcado como rechazado" in r.headers["HX-Trigger"]
    p = _presentaciones(cliente)[0]
    assert p.estado == "rechazada" and "IBAN" in p.observaciones
    assert "Presentar en la sede" not in r.text
    cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "guardar", "tipo_presentacion": "normal", "forma_pago": "domiciliacion"})
    assert [x.estado for x in _presentaciones(cliente)] == ["rechazada", "borrador"]


# ---------------------------------------------------------------------------------------------- el PDF de la sede lo rellena todo; dónde está lo que se prepara


def test_basta_subir_el_pdf_de_la_sede(cliente):
    from test_justificante_aeat import pdf_de_la_sede

    _generar(cliente)
    pdf = pdf_de_la_sede(resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None, fecha="14-04-2026 a las 17:24:37")
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf, "application/pdf")})
    assert "leído del PDF" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"], r.text[:400]
    p = _presentaciones(cliente)[0]
    assert p.estado == "presentada" and p.justificante == "3036479211552" and p.csv == "CKRKN4WXFTXCU8QT" and p.presentada_en.strftime("%d/%m/%Y %H:%M") == "14/04/2026 17:24"
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"})
    assert "No hay un fichero generado" in r.text or "Suba el PDF" in r.text


def test_un_pdf_que_no_corresponde_al_fichero_se_rechaza_con_un_mensaje_claro(cliente):
    from test_justificante_aeat import pdf_de_la_sede

    _generar(cliente)
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "registrar"}, files={"pdf": ("sede.pdf", pdf_de_la_sede(modelo="111"), "application/pdf")})
    assert "del modelo 111" in r.text and _presentaciones(cliente)[0].estado == "generada"


def test_lo_que_se_prepara_sobre_un_trimestre_presentado_se_ve_en_el_listado_y_dice_donde_esta_el_fichero(cliente):
    from conta_pridalac.db.modelos import PRESENTADA, PresentacionAeat

    s = cliente.app.state.config.sesion("prueba")
    s.add(PresentacionAeat(empresa_id=s.scalars(select(Empresa)).first().id, modelo="303", anio=2026, periodo="1T", estado=PRESENTADA, justificante="3037084443540", casillas=json.dumps({"69": "210.00", "71": "210.00"}), resultado=D("210.00")))
    s.commit()
    s.close()
    cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "rectificativa", "forma_pago": "domiciliacion"})
    tabla = cliente.get(f"{BASE}/tabla").text
    assert tabla.count("1T 2026") == 2 and "1T 2026 · rectificativa" in tabla and "Fichero generado (sin presentar)" in tabla and "EMPRESA_DE_PRUEBA_AEAT_303_2026_1T_rectificativa.303" in tabla
    ficha = cliente.get(f"{BASE}/f/1:2").text  # la fila de la rectificativa abre la ficha del trimestre
    assert "Guardado en" in ficha and "aeat" in ficha and "EMPRESA_DE_PRUEBA_AEAT_303_2026_1T_rectificativa.303" in ficha


# ---------------------------------------------------------------------------------------------- una sola pantalla: trimestres y declaraciones presentadas; ver y localizar el fichero


def test_la_pantalla_del_303_lleva_debajo_las_declaraciones_presentadas(cliente):
    pagina = cliente.get(BASE).text
    assert "Declaraciones presentadas" in pagina and "/e/prueba/2026/declaraciones/tabla" in pagina
    assert "/e/prueba/2026/declaraciones" not in cliente.get("/e/prueba/2026").text.replace("/e/prueba/2026/declaraciones/tabla", "")  # el panel sólo tiene la entrada del 303
    assert cliente.get("/e/prueba/2026/declaraciones/tabla").status_code == 200


def test_la_ficha_enseña_lo_que_lleva_el_fichero_y_abre_su_carpeta(cliente, monkeypatch):
    r = _generar(cliente)
    assert "Ver lo que lleva el fichero" in r.text and "Abrir la carpeta" in r.text and "B12345678" in r.text and "casillas con importe" in r.text
    abiertas = []
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: abiertas.append(args))
    p = _presentaciones(cliente)[0]
    r = cliente.post(f"{BASE}/{p.id}/carpeta")
    assert r.status_code == 200 and "Carpeta abierta" in r.headers["HX-Trigger"] and len(abiertas) == 1 and "aeat" in str(abiertas[0])
    assert cliente.post(f"{BASE}/99999/carpeta").status_code == 404


def test_si_el_fichero_cambia_la_ficha_lo_avisa(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    (cliente.app.state.config.almacen / p.fichero_ruta).write_bytes(b"<T303>cambiado")
    assert "ha cambiado desde que se generó" in cliente.get(f"{BASE}/f/1").text


# ---------------------------------------------------------------------------------------------- higiene: borrar lo no presentado


def test_la_ficha_borra_lo_no_presentado_con_sus_ficheros(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ruta = cliente.app.state.config.almacen / p.fichero_ruta
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "Eliminar lo no presentado (1)" in ficha and ruta.is_file()
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "eliminar_sin_presentar"})
    assert "Eliminado lo que no se presentó" in json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"] and not ruta.exists() and _presentaciones(cliente) == []
    assert "Eliminar lo no presentado" not in cliente.get(f"{BASE}/f/1").text
    r = cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "eliminar_sin_presentar"})
    assert "No hay borradores ni ficheros sin presentar" in r.text


def test_el_listado_borra_lo_pendiente_y_no_lo_presentado(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    ruta = cliente.app.state.config.almacen / p.fichero_ruta
    r = cliente.post(f"{BASE}/borrar", data={"ids": ["1"]})
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "ok" and not ruta.exists()
    s = cliente.app.state.config.sesion("prueba")
    s.add(PresentacionAeat(empresa_id=s.scalars(select(Empresa)).first().id, modelo="303", anio=2026, periodo="1T", estado=PRESENTADA, justificante="3037084443540", casillas="{}"))
    s.commit()
    s.close()
    r = cliente.post(f"{BASE}/borrar", data={"ids": ["1"]})  # el trimestre está presentado y no hay nada pendiente
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "error" and len(_presentaciones(cliente)) == 1
    ident = _presentaciones(cliente)[0].id
    r = cliente.post(f"{BASE}/borrar", data={"ids": [f"1:{ident}"]})  # ni siquiera señalándola
    assert json.loads(r.headers["HX-Trigger"])["mensaje"]["tipo"] == "error" and len(_presentaciones(cliente)) == 1


def test_lo_presentado_no_ofrece_casilla_de_borrado_y_lo_pendiente_si(cliente):
    from conta_pridalac.db.modelos import PRESENTADA, PresentacionAeat

    assert 'class="sel"' not in cliente.get(f"{BASE}/tabla").text  # nada que borrar: ni borradores ni presentaciones
    s = cliente.app.state.config.sesion("prueba")
    s.add(PresentacionAeat(empresa_id=s.scalars(select(Empresa)).first().id, modelo="303", anio=2026, periodo="1T", estado=PRESENTADA, justificante="3037084443540", casillas=json.dumps({"69": "210.00"}), resultado=D("210.00")))
    s.commit()
    s.close()
    assert 'class="sel"' not in cliente.get(f"{BASE}/tabla").text  # el trimestre presentado no se ofrece
    cliente.post(f"{BASE}/guardar", data={"id": "1", "accion": "generar", "tipo_presentacion": "rectificativa", "forma_pago": "domiciliacion"})
    tabla = cliente.get(f"{BASE}/tabla").text
    assert tabla.count('class="sel"') == 1 and 'value="1:' in tabla  # sólo la fila de la rectificativa pendiente


# ---------------------------------------------------------------------------------------------- copiar el fichero para presentar


def test_copiar_para_presentar_desde_la_ficha_y_abrir_su_carpeta(cliente, monkeypatch):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    destino = cliente.app.state.config.descargas
    r = cliente.post(f"{BASE}/{p.id}/copiar")
    texto = json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]
    esperado = destino / "EMPRESA_DE_PRUEBA_AEAT_303_2026_1T.303"
    assert texto == f"Copiado a {esperado}" and esperado.read_bytes() == (cliente.app.state.config.almacen / p.fichero_ruta).read_bytes()
    assert "Ya estaba copiado" in json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    abiertas = []
    monkeypatch.setattr("subprocess.Popen", lambda args, *a, **k: abiertas.append(args))
    assert cliente.post(f"{BASE}/{p.id}/carpeta-copia").status_code == 200
    # Windows abre el explorador con el fichero seleccionado; Linux, con xdg-open, abre su carpeta
    assert ("EMPRESA_DE_PRUEBA_AEAT_303_2026_1T.303" if os.name == "nt" else str(destino)) in str(abiertas[0])
    assert cliente.post(f"{BASE}/99999/copiar").status_code == 404 and cliente.post(f"{BASE}/99999/carpeta-copia").status_code == 404
    ficha = cliente.get(f"{BASE}/f/1").text
    assert "Copiar para presentar" in ficha and str(destino) in ficha


def test_si_el_fichero_cambio_no_se_copia(cliente):
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    (cliente.app.state.config.almacen / p.fichero_ruta).write_bytes(b"<T303>cambiado")
    assert "ha cambiado desde que se generó" in json.loads(cliente.post(f"{BASE}/{p.id}/copiar").headers["HX-Trigger"])["mensaje"]["texto"]
    assert cliente.post(f"{BASE}/{p.id}/carpeta-copia").status_code == 404  # nada copiado


def test_el_listado_copia_el_fichero_elegido(cliente):
    dialogo = cliente.get(f"{BASE}/accion/copiar").text
    assert "Todavía no hay ningún fichero generado" in dialogo
    _generar(cliente)
    p = _presentaciones(cliente)[0]
    dialogo = cliente.get(f"{BASE}/accion/copiar").text
    assert "EMPRESA_DE_PRUEBA_AEAT_303_2026_1T.303" in dialogo and "sin presentar" in dialogo
    r = cliente.post(f"{BASE}/accion/copiar", data={"presentacion": str(p.id)})
    assert "Copiado." in r.text and "Abrir la carpeta" in r.text and (cliente.app.state.config.descargas / "EMPRESA_DE_PRUEBA_AEAT_303_2026_1T.303").is_file()
    assert "Elija el fichero" in cliente.post(f"{BASE}/accion/copiar", data={}).text
    assert "Ya estaba copiado" not in r.text and "Ya estaba copiado." in cliente.post(f"{BASE}/accion/copiar", data={"presentacion": str(p.id)}).text
    assert "Copiar fichero para presentar" in cliente.get(BASE).text
