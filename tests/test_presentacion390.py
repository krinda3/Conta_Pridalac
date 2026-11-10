"""Borrador del 390, controles, fichero, registro con el PDF de la sede y sustitutiva."""
import json
from datetime import date
from decimal import Decimal

import pytest

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Factura, FacturaIva
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero390
from conta_pridalac.servicios import ficha_390
from conta_pridalac.servicios.presentacion390 import controlar_390, crear_borrador, generar_fichero, registrar
from conta_pridalac.servicios.modelo390 import calcular_390
from test_justificante_aeat import pdf_de_la_sede

D = Decimal


@pytest.fixture(autouse=True)
def en_el_plazo(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion390.hoy", lambda: date(2026, 1, 15))


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    cuenta = Cuenta(empresa_id=e.id, codigo="62800000", nombre="G")
    sesion.add(cuenta)
    sesion.flush()
    for sentido, numero, fecha, base, cuota in (("E", 1, date(2025, 7, 5), "1000.00", "210.00"), ("R", 1, date(2025, 7, 9), "200.00", "42.00")):
        f = Factura(ejercicio_id=ej.id, sentido=sentido, numero=numero, fecha_contable=fecha, fecha_factura=fecha, numero_factura=f"F{numero}", total=D("0"), cuenta_tercero_id=cuenta.id, cuenta_contrapartida_id=cuenta.id)
        f.ivas.append(FacturaIva(base=D(base), pct_iva=D("21"), cuota_iva=D(cuota), deducible=True))
        sesion.add(f)
    sesion.flush()
    return ej


def _ficha(sesion, ej):
    ficha_390.guardar_actividades(sesion, ej.empresa, [("Servicios técnicos", "a03", "8431")])
    ficha_390.guardar_representantes(sesion, ej.empresa, [("Lopez Garcia, Elena", "00000014Z", "261011", "Romero")])


def codigos(h, gravedad=None):
    return {x.codigo for x in h if gravedad is None or x.gravedad == gravedad}


def test_sin_actividad_ni_representante_hay_errores(sesion, ej):
    hallazgos = controlar_390(sesion, ej, calcular_390(sesion, ej))
    assert {"falta_actividad", "falta_representante"} <= codigos(hallazgos, "ERROR")
    _ficha(sesion, ej)
    assert not codigos(controlar_390(sesion, ej, calcular_390(sesion, ej)), "ERROR")


def test_el_plazo_se_avisa_antes_y_despues(sesion, ej, monkeypatch):
    _ficha(sesion, ej)
    monkeypatch.setattr("conta_pridalac.servicios.presentacion390.hoy", lambda: date(2025, 12, 20))
    assert "presentacion_antes_de_plazo" in codigos(controlar_390(sesion, ej, calcular_390(sesion, ej)), "AVISO")
    monkeypatch.setattr("conta_pridalac.servicios.presentacion390.hoy", lambda: date(2026, 2, 3))
    assert "presentacion_fuera_de_plazo" in codigos(controlar_390(sesion, ej, calcular_390(sesion, ej)), "AVISO")


def test_borrador_y_fichero(sesion, ej, tmp_path):
    _ficha(sesion, ej)
    p, hallazgos = crear_borrador(sesion, ej)
    assert (p.modelo, p.periodo, p.estado, p.tipo_declaracion, p.resultado) == ("390", "0A", "borrador", "X", D("168.00"))
    c = json.loads(p.casillas)
    assert c["casillas"]["34"] == "210.00" and c["casillas"]["64"] == "42.00" and c["actividades"] == [["Servicios técnicos", "A03", "8431"]]
    ruta = generar_fichero(sesion, ej, p, tmp_path)
    assert p.estado == "generada" and p.fichero_nombre == "PRUEBA_AEAT_390_2025_0A.390" and p.diseno_version == fichero390.DISENO_VERSION
    texto = ruta.read_bytes().decode("latin-1")
    leidas = fichero390.casillas_del_fichero(texto)
    assert leidas[34] == D("210.00") and leidas[64] == D("42.00") and leidas[87] == D("100")
    assert fichero390.leer(texto)["01000"][646].strip() == "LOPEZ GARCIA, ELENA"


def test_si_cambia_la_ficha_hay_que_guardar_el_borrador_de_nuevo(sesion, ej, tmp_path):
    _ficha(sesion, ej)
    p, _ = crear_borrador(sesion, ej)
    ficha_390.guardar_representantes(sesion, ej.empresa, [("Otra Persona", "12345678Z", "", "")])
    with pytest.raises(ErrorContable, match="guarde el borrador"):
        generar_fichero(sesion, ej, p, tmp_path)


def test_registrar_con_el_pdf_de_la_sede_y_sustituir(sesion, ej, tmp_path):
    _ficha(sesion, ej)
    p, _ = crear_borrador(sesion, ej)
    generar_fichero(sesion, ej, p, tmp_path)
    pdf = pdf_de_la_sede(modelo="390", registro="202539000790112R", justificante="3906032822903", resultado="", nrc_importe=None, fecha="14-01-2026 a las 12:08:39")
    registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "presentada" and p.justificante == "3906032822903"
    with pytest.raises(ErrorContable, match="ya está presentado"):
        crear_borrador(sesion, ej)
    s, _ = crear_borrador(sesion, ej, tipo_presentacion="sustitutiva")
    assert s.anterior_id == p.id
    d = fichero390.leer(generar_fichero(sesion, ej, s, tmp_path).read_bytes().decode("latin-1"))["01000"]
    assert d[134] == "1" and d[136] == "3906032822903"


def test_un_pdf_de_otro_modelo_no_se_registra(sesion, ej, tmp_path):
    _ficha(sesion, ej)
    p, _ = crear_borrador(sesion, ej)
    generar_fichero(sesion, ej, p, tmp_path)
    pdf = pdf_de_la_sede(modelo="190", registro="2025190009950902801851", justificante="1900000000001", resultado="", nrc_importe=None, fecha="14-01-2026 a las 12:08:39")
    with pytest.raises(ErrorContable, match="modelo 190"):
        registrar(sesion, ej, p, tmp_path, pdf=pdf)
    assert p.estado == "generada"


def test_el_asistente_del_4t_ofrece_el_390_solo_en_el_cuarto_trimestre(sesion, ej, monkeypatch, tmp_path):
    from conta_pridalac.servicios import asistente_trimestre as asistente

    monkeypatch.setattr("conta_pridalac.servicios.vigilancia.PRIMER_EJERCICIO_390", 2025)

    def pasos_390(periodo):
        return [p for p in asistente.pasos(sesion, ej.empresa, ej, periodo, "Sin presentar", "Sin presentar") if "390" in p.titulo]

    assert pasos_390((date(2025, 7, 1), date(2025, 9, 30))) == []
    (paso,) = pasos_390((date(2025, 10, 1), date(2025, 12, 31)))
    assert paso.estado == "pendiente" and paso.pantalla == "modelo-390"
    _ficha(sesion, ej)
    p, _ = crear_borrador(sesion, ej)
    generar_fichero(sesion, ej, p, tmp_path)
    pdf = pdf_de_la_sede(modelo="390", registro="202539000790112R", justificante="3906032822903", resultado="", nrc_importe=None, fecha="14-01-2026 a las 12:08:39")
    registrar(sesion, ej, p, tmp_path, pdf=pdf)
    (paso,) = pasos_390((date(2025, 10, 1), date(2025, 12, 31)))
    assert paso.estado == "hecho" and "3906032822903" in paso.detalle
