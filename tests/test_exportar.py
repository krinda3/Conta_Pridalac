"""Copia de los ficheros generados a una carpeta fácil de encontrar y con un nombre que se entienda."""
from pathlib import Path

import pytest

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.servicios.exportar import carpeta_de_descargas, carpeta_para_presentar, copiar_para_presentar, nombre_corto, nombre_para_presentar


@pytest.mark.parametrize(
    "nombre, corto, esperado",
    [
        ("EMPRESA A S.L.", None, "EMPRESA_A"),
        ("EMPRESA B S.L.", None, "EMPRESA_B"),
        ("Empresa A, S.L.U.", "", "EMPRESA_A"),
        ("EMPRESA A S.L.", "Corto", "CORTO"),
        ("Cooperativa Ñandú S. Coop.", None, "COOPERATIVA_NANDU"),
        ("ARIAS Y ASOCIADOS S.A.", None, "ARIAS_Y_ASOCIADOS"),
        ("???", None, "EMPRESA"),
    ],
)
def test_prefijo_del_nombre_de_fichero(nombre, corto, esperado):
    assert nombre_corto(Empresa(nombre=nombre, nombre_corto=corto)) == esperado


def test_nombre_del_fichero_para_presentar():
    empresa_a = Empresa(nombre="EMPRESA A S.L.", nombre_corto="EMPRESA A")
    assert nombre_para_presentar(empresa_a, "303", 2026, "1T", "rectificativa", "303") == "EMPRESA_A_AEAT_303_2026_1T_rectificativa.303"
    assert nombre_para_presentar(empresa_a, "111", 2026, "4T", "normal", ".111") == "EMPRESA_A_AEAT_111_2026_4T.111"


def test_copiar_no_pisa_un_fichero_distinto_y_no_repite_uno_igual(tmp_path):
    origen = tmp_path / "origen.303"
    origen.write_bytes(b"<T303>uno")
    carpeta = tmp_path / "descargas" / "Conta Pridalac"
    ruta, nueva = copiar_para_presentar(origen, carpeta, "EMPRESA_A_AEAT_303_2026_1T.303")
    assert (ruta, nueva) == (carpeta / "EMPRESA_A_AEAT_303_2026_1T.303", True) and ruta.read_bytes() == b"<T303>uno"
    assert copiar_para_presentar(origen, carpeta, "EMPRESA_A_AEAT_303_2026_1T.303") == (ruta, False)  # el mismo contenido: no se repite
    origen.write_bytes(b"<T303>dos")  # otro contenido con el mismo nombre
    segunda, nueva = copiar_para_presentar(origen, carpeta, "EMPRESA_A_AEAT_303_2026_1T.303")
    assert nueva and segunda.name == "EMPRESA_A_AEAT_303_2026_1T_2.303" and ruta.read_bytes() == b"<T303>uno" and segunda.read_bytes() == b"<T303>dos"
    origen.write_bytes(b"<T303>tres")
    assert copiar_para_presentar(origen, carpeta, "EMPRESA_A_AEAT_303_2026_1T.303")[0].name == "EMPRESA_A_AEAT_303_2026_1T_3.303"


def test_la_carpeta_de_descargas_y_la_de_presentar(monkeypatch, tmp_path):
    assert isinstance(carpeta_de_descargas(), Path) and carpeta_de_descargas().name  # la que diga el sistema (puede estar redirigida)
    monkeypatch.delenv("CONTA_DESCARGAS", raising=False)
    assert carpeta_para_presentar() == carpeta_de_descargas() / "Conta Pridalac"
    monkeypatch.setenv("CONTA_DESCARGAS", str(tmp_path / "otra"))
    assert carpeta_para_presentar() == tmp_path / "otra"


def test_el_explorador_recibe_la_ruta_con_espacios_entrecomillada(monkeypatch, tmp_path):
    from conta_pridalac.servicios import exportar

    ordenes = []
    monkeypatch.setattr(exportar.subprocess, "Popen", lambda args, *a, **k: ordenes.append(args))
    monkeypatch.setattr(exportar.os, "name", "nt")
    ruta = tmp_path / "Conta Pridalac" / "X_AEAT_303_2026_1T.303"
    exportar.abrir_en_el_explorador(ruta)
    assert ordenes == [f'explorer /select,"{ruta}"']
