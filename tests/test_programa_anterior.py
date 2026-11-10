"""Carga de un respaldo del programa anterior y de sus comprobantes. Usa un respaldo sintético mínimo (los reales no están en el repositorio)."""
import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Adjunto, Apunte, Asiento, Banco, BienInversion, DeclaracionPresentada, Ejercicio, Empresa, Factura, MovimientoBanco, Parametro, Tercero, TipoIva, Vencimiento
from conta_pridalac.migracion.comprobantes import importar_comprobantes, informe
from conta_pridalac.migracion.programa_anterior import cargar_sdb, fecha_programa_anterior, netear_lineas
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos

P = "C0009"
COLS_012 = "NOMEMP VIAEMP DOMEMP NUMEMP ESCEMP PISEMP PUEEMP POSEMP POBEMP PROEMP TELEMP CIFEMP PERCON PERGAN IVAACR IVADEU".split()
COLS_415 = "COD NOM NIF DIR POS POB PRO TEL MAIL WEB OBS NO347 NOMCOM PAI CTAASO".split()
COLS_006 = ["EJE", "SER", "COD", "FEC", "DES", "ASI", "TIPINT", "CLIPRO", "FAC", "FECFAC", "TOTFAC"] + [f"{n}{i}" for n in ("BIVA", "PIVA", "CIVA", "PREC", "CREC") for i in range(1, 9)]
COLS_007 = "EJE SER COD LIN CTA DEB HAB DES".split()
COLS_051 = "COD NOM PROVEE FECCOM FECDIS PRE PORAMO VALRES VALSUE CIVAC CUEIN2 CUEAM2 CUEDO2 FECVEN CAUBAJ EJECOM SERCOM DOCCOM FACCOM".split()
COLS_052 = "COD ANO IMPAMO IMPAFI".split()
COLS_027 = "EJE SER DOC NUM VEN IMP COBPAG CONTA EJECON DOCCON".split()
COLS_440 = "ANO PER TIPDEC FECEMI FECENV NUMDEC CAS27 CAS29 CAS45 CAS46 CAS71 CAS87 EJECON SER DOC".split()
COLS_444 = "ANO PER TIPDEC LIN EJE SER COD NUMFAC FECFAC FECFIS BAS POR CUO CAS".split()
COLS_401 = "COD IVASOP IVAREP".split()
COLS_076 = "EJE SER DOC LIN EJEPAG SERPAG DOCPAG CTAPAG".split()


def _tabla(con, nombre, columnas, filas):
    con.execute(f"create table {nombre} ({', '.join(columnas)})")
    for fila in filas:
        valores = {**{c: None for c in columnas}, **fila}
        con.execute(f"insert into {nombre} values ({', '.join('?' * len(columnas))})", [valores[c] for c in columnas])


