"""Depósito de cuentas: los importes con su código de D2, los controles, el DEPOSITO.XML y la memoria, el plazo, el acuse y la pantalla."""
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from conta_pridalac.db.modelos import Acta, DepositoCuentas, Ejercicio, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import deposito_cuentas as dc
from conta_pridalac.servicios import plazos
from conta_pridalac.servicios.cierre import cerrar_ejercicio
from test_libros_oficiales import _pdf_acuse, _preparar_empresa, codigos, ej  # noqa: F401 - `ej` es una fixture
from test_web_auditoria import _sesion, cliente  # noqa: F401 - `cliente` es una fixture

D = Decimal
BASE = "/e/prueba/2026/deposito-cuentas"


def _completar_ficha(e):
    e.provincia_ine, e.municipio_ine, e.telefono, e.email, e.cnae = "28", "28065", "600 00 00 00", "sociedad@ejemplo.es", "0125"
    e.presentador_nombre, e.presentador_apellido1, e.presentador_apellido2, e.presentador_nif = "elena", "lopez", "garcia de soto", "00000014Z"
    e.presentador_domicilio, e.presentador_poblacion, e.presentador_cp, e.presentador_telefono, e.presentador_email = "Mayor 21", "Majadahonda", "28221", "600000000", "elena@ejemplo.es"


def _por_codigo(filas):
    return {f.codigo: (f.actual, f.anterior) for f in filas}


def test_los_importes_llevan_el_codigo_de_d2(sesion, ej):
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    im = dc.importes_de_las_cuentas(sesion, ej)
    por_codigo = _por_codigo(im.filas)
    # caja 5.000 + venta 1.210 − gasto 300 = 5.910; capital 5.000 y resultado 910
    assert por_codigo["10000"] == (D(5910), D(0)) and por_codigo["30000"] == (D(5910), D(0))
    assert por_codigo["12000"][0] == D(5910) and por_codigo["12700"][0] == D(5910)
    assert por_codigo["21100"][0] == D(5000) and por_codigo["21110"][0] == D(5000) and por_codigo["21700"][0] == D(910) and por_codigo["20000"][0] == D(5910)
    assert por_codigo["40100"][0] == D(1210) and por_codigo["40700"][0] == D(-300) and por_codigo["49100"][0] == D(910) and por_codigo["49500"][0] == D(910)
    assert "11000" not in por_codigo and not im.hay_anterior and im.sin_codigo == []  # lo que vale cero no se emite (salvo los dos totales del balance)
    assert all(f.confirmado for f in im.filas)


def test_los_importes_se_escriben_como_los_escribe_d2():
    assert [dc._numero(D(v)) for v in ("34580.00", "1431.80", "-49135.52", "0.00", "-0.00", "85475.59", "0.004")] == ["34580.00", "1431.80", "-49135.52", "0.00", "0.00", "85475.59", "0.00"]


def test_el_ejercicio_abierto_y_la_ficha_incompleta_se_avisan(sesion, ej):
    h = dc.controlar(sesion, ej)
    assert "ejercicio_sin_cerrar" in codigos(h, "ERROR") and "falta_dato_de_la_empresa" in codigos(h, "ERROR")  # falta el INE de la provincia
    assert {"falta_dato_del_deposito", "sin_ejercicio_anterior", "sin_periodo_medio_de_pago", "sin_fecha_de_aprobacion"} <= codigos(h, "AVISO")
    with pytest.raises(ErrorContable, match="No se puede preparar el depósito"):
        dc.preparar_deposito(sesion, ej, ".")


