"""Extractos del banco: lectura de los cuatro formatos, guardado sin duplicados y cuadre con el Mayor."""
import itertools
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Empresa, Extracto, ExtractoLinea
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
from conta_pridalac.servicios.extractos import _importe, cuadrar_banco, importar_extracto, leer_extracto

D = Decimal


def excel(filas, hoja="Hoja") -> bytes:
    libro = Workbook()
    ws = libro.active
    ws.title = hoja
    for fila in filas:
        ws.append(fila)
    memoria = BytesIO()
    libro.save(memoria)
    return memoria.getvalue()


# Lo más reciente primero, como los descargan los bancos (el saldo es el posterior al movimiento)
CAIXA = excel([
    ["Movimientos de la cuenta ES91 2100 0418"], ["Importes expresados en euros"],
    ["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"],
    [datetime(2026, 3, 10), datetime(2026, 3, 10), "IBERDROLA CLIENT.", "Recibo de suministros", -100.5, 900.0],
    [datetime(2026, 3, 5), datetime(2026, 3, 5), "V.NEGOCIOS CRED.", "", -200.0, 1000.5],
    [datetime(2026, 3, 1), datetime(2026, 3, 1), "TRANSFERENCIA DE CLIENTE", "Fra 12", 300.5, 1200.5],
])
BBVA = excel([
    ["Movimientos"], [None], ["Titular", "EMPRESA A S.L."], ["Cuenta", "ES64 0182"], [None],
    [None, None, "F. CONTABLE", "F. VALOR", "CÓDIGO", "CONCEPTO", "BENEFICIARIO/ORDENANTE", "OBSERVACIONES", "IMPORTE", "SALDO", "DIVISA"],
    [None, None, "10/03/2026", "09/03/2026", "00007", "TRANSFERENCIAS", "BELMO Muebles", "Fact. D5 250150", -1442.75, 5000.0, "EUR"],
    [None, None, "01/03/2026", "01/03/2026", "00009", "INGRESO EN EFECTIVO", None, "-", 1000, 6442.75, "EUR"],
])
SANTANDER = excel([
    ["Titular", "Saldo disponible"], ["EMPRESA A S.L.", "309,99 EUR"], [None], ["Movimientos Fecha desde 01/03/2026"],
    ["Fecha Operación", "Fecha Valor", "Concepto", "Importe", "Divisa", "Saldo", "Divisa", "Código", "Información adicional"],
    ["12/03/2026", "10/03/2026", "Compra Anthropic, Anthropic.com, Tarjeta", -11.03, "EUR", 331.83, "EUR", "136", ""],
    ["11/03/2026", "09/03/2026", "Compra Anthropic, Anthropic.com, Tarjeta", -10.91, "EUR", 342.86, "EUR", "136", ""],
])
TARJETA = excel([  # los gastos vienen en positivo y sin saldo; el importe es texto
    ["Fecha", "Tarjeta", "Establecimiento", "Importe"],
    ["01/10/2025", "4273 6706 0932 0793", "TAXI 0698", "29,7 EUR"],
    ["02/10/2025", "4273 6706 0932 0793", "HOTEL PALACE", "1.041,10 EUR"],
    ["02/10/2025", "4273 6706 0932 0793", "DEVOLUCION TIENDA", "-8,25 EUR"],
])


def test_los_importes_se_entienden_como_los_dan_los_bancos():
    for texto, esperado in (("29,7 EUR", "29.70"), ("1.041,10 EUR", "1041.10"), ("-8,25", "-8.25"), ("1,234.56", "1234.56"), (12, "12.00"), (-3.99, "-3.99"), ("0,5", "0.50")):
        assert _importe(texto) == D(esperado), texto
    assert _importe("Importe") is None and _importe("") is None and _importe(None) is None