@pytest.fixture
def sdb(tmp_path):
    ruta = tmp_path / "C0009.SDB"
    con = sqlite3.connect(ruta)
    _tabla(con, f"{P}012", COLS_012, [{"NOMEMP": "EMPRESA DE PRUEBA S.L.", "VIAEMP": "CL", "DOMEMP": "MAYOR", "NUMEMP": "1", "POSEMP": 28001, "POBEMP": "madrid", "PROEMP": "MADRID", "CIFEMP": "B12345674", "PERCON": "Ana Pérez", "PERGAN": "12900000", "IVAACR": "47500000", "IVADEU": "47000000"}])
    _tabla(con, f"{P}020", ["COD", "INI", "FIN", "CER"], [{"COD": "2024", "INI": 20240101, "FIN": 20241231, "CER": "*"}, {"COD": "2025", "INI": 20250101, "FIN": 20251231, "CER": ""}])
    _tabla(con, f"{P}415", COLS_415, [
        {"COD": "41000001", "NOM": "SUMINISTROS ESPAÑA SA", "NIF": "A00000000", "DIR": "C/ Larga 1", "POS": 28002, "POB": "Madrid"},
        {"COD": "43000001", "NOM": "CLIENTE UNO", "NIF": "B11111111", "NO347": "*"},
        {"COD": "47200000", "NOM": "H.P. IVA soportado"}, {"COD": "47700000", "NOM": "H.P. IVA repercutido"},
        {"COD": "62800000", "NOM": "Suministros"}, {"COD": "70500000", "NOM": "Prestaciones de servicios"}, {"COD": "57200000", "NOM": "Banco"}, {"COD": "47000000", "NOM": "Hacienda deudora"}, {"COD": "47500000", "NOM": "Hacienda acreedora"},
    ])
    cab = {"ASI": 1, "FEC": 20240331}
    _tabla(con, f"{P}006", COLS_006, [
        {**cab, "EJE": "2024", "SER": "2", "COD": 1, "DES": "F-77-SUMINISTROS ESPAÑA SA", "CLIPRO": "41000001", "FAC": "F-77", "FECFAC": 20240320, "TOTFAC": 121, "BIVA1": 100, "PIVA1": 21, "CIVA1": 21},
        {**cab, "EJE": "2024", "SER": "1", "COD": 1, "DES": "A/1-CLIENTE UNO", "CLIPRO": "43000001", "FAC": "A/1", "FECFAC": 20240331, "TOTFAC": 242, "BIVA1": 200, "PIVA1": 21, "CIVA1": 42},
        {**cab, "EJE": "2025", "SER": "3", "COD": 4, "DES": "Pago", "ASI": 9, "FEC": 20250105},
        {**cab, "EJE": "2025", "SER": "4", "COD": 1, "DES": "Ajuste negativo", "ASI": 10, "FEC": 20250110},
        {**cab, "EJE": "2025", "SER": "9", "COD": 2, "DES": "Liquidacion IVA", "TIPINT": 7, "ASI": 11, "FEC": 20250331},
    ])
    _tabla(con, f"{P}007", COLS_007, [
        {"EJE": "2024", "SER": "2", "COD": 1, "LIN": 1, "CTA": "62800000", "DEB": 100, "HAB": 0},
        {"EJE": "2024", "SER": "2", "COD": 1, "LIN": 2, "CTA": "47200000", "DEB": 21, "HAB": 0},
        {"EJE": "2024", "SER": "2", "COD": 1, "LIN": 3, "CTA": "41000001", "DEB": 0, "HAB": 121},
        {"EJE": "2024", "SER": "1", "COD": 1, "LIN": 1, "CTA": "43000001", "DEB": 242, "HAB": 0},
        {"EJE": "2024", "SER": "1", "COD": 1, "LIN": 2, "CTA": "70500000", "DEB": 0, "HAB": 200},
        {"EJE": "2024", "SER": "1", "COD": 1, "LIN": 3, "CTA": "47700000", "DEB": 0, "HAB": 42},
        {"EJE": "2025", "SER": "3", "COD": 4, "LIN": 1, "CTA": "41000001", "DEB": 121, "HAB": 0},
        {"EJE": "2025", "SER": "3", "COD": 4, "LIN": 2, "CTA": "57200000", "DEB": 0, "HAB": 121},
        {"EJE": "2025", "SER": "4", "COD": 1, "LIN": 1, "CTA": "62800000", "DEB": -5, "HAB": 0},
        {"EJE": "2025", "SER": "4", "COD": 1, "LIN": 2, "CTA": "57200000", "DEB": 0, "HAB": 3},
        {"EJE": "2025", "SER": "9", "COD": 2, "LIN": 1, "CTA": "47000000", "DEB": 50, "HAB": 0},
        {"EJE": "2025", "SER": "9", "COD": 2, "LIN": 2, "CTA": "47200000", "DEB": 0, "HAB": 50},
    ])
    _tabla(con, f"{P}051", COLS_051, [{"COD": 1, "NOM": "NAVE", "PROVEE": "41000001", "FECCOM": 20240301, "FECDIS": 20240301, "PRE": 1000, "PORAMO": 10, "CIVAC": 210, "CUEIN2": "62800000", "CUEAM2": "62800000", "CUEDO2": "62800000"}])
    _tabla(con, f"{P}052", COLS_052, [{"COD": 1, "ANO": 2023, "IMPAMO": 100}, {"COD": 1, "ANO": 2024, "IMPAMO": 83.33}, {"COD": 1, "ANO": 2025, "IMPAMO": 100}])
    _tabla(con, f"{P}027", COLS_027, [{"EJE": "2024", "SER": "2", "DOC": 1, "NUM": 1, "VEN": 20240430, "IMP": 121, "COBPAG": "57200000"}])
    _tabla(con, f"{P}076", COLS_076, [{"EJE": "2024", "SER": "2", "DOC": 1, "LIN": 1, "EJEPAG": "2025", "SERPAG": "3", "DOCPAG": 4, "CTAPAG": "57200000"}])
    _tabla(con, f"{P}440", COLS_440, [{"ANO": 2025, "PER": 1, "TIPDEC": 1, "FECEMI": 20250415, "FECENV": 20250416, "NUMDEC": "3030000000001", "CAS27": 0, "CAS29": 50, "CAS45": 50, "CAS46": -50, "CAS71": -50, "CAS87": 50, "EJECON": "2025", "SER": "9", "DOC": 2}])
    _tabla(con, f"{P}444", COLS_444, [{"ANO": 2025, "PER": 1, "TIPDEC": 1, "LIN": 1, "EJE": "2024", "SER": "2", "COD": 1, "NUMFAC": "F-77", "FECFAC": 20240320, "FECFIS": 20250310, "BAS": 100, "POR": 21, "CUO": 21, "CAS": "29"}])
    _tabla(con, f"{P}401", COLS_401, [{"COD": 1, "IVASOP": "47200000", "IVAREP": "47700000"}])
    con.commit()
    con.close()
    return ruta