def test_prepara_el_zip_con_el_formulario_la_memoria_y_la_huella(sesion, ej, tmp_path):
    import base64
    import hashlib
    import zipfile

    _completar_ficha(ej.empresa)
    ej.empresa.codigo_irus = "1000000000001"
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, fecha_aprobacion=date(2026, 3, 31), pmp_actual=5, pmp_anterior=15, mujeres_organo=1, miembros_organo=2)
    assert dep.estado == "preparada" and dep.carpeta_ruta.endswith("/2025/deposito") and dep.zip_nombre == "PRUEBA_DEPOSITO_2025.zip" and dep.fecha_aprobacion == date(2026, 3, 31) and len(dep.xml_sha256) == 64
    carpeta = tmp_path / dep.carpeta_ruta
    datos_zip = (carpeta / dep.zip_nombre).read_bytes()
    assert dep.zip_huella == base64.b64encode(hashlib.sha256(datos_zip).digest()).decode() and len(dep.zip_huella) == 44  # la huella es el SHA-256 del ZIP en base64
    z = zipfile.ZipFile(carpeta / dep.zip_nombre)
    assert z.namelist() == ["DEPOSITO.xbrl", "DEPOSITO.xml", "MEMORIA.pdf"] and z.read("DEPOSITO.xbrl") == (carpeta / "DEPOSITO.xbrl").read_bytes() and z.read("DEPOSITO.xml") == (carpeta / "DEPOSITO.xml").read_bytes() and z.read("MEMORIA.pdf") == (carpeta / "MEMORIA.pdf").read_bytes()
    xbrl = ET.fromstring(z.read("DEPOSITO.xbrl"))  # XML bien formado, con los dos periodos y los importes del balance y de la cuenta de resultados
    hechos = {(e.tag.split("}")[1], e.get("contextRef")): e.text for e in xbrl.iter() if e.get("contextRef")}
    assert hechos[("TotalActivo", "I.ACTUAL")] == "5910.00" and hechos[("PatrimonioNetoPasivoTotal", "I.ACTUAL")] == "5910.00" and hechos[("PatrimonioNetoFondosPropiosCapitalEscriturado", "I.ACTUAL")] == "5000.00"
    assert hechos[("PerdidasGananciasOperacionesContinuadasImporteNetoCifraNegocios", "D.ACTUAL")] == "1210.00" and hechos[("PerdidasGananciasResultadoEjercicio", "D.ACTUAL")] == "910.00"
    assert hechos[("IdentifierValue", "D.ACTUAL")] == "B12345678" and hechos[("NumeroTotalMiembrosOrganoAdministracion", "D.ACTUAL")] == "2.00" and hechos[("PeriodoMedioPagoPeriodoMedioPagoProveedores", "D.ACTUAL")] == "5.00"
    assert hechos[("Xcode_ACC.CNAE25.0125", "D.ACTUAL")] == "0125"
    raiz = ET.fromstring(z.read("DEPOSITO.xml"))
    cabecera = {e.tag: e.text for e in raiz.find("Cabecera")}
    assert cabecera["CIF"] == "B12345678" and cabecera["RazonSocial"] == "Prueba S.L." and cabecera["TipoCuestionario"] == "Pymes" and cabecera["Ejercicio"] == "2025"
    claves = {c.find("Codigo").text: c.find("Valor").text for c in raiz.find("Claves")}
    assert [claves[k] for k in ("1010", "1008", "1024", "1025", "1031", "2014")] == ["B12345678", "1000000000001", "28221", "28", "600000000", "125"] and "2001" not in claves  # el CNAE (2014) va como en la CNAE-2025 de D2: sin el cero inicial
    assert [claves[k] for k in ("11021", "11013", "110219", "110139")] == ["2025", "31", "2024", "31"] and (claves["4212"], claves["4213"]) == ("1", "2")
    assert [claves[k] for k in ("10000", "30000", "21110", "21700", "40100", "49500")] == ["5910.00", "5910.00", "5000.00", "910.00", "1210.00", "910.00"]
    assert claves["100009"] == "0.00" and claves["300009"] == "0.00" and "110009" not in claves  # el anterior sólo lleva los totales a cero
    assert (claves["94705"], claves["947059"]) == ("5.00", "15.00")
    assert [claves[k] for k in ("8081001", "8081002", "8081003", "8081004")] == ["28065", "30001", "2001", "500001"]
    assert claves["8081201"] == "LOPEZ GARCIA DE SOTO , ELENA" and claves["8091001"] == "lopez garcia de soto , elena" and claves["8081202"] == "00000014Z"
    # los dos socios: cada uno ocupa diez códigos, con su porcentaje
    assert claves["8234001"] == "2" and [claves[k] for k in ("8230001", "8230002", "8230003", "8230004", "8230005", "8230008")] == ["lopez garcia de soto , elena", "ES", "1", "00000014Z", "14.04.1960", "60.00"]
    assert [claves[k] for k in ("8230011", "8230014", "8230018")] == ["gil navarro , pedro", "00000001R", "40.00"]
    assert not {"8081220", "8081210", "8081011", "8081012", "8080814", "1102", "2001"} & set(claves)  # firmas, adjuntos y claves de versiones antiguas: fuera
    assert len([c.find("Codigo").text for c in raiz.find("Claves")]) == len(claves)  # ningún código repetido
    assert not list(carpeta.glob("*CAC.pdf")) and dep.huella_d2 is None  # la certificación no sale hasta tener la huella que genera D2
    texto = "".join(p.extract_text() for p in PdfReader(carpeta / "MEMORIA.pdf").pages)
    for esperado in ("Memoria Ejercicio 2025", "MEMORIA ANUAL DE LA SOCIEDAD Prueba S.L.", "inscrita en el Registro Mercantil de MADRID I en tomo 30001", "Cultivo de árboles"):
        assert esperado in texto, esperado
    dep2 = dc.preparar_deposito(sesion, ej, tmp_path)  # volver a prepararlo sustituye lo anterior, conserva lo escrito y da el mismo ZIP (mismo contenido, mismas fechas)
    assert dep2.id == dep.id and dep2.pmp_actual == 5 and dep2.fecha_aprobacion == date(2026, 3, 31) and dep2.miembros_organo == 2 and dep2.zip_huella == dep.zip_huella


