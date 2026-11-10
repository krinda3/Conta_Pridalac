"""Las bases creadas con un modelo anterior ganan las columnas nuevas sin perder nada."""
from decimal import Decimal

from sqlalchemy import inspect, text

from conta_pridalac.db.modelos import Empresa, Tercero
from conta_pridalac.db.sesion import actualizar_esquema, crear_esquema, crear_motor, nueva_sesion


def test_una_base_antigua_gana_las_columnas_nuevas(tmp_path):
    motor = crear_motor(tmp_path / "vieja.sqlite")
    crear_esquema(motor)
    with motor.begin() as c:  # se simula una base de antes: sin las columnas de la ficha del tercero
        c.execute(text("PRAGMA foreign_keys=OFF"))
        c.execute(text("ALTER TABLE tercero RENAME TO tercero_nueva"))
        c.execute(text("CREATE TABLE tercero (id INTEGER PRIMARY KEY, empresa_id INTEGER NOT NULL, clase VARCHAR(1) NOT NULL, numero_origen INTEGER, nombre VARCHAR(128) NOT NULL, "
                       "comercial VARCHAR(64), nif VARCHAR(20), cuenta_id INTEGER, cuenta_irpf_id INTEGER)"))
        c.execute(text("DROP TABLE tercero_nueva"))
        c.execute(text("INSERT INTO empresa (id, codigo, nombre) VALUES (1, 1, 'Prueba')"))
        c.execute(text("INSERT INTO tercero (id, empresa_id, clase, nombre) VALUES (1, 1, 'P', 'Antiguo')"))
    columnas = {c["name"] for c in inspect(motor).get_columns("tercero")}
    assert "iban" not in columnas
    anadidas = actualizar_esquema(motor)
    assert "tercero.iban" in anadidas and "tercero.pct_iva_deducible" in anadidas and "tercero.recargo_equivalencia" in anadidas
    s = nueva_sesion(motor)
    t = s.get(Tercero, 1)
    assert t.nombre == "Antiguo" and t.iban is None and t.recargo_equivalencia is False and t.pct_iva_deducible == Decimal("100.00")
    t.iban = "ES9121000418450200051332"
    s.commit()
    assert s.get(Tercero, 1).iban == "ES9121000418450200051332"
    assert actualizar_esquema(motor) == []  # idempotente
