"""Preparar un ensayo del trimestre: quitar de una **copia** de la base las facturas recibidas de un periodo y sus pagos, para volver a contabilizarlas desde la conciliación y comparar con lo que había.

Quita, por este orden: las declaraciones 303 presentadas de los trimestres afectados (si no, el bloqueo de trimestre presentado impide borrar), los pagos de esas facturas y los movimientos de banco que
se quedan sin pagos (con sus asientos), y por último las facturas con sus asientos, vencimientos y justificantes. No toca las facturas emitidas, los movimientos que no pagan estas facturas ni el extracto.
No hace commit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionLinea, DeclaracionPresentada, Ejercicio, Factura, MovimientoBanco, Pago, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.entorno import exigir_ensayo
from conta_pridalac.servicios.facturas import eliminar_factura
from conta_pridalac.servicios.tesoreria import eliminar_movimiento, regenerar_asiento


@dataclass
class ResumenQuitar:
    facturas: int = 0
    total: object = 0
    pagos: int = 0
    movimientos_borrados: int = 0
    movimientos_rehechos: int = 0
    declaraciones: int = 0


def _trimestres(desde: date, hasta: date) -> list[int]:
    return sorted({(m - 1) // 3 + 1 for m in range(desde.month, hasta.month + 1)})


def quitar_recibidas(sesion: Session, ejercicio: Ejercicio, desde: date, hasta: date) -> ResumenQuitar:
    """Quita las facturas recibidas con fecha contable entre `desde` y `hasta` (ambas incluidas) y todo lo que cuelga de ellas."""
    exigir_ensayo(sesion, ejercicio.empresa_id, "quitar facturas y pagos")
    if desde > hasta or desde.year != hasta.year:
        raise ErrorContable("El periodo debe estar dentro de un mismo año y empezar antes de acabar")
    facturas = list(sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == "R", Factura.fecha_contable >= desde, Factura.fecha_contable <= hasta)
                                   .order_by(Factura.numero)))
    resumen = ResumenQuitar(facturas=len(facturas), total=sum((f.total for f in facturas), 0))
    if not facturas:
        return resumen
    ids = [f.id for f in facturas]
    # 303 presentados de esos trimestres (y cualquier línea de declaración que cite estas facturas)
    declaradas = list(sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == ejercicio.empresa_id, DeclaracionPresentada.modelo == "303", DeclaracionPresentada.anio == ejercicio.anio,
        DeclaracionPresentada.periodo.in_(_trimestres(desde, hasta)))))
    for d in declaradas:
        sesion.execute(delete(DeclaracionLinea).where(DeclaracionLinea.declaracion_id == d.id))
        sesion.delete(d)
    sesion.execute(delete(DeclaracionLinea).where(DeclaracionLinea.factura_id.in_(ids)))
    resumen.declaraciones = len(declaradas)
    sesion.flush()
    # pagos de sus vencimientos y movimientos que se quedan vacíos
    vencimientos = list(sesion.scalars(select(Vencimiento.id).where(Vencimiento.factura_id.in_(ids))))
    pagos = list(sesion.scalars(select(Pago).where(Pago.vencimiento_id.in_(vencimientos)))) if vencimientos else []
    movimientos = {p.movimiento_id for p in pagos}
    resumen.pagos = len(pagos)
    for p in pagos:
        sesion.delete(p)
    sesion.flush()
    for mid in sorted(movimientos):
        m = sesion.get(MovimientoBanco, mid)
        sesion.refresh(m)
        if m.pagos:
            regenerar_asiento(sesion, ejercicio, m)
            resumen.movimientos_rehechos += 1
        else:
            resumen.movimientos_borrados += eliminar_movimiento(sesion, ejercicio, m)
    for f in facturas:
        eliminar_factura(sesion, ejercicio, f)
    sesion.flush()
    return resumen


# ---------------------------------------------------------------------------- comparar dos bases (la original y la del ensayo)


@dataclass
class FacturaComparada:
    nif: str
    nombre: str
    numero: str
    fecha_factura: str
    fecha_contable: str
    total: int  # céntimos
    gasto: str
    proveedor: str
    pagos: tuple  # ((fecha, subcuenta del banco, importe en céntimos), …) ordenados


@dataclass
class Comparacion:
    solo_original: list[FacturaComparada]
    solo_ensayo: list[FacturaComparada]
    distintas: list[tuple[FacturaComparada, FacturaComparada, list[str]]]
    iguales: int
    saldos: dict[str, tuple[int, int]]  # cuenta → (saldo original, saldo ensayo) sólo si difieren


def _nif(texto) -> str:
    return "".join(c for c in str(texto or "").upper() if c.isalnum())


def _leer_recibidas(con, desde: str, hasta: str) -> list[FacturaComparada]:
    pagos: dict[int, list] = {}
    for fid, fecha, cuenta, importe in con.execute(
        "select v.factura_id, m.fecha, c.codigo, p.importe from pago p join vencimiento v on v.id=p.vencimiento_id join movimiento_banco m on m.id=p.movimiento_id "
        "join banco b on b.id=m.banco_id left join cuenta c on c.id=b.cuenta_id where v.factura_id is not null"
    ):
        pagos.setdefault(fid, []).append((str(fecha), cuenta or "", importe))
    filas = []
    for fid, nif, nombre, numero, ffac, fcon, total, gasto, prov in con.execute(
        "select f.id, t.nif, t.nombre, f.numero_factura, f.fecha_factura, f.fecha_contable, f.total, cg.codigo, cp.codigo from factura f join ejercicio e on e.id=f.ejercicio_id "
        "left join tercero t on t.id=f.tercero_id left join cuenta cg on cg.id=f.cuenta_contrapartida_id left join cuenta cp on cp.id=f.cuenta_tercero_id "
        "where f.sentido='R' and f.fecha_contable between ? and ? order by f.fecha_contable, f.numero", (desde, hasta)
    ):
        filas.append(FacturaComparada(_nif(nif), nombre or "", (numero or "").strip().upper(), str(ffac), str(fcon), total, gasto or "", prov or "", tuple(sorted(pagos.get(fid, [])))))
    return filas


def _saldos(con, desde: str, hasta: str) -> dict[str, int]:
    return {c: s for c, s in con.execute(
        "select c.codigo, sum(a.debe - a.haber) from apunte a join asiento s on s.id=a.asiento_id join cuenta c on c.id=a.cuenta_id where s.fecha between ? and ? group by c.codigo", (desde, hasta))}


def comparar_recibidas(original, ensayo, desde: date, hasta: date) -> Comparacion:
    """Compara las facturas recibidas del periodo de dos bases (conexiones `sqlite3`): qué facturas están en una y no en otra, en qué difieren las que están en las dos (fechas, cuentas, pagos) y qué saldos de cuenta no coinciden."""
    d, h = desde.isoformat(), hasta.isoformat()
    a, b = _leer_recibidas(original, d, h), _leer_recibidas(ensayo, d, h)
    restantes = list(b)
    solo_original, distintas, iguales = [], [], 0
    for f in a:
        pareja = next((g for g in restantes if (g.nif, g.numero) == (f.nif, f.numero)), None) or next((g for g in restantes if (g.nif, g.total, g.fecha_factura) == (f.nif, f.total, f.fecha_factura)), None)
        if pareja is None:
            solo_original.append(f)
            continue
        restantes.remove(pareja)
        diferencias = [f"{campo}: {getattr(f, campo)} → {getattr(pareja, campo)}" for campo in ("numero", "fecha_factura", "fecha_contable", "total", "gasto", "proveedor", "pagos") if getattr(f, campo) != getattr(pareja, campo)]
        if diferencias:
            distintas.append((f, pareja, diferencias))
        else:
            iguales += 1
    sa, sb = _saldos(original, d, h), _saldos(ensayo, d, h)
    saldos = {c: (sa.get(c, 0), sb.get(c, 0)) for c in sorted(set(sa) | set(sb)) if sa.get(c, 0) != sb.get(c, 0)}
    return Comparacion(solo_original, restantes, distintas, iguales, saldos)
