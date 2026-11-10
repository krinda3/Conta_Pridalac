"""Alta de una empresa nueva: vacía con el plan de cuentas del PGC, o cargada desde una copia de Gestión MGD.

Una empresa es un fichero `<slug>.sqlite` en la carpeta de datos. El alta nunca sustituye una empresa que ya exista y, si algo
falla a medias, no deja el fichero a medio hacer. Los dígitos de las subcuentas se eligen aquí, al crearla, y no se cambian.
"""
from __future__ import annotations

import re
import tempfile
import unicodedata
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from conta_pridalac.db.modelos import Cuenta, Ejercicio, Empresa, Parametro, TipoIva
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.pgc import TIPOS_DE_PLAN
from conta_pridalac.domain.pgc_cuentas import CUENTAS_3
from conta_pridalac.domain.pgc_esfl import CUENTAS_3_ESFL, CUENTAS_4_ESFL
from conta_pridalac.migracion.mgd import CopiaMgd, cargar_mgd, explorar_copia
from conta_pridalac.servicios.adjuntos import trasladar_a_almacen
from conta_pridalac.servicios import ubicacion_datos
from conta_pridalac.servicios.cuentas import validar_digitos
from conta_pridalac.servicios.empresa import MODELOS_POR_PLAN, validar_proteccion

if TYPE_CHECKING:  # el alta sólo necesita saber dónde están las carpetas de datos
    from conta_pridalac.web.config import Configuracion

# Cuentas de cuatro dígitos que el programa necesita además de las de tres del PGC: se llaman igual que las de tres si coinciden al rellenar con ceros.
CUENTAS_4 = {
    "4700": "Hacienda Pública, deudora por IVA",
    "4709": "Hacienda Pública, deudora por devolución de impuestos",
    "4730": "Hacienda Pública, retenciones y pagos a cuenta",
    "4750": "Hacienda Pública, acreedora por IVA",
    "4751": "Hacienda Pública, acreedora por retenciones practicadas",
}
# (texto, abreviatura, % de IVA, % de recargo de equivalencia)
TIPOS_DE_IVA = [("General 21%", "G", "21.00", "5.20"), ("Reducido 10%", "R", "10.00", "1.40"), ("Superreducido 4%", "S", "4.00", "0.50"), ("Exento / no sujeto", "E", "0.00", "0.00")]


@dataclass
class Alta:
    slug: str
    anio: int
    cuentas: int = 0
    asientos: int = 0
    justificantes: int = 0
    copiados: int = 0
    avisos: list[str] = field(default_factory=list)


def slug_de(nombre: str) -> str:
    """`Fundación Ñ & Co.` → `fundacion-n-co`: el nombre interno de la empresa (el del fichero y el de la dirección web)."""
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "empresa"


def cuenta_de(codigo: str, digitos: int) -> str:
    return codigo.ljust(digitos, "0")


def validar_tipo_plan(tipo_plan: str) -> str:
    if tipo_plan not in TIPOS_DE_PLAN:
        raise ErrorContable("El tipo de plan de cuentas no es válido")
    return tipo_plan


def plan_basico(digitos: int, tipo_plan: str = "pymes") -> dict[str, str]:
    """El plan de cuentas con el que nace una empresa: una subcuenta por cada cuenta de tres dígitos del plan, más las de cuatro que usan el IVA y las retenciones."""
    if tipo_plan == "esfl":
        plan = {cuenta_de(c, digitos): nombre for c, nombre in CUENTAS_3_ESFL.items()}
        plan.update({cuenta_de(c, digitos): CUENTAS_4_ESFL[c] for c in CUENTAS_4 if c in CUENTAS_4_ESFL})  # la 4730 no existe en este plan: sirve la 473
        return plan
    plan = {cuenta_de(c, digitos): nombre for c, nombre in CUENTAS_3.items()}
    plan.update({cuenta_de(c, digitos): nombre for c, nombre in CUENTAS_4.items()})
    return plan


def _comprobar(config: Configuracion, nombre: str, slug: str | None, anio: int | None) -> tuple[str, Path]:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorContable("Falta el nombre de la empresa")
    if anio is None or not 1990 <= int(anio) <= 2100:
        raise ErrorContable("El año del ejercicio no es válido")
    slug = slug_de(slug or nombre)
    destino = config.datos / f"{slug}.sqlite"
    if destino.exists():
        raise ErrorContable(f"Ya existe una empresa «{slug}»: cambie el nombre (el alta nunca sustituye una empresa)")
    return nombre, destino


def _nif(nif: str | None) -> str | None:
    limpio = re.sub(r"[\s.\-]", "", nif or "").upper()
    return limpio or None


