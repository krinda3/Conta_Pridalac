import os
from pathlib import Path

import pytest

from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion

# Los datos reales NO están en el repositorio. Se localizan por variable de entorno o por la ruta de desarrollo.
MGD_2021_DEFECTO = r"D:\Proyectos\GestionMGD Access\BBDD 2021"


@pytest.fixture(autouse=True)
def _config_de_usuario_aislada(tmp_path_factory, monkeypatch):
    """Ningún test lee ni escribe la configuración real del usuario (dónde están sus datos)."""
    monkeypatch.setenv("CONTA_CONFIG", str(tmp_path_factory.mktemp("config_usuario")))


@pytest.fixture(autouse=True)
def _sin_red_al_boe(monkeypatch):
    """Ningún test consulta el BOE de verdad: el que quiera datos del BOE pasa su propio `abrir_boe`."""
    from conta_pridalac.servicios import normativa

    def sin_red(dia):
        raise OSError("sin red en los tests")

    monkeypatch.setattr(normativa, "_boe_dia", sin_red)


@pytest.fixture(autouse=True)
def _descargas_de_prueba(tmp_path_factory, monkeypatch):
    """Los tests no tocan las Descargas reales del usuario."""
    monkeypatch.setenv("CONTA_DESCARGAS", str(tmp_path_factory.mktemp("descargas")))


@pytest.fixture
def sesion():
    motor = crear_motor(None)
    crear_esquema(motor)
    s = nueva_sesion(motor)
    yield s
    s.close()


@pytest.fixture(scope="session")
def carpeta_mgd_2021() -> Path:
    ruta = Path(os.environ.get("CONTA_MGD_2021", MGD_2021_DEFECTO))
    if not (ruta / "Diario.dbf").exists():
        pytest.skip(f"No hay datos MGD 2021 en {ruta} (define CONTA_MGD_2021)")
    return ruta


# Segunda empresa: copia de MGD de Empresa B (empresa 012). Vive en `datos_locales/` (ignorada por git).
EMPRESA_B_2021_DEFECTO = Path(__file__).resolve().parents[1] / "datos_locales" / "mgd_empresa_b_2021"

EMPRESAS_MGD_2021 = {
    "empresa_a": {"codigo": 11, "nombre": "Empresa A"},
    "empresa_b": {"codigo": 12, "nombre": "Empresa B"},
}


def _carpeta_empresa(clave: str) -> Path:
    if clave == "empresa_a":
        return Path(os.environ.get("CONTA_MGD_2021", MGD_2021_DEFECTO))
    return Path(os.environ.get("CONTA_MGD_EMPRESA_B_2021", EMPRESA_B_2021_DEFECTO))


@pytest.fixture(params=sorted(EMPRESAS_MGD_2021))
def carga_mgd(request, sesion):
    """Carga cada empresa de MGD 2021 (Empresa A y Empresa B). Se omite si no están los datos de esa empresa."""
    from conta_pridalac.migracion.mgd import cargar_mgd

    carpeta = _carpeta_empresa(request.param)
    if not (carpeta / "Diario.dbf").exists():
        pytest.skip(f"No hay datos MGD 2021 de {request.param} en {carpeta}")
    datos = EMPRESAS_MGD_2021[request.param]
    res = cargar_mgd(sesion, carpeta, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
    sesion.commit()
    res.clave = request.param
    return res
