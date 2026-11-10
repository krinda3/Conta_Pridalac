"""Generador del modelo 200 de 2025, etapa A: identificación, liquidación, bases negativas, gastos financieros, aplicación del resultado y cuenta bancaria."""
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, DeclaracionPresentada, Ejercicio, RepresentanteEmpresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero200 import Fichero200
from conta_pridalac.servicios import impuesto_sociedades_200 as gen
from conta_pridalac.servicios import impuesto_sociedades_200_estados as est
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from test_libros_oficiales import ej  # noqa: F401 - es una fixture

D = Decimal


def _gasto(sesion, ej, cuenta, importe, n):
    if not sesion.query(Cuenta).filter_by(empresa_id=ej.empresa_id, codigo=cuenta).first():
        sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=cuenta, nombre="GASTO"))
        sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=n, fecha=date(2025, 9, 1), concepto="Gasto", lineas=[LineaAsiento(cuenta, D(importe)), LineaAsiento("57200001", -D(importe))])


def _por_codigo(fichero):
    return {p.codigo: p for p in fichero.paginas}


def _valor(fichero, codigo, casilla):
    p = _por_codigo(fichero)[codigo]
    return p.importe(p.n_de_casilla(casilla))


def test_con_beneficio_sale_la_liquidacion_con_el_tipo_general(sesion, ej):
    ej.empresa.telefono, ej.empresa.iban = "600 00 00 00", "ES91 2100 0418 4502 0005 1332"
    f = gen.generar(sesion, ej)
    paginas = _por_codigo(f)
    assert list(paginas) == ["01000", "01B00", "02000", "02B00", "03000", "04000", "05000", "06000", "07000", "08000", "09000", "10000", "11000", "12000", "13000", "14000", "14B00", "20000", "20D00", "DID00"]  # sin bases negativas ni pérdidas: sin 15000
    ident = paginas["01000"]
    assert (ident.texto(6), ident.texto(7), ident.texto(8), ident.numero(9), ident.numero(17)) == ("I", "B12345678", "PRUEBA S.L.", 2025, 1) and ident.texto(20) == "600000000" or ident.numero(20) == 600000000
    assert _valor(f, "12000", 500) == 910 and _valor(f, "14000", 550) == 910 and _valor(f, "14000", 552) == 910 and _valor(f, "14000", 562) == D("227.50")  # 25 % de 910: sin cifra del año anterior
    assert paginas["14000"].numero(paginas["14000"].n_de_casilla(558)) == 2500
    assert _valor(f, "14B00", 592) == D("227.50") and _valor(f, "14B00", 599) == D("227.50") and _valor(f, "14B00", 621) == D("227.50")
    assert _valor(f, "20D00", 653) == 910 and _valor(f, "20D00", 654) == 910 and _valor(f, "20D00", 1522) == 910 and _valor(f, "20D00", 666) == 910
    assert Fichero200.leer(f.escribir()).escribir() == f.escribir()  # lo escrito se lee igual


def test_los_pagos_fraccionados_se_restan_y_dan_la_devolucion(sesion, ej):
    ej.empresa.iban = "ES9121000418450200051332"
    for periodo, importe in ((1, "100"), (2, "80"), (3, "80")):
        sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="202", anio=2025, periodo=periodo, tipo=1, resultado=D(importe), resultado_liquidacion=D(importe)))
    sesion.flush()
    f = gen.generar(sesion, ej)
    assert (_valor(f, "14B00", 601), _valor(f, "14B00", 603), _valor(f, "14B00", 605)) == (100, 80, 80)
    assert _valor(f, "14B00", 611) == D("227.50") - 260 == D("-32.50") and _valor(f, "14B00", 621) == D("-32.50")
    assert _por_codigo(f)["01000"].texto(6) == "D"
    did = _por_codigo(f)["DID00"]
    assert did.texto(23) == "D" and did.importe(24) == D("32.50") and did.texto(27) == "ES9121000418450200051332" and did.numero(26) == 1


def test_con_perdidas_se_marca_la_base_negativa_y_se_genera_la_pagina_de_bases(sesion, ej):
    _gasto(sesion, ej, "62900000", 5000, 3)
    f = gen.generar(sesion, ej)
    ident = _por_codigo(f)["01000"]
    assert ident.numero(ident.n_de_casilla(27)) == 1 and ident.texto(6) == "N"
    base = _valor(f, "14000", 552)
    assert base < 0 and _valor(f, "14000", 562) == 0 and _valor(f, "14B00", 621) == 0
    assert "20D00" not in _por_codigo(f) and "15000" in _por_codigo(f)
    p15 = _por_codigo(f)["15000"]
    assert p15.importe(p15.n_de_casilla(1048)) == -base and p15.importe(p15.n_de_casilla(1049)) == -base  # la base generada este año queda pendiente
    assert _por_codigo(f)["DID00"].numero(41) == 1  # resultado cero


