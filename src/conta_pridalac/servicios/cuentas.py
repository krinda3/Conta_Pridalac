"""Alta, cambio y baja de subcuentas (plan de cuentas de 8 dígitos) y de terceros (clientes y proveedores)."""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Base, Cuenta, Empresa, Parametro, Tercero
from conta_pridalac.domain.errores import ErrorContable


def _referencias(sesion: Session, tabla_destino: str, id_: int) -> list[tuple[str, int]]:
    """Cuántas filas de qué tablas apuntan a la fila `id_` de `tabla_destino` (por clave foránea, sin listar a mano)."""
    usos = []
    for tabla in Base.metadata.sorted_tables:
        for fk in tabla.foreign_keys:
            if fk.column.table.name == tabla_destino and fk.column.name == "id":
                n = sesion.scalar(select(func.count()).select_from(tabla).where(fk.parent == id_))
                if n:
                    usos.append((tabla.name, n))
    return usos


def usos_de_cuenta(sesion: Session, cuenta: Cuenta) -> list[tuple[str, int]]:
    """Tablas que usan la cuenta (apuntes, facturas, bancos, bienes…), incluidos los parámetros que la nombran."""
    usos = _referencias(sesion, "cuenta", cuenta.id)
    n = sesion.scalar(select(func.count()).select_from(Parametro).where(Parametro.empresa_id == cuenta.empresa_id, Parametro.valor == cuenta.codigo))
    if n:
        usos.append(("parametro", n))
    return usos


def _describir(usos: list[tuple[str, int]]) -> str:
    return ", ".join(f"{tabla} ({n})" for tabla, n in usos)


DIGITOS_MIN, DIGITOS_MAX = 4, 12  # dígitos que puede tener una subcuenta; se elige al crear la empresa y no se cambia


def validar_digitos(digitos) -> int:
    try:
        n = int(digitos)
    except (TypeError, ValueError):
        raise ErrorContable("Los dígitos de las subcuentas son un número") from None
    if not DIGITOS_MIN <= n <= DIGITOS_MAX:
        raise ErrorContable(f"Las subcuentas tienen entre {DIGITOS_MIN} y {DIGITOS_MAX} dígitos")
    return n


def digitos_de(sesion: Session, empresa_id: int) -> int:
    """Dígitos de las subcuentas de la empresa."""
    empresa = sesion.get(Empresa, empresa_id)
    return empresa.digitos_cuenta if empresa is not None else 8


def cuenta_estandar(codigo: str, digitos: int) -> str:
    """El código del PGC con los dígitos de la empresa: los tres primeros dígitos y ceros (`47200000` → `4720000` con 7 dígitos)."""
    return codigo[:3].ljust(digitos, "0")


def validar_codigo(codigo: str, digitos: int = 8) -> str:
    codigo = (codigo or "").strip()
    if len(codigo) != digitos or not codigo.isdigit():
        raise ErrorContable(f"El código de una subcuenta tiene {digitos} dígitos (por ejemplo {'572'.ljust(digitos - 1, '0')}1)")
    return codigo


def crear_cuenta(sesion: Session, empresa_id: int, codigo: str, nombre: str) -> Cuenta:
    codigo, nombre = validar_codigo(codigo, digitos_de(sesion, empresa_id)), (nombre or "").strip()
    if not nombre:
        raise ErrorContable("Falta el nombre de la cuenta")
    if sesion.scalar(select(Cuenta.id).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo)):
        raise ErrorContable(f"Ya existe la cuenta {codigo}")
    cuenta = Cuenta(empresa_id=empresa_id, codigo=codigo, nombre=nombre[:128])
    sesion.add(cuenta)
    sesion.flush()
    return cuenta


def modificar_cuenta(sesion: Session, cuenta: Cuenta, *, codigo: str | None = None, nombre: str | None = None) -> Cuenta:
    """El nombre se cambia siempre; el código sólo si nada usa la cuenta."""
    if codigo is not None and validar_codigo(codigo, digitos_de(sesion, cuenta.empresa_id)) != cuenta.codigo:
        usos = usos_de_cuenta(sesion, cuenta)
        if usos:
            raise ErrorContable(f"No se puede cambiar el código de {cuenta.codigo}: está en uso en {_describir(usos)}")
        if sesion.scalar(select(Cuenta.id).where(Cuenta.empresa_id == cuenta.empresa_id, Cuenta.codigo == codigo.strip())):
            raise ErrorContable(f"Ya existe la cuenta {codigo.strip()}")
        cuenta.codigo = codigo.strip()
    if nombre is not None:
        if not nombre.strip():
            raise ErrorContable("Falta el nombre de la cuenta")
        cuenta.nombre = nombre.strip()[:128]
    sesion.flush()
    return cuenta


