"""Herramientas de corrección de las declaraciones presentadas importadas."""
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))

import completar_declaracion  # noqa: E402
import corregir_periodo_declaracion  # noqa: E402

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa  # noqa: E402
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion  # noqa: E402


@pytest.fixture
def base(tmp_path):
    motor = crear_motor(tmp_path / "p.sqlite")
    crear_esquema(motor)
    s = nueva_sesion(motor)
    e = Empresa(codigo=1, nombre="P", nif="B12345678")
    s.add(e)
    s.flush()
    for periodo, tipo, just in ((6, 2, "3033015825734"), (2, 2, None), (2, 1, None), (1, 1, None)):
        s.add(DeclaracionPresentada(empresa_id=e.id, modelo="303", anio=2022, periodo=periodo, tipo=tipo, justificante=just, casillas="{}"))
    s.commit()
    s.close()
    motor.dispose()
    return tmp_path


def estado(base):
    motor = crear_motor(base / "p.sqlite")
    s = nueva_sesion(motor)
    try:
        return sorted((d.periodo, d.tipo, d.justificante) for d in s.scalars(select(DeclaracionPresentada)))
    finally:
        s.close()
        motor.dispose()


def test_cambia_periodo_y_tipo_solo_si_hay_hueco(base, capsys):
    args = ["--nombre", "p", "--datos", str(base), "--modelo", "303", "--anio", "2022", "--de", "6", "--a", "2", "--tipo", "2"]
    assert corregir_periodo_declaracion.main(args + ["--aplicar"]) == 1  # (2, 2) ya existe
    assert "tipo libre" in capsys.readouterr().out and (6, 2, "3033015825734") in estado(base)
    assert corregir_periodo_declaracion.main(args + ["--tipo-destino", "3"]) == 0 and (6, 2, "3033015825734") in estado(base)  # sin --aplicar no cambia nada
    assert corregir_periodo_declaracion.main(args + ["--tipo-destino", "3", "--aplicar"]) == 0
    assert (2, 3, "3033015825734") in estado(base) and (6, 2, "3033015825734") not in estado(base)


def test_completa_lo_vacio_y_no_pisa(base, capsys):
    args = ["--nombre", "p", "--datos", str(base), "--modelo", "303", "--anio", "2022", "--periodo", "1", "--justificante", "3033015265052", "--fecha", "2022-04-14"]
    assert completar_declaracion.main(args) == 0 and (1, 1, None) in estado(base)
    assert completar_declaracion.main(args + ["--aplicar"]) == 0 and (1, 1, "3033015265052") in estado(base)
    capsys.readouterr()
    otro = ["--nombre", "p", "--datos", str(base), "--modelo", "303", "--anio", "2022", "--periodo", "1", "--justificante", "9999999999999", "--aplicar"]
    assert completar_declaracion.main(otro) == 0
    assert "no se pisa" in capsys.readouterr().out and (1, 1, "3033015265052") in estado(base)