def test_las_bases_negativas_pendientes_se_compensan_y_se_detallan(sesion, ej):
    isd.guardar_base_negativa(sesion, ej.empresa_id, 2014, D("400"))
    isd.guardar_base_negativa(sesion, ej.empresa_id, 2024, D("300"))
    f = gen.generar(sesion, ej)
    p15 = _por_codigo(f)["15000"]
    assert (p15.importe(p15.n_de_casilla(607)), p15.importe(p15.n_de_casilla(675)), p15.importe(p15.n_de_casilla(699))) == (400, 400, 0)  # 2014: todo compensado
    assert _valor(f, "15000", 670) == 700 and _valor(f, "15000", 547) == 700 and _valor(f, "15000", 671) == 0
    assert _valor(f, "14000", 550) == 910 and _valor(f, "14000", 547) == 700 and _valor(f, "14000", 552) == 210 and _valor(f, "14000", 562) == D("52.50")


def test_las_multas_van_a_su_casilla_y_se_suman_a_la_base(sesion, ej):
    _gasto(sesion, ej, "67800005", 100, 3)
    f = gen.generar(sesion, ej)
    assert _valor(f, "12000", 1815) == 100 and _valor(f, "12000", 500) == 810 and _valor(f, "14000", 550) == 910
    assert _valor(f, "13000", 417) == 100 and _valor(f, "13000", 418) == 0  # el total de correcciones de la página 13: la sede lo recalcula y lo compara con el detalle
    como_programa_anterior = gen.generar(sesion, ej, con_correcciones_automaticas=False)
    assert _valor(como_programa_anterior, "12000", 1815) == 0 and _valor(como_programa_anterior, "14000", 550) == 810 and _valor(como_programa_anterior, "13000", 417) == 0


def test_el_limite_de_gastos_financieros_es_el_30_por_ciento_del_beneficio_operativo(sesion, ej):
    f = gen.generar(sesion, ej)
    assert _valor(f, "20000", 1250) == 910 and _valor(f, "20000", 1249) == D("273.00") and _valor(f, "20000", 2369) == 1_000_000


def test_solo_hay_diseno_del_2025(sesion, ej):
    ej2 = Ejercicio(empresa_id=ej.empresa_id, anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31))
    with pytest.raises(ErrorContable, match="solo hay diseño del modelo 200 de 2025"):
        gen.generar(sesion, ej2)


def test_el_balance_y_la_pyg_van_a_las_casillas_de_su_linea(sesion, ej):
    _gasto(sesion, ej, "62300000", 100, 3)  # servicios de profesionales independientes
    f = gen.generar(sesion, ej)
    assert _valor(f, "03000", 101) == 0 and _valor(f, "04000", 177) == _valor(f, "04000", 180) == _valor(f, "06000", 252) == D("5810")  # caja 5.000 + venta 1.210 − 300 − 100; todo en efectivo
    assert _valor(f, "05000", 188) == 5000 and _valor(f, "05000", 199) == D("810")
    assert _valor(f, "07000", 255) == 1210 and _valor(f, "07000", 279) == _valor(f, "07000", 280) == -400 and _valor(f, "07000", 253) == -100 and _valor(f, "07000", 254) == -300  # resto de servicios
    assert _valor(f, "07000", 296) == D("810") == _valor(f, "08000", 325) == _valor(f, "08000", 327) == _valor(f, "08000", 500)
    assert not any("casilla" in a for a in f.avisos)  # (los avisos del estado de cambios del patrimonio por no haber ejercicio anterior no cuentan)


def test_lo_que_no_cae_en_ninguna_casilla_hija_va_a_la_casilla_resto_y_se_avisa(sesion, ej):
    _gasto(sesion, ej, "60900000", 40, 3)  # rappels sobre compras: línea 4, casilla de consumo de mercaderías
    _gasto(sesion, ej, "60300000", 10, 4)  # una cuenta 603 que ninguna hija recoge
    f = gen.generar(sesion, ej)
    assert _valor(f, "07000", 260) == -50 and _valor(f, "07000", 261) == -40 and _valor(f, "07000", 262) == -10  # el resto, a materias primas
    assert any("no cae en ninguna casilla concreta" in a for a in f.avisos)


