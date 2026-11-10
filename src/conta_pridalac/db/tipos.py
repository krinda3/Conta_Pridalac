"""Tipos de columna propios."""
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator

CENTIMO = Decimal("0.01")


def dinero(valor) -> Decimal:
    """Convierte a Decimal con 2 decimales. Los `float` se pasan por `str` para no arrastrar ruido binario."""
    if valor is None or valor == "":
        return Decimal("0.00")
    if isinstance(valor, float):
        valor = repr(valor)
    return Decimal(valor).quantize(CENTIMO, rounding=ROUND_HALF_EVEN)


class Dinero(TypeDecorator):
    """Importe monetario: se guarda como entero en céntimos y se lee como `Decimal`.

    Evita los `float` del original (Gestión MGD compara con tolerancia de 3 decimales) y el
    `Numeric` de SQLite, que guarda coma flotante.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int(dinero(value) * 100)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(CENTIMO)
