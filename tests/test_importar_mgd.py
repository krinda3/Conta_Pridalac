"""Herramienta `tools/importar_mgd.py`: crea una empresa nueva desde una copia de MGD, con los dígitos de su plan."""
import sys
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

import importar_mgd  # noqa: E402

from conta_pridalac.db.modelos import Cuenta, Empresa  # noqa: E402
from conta_pridalac.db.sesion import crear_motor, nueva_sesion  # noqa: E402
from conta_pridalac.migracion.mgd import explorar_copia  # noqa: E402


@pytest.fixture
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTA_DATOS", str(tmp_path / "bd"))
    return tmp_path / "bd"


def test_slug_de():
    assert importar_mgd.slug_de("Fundación Ñandú & Co., S.L.") == "fundacion-nandu-co-s-l" and importar_mgd.slug_de("¿¿") == "empresa"


def test_algo_que_no_es_una_copia_se_rechaza(datos, tmp_path, capsys):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    assert importar_mgd.main([str(vacia), "--nombre", "X"]) == 1
    assert "No parece una copia de MGD" in capsys.readouterr().err
    assert importar_mgd.main([str(tmp_path / "no_existe.zip")]) == 1 and not datos.exists()


def test_explorar_una_copia(carpeta_mgd_2021):
    c = explorar_copia(carpeta_mgd_2021)
    assert c.digitos_cuenta == 7 and c.anio == 2021 and c.asientos > 0 and c.codigo_empresa == 11


def test_sin_aplicar_no_crea_nada_y_con_aplicar_crea_la_empresa(datos, carpeta_mgd_2021, tmp_path, capsys):
    assert importar_mgd.main([str(carpeta_mgd_2021), "--nombre", "Empresa Amiga S.L.", "--nif", "B12345678"]) == 0
    assert not datos.exists() and "No se ha creado nada" in capsys.readouterr().out
    assert importar_mgd.main([str(carpeta_mgd_2021), "--nombre", "Empresa Amiga S.L.", "--nif", "B12345678", "--aplicar"]) == 0
    fichero = datos / "empresa-amiga-s-l.sqlite"
    assert fichero.exists()
    s = nueva_sesion(crear_motor(fichero))
    e = s.scalars(select(Empresa)).one()
    assert (e.nombre, e.nif, e.digitos_cuenta) == ("Empresa Amiga S.L.", "B12345678", 7)
    assert set(s.scalars(select(func.length(Cuenta.codigo)))) == {7}
    assert (tmp_path / "justificantes").is_dir()
    # nunca sustituye una empresa que ya existe
    assert importar_mgd.main([str(carpeta_mgd_2021), "--nombre", "Empresa Amiga S.L.", "--aplicar"]) == 1
    assert "nunca sustituye" in capsys.readouterr().err


def test_un_zip_con_los_ficheros_en_una_carpeta_interior(datos, carpeta_mgd_2021, tmp_path):
    z = tmp_path / "copia.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for real in carpeta_mgd_2021.iterdir():
            if real.is_file() and real.suffix.lower() != ".pdf":
                zf.write(real, f"copia/{real.name}")
    assert importar_mgd.main([str(z), "--nombre", "Desde Zip", "--aplicar"]) == 0
    assert (datos / "desde-zip.sqlite").exists()


def test_si_la_carga_falla_no_queda_una_empresa_a_medias(datos, carpeta_mgd_2021, tmp_path, capsys):
    rota = tmp_path / "rota"
    rota.mkdir()
    for f in ("Diario.dbf", "Cuentas.dbf"):  # lo justo para parecer una copia, pero sin el resto de las tablas
        (rota / f).write_bytes((carpeta_mgd_2021 / f).read_bytes())
    with pytest.raises(Exception):
        importar_mgd.main([str(rota), "--nombre", "Rota", "--aplicar"])
    assert list(datos.glob("*.sqlite")) == []


def test_si_no_encuentra_el_zip_dice_donde_lo_ha_buscado(datos, capsys):
    assert importar_mgd.main(["no_esta.zip", "--nombre", "X"]) == 1
    err = capsys.readouterr().err
    assert "no_esta.zip" in err and "ruta completa" in err and str(Path.cwd()) in err
