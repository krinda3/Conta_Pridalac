"""Modelo 347 (declaración anual de operaciones con terceras personas): cálculo del ejercicio desde las facturas.

Regla: por cada tercero (y clave: **A** adquisiciones = facturas recibidas, **B** entregas = facturas emitidas) se suma lo operado en el año con IVA incluido, trimestre a trimestre; se declara si el total anual
supera 3.005,06 € (umbral de la Orden EHA/3012/2008). El importe de una factura es su base más la cuota de IVA y el recargo, **sin descontar retenciones** de IRPF. Las rectificativas restan (importes negativos).
Se omiten los terceros marcados «No incluir en el 347» en su ficha y los que no tienen NIF (se avisa).
El trimestre sale de la fecha de la factura, y si no la tiene, de la fecha contable (`FECHA_DEL_TRIMESTRE`). Comprobado contra lo presentado con `tools/comparar_347.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio, Factura, Tercero
from conta_pridalac.ficheros_aeat.provincias import codigo_de_provincia

CERO = Decimal("0.00")
UMBRAL = Decimal("3005.06")
FECHA_DEL_TRIMESTRE = "contable"  # «contable»: la fecha contable (la misma que decide el trimestre del 303) · «factura»: la fecha de la factura (o la contable si falta)


@dataclass
class Operado347:
    clave: str  # A o B
    nombre: str
    nif: str | None
    provincia: str | None
    trimestres: list[Decimal] = field(default_factory=lambda: [CERO] * 4)
    facturas: list[tuple[str, Decimal]] = field(default_factory=list)  # (identificación de la factura, importe) para poder revisarlo

    @property
    def anual(self) -> Decimal:
        return sum(self.trimestres, CERO)

    @property
    def declarable(self) -> bool:
        return self.anual > UMBRAL


@dataclass
class Calculo347:
    anio: int
    declarados: list[Operado347] = field(default_factory=list)  # superan el umbral
    por_debajo: list[Operado347] = field(default_factory=list)  # no lo superan: no se declaran
    avisos: list[str] = field(default_factory=list)
    sin_nif: list[tuple[str, Decimal]] = field(default_factory=list)  # terceros sin NIF que superan el umbral: no se pueden declarar

    @property
    def total(self) -> Decimal:
        return sum((d.anual for d in self.declarados), CERO)


def _provincia(t: Tercero | None) -> str | None:
    """El código de provincia: los dos primeros dígitos del código postal o, si no hay, el nombre de la provincia de la ficha."""
    return codigo_de_provincia(t.codigo_postal, t.provincia) if t is not None else None


def calcular_347(sesion: Session, ejercicio: Ejercicio, *, fecha_del_trimestre: str | None = None) -> Calculo347:
    modo = fecha_del_trimestre or FECHA_DEL_TRIMESTRE
    c = Calculo347(ejercicio.anio)
    grupos: dict[tuple[str, str], Operado347] = {}
    sin_nif: dict[str, Decimal] = {}
    for f in sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id).order_by(Factura.fecha_contable, Factura.numero)):
        t = f.tercero
        if t is not None and t.no_incluir_347:
            continue
        importe = sum((i.base + i.cuota_iva + i.cuota_recargo for i in f.ivas), CERO)
        if not importe:
            continue
        fecha = f.fecha_contable if modo == "contable" else (f.fecha_factura or f.fecha_contable)
        if fecha.year != ejercicio.anio:  # facturas de otro año contabilizadas en éste: el trimestre sería de otro ejercicio
            fecha = f.fecha_contable
        clave = "A" if f.sentido == "R" else "B"
        nombre = t.nombre if t is not None else (f.cuenta_tercero.nombre if f.cuenta_tercero is not None else "(sin tercero)")
        nif = (t.nif or "").strip().upper() if t is not None else ""
        if not nif:
            sin_nif[nombre] = sin_nif.get(nombre, CERO) + importe
            continue
        g = grupos.setdefault((nif, clave), Operado347(clave, nombre, nif, _provincia(t)))
        g.trimestres[(fecha.month - 1) // 3] += importe
        g.facturas.append((f"{f.sentido} {f.numero}", importe))
    for g in sorted(grupos.values(), key=lambda g: (g.clave, g.nif)):
        (c.declarados if g.declarable else c.por_debajo).append(g)
    for nombre, total in sin_nif.items():
        if total > UMBRAL:
            c.sin_nif.append((nombre, total))
            c.avisos.append(f"{nombre}: opera {total} en el año pero no tiene NIF en su ficha: no se puede declarar")
    for g in c.declarados:
        if not g.provincia:
            c.avisos.append(f"{g.nombre}: no se sabe su provincia (en su ficha faltan el código postal o la provincia)")
    return c
