"""Borrador del 303 y sus controles: estados, periodo presentado, compensación, contabilidad y avisos."""
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR
from conta_pridalac.db.modelos import (
    BORRADOR,
    PRESENTADA,
    Apunte,
    Asiento,
    Cuenta,
    DeclaracionPresentada,
    Ejercicio,
    Empresa,
    Factura,
    FacturaIva,
    PresentacionAeat,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.modelo303 import bolsa_de_periodos_anteriores, calcular_303
from conta_pridalac.servicios.presentacion303 import controlar_303, crear_borrador, hay_errores, presentada_del_periodo

D = Decimal


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    """Los tests no dependen del día en que se ejecutan: «hoy» es anterior a cualquier plazo de 2026."""
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("62900000", "SERVICIOS"), ("47200000", "IVA SOPORTADO"), ("47700000", "IVA REPERCUTIDO"), ("41000186", "PROVEEDOR"), ("43000001", "CLIENTE"), ("70500000", "VENTAS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    return ej


def _cuenta(sesion, codigo):
    return sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()


def recibida(sesion, ej, fecha, base, cuota, numero="A-1"):
    f = Factura(sentido="R", fecha_contable=fecha, fecha_factura=fecha, numero_factura=numero, cuenta_tercero_id=_cuenta(sesion, "41000186").id,
                cuenta_contrapartida_id=_cuenta(sesion, "62900000").id, total=D(base) + D(cuota))
    f.ivas.append(FacturaIva(base=D(base), pct_iva=D("21.00"), cuota_iva=D(cuota), cuenta_iva_id=_cuenta(sesion, "47200000").id))
    return grabar_factura(sesion, ej, f).factura


def emitida(sesion, ej, fecha, base, cuota, numero="E-1", pct="21.00"):
    f = Factura(sentido="E", fecha_contable=fecha, fecha_factura=fecha, numero_factura=numero, cuenta_tercero_id=_cuenta(sesion, "43000001").id,
                cuenta_contrapartida_id=_cuenta(sesion, "70500000").id, total=D(base) + D(cuota))
    f.ivas.append(FacturaIva(base=D(base), pct_iva=D(pct), cuota_iva=D(cuota), cuenta_iva_id=_cuenta(sesion, "47700000").id))
    return grabar_factura(sesion, ej, f).factura


def codigos(hallazgos, gravedad=None):
    return Counter(h.codigo for h in hallazgos if gravedad is None or h.gravedad == gravedad)


def presentada(sesion, ej, periodo, casillas, **kw):
    p = PresentacionAeat(empresa_id=ej.empresa_id, modelo="303", anio=ej.anio, periodo=f"{periodo}T", estado=PRESENTADA, casillas=json.dumps({str(k): str(v) for k, v in casillas.items()}), **kw)
    sesion.add(p)
    sesion.flush()
    return p


def test_borrador_correcto_congela_las_casillas_y_deja_historial(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    recibida(sesion, ej, date(2026, 2, 12), "300.00", "63.00")
    p, h = crear_borrador(sesion, ej, 1, usuario="javier")
    assert not hay_errores(h) and codigos(h) == {"facturas_sin_justificante": 1}  # los justificantes no son obligatorios: sólo aviso
    assert p.estado == BORRADOR and p.tipo_declaracion == "U" and p.resultado == D("147.00") and p.periodo == "1T"
    c = json.loads(p.casillas)
    assert (c["27"], c["29"], c["71"]) == ("210.00", "63.00", "147.00")
    assert [(e.evento, e.usuario) for e in p.eventos] == [("creada", "javier")]


def test_un_nuevo_borrador_sustituye_al_anterior(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    crear_borrador(sesion, ej, 1)
    segundo, _ = crear_borrador(sesion, ej, 1)
    assert sesion.scalars(select(PresentacionAeat)).all() == [segundo]


def test_resultado_negativo_se_presenta_con_compensacion(sesion, ej):
    recibida(sesion, ej, date(2026, 2, 12), "300.00", "63.00")
    p, h = crear_borrador(sesion, ej, 1)
    assert p.tipo_declaracion == "C" and p.resultado == D("-63.00") and not hay_errores(h)


def test_periodo_presentado_solo_admite_una_rectificativa_con_el_justificante_de_la_anterior(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    anterior = presentada(sesion, ej, 1, {69: "210.00", 71: "210.00"})
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 1)
    p, h = crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")
    assert p.anterior_id == anterior.id and codigos(h, ERROR) == {"falta_justificante_anterior": 1}  # sin justificante anterior no hay fichero de rectificativa
    anterior.justificante = "3031234567890"
    assert not hay_errores(crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")[1])


def test_rectificativa_sin_nada_presentado_es_error(sesion, ej):
    with pytest.raises(ErrorContable, match="No hay un 1T 2026 presentado"):
        crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")


def test_lo_importado_de_programa_anterior_tambien_cuenta_como_presentado(sesion, ej):
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=1, tipo=1, casillas="{}"))
    sesion.flush()
    assert presentada_del_periodo(sesion, ej.empresa_id, 2026, 1) is not None
    with pytest.raises(ErrorContable):
        crear_borrador(sesion, ej, 1)


def test_el_trimestre_anterior_debe_estar_presentado_o_dar_la_bolsa_a_mano(sesion, ej):
    emitida(sesion, ej, date(2026, 5, 10), "1000.00", "210.00")
    _, h = crear_borrador(sesion, ej, 2)
    assert codigos(h, ERROR) == {"trimestre_anterior_sin_presentar": 1}
    p, h = crear_borrador(sesion, ej, 2, bolsa=D("100.00"))
    assert not hay_errores(h) and codigos(h, AVISO)["bolsa_introducida_a_mano"] == 1
    assert p.bolsa_inicial == D("100.00") and p.resultado == D("110.00")


def test_la_bolsa_sale_de_lo_presentado_con_este_programa(sesion, ej):
    presentada(sesion, ej, 1, {46: "-300.00", 87: "100.00", 71: "-300.00"})
    assert bolsa_de_periodos_anteriores(sesion, ej.empresa_id, 2026, 2) == D("400.00")
    emitida(sesion, ej, date(2026, 5, 10), "1000.00", "210.00")
    p, h = crear_borrador(sesion, ej, 2)
    assert not hay_errores(h) and p.bolsa_inicial == D("400.00") and p.resultado == D("0.00") and p.tipo_declaracion == "N"


def test_asiento_descuadrado_del_periodo_es_error_pero_el_de_otro_periodo_no(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")

    def asiento(fecha, numero):
        a = Asiento(ejercicio_id=ej.id, tipo=4, numero=numero, fecha=fecha, numero_diario=numero)
        a.apuntes.append(Apunte(orden=1, cuenta_id=_cuenta(sesion, "62900000").id, debe=D("30.38")))
        a.apuntes.append(Apunte(orden=2, cuenta_id=_cuenta(sesion, "41000186").id, haber=D("34.56")))
        sesion.add(a)
        sesion.flush()

    asiento(date(2026, 8, 1), 1)
    assert "asiento_descuadrado" not in codigos(crear_borrador(sesion, ej, 1)[1])
    asiento(date(2026, 2, 5), 2)
    assert codigos(crear_borrador(sesion, ej, 1)[1], ERROR)["asiento_descuadrado"] == 1


def test_un_asiento_manual_en_la_477_se_avisa_pero_no_bloquea(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    a = Asiento(ejercicio_id=ej.id, tipo=4, numero=1, fecha=date(2026, 3, 1), numero_diario=1)
    a.apuntes.append(Apunte(orden=1, cuenta_id=_cuenta(sesion, "43000001").id, debe=D("50.00")))
    a.apuntes.append(Apunte(orden=2, cuenta_id=_cuenta(sesion, "47700000").id, haber=D("50.00")))
    sesion.add(a)
    sesion.flush()
    _, h = crear_borrador(sesion, ej, 1)
    assert not hay_errores(h) and codigos(h, AVISO)["asientos_manuales_en_cuentas_de_iva"] == 1


def test_el_303_debe_cuadrar_con_los_asientos_de_las_facturas(sesion, ej):
    f = emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    ap = sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo == "47700000", Apunte.asiento_id.in_(select(Asiento.id).where(Asiento.tipo == 1, Asiento.numero == f.numero)))).one()
    ap.haber = D("200.00")  # alguien toca el asiento de la factura
    sesion.flush()
    assert "devengado_distinto_de_la_contabilidad" in codigos(crear_borrador(sesion, ej, 1)[1], ERROR)


def test_factura_sin_su_asiento_es_error(sesion, ej):
    f = emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    sesion.delete(sesion.scalars(select(Asiento).where(Asiento.tipo == 1, Asiento.numero == f.numero)).one())
    sesion.flush()
    _, h = crear_borrador(sesion, ej, 1)
    assert hay_errores(h) and "factura_sin_asiento" in codigos(h, ERROR)


def test_el_4t_avisa_de_la_prorrata_si_la_empresa_la_aplica(sesion, ej):
    for per in (1, 2, 3):
        presentada(sesion, ej, per, {71: "0.00"})
    emitida(sesion, ej, date(2026, 11, 10), "1000.00", "210.00")
    emitida(sesion, ej, date(2026, 11, 2), "680.00", "0.00", numero="E-2", pct="0.00")  # alquiler exento: casilla 150
    _, h = crear_borrador(sesion, ej, 4)
    assert codigos(h, AVISO)["prorrata_sin_introducir"] == 1 and not hay_errores(h)
    _, h = crear_borrador(sesion, ej, 4, regularizacion_prorrata=D("-50.00"))
    assert "prorrata_sin_introducir" not in codigos(h)


def test_sin_iban_no_se_puede_domiciliar(sesion, ej):
    ej.empresa.iban = None
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    assert codigos(crear_borrador(sesion, ej, 1)[1], ERROR) == {"domiciliacion_sin_iban": 1}
    assert not hay_errores(crear_borrador(sesion, ej, 1, domiciliar=False)[1])


def test_los_controles_se_pueden_pedir_sin_crear_nada(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    calculo = calcular_303(sesion, ej, 1)
    assert not hay_errores(controlar_303(sesion, ej, 1, calculo, iban="ES00"))
    assert sesion.scalars(select(PresentacionAeat)).all() == []


def test_generar_el_fichero_lo_guarda_con_su_huella_y_la_version_del_diseno(sesion, ej, tmp_path):
    import hashlib

    from conta_pridalac.db.modelos import GENERADA
    from conta_pridalac.ficheros_aeat.fichero303 import DISENO_VERSION, leer
    from conta_pridalac.servicios.presentacion303 import generar_fichero

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p, _ = crear_borrador(sesion, ej, 1, usuario="javier")
    ruta = generar_fichero(sesion, ej, p, tmp_path, usuario="javier")
    texto = ruta.read_bytes()
    assert ruta.parent == tmp_path / "001" / "2026" / "aeat" and p.fichero_ruta == ruta.relative_to(tmp_path).as_posix()
    assert p.estado == GENERADA and p.fichero_sha256 == hashlib.sha256(texto).hexdigest() and p.diseno_version == DISENO_VERSION
    assert p.fichero_nombre == "PRUEBA_AEAT_303_2026_1T.303" and p.tipo_declaracion == "U"
    assert leer(texto.decode("latin-1"))["01000"][14] == "B12345678"
    assert [e.evento for e in p.eventos] == ["creada", "fichero_generado"]


def test_no_se_genera_con_errores_ni_si_las_facturas_cambiaron(sesion, ej, tmp_path):
    from conta_pridalac.servicios.presentacion303 import generar_fichero

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p, _ = crear_borrador(sesion, ej, 1)
    emitida(sesion, ej, date(2026, 2, 11), "100.00", "21.00", numero="E-2")
    with pytest.raises(ErrorContable, match="han cambiado"):
        generar_fichero(sesion, ej, p, tmp_path)
    ej.empresa.iban = None
    p, h = crear_borrador(sesion, ej, 1)
    assert hay_errores(h)
    with pytest.raises(ErrorContable, match="IBAN"):
        generar_fichero(sesion, ej, p, tmp_path)
    assert not list(tmp_path.rglob("*.303"))


def test_los_ficheros_de_las_presentaciones_no_son_huerfanos_para_la_auditoria(sesion, ej, tmp_path):
    from conta_pridalac.auditoria import auditar
    from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos
    from conta_pridalac.servicios.presentacion303 import generar_fichero

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p, _ = crear_borrador(sesion, ej, 1)
    generar_fichero(sesion, ej, p, tmp_path)
    assert "fichero_huerfano" not in {h.codigo for h in auditar(sesion, ej, almacen=AlmacenAdjuntos(tmp_path))}


def test_domiciliar_fuera_de_plazo_es_error_y_con_nrc_ya_no(sesion, ej, monkeypatch):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 4, 16))  # el 1T se domicilia hasta el 15 de abril
    p, h = crear_borrador(sesion, ej, 1)
    assert codigos(h, ERROR) == {"domiciliacion_fuera_de_plazo": 1} and "15/04/2026" in next(x for x in h if x.codigo == "domiciliacion_fuera_de_plazo").mensaje
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False)
    assert not hay_errores(h) and codigos(h, AVISO)["nrc_pendiente"] == 1
    assert p.tipo_declaracion == "I"
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 4, 15))
    assert not hay_errores(crear_borrador(sesion, ej, 1)[1])  # el último día aún vale


