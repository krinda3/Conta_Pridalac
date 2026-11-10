"""Grabar y borrar asientos (docs/pseudocodigo/01_asientos_diario.md §3, §4 y §5).

Reglas:
- Un asiento **cuadra** (Σ debe = Σ haber) o no se graba.
- Solo las subcuentas (con los dígitos de la empresa) existentes admiten apuntes.
- La fecha ha de estar en el ejercicio y éste abierto.
- Las líneas de la misma cuenta se agrupan y las de importe 0 desaparecen (MGD `ReduceApuntes`, `NO_REDUCE_APUNTES = 'N'`).
  Los asientos manuales (tipo 4) pueden pedir que **no** se agrupen.
- Grabar es **idempotente**: si el asiento ya existe, se reemplazan sus líneas conservando su `numero_diario` y los textos
  (concepto/documento) que tuviera cada cuenta (MGD `Graba`, que reutiliza los registros y los textos de `DiarioTxt`).
- El número del libro diario es correlativo por ejercicio, se asigna al crear el asiento y **no se recompacta** al borrar.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Apunte, Asiento, Cuenta, Ejercicio
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import AsientoDescuadrado, CuentaNoAdmiteApuntes
from conta_pridalac.domain.fechas import validar_en_ejercicio

CERO = Decimal("0.00")


@dataclass(frozen=True)
class LineaAsiento:
    """Una línea a grabar. `importe` con signo: positivo = debe, negativo = haber."""

    cuenta: str  # código de la subcuenta
    importe: Decimal
    concepto: str | None = None
    documento: str | None = None


def reducir(lineas: list[LineaAsiento]) -> list[LineaAsiento]:
    """Agrupa por cuenta (conservando el orden de aparición) y elimina las líneas de importe 0."""
    por_cuenta: dict[str, LineaAsiento] = {}
    for linea in lineas:
        importe = dinero(linea.importe)
        previa = por_cuenta.get(linea.cuenta)
        if previa is None:
            por_cuenta[linea.cuenta] = LineaAsiento(linea.cuenta, importe, linea.concepto, linea.documento)
        else:
            por_cuenta[linea.cuenta] = LineaAsiento(
                linea.cuenta, previa.importe + importe, previa.concepto or linea.concepto, previa.documento or linea.documento
            )
    return [linea for linea in por_cuenta.values() if linea.importe != 0]


def siguiente_numero_diario(sesion: Session, ejercicio: Ejercicio) -> int:
    maximo = sesion.scalar(select(func.max(Asiento.numero_diario)).where(Asiento.ejercicio_id == ejercicio.id))
    return (maximo or 0) + 1


def _cuentas_por_codigo(sesion: Session, ejercicio: Ejercicio, codigos: set[str]) -> dict[str, Cuenta]:
    encontradas = {
        c.codigo: c
        for c in sesion.scalars(
            select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo.in_(codigos))
        )
    }
    for codigo in sorted(codigos):
        if codigo not in encontradas:
            raise CuentaNoAdmiteApuntes(f"La cuenta {codigo} no existe en el plan de la empresa")
        if not encontradas[codigo].es_subcuenta:
            raise CuentaNoAdmiteApuntes(f"La cuenta {codigo} es de grupo: solo las subcuentas admiten apuntes")
    return encontradas


def buscar_asiento(sesion: Session, ejercicio: Ejercicio, tipo: int, numero: int, sub: int = 0) -> Asiento | None:
    return sesion.scalars(
        select(Asiento).where(
            Asiento.ejercicio_id == ejercicio.id, Asiento.tipo == tipo, Asiento.numero == numero, Asiento.sub == sub
        )
    ).one_or_none()


def grabar_asiento(
    sesion: Session,
    ejercicio: Ejercicio,
    *,
    tipo: int,
    numero: int,
    fecha,
    lineas: list[LineaAsiento],
    sub: int = 0,
    concepto: str = "",
    subtipo: str | None = None,
    agrupar: bool = True,
) -> Asiento | None:
    """Crea o reemplaza el asiento `(ejercicio, tipo, numero, sub)`. Devuelve `None` si queda sin líneas (se borra)."""
    validar_en_ejercicio(fecha, ejercicio)
    lineas = reducir(lineas) if agrupar else [l for l in lineas if dinero(l.importe) != 0]

    existente = buscar_asiento(sesion, ejercicio, tipo, numero, sub)
    if not lineas:
        if existente is not None:
            sesion.delete(existente)
            sesion.flush()
        return None

    debe = sum((dinero(l.importe) for l in lineas if l.importe > 0), CERO)
    haber = -sum((dinero(l.importe) for l in lineas if l.importe < 0), CERO)
    if debe != haber:
        raise AsientoDescuadrado(
            f"El asiento {tipo}.{numero} no cuadra: debe {debe} · haber {haber} · diferencia {debe - haber}"
        )

    cuentas = _cuentas_por_codigo(sesion, ejercicio, {l.cuenta for l in lineas})

    if existente is None:
        asiento = Asiento(
            ejercicio_id=ejercicio.id,
            tipo=tipo,
            numero=numero,
            sub=sub,
            numero_diario=siguiente_numero_diario(sesion, ejercicio),
        )
        sesion.add(asiento)
        previos: dict[str, list[Apunte]] = {}
    else:
        asiento = existente
        previos = {}
        for a in asiento.apuntes:
            previos.setdefault(a.cuenta.codigo, []).append(a)

    asiento.fecha = fecha
    asiento.concepto = concepto or asiento.concepto or ""
    asiento.subtipo = subtipo if subtipo is not None else asiento.subtipo

    # Debe primero y haber después, como el Diario de MGD. Se **reutilizan** los apuntes que ya había en cada cuenta
    # (MGD reutiliza los registros): conservan su identidad —de la que cuelgan los vencimientos de los extras— y sus textos.
    ordenadas = [l for l in lineas if l.importe > 0] + [l for l in lineas if l.importe < 0]
    resultado: list[Apunte] = []
    for orden, l in enumerate(ordenadas, start=1):
        importe = dinero(l.importe)
        reutilizable = previos.get(l.cuenta)
        apunte = reutilizable.pop(0) if reutilizable else Apunte(cuenta_id=cuentas[l.cuenta].id)
        apunte.orden = orden
        apunte.debe = importe if importe > 0 else CERO
        apunte.haber = -importe if importe < 0 else CERO
        apunte.concepto = l.concepto or apunte.concepto
        apunte.documento = l.documento or apunte.documento
        resultado.append(apunte)
    asiento.apuntes = resultado  # los apuntes que no se reutilizan se borran (delete-orphan)
    sesion.flush()
    return asiento


def borrar_asiento(sesion: Session, ejercicio: Ejercicio, tipo: int, numero: int, sub: int = 0) -> bool:
    """Borra un asiento (el ejercicio ha de estar abierto). Su número de diario queda como hueco."""
    validar_en_ejercicio(ejercicio.fecha_inicio, ejercicio)  # solo comprueba que el ejercicio admite cambios
    asiento = buscar_asiento(sesion, ejercicio, tipo, numero, sub)
    if asiento is None:
        return False
    sesion.delete(asiento)
    sesion.flush()
    return True
