"""Las sumas por cuenta (3 dígitos) del Diario de MGD 2020 son las del Balance de sumas y saldos del programa anterior."""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
from comparar_balance_programa_anterior import main  # noqa: E402

pytestmark = pytest.mark.datos_reales


@pytest.mark.parametrize("empresa", ["EMPRESA A", "EMPRESA B"])
def test_balance_2020_coincide_con_el_diario(empresa):
    diario = RAIZ / "datos_locales" / f"{empresa} Diario.dbf"
    pdf = RAIZ / "docs" / "Exportaciones del programa anterior" / f"{empresa} Balance de sumas y saldos del año 2020.pdf"
    if not (diario.exists() and pdf.exists()):
        pytest.skip("Faltan el Diario de 2020 o el balance en PDF")
    real, mio, difs = main(str(diario), str(pdf))
    assert len(real) >= 30 and set(real) == set(mio)
    assert difs == {}