def test_el_acta_de_aprobacion_se_busca_en_el_ano_siguiente(sesion, ej):
    assert dc.acta_de_aprobacion(sesion, ej) is None  # la del fixture es de marzo de 2025 y aprueba las cuentas de 2024
    sesion.add(Acta(empresa_id=ej.empresa_id, numero=2, fecha=date(2026, 3, 31), clase="Ordinaria", organo="Junta General", acuerdos="Se aprueban las cuentas anuales del ejercicio 2025"))
    sesion.flush()
    assert dc.acta_de_aprobacion(sesion, ej).fecha == date(2026, 3, 31)


def test_el_plazo_es_un_mes_desde_la_aprobacion():
    assert plazos.un_mes_despues(date(2026, 12, 31)) == date(2027, 1, 31) and plazos.un_mes_despues(date(2027, 1, 31)) == date(2027, 2, 28)
    assert plazos.fin_del_deposito(2026, None) == date(2027, 7, 30)  # viernes
    assert plazos.fin_del_deposito(2026, date(2027, 3, 31)) == date(2027, 4, 30)
    assert plazos.fin_del_deposito(2026, date(2027, 1, 31)) == date(2027, 3, 1)  # el 28 de febrero es domingo


def _pdf_deposito(referencia="28065B1234567820250", fecha="13/07/2026"):
    return _pdf_acuse(referencia=referencia, fecha=fecha, entrada="2026 / 2 / 657403")


def test_registrar_el_envio_con_el_acuse(sesion, ej, tmp_path):
    dep = dc.registrar_envio(sesion, ej, tmp_path, pdf_acuse=_pdf_deposito())
    assert dep.estado == "enviada" and dep.enviado_en == date(2026, 7, 13) and dep.referencia == "28065B1234567820250" and dep.numero_entrada == "2026 / 2 / 657403"
    assert (tmp_path / dep.acuse_ruta).read_bytes().startswith(b"%PDF") and dep.acuse_ruta.endswith("28065B1234567820250_Acuse_Entrada.pdf")
    assert "ya_enviado" in codigos(dc.controlar(sesion, ej, dep), "ERROR")
    # una subsanación lleva el sufijo _SUBSANACION y vale igual
    assert dc.registrar_envio(sesion, ej, tmp_path, pdf_acuse=_pdf_deposito(referencia="28065B1234567820250_SUBSANACION")).referencia == "28065B1234567820250_SUBSANACION"


