"""Pantalla de conciliación: cargar el Excel de Verifactu y ver qué movimiento del extracto propone para cada factura."""
from datetime import datetime

from sqlalchemy import select

from conta_pridalac.db.modelos import FacturaTrimestre
from test_extractos import CAIXA, excel as excel_extracto
from test_trimestre import excel, fila
from decimal import Decimal as D  # noqa: E402
from test_web_extractos import XLSX, cliente, importar, _sesion  # noqa: F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/conciliacion"


def cargar(cliente, contenido, nombre="recibidas.xlsx"):
    return cliente.post(f"{BASE}/accion/cargar", files={"fichero": (nombre, contenido, XLSX)})


def test_el_menu_ofrece_la_conciliacion_en_tesoreria(cliente):
    assert f'href="{BASE}"' in cliente.get("/e/prueba/2026").text and cliente.get(BASE).status_code == 200
    assert "está vacía" in cliente.get(f"{BASE}/tabla").text


def test_el_formulario_pide_el_excel(cliente):
    f = cliente.get(f"{BASE}/accion/cargar")
    assert f.status_code == 200 and 'type="file"' in f.text and "Verifactu" in f.text


def test_cargar_las_facturas_enseña_el_resultado_y_no_las_repite(cliente):
    contenido = excel([fila("Iberdrola Clientes", 100.5, 10, "F-1"), fila("Proveedor Raro", 77.7, 12, "F-2")])
    r = cargar(cliente, contenido)
    assert "Facturas cargadas" in r.text and "Nuevas</span><strong>2<" in r.text
    assert "Ya estaban</span><strong>2<" in cargar(cliente, contenido).text


def test_la_lista_enseña_la_propuesta_las_dudas_y_los_movimientos_sin_factura(cliente):
    importar(cliente)  # CAIXA: IBERDROLA -100,50 (10/03), V.NEGOCIOS CRED. -200 (5/03), TRANSFERENCIA +300,50
    mal = [fila("Iberdrola Clientes", 100.5, 10, "F-1"), fila("Proveedor Raro", 77.7, 12, "F-2")]
    for f in mal:
        f[3] = datetime(2026, 3, f[3].day)
    cargar(cliente, excel(mal))
    t = cliente.get(f"{BASE}/tabla").text
    assert "Propuesta" in t and "IBERDROLA CLIENT." in t and "Misma cantidad y el nombre coincide" in t
    assert "Sin movimiento" in t and "Proveedor Raro" in t
    assert "Sin factura" in t and "V.NEGOCIOS CRED." in t


def test_se_pueden_quitar_facturas_de_la_lista(cliente):
    cargar(cliente, excel([fila("Iberdrola Clientes", 100.5, 10, "F-1")]))
    s = _sesion(cliente)
    ident = s.scalars(select(FacturaTrimestre.id)).one()
    s.close()
    assert cliente.post(f"{BASE}/borrar", data={"ids": [f"f{ident}"]}).status_code == 200
    s = _sesion(cliente)
    assert s.scalars(select(FacturaTrimestre)).one().descartada  # sigue guardada, para que cargar el mismo Excel no la devuelva
    s.close()
    assert "Iberdrola" not in cliente.get(f"{BASE}/tabla").text


def test_un_excel_que_no_es_el_de_verifactu_se_dice_en_el_dialogo(cliente):
    assert "faltan las columnas" in cargar(cliente, excel_extracto([["a", "b"], [1, 2]])).text
    assert "Elija el Excel" in cliente.post(f"{BASE}/accion/cargar").text


def test_las_duplicadas_se_señalan_y_se_quitan_con_confirmacion(cliente):
    cargar(cliente, excel([fila("Securitas Direct", 165.66, 1, "2607C00300545", nif="A26106013"), fila("Securitas Direct", 165.66, 3, "FUS2607C00300545", nif="A26106013"), fila("Hotel Palace", 57, 10, "F-2")]))
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Duplicada" in tabla and "Parece la misma" in tabla
    dialogo = cliente.get(f"{BASE}/accion/duplicadas").text
    assert "FUS2607C00300545" in dialogo and "Quitar 1 duplicada" in dialogo
    hecho = cliente.post(f"{BASE}/accion/duplicadas").text
    assert "Duplicadas quitadas" in hecho and "Se han quitado 1" in hecho
    assert "FUS2607C00300545" not in cliente.get(f"{BASE}/tabla").text and "Hotel Palace" in cliente.get(f"{BASE}/tabla").text
    assert "ninguna posible duplicada" in cliente.get(f"{BASE}/accion/duplicadas").text


def test_aplicar_las_propuestas_crea_la_factura_y_el_pago_del_banco(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Cuenta, Factura, MovimientoBanco
    from test_trimestre import fila_en

    s = _sesion(cliente)
    s.add(Cuenta(empresa_id=s.scalar(select(Cuenta.empresa_id)), codigo="47200000", nombre="IVA SOPORTADO"))
    s.commit()
    s.close()
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 el 10/03
    cargar(cliente, excel([fila_en("Iberdrola Clientes", 100.5, date(2026, 3, 10), "F-1"), fila_en("Proveedor Raro", 77.7, date(2026, 3, 12), "F-2")]))
    sin_decidir = cliente.get(f"{BASE}/accion/aplicar").text
    assert "Proveedor nuevo: elija" in sin_decidir and "Aplicar 1<" not in sin_decidir  # un proveedor que Conta no tiene hay que decidirlo antes
    s = _sesion(cliente)
    ident = s.scalars(select(FacturaTrimestre.id).where(FacturaTrimestre.numero_factura == "F-1")).one()
    s.close()
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "crear": "on"}).status_code == 200
    dialogo = cliente.get(f"{BASE}/accion/aplicar").text
    assert "Aplicar 1<" in dialogo and "Se aplicarán</span><strong>1<" in dialogo
    hecho = cliente.post(f"{BASE}/accion/aplicar").text
    assert "Propuestas aplicadas" in hecho and "Facturas creadas</span><strong>1<" in hecho and "Proveedores nuevos" in hecho
    s = _sesion(cliente)
    assert s.scalars(select(Factura)).one().numero_factura == "F-1"
    m = s.scalars(select(MovimientoBanco)).one()
    assert (m.fecha, m.pagos[0].importe) == (date(2026, 3, 10), D("-100.50"))
    s.close()
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Proveedor Raro" in tabla and "Iberdrola" not in tabla  # lo aplicado sale de la lista de trabajo
    assert "Aplicar 1<" not in cliente.get(f"{BASE}/accion/aplicar").text
    hechas = cliente.get(f"{BASE}/tabla?ver=hechas").text
    assert "Contabilizada y pagada" in hechas and "IBERDROLA CLIENT" in hechas and "Proveedor Raro" not in hechas  # lo hecho se puede revisar, con su pago
    assert "Proveedor Raro" in cliente.get(f"{BASE}/tabla?ver=todas").text and "Contabilizada y pagada" in cliente.get(f"{BASE}/tabla?ver=todas").text
    assert "Contabilizada y pagada" not in tabla
    s = _sesion(cliente)
    factura_id = s.scalars(select(Factura.id)).one()
    s.close()
    formulario = cliente.get(f"/e/prueba/2026/facturas-recibidas/f/{factura_id}").text
    assert "con pagos" in formulario and "ver el movimiento" in formulario and "IBERDROLA CLIENT" in formulario and "movimientos?abrir=" in formulario  # el pago se ve en la propia factura


