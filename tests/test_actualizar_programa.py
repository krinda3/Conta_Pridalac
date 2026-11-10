"""Actualizar el programa desde GitHub: con repositorios git de verdad (un «origen», el equipo de quien desarrolla y el de quien usa el programa), sin red."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import actualizar_programa as ap

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git no está instalado")

ENTORNO = {**os.environ, "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t", "GIT_TERMINAL_PROMPT": "0"}


def git(carpeta: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(carpeta), *args], capture_output=True, text=True, env=ENTORNO)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def confirmar(carpeta: Path, fichero: str, texto: str, mensaje: str) -> None:
    (carpeta / fichero).write_text(texto, encoding="utf-8")
    git(carpeta, "add", fichero)
    git(carpeta, "commit", "-m", mensaje)


@pytest.fixture
def repos(tmp_path):
    origen = tmp_path / "origen.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origen)], check=True, capture_output=True)
    desarrollo = tmp_path / "desarrollo"
    subprocess.run(["git", "clone", str(origen), str(desarrollo)], check=True, capture_output=True, env=ENTORNO)
    git(desarrollo, "checkout", "-B", "main")
    confirmar(desarrollo, "pyproject.toml", "v1", "Primera versión")
    git(desarrollo, "push", "-u", "origin", "main")
    equipo = tmp_path / "equipo"
    subprocess.run(["git", "clone", str(origen), str(equipo)], check=True, capture_output=True, env=ENTORNO)
    return desarrollo, equipo


def publicar(desarrollo: Path, fichero: str, texto: str, mensaje: str) -> None:
    confirmar(desarrollo, fichero, texto, mensaje)
    git(desarrollo, "push")


def test_una_carpeta_copiada_a_mano_no_se_puede_actualizar(tmp_path):
    assert "no es un clon" in ap.disponible(tmp_path)
    assert not ap.version(tmp_path).hash and not ap.comprobar(tmp_path).al_dia


def test_comprobar_cuenta_los_cambios_nuevos(repos):
    desarrollo, equipo = repos
    c = ap.comprobar(equipo)
    assert c.al_dia and c.cambios == [] and "al día" in c.mensaje
    publicar(desarrollo, "a.txt", "1", "Cambio uno")
    publicar(desarrollo, "b.txt", "2", "Cambio dos")
    c = ap.comprobar(equipo)
    assert c.pendientes == 2 and len(c.cambios) == 2 and "Cambio dos" in c.cambios[0]
    assert ap.version(equipo).resumen == "Primera versión"      # comprobar no cambia nada del programa
    assert not (equipo / "a.txt").exists()


def test_actualizar_baja_los_cambios_y_hace_la_copia_antes(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "a.txt", "1", "Cambio uno")
    llamadas = []

    def antes():
        llamadas.append("copia: a.txt existe = " + str((equipo / "a.txt").exists()))
        return ["Copia hecha"]

    instaladas = []
    r = ap.actualizar(equipo, antes=antes, instalar=lambda raiz: instaladas.append(raiz) or (True, ""))
    assert r.ok and r.actualizado and llamadas == ["copia: a.txt existe = False"]           # la copia se hace ANTES de tocar nada
    assert (equipo / "a.txt").read_text() == "1" and "Copia hecha" in r.informe and "Cierre el programa" in r.informe[-1]
    assert instaladas == []                                                                    # no cambió pyproject.toml
    assert ap.comprobar(equipo).al_dia
    assert ap.actualizar(equipo).informe == ["El programa ya estaba al día."]


def test_si_cambian_las_dependencias_se_vuelven_a_instalar(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "pyproject.toml", "v2", "Dependencia nueva")
    instaladas = []
    r = ap.actualizar(equipo, instalar=lambda raiz: instaladas.append(raiz) or (True, ""))
    assert r.ok and instaladas == [equipo] and "Dependencias actualizadas." in r.informe
    publicar(desarrollo, "pyproject.toml", "v3", "Otra dependencia")
    r = ap.actualizar(equipo, instalar=lambda raiz: (False, "no hay red"))
    assert not r.ok and r.actualizado and any("instalar.bat" in l for l in r.informe)      # el código ya cambió: hay que decirlo


def test_no_actualiza_si_hay_ficheros_modificados_a_mano(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "a.txt", "1", "Cambio uno")
    (equipo / "pyproject.toml").write_text("cambiado a mano")
    copias = []
    r = ap.actualizar(equipo, antes=lambda: copias.append(1) or [])
    assert not r.ok and "pyproject.toml" in "\n".join(r.informe) and copias == [] and not (equipo / "a.txt").exists()


def test_los_ficheros_nuevos_sin_seguir_no_impiden_actualizar(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "a.txt", "1", "Cambio uno")
    (equipo / "datos_locales.txt").write_text("mis datos")        # como datos_locales, que no está en git
    assert ap.actualizar(equipo, instalar=lambda raiz: (True, "")).ok and (equipo / "datos_locales.txt").read_text() == "mis datos"


def test_si_la_copia_de_seguridad_falla_no_se_actualiza(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "a.txt", "1", "Cambio uno")

    def antes():
        raise ErrorContable("disco lleno")

    r = ap.actualizar(equipo, antes=antes)
    assert not r.ok and "copia de seguridad" in r.informe[0] and "disco lleno" in r.informe[0]
    assert not (equipo / "a.txt").exists() and ap.comprobar(equipo).pendientes == 1


def test_si_los_dos_lados_cambiaron_no_mezcla_nada(repos):
    desarrollo, equipo = repos
    publicar(desarrollo, "a.txt", "1", "Cambio de GitHub")
    confirmar(equipo, "local.txt", "mío", "Cambio local")
    antes = git(equipo, "rev-parse", "HEAD")
    r = ap.actualizar(equipo, instalar=lambda raiz: (True, ""))
    assert not r.ok and "no se ha cambiado nada" in r.informe[-1] and git(equipo, "rev-parse", "HEAD") == antes
    assert ap.comprobar(equipo).adelantados == 1


def test_la_direccion_del_origen_no_enseña_la_clave(repos):
    _, equipo = repos
    git(equipo, "remote", "set-url", "origin", "https://usuario:secreto@github.com/krinda3/Conta_Pridalac.git")
    assert ap.origen(equipo) == "https://github.com/krinda3/Conta_Pridalac.git"


# ------------------------------------------------------------------------------------------------ la pantalla

@pytest.fixture
def cliente(tmp_path, monkeypatch):
    from datetime import date

    from fastapi.testclient import TestClient

    from conta_pridalac.db.modelos import Ejercicio, Empresa
    from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
    from conta_pridalac.web import sistema as pantalla
    from conta_pridalac.web.app import crear_app
    from conta_pridalac.web.config import Configuracion

    datos = tmp_path / "bd"
    datos.mkdir()
    motor = crear_motor(datos / "prueba.sqlite")
    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="Empresa de Prueba", nif="B12345678")
    s.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    s.commit()
    s.close()
    motor.dispose()
    # el programa de verdad (esta carpeta) no se toca nunca desde los tests: se sustituye lo que habla con git
    falso = type("Falso", (), {})()
    falso.estado = dict(pendientes=2, cambios=["abc1234 · 05/11/2026 · Cambio uno", "def5678 · 05/11/2026 · Cambio dos"], propios=[], hecho=[], motivo=None)
    monkeypatch.setattr(pantalla.ap, "disponible", lambda *a, **k: falso.estado["motivo"])
    monkeypatch.setattr(pantalla.ap, "version", lambda *a, **k: pantalla.ap.Version("aaa1111", "01/11/2026", "Versión actual"))
    monkeypatch.setattr(pantalla.ap, "origen", lambda *a, **k: "https://github.com/krinda3/Conta_Pridalac.git")
    monkeypatch.setattr(pantalla.ap, "comprobar", lambda *a, **k: pantalla.ap.Comprobacion(falso.estado["pendientes"], falso.estado["cambios"], 0, "Hay cambios." if falso.estado["pendientes"] else "El programa está al día."))
    monkeypatch.setattr(pantalla.ap, "modificados", lambda *a, **k: falso.estado["propios"])

    def actualizar_falso(*a, antes=None, **k):
        informe = antes() if antes else []
        falso.estado["hecho"].append(informe)
        return pantalla.ap.Resultado(True, informe + ["Actualizado a bbb2222."], actualizado=True)

    monkeypatch.setattr(pantalla.ap, "actualizar", actualizar_falso)
    cl = TestClient(crear_app(Configuracion(datos=datos, almacen=tmp_path / "almacen", copias=tmp_path / "copias")))
    cl.falso, cl.tmp = falso, tmp_path
    return cl


def test_el_programa_cuelga_de_la_pantalla_de_empresas_y_enseña_la_version(cliente):
    inicio = cliente.get("/").text
    assert 'href="/programa"' in inicio and "aaa1111" in inicio and "sin comprobar todavía" in inicio.lower()
    t = cliente.get("/programa").text
    assert "aaa1111" in t and "Versión actual" in t and "todavía no se ha buscado" in t and ">Actualizar ahora</button>" not in t   # sin comprobar, no se ofrece actualizar
    assert "/programa" not in cliente.get("/e/prueba/2025").text                                                          # ya no está en el menú de la empresa


def test_buscar_actualizaciones_recuerda_lo_encontrado_y_ofrece_actualizar(cliente):
    r = cliente.post("/programa/comprobar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/programa?m=")
    t = cliente.get("/programa").text
    assert "hay 2 cambio(s) nuevo(s)" in t and "Cambio dos" in t and ">Actualizar ahora</button>" in t and (cliente.tmp / "bd" / "_programa.json").exists()
    assert "Hay 2 cambio(s) nuevo(s)".lower() in cliente.get("/").text.lower()                                                # la tarjeta de inicio lo avisa
    assert "copia de seguridad ligera" in t


def test_actualizar_hace_antes_la_copia_de_cada_empresa(cliente):
    cliente.post("/programa/comprobar")
    r = cliente.post("/programa/actualizar")
    assert r.status_code == 200 and "Programa actualizado" in r.text and "Cierre el programa" in r.text
    copias = list((cliente.tmp / "copias").glob("copia_prueba_*antes_de_actualizar*.zip"))
    assert len(copias) == 1 and "Copia de seguridad ligera hecha de: prueba" in cliente.falso.estado["hecho"][0][0]


def test_si_no_es_un_clon_dice_por_que_no_se_puede_actualizar(cliente):
    cliente.falso.estado["motivo"] = "Esta carpeta no es un clon de GitHub (se copió a mano)"
    t = cliente.get("/programa").text
    assert "no es un clon de GitHub" in t and ">Buscar actualizaciones</button>" not in t and ">Actualizar ahora</button>" not in t
    assert "no se puede actualizar desde aquí" in cliente.get("/").text.lower()


def test_sin_cambios_pendientes_no_se_ofrece_actualizar(cliente):
    cliente.falso.estado.update(pendientes=0, cambios=[])
    cliente.post("/programa/comprobar")
    t = cliente.get("/programa").text
    assert "el programa está al día" in t and ">Actualizar ahora</button>" not in t


def test_el_resumen_de_inicio_no_se_cae_si_git_falla(cliente, monkeypatch):
    from conta_pridalac.web import sistema as pantalla

    def roto(*a, **k):
        raise RuntimeError("git roto")

    monkeypatch.setattr(pantalla.ap, "disponible", roto)
    assert cliente.get("/").status_code == 200