def test_el_acuse_de_otro_ejercicio_o_el_futuro_no_valen(sesion, ej, tmp_path):
    with pytest.raises(ErrorContable, match="otro ejercicio o de otra empresa"):
        dc.registrar_envio(sesion, ej, tmp_path, pdf_acuse=_pdf_deposito(referencia="28065B1234567820240"))
    with pytest.raises(ErrorContable, match="futura"):
        dc.registrar_envio(sesion, ej, tmp_path, fecha=date(2999, 1, 1), referencia="28065B1234567820250")
    with pytest.raises(ErrorContable, match="Falta la fecha"):
        dc.registrar_envio(sesion, ej, tmp_path)
    assert dc.registrar_envio(sesion, ej, ".", fecha=date(2026, 7, 13)).acuse_ruta is None  # sin PDF basta la fecha


def test_el_plazo_del_deposito_avisa_y_se_calla_al_registrar_el_envio(sesion, ej, monkeypatch):
    from conta_pridalac.servicios.vigilancia import plazos_de_modelos

    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.PRIMER_EJERCICIO_DEPOSITO", 2025)

    def del_deposito(dia):
        return [h for h in plazos_de_modelos(sesion, ej, dia) if h.referencia == "depósito 2025"]

    assert del_deposito(date(2026, 5, 30)) == []  # el plazo general acaba el 30 de julio: el aviso empieza dos meses antes
    (h,) = del_deposito(date(2026, 6, 1))
    assert (h.codigo, h.gravedad) == ("plazo_deposito_proximo", "AVISO") and "30/07/2026" in h.mensaje and "sin empezar" in h.mensaje
    assert del_deposito(date(2026, 7, 27))[0].codigo == "plazo_deposito_ultima_semana"
    (h,) = del_deposito(date(2026, 8, 3))
    assert h.codigo == "plazo_deposito_vencido" and "hace 4 día(s)" in h.mensaje
    sesion.add(DepositoCuentas(empresa_id=ej.empresa_id, anio=2025, fecha_aprobacion=date(2026, 3, 31)))  # aprobadas el 31/03: el plazo acaba el 30/04
    sesion.flush()
    assert del_deposito(date(2026, 2, 27)) == [] and del_deposito(date(2026, 3, 1))[0].codigo == "plazo_deposito_proximo"
    dc.registrar_envio(sesion, ej, ".", fecha=date(2026, 4, 20), referencia="28065B1234567820250")
    assert del_deposito(date(2026, 8, 3)) == []


def test_el_asistente_del_2t_pide_depositar_las_cuentas_del_ano_anterior(sesion, ej, monkeypatch, tmp_path):
    from conta_pridalac.servicios import asistente_trimestre as asistente

    monkeypatch.setattr("conta_pridalac.servicios.asistente_trimestre.PRIMER_EJERCICIO_DEPOSITO", 2025)
    ej26 = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=ej.empresa)
    sesion.add(ej26)
    sesion.flush()

    def paso(periodo):
        return [p for p in asistente.pasos(sesion, ej.empresa, ej26, periodo, "Sin presentar", "Sin presentar") if "Depositar las cuentas" in p.titulo]

    assert paso((date(2026, 1, 1), date(2026, 3, 31))) == []  # sólo en el segundo trimestre
    (p,) = paso((date(2026, 4, 1), date(2026, 6, 30)))
    assert (p.estado, p.pantalla) == ("pendiente", "deposito-cuentas") and "cuentas de 2025" in p.titulo and "sin preparar" in p.detalle
    dc.registrar_envio(sesion, ej, tmp_path, fecha=date(2026, 7, 13), referencia="28065B1234567820250")
    (p,) = paso((date(2026, 4, 1), date(2026, 6, 30)))
    assert p.estado == "hecho" and "13/07/2026" in p.detalle


