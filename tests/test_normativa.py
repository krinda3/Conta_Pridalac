"""Control de cambios normativos: ventanas de revisión, revisiones guardadas y sondeo de la sede (sin red: con un abridor de mentira)."""
from datetime import date

import pytest

from conta_pridalac.servicios import normativa as nv
from conta_pridalac.web.config import Configuracion


@pytest.fixture
def config(tmp_path):
    return Configuracion(datos=tmp_path / "bd", almacen=tmp_path / "almacen", motores={})


def _estado(estados, clave):
    return next(e for e in estados if e.fuente.clave == clave)


def test_el_catalogo_tiene_lo_que_conta_implementa():
    assert {"200", "202", "303", "390", "190", "347", "111", "plazos", "d2", "legalia", "pgc"} <= set(nv.POR_CLAVE)
    assert nv.POR_CLAVE["200"].version == "DR200e25v102" and nv.POR_CLAVE["200"].ejercicio == 2025 and nv.POR_CLAVE["390"].ejercicio == 2026
    assert all(f.que_hacer and f.donde for f in nv.CATALOGO)


def test_hoy_no_hay_nada_por_revisar_y_la_ventana_se_abre_cuando_toca(config):
    assert not any(e.por_revisar for e in nv.estados(config, date(2026, 11, 3)))  # el día en que se fijó todo
    antes = _estado(nv.estados(config, date(2026, 11, 30)), "190")
    despues = _estado(nv.estados(config, date(2026, 12, 1)), "190")
    assert not antes.por_revisar and despues.por_revisar and despues.apertura == date(2026, 12, 1) and despues.proxima == date(2027, 12, 1)
    assert _estado(nv.estados(config, date(2027, 4, 1)), "200").por_revisar and not _estado(nv.estados(config, date(2027, 3, 31)), "200").por_revisar
    assert _estado(nv.estados(config, date(2027, 1, 20)), "111").por_revisar  # los estables, cada enero


def test_marcar_como_revisada_apaga_el_aviso_hasta_la_ventana_siguiente(config):
    assert _estado(nv.estados(config, date(2026, 12, 5)), "plazos").por_revisar
    nv.marcar_revisada(config, "plazos", date(2026, 12, 5))
    e = _estado(nv.estados(config, date(2026, 12, 6)), "plazos")
    assert not e.por_revisar and e.revisada == date(2026, 12, 5)
    assert _estado(nv.estados(config, date(2027, 12, 2)), "plazos").por_revisar  # el año que viene, otra vez
    with pytest.raises(ValueError, match="desconocida"):
        nv.marcar_revisada(config, "inventada")
    assert (config.datos / "_normativa.json").is_file()


def test_el_sondeo_distingue_sin_cambios_cambio_y_diseno_nuevo():
    f = nv.POR_CLAVE["200"]
    igual = nv.sondear(f, lambda url: (f.tamano, f.modificado) if "archivos_25" in url else (None, None), date(2027, 4, 2))
    assert (igual["cambiado"], igual["siguiente_existe"], igual["error"]) == (False, False, None)
    cambiado = nv.sondear(f, lambda url: (f.tamano + 1, f.modificado) if "archivos_25" in url else (None, None))
    assert cambiado["cambiado"] is True
    solo_fecha = nv.sondear(f, lambda url: (f.tamano, "Mon, 01 Mar 2027 10:00:00 GMT") if "archivos_25" in url else (None, None))
    assert solo_fecha["cambiado"] is True  # mismo tamaño pero se ha vuelto a subir
    nuevo = nv.sondear(f, lambda url: (f.tamano, f.modificado) if "archivos_25" in url else (9999, "x"))
    assert nuevo["siguiente_existe"] is True
    rutas = []
    nv.sondear(f, lambda url: rutas.append(url) or (None, None))
    assert any(r.endswith("DR_200_299/archivos_26/DR200e26.xls") for r in rutas)  # busca el del ejercicio siguiente
    desaparecido = nv.sondear(f, lambda url: (None, None))
    assert desaparecido["cambiado"] is True  # si el diseño ya no está en su sitio, algo ha pasado


