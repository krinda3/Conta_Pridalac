"""Movimientos de banco, cobros, pagos, compensaciones y transferencias (docs/pseudocodigo/02_tesoreria.md).

Un movimiento de banco agrupa uno o varios **pagos** (líneas) y su asiento (tipo 3, mismo número) se genera siempre a partir
de ellos (`domain.tesoreria.apuntes_de_movimiento`); no se teclea. Si las líneas se anulan (el lado de entrada de una
transferencia) no hay asiento.

Signo de un pago, desde el banco: positivo = entra dinero (cobro), negativo = sale (pago). Para saldar un vencimiento, el
pago tiene el mismo signo que el vencimiento (a pagar negativo, a cobrar positivo).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    BANCO_COMPENSACION,
    TIPO_TESORERIA,
    Asiento,
    Banco,
    Cuenta,
    Ejercicio,
    ExtractoLinea,
    MovimientoBanco,
    Pago,
    Vencimiento,
)
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import validar_en_ejercicio
from conta_pridalac.domain.tesoreria import (
    CERO,
    apuntes_de_movimiento,
    cuenta_pendiente_de_aplicar,
    pendiente,
)
from conta_pridalac.servicios.asientos import LineaAsiento, borrar_asiento, grabar_asiento

CLAVE_AUTOMATICA = "ZZZ"  # los movimientos automáticos quedan los últimos del día


@dataclass
class LineaPago:
    """Una línea a grabar. Sin `vencimiento` ni `cuenta_directa` queda **pendiente de aplicar**."""

    importe: Decimal
    vencimiento: Vencimiento | None = None
    cuenta_directa: str | None = None  # código de 8 dígitos


@dataclass
class ResultadoMovimiento:
    movimiento: MovimientoBanco
    asiento: Asiento | None
    advertencias: list[str] = field(default_factory=list)


def siguiente_numero(sesion: Session, ejercicio: Ejercicio) -> int:
    maximo = sesion.scalar(select(func.max(MovimientoBanco.numero)).where(MovimientoBanco.ejercicio_id == ejercicio.id))
    return (maximo or 0) + 1


def texto_automatico(movimiento: MovimientoBanco) -> str:
    """Texto de un movimiento según lo que salda. Ej.: `PAGO 12 R 48 · FACTOR HUMUS` (MGD `AUTOTEXT`)."""
    partes = []
    for p in movimiento.pagos:
        if p.vencimiento is not None:
            v = p.vencimiento
            tercero = v.factura.tercero.nombre if v.factura is not None and v.factura.tercero is not None else ""
            partes.append(f"{v.origen_tipo} {v.origen_numero}" + (f" {tercero}" if tercero else ""))
        elif p.cuenta_directa is not None:
            partes.append(p.cuenta_directa.nombre)
        else:
            partes.append("PENDIENTE DE APLICAR")
    verbo = "COBRO" if sum((p.importe for p in movimiento.pagos), CERO) > 0 else "PAGO"
    return f"{verbo} {movimiento.fecha:%d/%m/%y} · " + " + ".join(partes[:3])


def _cuenta(sesion: Session, ejercicio: Ejercicio, codigo: str) -> Cuenta:
    c = sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == codigo)).one_or_none()
    if c is None:
        raise ErrorContable(f"La cuenta {codigo} no existe en el plan de la empresa")
    return c


def _advertencias(sesion: Session, lineas: list[LineaPago], movimiento: MovimientoBanco | None) -> list[str]:
    avisos = []
    for l in lineas:
        v = l.vencimiento
        if v is None or v.id is None:
            continue
        # lo ya pagado por *otros* movimientos
        otros = sesion.scalar(
            select(func.sum(Pago.importe)).where(Pago.vencimiento_id == v.id, Pago.movimiento_id != (movimiento.id if movimiento else -1))
        ) or CERO
        resto = v.importe - otros
        if l.importe != 0 and (resto == 0 or (l.importe > 0) != (resto > 0)):
            avisos.append(f"El vencimiento de {v.origen_tipo} {v.origen_numero} ya está pagado: queda {resto} y se paga {l.importe}")
        elif abs(l.importe) > abs(resto):
            avisos.append(f"Se paga {l.importe} del vencimiento de {v.origen_tipo} {v.origen_numero}, que solo tiene {resto} pendiente")
    return avisos


def registrar_movimiento(
    sesion: Session,
    ejercicio: Ejercicio,
    banco: Banco,
    fecha: date,
    lineas: list[LineaPago],
    *,
    texto: str = "",
    clave: str = "",
    movimiento: MovimientoBanco | None = None,
    contrapartes: list[MovimientoBanco | None] | None = None,
) -> ResultadoMovimiento:
    """Crea (o, si se pasa `movimiento`, reemplaza) un movimiento de banco con sus pagos y regenera su asiento."""
    validar_en_ejercicio(fecha, ejercicio)
    if not lineas:
        raise ErrorContable("Un movimiento necesita al menos una línea")
    advertencias = _advertencias(sesion, lineas, movimiento)

    if movimiento is None:
        movimiento = MovimientoBanco(ejercicio_id=ejercicio.id, numero=siguiente_numero(sesion, ejercicio))
        sesion.add(movimiento)
    else:
        movimiento.pagos.clear()
        sesion.flush()
    movimiento.banco, movimiento.fecha, movimiento.clave = banco, fecha, clave

    for orden, l in enumerate(lineas, start=1):
        movimiento.pagos.append(
            Pago(
                orden=orden,
                importe=dinero(l.importe),
                vencimiento=l.vencimiento,
                cuenta_directa=_cuenta(sesion, ejercicio, l.cuenta_directa) if l.cuenta_directa else None,
                movimiento_contraparte=(contrapartes[orden - 1] if contrapartes else None),
            )
        )
    sesion.flush()
    movimiento.texto_automatico = not texto
    movimiento.texto = texto or texto_automatico(movimiento)

    esperado = apuntes_de_movimiento(sesion, movimiento)
    asiento = grabar_asiento(
        sesion, ejercicio, tipo=TIPO_TESORERIA, numero=movimiento.numero, fecha=fecha,
        concepto=movimiento.texto, subtipo="M",
        lineas=[LineaAsiento(cuenta, importe) for cuenta, importe in esperado.items()],
    )
    return ResultadoMovimiento(movimiento, asiento, advertencias)


def eliminar_movimiento(sesion: Session, ejercicio: Ejercicio, movimiento: MovimientoBanco) -> int:
    """Borra el movimiento y su asiento (y, si es una transferencia, también el movimiento espejo). Devuelve cuántos borró."""
    validar_en_ejercicio(ejercicio.fecha_inicio, ejercicio)  # solo comprueba que el ejercicio admite cambios
    a_borrar = {movimiento.id: movimiento}
    for p in list(movimiento.pagos):
        if p.movimiento_contraparte is not None:
            a_borrar[p.movimiento_contraparte.id] = p.movimiento_contraparte
    for m in a_borrar.values():
        for p in m.pagos:
            p.movimiento_contraparte_id = None
    # las bases antiguas no llevan la restricción «poner a nulo» en esta columna: se suelta aquí la línea del extracto que pagó la factura
    sesion.execute(update(ExtractoLinea).where(ExtractoLinea.movimiento_id.in_(list(a_borrar))).values(movimiento_id=None))
    sesion.flush()
    for m in a_borrar.values():
        borrar_asiento(sesion, ejercicio, TIPO_TESORERIA, m.numero)
        sesion.delete(m)
    sesion.flush()
    return len(a_borrar)


def regenerar_asiento(sesion: Session, ejercicio: Ejercicio, movimiento: MovimientoBanco) -> Asiento | None:
    """Rehace el asiento de un movimiento (p. ej. tras cambiar la cuenta de devengo de un vencimiento que salda)."""
    esperado = apuntes_de_movimiento(sesion, movimiento)
    return grabar_asiento(
        sesion, ejercicio, tipo=TIPO_TESORERIA, numero=movimiento.numero, fecha=movimiento.fecha,
        concepto=movimiento.texto, subtipo="M",
        lineas=[LineaAsiento(cuenta, importe) for cuenta, importe in esperado.items()],
    )


# ---------------------------------------------------------------------------------------------- atajos


def pagar_vencimiento(
    sesion: Session, ejercicio: Ejercicio, vencimiento: Vencimiento, banco: Banco, fecha: date | None = None,
    *, importe: Decimal | None = None, texto: str = "", clave: str = CLAVE_AUTOMATICA,
) -> ResultadoMovimiento:
    """Pago (o cobro) **inmediato directo** (`UnVto.PIDirecto`): salda el pendiente, o `importe`, por `banco`."""
    pte = pendiente(sesion, vencimiento)
    if pte == 0 and importe is None:
        raise ErrorContable("El vencimiento ya está saldado")
    fecha = fecha or vencimiento.fecha
    if fecha is None:
        raise ErrorContable("Falta la fecha del movimiento")
    return registrar_movimiento(
        sesion, ejercicio, banco, fecha, [LineaPago(importe if importe is not None else pte, vencimiento)], texto=texto, clave=clave
    )


def banco_de_compensacion(sesion: Session, ejercicio: Ejercicio) -> Banco:
    """El banco especial «Compensación de vencimientos» de la empresa; se crea si falta (`CompruebaBancoCompVtos`)."""
    banco = sesion.scalars(select(Banco).where(Banco.empresa_id == ejercicio.empresa_id, Banco.clase == BANCO_COMPENSACION)).first()
    if banco is None:
        cuenta = _cuenta(sesion, ejercicio, cuenta_pendiente_de_aplicar(sesion, ejercicio.empresa_id))
        banco = Banco(empresa_id=ejercicio.empresa_id, numero=-1, clase=BANCO_COMPENSACION, nombre="COMPENSACION DE VENCIMIENTOS", cuenta_id=cuenta.id)
        sesion.add(banco)
        sesion.flush()
    return banco


def compensar_vencimiento(
    sesion: Session, ejercicio: Ejercicio, vencimiento: Vencimiento, cuenta_compensacion: str, fecha: date | None = None,
    *, texto: str = "",
) -> ResultadoMovimiento:
    """Salda el vencimiento contra otra cuenta sin pasar por tesorería (`UnVto.PICompensacion`): dos pagos que suman 0."""
    pte = pendiente(sesion, vencimiento)
    if pte == 0:
        raise ErrorContable("El vencimiento ya está saldado")
    fecha = fecha or vencimiento.fecha
    if fecha is None:
        raise ErrorContable("Falta la fecha del movimiento")
    return registrar_movimiento(
        sesion, ejercicio, banco_de_compensacion(sesion, ejercicio), fecha,
        [LineaPago(pte, vencimiento), LineaPago(-pte, cuenta_directa=cuenta_compensacion)],
        texto=texto, clave=CLAVE_AUTOMATICA,
    )


def transferir(
    sesion: Session, ejercicio: Ejercicio, origen: Banco, destino: Banco, fecha: date, importe: Decimal, *, texto: str = ""
) -> tuple[ResultadoMovimiento, ResultadoMovimiento]:
    """Transferencia entre dos bancos: dos movimientos espejo (salida y entrada) que se apuntan entre sí.

    Solo el lado de salida genera asiento (banco origen contra banco destino): el de entrada lleva la cuenta de su propio
    banco, sus líneas se anulan y no hay asiento.
    """
    if origen.id == destino.id:
        raise ErrorContable("El banco de origen y el de destino son el mismo")
    if importe <= 0:
        raise ErrorContable("El importe de la transferencia ha de ser positivo")
    if origen.cuenta is None or destino.cuenta is None:
        raise ErrorContable("Los dos bancos necesitan cuenta contable")
    salida = registrar_movimiento(
        sesion, ejercicio, origen, fecha, [LineaPago(-importe, cuenta_directa=destino.cuenta.codigo)], texto=texto, clave=CLAVE_AUTOMATICA
    )
    entrada = registrar_movimiento(
        sesion, ejercicio, destino, fecha, [LineaPago(importe, cuenta_directa=destino.cuenta.codigo)], texto=texto, clave=CLAVE_AUTOMATICA,
        contrapartes=[salida.movimiento],
    )
    salida.movimiento.pagos[0].movimiento_contraparte = entrada.movimiento
    sesion.flush()
    return salida, entrada


# ---------------------------------------------------------------------------------------------- bancos


def _datos_de_banco(sesion: Session, empresa_id: int, nombre: str, cuenta: str, iban: str | None, bic: str | None, sucursal: str | None) -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorContable("Falta el nombre del banco")
    cuenta = (cuenta or "").strip()
    if not cuenta:
        raise ErrorContable("Falta la cuenta contable del banco (por ejemplo 57200001)")
    c = sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == cuenta)).one_or_none()
    if c is None:
        raise ErrorContable(f"No existe la cuenta {cuenta}: créela primero en el plan de cuentas")
    otro = sesion.scalars(select(Banco).where(Banco.empresa_id == empresa_id, Banco.cuenta_id == c.id, Banco.clase == "B")).first()
    return dict(
        nombre=nombre[:64], cuenta_id=c.id, iban=(iban or "").replace(" ", "").upper()[:34] or None, bic=(bic or "").strip().upper()[:11] or None,
        sucursal=(sucursal or "").strip()[:64] or None, _otro=otro,
    )


ORDEN_DE_BANCOS = (Banco.orden.is_(None), Banco.orden, Banco.numero)  # el de las listas para elegir banco: primero los que el usuario ha ordenado, luego por número


def crear_banco(
    sesion: Session, empresa_id: int, nombre: str, cuenta: str, *, iban: str | None = None, bic: str | None = None, sucursal: str | None = None,
    saldo_inicial: Decimal = CERO, orden: int | None = None,
) -> Banco:
    datos = _datos_de_banco(sesion, empresa_id, nombre, cuenta, iban, bic, sucursal)
    if datos.pop("_otro") is not None:
        raise ErrorContable(f"La cuenta {cuenta} ya es la de otro banco")
    numero = (sesion.scalar(select(func.max(Banco.numero)).where(Banco.empresa_id == empresa_id)) or 0) + 1
    banco = Banco(empresa_id=empresa_id, numero=max(numero, 1), clase="B", saldo_inicial=dinero(saldo_inicial), orden=orden, **datos)
    sesion.add(banco)
    sesion.flush()
    return banco


def modificar_banco(
    sesion: Session, banco: Banco, nombre: str, cuenta: str, *, iban: str | None = None, bic: str | None = None, sucursal: str | None = None,
    saldo_inicial: Decimal = CERO, orden: int | None = None,
) -> Banco:
    if banco.clase != "B":
        raise ErrorContable("Este banco es del sistema y no se modifica")
    datos = _datos_de_banco(sesion, banco.empresa_id, nombre, cuenta, iban, bic, sucursal)
    otro = datos.pop("_otro")
    if otro is not None and otro.id != banco.id:
        raise ErrorContable(f"La cuenta {cuenta} ya es la de otro banco")
    movimientos = sesion.scalar(select(func.count()).select_from(MovimientoBanco).where(MovimientoBanco.banco_id == banco.id))
    if movimientos and datos["cuenta_id"] != banco.cuenta_id:
        raise ErrorContable(f"No se puede cambiar la cuenta de un banco con {movimientos} movimientos: sus asientos usan la cuenta actual")
    for campo, valor in datos.items():
        setattr(banco, campo, valor)
    banco.saldo_inicial = dinero(saldo_inicial)
    banco.orden = orden
    sesion.flush()
    return banco


def borrar_banco(sesion: Session, banco: Banco) -> None:
    if banco.clase != "B":
        raise ErrorContable("Este banco es del sistema y no se borra")
    movimientos = sesion.scalar(select(func.count()).select_from(MovimientoBanco).where(MovimientoBanco.banco_id == banco.id))
    if movimientos:
        raise ErrorContable(f"No se puede borrar «{banco.nombre}»: tiene {movimientos} movimientos")
    sesion.delete(banco)
    sesion.flush()