def test_caixabank_se_lee_por_nombre_de_columna_en_orden_cronologico_y_con_su_saldo():
    e = leer_extracto(CAIXA)
    assert e.formato == "caixabank" and [l.fecha for l in e.lineas] == [date(2026, 3, 1), date(2026, 3, 5), date(2026, 3, 10)]
    assert [l.importe for l in e.lineas] == [D("300.50"), D("-200.00"), D("-100.50")] and e.lineas[1].texto == "V.NEGOCIOS CRED." and e.lineas[0].mas_datos == "Fra 12"
    assert e.saltos == [] and e.saldo_inicial == D("900.00") and e.saldo_final == D("900.00") and not e.invertido
    assert (e.desde, e.hasta) == (date(2026, 3, 1), date(2026, 3, 10))


def test_bbva_con_cabecera_en_otra_fila_y_columnas_desplazadas():
    e = leer_extracto(BBVA)
    assert e.formato == "bbva" and len(e.lineas) == 2 and e.saltos == []
    assert e.lineas[1].texto == "TRANSFERENCIAS · BELMO Muebles" and e.lineas[1].mas_datos == "Fact. D5 250150" and e.lineas[1].fecha_valor == date(2026, 3, 9)
    assert e.lineas[0].importe == D("1000.00") and e.saldo_final == D("5000.00")


def test_santander_y_la_tarjeta():
    s = leer_extracto(SANTANDER)
    assert s.formato == "santander" and [l.saldo for l in s.lineas] == [D("342.86"), D("331.83")] and s.saltos == []
    t = leer_extracto(TARJETA)
    assert t.formato == "tarjeta" and t.invertido  # gastos en positivo: se da la vuelta para que sean haber
    assert [l.importe for l in t.lineas] == [D("-29.70"), D("-1041.10"), D("8.25")] and t.saldo_final is None


def test_un_extracto_de_tarjeta_que_ya_trae_los_gastos_en_negativo_no_se_invierte():
    recortado = excel([["Fecha", "Tarjeta", "Establecimiento", "Importe"], ["11/02/2026", "09/02/2026", "Compra Anthropic", -10], ["11/02/2026", "09/02/2026", "Compra Anthropic", -15.49]])
    e = leer_extracto(recortado)
    assert not e.invertido and [l.importe for l in e.lineas] == [D("-10.00"), D("-15.49")] and e.lineas[0].fecha_valor == date(2026, 2, 9)
    assert leer_extracto(TARJETA, invertir=False).lineas[0].importe == D("29.70")  # se puede forzar


def test_el_saldo_delata_las_lineas_que_faltan():
    falta_una = excel([["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"],
                       [datetime(2026, 3, 10), None, "A", "", -100.5, 900.0], [datetime(2026, 3, 1), None, "C", "", 300.5, 1200.5]])  # entre las dos faltaba el pago de 200
    e = leer_extracto(falta_una)
    assert len(e.saltos) == 1 and e.saltos[0].diferencia == D("-200.00")  # el importe de lo que falta: un pago de 200 and e.saltos[0].despues.texto == "A"


def test_una_fila_ilegible_se_avisa_y_no_se_pierde_en_silencio():
    mal = excel([["Fecha", "Tarjeta", "Establecimiento", "Importe"], ["01/10/2025", "4273", "TAXI", "29,7 EUR"], ["01/12/2025", "4273", "FINCA RESTAURANTE", "Importe"]])
    e = leer_extracto(mal)
    assert len(e.lineas) == 1 and len(e.avisos) == 1 and "fila 3" in e.avisos[0]


def test_solo_se_lee_la_primera_hoja_con_movimientos():
    libro = Workbook()
    libro.active.title = "Movimientos"
    for fila in (["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"], [datetime(2026, 3, 1), None, "A", "", 1, 1]):
        libro.active.append(fila)
    otra = libro.create_sheet("Hoja1")
    for fila in (["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"], [datetime(2026, 1, 1), None, "B", "", 2, 2]):
        otra.append(fila)
    memoria = BytesIO()
    libro.save(memoria)
    e = leer_extracto(memoria.getvalue())
    assert [l.texto for l in e.lineas] == ["A"] and any("Hoja1" in a for a in e.avisos)


def test_lo_que_no_es_un_extracto_se_rechaza():
    with pytest.raises(ErrorContable, match="No reconozco"):
        leer_extracto(excel([["Nombre", "Edad"], ["Ana", 30]]))
    with pytest.raises(ErrorContable, match="No se puede abrir"):
        leer_extracto(b"no soy un excel")


