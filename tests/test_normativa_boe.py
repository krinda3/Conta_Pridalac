"""Vigilancia del BOE para el depósito de cuentas: búsqueda incremental de la resolución de modelos, sin red (el BOE se sustituye por un sumario de mentira)."""
from datetime import date, timedelta

import pytest

from conta_pridalac.servicios import normativa as nv
from conta_pridalac.web.config import Configuracion

D2 = nv.POR_CLAVE["d2"]
RESOLUCION = "Resolución de 19 de mayo de 2026, de la Dirección General de Seguridad Jurídica y Fe Pública, referida a los modelos para la presentación en el Registro Mercantil de las cuentas anuales de los sujetos obligados a su publicación."
CONSOLIDADAS = "Resolución de 19 de mayo de 2026, de la Dirección General de Seguridad Jurídica y Fe Pública, referida a los modelos para la presentación en el Registro Mercantil de las cuentas anuales consolidadas de los sujetos obligados a su publicación."
RUIDO = "Resolución de 5 de mayo de 2026, de la Dirección General de Tributos, por la que se aprueban los modelos de declaración del impuesto."


def sumario(*titulos):
    """Con la misma forma anidada que el del BOE: diario → sección → departamento → epígrafe → ítems."""
    items = [{"identificador": f"BOE-A-2026-{11000 + i}", "titulo": t, "url_pdf": {"texto": f"https://www.boe.es/pdf/{11000 + i}.pdf"}} for i, t in enumerate(titulos)]
    return {"data": {"sumario": {"diario": [{"seccion": [{"departamento": [{"epigrafe": [{"item": items[:1]}, {"item": items[1:]}]}]}]}]}}}


class FalsoBoe:
    def __init__(self, por_dia=None, falla_el=None):
        self.por_dia, self.falla_el, self.dias = por_dia or {}, falla_el, []

    def __call__(self, dia):
        if dia == self.falla_el:
            raise OSError("El BOE respondió 503")
        self.dias.append(dia)
        return self.por_dia.get(dia)


def dias_habiles(ini, fin):
    return [ini + timedelta(days=n) for n in range((fin - ini).days + 1) if (ini + timedelta(days=n)).weekday() != 6]


def test_encuentra_la_resolucion_de_modelos_y_solo_consulta_la_epoca_del_ano():
    boe = FalsoBoe({date(2026, 5, 29): sumario(RESOLUCION, CONSOLIDADAS, RUIDO), date(2026, 5, 20): sumario(RUIDO)})
    r = nv.sondear_boe(D2, boe, date(2026, 11, 5))
    assert [h["id"] for h in r["encontradas"]] == ["BOE-A-2026-11000", "BOE-A-2026-11001"]
    assert r["encontradas"][0]["fecha"] == "2026-05-29" and r["encontradas"][0]["url"].endswith("11000.pdf") and "modelos para la presentación" in r["encontradas"][0]["titulo"]
    assert boe.dias == dias_habiles(date(2026, 4, 1), date(2026, 7, 31)) and r["hasta"] == "2026-07-31" and r["error"] is None   # abril a julio, sin domingos


def test_fuera_de_la_epoca_no_se_consulta_nada():
    boe = FalsoBoe()
    r = nv.sondear_boe(D2, boe, date(2026, 2, 10))
    assert boe.dias == [] and r["hasta"] is None and r["encontradas"] == []


def test_es_incremental_no_repite_los_dias_ya_vistos():
    boe = FalsoBoe({date(2026, 5, 29): sumario(RESOLUCION)})
    primera = nv.sondear_boe(D2, boe, date(2026, 6, 5))
    assert primera["hasta"] == "2026-06-05" and len(primera["encontradas"]) == 1
    boe.dias.clear()
    segunda = nv.sondear_boe(D2, boe, date(2026, 6, 12), primera)
    assert boe.dias == dias_habiles(date(2026, 6, 6), date(2026, 6, 12)) and len(segunda["encontradas"]) == 1      # solo lo nuevo; lo hallado se conserva
    boe.dias.clear()
    assert nv.sondear_boe(D2, boe, date(2026, 6, 12), segunda)["hasta"] == "2026-06-12" and boe.dias == []