def test_presentacion_fuera_de_plazo_solo_avisa(sesion, ej, monkeypatch):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 4, 21))
    _, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc="3036479211552SFK8Y016Y")
    assert codigos(h, AVISO)["presentacion_fuera_de_plazo"] == 1 and not hay_errores(h) and "nrc_pendiente" not in codigos(h)


def test_el_nrc_se_valida_y_se_guarda_en_el_borrador(sesion, ej):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    assert codigos(crear_borrador(sesion, ej, 1, domiciliar=False, nrc="corto")[1], ERROR) == {"nrc_no_valido": 1}
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc="3036479211552SFK8Y016Y")
    assert not hay_errores(h) and p.nrc == "3036479211552SFK8Y016Y" and p.tipo_declaracion == "I"
    assert "nrc_sin_importe_a_ingresar" in codigos(crear_borrador(sesion, ej, 1, domiciliar=True, nrc="3036479211552SFK8Y016Y")[1])


def test_el_nrc_solo_vale_para_el_importe_con_el_que_se_anoto(sesion, ej):
    nrc = "3036479211552SFK8Y016Y"
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc=nrc)
    assert p.nrc_importe == D("210.00") and not hay_errores(h)
    emitida(sesion, ej, date(2026, 2, 11), "100.00", "21.00", numero="E-2")  # el resultado pasa a 231
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc=nrc)
    assert codigos(h, ERROR) == {"nrc_de_otro_importe": 1} and p.nrc_importe == D("210.00")  # sigue constando el importe con el que se pagó
    p, h = crear_borrador(sesion, ej, 1, domiciliar=False, nrc="9999999999999AAAAAAAAA")  # un NRC nuevo, pagado con el importe de ahora
    assert not hay_errores(h) and p.nrc_importe == D("231.00")


