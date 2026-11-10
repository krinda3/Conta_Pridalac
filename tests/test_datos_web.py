"""Carpeta de datos y candado en la web: usar otra carpeta, mover los datos, «¿dónde están?» al arrancar, bloqueo, forzar y detección de que otro equipo toma el control."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conta_pridalac.servicios import candado as cd
from conta_pridalac.servicios import ubicacion_datos as ub
from conta_pridalac.servicios.alta_empresa import crear_empresa_nueva
from conta_pridalac.web import datos as datos_web
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

OTRO = "SOBREMESA-DE-OTRO"


@pytest.fixture(autouse=True)
def _sin_hilo(monkeypatch):
    monkeypatch.setenv("CONTA_SIN_HILO", "1")      # el latido lo da el test, a mano
    monkeypatch.delenv("CONTA_DATOS", raising=False)


def config_en(raiz: Path, **extra) -> Configuracion:
    return Configuracion(datos=raiz / "bd", almacen=raiz / "justificantes", copias=raiz / "copias", **extra)


def datos_con_empresa(raiz: Path, nombre="Empresa Uno", justificante=True) -> Path:
    c = config_en(raiz)
    crear_empresa_nueva(c, nombre=nombre, nif="B12345678", anio=2026)
    if justificante:
        (raiz / "justificantes" / "1" / "2026").mkdir(parents=True)
        (raiz / "justificantes" / "1" / "2026" / "f.pdf").write_bytes(b"%PDF-1.4 " + b"x" * 3000)
    (raiz / "copias").mkdir(exist_ok=True)
    return raiz


def cliente(raiz: Path, **extra) -> TestClient:
    return TestClient(crear_app(config_en(raiz, **extra)), follow_redirects=False)


def sigue(c: TestClient, r):
    return c.get(r.headers["location"])


# ------------------------------------------------------------------------------------------------ la carpeta de datos

def test_la_pantalla_de_empresas_ensena_la_carpeta_de_datos(tmp_path):
    raiz = datos_con_empresa(tmp_path / "a")
    c = cliente(raiz)
    inicio = c.get("/").text
    assert "Carpeta de datos" in inicio and str(raiz) in inicio and "¿Dónde están sus datos?" not in inicio
    datos = c.get("/datos").text
    assert str(raiz) in datos and "empresa-uno" in datos and "por defecto" in datos and "Usar otra carpeta que ya tiene datos" in datos and "Mover los datos" in datos


def test_si_la_carpeta_elegida_no_esta_se_pregunta_donde_estan_los_datos(tmp_path):
    raiz = tmp_path / "unidad-desconectada"                                                           # configurada, pero no está (disco o red desconectados)
    ub.guardar_ubicacion(raiz)
    c = cliente(raiz)
    inicio = c.get("/").text
    assert "¿Dónde están sus datos?" in inicio and "no está disponible" in inicio and "Elegir la carpeta donde están mis datos" in inicio
    assert "/empresa-nueva" not in inicio                                                              # no se ofrece crear una empresa que dejaría los datos en un sitio equivocado
    assert not raiz.exists()                                                                           # y no se ha creado la carpeta por el camino
    r = c.post("/datos/empezar")                                                                       # «Empezar con datos nuevos aquí»: una decisión explícita
    assert r.status_code == 303 and (raiz / ub.MARCA).is_file()
    inicio = c.get("/").text
    assert "¿Dónde están sus datos?" not in inicio and "/empresa-nueva" in inicio


def test_usar_otra_carpeta_con_datos_cambia_de_sitio_sin_reiniciar(tmp_path):
    a, b = datos_con_empresa(tmp_path / "a", "Empresa A"), datos_con_empresa(tmp_path / "b", "Empresa B", justificante=False)
    ub.guardar_ubicacion(a)
    c = cliente(a)
    assert "empresa-a" in c.get("/").text
    r = c.post("/datos/usar", data={"ruta": str(b / "bd")})                                             # quien elige «bd» en vez de la raíz también vale
    assert r.status_code == 303
    inicio = sigue(c, r).text
    assert "Ahora Conta usa" in inicio and "empresa-b" in inicio and "empresa-a<" not in inicio and "/e/empresa-a/" not in inicio
    assert ub.ubicacion_guardada() == b.resolve() and c.app.state.config.raiz == b
    assert (a / "bd" / "empresa-a.sqlite").exists()                                                    # la anterior no se toca


def test_usar_otra_carpeta_dice_por_que_no_se_puede(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    ub.guardar_ubicacion(a)
    c = cliente(a)
    (tmp_path / "vacia").mkdir()
    for ruta, texto in (("", "Indique"), (str(tmp_path / "no-existe"), "no está disponible"), (str(tmp_path / "vacia"), "No hay empresas")):
        r = c.post("/datos/usar", data={"ruta": ruta})
        assert "m=" in r.headers["location"] and texto in sigue(c, r).text, ruta
    assert c.app.state.config.raiz == a                                                                # nada cambió


def test_con_la_variable_de_entorno_no_se_puede_cambiar_desde_la_pantalla(tmp_path, monkeypatch):
    a, b = datos_con_empresa(tmp_path / "a"), datos_con_empresa(tmp_path / "b", "Otra")
    monkeypatch.setenv("CONTA_DATOS", str(a / "bd"))
    c = cliente(a)
    assert "CONTA_DATOS" in c.get("/datos").text and "Usar otra carpeta que ya tiene datos" not in c.get("/datos").text
    r = c.post("/datos/usar", data={"ruta": str(b)})
    assert "CONTA_DATOS" in sigue(c, r).text and c.app.state.config.raiz == a


def esperar_traslado(c, segundos=20):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        t = c.app.state.traslado
        if t and t["estado"] != "copiando":
            return t
        time.sleep(0.05)
    raise AssertionError("el traslado no terminó")


def test_mover_los_datos_copia_verifica_y_pasa_a_usar_la_nueva(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    ub.guardar_ubicacion(a)
    c = cliente(a)
    destino = tmp_path / "nueva" / "datos"
    assert c.post("/datos/mover", data={"destino": str(destino)}).headers["location"] == "/datos"
    t = esperar_traslado(c)
    assert t["estado"] == "listo" and "verificados" in t["mensaje"], t
    assert c.app.state.config.raiz == destino and ub.ubicacion_guardada() == destino.resolve()
    assert (destino / "bd" / "empresa-uno.sqlite").exists() and (destino / "justificantes" / "1" / "2026" / "f.pdf").read_bytes().startswith(b"%PDF")
    assert (a / ub.NOTA_DE_TRASLADO).exists() and (a / "bd" / "empresa-uno.sqlite").exists()           # el origen sigue ahí, con su nota
    assert "empresa-uno" in c.get("/").text                                                            # y el programa sigue funcionando, ya sobre la nueva
    assert "Datos movidos" in c.get("/datos").text
    assert c.post("/datos/mover/cerrar").status_code == 303 and c.app.state.traslado is None


def test_mover_los_datos_a_un_sitio_no_valido_no_empieza(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    ub.guardar_ubicacion(a)
    c = cliente(a)
    lleno = tmp_path / "lleno"
    lleno.mkdir()
    (lleno / "algo.txt").write_text("x")
    for destino, texto in (("", "Indique"), (str(lleno), "no está vacía"), (str(a / "dentro"), "dentro"), (str(a), "misma carpeta")):
        r = c.post("/datos/mover", data={"destino": destino})
        assert texto in sigue(c, r).text, destino
    assert c.app.state.traslado is None and c.app.state.config.raiz == a


def test_mientras_se_mueve_el_resto_del_programa_esta_bloqueado(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a)
    c.app.state.traslado = {"estado": "copiando", "mensaje": "Copiando", "hecho": 10, "total": 100, "origen": str(a), "destino": "x", "error": ""}
    assert c.get("/").headers["location"] == "/datos" and c.get("/e/empresa-uno/2026").headers["location"] == "/datos"
    assert c.get("/e/empresa-uno/2026/facturas-recibidas/tabla", headers={"HX-Request": "true"}).headers["HX-Redirect"] == "/datos"
    assert c.get("/datos").status_code == 200 and c.get("/static/app.css").status_code == 200 and c.get("/datos/estado").json()["estado"] == "copiando"
    assert "Moviendo los datos" in c.get("/datos").text and "Usar otra carpeta que ya tiene datos" not in c.get("/datos").text


# ------------------------------------------------------------------------------------------------ el candado

def test_el_programa_toma_el_candado_al_arrancar_y_lo_suelta_al_cerrar(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a, usar_candado=True)
    assert (a / cd.NOMBRE).exists() and c.app.state.candado.tengo() and c.app.state.bloqueo is None
    assert c.get("/").status_code == 200
    datos_web.soltar(c.app)
    assert not (a / cd.NOMBRE).exists()


def test_sin_usar_candado_no_se_toca_nada(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a)
    assert not (a / cd.NOMBRE).exists() and c.app.state.candado is None


def bloqueado_por_otro(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    otro = cd.Candado(a, equipo=OTRO, usuario="carlos", pid=4321)
    assert otro.adquirir() == (True, None)
    return a, otro


def test_si_lo_tiene_otro_equipo_todo_lleva_a_la_pantalla_de_bloqueo(tmp_path):
    a, otro = bloqueado_por_otro(tmp_path)
    c = cliente(a, usar_candado=True)
    assert c.app.state.bloqueo is not None and not c.app.state.candado.tengo()
    for ruta in ("/", "/e/empresa-uno/2026", "/programa", "/normativa", "/empresa-nueva"):
        assert c.get(ruta).headers["location"] == "/bloqueado", ruta
    assert c.get("/e/empresa-uno/2026/facturas-recibidas/tabla", headers={"HX-Request": "true"}).headers["HX-Redirect"] == "/bloqueado"
    pagina = c.get("/bloqueado").text
    assert "otro equipo" in pagina and OTRO in pagina and "carlos" in pagina and "Reintentar" in pagina and "FORZAR" in pagina
    assert c.get("/static/app.css").status_code == 200 and c.get("/datos").status_code == 200 and c.get("/ayuda").status_code == 200   # lo que hace falta para salir del paso
    assert otro.tengo()                                                                                # y quien lo tenía no ha perdido nada


def test_reintentar_entra_cuando_el_otro_equipo_ya_ha_cerrado(tmp_path):
    a, otro = bloqueado_por_otro(tmp_path)
    c = cliente(a, usar_candado=True)
    r = c.post("/bloqueado/reintentar")
    assert r.headers["location"].startswith("/bloqueado?m=") and "Sigue en uso" in sigue(c, r).text         # aún lo tiene
    otro.liberar()
    r = c.post("/bloqueado/reintentar")
    assert r.headers["location"] == "/" and c.get("/").status_code == 200 and c.app.state.candado.tengo()


def test_forzar_exige_escribir_forzar_y_toma_el_control(tmp_path):
    a, otro = bloqueado_por_otro(tmp_path)
    c = cliente(a, usar_candado=True)
    for texto in ("", "forzar", "si"):
        r = c.post("/bloqueado/forzar", data={"confirmacion": texto})
        assert "FORZAR" in sigue(c, r).text and c.app.state.bloqueo is not None
    r = c.post("/bloqueado/forzar", data={"confirmacion": "FORZAR"})
    assert r.headers["location"] == "/" and c.app.state.bloqueo is None and c.app.state.candado.tengo()
    assert c.get("/").status_code == 200 and cd.Candado(a).titular().equipo != OTRO


def test_si_otro_equipo_fuerza_el_candado_este_programa_se_bloquea_al_siguiente_latido(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a, usar_candado=True)
    assert c.get("/").status_code == 200
    cd.Candado(a, equipo=OTRO, usuario="carlos", pid=1).forzar()                                        # el otro equipo lo toma a la fuerza
    datos_web.latir(c.app)
    assert c.app.state.bloqueo is not None and c.app.state.bloqueo_perdido
    assert c.get("/").headers["location"] == "/bloqueado" and "ha tomado el control" in c.get("/bloqueado").text
    datos_web.soltar(c.app)                                                                            # al cerrar no le quita el candado al nuevo titular
    assert cd.Candado(a).titular().equipo == OTRO


def test_si_el_fichero_del_candado_desaparece_se_vuelve_a_poner(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a, usar_candado=True)
    (a / cd.NOMBRE).unlink()                                                                            # p. ej. lo quitó la sincronización
    datos_web.latir(c.app)
    assert (a / cd.NOMBRE).exists() and c.app.state.bloqueo is None


def test_un_latido_renueva_la_senal(tmp_path):
    a = datos_con_empresa(tmp_path / "a")
    c = cliente(a, usar_candado=True)
    antes = cd.Candado(a).titular().senal
    time.sleep(1.1)
    datos_web.latir(c.app)
    assert cd.Candado(a).titular().senal > antes


def test_una_carpeta_sin_datos_elegida_a_mano_no_recibe_candado(tmp_path):
    raiz = tmp_path / "montaje-vacio"
    raiz.mkdir()                                                                                        # el punto de montaje existe, pero la unidad no está conectada
    ub.guardar_ubicacion(raiz)
    c = cliente(raiz, usar_candado=True)
    assert not (raiz / cd.NOMBRE).exists() and c.app.state.candado is None and "¿Dónde están sus datos?" in c.get("/").text


def test_cambiar_a_una_carpeta_en_uso_en_otro_equipo_no_se_hace_y_no_suelta_la_actual(tmp_path):
    a, b = datos_con_empresa(tmp_path / "a", "Empresa A"), datos_con_empresa(tmp_path / "b", "Empresa B", justificante=False)
    ub.guardar_ubicacion(a)
    otro = cd.Candado(b, equipo=OTRO, usuario="carlos", pid=77)
    otro.adquirir()
    c = cliente(a, usar_candado=True)
    r = c.post("/datos/usar", data={"ruta": str(b)})
    assert "la tiene abierta otro equipo" in sigue(c, r).text
    assert c.app.state.config.raiz == a and c.app.state.candado.tengo() and (a / cd.NOMBRE).exists()
    otro.liberar()
    c.post("/datos/usar", data={"ruta": str(b)})
    assert c.app.state.config.raiz == b and c.app.state.candado.tengo() and not (a / cd.NOMBRE).exists() and (b / cd.NOMBRE).exists()   # toma la nueva y suelta la vieja


def test_las_acciones_de_datos_y_bloqueo_solo_valen_desde_este_programa(tmp_path):
    a, otro = bloqueado_por_otro(tmp_path)
    c = cliente(a, usar_candado=True)
    ajeno = {"Origin": "https://pagina-ajena.example"}
    for ruta, datos in (("/datos/usar", {"ruta": str(a)}), ("/datos/mover", {"destino": str(tmp_path / "x")}), ("/datos/empezar", {}), ("/datos/examinar", {}),
                        ("/bloqueado/forzar", {"confirmacion": "FORZAR"}), ("/bloqueado/reintentar", {})):
        assert c.post(ruta, data=datos, headers=ajeno).status_code == 403, ruta
    assert c.app.state.bloqueo is not None and otro.tengo()