def borrar_cuenta(sesion: Session, cuenta: Cuenta) -> None:
    usos = usos_de_cuenta(sesion, cuenta)
    if usos:
        raise ErrorContable(f"No se puede borrar la cuenta {cuenta.codigo} {cuenta.nombre}: está en uso en {_describir(usos)}")
    sesion.delete(cuenta)
    sesion.flush()


# ------------------------------------------------------------------------------------------------ terceros


def _cuenta_por_codigo(sesion: Session, empresa_id: int, codigo: str | None, para: str) -> int | None:
    if not (codigo or "").strip():
        return None
    c = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo.strip()))
    if c is None:
        raise ErrorContable(f"No existe la cuenta {codigo.strip()} ({para})")
    return c.id


def _datos_de_tercero(sesion: Session, empresa_id: int, clase: str, nombre: str, comercial: str | None, nif: str | None, cuenta: str | None, cuenta_irpf: str | None) -> dict:
    if clase not in ("C", "P"):
        raise ErrorContable("La clase de un tercero es C (cliente) o P (proveedor)")
    if not (nombre or "").strip():
        raise ErrorContable("Falta el nombre del tercero")
    return dict(
        clase=clase, nombre=nombre.strip()[:128], comercial=(comercial or "").strip()[:64] or None, nif=(nif or "").strip().upper()[:20] or None,
        cuenta_id=_cuenta_por_codigo(sesion, empresa_id, cuenta, "cuenta del tercero"),
        cuenta_irpf_id=_cuenta_por_codigo(sesion, empresa_id, cuenta_irpf, "cuenta de IRPF"),
    )


# ---- ficha ampliada del tercero -------------------------------------------------------------------------------------

CAMPOS_DE_TEXTO = {  # campo → longitud máxima
    "tipo_identificador": 32, "domicilio": 128, "codigo_postal": 10, "poblacion": 64, "provincia": 32, "pais": 64, "telefonos": 64, "email": 128, "web": 128,
    "tipo_operacion": 64, "tipo_exencion_iva": 64, "bic": 11, "provincia_190": 2, "clave_190": 1, "subclave_190": 2,
    "inmueble_situacion": 1, "inmueble_catastro": 20, "inmueble_tipo_via": 5, "inmueble_via": 50, "inmueble_tipo_numeracion": 3, "inmueble_numero": 5, "inmueble_calificador": 3,
    "inmueble_bloque": 3, "inmueble_portal": 3, "inmueble_escalera": 3, "inmueble_planta": 3, "inmueble_puerta": 3, "inmueble_complemento": 40, "inmueble_localidad": 30,
    "inmueble_municipio": 30, "inmueble_codigo_municipio": 5, "inmueble_provincia": 2, "inmueble_codigo_postal": 5,
}
CAMPOS_DEL_INMUEBLE = tuple(c for c in CAMPOS_DE_TEXTO if c.startswith("inmueble_"))
CAMPOS_BOOLEANOS = ("recargo_equivalencia", "no_incluir_347", "generico", "criterio_caja", "reagp", "pago_directo")
CAMPOS_DE_CUENTA = {  # campo del formulario → (columna, cómo se llama en los mensajes)
    "cuenta_gasto": ("cuenta_gasto_id", "subcuenta de gasto o de ingreso"), "cuenta_suplidos": ("cuenta_suplidos_id", "subcuenta de suplidos"),
    "cuenta_pago": ("cuenta_pago_id", "subcuenta de pago o de cobro"),
}


def iban_valido(iban: str) -> bool:
    """Un IBAN con dígitos de control correctos (módulo 97). Lo que no empieza por dos letras y dos cifras (un CCC antiguo) no se comprueba."""
    iban = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    reordenado = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in reordenado)) % 97 == 1