def test_netear_lineas():
    d = Decimal
    lineas = [{"cta": "A", "deb": d(100), "hab": d(0), "des": None}, {"cta": "A", "deb": d(-30), "hab": d(0), "des": None},
              {"cta": "B", "deb": d(0), "hab": d(-5), "des": None}, {"cta": "C", "deb": d(0), "hab": d(70), "des": None}]
    netas, neteadas, pasadas = netear_lineas(lineas)
    assert [(x["cta"], x["deb"], x["hab"]) for x in netas] == [("A", 70, 0), ("B", 5, 0), ("C", 0, 70)]
    assert (neteadas, pasadas) == (1, 1)


def test_fecha_programa_anterior():
    assert fecha_programa_anterior(20240331).isoformat() == "2024-03-31"
    assert fecha_programa_anterior(0) is None


def test_carga_sdb(sesion, sdb):
    antes = sdb.read_bytes()
    r = cargar_sdb(sesion, sdb, codigo_empresa=9)
    assert sdb.read_bytes() == antes  # el respaldo no se toca
    assert (r.ejercicios, r.cuentas, r.terceros, r.asientos, r.apuntes, r.facturas) == (2, 9, 2, 5, 12, 2)
    empresa = sesion.scalars(select(Empresa)).one()
    assert (empresa.nombre, empresa.nif, empresa.poblacion, empresa.domicilio, empresa.codigo_postal) == ("EMPRESA DE PRUEBA S.L.", "B12345674", "MADRID", "CL MAYOR 1", "28001")
    assert {e.anio: e.cerrado for e in sesion.scalars(select(Ejercicio))} == {2024: True, 2025: False}
    assert {t.nombre: (t.clase, t.no_incluir_347) for t in sesion.scalars(select(Tercero))} == {"SUMINISTROS ESPAÑA SA": ("P", False), "CLIENTE UNO": ("C", True)}

    recibida = sesion.scalars(select(Factura).where(Factura.sentido == "R")).one()
    assert (recibida.numero, recibida.numero_factura, recibida.total, recibida.fecha_factura.isoformat()) == (1, "F-77", Decimal("121.00"), "2024-03-20")
    assert recibida.cuenta_contrapartida.codigo == "62800000" and recibida.tercero.nif == "A00000000"
    (iva,) = recibida.ivas
    assert (iva.base, iva.pct_iva, iva.cuota_iva, iva.cuenta_iva.codigo) == (Decimal("100.00"), Decimal("21.00"), Decimal("21.00"), "47200000")
    emitida = sesion.scalars(select(Factura).where(Factura.sentido == "E")).one()
    assert emitida.cuenta_contrapartida.codigo == "70500000" and emitida.ivas[0].cuenta_iva.codigo == "47700000"


def test_subtipos_parametros_y_desde(sesion, sdb):
    r = cargar_sdb(sesion, sdb, codigo_empresa=9)
    assert {(a.tipo, a.subtipo) for a in sesion.scalars(select(Asiento))} == {(1, "M"), (2, "M"), (3, "M"), (4, "M"), (9, "P")}
    assert {p.clave: p.valor for p in sesion.scalars(select(Parametro))} == {"PYG": "12900000", "IVA_DEBE": "47000000", "IVA_HABER": "47500000"}
    assert r.asientos == 5


