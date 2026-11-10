"""Conciliar vencimientos pendientes de pago con las líneas del extracto que se han quedado sin factura.

Después de contabilizar las facturas con «Contabilizar el resto», lo que no se ha pagado queda como vencimiento pendiente, y los cargos del banco que no han pagado nada siguen libres. Aquí se juntan: una
o varias líneas pagan uno o varios vencimientos. Se crea un movimiento de banco por línea, con su fecha valor y su importe, que salda los vencimientos; así el Mayor del banco coincide con el extracto.

Si las líneas suman distinto que lo pendiente, hay dos salidas: dejar un **pago parcial** (el resto del vencimiento sigue pendiente; sólo si se ha pagado menos) o **saldar con una diferencia** que se
lleva a una cuenta (una propina, un redondeo, un descuento), sea por defecto o por exceso. Por ahora sólo facturas recibidas (cargos del banco).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Extracto, ExtractoLinea, MovimientoBanco, PalabraConciliacion, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.conciliacion import FacturaPorConciliar, LineaPorConciliar, conciliar, normalizar
from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento

CERO = Decimal("0.00")
MARGEN_DIAS = 90  # las líneas se buscan entre las fechas de los vencimientos menos y más esto
PARCIAL, CON_DIFERENCIA = "parcial", "diferencia"
# Proveedores que facturan en un solo documento lo que se les ha ido pagando con su tarjeta, en varios cargos y con descuentos (su palabra en el nombre, sin tildes ni mayúsculas).
PROVEEDORES_ACUMULADOS = ("solred",)
MAX_LINEAS_ACUMULADAS = 7  # cargos y descuentos que se prueban juntos
MAX_CANDIDATAS = 20  # las líneas más cercanas a la fecha de la factura
DIAS_ACUMULADOS = 45  # cuánto antes y después de la factura se miran los cargos (los descuentos llegan semanas más tarde)


@dataclass
class Sugerencia:
    vencimientos: list[Vencimiento]
    lineas: list[ExtractoLinea]
    regla: str
    motivo: str

    @property
    def clave(self) -> str:
        """Identifica la sugerencia en la web: «v12-13_l5-6»."""
        return "v" + "-".join(str(v.id) for v in self.vencimientos) + "_l" + "-".join(str(l.id) for l in self.lineas)


@dataclass
class ResultadoPagos:
    movimientos: int = 0
    saldados: int = 0
    parciales: int = 0
    diferencia: Decimal = CERO
    avisos: list[str] = field(default_factory=list)


def vencimientos_a_pagar(sesion: Session, ejercicio: Ejercicio) -> list[tuple[Vencimiento, Decimal]]:
    """(vencimiento, pendiente) de las facturas recibidas con algo por pagar, por fecha. El pendiente va en positivo."""
    consulta = select(Vencimiento).where(Vencimiento.ejercicio_id == ejercicio.id, Vencimiento.origen_tipo == "R", Vencimiento.importe < 0).order_by(Vencimiento.fecha, Vencimiento.id)
    resultado = []
    for v in sesion.scalars(consulta):
        pte = pendiente(sesion, v)
        if pte < 0:
            resultado.append((v, -pte))
    return resultado


def lineas_libres(sesion: Session, empresa_id: int, desde: date | None = None, hasta: date | None = None, *, con_abonos: bool = False) -> list[ExtractoLinea]:
    """Cargos del extracto (importe negativo) que todavía no han pagado nada, de bancos con subcuenta. Con `con_abonos`, también los abonos (descuentos y devoluciones, que restan de lo pagado)."""
    consulta = (select(ExtractoLinea).join(Banco, Banco.id == ExtractoLinea.banco_id).where(ExtractoLinea.empresa_id == empresa_id, ExtractoLinea.movimiento_id.is_(None),
                                                                                         Banco.cuenta_id.is_not(None)).order_by(ExtractoLinea.fecha, ExtractoLinea.id))
    if not con_abonos:
        consulta = consulta.where(ExtractoLinea.importe < 0)
    if desde:
        consulta = consulta.where(ExtractoLinea.fecha >= desde)
    if hasta:
        consulta = consulta.where(ExtractoLinea.fecha <= hasta)
    return list(sesion.scalars(consulta))


def _nombre(v: Vencimiento) -> str:
    return v.factura.tercero.nombre if v.factura is not None and v.factura.tercero is not None else ""


def sugerir(sesion: Session, ejercicio: Ejercicio, periodo: tuple[date, date] | None = None) -> list[Sugerencia]:
    """Qué líneas parecen haber pagado qué vencimientos: el mismo motor de la conciliación de facturas, ahora sobre lo pendiente."""
    pendientes = vencimientos_a_pagar(sesion, ejercicio)
    if not pendientes:
        return []
    fechas = [v.fecha or date.min for v, _ in pendientes if v.fecha]
    desde, hasta = (min(fechas) - timedelta(days=MARGEN_DIAS), max(fechas) + timedelta(days=MARGEN_DIAS)) if fechas else (None, None)
    lineas = lineas_libres(sesion, ejercicio.empresa_id, desde, hasta)
    por_id_v, por_id_l = {str(v.id): v for v, _ in pendientes}, {str(l.id): l for l in lineas}
    alias = [(a.nombre, a.palabra) for a in sesion.scalars(select(PalabraConciliacion).where(PalabraConciliacion.empresa_id == ejercicio.empresa_id))]
    resultado = conciliar(
        [FacturaPorConciliar(str(v.id), _nombre(v), (v.factura.tercero.nif if v.factura and v.factura.tercero else "") or "", v.fecha or (v.factura.fecha_factura if v.factura else date.min), pte) for v, pte in pendientes],
        [LineaPorConciliar(str(l.id), l.fecha, f"{l.texto} {l.mas_datos}".strip(), l.importe, l.fecha_valor) for l in lineas], "R", alias)
    sugerencias = [Sugerencia([por_id_v[f.id] for f in e.facturas], [por_id_l[l.id] for l in e.lineas], e.regla, "") for e in resultado.emparejadas]
    for d in resultado.dudosas:
        if d.candidatas and d.motivo.startswith("Mismo nombre"):
            sugerencias.append(Sugerencia([por_id_v[d.factura.id]], [por_id_l[d.candidatas[0].id]], "importe_distinto", d.motivo))
    sugerencias += _acumulados(sesion, ejercicio, pendientes, sugerencias)
    if periodo is not None:  # sólo lo que se paga con líneas del trimestre de trabajo
        sugerencias = [s for s in sugerencias if all(periodo[0] <= l.fecha <= periodo[1] for l in s.lineas)]
    return sugerencias


def _es_acumulado(v: Vencimiento) -> str | None:
    """La palabra del proveedor acumulado («solred») si el vencimiento es de uno."""
    nombre = normalizar(_nombre(v))
    return next((p for p in PROVEEDORES_ACUMULADOS if p in nombre.split() or p in nombre), None)


def _acumulados(sesion: Session, ejercicio: Ejercicio, pendientes: list[tuple[Vencimiento, Decimal]], ya: list[Sugerencia]) -> list[Sugerencia]:
    """Para un proveedor que factura lo gastado con su tarjeta (Solred): los cargos de la tarjeta que suman **exactamente** la factura, con sus descuentos. Si suman justo, es casi seguro que son de esa factura."""
    resultado: list[Sugerencia] = []
    usadas = {l.id for s in ya for l in s.lineas}
    en_sugerencia = {v.id for s in ya for v in s.vencimientos}
    for v, pte in pendientes:
        palabra = _es_acumulado(v)
        if palabra is None or v.id in en_sugerencia:
            continue
        dia = v.fecha or (v.factura.fecha_factura if v.factura else None)
        if dia is None:
            continue
        tarjetas = {b for b in sesion.scalars(select(Extracto.banco_id).where(Extracto.empresa_id == ejercicio.empresa_id, Extracto.formato == "tarjeta"))}
        libres = [l for l in lineas_libres(sesion, ejercicio.empresa_id, dia - timedelta(days=DIAS_ACUMULADOS), dia + timedelta(days=DIAS_ACUMULADOS), con_abonos=True)
                  if l.id not in usadas and l.banco_id in tarjetas and (l.importe < 0 or palabra in normalizar(l.texto))]  # un abono sólo si lleva el nombre del proveedor («descuento extra solred»)
        candidatas = sorted(libres, key=lambda l: abs((l.fecha - dia).days))[:MAX_CANDIDATAS]
        objetivo = int(pte * 100)
        mejor: list[ExtractoLinea] | None = None
        mejor_clave = None
        for k in range(1, min(MAX_LINEAS_ACUMULADAS, len(candidatas)) + 1):
            for combo in combinations(candidatas, k):
                if sum(int(-l.importe * 100) for l in combo) == objetivo and any(l.importe < 0 for l in combo):
                    clave = sum(abs((l.fecha - dia).days) for l in combo)
                    if mejor_clave is None or clave < mejor_clave:
                        mejor, mejor_clave = list(combo), clave
            if mejor is not None:
                break  # la combinación con menos líneas
        if mejor is not None:
            usadas |= {l.id for l in mejor}
            cargos = sum(1 for l in mejor if l.importe < 0)
            motivo = f"{cargos} cargo(s) de la tarjeta" + (f" y {len(mejor) - cargos} descuento(s)" if len(mejor) > cargos else "") + f" suman exactamente {pte} €"
            resultado.append(Sugerencia([v], sorted(mejor, key=lambda l: (l.fecha, l.id)), "acumulado", motivo))
    return resultado


def _comprobar(ejercicio: Ejercicio, vencimientos: list[Vencimiento], lineas: list[ExtractoLinea], pendientes: dict[int, Decimal]) -> tuple[Decimal, Decimal]:
    if not vencimientos or not lineas:
        raise ErrorContable("Elija al menos un vencimiento y al menos una línea del extracto")
    if len({v.id for v in vencimientos}) != len(vencimientos) or len({l.id for l in lineas}) != len(lineas):
        raise ErrorContable("Hay un vencimiento o una línea repetidos")
    for v in vencimientos:
        if v.ejercicio_id != ejercicio.id or v.origen_tipo != "R" or v.importe >= 0:
            raise ErrorContable("De momento sólo se concilian vencimientos de facturas recibidas del ejercicio abierto")
    for l in lineas:
        if l.empresa_id != ejercicio.empresa_id:
            raise ErrorContable("Una línea del extracto es de otra empresa")
        if l.movimiento_id is not None:
            raise ErrorContable(f"El movimiento del {l.fecha:%d/%m/%Y} ({l.texto}) ya está conciliado")
    if all(l.importe >= 0 for l in lineas):
        raise ErrorContable(f"El movimiento del {lineas[0].fecha:%d/%m/%Y} ({lineas[0].texto}) es un ingreso, no un pago: un descuento sólo se puede juntar con algún pago")
    return sum((-pendientes[v.id] for v in vencimientos), CERO), sum((-l.importe for l in lineas), CERO)


def resumen(sesion: Session, vencimientos: list[Vencimiento], lineas: list[ExtractoLinea]) -> tuple[Decimal, Decimal, Decimal]:
    """(pendiente de los vencimientos, importe de las líneas, diferencia pendiente − líneas): positiva si se ha pagado menos de lo debido."""
    pte = sum((-pendiente(sesion, v) for v in vencimientos), CERO)
    pagado = sum((-l.importe for l in lineas), CERO)
    return pte, pagado, pte - pagado


def conciliar_pagos(
    sesion: Session, ejercicio: Ejercicio, vencimientos: list[Vencimiento], lineas: list[ExtractoLinea], *, modo: str = PARCIAL, cuenta_diferencia: str | None = None,
) -> ResultadoPagos:
    """Crea un movimiento de banco por línea que salda los vencimientos elegidos. No hace commit: si falla, quien llama hace rollback."""
    pendientes = {v.id: pendiente(sesion, v) for v in vencimientos}
    pte_total, pagado_total = _comprobar(ejercicio, vencimientos, lineas, pendientes)
    if pte_total <= 0:
        raise ErrorContable("Los vencimientos elegidos ya están saldados")
    diferencia = pte_total - pagado_total  # > 0: se paga menos de lo debido; < 0: se paga de más
    if diferencia != 0 and modo == PARCIAL and diferencia < 0:
        raise ErrorContable(f"Las líneas suman {-diferencia} € más de lo pendiente: elija «saldar con una diferencia a una cuenta» para llevar ese exceso a una cuenta")
    cuenta = None
    if diferencia != 0 and modo == CON_DIFERENCIA:
        cuenta = sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == (cuenta_diferencia or "").strip())).first()
        if cuenta is None:
            raise ErrorContable("Elija la subcuenta a la que llevar la diferencia (debe existir en el plan de cuentas)")
    if modo not in (PARCIAL, CON_DIFERENCIA):
        raise ErrorContable("Elija qué hacer con la diferencia")

    cola = [[v, -pendientes[v.id]] for v in sorted(vencimientos, key=lambda v: (v.fecha or date.max, v.id)) if pendientes[v.id] < 0]  # [vencimiento, lo que le falta por cubrir, en positivo]
    ordenadas = sorted(lineas, key=lambda l: (l.importe < 0, l.fecha, l.id))  # primero los abonos (descuentos), que suben lo que hay que cubrir con los pagos
    resultado = ResultadoPagos(diferencia=diferencia if cuenta is not None else CERO)
    cubiertos: dict[int, Decimal] = {}
    for i, linea in enumerate(ordenadas):
        pagos: list[LineaPago] = []
        if linea.importe > 0:  # un abono (descuento, devolución): resta de lo pagado, así que el vencimiento más antiguo vuelve a deber ese importe
            if not cola:
                raise ErrorContable("No hay ningún vencimiento al que aplicar el abono")
            pagos.append(LineaPago(linea.importe, cola[0][0]))
            cola[0][1] += linea.importe
            capacidad = CERO
        else:
            capacidad = -linea.importe
        if cuenta is not None and i == len(ordenadas) - 1:
            capacidad += diferencia  # el resto de lo debido (o menos, si se pagó de más) lo absorbe la diferencia de la última línea
        while capacidad > 0 and cola:
            v, falta = cola[0]
            parte = min(falta, capacidad)
            pagos.append(LineaPago(-parte, v))
            cubiertos[v.id] = cubiertos.get(v.id, CERO) + parte
            capacidad -= parte
            cola[0][1] -= parte
            if cola[0][1] == 0:
                cola.pop(0)
        if cuenta is not None and i == len(ordenadas) - 1 and diferencia != 0:
            pagos.append(LineaPago(diferencia, cuenta_directa=cuenta.codigo))  # + si se pagó menos de lo debido (entra a favor), − si se pagó de más
        if not pagos:
            raise ErrorContable(f"El movimiento del {linea.fecha:%d/%m/%Y} ({linea.texto}) no tiene a qué aplicarse: sobra tras saldar los vencimientos")
        r = registrar_movimiento(sesion, ejercicio, sesion.get(Banco, linea.banco_id), linea.fecha_valor or linea.fecha, pagos, texto=linea.texto)
        linea.movimiento_id = r.movimiento.id
        resultado.movimientos += 1
        resultado.avisos += r.advertencias
    for v in vencimientos:
        if pendientes[v.id] < 0:
            if pendiente(sesion, v) == 0:
                resultado.saldados += 1
            else:
                resultado.parciales += 1
    sesion.flush()
    return resultado


def pagar_con_banco(sesion: Session, ejercicio: Ejercicio, vencimientos: list[Vencimiento], banco: Banco, fecha: date | None = None) -> ResultadoPagos:
    """Paga lo que falta de cada vencimiento con ese banco o cuenta de socio, sin línea de extracto (lo que adelantó un socio con su dinero). Un movimiento por vencimiento, en `fecha` o, si no se da, el día del vencimiento."""
    if banco.empresa_id != ejercicio.empresa_id or banco.cuenta_id is None:
        raise ErrorContable("Elija un banco o una cuenta de socio de esta empresa que tenga subcuenta")
    if not vencimientos:
        raise ErrorContable("Elija al menos un vencimiento")
    resultado = ResultadoPagos()
    for v in sorted(vencimientos, key=lambda v: (v.fecha or date.max, v.id)):
        if v.ejercicio_id != ejercicio.id or v.origen_tipo != "R" or v.importe >= 0:
            raise ErrorContable("De momento sólo se pagan vencimientos de facturas recibidas del ejercicio abierto")
        pte = pendiente(sesion, v)
        if pte >= 0:
            raise ErrorContable(f"El vencimiento de {_nombre(v)} ya está saldado")
        dia = fecha or v.fecha or (v.factura.fecha_factura if v.factura else None)
        if dia is None:
            raise ErrorContable(f"Falta la fecha del pago de {_nombre(v)}")
        r = registrar_movimiento(sesion, ejercicio, banco, dia, [LineaPago(pte, v)])
        resultado.movimientos += 1
        resultado.saldados += 1
        resultado.avisos += r.advertencias
    sesion.flush()
    return resultado


@dataclass
class Enlaces:
    pares: list[tuple[ExtractoLinea, MovimientoBanco]] = field(default_factory=list)
    ambiguos: int = 0  # líneas que podrían ser de varios movimientos (o al revés): se dejan sin enlazar


def enlazables(sesion: Session, empresa_id: int, periodo: tuple[date, date] | None = None) -> Enlaces:
    """Líneas libres del extracto que ya están contabilizadas por un movimiento de banco sin enlazar (migrado del programa anterior, hecho a mano…): mismo banco, mismo importe y mismo día.

    Sólo se enlaza cuando la pareja es única de los dos lados; si una línea encaja con varios movimientos (o un movimiento con varias líneas) se deja y se cuenta como ambigua.
    """
    enlazados = select(ExtractoLinea.movimiento_id).where(ExtractoLinea.movimiento_id.is_not(None))
    movimientos = list(sesion.scalars(select(MovimientoBanco).join(Banco, Banco.id == MovimientoBanco.banco_id).where(Banco.empresa_id == empresa_id, MovimientoBanco.id.not_in(enlazados))))
    por_clave: dict[tuple, list[MovimientoBanco]] = {}
    for m in movimientos:
        if m.pagos:
            por_clave.setdefault((m.banco_id, sum((p.importe for p in m.pagos), CERO), m.fecha), []).append(m)
    candidatas: dict[int, list[MovimientoBanco]] = {}
    de_cada_movimiento: dict[int, list[ExtractoLinea]] = {}
    lineas = lineas_libres(sesion, empresa_id, periodo[0] if periodo else None, periodo[1] if periodo else None, con_abonos=True)  # con `periodo`, sólo las líneas de ese trimestre
    for l in lineas:
        vistos: dict[int, MovimientoBanco] = {}
        for dia in {l.fecha, l.fecha_valor} - {None}:
            for m in por_clave.get((l.banco_id, l.importe, dia), []):
                vistos[m.id] = m
        if vistos:
            candidatas[l.id] = list(vistos.values())
            for m in vistos.values():
                de_cada_movimiento.setdefault(m.id, []).append(l)
    resultado = Enlaces()
    for l in lineas:
        cand = candidatas.get(l.id)
        if not cand:
            continue
        if len(cand) == 1 and len(de_cada_movimiento[cand[0].id]) == 1:
            resultado.pares.append((l, cand[0]))
        else:
            resultado.ambiguos += 1
    return resultado


def enlazar(sesion: Session, empresa_id: int, periodo: tuple[date, date] | None = None) -> Enlaces:
    """Enlaza las parejas únicas de `enlazables`: no crea ni cambia ningún asiento, sólo dice que esa línea es ese movimiento. No hace commit."""
    e = enlazables(sesion, empresa_id, periodo)
    for linea, movimiento in e.pares:
        linea.movimiento_id = movimiento.id
    sesion.flush()
    return e
