"""Importación de los 347 ya presentados desde sus ficheros."""
from datetime import date
from decimal import Decimal

from conta_pridalac.db.modelos import Ejercicio, Empresa
from conta_pridalac.ficheros_aeat.fichero347 import Declarado347, Declaracion347, generar
from conta_pridalac.migracion.declaraciones347 import cargar_declaraciones_347
from conta_pridalac.servicios.presentacion303 import presentada_del_periodo

D = Decimal


def fichero(carpeta, nif, anio, ident, con_declarado=True):
    d = Declaracion347(nif=nif, nombre="PRUEBA S.L.", ejercicio=anio, contacto_telefono="600111222", contacto_nombre="PEREZ GOMEZ ANA", identificativo=ident,
                       declarados=[Declarado347("12345678Z", "AGRICULTOR UNO", "13", "A", [D("0"), D("3000.00"), D("0"), D("1000.50")])] if con_declarado else [])
    (carpeta / f"C0001_347_{anio}.347").write_bytes(generar(d).encode("latin-1"))


def test_importa_los_de_su_empresa_una_sola_vez(sesion, tmp_path):
    e = Empresa(codigo=1, nombre="Prueba S.L.", nif="B12345678")
    sesion.add_all([e, Ejercicio(anio=2025, fecha_inicio=date(2025, 1, 1), fecha_fin=date(2025, 12, 31), empresa=e)])
    sesion.flush()
    fichero(tmp_path, "B12345678", 2024, "3470000000024", con_declarado=False)
    fichero(tmp_path, "B12345678", 2025, "3470000000025")
    fichero(tmp_path, "B99999999", 2023, "3470000000023")  # de otra empresa
    assert cargar_declaraciones_347(sesion, e, tmp_path) == (2, [])
    assert cargar_declaraciones_347(sesion, e, tmp_path) == (0, [])
    d = presentada_del_periodo(sesion, e.id, 2025, 0, "347")
    assert (d.justificante, d.periodo, d.resultado) == ("3470000000025", 0, D("4000.50"))
    assert '"declarados": 1' in d.casillas and '"nif": "12345678Z"' in d.casillas and '"clave": "A"' in d.casillas
    assert '"declarados": 0' in presentada_del_periodo(sesion, e.id, 2024, 0, "347").casillas
    assert presentada_del_periodo(sesion, e.id, 2023, 0, "347") is None
