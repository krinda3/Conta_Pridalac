"""Motor y sesión. SQLite por empresa; claves foráneas activadas."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from conta_pridalac.db import registro  # engancha el registro de cambios a la sesión y define su tabla
from conta_pridalac.db.modelos import Base


def crear_motor(ruta: str | Path | None = None) -> Engine:
    """`None` → base de datos en memoria (tests)."""
    url = "sqlite://" if ruta is None else f"sqlite:///{ruta}"
    motor = create_engine(url)

    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):  # pragma: no cover - cableado de SQLite
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return motor


def crear_esquema(motor: Engine) -> None:
    """Crea las tablas que faltan y añade a las que ya existen las columnas nuevas (ver `actualizar_esquema`)."""
    Base.metadata.create_all(motor)
    actualizar_esquema(motor)
    with motor.begin() as conexion:
        registro.crear_disparadores(conexion)


def _literal(valor) -> str:
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, (int, float)):
        return str(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def actualizar_esquema(motor: Engine) -> list[str]:
    """Añade a las bases ya creadas las columnas que el modelo ha ido ganando (SQLite no las crea con `create_all`).

    Sólo se pueden añadir columnas que admitan nulos o tengan valor por defecto; las claves foráneas añadidas así quedan sin la
    restricción (las bases nuevas sí la llevan). Devuelve las columnas añadidas, como `tabla.columna`.
    """
    inspector = inspect(motor)
    anadidas: list[str] = []
    with motor.begin() as conexion:
        for tabla in Base.metadata.sorted_tables:
            if not inspector.has_table(tabla.name):
                continue
            existentes = {c["name"] for c in inspector.get_columns(tabla.name)}
            for columna in tabla.columns:
                if columna.name in existentes:
                    continue
                defecto = None
                if columna.default is not None and getattr(columna.default, "is_scalar", False):
                    defecto = columna.default.arg
                    procesador = columna.type.dialect_impl(motor.dialect).bind_processor(motor.dialect)
                    defecto = procesador(defecto) if procesador else defecto
                if not columna.nullable and defecto is None:
                    raise RuntimeError(f"No se puede añadir {tabla.name}.{columna.name}: no admite nulos y no tiene valor por defecto")
                sql = f'ALTER TABLE "{tabla.name}" ADD COLUMN "{columna.name}" {columna.type.compile(motor.dialect)}'
                if defecto is not None:
                    sql += f" DEFAULT {_literal(defecto)}"
                conexion.execute(text(sql))
                anadidas.append(f"{tabla.name}.{columna.name}")
    return anadidas


def nueva_sesion(motor: Engine) -> Session:
    return sessionmaker(motor, expire_on_commit=False)()