def test_se_elige_el_proveedor_de_conta_en_la_propia_lista_y_se_recuerda_para_el_nif(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Cuenta, Factura, Tercero
    from test_trimestre import fila_en

    s = _sesion(cliente)
    empresa_id = s.scalar(select(Cuenta.empresa_id))
    parking = Cuenta(empresa_id=empresa_id, codigo="41000010", nombre="TICKETS APARCAMIENTO")
    gasto = Cuenta(empresa_id=empresa_id, codigo="62900011", nombre="APARCAMIENTOS")
    s.add_all([parking, gasto, Cuenta(empresa_id=empresa_id, codigo="47200000", nombre="IVA SOPORTADO")])
    s.flush()
    s.add(Tercero(empresa_id=empresa_id, clase="P", nombre="TICKETS APARCAMIENTO", nif="VARIOSPARKING", cuenta_id=parking.id, cuenta_gasto_id=gasto.id))
    s.commit()
    s.close()
    importar(cliente)
    cargar(cliente, excel([fila_en("Archer Hotel Palace", 100.5, date(2026, 3, 10), "A-1", nif="B84623735"), fila_en("Archer Hotel Palace", 77.7, date(2026, 3, 12), "A-2", nif="B84623735")]))
    s = _sesion(cliente)
    primera = s.scalars(select(FacturaTrimestre.id).where(FacturaTrimestre.numero_factura == "A-1")).one()
    s.close()
    formulario = cliente.get(f"{BASE}/f/f{primera}").text
    assert "TICKETS APARCAMIENTO" in formulario and "VARIOSPARKING" in formulario  # la lista de sugerencias lleva el proveedor y su NIF
    malo = cliente.post(f"{BASE}/guardar", data={"id": f"f{primera}", "proveedor": "NO EXISTE"})
    assert "No hay ningún proveedor llamado" in malo.text
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{primera}", "proveedor": "tickets aparcamiento", "recordar": "on"}).status_code == 200
    tabla = cliente.get(f"{BASE}/tabla").text
    assert tabla.count("TICKETS APARCAMIENTO") >= 2 and "62900011" in tabla  # también la factura A-2, por la correspondencia del NIF
    hecho = cliente.post(f"{BASE}/accion/aplicar").text
    assert "Facturas creadas</span><strong>1<" in hecho and "Proveedores nuevos" not in hecho
    s = _sesion(cliente)
    f = s.scalars(select(Factura)).one()
    assert f.numero_factura == "A-1" and f.tercero.nombre == "TICKETS APARCAMIENTO" and f.cuenta_contrapartida.codigo == "62900011"
    s.close()


def _con_socio_y_proveedor(cliente):
    from conta_pridalac.db.modelos import Banco, Cuenta, Tercero
    s = _sesion(cliente)
    empresa_id = s.scalar(select(Cuenta.empresa_id))
    socio = Cuenta(empresa_id=empresa_id, codigo="55100002", nombre="BANCO JAVIER")
    proveedor = Cuenta(empresa_id=empresa_id, codigo="41000010", nombre="LEROY MERLIN")
    s.add_all([socio, proveedor, Cuenta(empresa_id=empresa_id, codigo="47200000", nombre="IVA SOPORTADO")])
    s.flush()
    s.add_all([Banco(empresa_id=empresa_id, numero=9, clase="B", nombre="BANCO JAVIER", cuenta_id=socio.id),
               Tercero(empresa_id=empresa_id, clase="P", nombre="LEROY MERLIN", nif="B84818442", cuenta_id=proveedor.id, cuenta_gasto_id=s.scalars(select(Cuenta.id).where(Cuenta.codigo == "62900000")).one())])
    s.commit()
    s.close()


def test_las_facturas_sin_movimiento_se_marcan_como_pagadas_por_el_socio_y_se_aplican(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Banco, Factura, MovimientoBanco
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442"), fila_en("Leroy Merlin", 14.86, date(2026, 3, 2), "L-2", nif="B84818442")]))
    dialogo = cliente.get(f"{BASE}/accion/socio").text
    assert "Facturas pagadas por el socio" in dialogo and "BANCO JAVIER" in dialogo and "L-1" in dialogo and "Leroy Merlin" in dialogo and "2 factura(s) sin movimiento" in dialogo
    s = _sesion(cliente)
    ids = [str(i) for i in s.scalars(select(FacturaTrimestre.id).order_by(FacturaTrimestre.numero_factura))]
    banco = s.scalars(select(Banco.id).where(Banco.nombre == "BANCO JAVIER")).one()
    s.close()
    assert "Elija el banco" in cliente.post(f"{BASE}/accion/socio", data={"factura": ids}).text
    assert "Marque las facturas" in cliente.post(f"{BASE}/accion/socio", data={"banco": str(banco)}).text
    hecho = cliente.post(f"{BASE}/accion/socio", data={"banco": str(banco), "fecha": "28/03/2026", "factura": ids[:1]}).text
    assert "Marcadas como pagadas por el socio" in hecho and "1 factura(s) pagadas por <strong>BANCO JAVIER" in hecho
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Pagada por socio" in tabla and "Sin movimiento" in tabla  # la otra sigue sin movimiento
    ap = cliente.get(f"{BASE}/accion/aplicar").text
    assert "pagadas por el socio</span><strong>1<" in ap and "Aplicar 1<" in ap
    hecho = cliente.post(f"{BASE}/accion/aplicar").text
    assert "Facturas creadas</span><strong>1<" in hecho
    s = _sesion(cliente)
    m = s.scalars(select(MovimientoBanco)).one()
    assert (m.fecha, m.banco.nombre, m.pagos[0].importe) == (date(2026, 3, 28), "BANCO JAVIER", D("-61.91")) and s.scalars(select(Factura)).one().numero_factura == "L-1"
    s.close()


def test_el_formulario_de_la_factura_permite_decir_quien_pago(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Banco
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442")]))
    s = _sesion(cliente)
    ident = s.scalars(select(FacturaTrimestre.id)).one()
    banco = s.scalars(select(Banco.id).where(Banco.nombre == "BANCO JAVIER")).one()
    s.close()
    assert "Pagada por" in cliente.get(f"{BASE}/f/f{ident}").text
    assert "Elija el proveedor" in cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "pagador": ""}).text
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "pagador": str(banco), "fecha_pago": "280326"}).status_code == 200  # basta con decir quién pagó
    s = _sesion(cliente)
    f = s.scalars(select(FacturaTrimestre)).one()
    assert (f.pagada_por_id, f.pagada_fecha) == (banco, date(2026, 3, 28))
    s.close()
    assert "Pagada por socio" in cliente.get(f"{BASE}/tabla").text


