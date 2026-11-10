"""Registra como presentada una declaración (303 o 111) de la que sólo se tiene el PDF «Información de la presentación» de la sede.

Sirve para los trimestres que el programa anterior no tiene en su tabla (presentados fuera de él, o completados después) y que, sin constar aquí, hacen que el programa crea que el periodo sigue sin presentar.
Del PDF se leen el justificante, la fecha y el NIF de quien presentó, y se comprueba que es del modelo y del ejercicio. **No se leen los importes**: la declaración queda sin casillas (el PDF las trae como
texto de formulario sin etiquetas fiables). Si el PDF no se puede leer (hay copias impresas con los valores perdidos), se puede indicar el justificante y la fecha a mano o dejarlos vacíos.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos, nombre_seguro, sha256_de
from conta_pridalac.servicios.justificante_aeat import leer_justificante

MODELOS = ("303", "111")


def importar_declaracion_desde_pdf(
    sesion: Session, almacen: AlmacenAdjuntos, empresa: Empresa, modelo: str, anio: int, periodo: int, pdf: str | Path, *, tipo: int = 1,
    justificante: str | None = None, fecha: date | None = None,
) -> DeclaracionPresentada:
    """Añade la declaración presentada (no hace commit). Falla si ya consta ese periodo y tipo, o si el PDF es de otro modelo, ejercicio o empresa."""
    if modelo not in MODELOS:
        raise ErrorContable(f"Modelo {modelo} no admitido (sólo {', '.join(MODELOS)})")
    pdf = Path(pdf)
    existente = sesion.scalar(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == modelo, DeclaracionPresentada.anio == anio,
        DeclaracionPresentada.periodo == periodo, DeclaracionPresentada.tipo == tipo))
    if existente is not None:
        raise ErrorContable(f"El {modelo} de {periodo}T {anio} (tipo {tipo}) ya consta como presentado: no se añade otra vez")
    leido = leer_justificante(pdf.read_bytes())
    if leido is not None:
        if leido.modelo != modelo:
            raise ErrorContable(f"El PDF es del modelo {leido.modelo}, no del {modelo}")
        if not leido.registro.startswith(f"{anio}{modelo}"):
            raise ErrorContable(f"El PDF es de otro ejercicio (registro {leido.registro}): se esperaba el de {anio}")
        if empresa.nif and leido.nif_presentador and leido.nif_presentador != empresa.nif.strip():
            raise ErrorContable(f"El PDF lo presentó el NIF {leido.nif_presentador}, no el de la empresa ({empresa.nif})")
        justificante, fecha = leido.justificante, leido.momento.date()
    elif not justificante and fecha is None:
        pass  # sin lectura ni datos: queda constancia de que se presentó, con el PDF, y nada más
    d = DeclaracionPresentada(empresa_id=empresa.id, modelo=modelo, anio=anio, periodo=periodo, tipo=tipo, fecha_emision=fecha, fecha_envio=fecha, justificante=justificante or None, casillas="{}")
    sesion.add(d)
    sesion.flush()
    destino = f"{empresa.codigo:03d}/{anio}/D/{d.id:06d}_{nombre_seguro(pdf.name)}"
    final = almacen.raiz / destino
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, final)
    d.pdf_nombre, d.pdf_ruta, d.pdf_sha256 = pdf.name, destino, sha256_de(final)
    sesion.flush()
    return d