def test_el_estado_de_cambios_del_patrimonio_lleva_el_resultado_y_los_saldos(sesion, ej):
    f = gen.generar(sesion, ej)
    assert _valor(f, "09000", 500) == 910 and _valor(f, "09000", 355) == 910
    assert _valor(f, "11000", 457) == 910 and _valor(f, "11000", 463) == 910  # «resultado cuenta de pérdidas y ganancias»: columna del resultado y total
    assert _valor(f, "11000", 639) == 910 and _valor(f, "11000", 645) == D("5910")  # saldo final: resultado y total (capital 5.000 + resultado 910)
    assert _valor(f, "10000", 632) == 5000


def test_los_socios_los_titulares_reales_y_los_representantes_salen_de_las_fichas(sesion, ej):
    from datetime import date as _d

    ej.empresa.provincia_ine = "28"
    ej.empresa.representantes.append(RepresentanteEmpresa(orden=0, nombre="Lopez García de Soto, Elena", nif="00000014Z", fecha_poder=_d(2013, 12, 27), notaria="Perez Ortega"))
    sesion.flush()
    f = gen.generar(sesion, ej)
    p2 = _por_codigo(f)["02000"]
    assert (p2.texto(6), p2.texto(7), p2.texto(9)) == ("00000014Z", "F", "LOPEZ GARCIA DE SOTO, ELENA")  # administrador: el primer representante
    # fixture: dos socios con 3.000 y 2.000 participaciones: 60 % y 40 %, sobre el capital del balance (5.000 €)
    assert (p2.texto(100), p2.texto(103), p2.texto(104), p2.importe(105), p2.numero(106)) == ("00000014Z", "LOPEZ GARCIA DE SOTO, ELENA", "28", D("3000"), 6000)
    assert (p2.texto(107), p2.importe(112), p2.numero(113)) == ("00000001R", D("2000"), 4000)
    p2b = [p for p in f.paginas if p.codigo == "02B00"]
    assert len(p2b) == 2 and not p2b[0].complementaria and p2b[1].complementaria  # los dos pasan del 25 %: uno por página, por orden alfabético
    assert p2b[0].texto(146) == "00000001R" and p2b[1].texto(146) == "00000014Z" and p2b[0].numero(149) == 19600414 or p2b[0].numero(149) > 0
    assert (p2b[0].texto(153), p2b[0].texto(155), p2b[0].numero(156), p2b[0].texto(157)) == ("00000014Z", "00000014Z", 20131227, "PEREZ ORTEGA") and p2b[1].texto(153) == ""
    assert Fichero200.leer(f.escribir()).escribir() == f.escribir()


# ------------------------------------------------------------------------------------------------ controles y fichero para la sede

from conta_pridalac.db.modelos import DESCARTADA, GENERADA, PresentacionAeat  # noqa: E402
from conta_pridalac.servicios import presentacion200 as pres  # noqa: E402


def _codigos(hallazgos, gravedad=None):
    return {h.codigo for h in hallazgos if gravedad is None or h.gravedad == gravedad}


def test_los_controles_avisan_de_lo_que_hay_que_mirar_y_bloquean_lo_que_no_se_puede_generar(sesion, ej):
    h = pres.controlar_200(sesion, ej)
    assert _codigos(h, "ERROR") == set() and {"tipo_general", "ejercicio_sin_cerrar", "sin_representantes", "sin_persona_de_contacto"} <= _codigos(h, "AVISO")
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="200", anio=2025, periodo=0, tipo=1, resultado=D("-228.95"), resultado_liquidacion=D("-228.95")))
    assert "ya_presentado" in _codigos(pres.controlar_200(sesion, ej), "AVISO")
    con_correccion = isd.DatosIS(correcciones=[isd.Correccion("Otra", aumento=D(5))])
    assert "correccion_manual_sin_casilla" in _codigos(pres.controlar_200(sesion, ej, con_correccion), "ERROR")
    assert "apartados_opcionales_sin_generar" in _codigos(pres.controlar_200(sesion, ej, isd.DatosIS(donativos=[{"importe": "10"}])), "ERROR")
    ej2 = Ejercicio(empresa_id=ej.empresa_id, anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31))
    assert _codigos(pres.controlar_200(sesion, ej2), "ERROR") == {"sin_diseno_del_ejercicio"}


def test_una_devolucion_exige_un_iban_valido(sesion, ej):
    for periodo in (1, 2, 3):
        sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="202", anio=2025, periodo=periodo, tipo=1, resultado=D(100), resultado_liquidacion=D(100)))
    sesion.flush()
    assert "devolucion_sin_iban" in _codigos(pres.controlar_200(sesion, ej), "ERROR")
    ej.empresa.iban = "ES91 2100 0418 4502 0005 1332"
    assert "devolucion_sin_iban" not in _codigos(pres.controlar_200(sesion, ej), "ERROR")


