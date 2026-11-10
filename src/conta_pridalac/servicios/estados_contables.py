"""Estados contables de gestión, por rango de fechas: saldos acumulados de un mes, balance de situación y cuenta de pérdidas y ganancias.

Son los listados «de trabajo», con las cuentas agrupadas por subgrupo del Plan General Contable. No son los modelos oficiales del Registro Mercantil (balance normal o abreviado), que asignan cada
cuenta a una línea concreta del modelo: eso va aparte. Todos excluyen por defecto los asientos de regularización y de cierre (subtipos R y Z), para ver el estado previo al cierre, como el balance de sumas y saldos.

- **Saldos acumulados de un mes**: por cuenta, el saldo hasta el mes anterior, lo movido en el mes y el saldo acumulado a final de mes.
- **Balance de situación**: el activo (grupos 2 y 3, y los saldos deudores de los grupos 4 y 5) frente al patrimonio neto y pasivo (grupo 1 y los saldos acreedores de los grupos 4 y 5), con el resultado del
  ejercicio (grupos 7 menos 6). Si la contabilidad cuadra, activo y pasivo coinciden.
- **Pérdidas y ganancias**: ingresos (grupo 7) y gastos (grupo 6) por subgrupo o por cuenta, y su diferencia.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, NIVEL_SUBCUENTA

CERO = Decimal("0.00")
SIN_CIERRE = ("R", "Z")  # regularización y cierre


@dataclass
class LineaEstado:
    tipo: str  # titulo · cuenta · subtotal · total
    codigo: str
    nombre: str
    importe: Decimal | None = None


@dataclass
class SaldoAcumulado:
    cuenta: str
    nombre: str
    anterior: Decimal  # saldo (debe - haber) hasta el fin del mes anterior
    debe: Decimal  # lo movido en el mes
    haber: Decimal
    acumulado: Decimal  # saldo (debe - haber) a fin de mes

    @property
    def deudor(self) -> Decimal:
        return self.acumulado if self.acumulado > 0 else CERO

    @property
    def acreedor(self) -> Decimal:
        return -self.acumulado if self.acumulado < 0 else CERO


def fin_de_mes(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def saldos_acumulados(sesion: Session, ejercicio: Ejercicio, mes: int, *, nivel: int = NIVEL_SUBCUENTA, incluir_cierre: bool = False) -> list[SaldoAcumulado]:
    """Saldos de cada cuenta al terminar el `mes` (1-12) del ejercicio, con el saldo anterior y lo movido en el mes. Salen las cuentas con saldo o con movimiento."""
    if not 1 <= mes <= 12:
        raise ValueError("El mes va de 1 a 12")
    sin = () if incluir_cierre else SIN_CIERRE
    hasta = fin_de_mes(ejercicio.anio, mes)
    acumulado = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ejercicio, nivel=nivel, hasta=hasta, excluir_subtipos=sin).filas}
    anterior = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ejercicio, nivel=nivel, hasta=fin_de_mes(ejercicio.anio, mes - 1), excluir_subtipos=sin).filas} if mes > 1 else {}
    del_mes = {f.cuenta: f for f in balance_sumas_y_saldos(sesion, ejercicio, nivel=nivel, desde=date(ejercicio.anio, mes, 1), hasta=hasta, excluir_subtipos=sin).filas}
    filas = []
    for cuenta in sorted(set(acumulado) | set(del_mes)):
        a, m = acumulado.get(cuenta), del_mes.get(cuenta)
        previo = anterior.get(cuenta)
        saldo_previo = (previo.debe - previo.haber) if previo else CERO
        saldo = (a.debe - a.haber) if a else CERO
        if saldo == 0 and saldo_previo == 0 and not (m and (m.debe or m.haber)):
            continue
        filas.append(SaldoAcumulado(cuenta, (a or m).nombre, saldo_previo, m.debe if m else CERO, m.haber if m else CERO, saldo))
    return filas


def _saldos(sesion: Session, ejercicio: Ejercicio, nivel: int, desde: date | None, hasta: date | None, incluir_cierre: bool) -> dict[str, tuple[str, Decimal]]:
    """{cuenta: (nombre, debe - haber)} del rango, sin los asientos de regularización y cierre salvo que se pidan."""
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=nivel, desde=desde, hasta=hasta, excluir_subtipos=() if incluir_cierre else SIN_CIERRE)
    return {f.cuenta: (f.nombre, f.debe - f.haber) for f in b.filas}


def cuenta_de_perdidas_y_ganancias(
    sesion: Session, ejercicio: Ejercicio, *, desde: date | None = None, hasta: date | None = None, nivel: int = 2, incluir_cierre: bool = False,
) -> list[LineaEstado]:
    """Ingresos (grupo 7), gastos (grupo 6) y resultado, por subgrupo (`nivel` 2) o por cuenta (`nivel` 3). Los gastos y los ingresos salen en positivo; el resultado es ingresos menos gastos."""
    saldos = _saldos(sesion, ejercicio, nivel, desde, hasta, incluir_cierre)
    lineas: list[LineaEstado] = []
    totales = {}
    for grupo, titulo, signo in (("7", "INGRESOS", -1), ("6", "GASTOS", 1)):
        lineas.append(LineaEstado("titulo", grupo, titulo))
        total = CERO
        for cuenta, (nombre, saldo) in saldos.items():
            if cuenta.startswith(grupo) and saldo != 0:
                lineas.append(LineaEstado("cuenta", cuenta, nombre, saldo * signo))
                total += saldo * signo
        lineas.append(LineaEstado("subtotal", grupo, f"Total {titulo.lower()}", total))
        totales[grupo] = total
    lineas.append(LineaEstado("total", "", "RESULTADO (ingresos − gastos)", totales["7"] - totales["6"]))
    return lineas


def balance_de_situacion(
    sesion: Session, ejercicio: Ejercicio, *, desde: date | None = None, hasta: date | None = None, incluir_cierre: bool = False,
) -> list[LineaEstado]:
    """Activo y patrimonio neto y pasivo por cuenta de 3 dígitos. Grupos 2 y 3 al activo (una amortización acumulada resta), grupo 1 al patrimonio neto y pasivo, y los grupos 4 y 5 según el signo del saldo
    de cada cuenta (deudor al activo, acreedor al pasivo). El resultado del ejercicio (grupo 7 menos grupo 6) va con el patrimonio neto. La última línea es la diferencia entre activo y pasivo (cero si cuadra)."""
    saldos = _saldos(sesion, ejercicio, 3, desde, hasta, incluir_cierre)
    activo: list[tuple[str, str, Decimal]] = []
    pasivo: list[tuple[str, str, Decimal]] = []
    resultado = CERO
    for cuenta, (nombre, saldo) in saldos.items():
        grupo = cuenta[0]
        if saldo == 0:
            continue
        if grupo in "23":
            activo.append((cuenta, nombre, saldo))
        elif grupo == "1":
            pasivo.append((cuenta, nombre, -saldo))
        elif grupo in "45":
            (activo if saldo > 0 else pasivo).append((cuenta, nombre, saldo if saldo > 0 else -saldo))
        elif grupo in "67":
            resultado -= saldo
    lineas: list[LineaEstado] = [LineaEstado("titulo", "", "ACTIVO")]
    lineas += [LineaEstado("cuenta", c, n, i) for c, n, i in sorted(activo)]
    total_activo = sum((i for _, _, i in activo), CERO)
    lineas.append(LineaEstado("total", "", "TOTAL ACTIVO", total_activo))
    lineas.append(LineaEstado("titulo", "", "PATRIMONIO NETO Y PASIVO"))
    lineas += [LineaEstado("cuenta", c, n, i) for c, n, i in sorted(pasivo)]
    if resultado:
        lineas.append(LineaEstado("cuenta", "", "Resultado del ejercicio (ingresos − gastos)", resultado))
    total_pasivo = sum((i for _, _, i in pasivo), CERO) + resultado
    lineas.append(LineaEstado("total", "", "TOTAL PATRIMONIO NETO Y PASIVO", total_pasivo))
    lineas.append(LineaEstado("subtotal", "", "Diferencia (activo − pasivo): cero si la contabilidad cuadra", total_activo - total_pasivo))
    return lineas