def test_la_pantalla_prepara_el_deposito_y_registra_el_envio(cliente):
    _preparar_empresa(cliente)
    s = _sesion(cliente)
    _completar_ficha(s.scalar(select(Empresa)))
    s.commit()
    s.close()
    assert cliente.get(BASE).status_code == 200 and "Depósito de cuentas" in cliente.get("/e/prueba/2026").text
    assert "Sin preparar" in cliente.get(f"{BASE}/tabla").text
    ficha = cliente.get(f"{BASE}/f/2026").text
    assert "Importes que van al formulario de D2" in ficha and "Periodo medio de pago" in ficha and "Sin errores" not in ficha  # faltan datos: avisos
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "preparar", "fecha_formulacion": "20/02/2027", "fecha_aprobacion": "31/03/2027", "pmp_actual": "5", "pmp_anterior": "15", "mujeres_organo": "1", "miembros_organo": "2"})
    assert r.status_code == 200 and "DEPOSITO.xml" in r.text and "MEMORIA.pdf" in r.text and "EMPRESA_DE_PRUEBA_DEPOSITO_2026.zip" in r.text and "Huella de D2 y certificación para firmar" in r.text
    s = _sesion(cliente)
    dep = s.scalar(select(DepositoCuentas))
    assert dep.anio == 2026 and dep.fecha_aprobacion == date(2027, 3, 31) and dep.fecha_formulacion == date(2027, 2, 20) and (dep.pmp_actual, dep.pmp_anterior) == (5, 15)
    xml = cliente.get(f"{BASE}/{dep.id}/doc/xml")
    assert xml.status_code == 200 and b"<Esquema" in xml.content and "attachment" in xml.headers["content-disposition"]
    zip_ = cliente.get(f"{BASE}/{dep.id}/doc/zip")
    assert zip_.status_code == 200 and zip_.content.startswith(b"PK")
    assert cliente.get(f"{BASE}/{dep.id}/doc/cac").status_code == 404  # sin la huella de D2 no hay certificación
    memoria = cliente.get(f"{BASE}/{dep.id}/doc/memoria")
    assert memoria.status_code == 200 and memoria.content.startswith(b"%PDF") and memoria.headers["content-type"] == "application/pdf"
    assert cliente.get(f"{BASE}/{dep.id}/doc/acuse").status_code == 404 and cliente.get(f"{BASE}/{dep.id}/doc/otro").status_code == 404
    s.close()
    assert "Preparado" in cliente.get(f"{BASE}/tabla").text
    destino = cliente.app.state.config.descargas / "Registro Mercantil"
    cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "copiar_zip"})
    assert (destino / "EMPRESA_DE_PRUEBA_DEPOSITO_2026.zip").read_bytes() == zip_.content  # el ZIP va a la subcarpeta «Registro Mercantil» de las descargas
    sin = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "copiar_cac"})
    assert "registre antes la huella" in sin.text and not (destino / "28065B1234567820260.CAC.pdf").exists()
    mala = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "registrar_huella", "huella_d2": "no es una huella"})
    assert "No encuentro la huella" in mala.text
    ok = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "registrar_huella", "huella_d2": "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw="})
    assert ok.status_code == 200 and "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=" in ok.text and "para firmarla digitalmente" in ok.text
    s = _sesion(cliente)
    dep = s.scalar(select(DepositoCuentas))
    assert dep.huella_d2 == "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw="
    cac = cliente.get(f"{BASE}/{dep.id}/doc/cac")
    assert cac.status_code == 200 and cac.content.startswith(b"%PDF") and cac.headers["content-type"] == "application/pdf"
    s.close()
    cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "copiar_cac"})
    assert (destino / "28065B1234567820260.CAC.pdf").read_bytes() == cac.content or any(destino.glob("*CAC.pdf"))
    r = cliente.post(f"{BASE}/guardar", data={"id": "2026", "accion": "registrar_envio"}, files={"acuse": ("acuse.pdf", _pdf_deposito(referencia="28065B1234567820260", fecha="13/07/2026"), "application/pdf")})
    assert r.status_code == 200 and "Depositado el" in r.text and "13/07/2026" in r.text and "Ver el acuse (PDF)" in r.text
    s = _sesion(cliente)
    dep = s.scalar(select(DepositoCuentas))
    assert dep.estado == "enviada" and dep.numero_entrada == "2026 / 2 / 657403"
    assert cliente.get(f"{BASE}/{dep.id}/doc/acuse").content.startswith(b"%PDF")
    s.close()
    assert "Depositado" in cliente.get(f"{BASE}/tabla").text