def test_contabilizar_el_resto_deja_las_facturas_sin_pago_en_vencimientos_pendientes(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Factura, MovimientoBanco, Vencimiento
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442"), fila_en("Leroy Merlin", 14.86, date(2026, 3, 2), "L-2", nif="B84818442")]))
    dialogo = cliente.get(f"{BASE}/accion/pendientes").text
    assert "Contabilizar el resto como pendientes" in dialogo and "Se contabilizarán</span><strong>2<" in dialogo and "Contabilizar 2<" in dialogo
    hecho = cliente.post(f"{BASE}/accion/pendientes").text
    assert "contabilizadas como pendientes de pago" in hecho and "Facturas creadas</span><strong>2<" in hecho
    s = _sesion(cliente)
    assert len(list(s.scalars(select(Factura)))) == 2 and not list(s.scalars(select(MovimientoBanco))) and len(list(s.scalars(select(Vencimiento)))) == 2
    s.close()
    assert "LEROY" in cliente.get("/e/prueba/2026/vencimientos/tabla").text.upper() and "2 filas" in cliente.get("/e/prueba/2026/vencimientos/tabla").text
    assert "No hay" in cliente.get(f"{BASE}/accion/pendientes").text or "Se contabilizarán</span><strong>0<" in cliente.get(f"{BASE}/accion/pendientes").text


# ---------------------------------------------------------------------------- conciliar pagos: vencimientos pendientes con líneas del extracto


def test_conciliar_pagos_sugiere_acepta_y_deja_hacerlo_a_mano(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Cuenta, ExtractoLinea, MovimientoBanco, Vencimiento
    from test_trimestre import fila_en

    BASE_P = "/e/prueba/2026/conciliar-pagos"
    _con_socio_y_proveedor(cliente)
    s = _sesion(cliente)
    s.add(Cuenta(empresa_id=s.scalar(select(Cuenta.empresa_id)), codigo="77800000", nombre="OTROS INGRESOS"))
    s.commit()
    s.close()
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 el 10/03 · V.NEGOCIOS CRED. -200,00 el 05/03
    cargar(cliente, excel([fila_en("Leroy Merlin", 100.51, date(2026, 3, 10), "L-1", nif="B84818442"), fila_en("V.NEGOCIOS CRED", 190, date(2026, 3, 5), "N-1", nif="B33333333")]))
    s = _sesion(cliente)
    nueva = s.scalars(select(FacturaTrimestre.id).where(FacturaTrimestre.numero_factura == "N-1")).one()
    s.close()
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{nueva}", "crear": "on"}).status_code == 200
    assert cliente.get("/e/prueba/2026").text.count(f'href="{BASE_P}"') >= 1 and cliente.get(BASE_P).status_code == 200
    cliente.post(f"{BASE}/accion/pendientes")  # las dos facturas, sin pago, quedan como vencimientos pendientes
    tabla = cliente.get(f"{BASE_P}/tabla").text
    assert "Mismo nombre y fecha, pero otro importe" in tabla and "V.NEGOCIOS CRED" in tabla  # una sugerencia: mismo nombre, otro importe
    sin_factura = cliente.get("/e/prueba/2026/lineas-sin-factura/tabla").text
    assert "Paga a" in sin_factura and "Sugerencias de pago" in sin_factura and "sugerencia de pago" in sin_factura  # la línea que ya tiene sugerencia no sale «sin regla» a secas
    s = _sesion(cliente)
    v_leroy = s.scalars(select(Vencimiento.id).where(Vencimiento.factura.has(numero_factura="L-1"))).one()
    v_neg = s.scalars(select(Vencimiento.id).where(Vencimiento.factura.has(numero_factura="N-1"))).one()
    lineas = {l.texto: l.id for l in s.scalars(select(ExtractoLinea))}
    s.close()
    clave = f"v{v_neg}_l{lineas['V.NEGOCIOS CRED.']}"
    resumen = cliente.get(f"{BASE_P}/f/{clave}").text
    assert "Diferencia de 10,00" in resumen and "pagada de más" in resumen and "Saldar con una diferencia" in resumen
    sin_cuenta = cliente.post(f"{BASE_P}/guardar", data={"clave": clave, "modo": "diferencia", "cuenta": "99999999"})
    assert "Elija la subcuenta" in sin_cuenta.text
    assert cliente.post(f"{BASE_P}/guardar", data={"clave": clave, "modo": "diferencia", "cuenta": "62900000"}).status_code == 200
    s = _sesion(cliente)
    assert len(list(s.scalars(select(MovimientoBanco)))) == 1
    s.close()
    # a mano, desde «Líneas sin factura»: Leroy (100,51) con la línea de Iberdrola (100,50), que falta un céntimo
    BASE_L = "/e/prueba/2026/lineas-sin-factura"
    assert "Pagar vencimientos con las marcadas" in cliente.get(BASE_L).text and 'class="sel"' in cliente.get(f"{BASE_L}/tabla").text  # la lista tiene casillas y el botón
    marcada = {"ids": [f"l{lineas['IBERDROLA CLIENT.']}"]}
    dialogo = cliente.post(f"{BASE_L}/accion/pagar", data=marcada).text
    assert "Pagar vencimientos con las líneas marcadas" in dialogo and "IBERDROLA CLIENT." in dialogo and "LEROY" in dialogo and "V.NEGOCIOS" not in dialogo  # la ya conciliada no sale
    assert "Marque al menos una línea" in cliente.post(f"{BASE_L}/accion/pagar", data={"paso": "resumen", "venc": [str(v_leroy)]}).text
    assert "Marque al menos un vencimiento" in cliente.post(f"{BASE_L}/accion/pagar", data={**marcada, "paso": "resumen"}).text
    paso2 = cliente.post(f"{BASE_L}/accion/pagar", data={**marcada, "paso": "resumen", "venc": [str(v_leroy)]}).text
    assert "Diferencia de 0,01" in paso2 and "por pagar" in paso2 and "Pago parcial" in paso2 and 'hx-post="/e/prueba/2026/conciliar-pagos/guardar"' in paso2
    assert cliente.post(f"{BASE_P}/guardar", data={"clave": f"v{v_leroy}_l{lineas['IBERDROLA CLIENT.']}", "modo": "diferencia", "cuenta": "77800000"}).status_code == 200
    s = _sesion(cliente)
    assert len(list(s.scalars(select(MovimientoBanco)))) == 2
    s.close()
    assert "No hay sugerencias" in cliente.get(f"{BASE_P}/tabla").text


def test_en_la_lista_se_puede_elegir_el_proveedor_por_su_nif_y_cambiar_el_numero_de_factura(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import FacturaTrimestre as FT
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Restaurante J.J.", 51.6, date(2026, 3, 5), "No reconocido", nif="B44444444")]))
    s = _sesion(cliente)
    ident = s.scalars(select(FT.id)).one()
    s.close()
    assert "Nº de factura" in cliente.get(f"{BASE}/f/f{ident}").text
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "numero": "T-123", "proveedor": "b84818442"}).status_code == 200  # el NIF de LEROY MERLIN
    s = _sesion(cliente)
    f = s.scalars(select(FT)).one()
    assert f.numero_factura == "T-123" and f.tercero_id is not None
    s.close()
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "41000010"}).status_code == 200  # la subcuenta de LEROY MERLIN
    assert 'value="LEROY MERLIN · B84818442 · 41000010"' in cliente.get(f"{BASE}/f/f{ident}").text  # la lista lleva nombre, NIF y subcuenta en una sola cadena, para filtrar por cualquiera
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "LEROY MERLIN · B84818442 · 41000010"}).status_code == 200  # y lo que se elige de la lista se entiende
    assert "ni con esa subcuenta" in cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "NO-EXISTE"}).text


