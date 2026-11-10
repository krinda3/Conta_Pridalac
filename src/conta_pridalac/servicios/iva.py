"""Liquidación (regularización) del IVA de un periodo (docs/pseudocodigo/07_cierre_e_iva.md §1).

Reproduce `ResumenIVA.GeneraAsientoIVA` de MGD. Para el periodo [desde, hasta]:
1. Se toma el saldo (debe − haber) de las cuentas de IVA —las 472 (soportado) y 477 (repercutido)— con los movimientos del
   periodo, **sin contar las liquidaciones anteriores**.
2. El asiento cancela cada cuenta con saldo: lo soportado (deudor) va al haber y lo repercutido (acreedor) al debe.
3. La diferencia va a la cuenta de **Hacienda deudora** (4700…, a compensar o devolver) si el soportado supera al repercutido, o
   a **Hacienda acreedora** (4750…, a pagar) en caso contrario. Un IVA a pagar crea un **vencimiento** en el día de pago del
   periodo (por defecto el 25 del mes siguiente al periodo; configurable).
4. Si hay saldo a favor de periodos anteriores en la cuenta de Hacienda deudora, se puede **compensar** contra el IVA a pagar.

Es idempotente: liquidar el mismo periodo otra vez sustituye su asiento. La liquidación **se queda desactualizada** si después
se contabilizan facturas con fecha del periodo: `calcular_liquidacion` permite comparar (lo usa la auditoría).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    TIPO_AUTOMATICO,
    Apunte,
    Asiento,
    Cuenta,
    DeclaracionPresentada,
    Ejercicio,
    Parametro,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import validar_en_ejercicio
from conta_pridalac.servicios.extras import LineaManual, ResultadoExtra, grabar_extra
from conta_pridalac.servicios.vencimientos import PlazoVencimiento

CERO = Decimal("0.00")
PREFIJOS_IVA = ("472", "477")  # soportado y repercutido (PGC)
SUBTIPO_IVA = "P"


def parametro(sesion: Session, ejercicio: Ejercicio, clave: str, defecto: str | None = None) -> str | None:
    valor = sesion.scalar(select(Parametro.valor).where(Parametro.empresa_id == ejercicio.empresa_id, Parametro.clave == clave))
    return valor.strip() if valor and valor.strip() else defecto


def periodo_de(hasta: date, periodicidad: int = 4) -> tuple[date, date]:
    """Periodo de IVA que acaba en `hasta`: `periodicidad` = nº de periodos al año (4 trimestral, 6 bimestral, 12 mensual)."""
    meses = 12 // periodicidad
    mes_inicio = ((hasta.month - 1) // meses) * meses + 1
    fin = date(hasta.year, mes_inicio + meses - 1, calendar.monthrange(hasta.year, mes_inicio + meses - 1)[1])
    return date(hasta.year, mes_inicio, 1), fin


def texto_periodo(desde: date, hasta: date, periodicidad: int = 4) -> str:
    if periodicidad == 4:
        return f"REGUL. IVA {(hasta.month - 1) // 3 + 1} TRIM/{hasta.year}"
    if periodicidad == 6:
        return f"REGUL. IVA {(hasta.month - 1) // 2 + 1} BIMESTRE/{hasta.year}"
    return f"REGUL. IVA {hasta:%m}/{hasta.year}"


def fecha_de_pago(hasta: date, periodicidad: int = 4, dias: list[int] | None = None) -> date:
    """Día de pago del IVA a ingresar: el día `dias[i]` del primer mes tras el periodo (por defecto 25, como MGD)."""
    meses = 12 // periodicidad
    indice = (hasta.month - 1) // meses
    primer_mes = hasta.month + 1
    anio = hasta.year + (1 if primer_mes > 12 else 0)
    primer_mes = (primer_mes - 1) % 12 + 1
    dia = dias[indice] if dias and indice < len(dias) else 25
    return date(anio, primer_mes, min(dia, calendar.monthrange(anio, primer_mes)[1]))


@dataclass
class Liquidacion:
    """Resultado del cálculo (sin grabar nada)."""

    desde: date
    hasta: date
    saldos: dict[str, Decimal]  # cuenta de IVA → saldo (debe − haber) del periodo
    soportado: Decimal = CERO  # Σ saldos deudores
    repercutido: Decimal = CERO  # Σ saldos acreedores (en positivo)
    a_pagar: Decimal = CERO  # tras compensar
    a_compensar: Decimal = CERO  # soportado > repercutido: queda a favor en Hacienda deudora
    compensado: Decimal = CERO  # saldo anterior a favor aplicado a este periodo
    lineas: dict[str, Decimal] = field(default_factory=dict)  # asiento: cuenta → importe con signo (debe +)


def _saldos_del_periodo(sesion: Session, ejercicio: Ejercicio, desde: date, hasta: date, prefijos) -> dict[str, Decimal]:
    filas = sesion.execute(
        select(Cuenta.codigo, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Apunte, Apunte.cuenta_id == Cuenta.id)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(
            Asiento.ejercicio_id == ejercicio.id,
            Asiento.fecha >= desde,
            Asiento.fecha <= hasta,
            func.coalesce(Asiento.subtipo, "") != SUBTIPO_IVA,
        )
        .group_by(Cuenta.codigo)
    ).all()
    saldos = {}
    for codigo, debe, haber in filas:
        neto = (debe or CERO) - (haber or CERO)
        if neto != 0 and codigo.startswith(tuple(prefijos)):
            saldos[codigo] = neto
    return saldos


def _saldo_a_favor_anterior(sesion: Session, ejercicio: Ejercicio, cuenta_deudora: str, antes_de: date) -> Decimal:
    """Saldo deudor de «Hacienda deudora por IVA» antes del periodo (lo que se puede compensar)."""
    debe, haber = sesion.execute(
        select(func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ejercicio.id, Cuenta.codigo == cuenta_deudora, Asiento.fecha < antes_de)
    ).one()
    saldo = (debe or CERO) - (haber or CERO)
    return saldo if saldo > 0 else CERO


def calcular_liquidacion(
    sesion: Session, ejercicio: Ejercicio, desde: date, hasta: date, *, compensar: bool = True, prefijos=PREFIJOS_IVA
) -> Liquidacion:
    cuenta_deudora = parametro(sesion, ejercicio, "IVA_DEBE")
    cuenta_acreedora = parametro(sesion, ejercicio, "IVA_HABER")
    if not cuenta_deudora or not cuenta_acreedora:
        raise ErrorContable("Faltan los parámetros IVA_DEBE e IVA_HABER (cuentas de Hacienda deudora y acreedora por IVA)")
    saldos = _saldos_del_periodo(sesion, ejercicio, desde, hasta, prefijos)
    liq = Liquidacion(desde=desde, hasta=hasta, saldos=saldos)
    if not saldos:
        return liq

    liq.soportado = sum((s for s in saldos.values() if s > 0), CERO)
    liq.repercutido = -sum((s for s in saldos.values() if s < 0), CERO)
    liq.lineas = {cuenta: -saldo for cuenta, saldo in saldos.items()}  # cancela cada cuenta

    neto = liq.soportado - liq.repercutido  # > 0: IVA a favor · < 0: IVA a pagar
    if neto > 0:
        liq.a_compensar = neto
        liq.lineas[cuenta_deudora] = liq.lineas.get(cuenta_deudora, CERO) + neto
    elif neto < 0:
        pagar = -neto
        a_favor = _saldo_a_favor_anterior(sesion, ejercicio, cuenta_deudora, desde) if compensar else CERO
        liq.compensado = min(a_favor, pagar)
        liq.a_pagar = pagar - liq.compensado
        if liq.a_pagar > 0:
            liq.lineas[cuenta_acreedora] = liq.lineas.get(cuenta_acreedora, CERO) - liq.a_pagar
        if liq.compensado > 0:
            liq.lineas[cuenta_deudora] = liq.lineas.get(cuenta_deudora, CERO) - liq.compensado
    return liq


def declaracion_de(sesion: Session, asiento: Asiento) -> DeclaracionPresentada | None:
    """Declaración presentada con la que se contabilizó este asiento de liquidación, si la hay."""
    return sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.asiento_id == asiento.id)).first()


def resultado_del_asiento(asiento: Asiento) -> Decimal:
    """Resultado de una liquidación contabilizada: lo que va a Hacienda acreedora (475) menos lo que va a Hacienda deudora (470);
    positivo = a ingresar, negativo = a compensar."""
    return sum((ap.haber - ap.debe for ap in asiento.apuntes if ap.cuenta.codigo.startswith(("470", "475"))), CERO)


def coincide_con_lo_presentado(asiento: Asiento, declaracion: DeclaracionPresentada) -> bool:
    """El asiento coincide con la declaración si su resultado es el de la casilla 46 (antes de compensar) o el de la 71 (después)."""
    resultado = resultado_del_asiento(asiento)
    return resultado in (declaracion.resultado_liquidacion, declaracion.resultado)


def _asiento_de_liquidacion(sesion: Session, ejercicio: Ejercicio, hasta: date) -> Asiento | None:
    return sesion.scalars(
        select(Asiento).where(
            Asiento.ejercicio_id == ejercicio.id,
            Asiento.tipo == TIPO_AUTOMATICO,
            Asiento.subtipo == SUBTIPO_IVA,
            Asiento.fecha == hasta,
        )
    ).first()


def liquidar_iva(
    sesion: Session, ejercicio: Ejercicio, hasta: date, *, periodicidad: int | None = None, compensar: bool = True,
    dias_pago: list[int] | None = None,
) -> tuple[Liquidacion, ResultadoExtra]:
    """Calcula y graba (o regraba) la liquidación del periodo que acaba en `hasta`."""
    validar_en_ejercicio(hasta, ejercicio)
    periodicidad = periodicidad or int(parametro(sesion, ejercicio, "IVA_PERIODICIDAD", "4"))
    if dias_pago is None and (texto := parametro(sesion, ejercicio, "IVA_DIAS_PAGO")):
        dias_pago = [int(x) for x in texto.split(",")]
    desde, hasta_periodo = periodo_de(hasta, periodicidad)
    if hasta != hasta_periodo:
        raise ErrorContable(f"El periodo de IVA que contiene el {hasta:%d/%m/%Y} acaba el {hasta_periodo:%d/%m/%Y}")
    liq = calcular_liquidacion(sesion, ejercicio, desde, hasta, compensar=compensar)
    if not liq.lineas:
        raise ErrorContable("No hay datos de IVA en el periodo para generar el asiento")

    cuenta_acreedora = parametro(sesion, ejercicio, "IVA_HABER")
    existente = _asiento_de_liquidacion(sesion, ejercicio, hasta)
    lineas = []
    for cuenta, importe in liq.lineas.items():
        plazos = None
        if cuenta == cuenta_acreedora and liq.a_pagar > 0:
            plazos = [PlazoVencimiento(importe=-liq.a_pagar, fecha=fecha_de_pago(hasta, periodicidad, dias_pago))]
        nombre = sesion.scalars(select(Cuenta.nombre).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == cuenta)).first() or ""
        lineas.append(LineaManual(cuenta, "D" if importe > 0 else "H", abs(importe), nombre, plazos))
    resultado = grabar_extra(
        sesion, ejercicio, fecha=hasta, texto=texto_periodo(desde, hasta, periodicidad), lineas=lineas,
        numero=existente.numero if existente else None, tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_IVA,
    )
    return liq, resultado
