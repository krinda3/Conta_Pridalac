from datetime import date

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import ficha_390
from tests.test_empresa import _empresa, cliente  # noqa: F401  (fixture)


def test_las_actividades_se_guardan_en_orden_y_se_validan(cliente):
    empresa, s = _empresa(cliente)
    try:
        ficha_390.guardar_actividades(s, empresa, [("Servicios técnicos de ingeniería", "a03", "8431"), ("", "", ""), ("Otra", "", "")])
        s.commit()
        assert [(a.orden, a.descripcion, a.codigo, a.epigrafe) for a in empresa.actividades] == [(0, "Servicios técnicos de ingeniería", "A03", "8431"), (1, "Otra", None, None)]
        ficha_390.guardar_actividades(s, empresa, [("Única", "B04", "")])
        assert [a.descripcion for a in empresa.actividades] == ["Única"]
        with pytest.raises(ErrorContable, match="descripción"):
            ficha_390.guardar_actividades(s, empresa, [("", "A03", "")])
        with pytest.raises(ErrorContable, match="código"):
            ficha_390.guardar_actividades(s, empresa, [("X", "ABCD", "")])
        with pytest.raises(ErrorContable, match="máximo"):
            ficha_390.guardar_actividades(s, empresa, [(f"A{i}", "", "") for i in range(7)])
    finally:
        s.close()


def test_los_representantes_se_guardan_y_se_validan(cliente):
    empresa, s = _empresa(cliente)
    try:
        ficha_390.guardar_representantes(s, empresa, [("Lopez Garcia de Soto Elena", "00000014z", "010120", "Madrid"), ("Gil Navarro Pedro Maria", "00000001R", "", "")])
        s.commit()
        r = empresa.representantes
        assert [(x.orden, x.nif, x.fecha_poder, x.notaria) for x in r] == [(0, "00000014Z", date(2020, 1, 1), "Madrid"), (1, "00000001R", None, None)]
        with pytest.raises(ErrorContable, match="NIF"):
            ficha_390.guardar_representantes(s, empresa, [("Ana", "123", "", "")])
        with pytest.raises(ErrorContable, match="fecha"):
            ficha_390.guardar_representantes(s, empresa, [("Ana", "12345678Z", "99999", "")])
        with pytest.raises(ErrorContable, match="máximo"):
            ficha_390.guardar_representantes(s, empresa, [(f"R{i}", "12345678Z", "", "") for i in range(4)])
    finally:
        s.close()


def test_la_ficha_guarda_y_muestra_las_lineas(cliente):
    datos = {"nombre": "Empresa Nueva SL", "act_descripcion": ["Cultivo de frutales", ""], "act_codigo": ["B04", ""], "act_epigrafe": ["", ""],
             "rep_nombre": ["Elena", "Pedro", ""], "rep_nif": ["00000014Z", "00000001R", ""], "rep_fecha_poder": ["010120", "", ""], "rep_notaria": ["", "", ""]}
    assert cliente.post("/empresa/prueba", data=datos).status_code == 303
    pagina = cliente.get("/empresa/prueba").text
    assert "Cultivo de frutales" in pagina and "Pedro" in pagina and "01/01/2020" in pagina and "+ Añadir línea" in pagina
    malo = cliente.post("/empresa/prueba", data={**datos, "rep_nif": ["1", "00000001R", ""]})
    assert malo.status_code == 200 and "NIF de Elena" in malo.text and "Pedro" in malo.text
    empresa, s = _empresa(cliente)
    assert [r.nombre for r in empresa.representantes] == ["Elena", "Pedro"]
    s.close()
    sin_lineas = cliente.post("/empresa/prueba", data={"nombre": "Empresa Nueva SL"})  # sin campos de líneas, no se borran
    assert sin_lineas.status_code == 303
    empresa, s = _empresa(cliente)
    assert len(empresa.actividades) == 1 and len(empresa.representantes) == 2
    s.close()