def test_contabilizar_el_resto_avisa_si_quedan_propuestas_sin_aplicar(cliente):
    from datetime import date

    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    importar(cliente)
    cargar(cliente, excel([fila_en("Iberdrola Clientes", 100.5, date(2026, 3, 10), "F-1", nif="B84818442")]))  # propuesta segura con el extracto
    assert "Antes, aplique las propuestas" in cliente.get(f"{BASE}/accion/pendientes").text
    cliente.post(f"{BASE}/accion/aplicar")
    assert "Antes, aplique las propuestas" not in cliente.get(f"{BASE}/accion/pendientes").text


def test_se_puede_pagar_con_un_banco_de_socio_sin_extracto_desde_lineas_sin_factura(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Banco, MovimientoBanco
    from test_trimestre import fila_en

    BASE_P = "/e/prueba/2026/conciliar-pagos"
    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442")]))
    cliente.post(f"{BASE}/accion/pendientes")
    s = _sesion(cliente)
    from conta_pridalac.db.modelos import Vencimiento
    v = s.scalars(select(Vencimiento.id)).one()
    banco = s.scalars(select(Banco.id).where(Banco.nombre == "BANCO JAVIER")).one()
    s.close()
    BASE_L = "/e/prueba/2026/lineas-sin-factura"
    assert "Pagar sin línea de extracto" in cliente.get(f"{BASE_L}/accion/sin_linea").text
    assert "Elija el banco" in cliente.post(f"{BASE_L}/accion/sin_linea", data={"venc": [str(v)]}).text
    hecho = cliente.post(f"{BASE_L}/accion/sin_linea", data={"venc": [str(v)], "banco": str(banco), "fecha": "28/03/2026"}).text
    assert "Pagos registrados" in hecho and "BANCO JAVIER" in hecho
    s = _sesion(cliente)
    m = s.scalars(select(MovimientoBanco)).one()
    assert (m.fecha, m.banco.nombre) == (date(2026, 3, 28), "BANCO JAVIER")
    s.close()


def test_se_abre_el_pdf_de_la_factura_desde_la_lista_de_trabajo(cliente, tmp_path):
    from datetime import date

    from conta_pridalac.db.modelos import FacturaTrimestre as FT
    from test_trimestre import fila_en

    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%prueba\n")
    fila = fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442")
    fila[9] = str(pdf)
    sin_pdf = fila_en("Otro", 10, date(2026, 3, 2), "O-1", nif="B84818442")
    sin_pdf[9] = str(tmp_path / "no_existe.pdf")
    peligro = fila_en("Peligro", 20, date(2026, 3, 3), "X-1", nif="B84818442")
    peligro[9] = str(tmp_path / "datos.sqlite")  # un fichero que no es PDF ni imagen
    (tmp_path / "datos.sqlite").write_bytes(b"secreto")
    cargar(cliente, excel([fila, sin_pdf, peligro]))
    s = _sesion(cliente)
    ids = {f.numero_factura: f.id for f in s.scalars(select(FT))}
    s.close()
    assert "Ver el PDF de la factura" in cliente.get(f"{BASE}/f/f{ids['L-1']}").text
    r = cliente.get(f"{BASE}/pdf/{ids['L-1']}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert cliente.get(f"{BASE}/pdf/{ids['O-1']}").status_code == 404  # la ruta no existe en el disco
    assert cliente.get(f"{BASE}/pdf/{ids['X-1']}").status_code == 404 and b"secreto" not in cliente.get(f"{BASE}/pdf/{ids['X-1']}").content  # sólo PDF o imágenes
    assert cliente.get(f"{BASE}/pdf/9999").status_code == 404


def test_buscar_proveedor_por_nombre_comercial_nif_o_subcuenta_o_por_la_cadena_de_la_lista():
    from conta_pridalac.db.modelos import Tercero
    from conta_pridalac.web.conciliacion import _buscar_proveedor, _texto_de_proveedor

    obramat = Tercero(id=1, empresa_id=1, clase="P", nombre="Obramat majadahonda", comercial="Bricolage Bricoman S.L.U OBRAMAT", nif="B84406000", cuenta_id=10)
    leroy = Tercero(id=2, empresa_id=1, clase="P", nombre="LEROY MERLIN", comercial="LEROY MERLIN", nif="B84818442", cuenta_id=11)
    codigos = {10: "41000166", 11: "41000049"}
    todos = [obramat, leroy]
    assert _texto_de_proveedor(obramat, codigos) == "Obramat majadahonda · Bricolage Bricoman S.L.U OBRAMAT · B84406000 · 41000166"
    assert _texto_de_proveedor(leroy, codigos) == "LEROY MERLIN · B84818442 · 41000049"  # el comercial igual al nombre no se repite
    for escrito in ("leroy merlin", "b-84818442", "41000049", "LEROY MERLIN · B84818442 · 41000049"):
        assert _buscar_proveedor(todos, codigos, escrito) == [leroy]
    for escrito in ("bricolage bricoman s.l.u obramat", "41000166", "Obramat majadahonda · Bricolage Bricoman S.L.U OBRAMAT · B84406000 · 41000166"):
        assert _buscar_proveedor(todos, codigos, escrito) == [obramat]
    assert _buscar_proveedor(todos, codigos, "nadie") == []


def test_en_la_lista_no_se_admite_como_gasto_una_cuenta_que_no_es_de_gasto(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import FacturaTrimestre as FT
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Leroy Merlin", 61.91, date(2026, 3, 1), "L-1", nif="B84818442")]))
    s = _sesion(cliente)
    ident = s.scalars(select(FT.id)).one()
    s.close()
    malo = cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "LEROY MERLIN", "gasto": "41000010"})
    assert "no es de gasto" in malo.text
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "LEROY MERLIN", "gasto": "62900000"}).status_code == 200