# ---------------------------------------------------------------------------------------------- plan B: registrar lo presentado en la sede

PDF = b"%PDF-1.4 justificante de prueba"
AYER = datetime(2026, 4, 14, 10, 30)


def generada(sesion, ej, tmp_path, periodo=1, **kw):
    from conta_pridalac.servicios.presentacion303 import generar_fichero

    p, _ = crear_borrador(sesion, ej, periodo, **kw)
    generar_fichero(sesion, ej, p, tmp_path)
    return p


def registrar(sesion, ej, p, tmp_path, **kw):
    from conta_pridalac.servicios.presentacion303 import registrar_presentacion

    datos = dict(justificante="3037084443540", csv="ABCD1234EFGH5678", momento=AYER, pdf=PDF, usuario="javier")
    datos.update(kw)
    return registrar_presentacion(sesion, ej, p, tmp_path, **datos)


def test_registrar_la_presentacion_bloquea_el_trimestre_y_guarda_el_justificante(sesion, ej, tmp_path):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p = generada(sesion, ej, tmp_path)
    registrar(sesion, ej, p, tmp_path)
    assert p.estado == PRESENTADA and p.justificante == "3037084443540" and p.csv == "ABCD1234EFGH5678" and p.presentada_por == "javier" and p.presentada_en == AYER
    ruta = tmp_path / p.respuesta_ruta
    assert ruta.read_bytes() == PDF and p.respuesta_sha256 and ruta.parent == tmp_path / "001" / "2026" / "aeat"
    assert [e.evento for e in p.eventos] == ["creada", "fichero_generado", "presentada"]
    assert presentada_del_periodo(sesion, ej.empresa_id, 2026, 1) is p
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej, 1)  # el trimestre queda bloqueado para un borrador normal
    emitida(sesion, ej, date(2026, 5, 10), "1000.00", "210.00", numero="E-9")
    assert crear_borrador(sesion, ej, 2)[0].bolsa_inicial == D("0.00") and "trimestre_anterior_sin_presentar" not in codigos(crear_borrador(sesion, ej, 2)[1])


