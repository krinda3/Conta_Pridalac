"""Regularización y cierre reconstruidos desde el Diario de un ejercicio ya cerrado en MGD (2020) = los que grabó MGD."""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
from validar_cierre_mgd import main  # noqa: E402

pytestmark = pytest.mark.datos_reales


@pytest.mark.parametrize("fichero, tras", [("EMPRESA A Diario.dbf", "4"), ("EMPRESA B Diario.dbf", "3")])
def test_r_y_z_de_2020_coinciden_con_mgd(fichero, tras, monkeypatch):
    ruta = RAIZ / "datos_locales" / fichero
    if not ruta.exists():
        pytest.skip(f"No está {ruta}")
    monkeypatch.setenv("CERO_TRAS", tras)
    reales, mios = main(str(ruta), 2020)
    assert reales["R"] and reales["Z"]
    for sub in ("R", "Z"):
        assert {c: i for c, i in mios[sub].items() if i} == reales[sub], sub