def test_se_corrigen_la_base_y_el_iva_de_una_factura_que_verifactu_leyo_mal_y_se_puede_aplicar(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import FacturaTrimestre as FT, Factura
    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    mal = fila_en("Leroy Merlin", 14.15, date(2026, 3, 1), "L-1", nif="B84818442")
    mal[5], mal[6], mal[7], mal[8] = 13.73, 21, 2.88, 14.15  # base + IVA = 16,61 > total 14,15
    cargar(cliente, excel([mal]))
    s = _sesion(cliente)
    ident = s.scalars(select(FT.id)).one()
    s.close()
    cliente.post(f"{BASE}/accion/pendientes")
    assert "Se contabilizarán</span><strong>0<" in cliente.get(f"{BASE}/accion/pendientes").text and "menor que base + IVA" in cliente.get(f"{BASE}/accion/pendientes").text
    form = cliente.get(f"{BASE}/f/f{ident}").text
    assert "Base imponible" in form and "13,73" in form
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "LEROY MERLIN", "base": "11,69", "pct_iva": "21", "cuota_iva": "2,46"}).status_code == 200
    hecho = cliente.post(f"{BASE}/accion/pendientes").text
    assert "Facturas creadas</span><strong>1<" in hecho
    s = _sesion(cliente)
    f = s.scalars(select(Factura)).one()
    assert (f.total, [(i.base, i.cuota_iva) for i in f.ivas]) == (D("14.15"), [(D("11.69"), D("2.46"))])
    s.close()


