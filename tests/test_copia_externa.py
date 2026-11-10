"""La copia de seguridad del final del trimestre, llevada a la carpeta de la empresa (OneDrive) y verificada allí."""
import json
import time

from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.servicios import copia_externa, copias
from test_web_copias import _añadir_cuenta, cliente  # noqa: F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/trimestre"


def _configurar(cliente, carpeta):
    s = cliente.app.state.config.sesion("prueba")
    s.scalars(select(Empresa)).first().carpeta_copias = str(carpeta)
    s.commit()
    s.close()


def test_sin_carpeta_configurada_se_dice_y_no_se_hace_nada(cliente, tmp_path):
    assert "Sin configurar" in cliente.get(f"{BASE}/tabla").text
    assert "no tiene configurada la carpeta de las copias" in cliente.get(f"{BASE}/accion/respaldo").text
    assert not list((tmp_path / "copias").glob("*.zip")) if (tmp_path / "copias").exists() else True


def test_la_copia_se_hace_se_lleva_y_se_verifica_en_la_carpeta_de_la_empresa(cliente, tmp_path):
    destino = tmp_path / "OneDrive" / "COPIAS CONTABILIDAD"
    _configurar(cliente, destino)
    assert "No hay ninguna copia en" in cliente.get(f"{BASE}/tabla").text  # configurada pero sin copias: pendiente
    previo = cliente.get(f"{BASE}/accion/respaldo").text
    assert "Hacer la copia ahora" in previo and "ninguna" in previo and not destino.exists()  # ver no copia
    assert "Haciendo la copia de seguridad" in previo and "se cerrará sola cuando termine" in previo and "find button[type=submit]" in previo  # el aviso de espera, oculto hasta que se pulsa
    respuesta = cliente.post(f"{BASE}/accion/respaldo")
    senal = json.loads(respuesta.headers["HX-Trigger"])["mensaje"]  # la acción termina bien: se cierra el diálogo y se avisa, sin pantalla de «hecho»
    assert respuesta.text == "" and "Copia de seguridad hecha, verificada y llevada a" in senal["texto"] and str(destino) in senal["texto"]
    llegada = list(destino.glob("copia_prueba_*.zip"))
    assert len(llegada) == 1 and copias.verificar_copia(llegada[0]) == [] and not list(destino.glob("*.parcial"))
    assert len(list((tmp_path / "copias").glob("copia_prueba_*.zip"))) == 1  # y queda la copia local
    assert "posterior al último cambio" in cliente.get(f"{BASE}/tabla").text  # con la copia hecha, el paso está al día


def test_un_cambio_posterior_deja_el_paso_pendiente(cliente, tmp_path):
    _configurar(cliente, tmp_path / "OneDrive")
    cliente.post(f"{BASE}/accion/respaldo")
    time.sleep(1.1)
    _añadir_cuenta(cliente, "62900001")  # un cambio en la contabilidad después de la copia
    assert "Hay cambios posteriores a la última copia" in cliente.get(f"{BASE}/tabla").text
    assert "hay cambios posteriores a la última copia" in cliente.get(f"{BASE}/accion/respaldo").text


def test_si_la_carpeta_no_se_puede_escribir_se_avisa_y_se_conserva_la_copia_local(cliente, tmp_path):
    ocupado = tmp_path / "es_un_fichero"
    ocupado.write_text("no es una carpeta")
    _configurar(cliente, ocupado / "copias")
    mensaje = cliente.post(f"{BASE}/accion/respaldo").text
    assert "no se pudo llevar a" in mensaje and "La copia está hecha en" in mensaje
    assert len(list((tmp_path / "copias").glob("copia_prueba_*.zip"))) == 1