# ---------------------------------------------------------------------------- guardar sin duplicados y cuadrar con el Mayor


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    for codigo, nombre in (("57200001", "BANCO"), ("62900000", "OTROS SERVICIOS"), ("70000000", "VENTAS"), ("10000000", "CAPITAL"), ("52100001", "TARJETA")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cuenta = sesion.scalar(select(Cuenta.id).where(Cuenta.codigo == "57200001"))
    sesion.add(Banco(empresa_id=e.id, numero=1, nombre="CAIXABANK", cuenta_id=cuenta))
    sesion.flush()
    return ej


def banco_de(sesion):
    return sesion.scalars(select(Banco)).one()


def test_importar_dos_veces_o_con_solape_no_repite_ninguna_linea(sesion, ej):
    banco = banco_de(sesion)
    primera = importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    assert (primera.lineas, primera.nuevas, primera.repetidas, primera.extracto_id is not None) == (3, 3, 0, True)
    segunda = importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    assert (segunda.nuevas, segunda.repetidas, segunda.extracto_id) == (0, 3, None) and any("ya se había importado" in a for a in segunda.avisos)
    solape = excel([["Fecha", "Fecha valor", "Movimiento", "Más datos", "Importe", "Saldo"],
                    [datetime(2026, 3, 20), None, "NUEVO", "", -50.0, 850.0], [datetime(2026, 3, 10), None, "IBERDROLA CLIENT.", "Recibo", -100.5, 900.0]])
    tercera = importar_extracto(sesion, ej.empresa_id, banco, "otro.xlsx", solape)
    assert (tercera.nuevas, tercera.repetidas) == (1, 1)  # la de IBERDROLA ya estaba, aunque el fichero la describa distinto
    lineas = list(sesion.scalars(select(ExtractoLinea).order_by(ExtractoLinea.fecha)))
    assert [l.fecha.day for l in lineas] == [1, 5, 10, 20] and len(list(sesion.scalars(select(Extracto)))) == 2


def test_las_lineas_identicas_del_mismo_dia_se_guardan_todas_y_solo_una_vez(sesion, ej):
    banco = banco_de(sesion)
    repetidas = excel([["Fecha", "Tarjeta", "Establecimiento", "Importe"], ["11/02/2026", "x", "Compra Anthropic", -10], ["11/02/2026", "x", "Compra Anthropic", -10], ["11/02/2026", "x", "Compra Anthropic", -5]])
    assert importar_extracto(sesion, ej.empresa_id, banco, "t.xlsx", repetidas).nuevas == 3
    assert importar_extracto(sesion, ej.empresa_id, banco, "t.xlsx", repetidas).nuevas == 0
    assert len(list(sesion.scalars(select(ExtractoLinea)))) == 3


_NUMEROS = itertools.count(1)


def movimiento(sesion, ej, fecha, importe, subtipo=None, contra="62900000", numero=None):
    """Un movimiento del banco en el Mayor: positivo entra dinero (debe), negativo sale (haber)."""
    n = numero or next(_NUMEROS)
    return grabar_asiento(sesion, ej, tipo=4, numero=n, sub=0, fecha=fecha, concepto="prueba", subtipo=subtipo, lineas=[LineaAsiento("57200001", D(importe)), LineaAsiento(contra, -D(importe))])


def test_el_extracto_cuadra_con_el_mayor_cuando_todo_coincide(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "900.00", subtipo="A", contra="10000000")  # la apertura entra en el saldo, no en los movimientos
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    movimiento(sesion, ej, date(2026, 3, 5), "-200.00")
    movimiento(sesion, ej, date(2026, 3, 10), "-100.50")
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    c = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert (c.emparejadas, c.solo_extracto, c.solo_mayor) == (3, [], []) and c.saldo_extracto == c.saldo_mayor == D("900.00") and c.cuadra


def test_si_los_movimientos_cuadran_pero_el_saldo_viene_descuadrado_de_antes_se_dice(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "1000.00", subtipo="A", contra="10000000")  # en el Mayor se abrió con 1.000 y el banco tenía 900
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    movimiento(sesion, ej, date(2026, 3, 5), "-200.00")
    movimiento(sesion, ej, date(2026, 3, 10), "-100.50")
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    c = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert c.cuadran_los_movimientos and not c.cuadra and c.arrastra_una_diferencia
    assert (c.saldo_previo_extracto, c.saldo_previo_mayor, c.diferencia_previa, c.diferencia_de_saldo) == (D("900.00"), D("1000.00"), D("-100.00"), D("-100.00"))  # la diferencia ya estaba al empezar
    movimiento(sesion, ej, date(2026, 3, 12), "-5.00")  # un movimiento sólo en el Mayor: esto ya no es un arrastre
    sobra = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert not sobra.cuadran_los_movimientos and not sobra.arrastra_una_diferencia


def test_la_auditoria_dice_que_asientos_manuales_mueven_el_banco_sin_ser_movimientos(sesion, ej):
    from conta_pridalac.auditoria import ERROR, auditar

    movimiento(sesion, ej, date(2026, 5, 13), "1477.62", contra="70000000")  # el banco movido por un asiento manual (tipo 4), no por un movimiento de banco
    h = [x for x in auditar(sesion, ej) if x.codigo == "saldo_de_banco"]
    assert len(h) == 1 and h[0].gravedad == ERROR
    assert "Asientos que mueven la cuenta del banco sin ser movimientos de banco (suman 1477.62)" in h[0].mensaje and "(+1477.62)" in h[0].mensaje and "4." in h[0].mensaje


def test_la_cuenta_con_socios_admite_asientos_manuales_aunque_sea_un_banco_de_conta(sesion, ej):
    """La cuenta con socios (551) no es un banco con extracto: una regularización con un asiento manual no es un error de «saldo del banco». Un banco de verdad (572) sí lo sigue siendo."""
    from conta_pridalac.auditoria import auditar
    from conta_pridalac.db.modelos import Banco

    sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo="55100000", nombre="CUENTA CON SOCIOS"))
    sesion.add(Cuenta(empresa_id=ej.empresa_id, codigo="41008196", nombre="PROVEEDOR"))
    sesion.flush()
    sesion.add(Banco(empresa_id=ej.empresa_id, numero=4, nombre="SOCIOS", cuenta_id=sesion.scalar(select(Cuenta.id).where(Cuenta.codigo == "55100000"))))
    sesion.flush()
    grabar_asiento(sesion, ej, tipo=4, numero=7, fecha=date(2026, 3, 5), concepto="Regularizacion", subtipo="M", agrupar=False, lineas=[LineaAsiento("55100000", D("2.80")), LineaAsiento("41008196", D("-2.80"))])
    assert [h for h in auditar(sesion, ej) if h.codigo == "saldo_de_banco"] == []  # el asiento manual sobre la cuenta de socios no se señala
    movimiento(sesion, ej, date(2026, 3, 6), "10.00", contra="70000000")  # y uno sobre el banco real (572), sí
    assert len([h for h in auditar(sesion, ej) if h.codigo == "saldo_de_banco"]) == 1