def test_recordar_no_guarda_la_subcuenta_de_gasto_y_la_lista_de_correspondencias_se_ve_y_se_borra(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import CorrespondenciaTercero, FacturaTrimestre as FT
    from test_trimestre import fila_en

    BASE_C = "/e/prueba/2026/correspondencias"
    _con_socio_y_proveedor(cliente)
    cargar(cliente, excel([fila_en("Areas SAU", 24.67, date(2026, 3, 1), "A-1", nif="A08225013")]))
    s = _sesion(cliente)
    ident = s.scalars(select(FT.id)).one()
    s.close()
    assert cliente.post(f"{BASE}/guardar", data={"id": f"f{ident}", "proveedor": "LEROY MERLIN", "gasto": "62900000", "recordar": "on"}).status_code == 200
    s = _sesion(cliente)
    c = s.scalars(select(CorrespondenciaTercero)).one()
    assert (c.nif, c.cuenta_gasto_id) == ("A08225013", None)  # el proveedor se recuerda, la subcuenta no
    ident_c = c.id
    s.close()
    assert "A08225013" in cliente.get(f"{BASE_C}/tabla").text and "LEROY MERLIN" in cliente.get(f"{BASE_C}/tabla").text
    assert cliente.post(f"{BASE_C}/borrar", data={"ids": [str(ident_c)]}).status_code == 200
    assert "No hay correspondencias" in cliente.get(f"{BASE_C}/tabla").text


# ---------------------------------------------------------------------------- líneas sin factura


def test_las_lineas_sin_factura_se_deciden_una_a_una_y_se_aplican_las_sugerencias(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Cuenta, ExtractoLinea, MovimientoBanco, ReglaLinea
    from test_trimestre import fila_en

    BASE_L = "/e/prueba/2026/lineas-sin-factura"
    _con_socio_y_proveedor(cliente)
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03) · V.NEGOCIOS CRED. -200,00 (05/03) · TRANSFERENCIA DE CLIENTE +300,50 (01/03)
    cargar(cliente, excel([fila_en("Leroy Merlin", 14.86, date(2026, 3, 1), "L-1", nif="B84818442")]))  # la lista de trabajo marca el periodo del extracto que se mira
    assert cliente.get("/e/prueba/2026").text.count(f'href="{BASE_L}"') >= 1
    tabla = cliente.get(f"{BASE_L}/tabla").text
    assert tabla.count("— sin regla —") == 3 and "V.NEGOCIOS CRED." in tabla
    s = _sesion(cliente)
    lineas = {l.texto: l.id for l in s.scalars(select(ExtractoLinea))}
    s.close()
    form = cliente.get(f"{BASE_L}/f/l{lineas['V.NEGOCIOS CRED.']}").text
    assert "Qué hacer con la línea" in form and "Recordar para los conceptos como éste" in form
    assert "datos-ficha" in form and "V.NEGOCIOS CRED." in form and "200,00" in form and "CAIXABANK" in form  # arriba se ve la línea que se está decidiendo
    assert "Proveedor (Verifactu)" in cliente.get(f"{BASE}/f/f{s_id}").text if (s_id := _sesion(cliente).scalars(select(FacturaTrimestre.id)).first()) else False  # y en la conciliación, la factura
    # errores
    assert "Elija el proveedor del ticket" in cliente.post(f"{BASE_L}/guardar", data={"id": f"l{lineas['V.NEGOCIOS CRED.']}", "tratamiento": "ticket"}).text
    assert "no existe en el plan" in cliente.post(f"{BASE_L}/guardar", data={"id": f"l{lineas['V.NEGOCIOS CRED.']}", "tratamiento": "cuenta", "cuenta": "99999999"}).text
    # una línea a una cuenta, y recordarlo
    assert cliente.post(f"{BASE_L}/guardar", data={"id": f"l{lineas['V.NEGOCIOS CRED.']}", "tratamiento": "cuenta", "cuenta": "52100001", "recordar": "on"}).status_code == 200
    s = _sesion(cliente)
    m = s.scalars(select(MovimientoBanco)).one()
    regla = s.scalars(select(ReglaLinea)).one()
    assert (m.fecha, m.texto, m.pagos[0].importe, regla.patron, regla.tratamiento) == (date(2026, 3, 5), "V.NEGOCIOS CRED.", D("-200.00"), "v negocios cred", "cuenta")
    cuenta_gasto = s.scalars(select(Cuenta.id).where(Cuenta.codigo == "62900000")).one()
    s.add(ReglaLinea(empresa_id=regla.empresa_id, patron="iberdrola client", tratamiento="cuenta", cuenta_id=cuenta_gasto))
    s.commit()
    s.close()
    dialogo = cliente.get(f"{BASE_L}/accion/aplicar").text
    assert "Se contabilizarán</span><strong>1<" in dialogo and "Sin regla</span><strong>1<" in dialogo and "IBERDROLA CLIENT." in dialogo and "Contabilizar las marcadas" in dialogo
    assert "Marque al menos una línea" in cliente.post(f"{BASE_L}/accion/aplicar").text  # sin marcar nada no se hace nada
    hecho = cliente.post(f"{BASE_L}/accion/aplicar", data={"linea": [str(lineas["IBERDROLA CLIENT."])]}).text
    assert "Líneas contabilizadas" in hecho and "Movimientos a una cuenta</span><strong>1<" in hecho
    s = _sesion(cliente)
    assert len(list(s.scalars(select(MovimientoBanco)))) == 2
    s.close()
    assert "IBERDROLA" not in cliente.get(f"{BASE_L}/tabla").text and "Se contabilizarán</span><strong>0<" in cliente.get(f"{BASE_L}/accion/aplicar").text


def test_se_crea_la_factura_que_pagan_varias_lineas_marcadas(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import ExtractoLinea, Factura, MovimientoBanco, Vencimiento
    from conta_pridalac.domain.tesoreria import pendiente
    from test_trimestre import fila_en

    BASE_L = "/e/prueba/2026/lineas-sin-factura"
    _con_socio_y_proveedor(cliente)
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03) · V.NEGOCIOS CRED. -200,00 (05/03) · TRANSFERENCIA DE CLIENTE +300,50 (01/03)
    cargar(cliente, excel([fila_en("Leroy Merlin", 14.86, date(2026, 3, 1), "L-1", nif="B84818442")]))
    s = _sesion(cliente)
    lineas = {l.texto: l.id for l in s.scalars(select(ExtractoLinea))}
    s.close()
    ids = [f"l{lineas['IBERDROLA CLIENT.']}", f"l{lineas['V.NEGOCIOS CRED.']}"]
    assert "Crear factura con las marcadas" in cliente.get(BASE_L).text
    dialogo = cliente.post(f"{BASE_L}/accion/crear", data={"ids": ids}).text
    assert "Crear la factura que pagan las líneas marcadas" in dialogo and "300,50" in dialogo and 'value="21,00"' in dialogo and "05/03/2026" in dialogo  # total = suma de las líneas, IVA 21 %, fecha de la primera línea
    datos = {"ids": ids, "paso": "crear", "proveedor": "", "numero": "X-1", "fecha": "10/03/2026", "iva": "21,00", "gasto": ""}
    assert "Elija el proveedor de la lista" in cliente.post(f"{BASE_L}/accion/crear", data=datos).text
    r = cliente.post(f"{BASE_L}/accion/crear", data={**datos, "proveedor": "LEROY MERLIN", "numero": ""}).text
    assert "Falta el número" in r, r[:1500]
    s = _sesion(cliente)
    assert s.scalars(select(Factura)).first() is None  # los errores no dejan nada a medias
    s.close()
    hecho = cliente.post(f"{BASE_L}/accion/crear", data={**datos, "proveedor": "LEROY MERLIN"}).text
    assert "Factura creada" in hecho and "X-1" in hecho
    s = _sesion(cliente)
    f = s.scalars(select(Factura)).one()
    assert (f.numero_factura, f.total, f.tercero.nombre, f.cuenta_contrapartida.codigo) == ("X-1", D("300.50"), "LEROY MERLIN", "62900000")
    assert sum(i.cuota_iva for i in f.ivas) == D("52.15") and all(pendiente(s, v) == 0 for v in s.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)))  # 300,50 con el IVA incluido, pagada del todo
    assert len(list(s.scalars(select(MovimientoBanco)))) == 2 and all(l.movimiento_id for l in s.scalars(select(ExtractoLinea).where(ExtractoLinea.id.in_([int(i[1:]) for i in ids]))))
    s.close()
    tabla = cliente.get(f"{BASE_L}/tabla").text
    assert "IBERDROLA" not in tabla and "V.NEGOCIOS" not in tabla  # las líneas dejan de estar libres


