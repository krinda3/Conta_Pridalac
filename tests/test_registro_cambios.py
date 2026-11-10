"""Registro de cambios inalterable: anota altas, cambios y bajas, encadena las huellas y detecta lo que se toque."""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from conta_pridalac.db import registro
from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Tercero
from conta_pridalac.db.registro import RegistroCambio

D = Decimal


def anotaciones(sesion):
    return list(sesion.scalars(select(RegistroCambio).order_by(RegistroCambio.id)))


def de(sesion, tabla):
    return [a for a in anotaciones(sesion) if a.tabla == tabla]


@pytest.fixture
def empresa(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    sesion.add(e)
    sesion.flush()
    return e


def test_la_primera_escritura_deja_la_situacion_de_partida_y_el_alta(sesion, empresa):
    primera, alta = anotaciones(sesion)[:2]
    assert (primera.tabla, primera.operacion) == ("sistema", "inicio") and json.loads(primera.datos)["filas"]["empresa"] == 0
    assert (alta.tabla, alta.operacion, alta.fila) == ("empresa", "alta", str(empresa.id)) and json.loads(alta.datos)["nombre"] == "Prueba S.L."
    assert registro.verificar(sesion) == []


def test_un_cambio_anota_el_antes_y_el_despues(sesion, empresa):
    empresa.nombre = "Otra S.L."
    sesion.flush()
    (cambio,) = [a for a in de(sesion, "empresa") if a.operacion == "cambio"]
    assert json.loads(cambio.datos) == {"nombre": ["Prueba S.L.", "Otra S.L."]}


def test_asignar_el_mismo_valor_no_anota_nada(sesion, empresa):
    antes = len(anotaciones(sesion))
    empresa.nombre = "Prueba S.L."
    sesion.flush()
    assert len(anotaciones(sesion)) == antes


def test_borrar_guarda_la_fila_entera(sesion, empresa):
    c = Cuenta(empresa_id=empresa.id, codigo="62800000", nombre="Suministros")
    sesion.add(c)
    sesion.flush()
    sesion.delete(c)
    sesion.flush()
    baja = de(sesion, "cuenta")[-1]
    assert baja.operacion == "baja" and json.loads(baja.datos)["codigo"] == "62800000" and json.loads(baja.datos)["nombre"] == "Suministros"
    assert registro.verificar(sesion) == []


def test_un_borrado_masivo_tambien_se_anota(sesion, empresa):
    sesion.add_all([Cuenta(empresa_id=empresa.id, codigo=f"6280000{i}", nombre=f"C{i}") for i in range(3)])
    sesion.flush()
    sesion.execute(delete(Cuenta).where(Cuenta.empresa_id == empresa.id))
    bajas = [a for a in de(sesion, "cuenta") if a.operacion == "baja"]
    assert sorted(json.loads(a.datos)["codigo"] for a in bajas) == ["62800000", "62800001", "62800002"]
    assert registro.verificar(sesion) == []


def test_una_importacion_grande_se_anota_en_un_lote(sesion, empresa):
    sesion.add_all([Cuenta(empresa_id=empresa.id, codigo=f"{i:08d}", nombre=f"C{i}") for i in range(registro.LOTE_A_PARTIR_DE + 5)])
    sesion.flush()
    (lote,) = de(sesion, "cuenta")
    assert lote.operacion == "alta_lote" and json.loads(lote.datos)["filas"] == registro.LOTE_A_PARTIR_DE + 5 and len(json.loads(lote.datos)["sha256"]) == 64


def test_lo_que_se_deshace_no_queda_anotado(sesion, empresa):
    sesion.commit()
    antes = len(anotaciones(sesion))
    sesion.add(Cuenta(empresa_id=empresa.id, codigo="62800000", nombre="X"))
    sesion.flush()
    assert len(anotaciones(sesion)) > antes
    sesion.rollback()
    assert len(anotaciones(sesion)) == antes


def test_los_datos_que_no_son_contables_no_se_anotan(sesion, empresa):
    antes = {a.tabla for a in anotaciones(sesion)}
    assert "registro_cambios" not in antes and "presentacion_evento" not in antes


def test_la_base_rechaza_modificar_o_borrar_el_registro(sesion, empresa):
    sesion.commit()
    with pytest.raises(DBAPIError, match="sólo se puede añadir"):
        sesion.execute(text("UPDATE registro_cambios SET usuario = 'otro'"))
    sesion.rollback()
    with pytest.raises(DBAPIError, match="sólo se puede añadir"):
        sesion.execute(text("DELETE FROM registro_cambios"))
    sesion.rollback()
    assert registro.verificar(sesion) == []


def _sin_disparadores(sesion):
    sesion.commit()
    sesion.execute(text("DROP TRIGGER registro_cambios_sin_update"))
    sesion.execute(text("DROP TRIGGER registro_cambios_sin_delete"))


def test_se_detecta_una_anotacion_modificada(sesion, empresa):
    sesion.add(Tercero(empresa_id=empresa.id, clase="P", nombre="Proveedor", nif="A1"))
    sesion.flush()
    _sin_disparadores(sesion)
    sesion.execute(text("UPDATE registro_cambios SET datos = REPLACE(datos, 'Proveedor', 'Otro') WHERE tabla = 'tercero'"))
    (problema,) = registro.verificar(sesion)
    assert "ha sido modificada" in problema and "tercero" in problema


def test_se_detecta_una_anotacion_borrada(sesion, empresa):
    sesion.add(Tercero(empresa_id=empresa.id, clase="P", nombre="Proveedor", nif="A1"))
    sesion.flush()
    _sin_disparadores(sesion)
    ultima = anotaciones(sesion)[-1].id
    sesion.execute(text(f"DELETE FROM registro_cambios WHERE id = {ultima - 1}"))
    (problema,) = registro.verificar(sesion)
    assert "Faltan anotaciones" in problema


def test_la_ultima_huella_es_la_de_la_ultima_anotacion(sesion, empresa):
    n, huella = registro.ultima_huella(sesion)
    ultima = anotaciones(sesion)[-1]
    assert (n, huella) == (ultima.id, ultima.huella)


def test_los_importes_y_fechas_se_guardan_como_texto(sesion, empresa):
    e = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=empresa)
    sesion.add(e)
    sesion.flush()
    assert json.loads(de(sesion, "ejercicio")[0].datos)["fecha_inicio"] == "2025-01-01"
    e.cerrado = True
    sesion.flush()
    assert json.loads(de(sesion, "ejercicio")[-1].datos) == {"cerrado": [False, True]}


def test_la_auditoria_avisa_si_la_cadena_se_rompe(sesion, empresa):
    from conta_pridalac.auditoria import auditar

    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=empresa)
    sesion.add(ej)
    sesion.flush()
    assert "registro_de_cambios_roto" not in {h.codigo for h in auditar(sesion, ej)}
    _sin_disparadores(sesion)
    sesion.execute(text("UPDATE registro_cambios SET usuario = 'otro' WHERE id = 2"))
    (h,) = [h for h in auditar(sesion, ej) if h.codigo == "registro_de_cambios_roto"]
    assert h.gravedad == "ERROR" and "ha sido modificada" in h.mensaje
