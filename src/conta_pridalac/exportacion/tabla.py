"""Tabla neutra que alimenta tanto la exportación a PDF como a Excel (y, más adelante, el componente de listado web)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

TEXTO, DINERO, FECHA, ENTERO, PORCENTAJE = "texto", "dinero", "fecha", "entero", "porcentaje"


@dataclass
class Columna:
    titulo: str
    tipo: str = TEXTO
    ancho: float = 1.0  # peso relativo en el PDF


@dataclass
class Tabla:
    titulo: str
    columnas: list[Columna]
    filas: list[list]
    subtitulo: str = ""
    totales: list | None = None  # una celda por columna (None = vacía)
    notas: list[str] = field(default_factory=list)

    def __post_init__(self):
        n = len(self.columnas)
        for i, fila in enumerate(self.filas):
            if len(fila) != n:
                raise ValueError(f"La fila {i} tiene {len(fila)} celdas y la tabla {n} columnas")
        if self.totales is not None and len(self.totales) != n:
            raise ValueError("Los totales deben tener una celda por columna")


def formatear(valor, tipo: str) -> str:
    """Texto de una celda tal como se ve en el PDF: importes `1.234,56`, fechas `dd/mm/aaaa`."""
    if valor is None or valor == "":
        return ""
    if tipo in (DINERO, PORCENTAJE):
        return f"{Decimal(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if tipo == FECHA and isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if tipo == ENTERO:
        return str(int(valor))
    return str(valor)
