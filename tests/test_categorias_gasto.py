"""Categorías de análisis del gasto: no cambian ningún asiento y se pueden fijar en ejercicios cerrados."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Apunte, Cuenta, Ejercicio, Empresa, Factura, FacturaIva, Tercero
from conta_pridalac.db.registro import RegistroCambio, verificar
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import categorias_gasto as cg
from conta_pridalac.servicios.facturas import grabar_factura

D = Decimal

REGLAS = {
    "categorias": {
        "GAS": {"nombre": "Gas", "tipo": "gasto"}, "ELECTRICIDAD": {"nombre": "Electricidad", "tipo": "gasto"},
        "COMBUSTIBLE": {"nombre": "Combustible", "tipo": "gasto"}, "COMIDAS": {"nombre": "Comidas", "tipo": "gasto"},
        "SERV_PROF": {"nombre": "Servicios profesionales", "tipo": "gasto"}, "INSTALACION": {"nombre": "Instalación", "tipo": "inversion", "amortizacion_anos": 5},
        "AMORTIZACION": {"nombre": "Amortizaciones", "tipo": "amortizacion"}, "SIN_CLASIFICAR": {"nombre": "Sin clasificar", "tipo": "gasto"},
    },
    "cuentas_prioritarias": {"623": "SERV_PROF", "68": "AMORTIZACION"},
    "cuenta_por_defecto": {"62800001": "SIN_CLASIFICAR", "62800002": "ELECTRICIDAD", "62900001": "COMIDAS"},
    "reglas_proveedor": [
        {"nombre_contiene": ["REPSOL", "CEPSA"], "categoria": "COMBUSTIBLE", "revisar": False},
        {"nombre_contiene": ["NATURGY"], "categoria": {"62800001": "GAS", "62800002": "ELECTRICIDAD"}, "revisar": False},
        {"nombre_contiene": ["CAMBIO ENERGETICO"], "categoria": "INSTALACION", "revisar": False},
    ],
    "excepciones_factura": [],
}


@pytest.fixture
def emp(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    cerrado = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e, cerrado=True)
    abierto = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, cerrado, abierto])
    sesion.flush()
    for codigo, nombre in (("62800001", "GAS"), ("62800002", "ELECTRICIDAD"), ("62900001", "COMIDAS"), ("62300000", "SERV PROF"), ("47200000", "IVA"), ("41000001", "PROVEEDOR"), ("68300000", "AMORT")):
        sesion.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    sesion.flush()
    cg.importar_catalogo(sesion, e.id, REGLAS)
    return e


def _c(sesion, codigo):
    return sesion.scalars(select(Cuenta).where(Cuenta.codigo == codigo)).one()


def factura(sesion, emp, anio, proveedor, cuenta, base, numero=None):
    ej = sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == emp.id, Ejercicio.anio == anio)).one()
    t = sesion.scalars(select(Tercero).where(Tercero.nombre == proveedor)).first() or Tercero(empresa_id=emp.id, clase="P", nombre=proveedor, cuenta_id=_c(sesion, "41000001").id)
    sesion.add(t)
    sesion.flush()
    f = Factura(sentido="R", fecha_contable=date(anio, 3, 1), fecha_factura=date(anio, 3, 1), numero_factura="X", tercero_id=t.id, cuenta_tercero_id=_c(sesion, "41000001").id,
                cuenta_contrapartida_id=_c(sesion, cuenta).id, total=D(base) * D("1.21"))
    f.ivas.append(FacturaIva(base=D(base), pct_iva=D("21.00"), cuota_iva=D(base) * D("0.21"), cuenta_iva_id=_c(sesion, "47200000").id))
    # un ejercicio cerrado no admite grabar facturas: las del cerrado se graban con el ejercicio abierto y se cierra después
    cerrado, ej.cerrado = ej.cerrado, False
    f = grabar_factura(sesion, ej, f).factura
    ej.cerrado = cerrado
    sesion.flush()
    return f


def test_el_catalogo_se_importa_con_sus_prefijos_de_cuenta(sesion, emp):
    gas = cg.categoria_por_codigo(sesion, emp.id, "ELECTRICIDAD")
    assert gas.cuentas == "62800002"
    assert cg.categoria_por_codigo(sesion, emp.id, "SERV_PROF").cuentas == "623"
    assert cg.importar_catalogo(sesion, emp.id, REGLAS)[0].startswith("Actualizada")  # idempotente


def test_clasificar_por_proveedor_cuenta_y_623(sesion, emp):
    naturgy_gas = factura(sesion, emp, 2025, "NATURGY IBERIA SA", "62800001", "100")
    naturgy_luz = factura(sesion, emp, 2025, "NATURGY IBERIA SA", "62800002", "50")
    repsol = factura(sesion, emp, 2025, "REPSOL", "62800001", "70")
    abogado = factura(sesion, emp, 2025, "UN ABOGADO", "62300000", "200")
    res = cg.clasificar_facturas(sesion, emp.id, REGLAS)
    assert res.facturas == 4 and not res.sin_categoria
    codigo = lambda f: sesion.get(type(cg.categoria_por_codigo(sesion, emp.id, "GAS")), f.categoria_gasto_id).codigo if f.categoria_gasto_id else None
    assert codigo(naturgy_gas) == "GAS"            # no coincide con la cuenta (62800001 es «sin clasificar»): se fija
    assert codigo(naturgy_luz) is None             # ya sale sola de la cuenta 62800002
    assert codigo(repsol) == "COMBUSTIBLE"
    assert codigo(abogado) is None                 # la 623 sale sola


def test_la_categoria_se_fija_en_ejercicio_cerrado_sin_tocar_el_asiento(sesion, emp):
    f = factura(sesion, emp, 2025, "REPSOL", "62800001", "70")
    antes = [(a.cuenta_id, a.debe, a.haber) for a in sesion.scalars(select(Apunte).order_by(Apunte.id))]
    assert cg.asignar_categoria(sesion, f, cg.categoria_por_codigo(sesion, emp.id, "COMBUSTIBLE"))
    assert not cg.asignar_categoria(sesion, f, cg.categoria_por_codigo(sesion, emp.id, "COMBUSTIBLE"))  # sin cambios
    assert [(a.cuenta_id, a.debe, a.haber) for a in sesion.scalars(select(Apunte).order_by(Apunte.id))] == antes
    ultimas = list(sesion.scalars(select(RegistroCambio).where(RegistroCambio.tabla == "factura").order_by(RegistroCambio.id.desc()).limit(1)))
    assert "categoria_gasto_id" in ultimas[0].datos                                      # queda en el registro de cambios
    assert verificar(sesion) == []


def test_no_se_asigna_una_categoria_de_otra_empresa(sesion, emp):
    otra = Empresa(codigo=2, nombre="Otra S.L.")
    sesion.add(otra)
    sesion.flush()
    ajena = cg.crear_o_actualizar_categoria(sesion, otra.id, "GAS", "Gas")
    f = factura(sesion, emp, 2026, "REPSOL", "62800001", "70")
    with pytest.raises(ErrorContable, match="otra empresa"):
        cg.asignar_categoria(sesion, f, ajena)


def test_informe_por_categoria_con_reparto_y_cuadre(sesion, emp):
    gasolinera = factura(sesion, emp, 2025, "REPSOL", "62800001", "100")
    factura(sesion, emp, 2025, "NATURGY IBERIA SA", "62800002", "40")
    factura(sesion, emp, 2026, "NATURGY IBERIA SA", "62800002", "30")
    cg.clasificar_facturas(sesion, emp.id, REGLAS)
    cg.repartir_factura(sesion, gasolinera, [(cg.categoria_por_codigo(sesion, emp.id, "COMIDAS"), D("15.00"), "tienda")])
    informe = cg.informe_por_categoria(sesion, emp.id)
    por = {f.categoria.codigo: f for f in informe.filas if f.categoria}
    assert por["COMBUSTIBLE"].por_anio == {2025: D("85.00")}
    assert por["COMIDAS"].por_anio == {2025: D("15.00")}
    assert por["ELECTRICIDAD"].por_anio == {2025: D("40.00"), 2026: D("30.00")}
    # lo categorizado suma lo mismo que el grupo 6 de los libros
    libros = sum(a.debe - a.haber for a in sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo.like("6%"))))
    assert sum(f.total for f in informe.filas) == libros == D("170.00")
    assert informe.total_gasto(2025) == D("140.00")


def test_el_reparto_no_puede_superar_el_gasto(sesion, emp):
    f = factura(sesion, emp, 2025, "REPSOL", "62800001", "100")
    with pytest.raises(ErrorContable, match="supera el gasto"):
        cg.repartir_factura(sesion, f, [(cg.categoria_por_codigo(sesion, emp.id, "COMIDAS"), D("100.01"), None)])


def test_amortizacion_teorica_informativa(sesion, emp):
    factura(sesion, emp, 2025, "CAMBIO ENERGETICO S.L.U.", "62800002", "1000")
    cg.clasificar_facturas(sesion, emp.id, {**REGLAS, "reglas_proveedor": REGLAS["reglas_proveedor"]})
    informe = cg.informe_por_categoria(sesion, emp.id)
    fila = next(f for f in informe.filas if f.categoria and f.categoria.codigo == "INSTALACION")
    assert fila.por_anio == {2025: D("1000.00")}
    assert fila.amortizacion_teorica == {2025: D("200.00")}  # 1000 / 5 años; lo contable no cambia


def test_apuntes_de_amortizacion_van_a_su_categoria(sesion, emp):
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
    ej = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2026)).one()
    grabar_asiento(sesion, ej, tipo=9, numero=1, sub=0, fecha=date(2026, 12, 31), concepto="Amort", subtipo="Q",
                   lineas=[LineaAsiento("68300000", D("500.00")), LineaAsiento("41000001", D("-500.00"))])
    informe = cg.informe_por_categoria(sesion, emp.id)
    assert any(f.categoria and f.categoria.codigo == "AMORTIZACION" and f.por_anio == {2026: D("500.00")} for f in informe.filas)


def test_pantalla_gastos_por_categoria(sesion, emp):
    """La pantalla y su detalle por proveedor, a través del programa web."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool
    import tempfile
    from pathlib import Path

    from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
    from conta_pridalac.web.app import crear_app
    from conta_pridalac.web.config import Configuracion

    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    s.flush()
    for codigo, nombre in (("62800001", "GAS"), ("47200000", "IVA"), ("41000001", "PROVEEDOR")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    cg.importar_catalogo(s, e.id, REGLAS)
    factura(s, e, 2025, "REPSOL", "62800001", "100")
    cg.clasificar_facturas(s, e.id, REGLAS)
    s.commit()
    s.close()
    with tempfile.TemporaryDirectory() as t:
        cliente = TestClient(crear_app(Configuracion(datos=Path(t) / "bd", almacen=Path(t) / "almacen", motores={"prueba": motor})))
        assert "gastos-categoria" in cliente.get("/e/prueba/2025").text  # está en el menú
        tabla = cliente.get("/e/prueba/2025/gastos-categoria/tabla").text
        assert "Combustible" in tabla and "100,00" in tabla and "GASTO CORRIENTE" in tabla


def _reglas_con_destino():
    reglas = {**REGLAS, "categorias": {k: dict(v) for k, v in REGLAS["categorias"].items()}}
    reglas["categorias"]["COMBUSTIBLE"]["cuenta_destino"] = "62900003"
    reglas["categorias"]["GAS"]["cuenta_destino"] = "62800001"
    reglas["categorias"]["INSTALACION"]["cuenta_destino"] = "21500000"
    reglas["cuentas_nuevas"] = {"62900003": "GASTOS DE VIAJE COMBUSTIBLE"}
    return reglas


def test_reclasificar_un_ejercicio_abierto_mueve_la_cuenta_y_la_ficha_sin_tocar_el_iva(sesion, emp):
    reglas = _reglas_con_destino()
    cg.importar_catalogo(sesion, emp.id, reglas)
    f = factura(sesion, emp, 2026, "REPSOL", "62800001", "100")
    cg.clasificar_facturas(sesion, emp.id, reglas)
    ej = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2026)).one()
    iva_antes = sum(a.debe - a.haber for a in sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo.like("472%"))))
    res = cg.reclasificar_ejercicio(sesion, emp.id, ej, reglas)
    assert res.cuentas_creadas == ["62900003 GASTOS DE VIAJE COMBUSTIBLE"] and len(res.facturas_movidas) == 1
    assert _c(sesion, "62900003").id == f.cuenta_contrapartida_id
    assert sesion.scalars(select(Tercero).where(Tercero.nombre == "REPSOL")).one().cuenta_gasto_id == _c(sesion, "62900003").id   # la ficha del proveedor
    saldo = lambda cod: sum(a.debe - a.haber for a in sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo == cod)))
    assert saldo("62900003") == D("100.00") and saldo("62800001") == D("0.00")
    assert sum(a.debe - a.haber for a in sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo.like("472%")))) == iva_antes   # el IVA no cambia
    assert cg.reclasificar_ejercicio(sesion, emp.id, ej, reglas).facturas_movidas == []                                                # idempotente


