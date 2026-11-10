"""Modelos que presenta cada empresa: de lo que no presenta no salen plazos, avisos, pasos del trimestre ni opciones de menú."""
from datetime import date

import pytest
from fastapi.testclient import TestClient  # noqa: F401
from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import asistente_trimestre as asistente
from conta_pridalac.servicios import empresa as svc
from conta_pridalac.servicios.vigilancia import plazos_de_modelos

from test_menu import cliente  # noqa: F401 - `cliente` es una fixture (empresa «prueba» con ejercicio 2025)


@pytest.fixture
def ej(sesion):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    ej = Ejercicio(anio=2026, fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31), empresa=e)
    sesion.add_all([e, ej])
    sesion.flush()
    return ej


def modelos_con_aviso(h):
    return {x.referencia.split()[0] for x in h if x.codigo.startswith("plazo_modelo")}


def test_las_empresas_anteriores_presentan_todos_los_modelos_y_el_plan_propone_los_suyos(ej):
    assert svc.modelos_de(ej.empresa) == set(svc.MODELOS)
    assert set(svc.MODELOS_POR_PLAN["pymes"]) == set(svc.MODELOS)
    assert set(svc.MODELOS_POR_PLAN["esfl"]) < set(svc.MODELOS) and "303" not in svc.MODELOS_POR_PLAN["esfl"]


def test_fijar_los_modelos_de_la_empresa(sesion, ej):
    svc.fijar_modelos(sesion, ej.empresa, ["347", "111"])
    assert ej.empresa.modelos == "111,347" and svc.modelos_de(ej.empresa) == {"111", "347"}              # en el orden de siempre
    svc.fijar_modelos(sesion, ej.empresa, [])
    assert svc.modelos_de(ej.empresa) == set()                                                          # una empresa puede no presentar ninguno
    with pytest.raises(ErrorContable, match="desconocido"):
        svc.fijar_modelos(sesion, ej.empresa, ["999"])


def test_los_plazos_son_solo_de_lo_que_la_empresa_presenta(sesion, ej):
    todo = plazos_de_modelos(sesion, ej, date(2026, 4, 25))                                              # el 1T venció el 20 de abril
    assert {"303", "111"} <= modelos_con_aviso(todo)
    svc.fijar_modelos(sesion, ej.empresa, ["111"])
    assert modelos_con_aviso(plazos_de_modelos(sesion, ej, date(2026, 4, 25))) == {"111"}
    svc.fijar_modelos(sesion, ej.empresa, [])
    assert plazos_de_modelos(sesion, ej, date(2026, 4, 25)) == []


def test_sin_registro_mercantil_no_hay_avisos_de_libros_ni_de_deposito(sesion, ej):
    dia = date(2027, 5, 10)                                                                              # tras el plazo de los libros del 2026
    codigos = {x.codigo for x in plazos_de_modelos(sesion, ej, dia)}
    assert any(c.startswith("plazo_libros") for c in codigos)
    svc.fijar_modelos(sesion, ej.empresa, [m for m in svc.MODELOS if m != "mercantil"])
    assert not any(c.startswith(("plazo_libros", "plazo_deposito")) for c in {x.codigo for x in plazos_de_modelos(sesion, ej, dia)})


def test_el_asistente_del_trimestre_solo_enseña_los_pasos_de_lo_que_presenta(sesion, ej):
    periodo = (date(2026, 10, 1), date(2026, 12, 31))
    titulos = lambda: [p.titulo for p in asistente.pasos(sesion, ej.empresa, ej, periodo, "Sin presentar", "Sin presentar")]   # noqa: E731
    assert any("modelo 303" in t for t in titulos()) and any("modelo 111" in t for t in titulos()) and any("modelo 202" in t for t in titulos())
    svc.fijar_modelos(sesion, ej.empresa, ["111"])
    ahora = titulos()
    assert any("modelo 111" in t for t in ahora) and not any("modelo 303" in t or "modelo 202" in t or "modelo 390" in t for t in ahora)


def test_la_ficha_tiene_las_casillas_y_el_menu_esconde_lo_que_no_se_presenta(cliente):
    ficha = cliente.get("/empresa/prueba").text
    assert 'name="modelos"' in ficha and 'value="303" checked' in ficha and "Modelos que presenta" in ficha          # empresa anterior: todo marcado
    antes = cliente.get("/e/prueba/2025").text
    assert 'href="/e/prueba/2025/modelo-303"' in antes and 'href="/e/prueba/2025/modelo-200"' in antes and 'href="/e/prueba/2025/deposito-cuentas"' in antes
    r = cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "modelos_presente": "1", "modelos": ["111", "347"]}, follow_redirects=False)
    assert r.status_code == 303
    despues = cliente.get("/e/prueba/2025").text
    assert 'href="/e/prueba/2025/modelo-111"' in despues and 'href="/e/prueba/2025/modelo-347"' in despues
    assert "modelo-303" not in despues and "modelo-200" not in despues and "deposito-cuentas" not in despues and "liquidacion-iva" not in despues
    assert 'id="pestana-sociedades"' not in despues and 'id="pestana-mercantil"' not in despues                      # las cajas que se quedan vacías desaparecen
    assert 'value="111" checked' in cliente.get("/empresa/prueba").text and 'value="303" checked' not in cliente.get("/empresa/prueba").text
    assert cliente.get("/e/prueba/2025/modelo-303").status_code == 200                                              # esconder no es prohibir: la pantalla sigue ahí por si se necesita


def test_un_modelo_con_presentaciones_registradas_sigue_en_el_menu_aunque_se_desmarque(cliente):
    sesion = cliente.app.state.config.sesion("prueba")
    e = sesion.scalars(select(Empresa)).one()
    sesion.add(DeclaracionPresentada(empresa_id=e.id, modelo="303", anio=2025, periodo=1, tipo=1, casillas="{}"))
    sesion.commit()
    sesion.close()
    cliente.post("/empresa/prueba", data={"nombre": "Empresa de Prueba", "modelos_presente": "1", "modelos": ["111"]})
    pagina = cliente.get("/e/prueba/2025").text
    assert 'href="/e/prueba/2025/modelo-303"' in pagina and "modelo-347" not in pagina                              # el historial no se esconde; lo que no tiene nada, sí


def test_una_empresa_nueva_nace_con_los_modelos_de_su_plan(tmp_path):
    from conta_pridalac.servicios.alta_empresa import crear_empresa_nueva
    from conta_pridalac.web.config import Configuracion

    config = Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "a", copias=tmp_path / "c")
    crear_empresa_nueva(config, nombre="Asociacion Uno", nif="G12345678", anio=2026, tipo_plan="esfl")
    crear_empresa_nueva(config, nombre="Sociedad Dos", nif="B12345678", anio=2026, tipo_plan="pymes")
    for slug, esperado in (("asociacion-uno", set(svc.MODELOS_POR_PLAN["esfl"])), ("sociedad-dos", set(svc.MODELOS))):
        s = config.sesion(slug)
        try:
            assert svc.modelos_de(s.scalars(select(Empresa)).one()) == esperado
        finally:
            s.close()
