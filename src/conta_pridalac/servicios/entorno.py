"""Base real o copia de ensayo.

Una copia de la base con la que se ensaya (se quitan facturas para volver a contabilizarlas, se prueban flujos) no puede pasar por contabilidad oficial: se marca como **ensayo** y desde entonces no puede generar los
ficheros para la sede ni registrar presentaciones, y las pantallas lo avisan. La marca es un parámetro de la propia base, así que viaja con las copias y queda en el registro de cambios. No hay forma de quitarla:
si hace falta la base real, se restaura una copia de seguridad.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Parametro
from conta_pridalac.domain.errores import ErrorContable

CLAVE = "ENSAYO"


def es_ensayo(sesion: Session, empresa_id: int) -> bool:
    return sesion.scalar(select(Parametro.id).where(Parametro.empresa_id == empresa_id, Parametro.clave == CLAVE)) is not None


def marcar_ensayo(sesion: Session, empresa_id: int, motivo: str = "") -> bool:
    """Marca la base como copia de ensayo. Devuelve `False` si ya lo estaba. No hace commit."""
    if es_ensayo(sesion, empresa_id):
        return False
    sesion.add(Parametro(empresa_id=empresa_id, clave=CLAVE, valor=motivo or "copia de ensayo"))
    sesion.flush()
    return True


def exigir_base_real(sesion: Session, empresa_id: int, accion: str) -> None:
    """Corta lo que sólo tiene sentido en la contabilidad oficial (`accion`: «generar el fichero para la sede»…)."""
    if es_ensayo(sesion, empresa_id):
        raise ErrorContable(f"Esta base es una copia de ensayo: no se puede {accion}. Hágalo en la base real.")


def exigir_ensayo(sesion: Session, empresa_id: int, accion: str) -> None:
    """Lo contrario: lo que borra datos contables para ensayar sólo se permite en una copia marcada como ensayo."""
    if not es_ensayo(sesion, empresa_id):
        raise ErrorContable(f"Esta base no está marcada como copia de ensayo: no se puede {accion}. Haga una copia, márquela con tools/marcar_ensayo.py y trabaje en ella.")