CABECERA_EMITIDAS = ["N° Factura", "Fecha", "Emisor NIF", "Emisor Nombre", "Fecha Expedición", "Fecha Operación", "Cliente Nombre", "Cliente NIF", "Cliente Dirección", "IBAN", "Base Imponible", "IVA %",
                     "Cuota IVA", "IVA Total", "Total", "Estado", "Descripción", "Fecha Creación"]


def fila_emitida(numero, dia, cliente_nombre, nif, base, iva, emisor="", estado="Pendiente"):
    cuota = round(base * iva / 100, 2)
    fecha = datetime(2026, 3, dia)
    return [numero, fecha, emisor, "EMPRESA", fecha, "02/07=2026", cliente_nombre, nif, "c/ Mayor 1", None, base, iva, cuota, cuota, round(base + cuota, 2), estado, "Factura", datetime(2026, 10, 14)]


def test_las_emitidas_se_cargan_de_un_excel_y_se_cobran_con_el_extracto(cliente):
    from conta_pridalac.db.modelos import Cuenta, Empresa, Factura, MovimientoBanco, Tercero
    from test_trimestre import excel

    BASE_E = "/e/prueba/2026/emitidas-trimestre"
    _con_socio_y_proveedor(cliente)
    s = _sesion(cliente)
    empresa_id = s.scalar(select(Cuenta.empresa_id))
    for codigo, nombre in (("43000010", "CLIENTE ALQUILER"), ("47700000", "IVA REPERCUTIDO"), ("70500000", "ALQUILERES")):
        if s.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).first() is None:
            s.add(Cuenta(empresa_id=empresa_id, codigo=codigo, nombre=nombre))
    s.flush()
    s.add(Tercero(empresa_id=empresa_id, clase="C", nombre="CLIENTE ALQUILER", nif="A28490027", cuenta_id=s.scalars(select(Cuenta.id).where(Cuenta.codigo == "43000010")).one(),
                  cuenta_gasto_id=s.scalars(select(Cuenta.id).where(Cuenta.codigo == "70500000")).one()))
    s.get(Empresa, empresa_id).nif = "B00000020"
    s.commit()
    s.close()
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03) · V.NEGOCIOS CRED. -200,00 (05/03) · TRANSFERENCIA DE CLIENTE +300,50 (01/03)
    assert f'href="{BASE_E}"' in cliente.get("/e/prueba/2026").text
    subir = lambda contenido: cliente.post(f"{BASE_E}/accion/cargar", files={"fichero": ("emitidas.xlsx", contenido, XLSX)}).text  # noqa: E731
    assert "faltan las columnas" in subir(excel([["a", "b"]], cabecera=["a", "b"]))
    assert "esta empresa tiene el" in subir(excel([fila_emitida("26/01", 1, "Cliente Alquiler", "A 28490027", 248.35, 21, emisor="B11111111")], cabecera=CABECERA_EMITIDAS))
    cargadas = subir(excel([fila_emitida("26/01", 1, "Cliente Alquiler", "A 28490027", 248.35, 21, emisor="B-00000020"), fila_emitida("26/02", 20, "Cliente Alquiler", "A 28490027", 100, 21, emisor="B00000020")], cabecera=CABECERA_EMITIDAS))
    assert "Facturas cargadas" in cargadas and "Nuevas</span><strong>2<" in cargadas
    tabla = cliente.get(f"{BASE_E}/tabla").text
    assert "Cliente Alquiler" in tabla and "300,50" in tabla and "TRANSFERENCIA DE CLIENTE" in tabla  # la factura de 300,50 se propone con el ingreso del mismo importe
    dialogo = cliente.get(f"{BASE_E}/accion/aplicar").text
    assert "Aplicar 1<" in dialogo and "cobrada por un ingreso" in dialogo
    hecho = cliente.post(f"{BASE_E}/accion/aplicar").text
    assert "Propuestas aplicadas" in hecho and "Facturas creadas</span><strong>1<" in hecho
    s = _sesion(cliente)
    f = s.scalars(select(Factura).where(Factura.sentido == "E")).one()
    m = s.scalars(select(MovimientoBanco)).one()
    assert (f.numero_factura, f.total, f.tercero.nombre, f.cuenta_contrapartida.codigo) == ("26/01", D("300.50"), "CLIENTE ALQUILER", "70500000") and m.pagos[0].importe == D("300.50")
    s.close()
    assert "Cliente Alquiler" in cliente.get(f"{BASE_E}/tabla?ver=hechas").text and "cobrada" in cliente.get(f"{BASE_E}/tabla?ver=hechas").text
    resto = cliente.post(f"{BASE_E}/accion/pendientes").text
    assert "pendientes de cobro" in resto and "Facturas creadas</span><strong>1<" in resto
    assert "Se contabilizarán</span><strong>0<" in cliente.get(f"{BASE_E}/accion/pendientes").text
    # volver a cargar el mismo Excel no repite nada, y lo que Conta ya tiene se enlaza sin duplicar
    otra = subir(excel([fila_emitida("26/01", 1, "Cliente Alquiler", "A 28490027", 248.35, 21)], cabecera=CABECERA_EMITIDAS))
    assert "Ya estaban</span><strong>1<" in otra