def test_un_ejercicio_cerrado_no_se_reclasifica(sesion, emp):
    reglas = _reglas_con_destino()
    cg.importar_catalogo(sesion, emp.id, reglas)
    cerrado = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2025)).one()
    with pytest.raises(ErrorContable, match="cerrado"):
        cg.reclasificar_ejercicio(sesion, emp.id, cerrado, reglas)


def test_las_inversiones_no_se_ponen_por_defecto_en_la_ficha(sesion, emp):
    reglas = _reglas_con_destino()
    cg.importar_catalogo(sesion, emp.id, reglas)
    factura(sesion, emp, 2026, "CAMBIO ENERGETICO S.L.U.", "62800002", "1000")
    cg.clasificar_facturas(sesion, emp.id, reglas)
    ej = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2026)).one()
    res = cg.reclasificar_ejercicio(sesion, emp.id, ej, {**reglas, "cuentas_nuevas": {**reglas["cuentas_nuevas"], "21500000": "OTRAS INSTALACIONES"}})
    assert len(res.facturas_movidas) == 1 and res.fichas == []


def test_regularizar_el_saldo_de_existencias_a_gasto(sesion, emp):
    from datetime import date as fecha
    sesion.add_all([Cuenta(empresa_id=emp.id, codigo="32100010", nombre="COMBUSTIBLE TRACTOR"), Cuenta(empresa_id=emp.id, codigo="62900002", nombre="GASOLEO")])
    sesion.flush()
    factura(sesion, emp, 2026, "GASOLEOS", "32100010", "250")
    ej = sesion.scalars(select(Ejercicio).where(Ejercicio.anio == 2026)).one()
    texto = cg.regularizar_saldo(sesion, emp.id, ej, prefijo="321", a="62900002", fecha=fecha(2026, 1, 1), concepto="Regularización")
    assert "250.00" in texto[0]
    saldo = lambda cod: sum(a.debe - a.haber for a in sesion.scalars(select(Apunte).join(Cuenta).where(Cuenta.codigo == cod)))
    assert saldo("32100010") == D("0.00") and saldo("62900002") == D("250.00")
    assert cg.regularizar_saldo(sesion, emp.id, ej, prefijo="321", a="62900002", fecha=fecha(2026, 1, 1), concepto="otra vez")[0].startswith("Las cuentas")   # sin saldo, no hace nada
    # en el informe, el gasto cuenta una vez (al comprar, en la 321); el asiento que lo consume no lo duplica
    informe = cg.informe_por_categoria(sesion, emp.id)
    assert sum(f.total for f in informe.filas if f.categoria and f.categoria.codigo == "GASOLEO") + sum(f.total for f in informe.filas if not f.categoria or f.categoria.codigo != "GASOLEO") == D("250.00")


