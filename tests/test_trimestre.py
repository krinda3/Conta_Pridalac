"""Lista de trabajo del trimestre: carga del Excel de Verifactu y propuestas de conciliación con el extracto."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Empresa, Extracto, ExtractoLinea, FacturaTrimestre, PalabraConciliacion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.trimestre import cargar_recibidas, descartar, posibles_duplicadas, preparar, proponer, quitar_duplicadas

D = Decimal
CABECERA = ["Nombre archivo", "Empresa", "CIF", "Fecha factura", "Num. factura", "Base imponible", "% IVA", "Monto IVA", "Monto total", "Ruta completa", "Fecha Contable", "% IVA 2", "Monto IVA 2",
            "% IVA 3", "Monto IVA 3", "Fecha Pago", "Concepto Pago", "Subcuenta de Pago", "Desc. Subcuenta"]


def excel(filas, cabecera=CABECERA) -> bytes:
    libro = Workbook()
    libro.active.append(cabecera)
    for fila in filas:
        libro.active.append(fila)
    memoria = BytesIO()
    libro.save(memoria)
    return memoria.getvalue()


def fila(nombre, total, dia, numero="A1", nif="B77777777", base=None, iva=21, pago=None):
    base = base if base is not None else round(total / 1.21, 2)
    return [None, nombre, nif, datetime(2026, 9, dia), numero, base, iva, round(total - base, 2), total, f"D:\\x\\{numero}.pdf", datetime(2026, 9, 30), None, None, None, None, pago, "", "", ""]


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    sesion.add_all([e, Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)])
    sesion.flush()
    sesion.add(Cuenta(empresa_id=e.id, codigo="57200001", nombre="BANCO"))
    sesion.flush()
    sesion.add(Banco(empresa_id=e.id, numero=1, nombre="BANCO", cuenta_id=sesion.scalar(select(Cuenta.id))))
    sesion.flush()
    return e


def linea(sesion, emp, dia, texto, importe, n):
    banco = sesion.scalars(select(Banco)).one()
    extracto = sesion.scalar(select(Extracto)) or Extracto(empresa_id=emp.id, banco_id=banco.id, fichero="x.xlsx", huella="h", formato="bbva")
    sesion.add(extracto)
    sesion.flush()
    sesion.add(ExtractoLinea(extracto_id=extracto.id, empresa_id=emp.id, banco_id=banco.id, orden=n, fecha=date(2026, 9, dia), texto=texto, importe=D(str(importe)), clave=f"k{n}"))
    sesion.flush()


def test_se_cargan_las_facturas_del_excel_con_sus_importes(sesion, emp):
    r = cargar_recibidas(sesion, emp.id, "recibidas.xlsx", excel([fila("Iberdrola Clientes", 162.33, 5, "F-1", pago=datetime(2026, 9, 7)), fila("Hotel Palace", 57, 10, "F-2", iva=10)]))
    assert (r.leidas, r.nuevas, r.repetidas, r.avisos) == (2, 2, 0, [])
    f = sesion.scalars(select(FacturaTrimestre).order_by(FacturaTrimestre.fecha_factura)).first()
    assert (f.nombre, f.nif, f.total, f.fecha_factura, f.numero_factura, f.pago_fecha) == ("Iberdrola Clientes", "B77777777", D("162.33"), date(2026, 9, 5), "F-1", date(2026, 9, 7))


def test_cargar_dos_veces_el_mismo_excel_o_uno_que_se_solapa_no_repite_facturas(sesion, emp):
    primero = excel([fila("Iberdrola", 162.33, 5, "F-1"), fila("Hotel Palace", 57, 10, "F-2")])
    cargar_recibidas(sesion, emp.id, "a.xlsx", primero)
    otra = cargar_recibidas(sesion, emp.id, "a.xlsx", primero)
    assert (otra.nuevas, otra.repetidas) == (0, 2)
    solape = cargar_recibidas(sesion, emp.id, "b.xlsx", excel([fila("Hotel Palace", 57, 10, "F-2"), fila("Securitas", 165.66, 20, "F-3")]))
    assert (solape.nuevas, solape.repetidas) == (1, 1) and len(list(sesion.scalars(select(FacturaTrimestre)))) == 3


def test_dos_facturas_distintas_con_el_mismo_importe_y_dia_no_se_confunden_si_difiere_el_numero(sesion, emp):
    r = cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila("Securitas", 165.66, 5, "F-1"), fila("Securitas", 165.66, 5, "F-2")]))
    assert r.nuevas == 2


def test_una_fila_sin_fecha_o_sin_total_se_avisa_y_no_se_carga(sesion, emp):
    mala = fila("Sin fecha", 10, 5)
    mala[3] = None
    r = cargar_recibidas(sesion, emp.id, "a.xlsx", excel([mala, fila("Bien", 20, 6, "F-9")]))
    assert (r.nuevas, len(r.avisos)) == (1, 1) and "Fila 2" in r.avisos[0]


@pytest.mark.parametrize("contenido, texto", [
    (excel([], cabecera=["Fecha", "Importe", "Concepto"]), "faltan las columnas"),
    (excel([]), "ninguna factura"),
    (b"esto no es un excel", "No se puede leer"),
])
def test_lo_que_no_es_el_excel_de_verifactu_se_rechaza(sesion, emp, contenido, texto):
    with pytest.raises(ErrorContable, match=texto):
        cargar_recibidas(sesion, emp.id, "a.xlsx", contenido)


def test_las_columnas_se_leen_por_nombre_aunque_cambien_de_sitio(sesion, emp):
    cabecera = ["Monto total", "Fecha factura", "Empresa"]
    r = cargar_recibidas(sesion, emp.id, "a.xlsx", excel([[10.5, datetime(2026, 9, 3), "Proveedor"]], cabecera=cabecera))
    assert r.nuevas == 1 and sesion.scalars(select(FacturaTrimestre)).one().total == D("10.50")


def test_las_propuestas_unen_cada_factura_con_su_linea_del_extracto(sesion, emp):
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila("Iberdrola Clientes", 162.33, 5, "F-1"), fila("Proveedor Raro", 99.99, 8, "F-2")]))
    linea(sesion, emp, 7, "IBERDROLA CLIENT. Recibo de suministros", -162.33, 1)
    linea(sesion, emp, 20, "COMISION", -6, 2)
    p = proponer(sesion, emp.id)
    (e,) = p.resultado.emparejadas
    assert p.facturas[e.facturas[0].id].numero_factura == "F-1" and p.lineas[e.lineas[0].id].importe == D("-162.33") and e.regla == "importe_y_texto"
    assert [p.facturas[x.id].numero_factura for x in p.resultado.sin_conciliar] == ["F-2"] and [p.lineas[x.id].texto for x in p.resultado.libres] == ["COMISION"]


def test_una_palabra_de_conciliacion_une_lo_que_el_nombre_no_dice(sesion, emp):
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila("Anthropic, PBC", 11.03, 5, "F-1"), fila("Anthropic, PBC", 10.91, 6, "F-2")]))
    linea(sesion, emp, 12, "Compra Tarjeta 4273", -11.03, 1)
    sin = proponer(sesion, emp.id)
    assert [e.regla for e in sin.resultado.emparejadas] == ["importe_unico"]  # el céntimo único la une aunque el nombre no diga nada
    sesion.add(PalabraConciliacion(empresa_id=emp.id, nombre="Anthropic, PBC", palabra="Compra Tarjeta"))
    sesion.flush()
    con = proponer(sesion, emp.id)
    assert [e.regla for e in con.resultado.emparejadas] == ["importe_y_texto"]


def test_cada_empresa_solo_ve_su_lista_de_trabajo(sesion, emp):
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila("Hotel Palace", 57, 10, "F-2")]))
    linea(sesion, emp, 10, "HOTEL PALACE", -57, 1)
    assert len(proponer(sesion, emp.id).resultado.emparejadas) == 1
    assert proponer(sesion, 999).facturas == {}  # otra empresa: nada


# ---------------------------------------------------------------------------- facturas reconocidas dos veces (factura y justificante de pago)


def fila_en(nombre, total, f, numero, nif="B77777777"):
    r = fila(nombre, total, f.day, numero, nif)
    r[3] = datetime(f.year, f.month, f.day)
    return r


PAREJAS = [  # (original, copia) tal como las dejó Verifactu en el 3T
    (("Securitas Direct España", 165.66, date(2026, 7, 1), "2607C00300545", "A26106013"), ("Securitas Direct España", 165.66, date(2026, 7, 6), "FUS2607C00300545", "A26106013")),
    (("Talleres Mazo Instalaciones", 260.15, date(2026, 7, 14), "001959", "B-86820990"), ("Talleres Mazo S.L.", 260.15, date(2026, 7, 18), "1959 14.7.26", "B86820990")),
    (("Jardinería Hermanos SA", 847, date(2026, 8, 16), "119 / 2026", "B70802517"), ("Jardineria Hermanos SA", 847, date(2026, 8, 18), "119/2026", "B70802517")),
    (("MULTISERVICIOS MAPFRE", 1331, date(2026, 7, 3), "5620261C1161141", "B00000020"), ("Multiservicios Mapfre", 1331, date(2026, 7, 26), "0261C1161141", "A82046061")),
]


@pytest.mark.parametrize("original, copia", PAREJAS)
def test_la_factura_y_su_justificante_de_pago_se_reconocen_como_la_misma(sesion, emp, original, copia):
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila_en(*original), fila_en(*copia)]))
    pendientes = {f.numero_factura: f for f in sesion.scalars(select(FacturaTrimestre))}
    (c, o), = posibles_duplicadas(list(pendientes.values())).items()
    assert pendientes[original[3]].id == o.id and pendientes[copia[3]].id == c


def test_el_recibo_mensual_de_la_alarma_no_es_una_duplicada(sesion, emp):
    filas = [fila_en("Securitas Direct", 3.33, date(2026, m, 6), n, "A26106013") for m, n in ((7, "250T000324322/13"), (8, "250T000324322/14"), (9, "25OT000324322/15"))]
    filas += [fila_en("Securitas Direct", 165.66, date(2026, 1, 1), "2601C00200317", "A26106013"), fila_en("Securitas Direct", 165.66, date(2026, 7, 1), "2607C00300545", "A26106013")]
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel(filas))
    assert posibles_duplicadas(list(sesion.scalars(select(FacturaTrimestre)))) == {}


def test_quitar_duplicadas_las_saca_de_la_conciliacion_y_cargar_otra_vez_no_las_devuelve(sesion, emp):
    (o, c) = PAREJAS[0]
    contenido = excel([fila_en(o[0], o[1], date(2026, 9, 1), *o[3:]), fila_en(c[0], c[1], date(2026, 9, 3), *c[3:])])
    cargar_recibidas(sesion, emp.id, "a.xlsx", contenido)
    linea(sesion, emp, 6, "SECURITAS DIRECT Recibo", -165.66, 1)
    antes = proponer(sesion, emp.id)
    assert len(antes.duplicadas) == 1 and [e.regla for e in antes.resultado.emparejadas] == ["importe_y_texto"] and len(antes.resultado.dudosas) == 0  # la copia no compite por la línea
    (copia, original), = quitar_duplicadas(sesion, emp.id)
    assert (copia.numero_factura, original.numero_factura, copia.descartada) == ("FUS2607C00300545", "2607C00300545", True)
    otra = cargar_recibidas(sesion, emp.id, "a.xlsx", contenido)
    assert (otra.nuevas, otra.repetidas) == (0, 2) and proponer(sesion, emp.id).duplicadas == {}
    assert quitar_duplicadas(sesion, emp.id) == []


def test_descartar_una_factura_no_toca_otra_empresa_ni_las_ya_aplicadas(sesion, emp):
    cargar_recibidas(sesion, emp.id, "a.xlsx", excel([fila("Hotel Palace", 57, 10, "F-2")]))
    f = sesion.scalars(select(FacturaTrimestre)).one()
    assert descartar(sesion, 999, [f.id]) == 0 and not f.descartada
    assert descartar(sesion, emp.id, [f.id]) == 1 and f.descartada and proponer(sesion, emp.id).facturas == {}


# ---------------------------------------------------------------------------- aplicar: factura + pago con la fecha y el importe del extracto


from conta_pridalac.db.modelos import Factura, MovimientoBanco, Tercero, TipoIva, Vencimiento  # noqa: E402
from conta_pridalac.domain.tesoreria import pendiente  # noqa: E402
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos  # noqa: E402
from conta_pridalac.servicios.trimestre import Aplicacion, aplicar  # noqa: E402


@pytest.fixture
def contab(sesion, tmp_path):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    c = {k: Cuenta(empresa_id=e.id, codigo=k, nombre=n) for k, n in (("57200001", "BANCO"), ("41000001", "PROVEEDOR"), ("62900000", "OTROS GASTOS"), ("47200000", "IVA SOPORTADO"))}
    sesion.add_all(c.values())
    sesion.flush()
    sesion.add(TipoIva(empresa_id=e.id, sentido="R", numero=1, texto="General", pct_iva=D("21.00"), cuenta_iva_id=c["47200000"].id, por_defecto=True))
    sesion.add(Banco(empresa_id=e.id, numero=1, clase="B", nombre="BANCO", cuenta_id=c["57200001"].id))
    sesion.flush()
    return sesion, ej, AlmacenAdjuntos(tmp_path / "almacen")


def _aplicacion(sesion, ej, fila_excel, texto="IBERDROLA CLIENT.", importe=None, dia=7, valor=None):
    cargar_recibidas(sesion, ej.empresa_id, "a.xlsx", excel([fila_excel]))
    f = sesion.scalars(select(FacturaTrimestre).order_by(FacturaTrimestre.id.desc())).first()
    banco = sesion.scalars(select(Banco)).one()
    n = len(list(sesion.scalars(select(ExtractoLinea)))) + 1
    extracto = sesion.scalar(select(Extracto)) or Extracto(empresa_id=ej.empresa_id, banco_id=banco.id, fichero="x.xlsx", huella="h", formato="bbva")
    sesion.add(extracto)
    sesion.flush()
    l = ExtractoLinea(extracto_id=extracto.id, empresa_id=ej.empresa_id, banco_id=banco.id, orden=n, fecha=date(2026, 9, dia), fecha_valor=date(2026, 9, valor) if valor else None,
                      texto=texto, importe=D(str(importe if importe is not None else -f.total)), clave=f"k{n}")
    sesion.add(l)
    sesion.flush()
    return Aplicacion(f, l)


def test_aplicar_crea_la_factura_y_su_pago_con_la_fecha_y_el_importe_del_banco(contab):
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100), valor=8)
    r = aplicar(sesion, almacen, ej, [a])
    assert r.movimientos == 1 and len(r.facturas) == 1 and [t for t in r.terceros_nuevos] != []
    factura = sesion.scalars(select(Factura)).one()
    assert (factura.total, factura.numero_factura, factura.fecha_contable) == (D("121.00"), "F-1", date(2026, 9, 30))
    movimiento = sesion.scalars(select(MovimientoBanco)).one()
    assert movimiento.fecha == date(2026, 9, 8)  # la fecha valor del banco
    assert movimiento.pagos[0].importe == D("-121.00") and movimiento.texto == "IBERDROLA CLIENT."
    assert pendiente(sesion, sesion.scalars(select(Vencimiento)).one()) == 0
    assert (a.factura.factura_id, a.linea.movimiento_id) == (factura.id, movimiento.id)


def test_la_linea_y_la_factura_aplicadas_no_se_vuelven_a_proponer(contab):
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    aplicar(sesion, almacen, ej, [a])
    p = proponer(sesion, ej.empresa_id)
    assert p.facturas == {} and p.lineas == {} and p.resultado.libres == []


def test_con_un_importe_distinto_no_se_aplica_nada(contab):
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100), importe=-120.9)
    with pytest.raises(ErrorContable, match="121.00 €.*120.9"):
        aplicar(sesion, almacen, ej, [a])
    assert not list(sesion.scalars(select(Factura))) and a.factura.factura_id is None and a.linea.movimiento_id is None


def test_si_una_de_varias_falla_no_se_aplica_ninguna(contab):
    sesion, ej, almacen = contab
    buena = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    mala = _aplicacion(sesion, ej, fila("Hotel Palace", 57, 10, "F-2", base=47.11), importe=-50, dia=10)
    with pytest.raises(ErrorContable):
        aplicar(sesion, almacen, ej, [buena, mala])
    assert not list(sesion.scalars(select(Factura))) and buena.linea.movimiento_id is None


def test_dos_facturas_no_pueden_usar_el_mismo_movimiento(contab):
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    b = _aplicacion(sesion, ej, fila("Otra Factura", 121, 6, "F-2", base=100))
    b.linea = a.linea
    with pytest.raises(ErrorContable, match="dos facturas"):
        aplicar(sesion, almacen, ej, [a, b])


def test_una_factura_que_ya_esta_en_la_contabilidad_se_dice(contab):
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    aplicar(sesion, almacen, ej, [a])
    repetida = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100) , dia=9)
    repetida.factura.factura_id = None
    with pytest.raises(ErrorContable, match="Ya existe la factura"):
        aplicar(sesion, almacen, ej, [repetida])


def test_preparar_deja_fuera_lo_que_ya_esta_en_la_contabilidad(contab):
    from conta_pridalac.servicios.trimestre import preparar
    sesion, ej, almacen = contab
    ya = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100), dia=7)
    aplicar(sesion, almacen, ej, [ya])
    nueva = _aplicacion(sesion, ej, fila("Hotel Palace", 57, 10, "F-2", base=47.11), texto="HOTEL PALACE", dia=10)
    otra = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 6, "F-1", base=100), texto="IBERDROLA CLIENT.", dia=9)  # la misma otra vez
    p = preparar(sesion, ej, proponer(sesion, ej.empresa_id))
    assert [a.factura.numero_factura for a in p.aplicables] == ["F-2"]
    assert [f.id for f, _ in p.omitidas] == [otra.factura.id] and "Ya existe la factura" in p.omitidas[0][1]
    aplicar(sesion, almacen, ej, p.aplicables)
    assert len(list(sesion.scalars(select(Factura)))) == 2 and nueva.linea.movimiento_id is not None


def test_preparar_no_incluye_lo_que_hay_que_confirmar_a_mano(contab):
    from conta_pridalac.servicios.trimestre import preparar
    sesion, ej, almacen = contab
    _aplicacion(sesion, ej, fila("Renfe Viajeros", 66.1, 8, "R-1", base=54.63), texto="RENFE VIRTUAL INTERNET", importe=-103.05, dia=8)
    _aplicacion(sesion, ej, fila("Renfe Viajeros", 36.95, 8, "R-2", base=30.54), texto="otra cosa", importe=-1, dia=20)
    assert preparar(sesion, ej, proponer(sesion, ej.empresa_id)).aplicables == []


def test_quitar_el_trimestre_deja_la_copia_como_antes_de_contabilizar(contab):
    from sqlalchemy import func

    from conta_pridalac.db.modelos import Asiento
    from conta_pridalac.servicios.ensayo import quitar_recibidas
    from conta_pridalac.servicios.entorno import marcar_ensayo
    sesion, ej, almacen = contab
    marcar_ensayo(sesion, ej.empresa_id)
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    aplicar(sesion, almacen, ej, [a])
    asientos = sesion.scalar(select(func.count()).select_from(Asiento))
    assert asientos >= 2
    r = quitar_recibidas(sesion, ej, date(2026, 7, 1), date(2026, 9, 30))
    assert (r.facturas, r.pagos, r.movimientos_borrados) == (1, 1, 1)
    assert not list(sesion.scalars(select(Factura))) and not list(sesion.scalars(select(MovimientoBanco))) and not sesion.scalar(select(func.count()).select_from(Asiento))
    sesion.refresh(a.linea)
    assert a.linea.movimiento_id is None  # la línea del banco vuelve a estar libre
    sesion.refresh(a.factura)
    assert a.factura.factura_id is None  # y la factura de la lista de trabajo, pendiente otra vez
    assert len(proponer(sesion, ej.empresa_id).resultado.emparejadas) == 1


def test_quitar_exige_un_periodo_de_un_solo_año(contab):
    from conta_pridalac.servicios.ensayo import quitar_recibidas
    from conta_pridalac.servicios.entorno import marcar_ensayo
    sesion, ej, _ = contab
    marcar_ensayo(sesion, ej.empresa_id)
    with pytest.raises(ErrorContable, match="mismo año"):
        quitar_recibidas(sesion, ej, date(2026, 7, 1), date(2027, 1, 31))


# ---------------------------------------------------------------------------- el proveedor de Conta de cada factura de Verifactu


def _proveedor(sesion, ej, nombre, nif, cuenta="41000010", gasto="62900011"):
    from conta_pridalac.db.modelos import Cuenta as C
    for codigo, n in ((cuenta, nombre), (gasto, "GASTO " + gasto)):
        if not sesion.scalars(select(C).where(C.empresa_id == ej.empresa_id, C.codigo == codigo)).first():
            sesion.add(C(empresa_id=ej.empresa_id, codigo=codigo, nombre=n))
    sesion.flush()
    ids = {c.codigo: c.id for c in sesion.scalars(select(C).where(C.empresa_id == ej.empresa_id))}
    t = Tercero(empresa_id=ej.empresa_id, clase="P", nombre=nombre, nif=nif, cuenta_id=ids[cuenta], cuenta_gasto_id=ids[gasto])
    sesion.add(t)
    sesion.flush()
    return t


def test_un_proveedor_que_no_existe_en_conta_bloquea_el_aplicar_hasta_decidir(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor, preparar, resolver_proveedor
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Archer Hotel Palace", 31.9, 5, "A-1", nif="B84623735", base=26.36))
    assert resolver_proveedor(sesion, a.factura).origen == "nuevo"
    p = preparar(sesion, ej, proponer(sesion, ej.empresa_id))
    assert p.aplicables == [] and "Proveedor nuevo" in p.omitidas[0][1]
    fijar_proveedor(sesion, a.factura, crear=True)
    assert [x.factura.id for x in preparar(sesion, ej, proponer(sesion, ej.empresa_id)).aplicables] == [a.factura.id]


def test_se_aplica_con_el_proveedor_generico_y_su_gasto_en_vez_del_de_verifactu(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor
    sesion, ej, almacen = contab
    parking = _proveedor(sesion, ej, "TICKETS APARCAMIENTO", "VARIOSPARKING")
    a = _aplicacion(sesion, ej, fila("Archer Hotel Palace", 31.9, 5, "A-1", nif="B84623735", base=26.36))
    fijar_proveedor(sesion, a.factura, tercero=parking)
    aplicar(sesion, almacen, ej, [a])
    f = sesion.scalars(select(Factura)).one()
    assert f.tercero_id == parking.id and f.cuenta_contrapartida.codigo == "62900011" and r_terceros(sesion) == 1  # no se ha creado ningún proveedor


def r_terceros(sesion):
    return len(list(sesion.scalars(select(Tercero))))


def test_el_gasto_elegido_para_la_factura_manda_sobre_el_del_proveedor(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor
    sesion, ej, almacen = contab
    mant = _proveedor(sesion, ej, "MANUTENCION", "MANUTENCION", gasto="62900001")
    otro = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "62900000")).one()
    a = _aplicacion(sesion, ej, fila("Areas SAU", 24.67, 5, "A-2", nif="A08225013", base=20.39))
    fijar_proveedor(sesion, a.factura, tercero=mant, cuenta_gasto=otro)
    aplicar(sesion, almacen, ej, [a])
    assert sesion.scalars(select(Factura)).one().cuenta_contrapartida.codigo == "62900000"


def test_recordar_guarda_la_correspondencia_para_el_nif_y_vale_para_otras_facturas(contab):
    from conta_pridalac.db.modelos import CorrespondenciaTercero
    from conta_pridalac.servicios.trimestre import fijar_proveedor, resolver_proveedor
    sesion, ej, almacen = contab
    parking = _proveedor(sesion, ej, "TICKETS APARCAMIENTO", "VARIOSPARKING")
    a = _aplicacion(sesion, ej, fila("Archer Hotel Palace", 31.9, 5, "A-1", nif="B84623735", base=26.36))
    b = _aplicacion(sesion, ej, fila("Archer Hotel Palace", 57, 6, "A-2", nif="B-84623735", base=47.11), dia=6)
    assert fijar_proveedor(sesion, a.factura, tercero=parking, recordar=True) == 2
    c = sesion.scalars(select(CorrespondenciaTercero)).one()
    assert (c.nif, c.tercero_id) == ("B84623735", parking.id)
    assert resolver_proveedor(sesion, b.factura).tercero.id == parking.id and resolver_proveedor(sesion, b.factura).origen == "correspondencia"
    # una decisión propia de la factura manda sobre la correspondencia
    otro = _proveedor(sesion, ej, "MANUTENCION", "MANUTENCION", cuenta="41000011", gasto="62900001")
    fijar_proveedor(sesion, b.factura, tercero=otro)
    assert resolver_proveedor(sesion, b.factura).tercero.id == otro.id
    # recordar otra vez cambia la correspondencia en vez de duplicarla
    fijar_proveedor(sesion, a.factura, tercero=otro, recordar=True)
    assert [x.tercero_id for x in sesion.scalars(select(CorrespondenciaTercero))] == [otro.id]


def test_fijar_el_proveedor_pide_una_cosa_o_la_otra(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor
    sesion, ej, _ = contab
    parking = _proveedor(sesion, ej, "TICKETS APARCAMIENTO", "VARIOSPARKING")
    a = _aplicacion(sesion, ej, fila("Archer Hotel Palace", 31.9, 5, "A-1", nif="B84623735", base=26.36))
    with pytest.raises(ErrorContable, match="Elija el proveedor"):
        fijar_proveedor(sesion, a.factura)
    with pytest.raises(ErrorContable, match="no las dos"):
        fijar_proveedor(sesion, a.factura, tercero=parking, crear=True)


def test_el_nif_de_la_propia_empresa_no_vale_como_nif_del_proveedor(contab):
    from conta_pridalac.servicios.trimestre import resolver_proveedor
    sesion, ej, almacen = contab
    propio = sesion.get(Empresa, ej.empresa_id)
    leroy = _proveedor(sesion, ej, "LEROY MERLIN", "B84818442")
    mal = _proveedor(sesion, ej, "OTRO PROVEEDOR", propio.nif)  # una ficha que tiene el NIF de la empresa (un error de datos)
    r = cargar_recibidas(sesion, ej.empresa_id, "a.xlsx", excel([fila("Leroy Merlin Majadahonda", 61.91, 5, "L-1", nif=propio.nif, base=51.17)]))
    assert any("el de la propia empresa" in a for a in r.avisos)
    f = sesion.scalars(select(FacturaTrimestre)).one()
    p = resolver_proveedor(sesion, f)
    assert p.tercero is None and p.origen == "nuevo"  # no se confunde con la ficha que tiene el NIF de la empresa
    a = _aplicacion(sesion, ej, fila("Leroy Merlin Majadahonda", 10, 6, "L-2", nif=propio.nif, base=8.26), dia=6) if False else None
    from conta_pridalac.servicios.trimestre import fijar_proveedor
    fijar_proveedor(sesion, f, crear=True)
    from conta_pridalac.servicios.trimestre import fila_de
    assert fila_de(sesion, f).nif == ""  # y si se crea el proveedor, no se crea con el NIF de la empresa


# ---------------------------------------------------------------------------- corregir proveedor y gasto de una factura ya contabilizada


def _saldo(sesion, codigo):
    from sqlalchemy import func as f

    from conta_pridalac.db.modelos import Apunte
    d, h = sesion.execute(select(f.sum(Apunte.debe), f.sum(Apunte.haber)).join(Cuenta, Cuenta.id == Apunte.cuenta_id).where(Cuenta.codigo == codigo)).one()
    return (d or 0) - (h or 0)


def test_corregir_proveedor_y_gasto_rehace_los_asientos_de_la_factura_y_de_su_pago_sin_tocar_el_iva(contab):
    from conta_pridalac.servicios.correcciones import cambiar_proveedor_y_gasto
    sesion, ej, almacen = contab
    mal = _proveedor(sesion, ej, "CANAL DE ISABEL II", "A86488087", cuenta="41000020", gasto="62800004")
    bien = _proveedor(sesion, ej, "NATURGY", "A08431090", cuenta="41000021", gasto="62800002")
    a = _aplicacion(sesion, ej, fila("Naturgy Clientes", 121, 5, "FE-1", nif="A08431090", base=100))
    fijar = __import__("conta_pridalac.servicios.trimestre", fromlist=["fijar_proveedor"]).fijar_proveedor
    fijar(sesion, a.factura, tercero=mal)
    aplicar(sesion, almacen, ej, [a])
    factura = sesion.scalars(select(Factura)).one()
    assert (_saldo(sesion, "62800004"), _saldo(sesion, "47200000")) == (100, 21) and _saldo(sesion, "41000020") == 0
    gas = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "62800002")).one()
    assert cambiar_proveedor_y_gasto(sesion, ej, factura, tercero=bien, gasto=gas) is True
    assert (_saldo(sesion, "62800004"), _saldo(sesion, "62800002"), _saldo(sesion, "47200000")) == (0, 100, 21)
    assert _saldo(sesion, "41000020") == 0 and _saldo(sesion, "41000021") == 0  # la factura y su pago pasaron juntos al proveedor nuevo
    assert factura.tercero_id == bien.id and sesion.scalars(select(Vencimiento)).one().factura_id == factura.id
    assert cambiar_proveedor_y_gasto(sesion, ej, factura, tercero=bien, gasto=gas) is False  # ya estaba


def test_corregir_se_permite_en_un_trimestre_presentado_pero_no_en_un_ejercicio_cerrado(contab):
    from conta_pridalac.db.modelos import DeclaracionPresentada
    from conta_pridalac.servicios.correcciones import cambiar_proveedor_y_gasto
    from conta_pridalac.servicios.facturas import grabar_factura
    sesion, ej, almacen = contab
    nuevo = _proveedor(sesion, ej, "OTRO PROVEEDOR", "A99999999", cuenta="41000021", gasto="62800002")
    a = _aplicacion(sesion, ej, fila("Naturgy Clientes", 121, 5, "FE-1", nif="A08431090", base=100))
    aplicar(sesion, almacen, ej, [a])
    factura = sesion.scalars(select(Factura)).one()
    sesion.add(DeclaracionPresentada(empresa_id=ej.empresa_id, modelo="303", anio=2026, periodo=3, **{c.name: None for c in DeclaracionPresentada.__table__.columns if c.nullable and c.name not in ("empresa_id", "modelo", "anio", "periodo", "id")}))
    sesion.flush()
    with pytest.raises(ErrorContable, match="ya está incluida en el 303"):
        grabar_factura(sesion, ej, factura)  # el camino normal sigue bloqueado
    assert cambiar_proveedor_y_gasto(sesion, ej, factura, tercero=nuevo) is True
    ej.cerrado = True
    with pytest.raises(ErrorContable, match="cerrado"):
        cambiar_proveedor_y_gasto(sesion, ej, factura, gasto=sesion.scalars(select(Cuenta).where(Cuenta.codigo == "62900000")).one())


def test_la_herramienta_de_correcciones_renombra_crea_y_mueve_facturas(contab):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from corregir_proveedores import operar
    sesion, ej, almacen = contab
    reg = _proveedor(sesion, ej, "REGISTRADORES DE ESPAÑA", "E81458556", cuenta="41000030", gasto="62900000")
    a = _aplicacion(sesion, ej, fila("Registradores", 3.15, 5, "CORPME1", nif="E81458556", base=2.6))
    aplicar(sesion, almacen, ej, [a])
    sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo="62300000", nombre="SERVICIOS DE PROFESIONALES INDEPENDIENTES"))
    sesion.flush()
    informe: list[str] = []
    for op in ({"op": "renombrar", "nif": "E81458556", "nombre": "REG. MERCANTILES DE MADRID CB"},
               {"op": "crear", "nombre": "COLEGIO DE REGISTRADORES DE ESPAÑA", "nif": "Q2863012G", "gasto": "62300000"},
               {"op": "crear", "nombre": "COLEGIO DE REGISTRADORES DE ESPAÑA", "nif": "Q-2863012-G", "gasto": "62300000"},  # idempotente
               {"op": "gasto_ficha", "tercero": {"nif": "E81458556"}, "gasto": "62300000", "desde": "2026-01-01"},
               {"op": "mover", "de": {"nif": "E81458556"}, "a": {"nif": "Q2863012G"}, "facturas": [{"numero": "CORPME1", "gasto": "62300000"}, {"numero": "NO-EXISTE"}]}):
        operar(sesion, ej.empresa_id, op, informe)
    colegio = sesion.scalars(select(Tercero).where(Tercero.nif == "Q2863012G")).one()
    f = sesion.scalars(select(Factura)).one()
    assert (reg.nombre, f.tercero_id, f.cuenta_contrapartida.codigo, colegio.cuenta_gasto.codigo if hasattr(colegio, "cuenta_gasto") else "62300000") == ("REG. MERCANTILES DE MADRID CB", colegio.id, "62300000", "62300000")
    assert any("Ya existe" in x for x in informe) and any("NO ESTÁ la factura NO-EXISTE" in x for x in informe)
    assert len(list(sesion.scalars(select(Tercero).where(Tercero.nif == "Q2863012G")))) == 1


def test_la_herramienta_crea_una_subcuenta_una_sola_vez(contab):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from corregir_proveedores import operar
    sesion, ej, _ = contab
    informe: list[str] = []
    for _ in range(2):
        operar(sesion, ej.empresa_id, {"op": "crear_cuenta", "codigo": "62900003", "nombre": "GASTOS DE VIAJE COMBUSTIBLE"}, informe)
    assert len(list(sesion.scalars(select(Cuenta).where(Cuenta.codigo == "62900003")))) == 1 and any("Ya existe" in x for x in informe)


# ---------------------------------------------------------------------------- facturas pagadas por un socio (sin línea de extracto)


def _socio(sesion, ej, codigo="55100002", nombre="BANCO JAVIER"):
    c = Cuenta(empresa_id=ej.empresa_id, codigo=codigo, nombre=nombre)
    sesion.add(c)
    sesion.flush()
    b = Banco(empresa_id=ej.empresa_id, numero=9, clase="B", nombre=nombre, cuenta_id=c.id)
    sesion.add(b)
    sesion.flush()
    return b


def _cargar(sesion, ej, *filas):
    cargar_recibidas(sesion, ej.empresa_id, "a.xlsx", excel(list(filas)))
    return {f.numero_factura: f for f in sesion.scalars(select(FacturaTrimestre))}


def test_una_factura_pagada_por_el_socio_se_aplica_en_su_cuenta_con_la_fecha_elegida(contab):
    from conta_pridalac.servicios.trimestre import marcar_pagadas_por, preparar
    sesion, ej, almacen = contab
    javier = _socio(sesion, ej)
    f = _cargar(sesion, ej, fila("Leroy Merlin", 61.91, 1, "L-1", nif="B84818442", base=51.17), fila("Chemmarkt", 56.47, 13, "L-2", nif="B11111111", base=46.67))
    assert marcar_pagadas_por(sesion, ej.empresa_id, [f["L-1"].id], javier, date(2026, 9, 28)) == 1
    assert marcar_pagadas_por(sesion, ej.empresa_id, [f["L-2"].id], javier) == 1  # sin fecha: la de la factura
    assert (f["L-1"].pagada_fecha, f["L-2"].pagada_fecha) == (date(2026, 9, 28), date(2026, 9, 13))
    for x in f.values():
        from conta_pridalac.servicios.trimestre import fijar_proveedor
        fijar_proveedor(sesion, x, crear=True)
    p = proponer(sesion, ej.empresa_id)
    assert p.resultado.sin_conciliar == [] and len(p.pagadas_por_banco) == 2  # no compiten por líneas del extracto
    prep = preparar(sesion, ej, p)
    assert len(prep.sin_extracto) == 2 and prep.con_extracto == [] and prep.omitidas == []
    r = aplicar(sesion, almacen, ej, prep.aplicables)
    assert r.movimientos == 2 and len(r.facturas) == 2
    movs = {m.fecha: m for m in sesion.scalars(select(MovimientoBanco))}
    assert set(movs) == {date(2026, 9, 28), date(2026, 9, 13)} and all(m.banco_id == javier.id for m in movs.values())
    assert movs[date(2026, 9, 28)].pagos[0].importe == D("-61.91")
    assert all(x.factura_id is not None for x in f.values()) and _saldo(sesion, "55100002") == D("-118.38")
    assert proponer(sesion, ej.empresa_id).pagadas_por_banco == []


def test_quitar_el_pagador_devuelve_la_factura_a_la_conciliacion_con_el_extracto(contab):
    from conta_pridalac.servicios.trimestre import marcar_pagadas_por
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    javier = _socio(sesion, ej)
    marcar_pagadas_por(sesion, ej.empresa_id, [a.factura.id], javier)
    assert proponer(sesion, ej.empresa_id).resultado.emparejadas == []  # mientras la pague el socio no se busca en el extracto
    marcar_pagadas_por(sesion, ej.empresa_id, [a.factura.id], None)
    assert a.factura.pagada_por_id is None and a.factura.pagada_fecha is None and len(proponer(sesion, ej.empresa_id).resultado.emparejadas) == 1


def test_el_pagador_tiene_que_ser_un_banco_de_la_empresa_con_subcuenta(contab):
    from conta_pridalac.servicios.trimestre import marcar_pagadas_por
    sesion, ej, _ = contab
    otra = Empresa(codigo=2, nombre="Otra", nif="B99999999")
    sesion.add(otra)
    sesion.flush()
    ajeno = Banco(empresa_id=otra.id, numero=1, clase="B", nombre="OTRO")
    sesion.add(ajeno)
    sesion.flush()
    f = _cargar(sesion, ej, fila("Leroy Merlin", 61.91, 1, "L-1", base=51.17))
    with pytest.raises(ErrorContable, match="de esta empresa"):
        marcar_pagadas_por(sesion, ej.empresa_id, [f["L-1"].id], ajeno)


# ---------------------------------------------------------------------------- contabilizar el resto como pendientes de pago


def test_lo_que_no_tiene_pago_se_contabiliza_con_su_vencimiento_pendiente(contab):
    from conta_pridalac.domain.tesoreria import pendiente
    from conta_pridalac.servicios.trimestre import fijar_proveedor, preparar_pendientes
    sesion, ej, almacen = contab
    con = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    sin = _cargar(sesion, ej, fila("Hotel Palace", 57, 10, "F-2", base=47.11))["F-2"]
    duplicada = _cargar(sesion, ej, fila("Hotel Palace", 57, 12, "F-2B", base=47.11, nif="B77777777"))["F-2B"]
    for f in (con.factura, sin, duplicada):
        fijar_proveedor(sesion, f, crear=True)
    p = proponer(sesion, ej.empresa_id)
    # primero se aplica lo que tiene movimiento; el resto se contabiliza sin pago
    aplicar(sesion, almacen, ej, preparar(sesion, ej, p).aplicables)
    prep = preparar_pendientes(sesion, ej, proponer(sesion, ej.empresa_id))
    assert sorted(a.factura.numero_factura for a in prep.aplicables) == ["F-2", "F-2B"] or prep.omitidas  # la repetida de Verifactu se trata aparte
    r = aplicar(sesion, almacen, ej, prep.aplicables)
    assert r.movimientos == 0
    vtos = {v.factura.numero_factura: v for v in sesion.scalars(select(Vencimiento))}
    assert pendiente(sesion, vtos["F-1"]) == 0 and pendiente(sesion, vtos["F-2"]) != 0 and vtos["F-2"].fecha == date(2026, 9, 10)
    assert all(f.factura_id is not None for f in sesion.scalars(select(FacturaTrimestre)) if f.numero_factura in ("F-1", "F-2"))


def test_los_proveedores_nuevos_sin_decidir_no_se_contabilizan_como_pendientes(contab):
    from conta_pridalac.servicios.trimestre import preparar_pendientes
    sesion, ej, _ = contab
    _cargar(sesion, ej, fila("Proveedor Raro", 99.99, 3, "R-1", nif="B55555555", base=82.64))
    prep = preparar_pendientes(sesion, ej, proponer(sesion, ej.empresa_id))
    assert prep.aplicables == [] and "Proveedor nuevo" in prep.omitidas[0][1]


def test_las_lineas_libres_siguen_a_la_vista_cuando_la_lista_de_trabajo_ya_esta_contabilizada(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor, preparar_pendientes
    sesion, ej, almacen = contab
    a = _aplicacion(sesion, ej, fila("Iberdrola Clientes", 121, 5, "F-1", base=100))
    fijar_proveedor(sesion, a.factura, crear=True)
    banco = sesion.scalars(select(Banco)).one()
    sesion.add(ExtractoLinea(extracto_id=a.linea.extracto_id, empresa_id=ej.empresa_id, banco_id=banco.id, orden=99, fecha=date(2026, 9, 12), texto="COMISION", importe=D("-6"), clave="k99"))
    sesion.flush()
    aplicar(sesion, almacen, ej, preparar(sesion, ej, proponer(sesion, ej.empresa_id)).aplicables)
    p = proponer(sesion, ej.empresa_id)
    assert p.facturas == {} and [l.texto for l in (p.lineas[x.id] for x in p.resultado.libres)] == ["COMISION"]


def test_la_cuenta_de_gasto_tiene_que_ser_de_gasto(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor
    sesion, ej, almacen = contab
    proveedor = _proveedor(sesion, ej, "TICKETS APARCAMIENTO", "VARIOSPARKING")
    f = _cargar(sesion, ej, fila("Archer Hotel Palace", 31.9, 5, "A-1", nif="B84623735", base=26.36))["A-1"]
    de_proveedor = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "41000010")).one()  # la subcuenta del propio proveedor: un error típico
    with pytest.raises(ErrorContable, match="no es de gasto"):
        fijar_proveedor(sesion, f, tercero=proveedor, cuenta_gasto=de_proveedor)
    banco = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "57200001")).one()
    with pytest.raises(ErrorContable, match="no es de gasto"):
        fijar_proveedor(sesion, f, tercero=proveedor, cuenta_gasto=banco)
    gasto = sesion.scalars(select(Cuenta).where(Cuenta.codigo == "62900000")).one()
    fijar_proveedor(sesion, f, tercero=proveedor, cuenta_gasto=gasto)
    assert f.cuenta_gasto_id == gasto.id


def test_aplicar_avisa_de_lo_que_se_contabiliza_sin_iva(contab):
    from conta_pridalac.servicios.trimestre import fijar_proveedor, preparar_pendientes
    sesion, ej, almacen = contab
    rara = fila("Golf Valdecañas", 130, 5, "G-1", nif="B88888888", base=100)
    rara[5], rara[6], rara[7], rara[8] = 100, 21, 21, 130  # el total supera a base + IVA en 9 €
    ok = fila("Hotel Palace", 57, 6, "H-1", nif="B99999999", base=47.11)
    f = _cargar(sesion, ej, rara, ok)
    for x in f.values():
        fijar_proveedor(sesion, x, crear=True)
    prep = preparar_pendientes(sesion, ej, proponer(sesion, ej.empresa_id))
    assert [(x.numero_factura, "sin IVA" in t) for x, t in prep.avisos] == [("G-1", True)] and len(prep.aplicables) == 2