def test_se_enlazan_las_lineas_del_extracto_con_los_movimientos_ya_contabilizados(cliente):
    from datetime import date

    from conta_pridalac.db.modelos import Banco, Ejercicio, ExtractoLinea, MovimientoBanco
    from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento

    BASE_E = "/e/prueba/2026/conciliacion"
    _con_socio_y_proveedor(cliente)
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03) · V.NEGOCIOS CRED. -200,00 (05/03) · TRANSFERENCIA DE CLIENTE +300,50 (01/03)
    cliente.post("/e/prueba/2026/trimestre/accion/cambiar", data={"trimestre": "2026-1"})  # el extracto es de marzo
    s = _sesion(cliente)
    banco = s.scalars(select(Banco).where(Banco.nombre == "CAIXABANK")).one()
    registrar_movimiento(s, s.scalars(select(Ejercicio).where(Ejercicio.anio == 2026)).one(), banco, date(2026, 3, 10), [LineaPago(D("-100.50"), cuenta_directa="62900000")], texto="IBERDROLA")
    s.commit()
    s.close()
    dialogo = cliente.get(f"{BASE_E}/accion/enlazar").text
    assert "Se enlazarán</span><strong>1<" in dialogo and "IBERDROLA CLIENT." in dialogo and "Enlazar 1<" in dialogo
    hecho = cliente.post(f"{BASE_E}/accion/enlazar").text
    assert "Líneas enlazadas" in hecho and "1 línea(s)" in hecho
    s = _sesion(cliente)
    linea = s.scalars(select(ExtractoLinea).where(ExtractoLinea.texto == "IBERDROLA CLIENT.")).one()
    assert linea.movimiento_id == s.scalars(select(MovimientoBanco.id)).one()  # no se ha creado ningún movimiento nuevo
    assert len(list(s.scalars(select(MovimientoBanco)))) == 1
    s.close()
    assert "Se enlazarán</span><strong>0<" in cliente.get(f"{BASE_E}/accion/enlazar").text  # ya no queda nada por enlazar


def test_la_lista_enseña_sólo_el_trimestre_de_trabajo_y_recargar_recupera_lo_borrado(cliente):
    from datetime import date

    from test_trimestre import fila_en

    BASE_T = "/e/prueba/2026/trimestre"
    _con_socio_y_proveedor(cliente)
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03) · V.NEGOCIOS CRED. -200,00 (05/03) · TRANSFERENCIA DE CLIENTE +300,50 (01/03)
    contenido = excel([fila_en("Leroy Merlin", 14.86, date(2026, 3, 1), "L-1", nif="B84818442"), fila_en("Proveedor Raro", 77.7, date(2026, 9, 12), "F-2")])
    assert "Nuevas</span><strong>2<" in cargar(cliente, contenido).text
    sin_elegir = cliente.get(f"{BASE}/tabla").text  # sin elegir, el trimestre de la factura más reciente (3T)
    assert "Proveedor Raro" in sin_elegir and "Leroy" not in sin_elegir and "IBERDROLA" not in sin_elegir  # el extracto de marzo no es de ese trimestre
    cliente.post(f"{BASE_T}/accion/cambiar", data={"trimestre": "2026-1"})
    primero = cliente.get(f"{BASE}/tabla").text
    assert "Leroy" in primero and "IBERDROLA CLIENT." in primero and "Proveedor Raro" not in primero
    # borrar a mano y volver a cargar el mismo Excel: la factura vuelve
    s = _sesion(cliente)
    ident = s.scalars(select(FacturaTrimestre.id).where(FacturaTrimestre.numero_factura == "L-1")).one()
    s.close()
    cliente.post(f"{BASE}/borrar", data={"ids": [f"f{ident}"]})
    assert "Leroy" not in cliente.get(f"{BASE}/tabla").text
    otra = cargar(cliente, contenido).text
    assert "Recuperadas" in otra and "Ya estaban</span><strong>1<" in otra and "Leroy" in cliente.get(f"{BASE}/tabla").text
    assert "Recuperadas" not in cargar(cliente, contenido).text  # y a la tercera ya no hay nada que recuperar


def test_un_cargo_que_paga_dos_facturas_enseña_lo_que_toca_a_cada_una(cliente):
    from datetime import date

    from test_trimestre import fila_en

    _con_socio_y_proveedor(cliente)
    importar(cliente)  # CAIXA: IBERDROLA CLIENT. -100,50 (10/03)
    cargar(cliente, excel([fila_en("Iberdrola Clientes", 60, date(2026, 3, 10), "I-1"), fila_en("Iberdrola Clientes", 40.5, date(2026, 3, 10), "I-2")]))
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Un solo cargo de 100,50 € para 2 facturas" in tabla and "60,00" in tabla and "40,50" in tabla  # el total del cargo va en el motivo; en cada fila, lo suyo


def test_los_bancos_salen_en_el_orden_que_se_les_da_en_todas_las_listas(cliente):
    from conta_pridalac.db.modelos import Banco

    _con_socio_y_proveedor(cliente)  # CAIXABANK (nº 1, de la base de pruebas) y BANCO JAVIER (nº 9)
    opciones = lambda: cliente.get("/e/prueba/2026/extractos").text  # noqa: E731
    assert opciones().index("CAIXABANK") < opciones().index("BANCO JAVIER")  # sin orden, por su número
    s = _sesion(cliente)
    javier = s.scalars(select(Banco).where(Banco.nombre == "BANCO JAVIER")).one()
    javier.orden = 1
    s.commit()
    banco_id = javier.id
    s.close()
    assert cliente.get("/e/prueba/2026/extractos").text.index("BANCO JAVIER") < cliente.get("/e/prueba/2026/extractos").text.index("CAIXABANK")  # el ordenado va primero
    assert "Orden en las listas" in cliente.get(f"/e/prueba/2026/bancos/f/{banco_id}").text
    assert cliente.get("/e/prueba/2026/cuadre-bancos").text.index("BANCO JAVIER") < cliente.get("/e/prueba/2026/cuadre-bancos").text.index("CAIXABANK")


def test_buscar_proveedor_con_texto_vacio_no_encuentra_a_nadie():
    from conta_pridalac.db.modelos import Tercero
    from conta_pridalac.web.conciliacion import _buscar_proveedor

    sin_comercial = Tercero(id=1, empresa_id=1, clase="P", nombre="UNO", comercial=None, nif=None, cuenta_id=None)
    assert _buscar_proveedor([sin_comercial], {}, "") == [] and _buscar_proveedor([sin_comercial], {}, "   ") == []