def test_los_desgloses_van_en_el_xbrl_con_el_espacio_de_nombres_que_reconoce_d2(sesion, ej, tmp_path):
    from conta_pridalac.db.modelos import Cuenta
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento

    for codigo, nombre in (("17000000", "DEUDAS A LARGO PLAZO"), ("41000000", "ACREEDORES"), ("43000000", "CLIENTES")):
        sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=codigo, nombre=nombre))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=3, fecha=date(2025, 9, 1), concepto="Préstamo", lineas=[LineaAsiento("57200001", D(1000)), LineaAsiento("17000000", D(-1000))])
    grabar_asiento(sesion, ej, tipo=4, numero=4, fecha=date(2025, 9, 2), concepto="Factura", lineas=[LineaAsiento("62900000", D(200)), LineaAsiento("41000000", D(-200))])
    grabar_asiento(sesion, ej, tipo=4, numero=5, fecha=date(2025, 9, 3), concepto="Venta", lineas=[LineaAsiento("43000000", D(300)), LineaAsiento("70000000", D(-300))])
    _completar_ficha(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    assert "xbrl_sin_elemento" not in codigos(dc.controlar(sesion, ej))
    dep = dc.preparar_deposito(sesion, ej, tmp_path)
    xbrl = (tmp_path / dep.carpeta_ruta / "DEPOSITO.xbrl").read_text(encoding="utf-8")
    # «otros acreedores» y «otras deudas»: espacio pgc-07-c-ap (con pgc-07-c-bs, D2 los deja en blanco y salta el cuadre); el resto, pgc-07-c-bs
    assert '<pgc-07-c-ap:PasivoCorrienteAcreedoresComercialesOtrasCuentasPagarOtrosAcreedores decimals="0" contextRef="I.ACTUAL" unitRef="euro">200.00<' in xbrl
    assert '<pgc-07-c-bs:PasivoNoCorrienteDeudasLargoPlazoDeudasEntidadesCredito decimals="0" contextRef="I.ACTUAL" unitRef="euro">1000.00<' in xbrl
    assert '<pgc-07-c-bs:ActivoCorrienteDeudoresComercialesOtrasCuentasCobrarClientesVentasPrestacionesServicios' in xbrl and "pgc-07-c-bs:PasivoCorrienteAcreedoresComercialesOtrasCuentasPagarOtrosAcreedores" not in xbrl
    claves = {c.find("Codigo").text: c.find("Valor").text for c in ET.fromstring((tmp_path / dep.carpeta_ruta / "DEPOSITO.xml").read_bytes()).find("Claves")}
    assert claves["32590"] == "200.00" and claves["32500"] == "200.00"
    assert claves["1901"] == str(len(PdfReader(tmp_path / dep.carpeta_ruta / "MEMORIA.pdf").pages) + 1)  # nº de páginas presentadas: la memoria y la certificación (PID_023)


def test_el_organo_del_ano_anterior_se_completa_con_el_actual_y_la_certificacion_lleva_la_huella(sesion, ej, tmp_path):
    _completar_ficha(ej.empresa)
    ej.empresa.forma_administracion = "Administradores solidarios"
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, fecha_aprobacion=date(2026, 3, 31), fecha_formulacion=date(2026, 3, 31), mujeres_organo=1, miembros_organo=2)
    with pytest.raises(ErrorContable, match="No encuentro la huella"):
        dc.registrar_huella(sesion, ej, tmp_path, huella="12345")
    dc.registrar_huella(sesion, ej, tmp_path, huella="OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=")
    claves = {c.find("Codigo").text: c.find("Valor").text for c in ET.fromstring((tmp_path / dep.carpeta_ruta / "DEPOSITO.xml").read_bytes()).find("Claves")}
    assert (claves["42129"], claves["42139"]) == ("1", "2") and (claves["4212"], claves["4213"]) == ("1", "2")  # PID_044 y PID_046
    cac = tmp_path / dep.carpeta_ruta / dc.nombre_de_la_certificacion(ej.empresa, 2025)
    assert len(PdfReader(cac).pages) == 1  # cabe en una página (se cuenta como una al sumar las páginas presentadas)
    texto = " ".join("".join(p.extract_text() for p in PdfReader(cac).pages).split())
    for esperado in ("JUNTA UNIVERSAL. CUENTAS PYME", "administradores solidarios de la sociedad Prueba S.L.", "C.I.F. B12345678", "31/03/2026 y en Majadahonda", "APROBAR LAS CUENTAS ANUALES correspondientes al ejercicio 2025 cerrado el 31/12/2025",
                     "A reserva legal", "910,00", "huella digital siguiente: OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=", "formuladas el día 31/03/2026", "00000014Z"):
        assert esperado in texto, esperado
    assert "no ha hecho uso de la previsión de reformulación" in texto and "Real Decreto-ley 4/2025" in texto  # Resolución DGSJFP de 19/05/2026, apartado segundo


