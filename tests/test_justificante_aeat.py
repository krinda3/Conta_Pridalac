"""Lectura del PDF de presentación de la AEAT y registro de la presentación a partir de él."""
import glob
import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Factura, FacturaIva, PresentacionAeat
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.justificante_aeat import leer_justificante
from conta_pridalac.servicios.presentacion303 import crear_borrador, generar_fichero, registrar_presentacion

D = Decimal
RAIZ = Path(__file__).resolve().parents[1]


def pdf_de_la_sede(*, modelo="303", registro="202630300790771G", csv="CKRKN4WXFTXCU8QT", justificante="3036479211552", fecha="20-07-2026 a las 13:36:04", resultado="INGRESAR", nrc_importe="NRC: 3036479211552SFK8Y016Y IMPORTE: 210,00"):
    """Una página con el mismo texto que la primera del justificante real de la sede."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    lineas = [
        "INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN", f"Modelo {modelo}", "Registro", f"Presentación realizada el: {fecha}", f"Expediente/Referencia (nº registro asignado): {registro}",
        f"Código Seguro de Verificación: {csv}", f"Número de justificante: {justificante}", "Vía de entrada: Presentación por Internet", "Presentador", "NIF Presentador: B12345678",
        "Apellidos y Nombre / Razón social: EMPRESA DE PRUEBA SL", "En calidad de: Titular", resultado, *([nrc_importe] if nrc_importe else []),
        "La autenticidad de este documento puede ser comprobada mediante el Código Seguro",
    ]
    for i, l in enumerate(lineas):
        c.drawString(50, 800 - 18 * i, l)
    c.save()
    return buf.getvalue()


def test_lee_los_datos_del_justificante():
    j = leer_justificante(pdf_de_la_sede())
    assert (j.modelo, j.registro, j.csv, j.justificante) == ("303", "202630300790771G", "CKRKN4WXFTXCU8QT", "3036479211552")
    assert j.momento == datetime(2026, 7, 20, 13, 36, 4) and j.nif_presentador == "B12345678"
    assert (j.resultado, j.nrc, j.importe) == ("I", "3036479211552SFK8Y016Y", D("210.00"))


@pytest.mark.parametrize(
    "resultado, tipo",
    [("A COMPENSAR", "C"), ("DOMICILIACIÓN DEL IMPORTE A INGRESAR", "U"), ("SOLICITUD DE DEVOLUCIÓN", "D"), ("NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO", "N")],
)
def test_reconoce_el_tipo_de_cada_resultado(resultado, tipo):
    j = leer_justificante(pdf_de_la_sede(resultado=resultado, nrc_importe=None))
    assert j.resultado == tipo and j.nrc is None and j.importe is None


@pytest.mark.parametrize("contenido", [b"no es un pdf", b"%PDF-1.4 roto", pdf_de_la_sede()[:200]])
def test_un_pdf_que_no_es_el_justificante_no_se_reconoce(contenido):
    assert leer_justificante(contenido) is None


def test_lee_los_justificantes_reales_de_programa_anterior():
    ficheros = sorted(glob.glob(str(RAIZ / "docs" / "Exportaciones del programa anterior" / "Comprobantes" / "202[3-6]" / "C000?_303_*.PDF")))
    if not ficheros:
        pytest.skip("no están los PDF del programa anterior (no se versionan)")
    for f in ficheros:
        j = leer_justificante(Path(f).read_bytes())
        assert j is not None and len(j.justificante) == 13 and len(j.csv) == 16 and j.resultado, f


# ---------------------------------------------------------------------------------------------- registrar sólo con el PDF


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678", iban="ES9121000418450200051332")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("47700000", "IVA REPERCUTIDO"), ("43000001", "CLIENTE"), ("70500000", "VENTAS")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = lambda c: sesion.scalars(select(Cuenta).where(Cuenta.codigo == c)).one()  # noqa: E731
    f = Factura(sentido="E", fecha_contable=date(2026, 2, 10), fecha_factura=date(2026, 2, 10), numero_factura="E-1", cuenta_tercero_id=cuenta("43000001").id,
                cuenta_contrapartida_id=cuenta("70500000").id, total=D("1210.00"))
    f.ivas.append(FacturaIva(base=D("1000.00"), pct_iva=D("21.00"), cuota_iva=D("210.00"), cuenta_iva_id=cuenta("47700000").id))
    grabar_factura(sesion, ej, f)
    return ej


@pytest.fixture(autouse=True)
def antes_de_todos_los_plazos(monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.presentacion303.hoy", lambda: date(2026, 1, 15))


def generada(sesion, ej, tmp_path, **kw):
    p, _ = crear_borrador(sesion, ej, 1, **kw)
    generar_fichero(sesion, ej, p, tmp_path)
    return p


def test_registrar_solo_con_el_pdf_rellena_justificante_csv_y_fecha(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path)  # domiciliación
    pdf = pdf_de_la_sede(resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None)
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf, usuario="javier")
    assert p.estado == "presentada" and p.justificante == "3036479211552" and p.csv == "CKRKN4WXFTXCU8QT" and p.presentada_en == datetime(2026, 7, 20, 13, 36, 4)
    assert (tmp_path / p.respuesta_ruta).read_bytes() == pdf


def test_al_registrar_se_copia_el_justificante_a_la_carpeta_de_la_empresa(sesion, ej, tmp_path):
    empresa = sesion.get(Empresa, ej.empresa_id)
    empresa.nombre_corto = "PRUEBA"
    empresa.carpeta_justificantes = str(tmp_path / "OneDrive" / "Hacienda {año}")
    p = generada(sesion, ej, tmp_path / "almacen")
    pdf = pdf_de_la_sede(resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None)
    registrar_presentacion(sesion, ej, p, tmp_path / "almacen", pdf=pdf)
    copiado = tmp_path / "OneDrive" / "Hacienda 2026" / "PRUEBA AEAT Mod 303 1T 2026.pdf"
    assert copiado.read_bytes() == pdf and str(copiado) in p.aviso_copia
    assert [e.evento for e in p.eventos][-1] == "copiada"


def test_si_la_copia_falla_la_presentacion_se_registra_igual_y_se_avisa(sesion, ej, tmp_path):
    empresa = sesion.get(Empresa, ej.empresa_id)
    ocupado = tmp_path / "es_un_fichero"
    ocupado.write_text("no es una carpeta")
    empresa.carpeta_justificantes = str(ocupado / "Hacienda {año}")  # no se puede crear una carpeta dentro de un fichero
    p = generada(sesion, ej, tmp_path / "almacen")
    registrar_presentacion(sesion, ej, p, tmp_path / "almacen", pdf=pdf_de_la_sede(resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None))
    assert p.estado == "presentada" and "AVISO" in p.aviso_copia and [e.evento for e in p.eventos][-1] == "copia_fallida"


def test_sin_carpeta_configurada_no_se_copia_ni_se_avisa(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path)
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede(resultado="DOMICILIACIÓN DEL IMPORTE A INGRESAR", nrc_importe=None))
    assert p.estado == "presentada" and p.aviso_copia == ""


def test_con_nrc_se_toma_del_pdf_y_se_contrasta_el_importe(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path, domiciliar=False)  # sin NRC anotado todavía
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede())
    assert p.nrc == "3036479211552SFK8Y016Y" and p.nrc_importe == D("210.00") and p.estado == "presentada"


@pytest.mark.parametrize(
    "pdf, mensaje",
    [
        (dict(modelo="111"), "del modelo 111"),
        (dict(registro="202511100790771G"), "otro ejercicio"),
        (dict(resultado="A COMPENSAR", nrc_importe=None), "tipo C.*era de tipo I"),
        (dict(nrc_importe="NRC: 3036479211552SFK8Y016Y IMPORTE: 99,00"), "ingresaron 99.00"),
    ],
)
def test_si_el_pdf_no_cuadra_con_lo_generado_no_se_registra(sesion, ej, tmp_path, pdf, mensaje):
    p = generada(sesion, ej, tmp_path, domiciliar=False)
    with pytest.raises(ErrorContable, match=mensaje):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede(**pdf))
    assert p.estado == "generada" and not p.justificante


def test_el_nrc_del_pdf_debe_ser_el_anotado(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path, domiciliar=False, nrc="9999999999999AAAAAAAAA")
    with pytest.raises(ErrorContable, match="no es el anotado"):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede())


def test_lo_tecleado_debe_coincidir_con_el_pdf_y_un_justificante_no_se_repite(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path, domiciliar=False)
    with pytest.raises(ErrorContable, match="CSV tecleado no coincide"):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede(), csv="AAAAAAAAAAAAAAAA")
    with pytest.raises(ErrorContable, match="fecha y hora tecleadas"):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede(), momento=datetime(2026, 7, 21, 9, 0))
    sesion.add(PresentacionAeat(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo="2T", estado="presentada", justificante="3036479211552", casillas="{}"))
    sesion.flush()
    with pytest.raises(ErrorContable, match="ya está registrado en otra presentación"):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=pdf_de_la_sede())


def test_un_pdf_irreconocible_exige_los_datos_a_mano(sesion, ej, tmp_path):
    p = generada(sesion, ej, tmp_path)
    with pytest.raises(ErrorContable, match="No se reconoce el PDF"):
        registrar_presentacion(sesion, ej, p, tmp_path, pdf=b"%PDF-1.4 cualquier cosa")
    registrar_presentacion(sesion, ej, p, tmp_path, pdf=b"%PDF-1.4 cualquier cosa", justificante="3036479211552", csv="CKRKN4WXFTXCU8QT", momento=datetime(2026, 7, 20, 13, 36))
    assert p.estado == "presentada"