def test_la_categoria_de_las_marcadas_se_cambia_en_un_ejercicio_cerrado_y_trimestre_presentado(sesion, emp):
    """Desde la pantalla de facturas recibidas: columna «Categoría» y acción sobre las marcadas, aunque el ejercicio esté cerrado y el 303 presentado."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool
    import tempfile
    from pathlib import Path

    from conta_pridalac.db.modelos import PRESENTADA, PresentacionAeat
    from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
    from conta_pridalac.web.app import crear_app
    from conta_pridalac.web.config import Configuracion

    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    s.flush()
    for codigo, nombre in (("62800001", "GAS"), ("47200000", "IVA"), ("41000001", "PROVEEDOR")):
        s.add(Cuenta(empresa_id=e.id, codigo=codigo, nombre=nombre))
    s.flush()
    cg.importar_catalogo(s, e.id, REGLAS)
    f = factura(s, e, 2025, "REPSOL", "62800001", "100")
    s.add(PresentacionAeat(empresa_id=e.id, modelo="303", anio=2025, periodo="1T", estado=PRESENTADA, casillas="{}"))
    s.scalars(select(Ejercicio)).one().cerrado = True
    s.commit()
    fid, combustible = f.id, cg.categoria_por_codigo(s, e.id, "COMBUSTIBLE").id
    s.close()
    with tempfile.TemporaryDirectory() as t:
        cliente = TestClient(crear_app(Configuracion(datos=Path(t) / "bd", almacen=Path(t) / "almacen", motores={"prueba": motor})))
        assert "Sin clasificar" in cliente.get("/e/prueba/2025/facturas-recibidas/tabla").text            # 62800001 no tiene categoría por sí sola
        paso1 = cliente.post("/e/prueba/2025/facturas-recibidas/accion/categoria", data={"ids": str(fid)})
        assert paso1.status_code == 200 and "Combustible" in paso1.text and "REPSOL" in paso1.text
        paso2 = cliente.post("/e/prueba/2025/facturas-recibidas/accion/categoria", data={"ids": str(fid), "categoria": str(combustible)})
        assert paso2.status_code == 200 and "cambiada" in paso2.headers["HX-Trigger"]
        assert "Combustible" in cliente.get("/e/prueba/2025/facturas-recibidas/tabla").text
        quitar = cliente.post("/e/prueba/2025/facturas-recibidas/accion/categoria", data={"ids": str(fid), "categoria": "auto"})
        assert quitar.status_code == 200
        assert cliente.post("/e/prueba/2025/facturas-recibidas/accion/categoria", data={"ids": str(fid), "categoria": "9999"}).text.count("Elija una categoría") == 1