def test_el_siguiente_ano_se_vuelve_a_abrir_la_ventana():
    boe = FalsoBoe()
    visto = nv.sondear_boe(D2, boe, date(2026, 12, 20))
    boe.dias.clear()
    nv.sondear_boe(D2, boe, date(2027, 4, 10), visto)
    assert boe.dias == dias_habiles(date(2027, 4, 1), date(2027, 4, 10))


def test_si_el_boe_falla_a_medias_conserva_lo_hallado_y_sigue_desde_ahi():
    boe = FalsoBoe({date(2026, 4, 20): sumario(RESOLUCION)}, falla_el=date(2026, 5, 15))
    r = nv.sondear_boe(D2, boe, date(2026, 6, 30))
    assert r["error"] == "El BOE respondió 503" and r["hasta"] == "2026-05-14" and len(r["encontradas"]) == 1
    boe.falla_el = None
    boe.dias.clear()
    r2 = nv.sondear_boe(D2, boe, date(2026, 6, 30), r)
    assert r2["error"] is None and boe.dias[0] == date(2026, 5, 15) and len(r2["encontradas"]) == 1


def test_tope_de_consultas_por_pasada(monkeypatch):
    monkeypatch.setattr(nv, "MAX_DIAS_BOE", 10)
    boe = FalsoBoe()
    r = nv.sondear_boe(D2, boe, date(2026, 11, 5))
    assert len(boe.dias) == 10 and "vuelva a consultar" in r["error"]
    r2 = nv.sondear_boe(D2, boe, date(2026, 11, 5), r)
    assert r2["hasta"] > r["hasta"]


def test_una_novedad_del_boe_avisa_hasta_que_se_marca_como_revisada(tmp_path):
    config = Configuracion(datos=tmp_path / "bd")
    boe = FalsoBoe({date(2026, 5, 29): sumario(RESOLUCION)})
    nv.sondear_todo(config, lambda url: (None, None), date(2026, 11, 5), boe)
    e = next(x for x in nv.estados(config, date(2026, 11, 5)) if x.fuente.clave == "d2")
    assert e.cambio_detectado and [h["id"] for h in e.novedades_boe] == ["BOE-A-2026-11000"]
    avisos = [h for h in nv.hallazgos_de_normativa(config, date(2026, 11, 5)) if h.referencia == "d2"]
    assert [h.codigo for h in avisos] == ["normativa_novedad_en_el_boe"] and "29/05/2026" in avisos[0].mensaje and "BOE-A-2026-11000" in avisos[0].mensaje
    nv.marcar_revisada(config, "d2", date(2026, 11, 5))                      # leída la resolución y adaptado lo que hiciera falta
    e = next(x for x in nv.estados(config, date(2026, 11, 5)) if x.fuente.clave == "d2")
    assert not e.novedades_boe and not e.cambio_detectado
    assert [h.codigo for h in nv.hallazgos_de_normativa(config, date(2026, 11, 5)) if h.referencia == "d2"] == []


def test_sin_red_el_sondeo_del_boe_lo_dice_y_no_falla(tmp_path):
    config = Configuracion(datos=tmp_path / "bd")
    r = nv.sondear_todo(config, lambda url: (None, None), date(2026, 11, 5))["d2"]       # la red está cortada en los tests (conftest)
    assert r["error"] == "sin red en los tests" and r["boe"]["hasta"] is None


def test_las_disposiciones_se_encuentran_esten_donde_esten():
    ids = sorted(d["identificador"] for d in nv._disposiciones(sumario("a", "b", "c")))
    assert ids == ["BOE-A-2026-11000", "BOE-A-2026-11001", "BOE-A-2026-11002"]
    assert list(nv._disposiciones({})) == []


def test_las_palabras_clave_ignoran_mayusculas_y_tildes():
    boe = FalsoBoe({date(2026, 5, 29): sumario("RESOLUCIÓN sobre los MODELOS del REGISTRO MERCANTIL para las CUENTAS ANUALES")})
    assert len(nv.sondear_boe(D2, boe, date(2026, 6, 1))["encontradas"]) == 1