def crear_empresa_nueva(config: Configuracion, *, nombre: str, nif: str | None, anio: int, digitos: int = 8, tipo_plan: str = "pymes", slug: str | None = None, proteccion: str | None = None) -> Alta:
    """Empresa vacía con el plan de cuentas del PGC, los parámetros del IVA y de las cuentas de resultado, y los tipos de IVA habituales."""
    digitos = validar_digitos(digitos)
    tipo_plan = validar_tipo_plan(tipo_plan)
    proteccion = validar_proteccion(proteccion)
    nombre, destino = _comprobar(config, nombre, slug, anio)
    anio = int(anio)
    config.datos.mkdir(parents=True, exist_ok=True)
    ubicacion_datos.marcar(config.raiz)
    motor = crear_motor(destino)
    sesion = None
    try:
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        empresa = Empresa(codigo=1, nombre=nombre, nif=_nif(nif), digitos_cuenta=digitos, tipo_plan=tipo_plan, proteccion=proteccion, modelos=",".join(MODELOS_POR_PLAN.get(tipo_plan, MODELOS_POR_PLAN["pymes"])))
        sesion.add_all([empresa, Ejercicio(anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, 31), empresa=empresa)])
        sesion.flush()
        cuentas = {}
        for codigo, texto in plan_basico(digitos, tipo_plan).items():
            cuentas[codigo] = Cuenta(empresa_id=empresa.id, codigo=codigo, nombre=texto[:128])
        sesion.add_all(cuentas.values())
        sesion.flush()
        for clave, cuenta in (("PYG", "129"), ("IVA_DEBE", "4700"), ("IVA_HABER", "4750"), ("PTE_APLIC", "555")):
            sesion.add(Parametro(empresa_id=empresa.id, clave=clave, valor=cuenta_de(cuenta, digitos)))
        for sentido, cuenta in (("R", "472"), ("E", "477")):
            for numero, (texto, abreviatura, iva, recargo) in enumerate(TIPOS_DE_IVA, start=1):
                sesion.add(TipoIva(empresa_id=empresa.id, sentido=sentido, numero=numero, texto=texto, abreviatura=abreviatura, pct_iva=Decimal(iva),
                                   cuenta_iva_id=cuentas[cuenta_de(cuenta, digitos)].id, pct_recargo=Decimal(recargo), por_defecto=numero == 1))
        sesion.commit()
        total = len(cuentas)
    except Exception:
        _descartar(motor, sesion, destino)
        raise
    sesion.close()
    motor.dispose()
    return Alta(slug=destino.stem, anio=anio, cuentas=total)


def _descartar(motor, sesion, destino: Path) -> None:
    """Quita lo creado a medias (sin tapar el error original si el fichero no se deja borrar)."""
    if sesion is not None:
        sesion.close()
    motor.dispose()
    try:
        destino.unlink(missing_ok=True)
    except OSError:
        pass


@contextmanager
def abrir_copia(origen: str | Path):
    """La carpeta con los `.dbf` de una copia de MGD: la propia carpeta, o el contenido de un `.zip` descomprimido en una carpeta temporal."""
    origen = Path(origen)
    if origen.is_dir():
        yield origen
        return
    if not origen.is_file() or not zipfile.is_zipfile(origen):
        raise ErrorContable(f"«{origen.name}» no es un .zip ni una carpeta")
    with tempfile.TemporaryDirectory(prefix="conta_mgd_") as tmp:
        with zipfile.ZipFile(origen) as z:
            z.extractall(tmp)
        carpeta = Path(tmp)
        interiores = [d for d in carpeta.iterdir() if d.is_dir()]
        if not any(f.name.lower() == "diario.dbf" for f in carpeta.iterdir()) and len(interiores) == 1:  # el zip trae una carpeta dentro
            carpeta = interiores[0]
        yield carpeta


def examinar_copia(carpeta: str | Path) -> CopiaMgd:
    try:
        return explorar_copia(carpeta)
    except ValueError as e:
        raise ErrorContable(str(e)) from None


def crear_desde_mgd(config: Configuracion, carpeta: str | Path, *, nombre: str, nif: str | None, anio: int, codigo: int = 1, digitos: int | None = None,
                    tipo_plan: str = "pymes", slug: str | None = None, proteccion: str | None = None) -> Alta:
    """Empresa nueva con los datos de una copia de MGD. Sin `digitos`, las subcuentas conservan los dígitos del plan de la copia."""
    copia = examinar_copia(carpeta)
    digitos = validar_digitos(digitos or copia.digitos_cuenta)
    tipo_plan = validar_tipo_plan(tipo_plan)
    proteccion = validar_proteccion(proteccion)
    nombre, destino = _comprobar(config, nombre, slug, anio)
    config.datos.mkdir(parents=True, exist_ok=True)
    motor = crear_motor(destino)
    sesion = None
    try:
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        r = cargar_mgd(sesion, carpeta, codigo_empresa=codigo, nombre_empresa=nombre, anio=int(anio), nif=_nif(nif), digitos_cuenta=digitos)
        sesion.get(Empresa, r.empresa_id).tipo_plan = tipo_plan
        sesion.get(Empresa, r.empresa_id).proteccion = proteccion
        sesion.get(Empresa, r.empresa_id).modelos = ",".join(MODELOS_POR_PLAN.get(tipo_plan, MODELOS_POR_PLAN["pymes"]))
        copiados = trasladar_a_almacen(sesion, config.almacen_de_adjuntos(), sesion.get(Ejercicio, r.ejercicio_id), carpeta)
        sesion.commit()
    except Exception:
        _descartar(motor, sesion, destino)
        raise
    sesion.close()
    motor.dispose()
    return Alta(slug=destino.stem, anio=int(anio), cuentas=r.cuentas, asientos=r.asientos, justificantes=r.adjuntos, copiados=copiados, avisos=list(r.avisos))