@pytest.mark.parametrize(
    "cambios, mensaje",
    [
        (dict(justificante="123"), "13 dígitos"),
        (dict(csv="corto"), "16 caracteres"),
        (dict(pdf=b"no es un pdf"), "PDF"),
        (dict(momento=datetime(2999, 1, 1)), "futuras"),
    ],
)
def test_registrar_valida_lo_que_se_anota(sesion, ej, tmp_path, cambios, mensaje):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p = generada(sesion, ej, tmp_path)
    with pytest.raises(ErrorContable, match=mensaje):
        registrar(sesion, ej, p, tmp_path, **cambios)
    assert p.estado == "generada" and not p.justificante


def test_solo_se_registra_un_fichero_generado_y_sin_alterar(sesion, ej, tmp_path):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p, _ = crear_borrador(sesion, ej, 1)
    with pytest.raises(ErrorContable, match="generar el fichero"):
        registrar(sesion, ej, p, tmp_path)
    p = generada(sesion, ej, tmp_path)
    (tmp_path / p.fichero_ruta).write_bytes(b"<T3030>alterado")
    with pytest.raises(ErrorContable, match="ha cambiado"):
        registrar(sesion, ej, p, tmp_path)


def test_el_ingreso_con_nrc_exige_el_nrc_para_registrar(sesion, ej, tmp_path):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p = generada(sesion, ej, tmp_path, domiciliar=False)
    with pytest.raises(ErrorContable, match="NRC"):
        registrar(sesion, ej, p, tmp_path)
    p = generada(sesion, ej, tmp_path, domiciliar=False, nrc="3036479211552SFK8Y016Y")
    assert registrar(sesion, ej, p, tmp_path).nrc == "3036479211552SFK8Y016Y"