def test_la_certificacion_dice_si_se_uso_la_reformulacion_del_rdl_4_2025(sesion, ej, tmp_path):
    _completar_ficha(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, fecha_aprobacion=date(2026, 3, 31), mujeres_organo=1, miembros_organo=2, cierre={"reformulacion": "1"})
    dc.registrar_huella(sesion, ej, tmp_path, huella="OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=")
    cac = tmp_path / dep.carpeta_ruta / dc.nombre_de_la_certificacion(ej.empresa, 2025)
    texto = " ".join("".join(p.extract_text() for p in PdfReader(cac).pages).split())
    assert "SÍ ha hecho uso de la previsión de reformulación" in texto and len(PdfReader(cac).pages) == 1


def test_con_perdidas_la_certificacion_las_compensa_con_futuros_beneficios(sesion, ej, tmp_path):
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento

    grabar_asiento(sesion, ej, tipo=4, numero=9, fecha=date(2025, 11, 1), concepto="Gasto grande", lineas=[LineaAsiento("62900000", D(3000)), LineaAsiento("57200001", D(-3000))])
    _completar_ficha(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, fecha_aprobacion=date(2026, 3, 31), mujeres_organo=1, miembros_organo=2)
    dc.registrar_huella(sesion, ej, tmp_path, huella="OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=")
    texto = " ".join("".join(p.extract_text() for p in PdfReader(tmp_path / dep.carpeta_ruta / dc.nombre_de_la_certificacion(ej.empresa, 2025)).pages).split())
    assert "pérdidas obtenidas durante el ejercicio 2025, con un importe de 2.090,00€" in texto and "compensarse con futuros beneficios" in texto


def test_los_datos_de_cierre_se_guardan_y_lo_que_iguala_la_propuesta_no(sesion, ej, tmp_path):
    _completar_ficha(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, mujeres_organo=1, miembros_organo=2, solo_guardar=True,
                               cierre={"medio_fijo": "2", "reserva_legal": "910.00", "lei": "ABC123", "participaciones": "5000", "fecha_emision": "02/04/2026"})
    guardado = dc.cierre_guardado(dep)
    assert guardado == {"medio_fijo": "2", "lei": "ABC123", "fecha_emision": "02/04/2026"} and dep.zip_nombre is None  # sólo guardado: sin ZIP; reserva legal y participaciones coinciden con la propuesta
    assert dc.cierre_efectivo(sesion, ej, dep)["reserva_legal"] == "910.00" and dc.cierre_efectivo(sesion, ej, dep)["participaciones"] == "5000" and dc.total_aplicacion(dc.cierre_efectivo(sesion, ej, dep)) == D("910.00")
    with pytest.raises(ErrorContable, match="no es un importe"):
        dc.preparar_deposito(sesion, ej, tmp_path, cierre={"medio_fijo": "dos"})


