"""Modelo 180 (resumen anual de retenciones por arrendamientos de inmuebles urbanos): cálculo del ejercicio desde los libros.

Es la suma de los cuatro 115 del año (`modelo115.calcular_115`, con la misma regla de base y retención), agrupada por arrendador: una percepción por arrendador, con su NIF, la renta anual sin IVA, el
porcentaje (el último del año), la retención y los datos del inmueble que salen de su ficha de proveedor (situación, referencia catastral y dirección).
Un arrendador con varios inmuebles necesita una cuenta de proveedor por inmueble: el programa no puede repartir la renta entre ellos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Tercero
from conta_pridalac.ficheros_aeat.fichero180 import Inmueble180
from conta_pridalac.servicios.modelo115 import CERO, calcular_115


@dataclass
class Arrendador180:
    cuenta: str
    nombre: str
    nif: str | None
    provincia: str | None  # del domicilio del arrendador
    inmueble: Inmueble180 = field(default_factory=Inmueble180)
    base: Decimal = CERO
    retencion: Decimal = CERO
    porcentaje: Decimal = CERO  # el último del año
    asientos: list[str] = field(default_factory=list)

    @property
    def faltan(self) -> list[str]:
        """Datos de la ficha sin los que la sede no admitiría el registro."""
        i = self.inmueble
        faltan = [n for n, v in (("NIF", self.nif), ("provincia del arrendador", self.provincia), ("situación del inmueble", i.situacion)) if not v]
        if i.situacion in ("1", "2", "3") and not i.catastro:
            faltan.append("referencia catastral")
        faltan += [n for n, v in (("nombre de la vía", i.via), ("municipio", i.municipio), ("provincia del inmueble", i.provincia), ("código postal del inmueble", i.codigo_postal)) if not v]
        return faltan

    @property
    def conviene(self) -> list[str]:
        """Datos que el diseño pide pero que no se exigen para generar el fichero."""
        return [n for n, v in (("tipo de vía", self.inmueble.tipo_via), ("código de municipio (INE)", self.inmueble.codigo_municipio)) if not v]


@dataclass
class Calculo180:
    anio: int
    arrendadores: list[Arrendador180] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def bases(self) -> Decimal:
        return sum((a.base for a in self.arrendadores), CERO)

    @property
    def retenciones(self) -> Decimal:
        return sum((a.retencion for a in self.arrendadores), CERO)


def inmueble_de(ficha: Tercero | None) -> Inmueble180:
    if ficha is None:
        return Inmueble180()
    return Inmueble180(
        situacion=ficha.inmueble_situacion or "", catastro=ficha.inmueble_catastro or "", tipo_via=ficha.inmueble_tipo_via or "", via=ficha.inmueble_via or "",
        tipo_numeracion=ficha.inmueble_tipo_numeracion or "", numero=ficha.inmueble_numero or "", calificador=ficha.inmueble_calificador or "", bloque=ficha.inmueble_bloque or "",
        portal=ficha.inmueble_portal or "", escalera=ficha.inmueble_escalera or "", planta=ficha.inmueble_planta or "", puerta=ficha.inmueble_puerta or "",
        complemento=ficha.inmueble_complemento or "", localidad=ficha.inmueble_localidad or "", municipio=ficha.inmueble_municipio or "",
        codigo_municipio=ficha.inmueble_codigo_municipio or "", provincia=ficha.inmueble_provincia or "", codigo_postal=ficha.inmueble_codigo_postal or "",
    )


def calcular_180(sesion: Session, ejercicio: Ejercicio) -> Calculo180:
    """Arrendadores del año con la renta y lo retenido; los datos de la ficha que falten se señalan en `faltan`."""
    c = Calculo180(ejercicio.anio)
    por_cuenta: dict[str, Arrendador180] = {}
    for trimestre in (1, 2, 3, 4):
        t = calcular_115(sesion, ejercicio, trimestre)
        c.avisos += [a for a in t.avisos if "sin NIF" not in a]
        for l in t.lineas:
            a = por_cuenta.get(l.cuenta)
            if a is None:
                cuenta = sesion.scalar(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id, Cuenta.codigo == l.cuenta))
                ficha = sesion.scalar(select(Tercero).where(Tercero.cuenta_id == cuenta.id)) if cuenta else None
                a = por_cuenta[l.cuenta] = Arrendador180(l.cuenta, l.perceptor, l.nif, getattr(ficha, "provincia_190", None), inmueble_de(ficha))
            a.base += l.base
            a.retencion += l.retencion
            a.porcentaje = l.porcentaje  # las líneas van por orden de fecha: queda el último
            a.asientos.append(l.asiento)
    c.arrendadores = sorted(por_cuenta.values(), key=lambda a: (a.nif or "", a.cuenta))
    for a in c.arrendadores:
        if a.faltan:
            c.avisos.append(f"{a.nombre}: faltan en su ficha {', '.join(a.faltan)} (hacen falta para el 180)")
    return c
