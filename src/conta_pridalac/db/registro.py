"""Registro de cambios inalterable: cada alta, cambio y baja de los datos contables queda anotada, con una huella encadenada.

Cumple lo que pide el art. 29.2.j de la LGT (trazabilidad e inalterabilidad: lo que se altere debe dejar anotación en el propio sistema). Se engancha a la sesión de SQLAlchemy, así que no hay que acordarse de anotar en cada
función: cualquier escritura por el ORM (`add`, `delete`, atributos modificados, `delete()` y `update()` masivos) se anota en la misma transacción que el cambio, y si ésta se deshace, la anotación también.

La tabla `registro_cambios` sólo se añade: la base de datos rechaza `UPDATE` y `DELETE` sobre ella (ver `crear_disparadores`). Cada fila lleva el SHA-256 de su contenido y de la fila anterior; `verificar` recorre la cadena y dice
dónde se rompe. Quien tenga el archivo y sepa lo que hace puede reescribir toda la cadena; por eso la última huella debe guardarse también fuera de la base (copias de seguridad y cierres).

No se anotan las lecturas ni lo que no sean datos contables (listas de trabajo, reglas y plantillas). Lo que se escribe con SQL directo, sin pasar por el ORM (migraciones), tampoco.
"""
from __future__ import annotations

import getpass
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Connection, DDL, String, Text, event, func, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from conta_pridalac.db.modelos import Base

LOTE_A_PARTIR_DE = 50  # más altas de una tabla en una misma escritura (una importación): una sola anotación con su resumen y la huella de las filas
HUELLA_INICIAL = ""

ALTA, CAMBIO, BAJA, ALTA_LOTE, INICIO = "alta", "cambio", "baja", "alta_lote", "inicio"

AUDITADAS = frozenset({
    "empresa", "empresa_actividad", "empresa_representante", "ejercicio", "cuenta", "tercero", "asiento", "apunte", "factura", "factura_iva", "factura_ajuste", "adjunto",
    "bien_inversion", "amortizacion_periodo", "declaracion_presentada", "declaracion_linea", "presentacion_aeat", "parametro", "banco", "vencimiento", "movimiento_banco", "pago",
    "extracto", "extracto_linea", "categoria_gasto", "factura_reparto",
})


class RegistroCambio(Base):
    """Una anotación del registro. Nunca se modifica ni se borra."""

    __tablename__ = "registro_cambios"

    id: Mapped[int] = mapped_column(primary_key=True)
    momento: Mapped[str] = mapped_column(String(32))
    usuario: Mapped[str] = mapped_column(String(64))
    tabla: Mapped[str] = mapped_column(String(48))
    fila: Mapped[str] = mapped_column(String(64))
    operacion: Mapped[str] = mapped_column(String(16))
    datos: Mapped[str] = mapped_column(Text)
    origen: Mapped[str | None] = mapped_column(String(64))
    huella_anterior: Mapped[str] = mapped_column(String(64))
    huella: Mapped[str] = mapped_column(String(64))


_TABLA = RegistroCambio.__table__

for _operacion in ("UPDATE", "DELETE"):
    event.listen(_TABLA, "after_create", DDL(
        f"CREATE TRIGGER IF NOT EXISTS registro_cambios_sin_{_operacion.lower()} BEFORE {_operacion} ON registro_cambios "
        f"BEGIN SELECT RAISE(ABORT, 'El registro de cambios sólo se puede añadir'); END"))


def crear_disparadores(conexion: Connection) -> None:
    """Los disparadores que impiden modificar el registro. `create_all` los crea con la tabla; esto los repone en una base que ya la tenía."""
    for operacion in ("UPDATE", "DELETE"):
        conexion.exec_driver_sql(
            f"CREATE TRIGGER IF NOT EXISTS registro_cambios_sin_{operacion.lower()} BEFORE {operacion} ON registro_cambios "
            f"BEGIN SELECT RAISE(ABORT, 'El registro de cambios sólo se puede añadir'); END")


def _usuario() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - sin usuario del sistema no se debe impedir escribir
        return "desconocido"