def test_la_huella_se_lee_del_pdf_o_del_txt_de_d2_y_si_cambia_el_zip_deja_de_valer(sesion, ej, tmp_path):
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    lienzo = canvas.Canvas(buf)
    lienzo.drawString(50, 800, "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=")
    lienzo.save()
    assert dc.leer_huella(pdf_o_txt=buf.getvalue()) == "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=" and dc.leer_huella(pdf_o_txt=b"OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=") == "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw="
    _completar_ficha(ej.empresa)
    cerrar_ejercicio(sesion, ej, abrir_siguiente=False, exigir_auditoria=False)
    dep = dc.preparar_deposito(sesion, ej, tmp_path, fecha_aprobacion=date(2026, 3, 31), mujeres_organo=1, miembros_organo=2)
    dc.registrar_huella(sesion, ej, tmp_path, pdf_o_txt=buf.getvalue())
    cac = tmp_path / dep.carpeta_ruta / dc.nombre_de_la_certificacion(ej.empresa, 2025)
    assert dep.huella_d2 == "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=" and cac.exists()
    dc.preparar_deposito(sesion, ej, tmp_path)  # mismo contenido: la huella sigue valiendo
    assert dep.huella_d2 == "OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=" and cac.exists()
    dc.preparar_deposito(sesion, ej, tmp_path, miembros_organo=3)  # cambia el XBRL y el XML: el ZIP es otro y la huella de D2 ya no vale
    assert dep.huella_d2 is None and not cac.exists()


def test_solo_los_titulares_con_mas_del_25_por_ciento_van_al_formulario_y_el_beneficio_lleva_su_base_de_reparto(sesion, ej):
    from conta_pridalac.exportacion.libros_pdf import SocioLibro

    def socio(nif, nombre, pct):
        return SocioLibro(nif=nif, nombre=nombre, nacionalidad="ESPAÑA", nacimiento="", domicilio="", poblacion="", provincia="", profesion="", estado_civil="", movimientos=[],
                          total_participaciones=1, total_importe=Decimal(1), porcentaje=Decimal(pct))

    importes = dc.importes_de_las_cuentas(sesion, ej)
    socios = [socio("00000014Z", "Lopez, Elena", "64.00"), socio("00000002W", "Ortega, Ana", "12.00"), socio("00000003A", "Ortega, Lucía", "12.00"), socio("00000004G", "Ortega, Eva", "12.00")]
    claves = dict(dc.claves_del_formulario(ej.empresa, ej, importes, socios=socios, aplicacion=Decimal("1038.90")))
    assert claves["8234001"] == "1" and "8230011" not in claves and "8230111" not in claves  # las de 12 % no van (PTR_0928, PTR_0975…)
    resultado = next(f for f in importes.filas if f.id == "D" and f.es_pyg)
    if resultado.actual > 0:
        assert claves["91000"] == claves["91004"] == dc._numero(resultado.actual) and claves["91012"] == "1038.90"
    else:
        assert "91000" not in claves  # con pérdida la base de reparto va vacía (PID_034)


def test_con_beneficio_el_xbrl_lleva_la_base_de_reparto_y_su_aplicacion(sesion, ej):
    importes = dc.importes_de_las_cuentas(sesion, ej)
    resultado = next(f for f in importes.filas if f.id == "D" and f.es_pyg)
    cierre = {"reserva_legal": "100.00", "reservas_voluntarias": "50.50", "reparto_remanente": "10.00"}
    elementos = {(n, c): v for n, c, v in dc.elementos_de_aplicacion(importes, cierre)}
    if resultado.actual > 0:
        assert elementos[("BaseRepartoResultadoSaldoCuentaPerdidasGanancias", "D.ACTUAL")] == resultado.actual
        assert elementos[("BaseTotalBaseRepartoResultadoTotalAplicacion", "D.ACTUAL")] == resultado.actual + 10
        assert elementos[("PropuestaAplicacionATotalAplicacionTotalBaseReparto", "D.ACTUAL")] == Decimal("150.50")
        assert elementos[("PropuestaResultadoAplicacionAReservaLegal", "D.ACTUAL")] == Decimal("100.00")
    else:
        assert not [k for k in elementos if k[1] == "D.ACTUAL"]  # con pérdida no se escribe la base de reparto (PID_034)
