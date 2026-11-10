"""Conversión de cuentas de Gestión MGD (7 dígitos) a 8 dígitos (como el programa anterior), sólo para las empresas que pasaron al programa anterior.
Las demás conservan los dígitos de su plan de MGD (`ajustar_cuenta` con los mismos dígitos no cambia nada).

**No hay una regla única.** el programa anterior asignó los códigos de forma distinta en cada empresa (comprobado con los nombres de cuenta
de los asientos de 2022 y el Mayor de 2026): en Empresa A todas las cuentas se explican insertando un `0` tras el
**cuarto** dígito (`2811000` → `28110000`); en Empresa B, tras el **tercero** (`4108123` → `41008123`). Donde el cuarto dígito es
`0` las dos reglas coinciden, por eso casi todas las cuentas de proveedores, clientes y bancos salen igual.
Para un traspaso exacto de años posteriores hará falta una tabla de equivalencias por empresa (Hito 2).
"""

# Dígito tras el cual se inserta el `0`, por empresa de MGD
CERO_TRAS_POR_EMPRESA = {11: 4, 12: 3}  # 11 Empresa A · 12 Empresa B


def ajustar_cuenta(codigo_mgd: str | None, digitos: int, tras: int = 3) -> str:
    """Deja la cuenta de MGD con `digitos` dígitos: si ya los tiene no cambia; si tiene uno menos, inserta un `0` tras el dígito `tras`.

    Cadena vacía se devuelve sin cambios; cualquier otra longitud es un error.
    """
    c = (codigo_mgd or "").strip()
    if c == "" or len(c) == digitos:
        return c
    if len(c) != digitos - 1 or not c.isdigit():
        raise ValueError(f"Cuenta MGD no convertible: {codigo_mgd!r}")
    return c[:tras] + "0" + c[tras:]


def cuenta_8(codigo_mgd: str | None, tras: int = 3) -> str:
    """`1210002` → `12100002`: se inserta un `0` tras el dígito `tras` (3 por defecto; 4 en Empresa A).

    Cadena vacía o ya de 8 dígitos se devuelve sin cambios; cualquier otra longitud es un error.
    """
    return ajustar_cuenta(codigo_mgd, 8, tras)
