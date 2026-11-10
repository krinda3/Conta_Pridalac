"""Importa los modelos 190 ya presentados a partir de sus ficheros (`C000X_190_<año>.190`), con la fecha del PDF de la sede cuando está.

El 190 no está en las tablas del programa anterior que se cargan; en cambio cada fichero presentado lleva todo lo que hace falta: ejercicio, NIF del declarante, número de justificante
(posiciones 108-120, que la sede conserva) y los perceptores con sus importes. Se guarda como `DeclaracionPresentada` (modelo 190, periodo 0), igual que el 303 y el 111.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero190 import CODIFICACION, leer
from conta_pridalac.servicios.justificante_aeat import leer_justificante


def cargar_declaraciones_190(sesion: Session, empresa: Empresa, carpeta_ficheros: str | Path, carpeta_pdf: str | Path | None = None) -> tuple[int, list[str]]:
    """Añade los 190 presentados de esa empresa (por su NIF) que aún no están. Devuelve (añadidos, avisos). No hace commit."""
    existentes = {d.anio for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == "190"))}
    nuevas, avisos = 0, []
    for ruta in sorted(Path(carpeta_ficheros).glob("C000?_190_*.190")):
        try:
            d = leer(ruta.read_bytes().decode(CODIFICACION))
        except ErrorContable as e:
            avisos.append(f"{ruta.name}: {e}")
            continue
        if d.nif != (empresa.nif or "").strip() or d.ejercicio in existentes:
            continue
        fecha = None
        if carpeta_pdf is not None:
            pdf = next(iter(sorted(Path(carpeta_pdf).rglob(f"C{empresa.codigo:04d}_190_{d.ejercicio}_00.PDF"))), None)
            leido = leer_justificante(pdf.read_bytes()) if pdf is not None else None
            if leido is not None:
                if leido.justificante != d.identificativo:
                    avisos.append(f"{ruta.name}: el PDF tiene el justificante {leido.justificante} y el fichero el {d.identificativo}")
                fecha = leido.momento.date()
        sesion.add(DeclaracionPresentada(
            empresa_id=empresa.id, modelo="190", anio=d.ejercicio, periodo=0, tipo=1, fecha_emision=fecha, justificante=d.identificativo, resultado=sum((p.retencion for p in d.percepciones), 0),
            resultado_liquidacion=sum((p.retencion for p in d.percepciones), 0),
            casillas=json.dumps({
                "perceptores": len(d.percepciones), "percepciones": float(sum(p.percepcion for p in d.percepciones)), "retenciones": float(sum(p.retencion for p in d.percepciones)),
                "lista": [{"nif": p.nif, "nombre": p.nombre, "provincia": p.provincia, "clave": p.clave, "subclave": p.subclave, "percepcion": float(p.percepcion), "retencion": float(p.retencion)} for p in d.percepciones],
            }),
        ))
        existentes.add(d.ejercicio)
        nuevas += 1
    sesion.flush()
    return nuevas, avisos