def test_el_cuadre_dice_que_sobra_y_que_falta_en_cada_lado(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "900.00", subtipo="A", contra="10000000")
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    movimiento(sesion, ej, date(2026, 3, 10), "-100.50")
    movimiento(sesion, ej, date(2026, 3, 12), "-77.00")  # un apunte del Mayor que no está en el extracto
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)  # le falta en el Mayor el pago de 200 del día 5
    c = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert c.emparejadas == 2 and [l.importe for l in c.solo_extracto] == [D("-200.00")] and [a.importe for a in c.solo_mayor] == [D("-77.00")]
    assert not c.cuadra and (c.saldo_extracto, c.saldo_mayor, c.diferencia_de_saldo) == (D("900.00"), D("1023.00"), D("-123.00"))


def test_el_cuadre_admite_unos_dias_de_diferencia_entre_la_fecha_del_banco_y_la_del_mayor(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "900.00", subtipo="A", contra="10000000")
    movimiento(sesion, ej, date(2026, 3, 3), "300.50", contra="70000000")  # el banco lo llevó al 1
    movimiento(sesion, ej, date(2026, 3, 5), "-200.00")
    movimiento(sesion, ej, date(2026, 3, 9), "-100.50")  # y éste al 10
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    assert cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31)).cuadra
    sin_margen = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31), tolerancia=0)
    assert sin_margen.cuadra and len(sin_margen.fecha_distinta) == 2  # sin margen, se emparejan por la cantidad y se avisa de que la fecha es otra


