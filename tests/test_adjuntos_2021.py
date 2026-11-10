"""Justificantes (PDF) de MGD 2021: tabla Etidat + carpeta de ficheros, para Empresa A y Empresa B."""
from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from conta_pridalac.db.modelos import Adjunto, Factura
from conta_pridalac.migracion.mgd import _justificantes_por_documento

pytestmark = pytest.mark.datos_reales

# Cifras de las tablas y carpetas originales. "faltantes" = referenciados en Etidat pero sin fichero en la copia.
ESPERADO = {
    "empresa_a": {"adjuntos": 56, "faltantes": 7, "huerfanos": 0},
    "empresa_b": {"adjuntos": 162, "faltantes": 18, "huerfanos": 0},
}


def test_recompone_la_lista_de_ficheros_troceada_en_bloques_de_64():
    filas = [
        {"TIPO": "R", "NUMERO": 18, "CLAVE": "?", "TEXTO": "011_R_00062_Renfe 01.pdf;011_R_00063_Renfe 02.pdf;011_R_00064_Re"},
        {"TIPO": "R", "NUMERO": 18, "CLAVE": "?", "TEXTO": "nfe 03.pdf;011_R_00065_Renfe 04.pdf"},
        {"TIPO": "R", "NUMERO": 19, "CLAVE": "?", "TEXTO": "011_R_00070_Otra.pdf"},
        {"TIPO": "R", "NUMERO": 20, "CLAVE": "X", "TEXTO": "se ignora: no es un justificante"},
    ]
    assert _justificantes_por_documento(filas) == {
        ("R", 18): ["011_R_00062_Renfe 01.pdf", "011_R_00063_Renfe 02.pdf", "011_R_00064_Renfe 03.pdf", "011_R_00065_Renfe 04.pdf"],
        ("R", 19): ["011_R_00070_Otra.pdf"],
    }


def test_cifras_de_adjuntos(sesion, carga_mgd):
    esperado = ESPERADO[carga_mgd.clave]
    assert carga_mgd.adjuntos == esperado["adjuntos"]
    assert len(carga_mgd.adjuntos_faltantes) == esperado["faltantes"]
    assert len(carga_mgd.adjuntos_huerfanos) == esperado["huerfanos"]
    assert sesion.scalar(select(func.count()).select_from(Adjunto)) == esperado["adjuntos"]


def test_los_presentes_tienen_huella_y_los_faltantes_no(sesion, carga_mgd):
    adjuntos = sesion.scalars(select(Adjunto)).all()
    presentes = [a for a in adjuntos if a.presente]
    assert len(presentes) == len(adjuntos) - len(carga_mgd.adjuntos_faltantes)
    for a in presentes:
        assert len(a.sha256) == 64 and a.tamano > 0
    for a in adjuntos:
        assert a.presente == (a.nombre not in carga_mgd.adjuntos_faltantes)


def test_cada_adjunto_cuelga_de_un_unico_documento_y_de_la_misma_empresa(sesion, carga_mgd):
    for a in sesion.scalars(select(Adjunto)):
        origenes = [a.factura_id, a.movimiento_banco_id, a.asiento_id]
        assert sum(o is not None for o in origenes) == 1
    # el prefijo del nombre (011/012) es la empresa de MGD
    prefijos = Counter(a.nombre[:3] for a in sesion.scalars(select(Adjunto)))
    assert set(prefijos) == {"011" if carga_mgd.clave == "empresa_a" else "012"}


def test_el_tipo_del_nombre_coincide_con_el_documento(sesion, carga_mgd):
    """`011_R_…` cuelga de una factura recibida, `_E_` de una emitida, `_B_` de un movimiento de banco, `_X_` de un extra."""
    for a in sesion.scalars(select(Adjunto)):
        tipo = a.nombre[4]
        if tipo in ("R", "E"):
            assert a.factura_id is not None and sesion.get(Factura, a.factura_id).sentido == tipo
        elif tipo == "B":
            assert a.movimiento_banco_id is not None
        elif tipo == "X":
            assert a.asiento_id is not None


def test_la_base_de_datos_rechaza_un_adjunto_sin_documento_o_con_dos(sesion, carga_mgd):
    ok = sesion.scalars(select(Adjunto)).first()
    sesion.add(Adjunto(nombre="x.pdf", ruta_relativa="x.pdf", tipo_mime="application/pdf"))
    with pytest.raises(IntegrityError):
        sesion.flush()
    sesion.rollback()
    sesion.add(Adjunto(factura_id=ok.factura_id or 1, asiento_id=1, nombre="y.pdf", ruta_relativa="y.pdf", tipo_mime="application/pdf"))
    with pytest.raises(IntegrityError):
        sesion.flush()
    sesion.rollback()