def test_desde_omite_ejercicios_anteriores(sesion, sdb):
    r = cargar_sdb(sesion, sdb, codigo_empresa=9, desde=2025)
    assert [e.anio for e in sesion.scalars(select(Ejercicio))] == [2025]
    assert (r.asientos, r.facturas) == (3, 0) and r.avisos == []


def test_bienes_y_tesoreria(sesion, sdb):
    r = cargar_sdb(sesion, sdb, codigo_empresa=9)
    assert (r.bienes, r.bancos, r.movimientos, r.pagos, r.vencimientos) == (1, 1, 1, 1, 1)
    bien = sesion.scalars(select(BienInversion)).one()
    assert (bien.descripcion, bien.precio_compra, bien.iva_soportado, bien.porcentaje_anual) == ("NAVE", Decimal("1000.00"), Decimal("210.00"), Decimal("10.00"))
    assert [(a.anio, a.importe_previsto, a.desde.isoformat()) for a in bien.amortizaciones] == [(2023, Decimal("100.00"), "2023-01-01"), (2024, Decimal("83.33"), "2024-03-01"), (2025, Decimal("100.00"), "2025-01-01")]
    assert [a.importe_contable for a in bien.amortizaciones] == [Decimal("100.00"), None, None]  # 2023 es anterior al primer ejercicio cargado (se da por amortizado); ni 2024 ni 2025 tienen asiento
    banco = sesion.scalars(select(Banco)).one()
    assert banco.cuenta.codigo == "57200000"
    mov = sesion.scalars(select(MovimientoBanco)).one()
    assert (mov.numero, mov.banco_id, mov.fecha.isoformat()) == (4, banco.id, "2025-01-05")
    (pago,) = mov.pagos
    venc = sesion.scalars(select(Vencimiento)).one()
    assert (pago.importe, pago.vencimiento_id, venc.importe, venc.fecha.isoformat()) == (Decimal("-121.00"), venc.id, Decimal("-121.00"), "2024-04-30")
    from conta_pridalac.domain.tesoreria import apuntes_de_movimiento, pendiente
    assert pendiente(sesion, venc) == 0
    assert dict(apuntes_de_movimiento(sesion, mov)) == {"57200000": Decimal("-121.00"), "41000001": Decimal("121.00")}


def test_catalogo_de_iva_y_ficha(sesion, sdb):
    cargar_sdb(sesion, sdb, codigo_empresa=9, ficha={"email": "info@prueba.es", "iban": "ES64 0182 0000 0000 0000 0001", "inventado": "x"})
    tipos = sesion.scalars(select(TipoIva).order_by(TipoIva.sentido, TipoIva.numero)).all()
    assert [(t.sentido, t.numero, t.pct_iva, t.cuenta_iva.codigo, t.por_defecto) for t in tipos if t.numero in (1, 4)] == [
        ("E", 1, Decimal("21.00"), "47700000", True), ("E", 4, Decimal("0.00"), "47700000", False), ("R", 1, Decimal("21.00"), "47200000", True), ("R", 4, Decimal("0.00"), "47200000", False)]
    empresa = sesion.scalars(select(Empresa)).one()
    assert (empresa.email, empresa.iban) == ("info@prueba.es", "ES64 0182 0000 0000 0000 0001")


def test_declaraciones_presentadas(sesion, sdb):
    from conta_pridalac.auditoria import auditar
    from conta_pridalac.servicios import iva as svc_iva

    r = cargar_sdb(sesion, sdb, codigo_empresa=9)
    assert r.declaraciones == 1
    d = sesion.scalars(select(DeclaracionPresentada)).one()
    assert (d.modelo, d.anio, d.periodo, d.resultado_liquidacion, d.resultado, d.a_compensar, d.justificante) == ("303", 2025, 1, Decimal("-50.00"), Decimal("-50.00"), Decimal("50.00"), "3030000000001")
    assert d.fecha_emision.isoformat() == "2025-04-15" and d.asiento.identificador == "9.2"
    (linea,) = d.lineas
    assert (linea.casilla, linea.cuota, linea.fecha_fiscal.isoformat()) == ("29", Decimal("21.00"), "2025-03-10") and linea.factura.numero == 1
    assert svc_iva.resultado_del_asiento(d.asiento) == Decimal("-50.00") and svc_iva.coincide_con_lo_presentado(d.asiento, d)
    ejercicio = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2025)).one()
    codigos = {h.codigo for h in auditar(sesion, ejercicio)}
    assert "liquidacion_iva_desactualizada" not in codigos and "liquidacion_distinta_de_la_presentada" not in codigos
    d.resultado_liquidacion = d.resultado = Decimal("-49.00")  # si lo presentado difiere, se avisa (y sólo se avisa)
    sesion.flush()
    assert "liquidacion_distinta_de_la_presentada" in {h.codigo for h in auditar(sesion, ejercicio)}