def test_la_rectificativa_presentada_sustituye_a_la_anterior(sesion, ej, tmp_path):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    original = generada(sesion, ej, tmp_path)
    registrar(sesion, ej, original, tmp_path)
    rectificativa = generada(sesion, ej, tmp_path, tipo_presentacion="rectificativa")
    registrar(sesion, ej, rectificativa, tmp_path, justificante="3037084443541", csv="ZZZZ1234EFGH5678")
    assert original.estado == "sustituida" and presentada_del_periodo(sesion, ej.empresa_id, 2026, 1) is rectificativa
    assert "rectificativa_de_una_rectificativa" in codigos(crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")[1])
    segunda = generada(sesion, ej, tmp_path, tipo_presentacion="rectificativa")
    registrar(sesion, ej, segunda, tmp_path, justificante="3037084443542", csv="YYYY1234EFGH5678")
    assert rectificativa.estado == "sustituida" and presentada_del_periodo(sesion, ej.empresa_id, 2026, 1) is segunda


# ---------------------------------------------------------------------------------------------- casillas de la rectificativa (instrucciones 2026)


@pytest.mark.parametrize(
    "anterior_69, c70, c71, c111, tipo",
    [
        (D("100.00"), D("100.00"), D("110.00"), None, "U"),  # mayor ingreso: la 70 lleva lo de la anterior y la 71 sólo la diferencia
        (D("210.00"), D("210.00"), D("0.00"), None, "N"),  # igual que antes
        (D("300.00"), D("300.00"), D("-90.00"), D("90.00"), "N"),  # ingreso de más: la parte negativa va a la 111 y el tipo no cuenta esa parte
        (D("-50.00"), None, D("210.00"), None, "U"),  # la anterior era a compensar: la 70 queda en blanco
    ],
)
def test_casillas_70_71_y_111_de_la_rectificativa(sesion, ej, anterior_69, c70, c71, c111, tipo):
    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    presentada(sesion, ej, 1, {69: str(anterior_69), 71: str(anterior_69)}, justificante="3037084443540")
    p, h = crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")
    c = json.loads(p.casillas)
    assert c["69"] == "210.00" and (D(c["70"]) if "70" in c else None) == c70 and D(c["71"]) == c71 and (D(c["111"]) if "111" in c else None) == c111
    assert p.resultado == c71 and p.tipo_declaracion == tipo
    assert not hay_errores(h) and ("casilla_111" in codigos(h)) == (c111 is not None)


def test_el_fichero_de_la_rectificativa_lleva_justificante_anterior_motivo_y_casillas(sesion, ej, tmp_path):
    from conta_pridalac.ficheros_aeat.fichero303 import leer

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    presentada(sesion, ej, 1, {69: "300.00", 71: "300.00"}, justificante="3037084443540")
    p = generada(sesion, ej, tmp_path, tipo_presentacion="rectificativa", baja_domiciliacion=True)
    paginas = leer((tmp_path / p.fichero_ruta).read_text(encoding="latin-1"))
    p1, p3 = paginas["01000"], paginas["03000"]
    assert p1[13] == "N"
    assert p3[426] == "X" and p3[427] == "3037084443540" and p3[440] == "X" and p3[458] == "X" and p3[459] == " "
    assert p3[357] == "00000000000030000" and p3[441] == "00000000000009000"  # casillas 70 y 111
    assert p.fichero_nombre == "PRUEBA_AEAT_303_2026_1T_rectificativa.303"


def test_el_fichero_normal_no_lleva_marcas_de_rectificativa(sesion, ej, tmp_path):
    from conta_pridalac.ficheros_aeat.fichero303 import leer

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p3 = leer((tmp_path / generada(sesion, ej, tmp_path).fichero_ruta).read_text(encoding="latin-1"))["03000"]
    assert p3[426] == " " and p3[427] == " " * 13 and p3[440] == " " and p3[458] == " "


def test_rechazada_y_borrador_nuevo_descarta_el_fichero_anterior(sesion, ej, tmp_path):
    from conta_pridalac.servicios.presentacion303 import marcar_rechazada

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    p = generada(sesion, ej, tmp_path)
    with pytest.raises(ErrorContable, match="motivo"):
        marcar_rechazada(sesion, p, "  ")
    marcar_rechazada(sesion, p, "Error 5: NIF no coincide", usuario="javier")
    assert p.estado == "rechazada" and p.observaciones == "Error 5: NIF no coincide" and p.eventos[-1].evento == "rechazada"
    otra = generada(sesion, ej, tmp_path)
    nueva, _ = crear_borrador(sesion, ej, 1)
    assert otra.estado == "descartada" and nueva.estado == "borrador" and (tmp_path / otra.fichero_ruta).is_file()
    with pytest.raises(ErrorContable):
        marcar_rechazada(sesion, otra, "x")


# ---------------------------------------------------------------------------------------------- higiene: borrar lo que no se presentó


def test_se_borra_lo_no_presentado_con_sus_ficheros_y_nunca_lo_presentado(sesion, ej, tmp_path):
    from conta_pridalac.servicios.presentacion303 import eliminar_presentacion, eliminar_sin_presentar, marcar_rechazada, sin_presentar

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    rechazada = generada(sesion, ej, tmp_path)
    marcar_rechazada(sesion, rechazada, "error de prueba")
    descartada = generada(sesion, ej, tmp_path)
    actual = generada(sesion, ej, tmp_path)  # deja la anterior como descartada
    assert descartada.estado == "descartada" and actual.estado == "generada"
    ficheros = [tmp_path / x.fichero_ruta for x in (rechazada, descartada, actual)]
    assert all(f.is_file() for f in ficheros) and len(sin_presentar(sesion, ej.empresa_id, 2026, 1)) == 3
    n, borrados = eliminar_sin_presentar(sesion, ej.empresa_id, 2026, 1, tmp_path)
    assert (n, borrados) == (3, 3) and not any(f.exists() for f in ficheros) and sesion.scalars(select(PresentacionAeat)).all() == []
    with pytest.raises(ErrorContable, match="No hay borradores ni ficheros sin presentar"):
        eliminar_sin_presentar(sesion, ej.empresa_id, 2026, 1, tmp_path)


def test_lo_presentado_no_se_borra(sesion, ej, tmp_path):
    from conta_pridalac.servicios.presentacion303 import eliminar_presentacion, eliminar_sin_presentar

    emitida(sesion, ej, date(2026, 2, 10), "1000.00", "210.00")
    original = generada(sesion, ej, tmp_path)
    registrar(sesion, ej, original, tmp_path)
    with pytest.raises(ErrorContable, match="no se puede borrar"):
        eliminar_presentacion(sesion, original, tmp_path)
    borrador, _ = crear_borrador(sesion, ej, 1, tipo_presentacion="rectificativa")
    assert eliminar_sin_presentar(sesion, ej.empresa_id, 2026, 1, tmp_path) == (1, 0)  # sólo el borrador, que aún no tenía fichero
    assert original.estado == PRESENTADA and (tmp_path / original.fichero_ruta).is_file() and (tmp_path / original.respuesta_ruta).is_file()
    rectificativa = generada(sesion, ej, tmp_path, tipo_presentacion="rectificativa")
    registrar(sesion, ej, rectificativa, tmp_path, justificante="3037084443541", csv="ZZZZ1234EFGH5678")
    assert original.estado == "sustituida"
    with pytest.raises(ErrorContable):
        eliminar_presentacion(sesion, original, tmp_path)  # lo sustituido tampoco: sigue siendo parte de la historia


def test_borrar_no_toca_ficheros_fuera_del_almacen(sesion, ej, tmp_path):
    from conta_pridalac.servicios.presentacion303 import eliminar_presentacion

    ajeno = tmp_path / "ajeno.txt"
    ajeno.write_text("no es del almacén")
    carpeta = tmp_path / "almacen"
    carpeta.mkdir()
    p = PresentacionAeat(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo="1T", estado="generada", casillas="{}", fichero_ruta="../ajeno.txt")
    sesion.add(p)
    sesion.flush()
    assert eliminar_presentacion(sesion, p, carpeta) is False and ajeno.exists()
