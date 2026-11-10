"""Lo que el 202 necesita del Impuesto sobre Sociedades ya presentado, leído de los ficheros `.200` y `.202` (del programa anterior o nuestros).

La base del pago fraccionado del 202 (art. 40.2 LIS) sale del último IS cuyo plazo de declaración estuviera vencido el primer día del periodo: la cuota íntegra [00562], menos las deducciones y bonificaciones
(la cuota líquida [00592]) y menos las retenciones e ingresos a cuenta [01766]. En un ejercicio natural el IS se presenta en julio, así que el 1P (abril) usa el IS de dos ejercicios atrás y el 2P y el 3P (octubre y
diciembre), el del ejercicio anterior. Se guardan como declaraciones presentadas (`modelo` «200» con `periodo` 0, y «202» con `periodo` 1 a 3), con sus casillas.

Las posiciones de las casillas del `.200` son las del diseño de registro del ejercicio 2025 (`DR200e25.xls`, hojas DP200014 y DP200014B), que valen también para 2023 y 2024; un ejercicio con otro diseño no se lee hasta cargar el suyo.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionPresentada, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero202

MODELO_IS, MODELO_202 = "200", "202"
CERO = Decimal("0")

# casilla → (página, posición, longitud, con signo) en el diseño del 200 de 2025; las mismas posiciones sirven para 2023 y 2024 (comprobado con los ficheros presentados de las dos empresas)
CASILLAS_200_2025 = {
    552: ("14000", 166, 17, True),  # base imponible
    562: ("14000", 646, 17, False),  # cuota íntegra
    592: ("14B00", 251, 17, False),  # cuota líquida
    1766: ("14B00", 541, 17, False),  # total de retenciones e ingresos a cuenta efectuados a la entidad
    601: ("14B00", 609, 17, False),  # 1er pago fraccionado
    603: ("14B00", 643, 17, False),  # 2º pago fraccionado
    605: ("14B00", 677, 17, False),  # 3er pago fraccionado
    611: ("14B00", 711, 17, True),  # cuota diferencial
    621: ("14B00", 1153, 17, True),  # resultado de la autoliquidación (positivo: a ingresar)
}
DISENOS_200 = {2023: CASILLAS_200_2025, 2024: CASILLAS_200_2025, 2025: CASILLAS_200_2025}


@dataclass
class IS:
    """Lo que se lee de un `.200`."""

    ejercicio: int
    nif: str
    nombre: str
    casillas: dict[int, Decimal] = field(default_factory=dict)

    @property
    def base_del_202(self) -> Decimal:
        """Cuota íntegra minorada en deducciones y bonificaciones (cuota líquida) y en las retenciones e ingresos a cuenta; nunca negativa."""
        liquida = self.casillas.get(592, self.casillas.get(562, CERO))
        return max(liquida - self.casillas.get(1766, CERO), CERO)


def _pagina(texto: str, etiqueta: str) -> str | None:
    inicio = texto.find(f"<T200{etiqueta}>")
    return None if inicio < 0 else texto[inicio : texto.index(f"</T200{etiqueta}>", inicio) + len(etiqueta) + 8]


def leer_200(texto: str) -> IS:
    cabecera = re.match(r"<T2000(\d{4})0A0000>", texto)
    if cabecera is None:
        raise ErrorContable("No es un fichero del modelo 200")
    ejercicio = int(cabecera.group(1))
    diseno = DISENOS_200.get(ejercicio)
    if diseno is None:
        raise ErrorContable(f"Todavía no se leen los ficheros del modelo 200 del ejercicio {ejercicio}: falta cargar su diseño de registro")
    identificacion = _pagina(texto, "01000") or ""
    nif, nombre = identificacion[13:22].strip(), identificacion[22:82].strip()
    casillas: dict[int, Decimal] = {}
    for casilla, (etiqueta, pos, lon, con_signo) in diseno.items():
        pagina = _pagina(texto, etiqueta)
        if pagina is None:
            continue
        bruto = pagina[pos - 1 : pos - 1 + lon]
        if not re.fullmatch(r"N?\d+", bruto):
            raise ErrorContable(f"La casilla {casilla:05d} del fichero no es un importe válido: «{bruto}»")
        importe = (Decimal(bruto.lstrip("N") or "0") / 100).quantize(Decimal("0.01"))
        casillas[casilla] = -importe if bruto.startswith("N") and con_signo else importe
    if not casillas.get(562) and not casillas.get(552):
        casillas.setdefault(562, CERO)
    return IS(ejercicio, nif, nombre, casillas)


def _json(casillas: dict[int, Decimal]) -> str:
    return json.dumps({str(k): str(v) for k, v in sorted(casillas.items())})


def _de_fichero(sesion: Session, texto: str, nombre_fichero: str, momento: date | None, *, comprobar_empresa: Empresa | None = None):
    """(empresa, modelo, ejercicio, periodo, casillas, resultado) de un fichero 200 o 202."""
    if texto.startswith("<T2000"):
        d = leer_200(texto)
        modelo, ejercicio, periodo, casillas, resultado = MODELO_IS, d.ejercicio, 0, d.casillas, d.casillas.get(621, CERO)
        nif = d.nif
    elif texto.startswith("<T2020"):
        d2 = fichero202.datos_del_fichero(texto)
        if d2["tipo"] not in fichero202.TIPOS_DECLARACION or not d2["nif"] or d2["inicio"] is None or not d2["tipo_gravamen"]:
            raise ErrorContable(f"«{nombre_fichero}» es un fichero 202 incompleto (sin fecha de inicio ni tipo de gravamen): no es una declaración presentada")
        modelo, ejercicio, periodo = MODELO_202, d2["ejercicio"], d2["periodo"]
        casillas = {1: d2["base"], 3: d2["a_ingresar"]}
        resultado, nif = d2["a_ingresar"], d2["nif"]
    else:
        raise ErrorContable(f"«{nombre_fichero}» no es un fichero de los modelos 200 o 202")
    empresa = sesion.scalars(select(Empresa).where(Empresa.nif == nif)).first()
    if empresa is None:
        raise ErrorContable(f"«{nombre_fichero}» es del NIF {nif}, que no es el de ninguna empresa de esta base")
    if comprobar_empresa is not None and empresa.id != comprobar_empresa.id:
        raise ErrorContable(f"«{nombre_fichero}» es de otra empresa ({nif})")
    return empresa, modelo, ejercicio, periodo, casillas, resultado


def importar(sesion: Session, texto: str, nombre_fichero: str = "", momento: date | None = None) -> tuple[str, DeclaracionPresentada]:
    """Guarda un `.200` o un `.202` ya presentado. Devuelve («nueva» | «ya estaba», declaración). Si ya hay otra distinta del mismo ejercicio y periodo, falla. No hace commit."""
    empresa, modelo, ejercicio, periodo, casillas, resultado = _de_fichero(sesion, texto, nombre_fichero, momento)
    existente = sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == modelo, DeclaracionPresentada.anio == ejercicio, DeclaracionPresentada.periodo == periodo,
        DeclaracionPresentada.tipo == 1)).first()
    if existente is not None:
        if json.loads(existente.casillas or "{}") != json.loads(_json(casillas)):
            raise ErrorContable(f"Ya consta un modelo {modelo} {ejercicio}{f' {periodo}P' if periodo else ''} de {empresa.nombre} con otras cifras: no se sobrescribe")
        return "ya estaba", existente
    d = DeclaracionPresentada(empresa_id=empresa.id, modelo=modelo, anio=ejercicio, periodo=periodo, tipo=1, fecha_emision=momento, resultado_liquidacion=resultado, resultado=resultado,
                              casillas=_json(casillas))
    sesion.add(d)
    sesion.flush()
    return "nueva", d


def importar_carpeta(sesion: Session, carpeta: Path) -> list[tuple[str, str]]:
    """Importa todos los `.200` y `.202` de una carpeta (los del programa anterior). Devuelve [(fichero, resultado o motivo por el que se salta)]. No hace commit."""
    resultados = []
    for ruta in sorted(Path(carpeta).glob("*")):
        if ruta.suffix.lower() not in (".200", ".202"):
            continue
        if ruta.stem.endswith("_Validacion"):  # copia idéntica que genera el programa anterior para validar el 200 antes de presentarlo
            resultados.append((ruta.name, "se salta: fichero de validación"))
            continue
        try:
            texto = ruta.read_bytes().decode("latin-1")
            estado, _ = importar(sesion, texto, ruta.name, date.fromtimestamp(ruta.stat().st_mtime))
            resultados.append((ruta.name, estado))
        except ErrorContable as e:
            resultados.append((ruta.name, f"se salta: {e}"))
    return resultados


def quitar_importada(sesion: Session, empresa_id: int, modelo: str, ejercicio: int, periodo: int) -> int:
    """Quita una declaración importada por error (la fila de `DeclaracionPresentada`, nunca una presentación nuestra). Devuelve cuántas quitó. No hace commit."""
    n = 0
    for d in sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == modelo, DeclaracionPresentada.anio == ejercicio, DeclaracionPresentada.periodo == periodo)):
        sesion.delete(d)
        n += 1
    return n


def is_de_referencia(sesion: Session, empresa_id: int, ejercicio: int, periodo: int) -> DeclaracionPresentada | None:
    """El IS en el que se apoya el pago fraccionado `periodo` (1 a 3) del `ejercicio`: el del ejercicio anterior si su plazo (25 de julio) ya había vencido el primer día del periodo (2P y 3P); si no, el anterior."""
    anio = ejercicio - 1 if periodo >= 2 else ejercicio - 2
    return sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == MODELO_IS, DeclaracionPresentada.anio == anio, DeclaracionPresentada.tipo == 1)).first()


def base_de(declaracion: DeclaracionPresentada) -> Decimal:
    casillas = {int(k): Decimal(v) for k, v in json.loads(declaracion.casillas or "{}").items()}
    return IS(declaracion.anio, "", "", casillas).base_del_202