def test_sin_red_el_sondeo_lo_dice_y_no_falla():
    def sin_red(url):
        raise OSError("No se pudo consultar la sede: sin red")

    r = nv.sondear(nv.POR_CLAVE["390"], sin_red)
    assert r["error"] == "No se pudo consultar la sede: sin red" and r["cambiado"] is None and r["siguiente_existe"] is None


def test_sondear_todo_guarda_el_resultado_y_el_estado_lo_enseña(config):
    resultados = nv.sondear_todo(config, lambda url: (None, None), date(2026, 11, 4), lambda dia: None)
    assert set(resultados) == {f.clave for f in nv.CATALOGO if f.url or f.siguiente or f.boe} and "190" not in resultados  # sin dirección ni BOE no se sondea
    e = _estado(nv.estados(config, date(2026, 11, 4)), "200")
    assert e.sondeo["fecha"] == "2026-11-04" and e.cambio_detectado
    assert _estado(nv.estados(config, date(2026, 11, 4)), "190").sondeo == {}


# ------------------------------------------------------------------------------------------------ comparación de diseños

import copy  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from conta_pridalac.ficheros_aeat import comparar as cmp  # noqa: E402

DISENOS = Path(nv.__file__).resolve().parents[1] / "ficheros_aeat"


def test_dos_disenos_iguales_no_tienen_cambios():
    for nombre in ("dr200_2025.json", "dr202_2025.json", "dr390_2026.json"):
        d = cmp.cargar(DISENOS / nombre)
        assert d and cmp.comparar(d, d).sin_cambios, nombre
    assert "14000" in cmp.cargar(DISENOS / "dr200_2025.json") and len(cmp.cargar(DISENOS / "dr200_2025.json")) == 41


def test_se_detectan_altas_bajas_movimientos_y_cambios_de_tamano_tipo_y_texto(tmp_path):
    viejo = cmp.cargar(DISENOS / "dr200_2025.json")
    nuevo = copy.deepcopy(viejo)
    p = nuevo["14000"]
    base = next(c for c in p if c["casilla"] == "00552")
    cuota = next(c for c in p if c["casilla"] == "00562")
    tipo = next(c for c in p if c["casilla"] == "00558")
    base["pos"] += 1  # movido
    cuota["lon"] = 15  # tamaño
    tipo["tipo"] = "N"  # tipo
    tipo["desc"] = tipo["desc"] + " (nuevo texto)"  # texto
    quitado = p.pop(next(i for i, c in enumerate(p) if c["casilla"] == "00560"))  # baja
    p.append({"n": 999, "pos": 5000, "lon": 17, "tipo": "N", "casilla": "09999", "desc": "Casilla nueva", "validacion": "", "contenido": ""})  # alta
    nuevo["99999"] = [dict(base)]  # página nueva
    del nuevo["21000"]  # página quitada
    informe = cmp.comparar(viejo, nuevo)
    assert informe.paginas_nuevas == ["99999"] and informe.paginas_quitadas == ["21000"] and not informe.sin_cambios
    assert {(c.clave, c.tipo) for c in informe.cambios} == {("casilla 00552", "movido"), ("casilla 00562", "tamaño"), ("casilla 00558", "tipo"), ("casilla 00558", "texto"),
                                                            ("casilla 00560", "baja"), ("casilla 09999", "alta")}
    texto = informe.texto()
    assert "Páginas NUEVAS: 99999" in texto and "Páginas QUITADAS: 21000" in texto and "movido" in texto and "Casilla nueva" in texto and quitado["casilla"] == "00560"
    assert informe.por_tipo()["alta"] == 1


