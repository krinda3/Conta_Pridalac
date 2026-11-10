"""Importación de los modelos 111 ya presentados desde el programa anterior (tabla 199) y de sus PDF."""
import json
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio, Empresa
from conta_pridalac.migracion.comprobantes import enlazar_pdfs_de_declaraciones
from conta_pridalac.migracion.programa_anterior import cargar_declaraciones_111
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos


@pytest.fixture
def empresa(sesion):
    e = Empresa(codigo=9, nombre="Prueba S.L.", nif="B12345678")
    sesion.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    sesion.flush()
    return e


@pytest.fixture
def respaldo():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("create table C0009199 (ANO int, PER int, TIPDEC int, CAS7 real, CAS8 real, CAS9 real, CAS28 real, CAS30 real, FECEMI int, FECENV int, NUMDEC text)")
    con.executemany("insert into C0009199 values (?,?,?,?,?,?,?,?,?,?,?)", [
        (2025, 3, 1, 0, 0, 0, 0, 0, 20251009, 20251009, "1116926253615"),
        (2025, 4, 1, 1, 1904.0, 38.08, 38.08, 38.08, 20260112, 20260112, "1116996603852"),
        (2020, 4, 1, 0, 0, 0, 0, 0, 20210112, 20210112, "1110000000000"),
    ])
    return con


def test_carga_los_111_presentados_sin_repetirlos(sesion, empresa, respaldo):
    assert cargar_declaraciones_111(sesion, respaldo, "C0009", empresa, 2021) == 2  # el de 2020 queda fuera
    assert cargar_declaraciones_111(sesion, respaldo, "C0009", empresa, 2021) == 0  # repetirlo no duplica
    ds = sesion.scalars(select(DeclaracionPresentada).order_by(DeclaracionPresentada.periodo)).all()
    assert [(d.modelo, d.anio, d.periodo, d.tipo) for d in ds] == [("111", 2025, 3, 1), ("111", 2025, 4, 1)]
    cuarto = ds[1]
    assert (cuarto.resultado_liquidacion, cuarto.resultado, cuarto.justificante, cuarto.fecha_emision) == (Decimal("38.08"), Decimal("38.08"), "1116996603852", date(2026, 1, 12))
    assert json.loads(cuarto.casillas) == {"7": 1, "8": 1904.0, "9": 38.08, "28": 38.08, "30": 38.08}
    assert json.loads(ds[0].casillas) == {}  # un trimestre sin actividad


def test_un_respaldo_sin_la_tabla_no_falla(sesion, empresa):
    assert cargar_declaraciones_111(sesion, sqlite3.connect(":memory:"), "C0009", empresa, 2021) == 0


def test_enlaza_los_pdf_del_111_y_deja_los_del_303(sesion, empresa, respaldo, tmp_path):
    cargar_declaraciones_111(sesion, respaldo, "C0009", empresa, 2021)
    carpeta = tmp_path / "comprobantes" / "2025"
    carpeta.mkdir(parents=True)
    pdf = b"%PDF-1.4\n%justificante\n"
    (carpeta / "C0009_111_2025_04.PDF").write_bytes(pdf)
    (carpeta / "C0009_111_2025_02.PDF").write_bytes(pdf)  # sin declaración en la base
    (carpeta / "C0009_303_2025_04.PDF").write_bytes(pdf)  # de otro modelo: no es de esta función
    (carpeta / "C0001_111_2025_04.PDF").write_bytes(pdf)  # de otra empresa
    almacen = AlmacenAdjuntos(tmp_path / "almacen")
    enlazados, sin = enlazar_pdfs_de_declaraciones(sesion, almacen, empresa, tmp_path / "comprobantes", ("111",))
    assert enlazados == 1 and [x.split("/")[-1] for x in sin] == ["C0009_111_2025_02.PDF"]
    d = sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.periodo == 4)).one()
    assert d.pdf_nombre == "C0009_111_2025_04.PDF" and d.pdf_ruta.startswith("009/2025/D/") and (tmp_path / "almacen" / d.pdf_ruta).read_bytes() == pdf