def test_importe_negativo_pasa_al_lado_contrario_y_descuadre_se_avisa(sesion, sdb):
    r = cargar_sdb(sesion, sdb, codigo_empresa=9)
    assert r.lineas_con_signo_negativo == 1
    a = sesion.scalars(select(Asiento).where(Asiento.tipo == 4)).one()
    assert [(x.debe, x.haber) for x in a.apuntes] == [(Decimal("0.00"), Decimal("5.00")), (Decimal("0.00"), Decimal("3.00"))]
    assert len(r.descuadrados) == 1 and "2025/4/1" in r.descuadrados[0]


def test_comprobantes(sesion, sdb, tmp_path):
    cargar_sdb(sesion, sdb, codigo_empresa=9)
    empresa = sesion.scalars(select(Empresa)).one()
    carpeta = tmp_path / "Comprobantes"
    (carpeta / "2024").mkdir(parents=True)
    (carpeta / "2025").mkdir()
    pdf = b"%PDF-1.4\n%contenido\n"
    (carpeta / "2024" / "C0009_F2024_2_1.PDF").write_bytes(pdf)  # factura recibida de un ejercicio CERRADO: se importa igualmente
    (carpeta / "2024" / "C0009_F2024_1_1.PDF").write_bytes(pdf + b"otro")
    (carpeta / "2025" / "C0009_F2025_3_4.PDF").write_bytes(b"\r\n--uuid:1\r\nContent-Type: application/pdf\r\n\r\n" + pdf)  # tesoreria -> asiento; PDF envuelto en una parte MIME
    (carpeta / "2025" / "C0009_F2025_2_99.PDF").write_bytes(pdf)  # sin asiento
    (carpeta / "2025" / "C0009_F2025_4_1.PDF").write_bytes(b"no es un pdf")  # rechazado
    (carpeta / "2025" / "C0009_303_2025_01.PDF").write_bytes(pdf)  # modelo 303 del 1T
    (carpeta / "2025" / "C0009_C303_2025_01.PDF").write_bytes(pdf)  # su complementaria, que no está en el respaldo
    (carpeta / "2025" / "C0009_111_2025_01.PDF").write_bytes(pdf)  # modelo 111 sin declaración en el respaldo
    (carpeta / "2025" / "C0001_F2025_2_1.PDF").write_bytes(pdf)  # de otra empresa
    res = importar_comprobantes(sesion, AlmacenAdjuntos(tmp_path / "almacen"), empresa, carpeta)
    assert (res.importados, res.a_facturas, res.a_asientos) == (3, 2, 1)
    assert [x.split("/")[-1] for x in res.sin_asiento] == ["C0009_F2025_2_99.PDF"]
    assert len(res.rechazados) == 1 and "C0009_F2025_4_1.PDF" in res.rechazados[0]
    assert res.a_declaraciones == 1 and res.declaraciones == [] and [x.split("/")[-1] for x in res.declaraciones_sin_registro] == ["C0009_111_2025_01.PDF", "C0009_C303_2025_01.PDF"]  # el 303 se enlaza con su declaración; la complementaria y el 111 no están en el respaldo
    d = sesion.scalars(select(DeclaracionPresentada)).one()
    assert d.pdf_nombre == "C0009_303_2025_01.PDF" and (tmp_path / "almacen" / d.pdf_ruta).read_bytes() == pdf and d.pdf_ruta.startswith("009/2025/D/")
    assert [x.split("/")[-1] for x in res.de_otra_empresa] == ["C0001_F2025_2_1.PDF"]
    assert res.facturas_sin_comprobante == {}
    assert all(a.presente for a in sesion.scalars(select(Adjunto)))
    texto = informe(res, "prueba")
    assert "SIN ASIENTO en la base: 1" in texto and "C0009_F2025_2_99.PDF" in texto
