"""Líneas del extracto que no tienen factura: tickets de la tarjeta, liquidación de la tarjeta, pagos del socio, impuestos…

Tras conciliar las facturas, en el extracto quedan líneas libres. Cada una se contabiliza de una de dos maneras:
- **a una cuenta**: un movimiento de banco contra una subcuenta directa (la del socio, la de la tarjeta pendiente de pago, Hacienda…);
- **ticket**: una factura sintética `TARJ-aammdd-n`, con el IVA al 21 % incluido en el importe, de un proveedor genérico (taxis, aparcamientos, manutención…), con su gasto, pagada por esa línea. Si la línea es un abono (un descuento, una devolución), la factura sale en negativo: un abono del ticket.

Qué hacer con cada línea lo dicen las **reglas**: las que el usuario guarda con «Recordar» (`ReglaLinea`) y las **aprendidas** de la contabilidad anterior (si «ADESLAS MADRID» ha ido siempre a la cuenta del socio, o
«SEITT» siempre al proveedor SEITTSA). Las reglas sólo proponen: nada se contabiliza sin que el usuario lo confirme.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, ExtractoLinea, Factura, MovimientoBanco, Pago, ReglaLinea, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.conciliacion import normalizar
from conta_pridalac.servicios.importar_facturas import FilaExcel, NIF_REAL, importar, normalizar_nif, planificar
from conta_pridalac.servicios import pagos_extracto
from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento

CERO = Decimal("0.00")
CUENTA, TICKET = "cuenta", "ticket"
MIN_VECES = 2  # una regla aprendida necesita verse al menos dos veces...
MIN_COHERENCIA = 0.8  # ...y llevar casi siempre al mismo sitio
PREFIJO_TICKET = "TARJ-"
IVA_DE_LOS_TICKETS = Decimal("21.00")  # el importe del ticket lleva IVA incluido: la base y la cuota se sacan de él


def patron(texto: str) -> str:
    """El concepto sin cifras ni signos: «SEITT AP41» y «SEITT R2» son los dos «seitt»."""
    return " ".join(p for p in normalizar(texto).split() if not any(c.isdigit() for c in p))[:120]


def _signo(importe: Decimal) -> int:
    return 1 if importe > 0 else -1


@dataclass
class Regla:
    tratamiento: str
    cuenta: Cuenta | None = None
    tercero: Tercero | None = None
    gasto: Cuenta | None = None
    origen: str = "manual"  # «manual» o «aprendida»
    veces: int = 0

    def describir(self) -> str:
        if self.tratamiento == CUENTA and self.cuenta is not None:
            return f"A la cuenta {self.cuenta.codigo} {self.cuenta.nombre}"
        if self.tratamiento == TICKET and self.tercero is not None:
            return f"Ticket de {self.tercero.nombre}"
        return "Sin tratamiento"


@dataclass
class Propuesta:
    linea: ExtractoLinea
    regla: Regla | None


@dataclass
class Preparadas:
    aplicables: list[Propuesta] = field(default_factory=list)
    omitidas: list[tuple[ExtractoLinea, str]] = field(default_factory=list)
    sin_regla: int = 0


@dataclass
class ResultadoLineas:
    movimientos: int = 0
    tickets: int = 0
    avisos: list[str] = field(default_factory=list)


def reglas_manuales(sesion: Session, empresa_id: int) -> dict[str, Regla]:
    resultado = {}
    for r in sesion.scalars(select(ReglaLinea).where(ReglaLinea.empresa_id == empresa_id)):
        resultado[r.patron] = Regla(r.tratamiento, r.cuenta, r.tercero, sesion.get(Cuenta, r.gasto_id) if r.gasto_id else None, "manual")
    return resultado


def reglas_aprendidas(sesion: Session, empresa_id: int) -> dict[tuple[str, int], Regla]:
    """Lo que la contabilidad anterior enseña: para cada (concepto, signo) visto, a qué cuenta o a qué proveedor genérico fue casi siempre."""
    cuentas: dict[tuple[str, int], Counter] = defaultdict(Counter)
    terceros: dict[tuple[str, int], Counter] = defaultdict(Counter)
    consulta = (select(MovimientoBanco.texto, MovimientoBanco.texto_automatico, Pago.importe, Pago.cuenta_directa_id, Pago.vencimiento_id, Pago.movimiento_contraparte_id)
                .join(Pago, Pago.movimiento_id == MovimientoBanco.id).join(Banco, Banco.id == MovimientoBanco.banco_id).where(Banco.empresa_id == empresa_id, Pago.importe != 0))
    ids_vtos = []
    pagos_vto = []
    for texto, automatico, importe, cuenta_id, vto_id, contraparte in sesion.execute(consulta):
        clave = (patron(texto), _signo(importe))
        if not clave[0] or automatico or contraparte is not None:
            continue
        if cuenta_id is not None and vto_id is None:  # (las cuentas del socio y de la tarjeta son «bancos» en Conta, pero aquí cuentan como cualquier otra cuenta)
            cuentas[clave][cuenta_id] += 1
        elif vto_id is not None:
            pagos_vto.append((clave, vto_id))
            ids_vtos.append(vto_id)
    if ids_vtos:
        from conta_pridalac.db.modelos import Vencimiento

        info = {v.id: v for v in sesion.scalars(select(Vencimiento).where(Vencimiento.id.in_(set(ids_vtos))))}
        for clave, vto_id in pagos_vto:
            f = info[vto_id].factura
            t = f.tercero if f is not None else None
            if t is None or f.sentido != "R":
                continue
            if (f.numero_factura or "").startswith(PREFIJO_TICKET) or not NIF_REAL.match(normalizar_nif(t.nif)):
                terceros[clave][t.id] += 1  # una factura de ticket o de un proveedor genérico (sin NIF de verdad)
    resultado: dict[tuple[str, int], Regla] = {}
    for clave, contador in cuentas.items():
        mejor, veces = contador.most_common(1)[0]
        if veces >= MIN_VECES and veces / sum(contador.values()) >= MIN_COHERENCIA:
            resultado[clave] = Regla(CUENTA, cuenta=sesion.get(Cuenta, mejor), origen="aprendida", veces=veces)
    for clave, contador in terceros.items():
        mejor, veces = contador.most_common(1)[0]
        if clave not in resultado and veces >= MIN_VECES and veces / sum(contador.values()) >= MIN_COHERENCIA:
            resultado[clave] = Regla(TICKET, tercero=sesion.get(Tercero, mejor), origen="aprendida", veces=veces)
    return resultado


def regla_de(linea: ExtractoLinea, manuales: dict[str, Regla], aprendidas: dict[tuple[str, int], Regla]) -> Regla | None:
    p = patron(linea.texto)
    if p in manuales:
        m = manuales[p]
        return m
    return aprendidas.get((p, _signo(linea.importe)))


def propuestas(sesion: Session, empresa_id: int, lineas: list[ExtractoLinea]) -> list[Propuesta]:
    manuales, aprendidas = reglas_manuales(sesion, empresa_id), reglas_aprendidas(sesion, empresa_id)
    return [Propuesta(l, regla_de(l, manuales, aprendidas)) for l in lineas]


def recordar(sesion: Session, empresa_id: int, linea: ExtractoLinea, tratamiento: str, *, cuenta: Cuenta | None = None, tercero: Tercero | None = None, gasto: Cuenta | None = None) -> None:
    """Guarda la regla «los conceptos como éste van así»; si ya había una para ese concepto, la cambia."""
    p = patron(linea.texto)
    if not p:
        raise ErrorContable("El concepto de esta línea no se puede recordar: no tiene letras")
    r = sesion.scalars(select(ReglaLinea).where(ReglaLinea.empresa_id == empresa_id, ReglaLinea.patron == p)).first()
    if r is None:
        r = ReglaLinea(empresa_id=empresa_id, patron=p, tratamiento=tratamiento)
        sesion.add(r)
    r.tratamiento, r.cuenta_id, r.tercero_id, r.gasto_id = tratamiento, cuenta.id if cuenta else None, tercero.id if tercero else None, gasto.id if gasto else None


def _siguiente_ticket(sesion: Session, ejercicio: Ejercicio, dia: date, usados: dict[str, int]) -> str:
    base = f"{PREFIJO_TICKET}{dia:%y%m%d}-"
    if base not in usados:
        existentes = [n for n in sesion.scalars(select(Factura.numero_factura).where(Factura.ejercicio_id == ejercicio.id, Factura.numero_factura.like(base + "%")))]
        usados[base] = max((int(n[len(base):]) for n in existentes if n[len(base):].isdigit()), default=0)
    usados[base] += 1
    return f"{base}{usados[base]}"


def _comprobar(linea: ExtractoLinea, regla: Regla) -> None:
    if linea.movimiento_id is not None:
        raise ErrorContable("Esta línea ya está contabilizada")
    if regla.tratamiento == CUENTA:
        if regla.cuenta is None:
            raise ErrorContable("Falta la subcuenta a la que llevar la línea")
        if linea.banco.cuenta_id == regla.cuenta.id:
            raise ErrorContable("La línea no puede ir a la cuenta de su propio banco")
    elif regla.tratamiento == TICKET:
        if regla.tercero is None:
            raise ErrorContable("Falta el proveedor del ticket")
        if linea.banco.cuenta is None:
            raise ErrorContable("El banco de la línea no tiene subcuenta")
    else:
        raise ErrorContable("Elija qué hacer con la línea")


def preparar(sesion: Session, ejercicio: Ejercicio, propuestas_: list[Propuesta]) -> Preparadas:
    resultado = Preparadas()
    for p in propuestas_:
        if p.regla is None:
            resultado.sin_regla += 1
            continue
        try:
            _comprobar(p.linea, p.regla)
            resultado.aplicables.append(p)
        except ErrorContable as e:
            resultado.omitidas.append((p.linea, str(e)))
    return resultado


def aplicar(sesion: Session, almacen, ejercicio: Ejercicio, aplicables: list[Propuesta]) -> ResultadoLineas:
    """Contabiliza las líneas con el tratamiento de su regla, todo o nada (no hace commit)."""
    if not aplicables:
        raise ErrorContable("No hay nada que contabilizar")
    resultado, usados = ResultadoLineas(), {}
    tickets: list[tuple[ExtractoLinea, FilaExcel]] = []
    for p in aplicables:  # primero se comprueba todo, para no dejar nada a medias
        _comprobar(p.linea, p.regla)
    for p in aplicables:
        l, r = p.linea, p.regla
        dia = l.fecha_valor or l.fecha
        if r.tratamiento == CUENTA:
            m = registrar_movimiento(sesion, ejercicio, l.banco, dia, [LineaPago(l.importe, cuenta_directa=r.cuenta.codigo)], texto=l.texto)
            l.movimiento_id = m.movimiento.id
            resultado.movimientos += 1
            resultado.avisos += m.advertencias
        else:
            total = -l.importe
            base = (total / (1 + IVA_DE_LOS_TICKETS / 100)).quantize(CERO)
            numero = _siguiente_ticket(sesion, ejercicio, l.fecha, usados)
            gasto = r.gasto or (sesion.get(Cuenta, r.tercero.cuenta_gasto_id) if r.tercero.cuenta_gasto_id else None)
            tickets.append((l, FilaExcel(fila=l.id, nombre=r.tercero.nombre, nif=r.tercero.nif or "", fecha_factura=l.fecha, fecha_contable=l.fecha, numero=numero, lineas=[(base, IVA_DE_LOS_TICKETS, total - base)], total=total,
                                         ruta=None, fecha_pago=dia, subcuenta=l.banco.cuenta.codigo, concepto=l.texto, tercero_id=r.tercero.id, cuenta_gasto_id=gasto.id if gasto else None)))
    if tickets:
        planes = planificar(sesion, ejercicio, "R", [f for _, f in tickets])
        malos = [f"{p.fila.concepto} {p.fila.numero}: " + ("; ".join(p.errores) if p.errores else p.detalle) for p in planes if not p.importable]
        if malos:
            raise ErrorContable("No se puede contabilizar:\n" + "\n".join(malos))
        importar(sesion, almacen, ejercicio, "R", planes, origen="líneas sin factura")
        for l, fila in tickets:
            factura = sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == "R", Factura.numero_factura == fila.numero)).one()
            from conta_pridalac.db.modelos import Vencimiento
            l.movimiento_id = sesion.scalar(select(Pago.movimiento_id).join(Vencimiento, Vencimiento.id == Pago.vencimiento_id).where(Vencimiento.factura_id == factura.id))
            resultado.tickets += 1
    sesion.flush()
    return resultado



def crear_factura(sesion: Session, almacen, ejercicio: Ejercicio, lineas: list[ExtractoLinea], tercero: Tercero, numero: str, fecha_factura: date, iva: Decimal = IVA_DE_LOS_TICKETS,
                  gasto: Cuenta | None = None) -> Factura:
    """Da de alta la factura recibida que pagan estas líneas del extracto (una o varias; un descuento o una devolución, en positivo, resta) y la deja pagada con ellas.

    El total de la factura es lo que suman las líneas y lleva el IVA incluido. No hace commit: si falla, quien llama hace rollback.
    """
    if not lineas:
        raise ErrorContable("Marque al menos una línea del extracto")
    if not (numero or "").strip():
        raise ErrorContable("Falta el número de la factura")
    for l in lineas:
        if l.movimiento_id is not None:
            raise ErrorContable(f"El movimiento del {l.fecha:%d/%m/%Y} ({l.texto}) ya está contabilizado")
        if l.banco.cuenta is None:
            raise ErrorContable(f"El banco {l.banco.nombre} no tiene subcuenta")
    total = sum((-l.importe for l in lineas), CERO)
    if total <= 0:
        raise ErrorContable("Las líneas marcadas suman cero o un ingreso: una factura recibida necesita un pago neto")
    base = (total / (1 + iva / 100)).quantize(CERO)
    gasto_id = gasto.id if gasto is not None else tercero.cuenta_gasto_id
    fila = FilaExcel(fila=lineas[0].id, nombre=tercero.nombre, nif=tercero.nif or "", fecha_factura=fecha_factura, fecha_contable=fecha_factura, numero=numero.strip(), lineas=[(base, iva, total - base)],
                     total=total, ruta=None, tercero_id=tercero.id, cuenta_gasto_id=gasto_id)
    planes = planificar(sesion, ejercicio, "R", [fila])
    if not planes[0].importable:
        raise ErrorContable("No se puede dar de alta la factura: " + ("; ".join(planes[0].errores) if planes[0].errores else planes[0].detalle))
    importar(sesion, almacen, ejercicio, "R", planes, origen="líneas sin factura")
    factura = sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == "R", Factura.numero_factura == numero.strip(), Factura.tercero_id == tercero.id)).one()
    vencimientos = list(sesion.scalars(select(Vencimiento).where(Vencimiento.factura_id == factura.id)))
    pagos_extracto.conciliar_pagos(sesion, ejercicio, vencimientos, lineas)
    return factura