def test_un_campo_sin_casilla_se_identifica_por_su_posicion():
    viejo = {"p": [{"pos": 1, "lon": 5, "tipo": "An", "desc": "NIF", "casilla": None, "contenido": ""}]}
    nuevo = {"p": [{"pos": 1, "lon": 9, "tipo": "An", "desc": "NIF", "casilla": None, "contenido": ""}]}
    assert [(c.clave, c.tipo) for c in cmp.comparar(viejo, nuevo).cambios] == [("posición 1", "tamaño")]


# ------------------------------------------------------------------------------------------------ avisos de la auditoría y pantalla

import json as _json  # noqa: E402

from test_web_auditoria import cliente  # noqa: E402,F401 - `cliente` es una fixture


def test_la_auditoria_avisa_de_lo_que_toca_revisar_y_de_lo_que_ha_cambiado(config):
    assert nv.hallazgos_de_normativa(config, date(2026, 11, 3)) == []
    h = nv.hallazgos_de_normativa(config, date(2026, 12, 5))
    assert {(x.codigo, x.referencia) for x in h} == {("normativa_por_revisar", "190"), ("normativa_por_revisar", "180"), ("normativa_por_revisar", "347"), ("normativa_por_revisar", "plazos")}
    assert all(x.gravedad == "AVISO" for x in h)
    nv.sondear_todo(config, lambda url: (None, None), date(2026, 12, 6))  # la sede ya no tiene los diseños: aviso de cambio
    codigos = {(x.codigo, x.referencia) for x in nv.hallazgos_de_normativa(config, date(2026, 12, 6))}
    assert ("normativa_cambio_en_la_sede", "200") in codigos and ("normativa_por_revisar", "200") not in codigos


def test_la_pantalla_lista_las_fuentes_y_marca_como_revisada(cliente, monkeypatch):
    inicio = cliente.get("/").text
    assert 'href="/normativa"' in inicio and "Normativa y diseños" in inicio                          # cuelga de la pantalla de empresas…
    assert "/normativa" not in cliente.get("/e/prueba/2026").text and "/programa" not in cliente.get("/e/prueba/2026").text   # …y ya no del menú de la empresa
    tabla = cliente.get("/normativa").text
    assert "Modelo 200" in tabla and "DR200e25v102" in tabla and "Calendario del contribuyente" in tabla and "Al día" in tabla
    ficha = cliente.get("/normativa/200").text
    assert "DR_200_299/archivos_25/DR200e25.xls" in ficha and "Si hay cambios" in ficha and "Marcar como revisada hoy" in ficha
    assert cliente.get("/normativa/no-existe").status_code == 404
    r = cliente.post("/normativa/200/revisada", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/normativa/200?m=")
    assert "Marcada como revisada" in cliente.get(r.headers["location"]).text
    assert nv.estados(cliente.app.state.config)[0].revisada == date.today()
    # consultar la sede, sin red: con un sondeo de mentira
    monkeypatch.setattr(nv, "sondear_todo", lambda config: {"200": {"fecha": "2026-11-03", "cambiado": True, "siguiente_existe": False, "error": None}, "390": {"fecha": "2026-11-03", "cambiado": False, "siguiente_existe": False, "error": None}})
    r = cliente.post("/normativa/consultar", follow_redirects=True)
    assert r.status_code == 200 and "CAMBIOS en 200" in r.text


def test_las_acciones_de_normativa_y_programa_solo_valen_desde_este_programa(cliente):
    """Otra web abierta en el navegador no puede lanzar una consulta, una revisión ni una actualización."""
    ajeno = {"Origin": "https://pagina-ajena.example"}
    for ruta in ("/normativa/consultar", "/normativa/200/revisada", "/normativa/200/consultar", "/programa/comprobar", "/programa/actualizar"):
        assert cliente.post(ruta, headers=ajeno, follow_redirects=False).status_code == 403, ruta
    assert cliente.post("/normativa/200/revisada", headers={"Origin": "http://127.0.0.1:8000"}, follow_redirects=False).status_code == 303
