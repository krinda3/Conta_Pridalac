"""Las huellas del registro de cambios guardadas fuera de la base: copias, restauración, presentación, cierre y la comprobación de la auditoría."""
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.db.registro import RegistroCambio
from conta_pridalac.db.sesion import crear_esquema, nueva_sesion
from conta_pridalac.servicios import copias, huellas
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "bd" / "prueba.sqlite"
    ruta.parent.mkdir()
    motor = create_engine(f"sqlite:///{ruta}")
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    sesion.add(Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678"))
    sesion.commit()
    yield sesion, ruta, tmp_path / "almacen", tmp_path / "copias"
    sesion.close()
    motor.dispose()


def _lineas(almacen):
    return huellas.ruta_del_fichero(almacen, 1).read_text(encoding="utf-8").splitlines()


def test_cada_copia_anota_la_ultima_huella_fuera_de_la_base(base):
    sesion, ruta, almacen, carpeta = base
    ultima = huellas.ultima_de_archivo(ruta)
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    (linea,) = _lineas(almacen)
    assert f" | {ultima[0]} | {ultima[1]} | " in linea and "copia de seguridad" in linea
    assert huellas.comprobar(sesion, almacen, 1) == []


def test_si_se_reescribe_el_registro_la_comprobacion_lo_detecta(base):
    sesion, ruta, almacen, carpeta = base
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    sesion.execute(text("DROP TRIGGER registro_cambios_sin_update"))
    sesion.execute(text("UPDATE registro_cambios SET huella = 'x' || substr(huella, 2) WHERE id = (SELECT MAX(id) FROM registro_cambios)"))
    sesion.commit()
    (problema,) = huellas.comprobar(sesion, almacen, 1)
    assert "se ha reescrito el registro" in problema


def test_si_faltan_anotaciones_se_detecta_y_la_restauracion_lo_explica(base):
    sesion, ruta, almacen, carpeta = base
    antigua = copias.hacer_copia("prueba", ruta, almacen, carpeta)  # con las anotaciones 1 y 2
    sesion.add(Empresa(codigo=2, nombre="Otra"))
    sesion.commit()
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    sesion.execute(text("DROP TRIGGER registro_cambios_sin_delete"))
    sesion.execute(text("DELETE FROM registro_cambios WHERE id = (SELECT MAX(id) FROM registro_cambios)"))
    sesion.commit()
    assert "faltan anotaciones" in huellas.comprobar(sesion, almacen, 1)[0]
    # volver a una copia antigua con la herramienta de restaurar deja su propia línea y lo posterior deja de exigirse
    numero, huella = huellas.ultima_de_archivo(ruta)
    huellas.anotar(almacen, 1, f"{huellas.RESTAURACION} de {antigua.name}", numero, huella)
    # la base ya no tiene la anotación citada por la última copia, pero sí la de la restauración
    assert huellas.comprobar(sesion, almacen, 1) == []


def test_si_se_toca_el_fichero_de_huellas_se_detecta(base):
    sesion, ruta, almacen, carpeta = base
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    fichero = huellas.ruta_del_fichero(almacen, 1)
    primera, segunda = fichero.read_text(encoding="utf-8").splitlines()
    fichero.write_text(primera.replace("copia de seguridad", "otra cosa") + "\n" + segunda + "\n", encoding="utf-8")
    assert "ha sido modificado" in huellas.comprobar(sesion, almacen, 1)[0]


def test_lo_que_se_deshace_no_deja_huella(base):
    sesion, ruta, almacen, carpeta = base
    sesion.add(Empresa(codigo=3, nombre="Se deshace"))
    sesion.flush()
    huellas.anotar_al_confirmar(sesion, almacen, 1, "prueba")
    sesion.rollback()
    sesion.commit()
    assert not huellas.ruta_del_fichero(almacen, 1).exists()
    huellas.anotar_al_confirmar(sesion, almacen, 1, "prueba")
    sesion.add(Empresa(codigo=4, nombre="Se confirma"))
    sesion.commit()
    (linea,) = _lineas(almacen)
    assert linea.split(" | ")[1] == "prueba" and int(linea.split(" | ")[2]) == huellas.ultima_de_archivo(ruta)[0]


def test_la_auditoria_lo_avisa(base):
    from conta_pridalac.auditoria import auditar
    from conta_pridalac.db.modelos import Ejercicio

    sesion, ruta, almacen, carpeta = base
    empresa = sesion.query(Empresa).first()
    ej = Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=empresa)
    sesion.add(ej)
    sesion.commit()
    copias.hacer_copia("prueba", ruta, almacen, carpeta)
    assert "huellas_externas_no_coinciden" not in {h.codigo for h in auditar(sesion, ej, almacen=AlmacenAdjuntos(almacen))}
    sesion.execute(text("DROP TRIGGER registro_cambios_sin_update"))
    sesion.execute(text("UPDATE registro_cambios SET huella = 'x' || substr(huella, 2) WHERE id = (SELECT MAX(id) FROM registro_cambios)"))
    sesion.commit()
    (h,) = [h for h in auditar(sesion, ej, almacen=AlmacenAdjuntos(almacen)) if h.codigo == "huellas_externas_no_coinciden"]
    assert h.gravedad == "ERROR"