def test_el_cierre_no_cuenta_en_el_saldo_ni_en_los_movimientos(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "900.00", subtipo="A", contra="10000000")
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    movimiento(sesion, ej, date(2026, 3, 5), "-200.00")
    movimiento(sesion, ej, date(2026, 3, 10), "-100.50")
    movimiento(sesion, ej, date(2026, 12, 31), "-900.00", subtipo="Z", contra="10000000")  # el cierre pone a cero la cuenta
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    assert cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31)).cuadra
    assert cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 12, 31)).cuadra  # a fin de año, con el cierre en el Mayor, sigue cuadrando


def test_un_banco_sin_cuenta_o_sin_extracto_no_cuadra(sesion, ej):
    banco = banco_de(sesion)
    c = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert not c.cuadra and c.lineas_en_el_periodo == 0 and c.saldo_extracto is None
    banco.cuenta_id = None
    with pytest.raises(ErrorContable, match="no tiene cuenta"):
        cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))


def test_el_pago_llevado_a_fin_de_trimestre_se_empareja_por_la_cantidad_y_se_avisa(sesion, ej):
    banco = banco_de(sesion)
    movimiento(sesion, ej, date(2026, 1, 1), "900.00", subtipo="A", contra="10000000")
    movimiento(sesion, ej, date(2026, 3, 1), "300.50", contra="70000000")
    movimiento(sesion, ej, date(2026, 3, 5), "-200.00")
    movimiento(sesion, ej, date(2026, 3, 31), "-100.50")  # el banco lo cargó el día 10 y el Mayor lo lleva al último día del trimestre
    importar_extracto(sesion, ej.empresa_id, banco, "caixa.xlsx", CAIXA)
    c = cuadrar_banco(sesion, ej, banco, date(2026, 3, 1), date(2026, 3, 31))
    assert c.cuadra and c.emparejadas == 3 and len(c.fecha_distinta) == 1
    linea, apunte = c.fecha_distinta[0]
    assert (linea.fecha, apunte.fecha, linea.importe) == (date(2026, 3, 10), date(2026, 3, 31), D("-100.50"))


def test_un_banco_que_ordena_cada_dia_a_su_manera_no_da_falsos_saltos_de_saldo():
    """BBVA da los días de más reciente a más antiguo, pero las líneas de un mismo día en orden cronológico: el orden lo marca la cadena del saldo."""
    bbva = excel([
        ["F. CONTABLE", "F. VALOR", "CONCEPTO", "BENEFICIARIO/ORDENANTE", "OBSERVACIONES", "IMPORTE", "SALDO"],
        ["05/03/2026", "05/03/2026", "ADEUDO", "D", "", -100, 875.0],
        ["02/03/2026", "02/03/2026", "PAGO", "A", "", -10, 990.0],
        ["02/03/2026", "02/03/2026", "PAGO", "B", "", -20, 970.0],
        ["02/03/2026", "02/03/2026", "INGRESO", "C", "", 5, 975.0],
    ])
    e = leer_extracto(bbva)
    assert e.saltos == [] and [l.texto.split(" · ")[1] for l in e.lineas] == ["A", "B", "C", "D"] and e.saldo_inicial == D("1000.00") and e.saldo_final == D("875.00")


def test_si_de_verdad_falta_una_linea_del_dia_se_sigue_avisando():
    falta = excel([
        ["F. CONTABLE", "F. VALOR", "CONCEPTO", "BENEFICIARIO/ORDENANTE", "OBSERVACIONES", "IMPORTE", "SALDO"],
        ["02/03/2026", "02/03/2026", "PAGO", "A", "", -10, 990.0],
        ["02/03/2026", "02/03/2026", "INGRESO", "C", "", 5, 950.0],  # entre una y otra faltan 45
    ])
    assert len(leer_extracto(falta).saltos) == 1