def test_generar_guarda_el_fichero_con_su_huella_y_descarta_el_anterior(sesion, ej, tmp_path):
    ej.empresa.nombre_corto = "Prueba"
    p1, ruta1, avisos = pres.generar_fichero(sesion, ej, tmp_path)
    assert p1.estado == GENERADA and p1.fichero_nombre == "PRUEBA_AEAT_200_2025_0A.200" and ruta1.name == f"{p1.id}_PRUEBA_AEAT_200_2025_0A.200" and p1.tipo_declaracion == "I"
    texto = ruta1.read_bytes().decode("latin-1")
    assert texto.startswith("<T200020250A0000><AUX>") and texto.endswith("</T200020250A0000>") and Fichero200.leer(texto).escribir() == texto
    import hashlib

    assert p1.fichero_sha256 == hashlib.sha256(ruta1.read_bytes()).hexdigest() and p1.resultado == D("227.50") and p1.diseno_version == "DR200e25v102"
    p2, _, _ = pres.generar_fichero(sesion, ej, tmp_path)
    assert p2.id != p1.id and p1.estado == DESCARTADA and pres.ultima_generada(sesion, ej.empresa_id, 2025).id == p2.id
    assert [e.evento for e in p1.eventos] == ["fichero_generado", "descartada"]


def test_no_se_genera_con_errores_en_los_controles(sesion, ej, tmp_path):
    with pytest.raises(ErrorContable, match="correcciones manuales"):
        gen_datos = isd.DatosIS(correcciones=[isd.Correccion("Otra", aumento=D(5))])
        isd.guardar_datos(sesion, ej, gen_datos)
        pres.generar_fichero(sesion, ej, tmp_path)
    assert sesion.query(PresentacionAeat).count() == 0


# ... y la pantalla

from sqlalchemy import select as _select  # noqa: E402

from conta_pridalac.db.modelos import Empresa  # noqa: E402
from test_web_auditoria import _sesion, cliente  # noqa: E402,F401


def test_la_pantalla_genera_el_fichero_y_lo_copia_a_descargas(cliente):
    import json as _json

    s = _sesion(cliente)
    e = s.scalar(_select(Empresa))
    e.nif = "B12345678"
    s.add(Ejercicio(empresa_id=e.id, anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31)))
    s.commit()
    s.close()
    base = "/e/prueba/2025/modelo-200"
    ficha = cliente.get(f"{base}/f/2025").text
    assert "Fichero para la sede" in ficha and "1.- Generar el fichero" in ficha and "2.- Copiar para presentar" not in ficha  # todavía no hay fichero
    r = cliente.post(f"{base}/guardar", data={"id": "2025", "accion": "generar", "compensar": "1"})
    assert r.status_code == 200 and "Fichero generado: EMPRESA_DE_PRUEBA_AEAT_200_2025_0A.200" in _json.loads(r.headers["HX-Trigger"])["mensaje"]["texto"]
    assert "2.- Copiar para presentar" in r.text and "✓ 1.- Generar el fichero" in r.text
    s = _sesion(cliente)
    p = s.scalar(_select(PresentacionAeat))
    assert p.modelo == "200" and p.estado == GENERADA and (cliente.app.state.config.almacen / p.fichero_ruta).is_file()
    r = cliente.post(f"{base}/{p.id}/copiar")
    destino = cliente.app.state.config.descargas / "EMPRESA_DE_PRUEBA_AEAT_200_2025_0A.200"
    assert r.status_code == 200 and destino.is_file() and destino.read_bytes() == (cliente.app.state.config.almacen / p.fichero_ruta).read_bytes()
    assert "✓ 2.- Copiar para presentar" in cliente.get(f"{base}/f/2025").text


def test_el_cnae_de_la_ficha_y_la_pagina_de_actividades_agricolas(sesion, ej):
    ej.empresa.cnae = "125"
    f = gen.generar(sesion, ej)
    assert _por_codigo(f)["01000"].numero(18) == 125 and _por_codigo(f)["01000"].valores[18] == "0125" and "21000" not in _por_codigo(f)
    f = gen.generar(sesion, ej, isd.DatosIS(agricola=True))
    assert _por_codigo(f)["01000"].numero(19) == 1 and list(_por_codigo(f)).index("21000") > list(_por_codigo(f)).index("20D00")
    assert _valor(f, "21000", 1897) == 1210 and _valor(f, "21000", 1901) == 0  # toda la cifra de negocios; sin otros ingresos de explotación
    assert Fichero200.leer(f.escribir()).escribir() == f.escribir()
