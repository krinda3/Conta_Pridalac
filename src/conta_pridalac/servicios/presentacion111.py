"""Borrador del modelo 111, sus controles y su fichero (el mismo molde que el 303: `servicios/presentacion303.py`).

Se reutilizan de allí las piezas que valen para cualquier modelo: el registro de la presentación con el PDF de la sede (`registrar_presentacion`), el rechazo, el borrado de lo no presentado y la comprobación
del fichero. Lo propio del 111: el cálculo (`servicios/modelo111.py`), los controles y que su rectificación se llama **complementaria** (casilla «Declaración complementaria» + justificante de la anterior).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac import auditoria
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import BORRADOR, DESCARTADA, GENERADA, Apunte, Asiento, Cuenta, DeclaracionPresentada, Ejercicio, PresentacionAeat, PresentacionEvento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero111 import CODIFICACION, DISENO_SHA256, DISENO_VERSION, Declaracion111, generar
from conta_pridalac.servicios.modelo111 import SUBTIPOS_QUE_NO_SON_OPERACIONES, Calculo111, calcular_111
from conta_pridalac.servicios.modelo303 import periodo_de_fechas
from conta_pridalac.servicios.entorno import exigir_base_real
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion303 import (
    JUSTIFICANTE_VALIDO,
    NRC_VALIDO,
    _usuario,
    hoy,
    importe_del_nrc,
    presentada_del_periodo,
    ruta_del_fichero,
)

MODELO = "111"
TIPOS_DE_PRESENTACION = ("normal", "complementaria")
CERO = Decimal("0.00")


def tipo_de_declaracion(resultado: Decimal, *, domiciliar: bool) -> str:
    """N negativa / sin actividad (resultado cero) · U domiciliación · I ingreso (con NRC)."""
    if resultado <= 0:
        return "N"
    return "U" if domiciliar else "I"


def lo_anterior(sesion: Session, empresa_id: int, anio: int, periodo: int, tipo_presentacion: str):
    """Para una complementaria: (declaración que se complementa, su resultado a ingresar —casilla 30—). `(None, None)` si es normal o no hay nada presentado."""
    if tipo_presentacion == "normal":
        return None, None
    previa = presentada_del_periodo(sesion, empresa_id, anio, periodo, MODELO)
    if previa is None:
        return None, None
    casillas = json.loads(previa.casillas or "{}")
    return previa, Decimal(str(casillas["30"])) if "30" in casillas else previa.resultado


def controlar_111(
    sesion: Session, ejercicio: Ejercicio, periodo: int, calculo: Calculo111, *, tipo_presentacion: str = "normal", domiciliar: bool = True, iban: str | None = None,
    nrc: str | None = None, nrc_importe: Decimal | None = None,
) -> list[Hallazgo]:
    desde, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    hallazgos: list[Hallazgo] = []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    # 1. Periodo ya presentado: sólo se rectifica con una complementaria
    previa = presentada_del_periodo(sesion, ejercicio.empresa_id, ejercicio.anio, periodo, MODELO)
    if tipo_presentacion not in TIPOS_DE_PRESENTACION:
        hallazgo("tipo_de_presentacion_desconocido", ERROR, f"Tipo de presentación desconocido: {tipo_presentacion}")
    elif tipo_presentacion == "normal" and previa is not None:
        hallazgo("periodo_ya_presentado", ERROR, f"El {periodo}T {ejercicio.anio} del 111 ya está presentado: sólo se puede rectificar con una declaración complementaria", f"{periodo}T")
    elif tipo_presentacion != "normal":
        if previa is None:
            hallazgo("rectificativa_sin_presentada", ERROR, f"No hay un 111 del {periodo}T {ejercicio.anio} presentado que complementar", f"{periodo}T")
        elif not JUSTIFICANTE_VALIDO.fullmatch((previa.justificante or "").strip()):
            hallazgo("falta_justificante_anterior", ERROR, "La declaración que se complementa no tiene un nº de justificante de 13 dígitos: el fichero de una complementaria lo lleva", f"{periodo}T")
        if calculo[30] < 0:
            hallazgo("complementaria_con_menos_retenciones", ERROR, f"La complementaria sale con {calculo[30]}: ingresó más de lo que ahora corresponde. Eso no se corrige con una complementaria del 111 (es una solicitud de devolución de ingresos indebidos)", "30")

    # 2. Contabilidad del trimestre
    en_periodo = {a.identificador for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta))}
    for h in auditoria.asientos_descuadrados(sesion, ejercicio):
        if h.referencia in en_periodo:
            hallazgos.append(h)

    # 3. Lo que avisa el cálculo (retención no habitual, perceptor sin NIF…)
    for aviso in calculo.avisos:
        hallazgo("aviso_del_calculo", AVISO, aviso)

    # 4. Plazos y forma de pago
    p, dia = plazo(MODELO, ejercicio.anio, periodo), hoy()
    if tipo_presentacion == "normal" and dia > p.fin:
        hallazgo("presentacion_fuera_de_plazo", AVISO, f"El plazo de presentación terminó el {p.fin:%d/%m/%Y}: presentarlo ahora es extemporáneo y puede llevar recargo", f"{periodo}T")
    if calculo[30] > 0 and domiciliar:
        if not (iban or "").strip():
            hallazgo("domiciliacion_sin_iban", ERROR, "Para domiciliar el pago hace falta el IBAN de la empresa (ficha de la empresa)")
        if dia > p.fin_domiciliacion:
            hallazgo(
                "domiciliacion_fuera_de_plazo", ERROR if p.confirmado else AVISO,
                f"El plazo para domiciliar terminó el {p.fin_domiciliacion:%d/%m/%Y}{'' if p.confirmado else ' (fecha estimada)'}: elija pagar con NRC", f"{periodo}T",
            )
    if nrc and not NRC_VALIDO.fullmatch(nrc):
        hallazgo("nrc_no_valido", ERROR, "El NRC son 22 caracteres (letras mayúsculas y números)")
    elif calculo[30] > 0 and not domiciliar and not nrc:
        hallazgo("nrc_pendiente", AVISO, "Falta el NRC: se obtiene pagando en la sede de la AEAT («Pago mediante cargo en cuenta») con el importe exacto, y hay que tenerlo para presentar", f"{periodo}T")
    elif nrc and (calculo[30] <= 0 or domiciliar):
        hallazgo("nrc_sin_importe_a_ingresar", AVISO, "Se ha indicado un NRC pero este periodo no se paga con NRC", f"{periodo}T")
    elif nrc and nrc_importe is not None and nrc_importe != calculo[30]:
        hallazgo(
            "nrc_de_otro_importe", ERROR,
            f"El NRC se anotó cuando el resultado era {nrc_importe} y ahora es {calculo[30]}: un NRC sólo vale para el importe exacto con el que se pagó. Obtenga otro NRC o revise qué ha cambiado", f"{periodo}T",
        )
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def crear_borrador(
    sesion: Session, ejercicio: Ejercicio, periodo: int, *, tipo_presentacion: str = "normal", domiciliar: bool = True, nrc: str | None = None, usuario: str | None = None,
) -> tuple[PresentacionAeat, list[Hallazgo]]:
    """Calcula el 111 del trimestre y guarda un borrador con las casillas congeladas (sustituye al borrador anterior del mismo periodo)."""
    empresa = ejercicio.empresa
    previa, anterior_30 = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, tipo_presentacion)
    calculo = calcular_111(sesion, ejercicio, periodo, anterior_30=anterior_30)
    importe_nrc = importe_del_nrc(sesion, empresa.id, ejercicio.anio, periodo, nrc, calculo[30], MODELO)
    hallazgos = controlar_111(sesion, ejercicio, periodo, calculo, tipo_presentacion=tipo_presentacion, domiciliar=domiciliar, iban=empresa.iban, nrc=nrc, nrc_importe=importe_nrc)
    bloqueantes = [h for h in hallazgos if h.codigo in ("periodo_ya_presentado", "rectificativa_sin_presentada", "tipo_de_presentacion_desconocido")]
    if bloqueantes:  # lo que impide crear el borrador, no el primer error que salga
        raise ErrorContable(bloqueantes[0].mensaje)
    quien = usuario or _usuario()
    for antiguo in sesion.scalars(select(PresentacionAeat).where(
        PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ejercicio.anio, PresentacionAeat.periodo == f"{periodo}T",
        PresentacionAeat.estado.in_((BORRADOR, GENERADA)),
    )):
        if antiguo.estado == BORRADOR:
            sesion.delete(antiguo)
        else:  # un fichero ya generado se conserva con su historia: puede que se haya llevado a la sede
            antiguo.estado = DESCARTADA
            antiguo.eventos.append(PresentacionEvento(usuario=quien, evento="descartada", detalle="Sustituida por un borrador nuevo", momento=datetime.now()))
    p = PresentacionAeat(
        empresa_id=empresa.id, modelo=MODELO, anio=ejercicio.anio, periodo=f"{periodo}T", estado=BORRADOR, tipo_presentacion=tipo_presentacion,
        tipo_declaracion=tipo_de_declaracion(calculo[30], domiciliar=domiciliar), resultado=calculo[30], casillas=json.dumps({str(k): str(v) for k, v in sorted(calculo.casillas.items())}),
        domiciliar=domiciliar, nrc=(nrc or None), nrc_importe=importe_nrc, anterior_id=previa.id if isinstance(previa, PresentacionAeat) else None, creada_por=quien,
    )
    p.eventos.append(PresentacionEvento(usuario=quien, evento="creada", detalle=f"{len(calculo.lineas)} retención(es); resultado {calculo[30]}"))
    sesion.add(p)
    sesion.flush()
    return p, hallazgos


def generar_fichero(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, usuario: str | None = None) -> Path:
    """Genera el fichero del 111 de un borrador y lo guarda en el almacén (`<empresa>/<año>/aeat/`) con su huella y la versión del diseño. Vuelve a calcular y a controlar."""
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede volver a generar")
    empresa, periodo = ejercicio.empresa, int(presentacion.periodo[0])
    previa, anterior_30 = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, presentacion.tipo_presentacion)
    calculo = calcular_111(sesion, ejercicio, periodo, anterior_30=anterior_30)
    if {str(k): str(v) for k, v in sorted(calculo.casillas.items())} != json.loads(presentacion.casillas or "{}"):
        raise ErrorContable("Los asientos o lo presentado han cambiado desde que se creó el borrador: guarde el borrador de nuevo")
    hallazgos = controlar_111(
        sesion, ejercicio, periodo, calculo, tipo_presentacion=presentacion.tipo_presentacion, domiciliar=presentacion.domiciliar, iban=empresa.iban, nrc=presentacion.nrc,
        nrc_importe=presentacion.nrc_importe,
    )
    errores = [h.mensaje for h in hallazgos if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    tipo = tipo_de_declaracion(calculo[30], domiciliar=presentacion.domiciliar)
    declaracion = Declaracion111(
        nif=(empresa.nif or "").strip(), nombre=empresa.nombre[:60], ejercicio=ejercicio.anio, periodo=f"{periodo}T", tipo=tipo, casillas=dict(calculo.casillas),
        iban=(empresa.iban or "").replace(" ", "") if tipo == "U" else "", complementaria=previa is not None, justificante_anterior=(previa.justificante or "").strip() if previa is not None else "",
    )
    datos = generar(declaracion).encode(CODIFICACION)
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, "111", ejercicio.anio, presentacion.periodo, presentacion.tipo_presentacion, "111")
    ruta = carpeta / f"{presentacion.id}_{nombre}"
    ruta.write_bytes(datos)
    quien = usuario or _usuario()
    presentacion.estado = GENERADA
    presentacion.tipo_declaracion = tipo
    presentacion.diseno_version, presentacion.diseno_sha256 = DISENO_VERSION, DISENO_SHA256
    presentacion.fichero_nombre, presentacion.fichero_sha256 = nombre, hashlib.sha256(datos).hexdigest()
    presentacion.fichero_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    presentacion.eventos.append(PresentacionEvento(usuario=quien, evento="fichero_generado", detalle=f"{nombre} · {len(datos)} bytes · diseño {DISENO_VERSION}", momento=datetime.now()))
    sesion.flush()
    return ruta


@dataclass
class PagoRetenciones:
    """Si lo retenido del trimestre se ha ingresado ya, según la contabilidad: cargos a la 4751 desde el fin del trimestre hasta el mes siguiente al plazo."""

    retenido: Decimal
    pagado: Decimal = CERO
    pagos: list[tuple[date, str, Decimal]] = field(default_factory=list)  # (fecha, asiento, importe)

    @property
    def pendiente(self) -> Decimal:
        return self.retenido - self.pagado


def pago_del_periodo(sesion: Session, ejercicio: Ejercicio, periodo: int, retenido: Decimal) -> PagoRetenciones | None:
    """`None` si no hay retenciones que pagar en el trimestre."""
    if retenido <= 0:
        return None
    _, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    limite = hasta + timedelta(days=60)  # el ingreso se hace en el mes siguiente; dos meses cubren cualquier retraso razonable
    pagos = []
    for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id.in_(select(Ejercicio.id).where(Ejercicio.empresa_id == ejercicio.empresa_id)), Asiento.fecha > hasta, Asiento.fecha <= limite).order_by(Asiento.fecha)):
        if a.subtipo in SUBTIPOS_QUE_NO_SON_OPERACIONES:
            continue
        cargo = sum((ap.debe - ap.haber for ap in a.apuntes if ap.cuenta.codigo.startswith("4751")), CERO)
        if cargo > 0:
            pagos.append((a.fecha, a.identificador, cargo))
    return PagoRetenciones(retenido, sum((p[2] for p in pagos), CERO), pagos)
