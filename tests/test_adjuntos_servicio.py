"""Servicio de adjuntos: almacén en disco, validaciones, duplicados, sustitución, verificación y traslado desde MGD."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Adjunto, Cuenta, Ejercicio, Empresa, Factura, FacturaIva
from conta_pridalac.domain.errores import EjercicioCerrado
from conta_pridalac.servicios.adjuntos import (
    AdjuntoInvalido,
    AlmacenAdjuntos,
    adjuntar,
    facturas_sin_justificante,
    listar,
    nombre_seguro,
    quitar,
    sustituir,
    trasladar_a_almacen,
    verificar_almacen,
)
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.facturas import grabar_factura

D = Decimal
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 20


@pytest.fixture
def almacen(tmp_path):
    return AlmacenAdjuntos(tmp_path / "almacen")


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=11, nombre="Prueba")
    x = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, x])
    sesion.flush()
    for c in ("57200001", "62900000", "41000001"):
        sesion.add(Cuenta(empresa_id=e.id, codigo=c, nombre=c))
    sesion.flush()
    return x


@pytest.fixture
def asiento(sesion, ej):
    return grabar_asiento(sesion, ej, tipo=4, numero=1, fecha=date(2026, 1, 5), lineas=[LineaAsiento("62900000", D(10)), LineaAsiento("57200001", D(-10))])


def _fichero(tmp_path, nombre, contenido):
    f = tmp_path / nombre
    f.write_bytes(contenido)
    return f


def test_nombre_seguro():
    assert nombre_seguro("../../etc/pas:swd?.PDF") == "pas_swd_.pdf"
    assert nombre_seguro("Factura Nº 12 (copia).jpg") == "Factura Nº 12 (copia).jpg"
    assert nombre_seguro("...") == "adjunto"
    assert len(nombre_seguro("a" * 300 + ".pdf")) == 100


def test_adjuntar_copia_al_almacen_con_huella(sesion, ej, asiento, almacen, tmp_path):
    r = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "Luz enero.pdf", PDF))
    a = r.adjunto
    assert r.advertencias == [] and a.presente and a.tamano == len(PDF) and a.tipo_mime == "application/pdf"
    assert a.ruta_relativa == f"011/2026/X/{a.id:06d}_Luz enero.pdf" and a.nombre == "Luz enero.pdf"
    assert almacen.ruta(a).read_bytes() == PDF
    assert listar(sesion, asiento) == [a]
    assert verificar_almacen(sesion, almacen).correcto


def test_adjuntar_a_una_factura_usa_su_sentido(sesion, ej, almacen, tmp_path):
    f = Factura(ejercicio_id=ej.id, sentido="R", numero=1, fecha_contable=date(2026, 2, 1), total=D("10.00"))
    sesion.add(f)
    sesion.flush()
    a = adjuntar(sesion, almacen, ej, f, _fichero(tmp_path, "f.jpeg", JPG)).adjunto
    assert "/R/" in a.ruta_relativa and a.tipo_mime == "image/jpeg" and a.factura_id == f.id
    assert facturas_sin_justificante(sesion, ej) == []
    quitar(sesion, almacen, ej, a)
    assert facturas_sin_justificante(sesion, ej) == [f]


@pytest.mark.parametrize(
    "nombre, contenido",
    [("nota.txt", b"hola"), ("falso.pdf", b"no soy un pdf"), ("falso.jpg", PDF), ("vacio.pdf", b"")],
)
def test_rechaza_ficheros_no_validos(sesion, ej, asiento, almacen, tmp_path, nombre, contenido):
    with pytest.raises(AdjuntoInvalido):
        adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, nombre, contenido))
    assert sesion.scalars(select(Adjunto)).all() == []
    assert not almacen.raiz.exists() or not list(almacen.raiz.rglob("*.*"))


def test_rechaza_ficheros_demasiado_grandes(sesion, ej, asiento, almacen, tmp_path, monkeypatch):
    monkeypatch.setattr("conta_pridalac.servicios.adjuntos.MAXIMO_BYTES", 10)
    with pytest.raises(AdjuntoInvalido, match="máximo"):
        adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "grande.pdf", PDF))


def test_un_duplicado_identico_no_se_guarda_dos_veces(sesion, ej, asiento, almacen, tmp_path):
    primero = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    r = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "b.pdf", PDF))
    assert r.adjunto.id == primero.id and "ya estaba adjunto" in r.advertencias[0]
    assert len(listar(sesion, asiento)) == 1
    segundo = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "c.pdf", PDF + b"distinto")).adjunto
    assert [a.orden for a in listar(sesion, asiento)] == [1, 2] and segundo.orden == 2


def test_quitar_borra_el_fichero(sesion, ej, asiento, almacen, tmp_path):
    a = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    ruta = almacen.ruta(a)
    quitar(sesion, almacen, ej, a)
    assert not ruta.exists() and listar(sesion, asiento) == []


def test_sustituir_conserva_la_posicion_y_no_pierde_el_original_si_falla(sesion, ej, asiento, almacen, tmp_path):
    a1 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    a2 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "b.pdf", PDF + b"2")).adjunto
    with pytest.raises(AdjuntoInvalido):
        sustituir(sesion, almacen, ej, a1, _fichero(tmp_path, "mal.pdf", b"xx"))
    assert almacen.ruta(a1).exists()
    nuevo = sustituir(sesion, almacen, ej, a1, _fichero(tmp_path, "c.jpg", JPG)).adjunto
    assert [a.nombre for a in listar(sesion, asiento)] == ["c.jpg", "b.pdf"] and nuevo.orden == 1 and a2.orden == 2


def test_ejercicio_cerrado_no_admite_cambios(sesion, ej, asiento, almacen, tmp_path):
    a = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    ej.cerrado = True
    with pytest.raises(EjercicioCerrado):
        adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "b.pdf", PDF + b"2"))
    with pytest.raises(EjercicioCerrado):
        quitar(sesion, almacen, ej, a)


def test_verificar_detecta_ausentes_alterados_y_huerfanos(sesion, ej, asiento, almacen, tmp_path):
    a1 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    a2 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "b.pdf", PDF + b"2")).adjunto
    almacen.ruta(a1).unlink()
    almacen.ruta(a2).write_bytes(PDF + b"cambiado")
    (almacen.raiz / "011" / "2026" / "X" / "suelto.pdf").write_bytes(PDF)
    informe = verificar_almacen(sesion, almacen, empresa_codigo=11)
    assert informe.ausentes == [a1] and informe.alterados == [a2] and [p.name for p in informe.huerfanos] == ["suelto.pdf"]
    assert not informe.correcto


def test_la_ruta_guardada_no_puede_salirse_del_almacen(sesion, ej, asiento, almacen):
    a = Adjunto(asiento_id=asiento.id, nombre="x.pdf", ruta_relativa="../fuera.pdf", tipo_mime="application/pdf")
    with pytest.raises(AdjuntoInvalido):
        almacen.ruta(a)


@pytest.mark.datos_reales
def test_traslado_de_los_justificantes_de_mgd(sesion, carga_mgd, carpeta_mgd_2021, tmp_path):
    from conftest import _carpeta_empresa

    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    almacen = AlmacenAdjuntos(tmp_path / "almacen")
    esperados = carga_mgd.adjuntos - len(carga_mgd.adjuntos_faltantes)
    assert trasladar_a_almacen(sesion, almacen, ej, _carpeta_empresa(carga_mgd.clave)) == esperados
    assert trasladar_a_almacen(sesion, almacen, ej, _carpeta_empresa(carga_mgd.clave)) == 0  # idempotente
    informe = verificar_almacen(sesion, almacen, empresa_codigo=ej.empresa.codigo)
    assert len(informe.alterados) == 0 and len(informe.huerfanos) == 0
    assert len(informe.ausentes) == len(carga_mgd.adjuntos_faltantes)


# ---------------------------------------------------------------------------- auditoría con almacén


def _codigos(hallazgos):
    return sorted(h.codigo for h in hallazgos)


def test_la_auditoria_sin_almacen_no_mira_los_ficheros(sesion, ej, asiento, almacen, tmp_path):
    from conta_pridalac.auditoria import auditar

    a = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF)).adjunto
    almacen.ruta(a).unlink()
    assert auditar(sesion, ej) == []


def test_la_auditoria_con_almacen_detecta_ausentes_alterados_huerfanos_y_gastos_sin_justificante(sesion, ej, asiento, almacen, tmp_path):
    from conta_pridalac.auditoria import auditar

    cuentas = {c.codigo: c.id for c in sesion.scalars(select(Cuenta))}
    factura = Factura(
        ejercicio_id=ej.id, sentido="R", numero=7, fecha_contable=date(2026, 2, 1), fecha_factura=date(2026, 2, 1), total=D("10.00"),
        cuenta_tercero_id=cuentas["41000001"], cuenta_contrapartida_id=cuentas["62900000"],
        ivas=[FacturaIva(base=D("10.00"), pct_iva=D("0.00"), cuota_iva=D("0.00"))],
    )
    grabar_factura(sesion, ej, factura)
    assert _codigos(auditar(sesion, ej, almacen=almacen)) == ["gasto_sin_justificante"]
    f = adjuntar(sesion, almacen, ej, factura, _fichero(tmp_path, "f.pdf", PDF)).adjunto
    a1 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "a.pdf", PDF + b"1")).adjunto
    a2 = adjuntar(sesion, almacen, ej, asiento, _fichero(tmp_path, "b.pdf", PDF + b"2")).adjunto
    assert auditar(sesion, ej, almacen=almacen) == []
    almacen.ruta(a1).unlink()
    almacen.ruta(a2).write_bytes(PDF + b"cambiado")
    (almacen.raiz / "011" / "2026" / "X" / "suelto.pdf").write_bytes(PDF)
    h = auditar(sesion, ej, almacen=almacen)
    assert _codigos(h) == ["fichero_huerfano", "justificante_alterado", "justificante_ausente"]
    assert {x.referencia for x in h} == {"a.pdf", "b.pdf", "suelto.pdf"}
    assert f.presente


def test_los_adjuntos_de_otro_ejercicio_no_cuentan(sesion, ej, asiento, almacen, tmp_path):
    from conta_pridalac.auditoria import auditar

    otro = Ejercicio(anio=2027, fecha_inicio=date(2027, 1, 1), fecha_fin=date(2027, 12, 31), empresa=ej.empresa)
    sesion.add(otro)
    sesion.flush()
    sesion.add(Adjunto(asiento_id=asiento.id, nombre="x.pdf", ruta_relativa="011/2026/X/x.pdf", tipo_mime="application/pdf"))
    sesion.flush()
    assert _codigos(auditar(sesion, ej)) == ["justificante_ausente"]
    assert auditar(sesion, otro) == []


@pytest.mark.datos_reales
def test_auditoria_con_almacen_tras_el_traslado_de_mgd(sesion, carga_mgd, tmp_path):
    from conftest import _carpeta_empresa

    from conta_pridalac.auditoria import auditar

    ej = sesion.get(Ejercicio, carga_mgd.ejercicio_id)
    almacen = AlmacenAdjuntos(tmp_path / "almacen")
    trasladar_a_almacen(sesion, almacen, ej, _carpeta_empresa(carga_mgd.clave))
    h = auditar(sesion, ej, almacen=almacen)
    assert len([x for x in h if x.codigo == "justificante_ausente"]) == len(carga_mgd.adjuntos_faltantes)
    assert [x for x in h if x.codigo in ("justificante_alterado", "fichero_huerfano")] == []
    sin = {f"R {f.numero}" for f in facturas_sin_justificante(sesion, ej)}
    assert {x.referencia for x in h if x.codigo == "gasto_sin_justificante"} == sin