def _valor(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return f"bytes:{len(v)}"
    return str(v)


def _json(objeto) -> str:
    return json.dumps(objeto, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def calcular_huella(fila: dict) -> str:
    contenido = [fila[k] for k in ("id", "momento", "usuario", "tabla", "fila", "operacion", "datos", "origen", "huella_anterior")]
    return hashlib.sha256(_json(contenido).encode("utf-8")).hexdigest()


class _Escritor:
    """Añade anotaciones a la cadena dentro de la conexión (y la transacción) de la sesión."""

    def __init__(self, sesion: Session):
        self.conexion = sesion.connection()
        self.origen = sesion.info.get("origen")
        self.usuario = _usuario()
        ultima = self.conexion.execute(select(_TABLA.c.id, _TABLA.c.huella).order_by(_TABLA.c.id.desc()).limit(1)).first()
        self.id, self.huella = (ultima[0], ultima[1]) if ultima else (0, HUELLA_INICIAL)

    @property
    def vacio(self) -> bool:
        return self.id == 0

    def anotar(self, tabla: str, fila, operacion: str, datos: dict) -> None:
        anotacion = dict(id=self.id + 1, momento=datetime.now().isoformat(timespec="microseconds"), usuario=self.usuario, tabla=tabla, fila=str(fila), operacion=operacion,
                         datos=_json(datos), origen=self.origen, huella_anterior=self.huella)
        anotacion["huella"] = calcular_huella(anotacion)
        self.conexion.execute(_TABLA.insert(), anotacion)
        self.id, self.huella = anotacion["id"], anotacion["huella"]


def _tabla_de(objeto) -> str:
    return inspect(objeto).mapper.local_table.name


def _clave(objeto) -> str:
    return ",".join(str(x) for x in inspect(objeto).mapper.primary_key_from_instance(objeto))


def _columnas(objeto) -> dict:
    """Los valores cargados de la fila (sin disparar lecturas en mitad de la escritura)."""
    estado = inspect(objeto)
    return {a.key: _valor(estado.dict.get(a.key)) for a in estado.mapper.column_attrs if a.key in estado.dict}


def _cambios(objeto) -> dict:
    estado = inspect(objeto)
    cambios = {}
    for atributo in estado.mapper.column_attrs:
        historia = estado.attrs[atributo.key].history
        if not historia.has_changes():
            continue
        antes = _valor(historia.deleted[0]) if historia.deleted else None
        despues = _valor(historia.added[0]) if historia.added else None
        if antes != despues:
            cambios[atributo.key] = [antes, despues]
    return cambios


def _tablas_presentes(sesion: Session) -> bool:
    return inspect(sesion.connection()).has_table(_TABLA.name)


def _anotar_inicio(sesion: Session, escritor: _Escritor) -> None:
    """La primera anotación de una base que ya tenía datos: cuántas filas había de cada tabla cuando se empezó a registrar."""
    cuentas = {}
    for nombre in sorted(AUDITADAS):
        tabla = Base.metadata.tables[nombre]
        cuentas[nombre] = escritor.conexion.execute(select(func.count()).select_from(tabla)).scalar_one()
    escritor.anotar("sistema", "-", INICIO, {"filas": cuentas})


def _escritor(sesion: Session) -> _Escritor | None:
    if not _tablas_presentes(sesion):
        return None
    escritor = _Escritor(sesion)
    if escritor.vacio:
        _anotar_inicio(sesion, escritor)
    return escritor


@event.listens_for(Session, "before_flush")
def _antes_de_grabar(sesion: Session, contexto, instancias) -> None:
    """Deja anotada la situación de partida antes del primer cambio, para que lo anterior quede como punto de partida y no como un cambio sin anotar."""
    if not (sesion.new or sesion.dirty or sesion.deleted):
        return
    if not any(_tabla_de(o) in AUDITADAS for grupo in (sesion.new, sesion.dirty, sesion.deleted) for o in grupo):
        return
    _escritor(sesion)


@event.listens_for(Session, "after_flush")
def _despues_de_grabar(sesion: Session, contexto) -> None:
    nuevas = [o for o in sesion.new if _tabla_de(o) in AUDITADAS]
    cambiadas = [(o, c) for o in sesion.dirty if _tabla_de(o) in AUDITADAS and (c := _cambios(o))]
    borradas = [o for o in sesion.deleted if _tabla_de(o) in AUDITADAS]
    if not (nuevas or cambiadas or borradas):
        return
    escritor = _escritor(sesion)
    if escritor is None:
        return
    por_tabla: dict[str, list] = {}
    for objeto in nuevas:
        por_tabla.setdefault(_tabla_de(objeto), []).append(objeto)
    for tabla, objetos in por_tabla.items():
        if len(objetos) > LOTE_A_PARTIR_DE:
            filas = [_columnas(o) for o in objetos]
            ids = sorted(_clave(o) for o in objetos)
            escritor.anotar(tabla, f"{ids[0]}..{ids[-1]}", ALTA_LOTE, {"filas": len(objetos), "sha256": hashlib.sha256(_json(filas).encode("utf-8")).hexdigest()})
        else:
            for objeto in objetos:
                escritor.anotar(tabla, _clave(objeto), ALTA, _columnas(objeto))
    for objeto, cambios in cambiadas:
        escritor.anotar(_tabla_de(objeto), _clave(objeto), CAMBIO, cambios)
    for objeto in borradas:
        escritor.anotar(_tabla_de(objeto), _clave(objeto), BAJA, _columnas(objeto))


@event.listens_for(Session, "do_orm_execute")
def _borrados_y_cambios_masivos(estado) -> None:
    """Los `delete()` y `update()` masivos no pasan por el ORM fila a fila: se anotan las filas afectadas antes de ejecutarlos."""
    sesion = estado.session
    if not (estado.is_delete or estado.is_update) or estado.bind_mapper is None:
        return
    mapper = estado.bind_mapper
    if mapper.local_table.name not in AUDITADAS or not _tablas_presentes(sesion):
        return
    consulta = select(mapper.class_)
    if estado.statement.whereclause is not None:
        consulta = consulta.where(estado.statement.whereclause)
    afectadas = list(sesion.execute(consulta, execution_options={"populate_existing": False}).scalars())
    if not afectadas:
        return
    escritor = _escritor(sesion)
    tabla = mapper.local_table.name
    nuevos = {}
    if estado.is_update:
        nuevos = {getattr(k, "key", str(k)): _valor(getattr(v, "value", v)) for k, v in (estado.statement._values or {}).items()}
    for objeto in afectadas:
        if estado.is_delete:
            escritor.anotar(tabla, _clave(objeto), BAJA, _columnas(objeto))
        else:
            antes = _columnas(objeto)
            escritor.anotar(tabla, _clave(objeto), CAMBIO, {k: [antes.get(k), v] for k, v in nuevos.items() if antes.get(k) != v})


def verificar(sesion: Session) -> list[str]:
    """Recorre la cadena y devuelve lo que no cuadra (vacío = íntegra): huellas que no coinciden, filas que faltan o enlaces rotos. Sólo cuenta el primer fallo, porque lo posterior ya no es de fiar."""
    anterior_id, anterior_huella = 0, HUELLA_INICIAL
    for fila in sesion.execute(select(_TABLA).order_by(_TABLA.c.id)).mappings():
        datos = dict(fila)
        if datos["id"] != anterior_id + 1:
            return [f"Faltan anotaciones entre la {anterior_id} y la {datos['id']}"]
        if datos["huella_anterior"] != anterior_huella:
            return [f"La anotación {datos['id']} no continúa la anterior"]
        if calcular_huella(datos) != datos["huella"]:
            return [f"La anotación {datos['id']} ({datos['tabla']} {datos['fila']}, {datos['operacion']}) ha sido modificada"]
        anterior_id, anterior_huella = datos["id"], datos["huella"]
    return []


def ultima_huella(sesion: Session) -> tuple[int, str]:
    """(número, huella) de la última anotación: lo que conviene guardar fuera de la base. (0, '') si no hay ninguna."""
    ultima = sesion.execute(select(_TABLA.c.id, _TABLA.c.huella).order_by(_TABLA.c.id.desc()).limit(1)).first()
    return (ultima[0], ultima[1]) if ultima else (0, HUELLA_INICIAL)
