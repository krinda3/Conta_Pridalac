"""Bienes de inversión: ficha, cuadro de amortización, amortización contable y baja (pseudocódigo en docs/pseudocodigo/03).

Cada periodo amortizado genera un asiento automático (tipo 9, subtipo `Q`): gasto de dotación al debe y amortización
acumulada al haber. El periodo guarda el asiento (`asiento_id`) y su importe contable; sin importe = pendiente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import TIPO_AUTOMATICO, AmortizacionPeriodo, Asiento, BienInversion, Cuenta, Ejercicio
from conta_pridalac.domain.amortizacion import generar_cuadro
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.cuentas import cuenta_estandar, digitos_de
from conta_pridalac.servicios.extras import LineaManual, eliminar_extra, grabar_extra

CERO = Decimal("0.00")
SUBTIPO_AMORTIZACION = "Q"
SUBTIPO_BAJA = "B"


@dataclass
class ResultadoAmortizacion:
    amortizados: list[AmortizacionPeriodo] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)  # motivo por el que un bien no se amortizó

    @property
    def total(self) -> Decimal:
        return sum((p.importe_contable or CERO for p in self.amortizados), CERO)


# ------------------------------------------------------------------------------------------------ ficha y cuadro


def siguiente_codigo(sesion: Session, empresa_id: int) -> int:
    return (sesion.scalar(select(func.max(BienInversion.codigo)).where(BienInversion.empresa_id == empresa_id)) or 0) + 1


def _cuenta(sesion: Session, empresa_id: int, codigo: str, para: str) -> Cuenta:
    c = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo))
    if c is None:
        raise ErrorContable(f"No existe la cuenta {codigo} ({para})")
    return c


def _validar_ficha(bien: BienInversion) -> None:
    if bien.fecha_funcionamiento is None:
        raise ErrorContable("Falta la fecha de puesta en funcionamiento")
    if bien.precio_compra - bien.valor_residual <= 0:
        raise ErrorContable("El importe a amortizar (precio − valor residual) debe ser mayor que cero")
    if not (bien.periodos_vida or 0) > 0 and not (bien.coeficiente_pct or 0) > 0:
        raise ErrorContable("Indique la vida útil (periodos) o el porcentaje de amortización")
    for atributo, nombre in (("cuenta_inmovilizado_id", "inmovilizado"), ("cuenta_amortizacion_id", "amortización acumulada"), ("cuenta_dotacion_id", "dotación (gasto)")):
        if getattr(bien, atributo) is None:
            raise ErrorContable(f"Falta la cuenta de {nombre}")


def alta_bien(
    sesion: Session,
    empresa_id: int,
    *,
    descripcion: str,
    precio_compra: Decimal,
    fecha_funcionamiento: date,
    cuenta_inmovilizado: str,
    cuenta_amortizacion: str,
    cuenta_dotacion: str,
    periodos_vida: int | None = None,
    coeficiente_pct: Decimal | None = None,
    valor_residual: Decimal = CERO,
    meses_periodo: int = 12,
    **otros,
) -> BienInversion:
    """Da de alta un bien y genera su cuadro. `otros`: cualquier otro campo de la ficha (fecha_adquisicion, tercero_id…)."""
    bien = BienInversion(
        empresa_id=empresa_id, codigo=siguiente_codigo(sesion, empresa_id), descripcion=descripcion.strip(),
        precio_compra=Decimal(precio_compra), valor_residual=Decimal(valor_residual), fecha_funcionamiento=fecha_funcionamiento,
        periodos_vida=periodos_vida, coeficiente_pct=coeficiente_pct, meses_periodo=meses_periodo, **otros,
    )
    if not bien.descripcion:
        raise ErrorContable("Falta la descripción del bien")
    bien.cuenta_inmovilizado_id = _cuenta(sesion, empresa_id, cuenta_inmovilizado, "inmovilizado").id
    bien.cuenta_amortizacion_id = _cuenta(sesion, empresa_id, cuenta_amortizacion, "amortización acumulada").id
    bien.cuenta_dotacion_id = _cuenta(sesion, empresa_id, cuenta_dotacion, "dotación").id
    _validar_ficha(bien)
    sesion.add(bien)
    sesion.flush()
    regenerar_cuadro(sesion, bien)
    return bien


# Lo que, una vez amortizado algún periodo, ya no se puede cambiar sin deshacerlo antes (importes, fechas, vida y cuentas de los asientos).
CAMPOS_BLOQUEADOS_CON_AMORTIZACION = (
    "precio_compra", "valor_residual", "fecha_funcionamiento", "periodos_vida", "meses_periodo", "coeficiente_pct",
    "cuenta_inmovilizado", "cuenta_amortizacion", "cuenta_dotacion",
)
CUENTAS_DE_LA_FICHA = {"cuenta_inmovilizado": "inmovilizado", "cuenta_amortizacion": "amortización acumulada", "cuenta_dotacion": "dotación"}


def periodos_amortizados(bien: BienInversion) -> list[AmortizacionPeriodo]:
    return [a for a in bien.amortizaciones if a.importe_contable is not None]


def modificar_ficha(sesion: Session, bien: BienInversion, **cambios) -> BienInversion:
    """Cambia la ficha del bien y rehace su cuadro. Con periodos ya amortizados sólo se cambian los datos descriptivos.

    `cambios`: campos de `BienInversion`; las cuentas se dan por **código** (`cuenta_inmovilizado="21800000"`).
    """
    hechos = periodos_amortizados(bien)
    economicos_cambian = False
    for clave, valor in cambios.items():
        actual = getattr(bien, clave) if clave not in CUENTAS_DE_LA_FICHA else (getattr(bien, clave + "_id") and getattr(bien, clave).codigo)
        if clave in CAMPOS_BLOQUEADOS_CON_AMORTIZACION and actual != valor and (actual or valor):  # None y 0 son «sin valor»
            economicos_cambian = True
            if hechos:
                raise ErrorContable(f"No se puede cambiar «{clave.replace('_', ' ')}»: el bien tiene {len(hechos)} periodo(s) amortizado(s); deshágalos primero")
    originales = {c.key: getattr(bien, c.key) for c in BienInversion.__table__.columns if c.key != "id"}
    try:
        for clave, valor in cambios.items():
            if clave in CUENTAS_DE_LA_FICHA:
                setattr(bien, clave + "_id", _cuenta(sesion, bien.empresa_id, valor, CUENTAS_DE_LA_FICHA[clave]).id)
            else:
                setattr(bien, clave, valor)
        if not (bien.descripcion or "").strip():
            raise ErrorContable("Falta la descripción del bien")
        _validar_ficha(bien)
        if economicos_cambian:  # si sólo cambian datos descriptivos, el cuadro (incluidos sus ajustes manuales) no se toca
            regenerar_cuadro(sesion, bien)
        else:
            sesion.flush()
    except ErrorContable:
        for clave, valor in originales.items():  # la ficha vuelve a como estaba
            setattr(bien, clave, valor)
        raise
    return bien


def anular_baja(sesion: Session, bien: BienInversion) -> BienInversion:
    """Quita la fecha de baja (y rehace el cuadro completo). No si ya se contabilizó el asiento de baja."""
    if bien.fecha_baja is None:
        raise ErrorContable(f"«{bien.descripcion}» no está dado de baja")
    if bien.asiento_baja_id is not None:
        raise ErrorContable("Deshaga primero el asiento de baja")
    bien.fecha_baja, bien.causa_baja, bien.no_amortizar_en_baja = None, None, False
    regenerar_cuadro(sesion, bien)
    return bien


def borrar_bien(sesion: Session, bien: BienInversion) -> None:
    """Borra un bien sin amortizaciones contabilizadas ni asiento de baja."""
    if periodos_amortizados(bien):
        raise ErrorContable(f"No se puede borrar «{bien.descripcion}»: tiene {len(periodos_amortizados(bien))} periodo(s) amortizado(s)")
    if bien.asiento_baja_id is not None:
        raise ErrorContable(f"No se puede borrar «{bien.descripcion}»: tiene asiento de baja")
    sesion.delete(bien)
    sesion.flush()


def cuadro_del_bien(bien: BienInversion):
    """Cuadro teórico según la ficha (no toca la base de datos)."""
    _validar_ficha(bien)
    return generar_cuadro(
        bien.fecha_funcionamiento, bien.precio_compra, bien.valor_residual, bien.periodos_vida or 0, bien.meses_periodo,
        bien.coeficiente_pct or Decimal("0"), bien.fecha_baja,
    )


def regenerar_cuadro(sesion: Session, bien: BienInversion) -> list[AmortizacionPeriodo]:
    """Rehace las líneas sin amortizar a partir de la ficha. Las ya amortizadas no se tocan.

    Si cambió la ficha de modo que una línea ya amortizada deja de existir en el cuadro (otras fechas), se avisa con un
    error: primero hay que deshacer esa amortización.
    """
    teorico = cuadro_del_bien(bien)
    hechas = {a.desde: a for a in bien.amortizaciones if a.importe_contable is not None}
    huerfanas = [a for d, a in hechas.items() if d not in {p.desde for p in teorico}]
    if huerfanas:
        raise ErrorContable(
            "El cuadro nuevo no incluye periodos ya amortizados ("
            + ", ".join(f"{a.desde:%d/%m/%Y}" for a in huerfanas)
            + "); deshaga esas amortizaciones antes de cambiar la ficha"
        )
    for a in [a for a in bien.amortizaciones if a.importe_contable is None]:
        bien.amortizaciones.remove(a)
    sesion.flush()
    for p in teorico:
        if p.desde in hechas:
            hechas[p.desde].importe_previsto = p.previsto  # lo realizado se conserva; sólo se actualiza lo previsto
        else:
            bien.amortizaciones.append(AmortizacionPeriodo(anio=p.ejercicio, desde=p.desde, hasta=p.hasta, importe_previsto=p.previsto))
    sesion.flush()
    return list(bien.amortizaciones)


# ------------------------------------------------------------------------------------------------ amortizar


def _texto(bien: BienInversion) -> str:
    return f"AMORTIZACION DE {bien.descripcion}"[:64]


def amortizar_periodo(
    sesion: Session, ejercicio: Ejercicio, periodo: AmortizacionPeriodo, *, fecha: date | None = None
) -> AmortizacionPeriodo:
    """Contabiliza un periodo: asiento automático (Q) gasto/amortización acumulada. Fecha por defecto: fin del periodo."""
    bien = periodo.bien
    if periodo.importe_contable is not None:
        raise ErrorContable(f"El periodo {periodo.desde:%d/%m/%Y}–{periodo.hasta:%d/%m/%Y} de «{bien.descripcion}» ya está amortizado")
    if periodo.importe_previsto <= 0:
        raise ErrorContable("El importe previsto del periodo es cero: no hay nada que amortizar")
    _validar_ficha(bien)
    fecha = fecha or min(periodo.hasta, ejercicio.fecha_fin)
    importe = periodo.importe_previsto
    r = grabar_extra(
        sesion, ejercicio, fecha=fecha, texto=_texto(bien), tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_AMORTIZACION,
        lineas=[
            LineaManual(bien.cuenta_dotacion.codigo, "D", importe, _texto(bien)),
            LineaManual(bien.cuenta_amortizacion.codigo, "H", importe, _texto(bien)),
        ],
    )
    periodo.importe_contable = importe
    periodo.origen = "X"
    periodo.asiento_id = r.asiento.id
    sesion.flush()
    return periodo


def deshacer_amortizacion(sesion: Session, ejercicio: Ejercicio, periodo: AmortizacionPeriodo) -> None:
    """Borra el asiento de un periodo amortizado y lo deja pendiente."""
    if periodo.importe_contable is None:
        raise ErrorContable("El periodo no está amortizado")
    asiento = sesion.get(Asiento, periodo.asiento_id) if periodo.asiento_id else None
    if asiento is None:
        raise ErrorContable("El periodo no tiene asiento propio (importe fijado a mano): no se puede deshacer desde aquí")
    if asiento.ejercicio_id != ejercicio.id:
        raise ErrorContable("El asiento de esta amortización pertenece a otro ejercicio")
    periodo.importe_contable = None
    periodo.origen = None
    periodo.asiento_id = None
    sesion.flush()
    eliminar_extra(sesion, ejercicio, asiento)


def editar_periodo(sesion: Session, periodo: AmortizacionPeriodo, *, importe_previsto: Decimal, importe_contable: Decimal | None) -> AmortizacionPeriodo:
    """Fija a mano los importes de un periodo del cuadro (como permitía MGD). Un periodo con asiento propio no se toca: primero se deshace.
    `importe_contable` vacío lo deja pendiente; con importe, queda como amortizado «a mano», sin asiento."""
    if periodo.asiento_id:
        raise ErrorContable(f"El periodo {periodo.anio} tiene su asiento de amortización: deshágalo antes de cambiar sus importes")
    if importe_previsto < 0 or (importe_contable is not None and importe_contable < 0):
        raise ErrorContable("Los importes del cuadro no pueden ser negativos")
    periodo.importe_previsto = importe_previsto
    periodo.importe_contable = importe_contable
    periodo.origen = "M" if importe_contable is not None else None
    sesion.flush()
    return periodo


def periodos_pendientes(sesion: Session, ejercicio: Ejercicio, *, hasta: date | None = None) -> list[AmortizacionPeriodo]:
    """Periodos sin amortizar que acaban dentro del ejercicio (y no después de `hasta`), de bienes de la empresa."""
    tope = min(hasta or ejercicio.fecha_fin, ejercicio.fecha_fin)
    return list(
        sesion.scalars(
            select(AmortizacionPeriodo)
            .join(BienInversion)
            .where(
                BienInversion.empresa_id == ejercicio.empresa_id,
                AmortizacionPeriodo.importe_contable.is_(None),
                AmortizacionPeriodo.importe_previsto > 0,
                AmortizacionPeriodo.hasta >= ejercicio.fecha_inicio,
                AmortizacionPeriodo.hasta <= tope,
            )
            .order_by(BienInversion.codigo, AmortizacionPeriodo.desde)
        )
    )


def amortizar_ejercicio(sesion: Session, ejercicio: Ejercicio, *, hasta: date | None = None) -> ResultadoAmortizacion:
    """«Amortizar los bienes de inversión» del cierre: todos los periodos pendientes que acaban en el ejercicio."""
    resultado = ResultadoAmortizacion()
    for periodo in periodos_pendientes(sesion, ejercicio, hasta=hasta):
        bien = periodo.bien
        if bien.fecha_baja and bien.no_amortizar_en_baja and periodo.desde <= bien.fecha_baja <= periodo.hasta:
            resultado.omitidos.append(f"{bien.descripcion}: no se amortiza en el ejercicio de baja")
            continue
        resultado.amortizados.append(amortizar_periodo(sesion, ejercicio, periodo))
    return resultado


# ------------------------------------------------------------------------------------------------ baja


def dar_de_baja(sesion: Session, bien: BienInversion, fecha: date, causa: str = "", *, no_amortizar_en_baja: bool = False) -> BienInversion:
    """Fija la fecha de baja y acorta el cuadro (el último periodo se prorratea). No genera el asiento de baja.

    No se puede dar de baja con fecha anterior a algún periodo ya amortizado.
    """
    if bien.fecha_baja is not None:
        raise ErrorContable(f"«{bien.descripcion}» ya está dado de baja el {bien.fecha_baja:%d/%m/%Y}")
    if bien.fecha_funcionamiento and fecha < bien.fecha_funcionamiento:
        raise ErrorContable("La fecha de baja es anterior a la puesta en funcionamiento")
    posteriores = [a for a in bien.amortizaciones if a.importe_contable is not None and a.hasta > fecha]
    if posteriores:
        raise ErrorContable("Hay periodos ya amortizados posteriores a la fecha de baja; deshágalos primero")
    bien.fecha_baja, bien.causa_baja, bien.no_amortizar_en_baja = fecha, causa or None, no_amortizar_en_baja
    regenerar_cuadro(sesion, bien)
    return bien


# ------------------------------------------------------------------------------------------------ asiento de baja


@dataclass
class ResultadoBaja:
    asiento: Asiento
    amortizacion_acumulada: Decimal
    valor_neto: Decimal  # coste − amortización acumulada
    resultado: Decimal  # precio de venta − valor neto: pérdida (<0) o beneficio (>0)


def asiento_de_baja(
    sesion: Session,
    ejercicio: Ejercicio,
    bien: BienInversion,
    *,
    fecha: date | None = None,
    precio_venta: Decimal = CERO,
    cuenta_cobro: str | None = None,
    cuenta_perdidas: str | None = None,
    cuenta_beneficios: str | None = None,
) -> ResultadoBaja:
    """Asiento que retira el bien al darlo de baja (PGC): el coste sale del inmovilizado, se salda su amortización
    acumulada y la diferencia con el precio de venta va a pérdidas (671) o beneficios (771) del inmovilizado material.

    ```
    D  amortización acumulada   Σ amortizado hasta la baja
    D  cuenta de cobro          precio de venta (si lo hay: banco, deudores…)
    D  pérdidas (671)           si precio < valor neto
    H  beneficios (771)         si precio > valor neto
    H  inmovilizado             coste
    ```
    El IVA de una venta no se contabiliza aquí: va en la factura emitida (su base ha de ser el `precio_venta` cobrado
    a través de `cuenta_cobro`, o bien la factura lleva el ingreso y aquí se deja `precio_venta` a cero).
    Hace falta que el bien tenga fecha de baja y que estén amortizados todos los periodos anteriores a ella.
    """
    if bien.fecha_baja is None:
        raise ErrorContable(f"«{bien.descripcion}» no tiene fecha de baja: use dar_de_baja primero")
    if bien.asiento_baja_id is not None:
        raise ErrorContable(f"«{bien.descripcion}» ya tiene su asiento de baja")
    digitos = digitos_de(sesion, bien.empresa_id)
    cuenta_perdidas = cuenta_perdidas or cuenta_estandar("67100000", digitos)
    cuenta_beneficios = cuenta_beneficios or cuenta_estandar("77100000", digitos)
    precio_venta = Decimal(precio_venta)
    if precio_venta < 0:
        raise ErrorContable("El precio de venta no puede ser negativo")
    if precio_venta > 0 and not cuenta_cobro:
        raise ErrorContable("Indique la cuenta en la que se cobra la venta")
    fecha = fecha or bien.fecha_baja
    sin_amortizar = [
        a for a in bien.amortizaciones
        if a.importe_contable is None and a.importe_previsto > 0
        and not (bien.no_amortizar_en_baja and a.desde <= bien.fecha_baja <= a.hasta)
    ]
    if sin_amortizar:
        raise ErrorContable(
            f"Faltan por amortizar {len(sin_amortizar)} periodo(s) de «{bien.descripcion}» antes de darlo de baja (desde {sin_amortizar[0].desde:%d/%m/%Y})"
        )
    acumulada = sum((a.importe_contable or CERO for a in bien.amortizaciones), CERO)
    coste = bien.precio_compra
    neto = coste - acumulada
    if neto < 0:
        raise ErrorContable(f"La amortización acumulada ({acumulada}) supera el coste ({coste}) de «{bien.descripcion}»")
    resultado = precio_venta - neto
    texto = f"BAJA DE {bien.descripcion}"[:64]
    lineas = [LineaManual(bien.cuenta_inmovilizado.codigo, "H", coste, texto)]
    if acumulada > 0:
        lineas.append(LineaManual(bien.cuenta_amortizacion.codigo, "D", acumulada, texto))
    if precio_venta > 0:
        _cuenta(sesion, bien.empresa_id, cuenta_cobro, "cobro de la venta")
        lineas.append(LineaManual(cuenta_cobro, "D", precio_venta, texto))
    if resultado < 0:
        _cuenta(sesion, bien.empresa_id, cuenta_perdidas, "pérdidas del inmovilizado")
        lineas.append(LineaManual(cuenta_perdidas, "D", -resultado, texto))
    elif resultado > 0:
        _cuenta(sesion, bien.empresa_id, cuenta_beneficios, "beneficios del inmovilizado")
        lineas.append(LineaManual(cuenta_beneficios, "H", resultado, texto))
    r = grabar_extra(sesion, ejercicio, fecha=fecha, texto=texto, lineas=lineas, tipo=TIPO_AUTOMATICO, subtipo=SUBTIPO_BAJA)
    bien.asiento_baja_id = r.asiento.id
    sesion.flush()
    return ResultadoBaja(r.asiento, acumulada, neto, resultado)


def deshacer_asiento_de_baja(sesion: Session, ejercicio: Ejercicio, bien: BienInversion) -> None:
    """Borra el asiento de baja (el bien sigue con su fecha de baja)."""
    asiento = sesion.get(Asiento, bien.asiento_baja_id) if bien.asiento_baja_id else None
    if asiento is None:
        raise ErrorContable(f"«{bien.descripcion}» no tiene asiento de baja")
    bien.asiento_baja_id = None
    sesion.flush()
    eliminar_extra(sesion, ejercicio, asiento)
