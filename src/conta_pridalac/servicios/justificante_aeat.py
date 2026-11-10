"""Lectura del PDF «Información de la presentación de la declaración» que devuelve la sede de la AEAT al presentar un modelo.

La primera página lleva todo lo que hace falta para registrar la presentación (fecha y hora, nº de registro, CSV, nº de justificante, presentador, resultado y, si se ingresó
con NRC, el NRC y su importe), así que se leen del propio PDF en lugar de teclearlos. Si el PDF no tiene esa forma devuelve `None`.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pypdf import PdfReader

# texto con el que la sede describe el resultado → tipo de declaración del fichero
RESULTADOS = {
    "NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO": "N",
    "DOMICILIACIÓN DEL IMPORTE A INGRESAR": "U",
    "SOLICITUD DE DEVOLUCIÓN": "D",
    "A COMPENSAR": "C",
    "INGRESAR": "I",
}


@dataclass(frozen=True)
class JustificanteAeat:
    modelo: str
    registro: str  # nº de registro asignado (expediente); empieza por el ejercicio y el modelo
    csv: str
    justificante: str
    momento: datetime
    nif_presentador: str
    resultado: str | None  # tipo de declaración (I, U, C, N, D) deducido del texto de la sede
    nrc: str | None = None
    importe: Decimal | None = None


def _importe(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def leer_justificante(pdf: bytes) -> JustificanteAeat | None:
    """Datos del justificante de presentación, o `None` si el PDF no es uno (o no se puede leer)."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        texto = PdfReader(io.BytesIO(pdf)).pages[0].extract_text() or ""
    except Exception:  # un PDF dañado o cifrado no es motivo de caída: simplemente no se reconoce
        return None
    buscar = lambda patron: (m.group(1) if (m := re.search(patron, texto)) else None)  # noqa: E731
    fecha = re.search(r"Presentación realizada el:\s*(\d{2})-(\d{2})-(\d{4}) a las (\d{2}):(\d{2}):(\d{2})", texto)
    modelo, registro = buscar(r"Modelo\s+(\d{3})"), buscar(r"nº registro asignado\):\s*(\S+)")
    csv, justificante = buscar(r"Código Seguro de Verificación:\s*([A-Z0-9]{16})"), buscar(r"Número de justificante:\s*(\d{13})")
    if not (fecha and modelo and registro and csv and justificante):
        return _formato_antiguo(texto)
    d, mes, a, h, mi, s = (int(x) for x in fecha.groups())
    tras = re.split(r"En calidad de:[^\n]*\n", texto, maxsplit=1)[-1]
    resultado = next((tipo for frase, tipo in RESULTADOS.items() if frase in tras), None)
    nrc = re.search(r"NRC:\s*([A-Z0-9]{22})\s+IMPORTE:\s*([\d.]+,\d{2})", texto)
    return JustificanteAeat(
        modelo=modelo, registro=registro, csv=csv, justificante=justificante, momento=datetime(a, mes, d, h, mi, s), nif_presentador=buscar(r"NIF Presentador:\s*(\S+)") or "",
        resultado=resultado, nrc=nrc.group(1) if nrc else None, importe=_importe(nrc.group(2)) if nrc else None,
    )


def _formato_antiguo(texto: str) -> JustificanteAeat | None:
    """El PDF de 2022 y anteriores: las etiquetas van todas juntas y los valores después, en el mismo orden, sin «etiqueta: valor». Se reconocen por su forma."""
    fecha = re.search(r"(\d{2})-(\d{2})-(\d{4}) a las (\d{2}):(\d{2}):(\d{2})", texto)
    registro = re.search(r"^(20\d{2})(303|111|115|190|180|390|347|200|202)([0-9A-Z]{7,15})$", texto, re.MULTILINE)
    justificante = re.search(r"^(\d{13})$", texto, re.MULTILINE)
    csv = next((m.group(1) for m in re.finditer(r"^([A-Z0-9]{16})$", texto, re.MULTILINE) if not (registro and m.group(1) == registro.group(0))), None)
    if not (fecha and registro and justificante and csv and "Presentación" in texto):
        return None
    d, mes, a, h, mi, s = (int(x) for x in fecha.groups())
    resultado = next((tipo for frase, tipo in RESULTADOS.items() if frase in texto), None)
    nif = re.search(r"^([A-Z]\d{8}|\d{8}[A-Z])$", texto, re.MULTILINE)
    return JustificanteAeat(
        modelo=registro.group(2), registro=registro.group(0), csv=csv, justificante=justificante.group(1), momento=datetime(a, mes, d, h, mi, s), nif_presentador=nif.group(1) if nif else "", resultado=resultado,
    )
