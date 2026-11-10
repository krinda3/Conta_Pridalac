"""Auditoría de integridad contable (Hito 1, punto 11 del plan).

`auditar(sesion, ejercicio, almacen=None)` devuelve una lista de `Hallazgo`. Vacía = sin problemas. Es de solo lectura y se puede lanzar a
demanda; será obligatoria (sin errores) antes de cerrar un ejercicio.

Gravedad:
- `ERROR`: la contabilidad es incorrecta o incoherente; hay que corregir antes de cerrar.
- `AVISO`: algo sospechoso o incompleto que conviene revisar (un justificante ausente, un saldo de signo raro…).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db import integridad
from conta_pridalac.db.modelos import (
    Adjunto,
    Apunte,
    Asiento,
    Banco,
    BienInversion,
    Cuenta,
    DeclaracionPresentada,
    Ejercicio,
    Factura,
    MovimientoBanco,
    Pago,
    PresentacionAeat,
    Vencimiento,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.facturas import asientos_de_factura, total_esperado
from conta_pridalac.domain.tesoreria import apuntes_de_movimiento, pendiente

ERROR, AVISO = "ERROR", "AVISO"
CERO = Decimal("0.00")


@dataclass(frozen=True)
class Hallazgo:
    codigo: str  # identificador estable de la comprobación
    gravedad: str
    mensaje: str
    referencia: str = ""  # a qué se refiere: "2.194", "factura R 23", "banco 5"…


def _lineas(asiento: Asiento) -> Counter:
    c: Counter = Counter()
    for ap in asiento.apuntes:
        c[ap.cuenta.codigo] += ap.debe - ap.haber
    return Counter({k: v for k, v in c.items() if v != 0})


# ---------------------------------------------------------------------------------------------- comprobaciones


def asientos_descuadrados(s: Session, ej: Ejercicio):
    for ident, dif in integridad.asientos_descuadrados(s, ej.id):
        yield Hallazgo("asiento_descuadrado", ERROR, f"El asiento {ident} no cuadra (diferencia {dif})", ident)


def apuntes_en_cuentas_de_grupo(s: Session, ej: Ejercicio):
    for apunte_id in integridad.apuntes_en_cuentas_de_grupo(s, ej.id):
        yield Hallazgo("apunte_en_cuenta_de_grupo", ERROR, "Apunte en una cuenta con menos dígitos que las subcuentas", f"apunte {apunte_id}")


def huecos_en_el_diario(s: Session, ej: Ejercicio):
    huecos = integridad.huecos_numeracion_diario(s, ej.id)
    if huecos:
        muestra = ", ".join(map(str, huecos[:8])) + ("…" if len(huecos) > 8 else "")
        yield Hallazgo("hueco_en_el_diario", AVISO, f"{len(huecos)} número(s) del libro diario sin asiento: {muestra}", "diario")


def asientos_fuera_del_ejercicio(s: Session, ej: Ejercicio):
    for a in s.scalars(select(Asiento).where(Asiento.ejercicio_id == ej.id)):
        if not (ej.fecha_inicio <= a.fecha <= ej.fecha_fin):
            yield Hallazgo("asiento_fuera_del_ejercicio", ERROR, f"El asiento {a.identificador} tiene fecha {a.fecha:%d/%m/%Y}, fuera del ejercicio", a.identificador)


def facturas_fuera_del_ejercicio(s: Session, ej: Ejercicio):
    for f in s.scalars(select(Factura).where(Factura.ejercicio_id == ej.id)):
        if not (ej.fecha_inicio <= f.fecha_contable <= ej.fecha_fin):
            yield Hallazgo("factura_fuera_del_ejercicio", ERROR, f"La factura {f.sentido} nº {f.numero} tiene fecha contable {f.fecha_contable:%d/%m/%Y}, fuera del ejercicio", f"{f.sentido} {f.numero}")


def facturas_y_sus_asientos(s: Session, ej: Ejercicio):
    """Cada factura tiene exactamente los asientos que se regenerarían de ella (y ninguno más)."""
    tipo_de = {"R": 2, "E": 1}
    existentes = {(a.tipo, a.numero, a.sub): a for a in s.scalars(select(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.tipo.in_((1, 2))))}
    esperados: set[tuple[int, int, int]] = set()
    for f in s.scalars(select(Factura).where(Factura.ejercicio_id == ej.id)):
        ref = f"{f.sentido} {f.numero}"
        try:
            grupos = asientos_de_factura(f)
        except ErrorContable as e:
            yield Hallazgo("factura_no_contabilizable", ERROR, f"La factura {ref} no se puede contabilizar: {e}", ref)
            continue
        for sub, lineas in enumerate(grupos):
            clave = (tipo_de[f.sentido], f.numero, sub)
            esperados.add(clave)
            real = existentes.get(clave)
            if real is None:
                if lineas:
                    yield Hallazgo("factura_sin_asiento", ERROR, f"La factura {ref} no tiene su asiento {clave[0]}.{clave[1]}", ref)
            elif _lineas(real) != lineas:
                yield Hallazgo("asiento_distinto_del_regenerado", ERROR, f"El asiento {real.identificador} no coincide con el que sale de la factura {ref}", real.identificador)
    for clave, a in existentes.items():
        if clave not in esperados:
            yield Hallazgo("asiento_sin_documento", AVISO, f"El asiento {a.identificador} no corresponde a ninguna factura", a.identificador)


def total_de_las_facturas(s: Session, ej: Ejercicio):
    for f in s.scalars(select(Factura).where(Factura.ejercicio_id == ej.id)):
        esperado = total_esperado(f)
        if esperado is not None and esperado != f.total:
            yield Hallazgo("total_incoherente", AVISO, f"El total de la factura {f.sentido} nº {f.numero} ({f.total}) ≠ base + IVA + recargo + ajustes ({esperado})", f"{f.sentido} {f.numero}")


def movimientos_y_sus_asientos(s: Session, ej: Ejercicio):
    existentes = {a.numero: a for a in s.scalars(select(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.tipo == 3))}
    vistos: set[int] = set()
    for m in s.scalars(select(MovimientoBanco).where(MovimientoBanco.ejercicio_id == ej.id)):
        try:
            esperado = apuntes_de_movimiento(s, m)
        except (ValueError, AttributeError) as e:
            yield Hallazgo("movimiento_no_contabilizable", ERROR, f"El movimiento nº {m.numero} no se puede contabilizar: {e}", f"mov {m.numero}")
            continue
        a = existentes.get(m.numero)
        vistos.add(m.numero)
        if esperado and a is None:
            yield Hallazgo("movimiento_sin_asiento", ERROR, f"El movimiento de banco nº {m.numero} no tiene asiento", f"mov {m.numero}")
        elif not esperado and a is not None:
            yield Hallazgo("asiento_de_movimiento_sobrante", ERROR, f"El movimiento nº {m.numero} no genera asiento y existe el 3.{m.numero}", f"mov {m.numero}")
        elif a is not None and _lineas(a) != esperado:
            yield Hallazgo("asiento_distinto_del_regenerado", ERROR, f"El asiento 3.{m.numero} no coincide con el que sale del movimiento de banco", f"3.{m.numero}")
    for numero, a in existentes.items():
        if numero not in vistos:
            yield Hallazgo("asiento_sin_documento", AVISO, f"El asiento {a.identificador} no corresponde a ningún movimiento de banco", a.identificador)


def _asientos_que_mueven_el_banco(s: Session, ej: Ejercicio, banco: Banco) -> list[tuple[str, Decimal]]:
    """Los asientos que tocan la cuenta del banco sin ser un movimiento de banco (un asiento manual con una línea del banco): (identificador, importe en el banco). Sin apertura, regularización ni cierre."""
    numeros = set(s.scalars(select(MovimientoBanco.numero).where(MovimientoBanco.banco_id == banco.id, MovimientoBanco.ejercicio_id == ej.id)))
    por_asiento: dict[str, Decimal] = defaultdict(Decimal)
    for tipo, numero, sub, subtipo, debe, haber in s.execute(
        select(Asiento.tipo, Asiento.numero, Asiento.sub, Asiento.subtipo, Apunte.debe, Apunte.haber).join(Apunte, Apunte.asiento_id == Asiento.id).where(Asiento.ejercicio_id == ej.id, Apunte.cuenta_id == banco.cuenta_id)
    ).all():
        if subtipo in ("A", "R", "Z") or (tipo == 3 and numero in numeros):
            continue
        por_asiento[f"{tipo}.{numero}" + (f"/{sub}" if sub else "")] += debe - haber
    return [(identificador, importe) for identificador, importe in por_asiento.items() if importe]


def saldo_de_los_bancos(s: Session, ej: Ejercicio):
    """Saldo contable de la cuenta del banco = saldo inicial + Σ movimientos (más lo que no pasa por tesorería)."""
    for banco in s.scalars(select(Banco).where(Banco.empresa_id == ej.empresa_id, Banco.clase == "B")):
        if banco.cuenta_id is None:
            yield Hallazgo("banco_sin_cuenta", ERROR, f"El banco «{banco.nombre}» no tiene cuenta contable", f"banco {banco.numero}")
            continue
        if banco.cuenta.codigo.startswith("551"):  # la cuenta con socios es una cuenta contable de siempre (no un banco con extracto): admite asientos manuales, como las regularizaciones
            continue
        movs = sum(
            (p.importe for m in s.scalars(select(MovimientoBanco).where(MovimientoBanco.banco_id == banco.id, MovimientoBanco.ejercicio_id == ej.id)) for p in m.pagos),
            CERO,
        )
        debe, haber = s.execute(
            select(func.coalesce(func.sum(Apunte.debe), 0), func.coalesce(func.sum(Apunte.haber), 0))
            .join(Asiento).where(
                Asiento.ejercicio_id == ej.id, Apunte.cuenta_id == banco.cuenta_id, func.coalesce(Asiento.subtipo, "") != "Z"
            )  # sin el asiento de cierre, que deja la cuenta a cero
        ).one()
        contable = Decimal(debe) - Decimal(haber)
        # un traspaso entre bancos de un solo asiento (el programa anterior) es un movimiento del banco que paga; el otro banco lo recibe como cuenta directa
        movs -= sum(
            (p.importe for p in s.scalars(select(Pago).join(MovimientoBanco, MovimientoBanco.id == Pago.movimiento_id).where(MovimientoBanco.ejercicio_id == ej.id, MovimientoBanco.banco_id != banco.id, Pago.cuenta_directa_id == banco.cuenta_id, Pago.movimiento_contraparte_id.is_(None)))),
            CERO,
        )
        # Saldo inicial del ejercicio: lo que el asiento de apertura pone en la cuenta del banco; si no hay apertura
        # (primer ejercicio cargado de otro programa), el saldo inicial de la ficha del banco.
        apertura = s.execute(
            select(func.sum(Apunte.debe), func.sum(Apunte.haber))
            .join(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.subtipo == "A", Apunte.cuenta_id == banco.cuenta_id)
        ).one()
        hay_apertura = s.scalar(select(func.count()).select_from(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.subtipo == "A"))
        inicial = (apertura[0] or CERO) - (apertura[1] or CERO) if hay_apertura else banco.saldo_inicial
        if contable != inicial + movs:
            ajenos = _asientos_que_mueven_el_banco(s, ej, banco)
            causa = ""
            if ajenos:  # lo más habitual: la parte del banco de un asiento manual, que no pasó por «Movimientos de banco»
                causa = f". Asientos que mueven la cuenta del banco sin ser movimientos de banco (suman {sum((i for _, i in ajenos), CERO)}): " + ", ".join(f"{ident} ({importe:+})" for ident, importe in ajenos[:6])
            yield Hallazgo("saldo_de_banco", ERROR, f"Banco «{banco.nombre}»: saldo contable {contable} ≠ saldo inicial {inicial} + movimientos {movs}{causa}", f"banco {banco.numero}")


def transferencias_entre_bancos(s: Session, ej: Ejercicio):
    for p in s.scalars(select(Pago).where(Pago.movimiento_contraparte_id.is_not(None))):
        espejo = p.movimiento_contraparte.pagos[0] if p.movimiento_contraparte.pagos else None
        ref = f"mov {p.movimiento.numero}"
        if espejo is None or espejo.movimiento_contraparte_id != p.movimiento_id:
            yield Hallazgo("transferencia_sin_espejo", ERROR, f"La transferencia del movimiento {p.movimiento.numero} no tiene movimiento espejo", ref)
        elif espejo.importe != -p.importe:
            yield Hallazgo("transferencia_importes", ERROR, f"La transferencia {p.movimiento.numero}↔{p.movimiento_contraparte.numero} tiene importes que no se anulan", ref)


def vencimientos_pagados_de_mas(s: Session, ej: Ejercicio):
    for v in s.scalars(select(Vencimiento).where(Vencimiento.ejercicio_id == ej.id)):
        pte = pendiente(s, v)
        if pte != 0 and (pte > 0) != (v.importe > 0):
            yield Hallazgo("vencimiento_pagado_de_mas", AVISO, f"El vencimiento de {v.origen_tipo} {v.origen_numero} está pagado de más (importe {v.importe}, pendiente {pte})", f"{v.origen_tipo} {v.origen_numero}")


def _adjuntos_del_ejercicio(s: Session, ej: Ejercicio) -> list[Adjunto]:
    """Adjuntos de las facturas, movimientos de banco y asientos del ejercicio."""
    return list(
        s.scalars(
            select(Adjunto).where(
                Adjunto.factura_id.in_(select(Factura.id).where(Factura.ejercicio_id == ej.id))
                | Adjunto.movimiento_banco_id.in_(select(MovimientoBanco.id).where(MovimientoBanco.ejercicio_id == ej.id))
                | Adjunto.asiento_id.in_(select(Asiento.id).where(Asiento.ejercicio_id == ej.id))
            )
        )
    )


def adjuntos_ausentes(s: Session, ej: Ejercicio):
    for a in (a for a in _adjuntos_del_ejercicio(s, ej) if a.sha256 is None):
        yield Hallazgo("justificante_ausente", AVISO, f"El justificante «{a.nombre}» está referenciado pero no está en disco", a.nombre)


def hoy() -> date:
    return date.today()


def amortizacion_del_ejercicio(s: Session, ej: Ejercicio):
    """La amortización contabilizada en el ejercicio en cada cuenta de amortización acumulada = la dotación del año que dice el cuadro de los bienes de esa cuenta.

    Sólo se compara lo que Conta lleva: la amortización anterior a la primera apertura la trajo el programa anterior, repartida en las cuentas como allí se llevaba, y no tiene por qué coincidir con el
    cuadro. En un ejercicio sin terminar la dotación suele hacerse al cierre: sólo se avisa si se ha contabilizado de más; terminado (o cerrado), cualquier diferencia es un aviso.
    """
    cuadro: dict[int, Decimal] = defaultdict(Decimal)
    for b in s.scalars(select(BienInversion).where(BienInversion.empresa_id == ej.empresa_id)):
        if b.cuenta_amortizacion_id:
            cuadro[b.cuenta_amortizacion_id] += sum((a.importe_previsto for a in b.amortizaciones if a.anio == ej.anio), CERO)  # la dotación prevista por el cuadro, no la ya contabilizada
    contabilizado: dict[int, Decimal] = defaultdict(Decimal)
    filas = s.execute(
        select(Apunte.cuenta_id, Apunte.haber, Apunte.debe).join(Asiento, Asiento.id == Apunte.asiento_id).join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .where(Asiento.ejercicio_id == ej.id, Cuenta.codigo.like("28%"), func.coalesce(Asiento.subtipo, "").notin_(("A", "R", "Z")))  # sin la apertura, la regularización ni el cierre
    ).all()
    for cuenta_id, haber, debe in filas:
        contabilizado[cuenta_id] += haber - debe
    terminado = ej.cerrado or hoy() > ej.fecha_fin
    for cuenta_id in sorted(set(cuadro) | set(contabilizado)):
        dotado, esperado = contabilizado.get(cuenta_id, CERO), cuadro.get(cuenta_id, CERO)
        if abs(dotado - esperado) <= Decimal("0.01") or (not terminado and dotado <= esperado):
            continue
        c = s.get(Cuenta, cuenta_id)
        yield Hallazgo("amortizacion_del_ejercicio", AVISO, f"Cuenta {c.codigo}: amortización contabilizada en {ej.anio} = {dotado}, dotación según el cuadro de los bienes = {esperado}", c.codigo)


def saldos_de_terceros_con_signo_raro(s: Session, ej: Ejercicio):
    """Clientes (430, 440) con saldo acreedor o proveedores y acreedores (400, 410) con saldo deudor."""
    # Se suma debe y haber por separado y se resta en Python: una resta dentro de SQL pierde el tipo `Dinero` y
    # devolvería céntimos enteros (58,85 € → 5885).
    filas = s.execute(
        select(Cuenta, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ej.id, func.coalesce(Asiento.subtipo, "") != "Z").group_by(Cuenta.id)  # sin el cierre
    ).all()
    for c, debe, haber in filas:
        saldo = (debe or CERO) - (haber or CERO)
        if c.codigo[:3] in ("430", "440") and saldo < 0:
            yield Hallazgo("saldo_con_signo_raro", AVISO, f"Cliente {c.codigo} «{c.nombre}» con saldo acreedor {saldo}", c.codigo)
        elif c.codigo[:3] in ("400", "410") and saldo > 0:
            yield Hallazgo("saldo_con_signo_raro", AVISO, f"Proveedor {c.codigo} «{c.nombre}» con saldo deudor {saldo}", c.codigo)


def registro_de_cambios_integro(s: Session, ej: Ejercicio):
    """La cadena de huellas del registro de cambios (`db/registro.py`) debe estar íntegra: si no, alguien ha tocado una anotación o la ha borrado."""
    from conta_pridalac.db.registro import verificar

    for problema in verificar(s):
        yield Hallazgo("registro_de_cambios_roto", ERROR, f"El registro de cambios no es íntegro: {problema}. Lo anotado a partir de ahí ya no es de fiar; conserve la base tal cual y compárela con una copia anterior.", "registro de cambios")


def liquidaciones_de_iva_desactualizadas(s: Session, ej: Ejercicio):
    """Una liquidación de IVA ya grabada debe coincidir con la que saldría hoy: si no, se contabilizaron facturas con fecha del
    periodo después de liquidar (o se cambió algo) y esas cuotas no se han declarado en ese periodo."""
    from conta_pridalac.servicios.iva import SUBTIPO_IVA, calcular_liquidacion, parametro, periodo_de

    from conta_pridalac.servicios.iva import coincide_con_lo_presentado, declaracion_de, resultado_del_asiento

    periodicidad = int(parametro(s, ej, "IVA_PERIODICIDAD", "4"))
    for a in s.scalars(select(Asiento).where(Asiento.ejercicio_id == ej.id, Asiento.subtipo == SUBTIPO_IVA)):
        presentada = declaracion_de(s, a)
        if presentada is not None:  # lo presentado manda: se compara con la declaración, no con lo que dicen hoy las cuentas
            if not coincide_con_lo_presentado(a, presentada):
                yield Hallazgo(
                    "liquidacion_distinta_de_la_presentada", AVISO,
                    f"La liquidación {a.identificador} ({a.concepto}) da {resultado_del_asiento(a)} y la declaración presentada del {presentada.periodo}T {presentada.anio} da {presentada.resultado_liquidacion} "
                    f"(tras compensar, {presentada.resultado})", a.identificador,
                )
            continue
        desde, hasta = periodo_de(a.fecha, periodicidad)
        guardada = {k: v for k, v in _lineas(a).items()}
        try:
            candidatas = [calcular_liquidacion(s, ej, desde, hasta, compensar=c) for c in (True, False)]
        except ErrorContable as e:
            yield Hallazgo("liquidacion_iva_no_calculable", AVISO, f"No se puede recalcular la liquidación {a.identificador}: {e}", a.identificador)
            continue
        if any(Counter({k: v for k, v in c.lineas.items() if v}) == guardada for c in candidatas):
            continue
        actual = candidatas[0].lineas
        difs = {k: actual.get(k, CERO) - guardada.get(k, CERO) for k in set(actual) | set(guardada)}
        difs = {k: v for k, v in difs.items() if v}
        detalle = "; ".join(f"{k}: {v:+}" for k, v in sorted(difs.items()))
        yield Hallazgo(
            "liquidacion_iva_desactualizada", AVISO,
            f"La liquidación de IVA {a.identificador} ({a.concepto}) no coincide con el saldo actual de las cuentas de IVA del periodo ({detalle})",
            a.identificador,
        )


# ---- Comprobaciones que necesitan el almacén de justificantes (sólo si se pasa `almacen` a `auditar`)


def justificantes_en_disco(s: Session, ej: Ejercicio, almacen):
    """Ficheros de los justificantes: ausentes del disco, alterados desde que se adjuntaron o sin justificante que los referencie."""
    from conta_pridalac.servicios.adjuntos import AdjuntoInvalido, sha256_de

    referenciados = set()
    for a in _adjuntos_del_ejercicio(s, ej):
        if a.sha256 is None:  # ya lo avisa adjuntos_ausentes
            continue
        try:
            ruta = almacen.ruta(a)
        except AdjuntoInvalido as e:
            yield Hallazgo("justificante_ausente", AVISO, f"El justificante «{a.nombre}» tiene una ruta no válida: {e}", a.nombre)
            continue
        if not ruta.is_file():
            yield Hallazgo("justificante_ausente", AVISO, f"El justificante «{a.nombre}» consta como adjuntado pero su fichero no está en el almacén", a.nombre)
            continue
        referenciados.add(ruta.resolve())
        if sha256_de(ruta) != a.sha256:
            yield Hallazgo("justificante_alterado", AVISO, f"El fichero del justificante «{a.nombre}» ha cambiado desde que se adjuntó", a.nombre)
    carpeta = almacen.raiz / f"{ej.empresa.codigo:03d}" / str(ej.anio)
    if carpeta.is_dir():
        todos = {a.ruta_relativa for a in s.scalars(select(Adjunto))}
        todos |= {d.pdf_ruta for d in s.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.pdf_ruta.is_not(None)))}  # PDF de las declaraciones presentadas
        for p in s.scalars(select(PresentacionAeat)):  # ficheros y respuestas de las presentaciones hechas con este programa
            todos |= {r for r in (p.fichero_ruta, p.respuesta_ruta) if r}
        for f in sorted(p for p in carpeta.rglob("*") if p.is_file()):
            if f.resolve() not in referenciados and f.relative_to(almacen.raiz).as_posix() not in todos:
                yield Hallazgo("fichero_huerfano", AVISO, f"El fichero {f.relative_to(almacen.raiz).as_posix()} está en el almacén y ningún documento lo referencia", f.name)


def gastos_sin_justificante(s: Session, ej: Ejercicio, almacen):
    """Facturas recibidas sin ningún justificante presente."""
    con_fichero = select(Adjunto.factura_id).where(Adjunto.factura_id.is_not(None), Adjunto.sha256.is_not(None))
    for f in s.scalars(select(Factura).where(Factura.ejercicio_id == ej.id, Factura.sentido == "R", Factura.id.not_in(con_fichero)).order_by(Factura.numero)):
        yield Hallazgo("gasto_sin_justificante", AVISO, f"La factura recibida {f.numero} ({f.fecha_contable:%d/%m/%Y}, {f.total}) no tiene justificante", f"R {f.numero}")


def huellas_del_registro_fuera_de_la_base(s: Session, ej: Ejercicio, almacen):
    """Las huellas del registro de cambios que constan fuera de la base (`servicios/huellas.py`) deben seguir existiendo en ella: si no, se ha reescrito el registro o se ha vuelto a una copia anterior sin dejar constancia."""
    from conta_pridalac.servicios.huellas import comprobar

    for problema in comprobar(s, almacen.raiz, ej.empresa.codigo):
        yield Hallazgo("huellas_externas_no_coinciden", ERROR, f"{problema}. Conserve la base y el fichero huellas_registro tal cual y compárelos con una copia de seguridad anterior.", "registro de cambios")


COMPROBACIONES_CON_ALMACEN: list[Callable[[Session, Ejercicio, object], object]] = [justificantes_en_disco, gastos_sin_justificante, huellas_del_registro_fuera_de_la_base]

COMPROBACIONES: list[Callable[[Session, Ejercicio], object]] = [
    asientos_descuadrados,
    apuntes_en_cuentas_de_grupo,
    huecos_en_el_diario,
    asientos_fuera_del_ejercicio,
    facturas_fuera_del_ejercicio,
    facturas_y_sus_asientos,
    total_de_las_facturas,
    movimientos_y_sus_asientos,
    saldo_de_los_bancos,
    transferencias_entre_bancos,
    vencimientos_pagados_de_mas,
    adjuntos_ausentes,
    amortizacion_del_ejercicio,
    saldos_de_terceros_con_signo_raro,
    liquidaciones_de_iva_desactualizadas,
    registro_de_cambios_integro,
]


def auditar(sesion: Session, ejercicio: Ejercicio, *, almacen=None, con_plazos: bool = False) -> list[Hallazgo]:
    """Ejecuta todas las comprobaciones. Orden: errores primero.

    Con `almacen` (un `AlmacenAdjuntos`) se comprueban además los ficheros de los justificantes y los gastos sin justificante. Con `con_plazos` se añade la vigilancia de los plazos de los modelos de la AEAT
    (`servicios/vigilancia.py`): no es contabilidad, así que el cierre del ejercicio no la pide.
    """
    hallazgos = [h for comprobacion in COMPROBACIONES for h in comprobacion(sesion, ejercicio)]
    if con_plazos:
        from conta_pridalac.servicios.vigilancia import plazos_de_modelos

        hallazgos += plazos_de_modelos(sesion, ejercicio)
    if almacen is not None:
        hallazgos += [h for comprobacion in COMPROBACIONES_CON_ALMACEN for h in comprobacion(sesion, ejercicio, almacen)]
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def hay_errores(hallazgos: list[Hallazgo]) -> bool:
    return any(h.gravedad == ERROR for h in hallazgos)
