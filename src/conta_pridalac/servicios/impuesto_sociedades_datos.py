"""Los datos del Impuesto sobre Sociedades (modelo 200) que no salen solos de la contabilidad, y las reglas que se aplican sobre ellos.

Lo que el usuario introduce de cada ejercicio vive en `ImpuestoSociedades.datos` (JSON, ver `DatosIS`); el histórico de bases imponibles negativas, en `BaseNegativa`.
De la contabilidad salen: el resultado contable, la cifra de negocios, los gastos no deducibles (cuentas marcadas en el parámetro `IS_NO_DEDUCIBLES`) y el gasto por el propio impuesto.

Reglas con el criterio acordado con Javier (02/11/2026):
- Las cuentas no deducibles (por defecto `678`: multas y sanciones) se suman a la base como corrección permanente, sin tocar la contabilidad.
- El tipo de gravamen lo propone la regla (microempresa: cifra de negocios del periodo anterior < 1 M€ y no patrimonial, ejercicios 2025 y siguientes) y el usuario puede **forzar el 25 %**.
- Las bases negativas se compensan con el límite del art. 26 LIS (70 %, 50 % o 25 % de la base previa según la cifra de negocios; siempre hasta 1 M€), de la más antigua a la más reciente.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import BaseNegativa, Ejercicio, ImpuestoSociedades, Parametro
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero200
from conta_pridalac.servicios import cierre as svc_cierre

CERO = Decimal("0.00")
MILLON = Decimal("1000000")
PARAM_NO_DEDUCIBLES = "IS_NO_DEDUCIBLES"
NO_DEDUCIBLES_POR_DEFECTO = "678"  # multas y sanciones (art. 15.c LIS)
PARAM_IMPUESTO = "IS_CUENTAS_IMPUESTO"
IMPUESTO_POR_DEFECTO = "630,633,638"  # el gasto por el propio impuesto: se suma a la base (no es deducible)
CASILLA_PATRIMONIAL, CASILLA_BASE_NEGATIVA, CASILLA_TIPO_REDUCIDO_1M, CASILLA_REDUCIDA_DIMENSION = 66, 27, 88, 6
# 2025 y siguientes (DT 44.ª LIS, Ley 7/2024): primeros 50.000 € de base y resto, para una cifra de negocios inferior a 1 M€
TIPOS_MICROEMPRESA = {2025: ("21", "22"), 2026: ("19", "21"), 2027: ("17", "20"), 2028: ("17", "20"), 2029: ("17", "20")}
TRAMO_MICRO = Decimal("50000")

CLAVES_RETENCIONES = (
    ("capital_mobiliario", "Retenciones por rendimientos del capital mobiliario"),
    ("arrendamientos", "Retenciones por arrendamientos de inmuebles urbanos"),
    ("capital_mobiliario_atribucion", "Retenciones por rendimientos del capital mobiliario por entidades en atribución de rentas"),
    ("arrendamientos_atribucion", "Retenciones por arrendamientos de inmuebles urbanos por entidades en atribución de rentas"),
    ("otros_atribucion", "Retenciones por otros conceptos diferentes por entidades en atribución de rentas"),
    ("iic", "Retenciones e ingresos a cuenta por participaciones en IIC"),
    ("premios", "Retenciones sobre los premios de determinadas loterías y apuestas"),
    ("otros", "Retenciones por otros conceptos no incluidos en las casillas anteriores"),
)


# ------------------------------------------------------------------------------------------------ los datos del ejercicio

@dataclass
class Correccion:
    concepto: str
    aumento: Decimal = CERO
    disminucion: Decimal = CERO
    permanente: bool = True  # permanente (no revierte) o temporaria
    automatica: bool = False  # la calcula el programa (cuentas no deducibles, gasto por el impuesto); no se guarda


@dataclass
class DatosIS:
    marcas: list[int] = field(default_factory=list)  # casillas de la página 1 marcadas (los «caracteres de la declaración»)
    forzar_25: bool = False  # no aplicar el tipo reducido aunque la regla lo proponga
    agricola: bool = False  # realiza actividades agrícolas y/o ganaderas
    personal_fijo: int = 0
    personal_no_fijo: int = 0
    firmante_cargo: str = ""
    firmante_nif: str = ""
    firmante_nombre: str = ""
    contacto_nombre: str = ""
    contacto_telefono: str = ""
    correcciones: list[Correccion] = field(default_factory=list)  # las introducidas a mano
    retenciones: dict[str, Decimal] = field(default_factory=dict)  # clave de `CLAVES_RETENCIONES` → importe
    incremento_perdida_beneficios_fiscales: Decimal = CERO
    intereses_demora: Decimal = CERO
    abono_deducciones_idi: Decimal = CERO
    compensar_bases_negativas: bool = True  # False = «no aplicar importes en el ejercicio»
    reinversion: list[dict] = field(default_factory=list)  # apartados opcionales: se rellenan solo si se usan
    donativos: list[dict] = field(default_factory=list)
    deducciones: list[dict] = field(default_factory=list)

    @property
    def patrimonial(self) -> bool:
        return CASILLA_PATRIMONIAL in self.marcas

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def de_json(cls, texto: str | None) -> DatosIS:
        crudo = json.loads(texto) if texto else {}
        datos = cls(**{k: v for k, v in crudo.items() if k in cls.__dataclass_fields__ and k not in ("correcciones", "retenciones")})
        datos.correcciones = [Correccion(c["concepto"], dinero(c.get("aumento")), dinero(c.get("disminucion")), bool(c.get("permanente", True))) for c in crudo.get("correcciones", [])]
        datos.retenciones = {k: dinero(v) for k, v in (crudo.get("retenciones") or {}).items()}
        for clave in ("incremento_perdida_beneficios_fiscales", "intereses_demora", "abono_deducciones_idi"):
            setattr(datos, clave, dinero(getattr(datos, clave)))
        return datos


def datos_del_ejercicio(sesion: Session, ejercicio: Ejercicio) -> DatosIS:
    fila = sesion.scalar(select(ImpuestoSociedades).where(ImpuestoSociedades.empresa_id == ejercicio.empresa_id, ImpuestoSociedades.anio == ejercicio.anio))
    return DatosIS.de_json(fila.datos if fila is not None else None)


def guardar_datos(sesion: Session, ejercicio: Ejercicio, datos: DatosIS) -> None:
    validar(datos)
    fila = sesion.scalar(select(ImpuestoSociedades).where(ImpuestoSociedades.empresa_id == ejercicio.empresa_id, ImpuestoSociedades.anio == ejercicio.anio))
    if fila is None:
        fila = ImpuestoSociedades(empresa_id=ejercicio.empresa_id, anio=ejercicio.anio)
        sesion.add(fila)
    fila.datos, fila.actualizado_en = datos.a_json(), datetime.now()
    sesion.flush()


def caracteres_disponibles() -> list[tuple[int, str]]:
    """Las casillas marcables de la página 1 del modelo 200 (los «caracteres de la declaración»), con su nombre, tal como las define el diseño de registro."""
    pagina = fichero200.DISENO["paginas"]["01000"]["campos"]
    return [(int(c["casilla"]), c["desc"].rsplit("[", 1)[0].strip()) for c in pagina if c["casilla"] and c["lon"] == 1 and c["tipo"] == "Num"]


def validar(datos: DatosIS) -> None:
    validas = {c for c, _ in caracteres_disponibles()}
    desconocidas = sorted(set(datos.marcas) - validas)
    if desconocidas:
        raise ErrorContable("Casillas de «caracteres de la declaración» que no existen en el modelo 200: " + ", ".join(f"{c:05d}" for c in desconocidas))
    if min(datos.personal_fijo, datos.personal_no_fijo) < 0:
        raise ErrorContable("El personal no puede ser negativo")
    for c in datos.correcciones:
        if not c.concepto.strip():
            raise ErrorContable("Cada corrección al resultado contable necesita un concepto")
        if c.aumento < 0 or c.disminucion < 0:
            raise ErrorContable(f"La corrección «{c.concepto}» tiene un importe negativo: los aumentos y las disminuciones van en positivo")
    desconocidas = sorted(set(datos.retenciones) - {k for k, _ in CLAVES_RETENCIONES})
    if desconocidas:
        raise ErrorContable("Tipos de retención desconocidos: " + ", ".join(desconocidas))


# ------------------------------------------------------------------------------------------------ lo que sale de la contabilidad

def _saldos(sesion: Session, ejercicio: Ejercicio) -> dict[str, Decimal]:
    return svc_cierre.saldos_del_ejercicio(sesion, ejercicio, excluir=(svc_cierre.SUBTIPO_CIERRE, svc_cierre.SUBTIPO_REGULARIZACION))


_DEFECTOS = {PARAM_NO_DEDUCIBLES: NO_DEDUCIBLES_POR_DEFECTO, PARAM_IMPUESTO: IMPUESTO_POR_DEFECTO}


def prefijos_guardados(sesion: Session, empresa_id: int, clave: str) -> tuple[str, ...]:
    """Las cuentas (o principios de cuenta) de un parámetro del IS: lo guardado o, si no hay nada, lo de por defecto."""
    valor = sesion.scalar(select(Parametro.valor).where(Parametro.empresa_id == empresa_id, Parametro.clave == clave))
    return tuple(p.strip() for p in (valor if valor and valor.strip() else _DEFECTOS[clave]).split(",") if p.strip())


def guardar_prefijos(sesion: Session, empresa_id: int, clave: str, texto: str) -> None:
    if clave not in (PARAM_NO_DEDUCIBLES, PARAM_IMPUESTO):
        raise ErrorContable(f"Parámetro desconocido: {clave}")
    limpio = ",".join(p.strip() for p in texto.split(",") if p.strip())
    if not all(p.isdigit() for p in limpio.split(",") if p):
        raise ErrorContable("Las cuentas se indican por su código o por el principio de su código (678, 67800005), separadas por comas")
    fila = sesion.scalar(select(Parametro).where(Parametro.empresa_id == empresa_id, Parametro.clave == clave))
    if fila is None:
        fila = Parametro(empresa_id=empresa_id, clave=clave)
        sesion.add(fila)
    fila.valor = limpio
    sesion.flush()


def resultado_contable(sesion: Session, ejercicio: Ejercicio) -> Decimal:
    """Ingresos menos gastos del ejercicio (grupos 7 y 6), antes de regularizar la cuenta de pérdidas y ganancias."""
    saldos = _saldos(sesion, ejercicio)
    prefijos = svc_cierre.prefijos_ingresos_y_gastos(sesion, ejercicio)
    return -sum((s for c, s in saldos.items() if c.startswith(prefijos)), CERO)


def cifra_de_negocios(sesion: Session, ejercicio: Ejercicio) -> Decimal:
    """Importe neto de la cifra de negocios (grupo 70, con devoluciones y rappels)."""
    return -sum((s for c, s in _saldos(sesion, ejercicio).items() if c.startswith("70")), CERO)


def correcciones_automaticas(sesion: Session, ejercicio: Ejercicio) -> list[Correccion]:
    """Lo que el programa suma o resta solo: los gastos no deducibles (permanentes) y el gasto por el propio impuesto."""
    saldos = _saldos(sesion, ejercicio)
    nombres = {c.codigo: c.nombre for c in _cuentas(sesion, ejercicio)}
    salida = []
    for prefijo, concepto, permanente in ((prefijos_guardados(sesion, ejercicio.empresa_id, PARAM_NO_DEDUCIBLES), "Gasto no deducible", True), (prefijos_guardados(sesion, ejercicio.empresa_id, PARAM_IMPUESTO), "Impuesto sobre Sociedades", True)):
        for cuenta, saldo in sorted(saldos.items()):
            if cuenta.startswith(prefijo) and saldo != 0:
                texto = f"{concepto}: {cuenta} {nombres.get(cuenta, '')}".strip()
                salida.append(Correccion(texto, aumento=saldo if saldo > 0 else CERO, disminucion=-saldo if saldo < 0 else CERO, permanente=permanente, automatica=True))
    return salida


def _cuentas(sesion: Session, ejercicio: Ejercicio):
    from conta_pridalac.db.modelos import Cuenta

    return sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == ejercicio.empresa_id))


def total_correcciones(correcciones: list[Correccion]) -> tuple[Decimal, Decimal]:
    return sum((c.aumento for c in correcciones), CERO), sum((c.disminucion for c in correcciones), CERO)


# ------------------------------------------------------------------------------------------------ tipo de gravamen

@dataclass
class TipoGravamen:
    campo: str  # el campo de 4 dígitos del modelo (casilla 00558): «2500» un tipo, «2122» dos
    marcar_00088: bool
    motivo: str

    @property
    def tipos(self) -> tuple[Decimal, Decimal | None]:
        return Decimal(self.campo[:2]), (Decimal(self.campo[2:]) if self.campo[2:] != "00" else None)


def tipo_de_gravamen(datos: DatosIS, ejercicio: Ejercicio, cifra_anterior: Decimal | None) -> TipoGravamen:
    """El tipo que corresponde por las reglas, salvo que el usuario fuerce el 25 %. `cifra_anterior`: cifra de negocios del periodo anterior (None si no hay)."""
    if datos.forzar_25:
        return TipoGravamen("2500", False, "Tipo general forzado por el usuario")
    if datos.patrimonial:
        return TipoGravamen("2500", False, "Entidad patrimonial: no aplica el tipo reducido de microempresas")
    if ejercicio.anio not in TIPOS_MICROEMPRESA:
        return TipoGravamen("2500", False, f"No hay regla de tipo reducido para el ejercicio {ejercicio.anio}")
    if cifra_anterior is None:
        return TipoGravamen("2500", False, "Sin cifra de negocios del periodo anterior: se aplica el tipo general")
    if cifra_anterior >= MILLON:
        return TipoGravamen("2500", False, "Cifra de negocios del periodo anterior de 1 M€ o más: tipo general (revisar si es de reducida dimensión)")
    primero, resto = TIPOS_MICROEMPRESA[ejercicio.anio]
    return TipoGravamen(primero + resto, True, f"Cifra de negocios del periodo anterior inferior a 1 M€ ({cifra_anterior:,.2f} €): {primero} % hasta 50.000 € y {resto} % el resto")


def cuota_integra(base: Decimal, tipo: TipoGravamen) -> Decimal:
    """La cuota íntegra de una base imponible positiva con el tipo (o los dos tipos por tramos) indicado."""
    if base <= 0:
        return CERO
    primero, segundo = tipo.tipos
    if segundo is None:
        return (base * primero / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    tramo = min(base, TRAMO_MICRO)
    return (tramo * primero / 100 + (base - tramo) * segundo / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)


# ------------------------------------------------------------------------------------------------ bases imponibles negativas

def bases_negativas(sesion: Session, empresa_id: int) -> list[BaseNegativa]:
    return list(sesion.scalars(select(BaseNegativa).where(BaseNegativa.empresa_id == empresa_id).order_by(BaseNegativa.anio)))


def guardar_base_negativa(sesion: Session, empresa_id: int, anio: int, base: Decimal, aplicado: Decimal = CERO, pendiente_manual: Decimal | None = None) -> BaseNegativa:
    base, aplicado = dinero(base), dinero(aplicado)
    if base < 0 or aplicado < 0 or (pendiente_manual is not None and dinero(pendiente_manual) < 0):
        raise ErrorContable("La base negativa, lo aplicado y lo pendiente se indican en positivo")
    if aplicado > base and pendiente_manual is None:
        raise ErrorContable(f"En {anio} se ha aplicado más de lo generado ({aplicado} > {base})")
    fila = sesion.scalar(select(BaseNegativa).where(BaseNegativa.empresa_id == empresa_id, BaseNegativa.anio == anio))
    if fila is None:
        fila = BaseNegativa(empresa_id=empresa_id, anio=anio)
        sesion.add(fila)
    fila.base, fila.aplicado = base, aplicado
    fila.pendiente_manual = dinero(pendiente_manual) if pendiente_manual is not None else None
    sesion.flush()
    return fila


def pendiente_hasta(sesion: Session, empresa_id: int, anio: int) -> Decimal:
    """Lo pendiente de compensar al empezar el ejercicio `anio`: las bases de los años anteriores."""
    return sum((b.pendiente for b in bases_negativas(sesion, empresa_id) if b.anio < anio), CERO)


def limite_de_compensacion(base_previa: Decimal, cifra_negocios: Decimal) -> Decimal:
    """Art. 26.1 LIS: el 70 % de la base previa (50 % si la cifra de negocios es de 20 M€ o más; 25 % si es de 60 M€ o más); en todo caso hasta 1 M€."""
    if base_previa <= 0:
        return CERO
    porcentaje = Decimal(25) if cifra_negocios >= 60 * MILLON else Decimal(50) if cifra_negocios >= 20 * MILLON else Decimal(70)
    return min(base_previa, max((base_previa * porcentaje / 100).quantize(Decimal("0.01"), ROUND_HALF_UP), min(MILLON, base_previa)))


def compensar(pendientes: list[tuple[int, Decimal]], limite: Decimal) -> list[tuple[int, Decimal]]:
    """Reparte lo que se puede compensar entre las bases pendientes, de la más antigua a la más reciente. Devuelve (año, importe aplicado) de las que se usan."""
    restante, usadas = limite, []
    for anio, pendiente in sorted(pendientes):
        if restante <= 0:
            break
        aplicar = min(pendiente, restante)
        if aplicar > 0:
            usadas.append((anio, aplicar))
            restante -= aplicar
    return usadas


# ------------------------------------------------------------------------------------------------ precálculo

@dataclass
class Precalculo:
    """De dónde sale la base imponible y la cuota íntegra, paso a paso. Es lo que enseña la pantalla y lo que usará el generador del fichero."""

    resultado: Decimal
    correcciones: list[Correccion]  # las automáticas y las del usuario
    aumentos: Decimal
    disminuciones: Decimal
    base_previa: Decimal  # resultado + aumentos − disminuciones, antes de compensar bases negativas
    cifra_anterior: Decimal | None
    limite_compensacion: Decimal
    compensaciones: list[tuple[int, Decimal]]  # (año de origen, importe compensado)
    compensacion: Decimal
    base_imponible: Decimal
    tipo: TipoGravamen
    cuota_integra: Decimal
    bases_pendientes: Decimal  # lo pendiente de compensar al empezar el ejercicio

    @property
    def base_negativa_generada(self) -> Decimal:
        return -self.base_imponible if self.base_imponible < 0 else CERO


def precalculo(sesion: Session, ejercicio: Ejercicio, datos: DatosIS | None = None, *, con_automaticas: bool = True) -> Precalculo:
    datos = datos if datos is not None else datos_del_ejercicio(sesion, ejercicio)
    resultado = resultado_contable(sesion, ejercicio)
    correcciones = (correcciones_automaticas(sesion, ejercicio) if con_automaticas else []) + datos.correcciones
    aumentos, disminuciones = total_correcciones(correcciones)
    base_previa = resultado + aumentos - disminuciones
    anterior = sesion.scalar(select(Ejercicio).where(Ejercicio.empresa_id == ejercicio.empresa_id, Ejercicio.anio == ejercicio.anio - 1))
    cifra_anterior = cifra_de_negocios(sesion, anterior) if anterior is not None else None
    pendientes = [(b.anio, b.pendiente) for b in bases_negativas(sesion, ejercicio.empresa_id) if b.anio < ejercicio.anio and b.pendiente > 0]
    limite = limite_de_compensacion(base_previa, cifra_anterior or CERO) if datos.compensar_bases_negativas else CERO
    compensaciones = compensar(pendientes, limite)
    compensacion = sum((c for _, c in compensaciones), CERO)
    base_imponible = base_previa - compensacion
    tipo = tipo_de_gravamen(datos, ejercicio, cifra_anterior)
    return Precalculo(resultado, correcciones, aumentos, disminuciones, base_previa, cifra_anterior, limite, compensaciones, compensacion, base_imponible, tipo, cuota_integra(base_imponible, tipo),
                      sum((p for _, p in pendientes), CERO))