def _ficha_de_tercero(sesion: Session, empresa_id: int, ficha: dict) -> dict:
    """Valida y convierte los datos de la ficha ampliada a columnas de `Tercero`. Los campos que no vienen no se tocan."""
    desconocidos = set(ficha) - set(CAMPOS_DE_TEXTO) - set(CAMPOS_BOOLEANOS) - set(CAMPOS_DE_CUENTA) - {
        "observaciones", "divisa", "tipos_iva_defecto", "retencion_pct", "pct_iva_deducible", "forma_pago_id", "iban"}
    if desconocidos:
        raise ErrorContable(f"Campos de tercero desconocidos: {', '.join(sorted(desconocidos))}")
    datos: dict = {}
    for campo, largo in CAMPOS_DE_TEXTO.items():
        if campo in ficha:
            datos[campo] = (ficha[campo] or "").strip()[:largo] or None
    for campo in CAMPOS_BOOLEANOS:
        if campo in ficha:
            datos[campo] = bool(ficha[campo])
    for campo, (columna, nombre) in CAMPOS_DE_CUENTA.items():
        if campo in ficha:
            datos[columna] = _cuenta_por_codigo(sesion, empresa_id, ficha[campo], nombre)
    if "observaciones" in ficha:
        datos["observaciones"] = (ficha["observaciones"] or "").strip() or None
    if datos.get("provincia_190") and not re.fullmatch(r"\d{2}", datos["provincia_190"]):
        raise ErrorContable("La provincia del modelo 190 son dos cifras (28 Madrid, 13 Ciudad Real…)")
    if datos.get("clave_190"):
        datos["clave_190"] = datos["clave_190"].upper()
        if not re.fullmatch(r"[A-Z]", datos["clave_190"]):
            raise ErrorContable("La clave de percepción del modelo 190 es una letra (G, H, I…)")
    if datos.get("subclave_190") and not re.fullmatch(r"\d{2}", datos["subclave_190"]):
        raise ErrorContable("La subclave de percepción del modelo 190 son dos cifras (03…)")
    for campo in CAMPOS_DEL_INMUEBLE:  # el diseño del 180 pide mayúsculas
        if datos.get(campo):
            datos[campo] = datos[campo].upper()
    if datos.get("inmueble_situacion") and datos["inmueble_situacion"] not in ("1", "2", "3", "4"):
        raise ErrorContable("La situación del inmueble del modelo 180 es 1, 2, 3 o 4")
    for campo, cifras, nombre in (("inmueble_provincia", 2, "La provincia del inmueble"), ("inmueble_codigo_municipio", 5, "El código de municipio del inmueble"), ("inmueble_codigo_postal", 5, "El código postal del inmueble")):
        if datos.get(campo) and not re.fullmatch(r"\d{%d}" % cifras, datos[campo]):
            raise ErrorContable(f"{nombre} son {cifras} cifras")
    if datos.get("inmueble_catastro") and not re.fullmatch(r"[A-Z0-9]{14,20}", datos["inmueble_catastro"]):
        raise ErrorContable("La referencia catastral son 14 a 20 letras y cifras (sin espacios)")
    if datos.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", datos["email"]):
        raise ErrorContable(f"El correo «{datos['email']}» no parece una dirección válida")
    if "divisa" in ficha:
        divisa = (ficha["divisa"] or "").strip().upper()
        if divisa and not re.fullmatch(r"[A-Z]{3}", divisa):
            raise ErrorContable("La divisa es un código de tres letras (EUR, USD…)")
        datos["divisa"] = divisa or None
    if "iban" in ficha:
        iban = (ficha["iban"] or "").replace(" ", "").upper()
        if iban and re.match(r"[A-Z]{2}\d{2}", iban) and not iban_valido(iban):
            raise ErrorContable(f"El IBAN {iban} no tiene los dígitos de control correctos")
        datos["iban"] = iban[:34] or None
    if "tipos_iva_defecto" in ficha:
        valor = (ficha["tipos_iva_defecto"] or "").replace(" ", "")
        if valor and not re.fullmatch(r"\d{1,3}(,\d{1,3}){0,2}", valor):
            raise ErrorContable("Los tipos de IVA por defecto son hasta tres números separados por comas (por ejemplo 1,2)")
        datos["tipos_iva_defecto"] = valor or None
    for campo in ("retencion_pct", "pct_iva_deducible"):
        if campo in ficha:
            valor = ficha[campo]
            if valor is not None and not (Decimal("0") <= Decimal(valor) <= Decimal("100")):
                raise ErrorContable(f"«{campo.replace('_', ' ')}» va de 0 a 100")
            datos[campo] = Decimal(valor) if valor is not None else (Decimal("100.00") if campo == "pct_iva_deducible" else None)
    if "forma_pago_id" in ficha:
        datos["forma_pago_id"] = ficha["forma_pago_id"] or None
    return datos


