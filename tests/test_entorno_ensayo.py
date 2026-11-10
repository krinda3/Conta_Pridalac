"""Copia de ensayo: la marca, el aviso en pantalla y lo que deja de poderse hacer (presentar) o sólo se puede hacer (quitar datos para ensayar)."""
import json
from datetime import date

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Parametro
from conta_pridalac.db.registro import RegistroCambio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import ficha_390
from conta_pridalac.servicios.entorno import es_ensayo, exigir_base_real, exigir_ensayo, marcar_ensayo
from conta_pridalac.servicios.presentacion390 import crear_borrador, generar_fichero
from test_presentacion390 import ej, en_el_plazo  # noqa: F401 - fixtures
from test_web_auditoria import _sesion, cliente  # noqa: F401 - `cliente` es una fixture


def test_marcar_una_base_deja_la_marca_y_queda_anotado(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.")
    sesion.add(e)
    sesion.flush()
    assert not es_ensayo(sesion, e.id)
    assert marcar_ensayo(sesion, e.id) is True and marcar_ensayo(sesion, e.id) is False and es_ensayo(sesion, e.id)
    alta = [a for a in sesion.scalars(select(RegistroCambio)) if a.tabla == "parametro"]
    assert len(alta) == 1 and json.loads(alta[0].datos)["clave"] == "ENSAYO"


def test_las_protecciones(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.")
    sesion.add(e)
    sesion.flush()
    exigir_base_real(sesion, e.id, "presentar")
    with pytest.raises(ErrorContable, match="no está marcada como copia de ensayo"):
        exigir_ensayo(sesion, e.id, "quitar facturas")
    marcar_ensayo(sesion, e.id)
    exigir_ensayo(sesion, e.id, "quitar facturas")
    with pytest.raises(ErrorContable, match="copia de ensayo: no se puede presentar"):
        exigir_base_real(sesion, e.id, "presentar")


def test_una_copia_de_ensayo_no_genera_el_fichero_para_la_sede(sesion, ej, tmp_path):  # noqa: F811
    ficha_390.guardar_actividades(sesion, ej.empresa, [("Servicios técnicos", "a03", "8431")])
    ficha_390.guardar_representantes(sesion, ej.empresa, [("Lopez Garcia, Elena", "00000014Z", "261011", "Romero")])
    p, _ = crear_borrador(sesion, ej)  # el borrador y los cálculos sí se pueden ensayar
    marcar_ensayo(sesion, ej.empresa_id)
    with pytest.raises(ErrorContable, match="copia de ensayo"):
        generar_fichero(sesion, ej, p, tmp_path)
    assert p.estado == "borrador"


def test_quitar_facturas_sólo_en_una_copia_marcada(sesion):
    from conta_pridalac.servicios.ensayo import quitar_recibidas

    e = Empresa(codigo=1, nombre="Prueba S.L.")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    with pytest.raises(ErrorContable, match="no está marcada"):
        quitar_recibidas(sesion, ej, date(2026, 7, 1), date(2026, 9, 30))
    marcar_ensayo(sesion, e.id)
    assert quitar_recibidas(sesion, ej, date(2026, 7, 1), date(2026, 9, 30)).facturas == 0


def test_el_aviso_de_copia_de_ensayo_sale_en_las_pantallas(cliente):
    base = "/e/prueba/2026/auditoria"
    assert "COPIA DE ENSAYO" not in cliente.get(base).text
    s = _sesion(cliente)
    marcar_ensayo(s, s.scalar(select(Empresa.id)))
    s.commit()
    s.close()
    for pagina in (base, "/e/prueba/2026"):
        assert "COPIA DE ENSAYO" in cliente.get(pagina).text
