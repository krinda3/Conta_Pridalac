"""Importación de facturas desde el Excel de conciliación de Verifactu."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from conta_pridalac.db.modelos import Adjunto, Asiento, Banco, Cuenta, Ejercicio, Empresa, Factura, MovimientoBanco, Tercero, TipoIva, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos
from conta_pridalac.servicios.importar_facturas import importar, leer_excel, normalizar_nif, planificar

D = Decimal
CABECERA = ["Nombre archivo", "Empresa", "CIF", "Fecha factura", "Num. factura", "Base imponible", "% IVA", "Monto IVA", "Monto total", "Ruta completa", "Fecha Contable",
            "% IVA 2", "Monto IVA 2", "% IVA 3", "Monto IVA 3", "Fecha Pago", "Concepto Pago", "Subcuenta de Pago", "Desc. Subcuenta"]


def excel(filas, cabecera=CABECERA) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.append(cabecera)
    for f in filas:
        hoja.append(f)
    sal = BytesIO()
    libro.save(sal)
    return sal.getvalue()


def fila(nombre, cif, fecha, numero, base, pct, iva, total, ruta="", pago="", concepto="", sub="", pct2=None, iva2=None, contable="30/09/2026"):
    return ["", nombre, cif, fecha, numero, base, pct, iva, total, ruta, contable, pct2, iva2, None, None, pago, concepto, sub, ""]


@pytest.fixture
def entorno(sesion, tmp_path):
    emp = Empresa(codigo=2, nombre="Empresa A")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=emp)
    sesion.add_all([emp, ej])
    sesion.flush()
    c = {k: Cuenta(empresa_id=emp.id, codigo=k, nombre=n) for k, n in (("41000001", "PROVEEDOR UNO"), ("41000002", "LEROY"), ("62800000", "SUMINISTROS"), ("62900000", "OTROS GASTOS"), ("47200000", "IVA SOPORTADO"), ("55100002", "BANCO JAVIER"), ("57200003", "BANCO BBVA"))}
    sesion.add_all(c.values())
    sesion.flush()
    sesion.add_all([TipoIva(empresa_id=emp.id, sentido="R", numero=1, texto="General", pct_iva=D("21.00"), cuenta_iva_id=c["47200000"].id, por_defecto=True),
                    TipoIva(empresa_id=emp.id, sentido="R", numero=2, texto="Reducido", pct_iva=D("10.00"), cuenta_iva_id=c["47200000"].id)])
    uno = Tercero(empresa_id=emp.id, clase="P", nombre="PROVEEDOR UNO SL", nif="B13521992", cuenta_id=c["41000001"].id, cuenta_gasto_id=c["62800000"].id)
    leroy = Tercero(empresa_id=emp.id, clase="P", nombre="LEROY MERLIN", nif="B84818442", cuenta_id=c["41000002"].id, cuenta_gasto_id=c["62800000"].id)
    sesion.add_all([uno, leroy])
    sesion.add_all([Banco(empresa_id=emp.id, numero=1, clase="B", nombre="Banco Javier", cuenta_id=c["55100002"].id), Banco(empresa_id=emp.id, numero=2, clase="B", nombre="BBVA", cuenta_id=c["57200003"].id)])
    sesion.flush()
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%prueba\n")
    return sesion, ej, AlmacenAdjuntos(tmp_path / "almacen"), str(pdf), c


def test_normalizar_nif():
    assert normalizar_nif(" b-13.521 992 ") == "B13521992"


def test_leer_excel_reconoce_columnas_y_deduce_la_base_de_los_tipos_2_y_3(entorno):
    _, _, _, pdf, _ = entorno
    (f,) = leer_excel(excel([fila("PROVEEDOR UNO SL", "B-13521992", "21/07/2026", "A-1", "100.00", 21, "21.00", "133.20", pdf, "22/07/2026", "Pago A-1", "55100002", pct2=10, iva2="1.20")]))
    assert (f.nombre, f.nif, f.numero, f.total, f.fecha_pago, f.subcuenta) == ("PROVEEDOR UNO SL", "B-13521992", "A-1", D("133.20"), date(2026, 7, 22), "55100002")
    assert f.fecha_contable == date(2026, 9, 30) and f.lineas == [(D("100.00"), D("21.00"), D("21.00")), (D("12.00"), D("10.00"), D("1.20"))]
    with pytest.raises(ErrorContable, match="faltan columnas"):
        leer_excel(excel([], cabecera=["Empresa", "CIF"]))
    with pytest.raises(ErrorContable, match="No se puede abrir"):
        leer_excel(b"esto no es un excel")


def test_plan_detecta_duplicadas_terceros_nuevos_y_errores(entorno):
    sesion, ej, _, pdf, c = entorno
    base = [
        fila("PROVEEDOR UNO SL", "B-13521992", "21/07/2026", "A-1", "100.00", 21, "21.00", "121.00", pdf, "21/07/2026", "Pago", "55100002"),  # nif con guion: encuentra al tercero
        fila("LEROY MERLIN", "B84818442", "02/07/2026", "L-9", "10.00", 21, "2.10", "15.00", "", "", "", ""),  # 2,90 € más que base+IVA: línea sin IVA
        fila("PROVEEDOR NUEVO SA", "A99999999", "03/07/2026", "N-1", "50.00", 10, "5.00", "55.00", pdf, "03/07/2026", "Pago", "57200003"),
        fila("LEROY MERLIN", "B84818442", "02/07/2026", "L-9", "10.00", 21, "2.10", "15.00"),  # repetida en el Excel
        fila("LEROY MERLIN", "B84818442", "05/07/2026", "L-10", "10.00", 21, "2.10", "12.00"),  # total menor que base+IVA
        fila("LEROY MERLIN", "B84818442", "06/07/2026", "L-11", "10.00", 21, "2.10", "12.10", "", "06/07/2026", "Pago", "99999999"),  # banco que no existe
        fila("LEROY MERLIN", "B84818442", "06/10/2027", "L-12", "10.00", 21, "2.10", "12.10", contable="01/01/2027"),  # otro ejercicio
    ]
    planes = planificar(sesion, ej, "R", leer_excel(excel(base)))
    estados = [(p.estado, bool(p.errores)) for p in planes]
    assert estados == [("nueva", False), ("nueva", False), ("nueva", False), ("duplicada", False), ("nueva", True), ("nueva", True), ("nueva", True)]
    assert planes[0].tercero.nombre == "PROVEEDOR UNO SL" and not planes[0].crear_tercero
    assert any("sin IVA" in a for a in planes[1].avisos) and [l.base for l in planes[1].lineas] == [D("10.00"), D("2.90")]
    assert planes[2].crear_tercero and any("Se creará" in a for a in planes[2].avisos)
    assert planes[3].detalle == "Repetida en este mismo Excel"
    assert "menor que base + IVA" in planes[4].errores[0] and "99999999" in planes[5].errores[0] and "no es del ejercicio" in planes[6].errores[0]
    assert any("no trae ruta de PDF" in a for a in planes[1].avisos)


def test_importar_crea_factura_vencimiento_pago_y_pdf(entorno):
    sesion, ej, almacen, pdf, c = entorno
    planes = planificar(sesion, ej, "R", leer_excel(excel([
        fila("PROVEEDOR UNO SL", "B-13521992", "21/07/2026", "A-1", "100.00", 21, "21.00", "121.00", pdf, "22/07/2026", "Pago A-1", "55100002"),
        fila("PROVEEDOR NUEVO SA", "A99999999", "03/07/2026", "N-1", "50.00", 10, "5.00", "58.00", "", "", "", ""),
    ])))
    r = importar(sesion, almacen, ej, "R", planes, cuentas_de_gasto={"A99999999": "62800000"})
    sesion.commit()
    assert [n for _, n in r.importadas] == [1, 2] and r.movimientos == 1 and r.pdfs == 1 and r.terceros_nuevos == ["PROVEEDOR NUEVO SA (41000003)"]
    # ordenadas por fecha: primero la del 3/7 (N-1, nº 1) y luego la del 21/7 (A-1, nº 2)
    nueva, a1 = sesion.scalars(select(Factura).order_by(Factura.numero)).all()
    assert (nueva.numero_factura, nueva.total, nueva.tercero.nif, nueva.cuenta_contrapartida.codigo) == ("N-1", D("58.00"), "A99999999", "62800000")
    assert [(i.base, i.pct_iva, i.cuota_iva) for i in nueva.ivas] == [(D("50.00"), D("10.00"), D("5.00")), (D("3.00"), D("0.00"), D("0.00"))]  # lo que sobra, sin IVA
    assert (a1.numero_factura, a1.notas) == ("A-1", "Importada de Excel (fila 2)")
    # su asiento, su vencimiento ya pagado y el movimiento del banco
    asiento = sesion.scalars(select(Asiento).where(Asiento.tipo == 2, Asiento.numero == a1.numero)).one()
    assert sorted((ap.cuenta.codigo, ap.debe, ap.haber) for ap in asiento.apuntes) == [("41000001", D("0.00"), D("121.00")), ("47200000", D("21.00"), D("0.00")), ("62800000", D("100.00"), D("0.00"))]
    v = sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == a1.id)).one()
    assert (v.importe, v.fecha) == (D("-121.00"), date(2026, 7, 22)) and pendiente(sesion, v) == 0
    mov = sesion.scalars(select(MovimientoBanco)).one()
    assert (mov.banco.nombre, mov.texto, mov.fecha) == ("Banco Javier", "Pago A-1", date(2026, 7, 22)) and mov.pagos[0].importe == D("-121.00")
    assert len(sesion.scalars(select(Adjunto).where(Adjunto.factura_id == a1.id)).all()) == 1
    # la del proveedor nuevo no tenía pago: su vencimiento queda pendiente
    assert pendiente(sesion, sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == nueva.id)).one()) == D("-58.00")
    # volver a importar el mismo Excel: todo duplicado, no se graba nada más
    planes = planificar(sesion, ej, "R", leer_excel(excel([fila("PROVEEDOR UNO SL", "B13521992", "21/07/2026", "a-1", "100.00", 21, "21.00", "121.00")])))
    assert planes[0].estado == "duplicada" and "nº 2" in planes[0].detalle
    assert importar(sesion, almacen, ej, "R", planes).importadas == []


def test_terceros_con_el_mismo_nif_o_nif_de_otro_nombre(entorno):
    sesion, ej, _, _, c = entorno
    otro = Tercero(empresa_id=ej.empresa_id, clase="P", nombre="EURO DEPOT ESPAÑA SA", nif="A62018064", cuenta_id=c["41000002"].id)
    gen1 = Tercero(empresa_id=ej.empresa_id, clase="P", nombre="TICKETS TAXIS VARIOS", nif="VARIOSTAXI", cuenta_id=c["41000002"].id)
    gen2 = Tercero(empresa_id=ej.empresa_id, clase="P", nombre="TAXI SEGUNDO", nif="VARIOSTAXI", cuenta_id=c["41000001"].id)
    sesion.add_all([otro, gen1, gen2])
    sesion.flush()
    planes = planificar(sesion, ej, "R", leer_excel(excel([
        fila("Brico Depot (MAJADAHONDA)", "A62018064", "01/09/2026", "B-1", "10.00", 21, "2.10", "12.10"),  # mismo NIF, nombre parecido: sin avisos de coincidencia
        fila("E.S. Santa Ana, S.L.", "A62018064", "01/07/2026", "010561", "40.64", 21, "8.53", "49.17"),  # NIF de otro: se avisa
        fila("Daniel Martínez - Taxi", "VARIOSTAXI", "08/09/2026", "1186", "31.32", 10, "3.13", "34.45"),  # NIF genérico compartido por dos terceros
    ])))
    assert planes[0].tercero.id == otro.id and not any("revise" in a or "terceros con el NIF" in a for a in planes[0].avisos)
    assert planes[1].tercero.id == otro.id and any("El NIF A62018064 es de «EURO DEPOT ESPAÑA SA» pero el Excel dice «E.S. Santa Ana, S.L.»" in a for a in planes[1].avisos)
    assert planes[2].tercero.id in (gen1.id, gen2.id) and any("Hay 2 terceros con el NIF VARIOSTAXI" in a for a in planes[2].avisos) and not any("revise" in a for a in planes[2].avisos)


def test_misma_factura_con_otro_tercero_se_considera_ya_existente(entorno):
    sesion, ej, almacen, pdf, c = entorno
    planes = planificar(sesion, ej, "R", leer_excel(excel([fila("LEROY MERLIN", "B84818442", "01/07/2026", "010561", "40.64", 21, "8.53", "49.17")])))
    importar(sesion, almacen, ej, "R", planes)
    # mismo número y mismo importe pero con el NIF de otro proveedor (un error del Excel): no se graba una segunda vez
    sesion.add(Tercero(empresa_id=ej.empresa_id, clase="P", nombre="EURO DEPOT", nif="A62018064", cuenta_id=c["41000002"].id))
    sesion.flush()
    (plan,) = planificar(sesion, ej, "R", leer_excel(excel([fila("E.S. Santa Ana, S.L.", "A62018064", "01/07/2026", "010561", "40.64", 21, "8.53", "49.17")])))
    assert plan.estado == "duplicada" and "Parece la misma que la recibida nº 1 de «LEROY MERLIN»" in plan.detalle and not plan.importable


def test_excel_de_facturas_emitidas_de_verifactu(entorno):
    sesion, ej, almacen, _, c = entorno
    for codigo, nombre in (("43000001", "CLIENTE"), ("70500000", "INGRESOS"), ("47700000", "IVA REPERCUTIDO")):
        sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo=codigo, nombre=nombre))
    sesion.flush()
    sesion.add(TipoIva(empresa_id=ej.empresa_id, sentido="E", numero=1, texto="General", pct_iva=D("21.00"), cuenta_iva_id=sesion.scalar(select(Cuenta.id).where(Cuenta.codigo == "47700000")), por_defecto=True))
    sesion.add(Tercero(empresa_id=ej.empresa_id, clase="C", nombre="CEMPRON S.A.", nif="A28490027", cuenta_id=sesion.scalar(select(Cuenta.id).where(Cuenta.codigo == "43000001")),
                       cuenta_gasto_id=sesion.scalar(select(Cuenta.id).where(Cuenta.codigo == "70500000"))))
    sesion.flush()
    cabecera = ["Nº Factura", "Fecha", "Emisor NIF", "Emisor Nombre", "Fecha Expedición", "Fecha Operación", "Cliente Nombre", "Cliente NIF", "Cliente Dirección", "IBAN", "Base Imponible", "IVA %", "Cuota IVA", "IVA Total", "Total", "Estado", "Descripción", "Fecha Creación"]
    fila_e = ["26/12", "2026-09-28 00:00:00", "B00000020", "EMPRESA B SL", "2026-09-28", "2026-09-28", "CEMPRON S.A.", "A 28490027", "c/ P. del Prado 12", "", "1100", "21", "231", "231", "1331", "Pendiente", "Factura", "2026-10-14"]
    planes = planificar(sesion, ej, "E", leer_excel(excel([fila_e], cabecera=cabecera)))
    (p,) = planes
    assert p.importable and p.tercero.nombre == "CEMPRON S.A." and p.banco is None and p.avisos == [] and p.fila.fecha_factura == date(2026, 9, 28)
    r = importar(sesion, almacen, ej, "E", planes)
    assert r.movimientos == 0 and r.pdfs == 0 and len(r.importadas) == 1
    f = sesion.scalars(select(Factura).where(Factura.sentido == "E")).one()
    asiento = sesion.scalars(select(Asiento).where(Asiento.tipo == 1, Asiento.numero == f.numero)).one()
    assert sorted((ap.cuenta.codigo, ap.debe, ap.haber) for ap in asiento.apuntes) == [("43000001", D("1331.00"), D("0.00")), ("47700000", D("0.00"), D("231.00")), ("70500000", D("0.00"), D("1100.00"))]
    v = sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == f.id)).one()
    assert v.importe == D("1331.00") and pendiente(sesion, v) == D("1331.00")  # queda a cobrar