# Grupo de la cuenta que se asigna a un tercero nuevo si no se indica ninguna: proveedores 400, clientes 430
GRUPOS_DE_TERCERO = {"400": "Proveedores", "410": "Acreedores por prestaciones de servicios", "430": "Clientes", "440": "Deudores varios"}
GRUPO_POR_DEFECTO = {"P": "400", "C": "430"}


def siguiente_cuenta_libre(sesion: Session, empresa_id: int, grupo: str) -> str:
    """La siguiente subcuenta libre del grupo (3 dígitos): la mayor que exista más uno, o `<grupo>00001` (con los dígitos de la empresa) si no hay ninguna."""
    if len(grupo) != 3 or not grupo.isdigit():
        raise ErrorContable("El grupo de la cuenta tiene 3 dígitos (por ejemplo 400)")
    digitos = digitos_de(sesion, empresa_id)
    mayor = sesion.scalar(select(func.max(Cuenta.codigo)).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo.like(f"{grupo}%"), func.length(Cuenta.codigo) == digitos))
    siguiente = int(mayor) + 1 if mayor else int(grupo + "1".rjust(digitos - 3, "0"))
    if not str(siguiente).startswith(grupo) or len(str(siguiente)) != digitos:
        raise ErrorContable(f"El grupo {grupo} no tiene más cuentas libres")
    return str(siguiente)


def crear_tercero(
    sesion: Session, empresa_id: int, clase: str, nombre: str, *, comercial=None, nif=None, cuenta=None, cuenta_irpf=None, grupo_cuenta: str | None = None, **ficha
) -> Tercero:
    """Crea el tercero. Sin `cuenta`, crea y le asigna la siguiente subcuenta libre de `grupo_cuenta` (400 proveedores o 430 clientes por defecto)."""
    if not (cuenta or "").strip() and clase in GRUPO_POR_DEFECTO and (nombre or "").strip():
        cuenta = crear_cuenta(sesion, empresa_id, siguiente_cuenta_libre(sesion, empresa_id, grupo_cuenta or GRUPO_POR_DEFECTO[clase]), nombre.strip().upper()).codigo
    datos = _datos_de_tercero(sesion, empresa_id, clase, nombre, comercial, nif, cuenta, cuenta_irpf)
    datos.update(_ficha_de_tercero(sesion, empresa_id, ficha))
    t = Tercero(empresa_id=empresa_id, **datos)
    sesion.add(t)
    sesion.flush()
    return t


def modificar_tercero(sesion: Session, tercero: Tercero, clase: str, nombre: str, *, comercial=None, nif=None, cuenta=None, cuenta_irpf=None, **ficha) -> Tercero:
    datos = _datos_de_tercero(sesion, tercero.empresa_id, clase, nombre, comercial, nif, cuenta, cuenta_irpf)
    datos.update(_ficha_de_tercero(sesion, tercero.empresa_id, ficha))
    if datos["clase"] != tercero.clase and _referencias(sesion, "tercero", tercero.id):
        raise ErrorContable("No se puede cambiar la clase de un tercero que ya tiene documentos")
    for campo, valor in datos.items():
        setattr(tercero, campo, valor)
    sesion.flush()
    return tercero


def borrar_tercero(sesion: Session, tercero: Tercero) -> None:
    usos = _referencias(sesion, "tercero", tercero.id)
    if usos:
        raise ErrorContable(f"No se puede borrar a {tercero.nombre}: tiene documentos ({_describir(usos)})")
    sesion.delete(tercero)
    sesion.flush()
