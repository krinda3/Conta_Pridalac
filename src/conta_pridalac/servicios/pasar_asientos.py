"""Pasar a «Movimientos de banco» la parte del banco de los asientos manuales, como el cobro o el pago de una operación.

Un asiento manual (tipo 4) puede llevar una línea de la cuenta del banco. Contablemente está bien, pero el saldo del banco ya no coincide con «saldo inicial + movimientos de banco» y la auditoría lo señala
(`saldo_de_banco`). Un movimiento de banco no se inventa: tiene que ser el cobro o el pago de algo que la contabilidad ya recoge. Por eso sólo se pasan los asientos que **contienen esa operación**: el
asiento de la concesión de una subvención y su cobro, o el de una corrección y su devolución, donde una cuenta (4708, un proveedor…) aparece primero por el importe de la operación y luego por el mismo importe
al contrario, que es lo que el banco cancela.

Para cada uno: la línea del banco y la de la cuenta que cancela se quitan del asiento manual; en la línea que queda de esa cuenta (la operación) se anota un **vencimiento** por el importe, y el movimiento de
banco **salda ese vencimiento**, como el cobro de una factura. Los saldos de todas las cuentas quedan exactamente como estaban. Si el asiento no contiene la operación, o hay dudas sobre cuál es, no se toca y se dice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Asiento, Banco, Ejercicio, MovimientoBanco, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.asientos import buscar_asiento
from conta_pridalac.servicios.extras import LineaManual, grabar_extra
from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento
from conta_pridalac.servicios.vencimientos import PlazoVencimiento


@dataclass
class Conversion:
    asiento: str  # «4.2»
    fecha: date
    concepto: str
    importe: Decimal  # en el banco: positivo entra, negativo sale
    contrapartida: str | None = None  # la cuenta que el cobro o el pago cancela (y en la que nace el vencimiento)
    movimiento: int | None = None  # nº del movimiento creado (sólo si se ha hecho)
    resto: list[tuple[str, Decimal]] = field(default_factory=list)  # lo que queda en el asiento manual: (cuenta, debe − haber)
    problema: str = ""

    @property
    def hecha(self) -> bool:
        return not self.problema


def _identificador(a: Asiento) -> str:
    return f"{a.tipo}.{a.numero}" + (f"/{a.sub}" if a.sub else "")


def asientos_a_pasar(sesion: Session, ejercicio: Ejercicio, banco: Banco) -> list[Asiento]:
    """Los asientos que tocan la cuenta del banco sin ser un movimiento de banco: ni apertura, regularización o cierre, ni el asiento 3.n de uno de sus movimientos."""
    numeros = set(sesion.scalars(select(MovimientoBanco.numero).where(MovimientoBanco.banco_id == banco.id, MovimientoBanco.ejercicio_id == ejercicio.id)))
    asientos = sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id).order_by(Asiento.fecha, Asiento.numero_diario))
    return [a for a in asientos if (a.subtipo or "") not in ("A", "R", "Z") and not (a.tipo == 3 and a.numero in numeros) and any(ap.cuenta_id == banco.cuenta_id for ap in a.apuntes)]


def _decidir(asiento: Asiento, banco: Banco):
    """(línea del banco, línea de la contrapartida, línea que queda con la operación) o un texto con el motivo por el que no se puede decidir sin dudar."""
    if asiento.sub:
        return "es un asiento con subnúmero"
    apuntes = sorted(asiento.apuntes, key=lambda a: a.orden)
    del_banco = [a for a in apuntes if a.cuenta_id == banco.cuenta_id]
    if len(del_banco) != 1:
        return f"tiene {len(del_banco)} líneas del banco: no se sabe cuál pasar"
    b = del_banco[0]
    importe = b.debe - b.haber
    validos = []
    for a in apuntes:
        if a is b or a.cuenta_id == banco.cuenta_id or a.debe - a.haber != -importe:
            continue  # sólo vale una línea de importe igual y lado contrario al del banco…
        operacion = [o for o in apuntes if o is not a and o is not b and o.cuenta_id == a.cuenta_id and o.debe - o.haber == importe]
        if len(operacion) == 1:  # …de una cuenta que en el asiento tiene la operación que el banco cancela
            validos.append((b, a, operacion[0]))
    if not validos:
        return "no recoge la operación que el banco cancela (no hay una cuenta con el mismo importe a un lado y al otro): un movimiento así no sale de ninguna operación de la contabilidad"
    if len(validos) > 1:
        return "hay varias cuentas posibles para la operación que el banco cancela y no se puede decidir cuál es"
    return validos[0]


def pasar_a_movimiento(sesion: Session, ejercicio: Ejercicio, banco: Banco, asiento: Asiento, *, hacer: bool = True) -> Conversion:
    """Pasa la línea del banco de un asiento manual a un movimiento que salda un vencimiento de la operación. Con `hacer=False` sólo dice qué haría. No hace commit."""
    c = Conversion(_identificador(asiento), asiento.fecha, asiento.concepto or "", Decimal("0.00"))
    decision = _decidir(asiento, banco)
    if isinstance(decision, str):
        c.problema = decision
        return c
    del_banco, contra, operacion = decision
    c.importe = del_banco.debe - del_banco.haber
    c.contrapartida = contra.cuenta.codigo
    resto = [a for a in sorted(asiento.apuntes, key=lambda x: x.orden) if a is not del_banco and a is not contra]
    c.resto = [(a.cuenta.codigo, a.debe - a.haber) for a in resto]
    if not hacer:
        return c
    lineas = []
    for a in resto:
        neto = a.debe - a.haber
        plazos = [PlazoVencimiento(importe=c.importe, fecha=asiento.fecha, banco=banco)] if a is operacion else None  # el vencimiento nace de la operación: a cobrar si entra, a pagar si sale
        lineas.append(LineaManual(a.cuenta.codigo, "D" if neto > 0 else "H", abs(neto), a.concepto or "", plazos))
    numero, tipo, fecha, concepto, subtipo = asiento.numero, asiento.tipo, asiento.fecha, asiento.concepto or "", asiento.subtipo or "M"
    sesion.expire(asiento)
    grabar_extra(sesion, ejercicio, fecha=fecha, texto=concepto, lineas=lineas, numero=numero, tipo=tipo, subtipo=subtipo)
    nuevo = buscar_asiento(sesion, ejercicio, tipo, numero)
    linea = next((a for a in nuevo.apuntes if a.cuenta.codigo == c.contrapartida and a.debe - a.haber == c.importe), None) if nuevo is not None else None  # la línea de la operación, ya regrabada
    vencimiento = sesion.scalars(select(Vencimiento).where(Vencimiento.apunte_id == linea.id, Vencimiento.importe == c.importe).order_by(Vencimiento.id.desc())).first() if linea is not None else None
    if vencimiento is None:
        raise ErrorContable(f"No se ha podido crear el vencimiento de la operación del asiento {c.asiento}")
    resultado = registrar_movimiento(sesion, ejercicio, banco, fecha, [LineaPago(c.importe, vencimiento=vencimiento)], texto=concepto)
    c.movimiento = resultado.movimiento.numero
    return c


def pasar_todos(sesion: Session, ejercicio: Ejercicio, banco: Banco, solo: set[str] | None = None, *, hacer: bool = True) -> list[Conversion]:
    """Pasa los asientos que se puedan decidir (o sólo los `solo`, por su identificador «4.2»)."""
    if ejercicio.cerrado:
        raise ErrorContable("El ejercicio está cerrado: no se tocan sus asientos")
    return [pasar_a_movimiento(sesion, ejercicio, banco, a, hacer=hacer) for a in asientos_a_pasar(sesion, ejercicio, banco) if solo is None or _identificador(a) in solo]
