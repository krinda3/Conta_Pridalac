"""Borrador del modelo 303 y sus controles (fase C del Hito 3).

`controlar_303` devuelve `Hallazgo`s como la auditoría: `ERROR` bloquea generar el fichero y presentar; `AVISO` se enseña pero no bloquea.
`crear_borrador` calcula el 303, congela las casillas en una `PresentacionAeat` y deja constancia en su historial.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import re
from datetime import date, datetime
from dataclasses import dataclass, field
from pathlib import Path
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac import auditoria
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import (
    BORRADOR,
    DESCARTADA,
    GENERADA,
    PRESENTADA,
    RECHAZADA,
    SUSTITUIDA,
    Adjunto,
    Apunte,
    Asiento,
    Cuenta,
    DeclaracionPresentada,
    Ejercicio,
    Factura,
    PresentacionAeat,
    MovimientoBanco,
    Pago,
    PresentacionEvento,
    Vencimiento,
)
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero303 import CODIFICACION, DISENO_SHA256, DISENO_VERSION, desde_calculo, generar, tipo_de_declaracion
from conta_pridalac.domain.tesoreria import pendiente
from conta_pridalac.servicios.iva import _asiento_de_liquidacion
from conta_pridalac.servicios.justificante_aeat import leer_justificante
from conta_pridalac.servicios.modelo303 import Calculo303, calcular_303, periodo_de_fechas
from conta_pridalac.servicios.plazos import plazo_303
from conta_pridalac.servicios.entorno import exigir_base_real

CERO = Decimal("0.00")
TOLERANCIA = Decimal("0.05")  # redondeo de céntimos entre las cuotas por línea y los asientos
TIPOS_DE_PRESENTACION = ("normal", "rectificativa")
TIPO_DE_ASIENTO = {"E": 1, "R": 2}


NRC_VALIDO = re.compile(r"[A-Z0-9]{22}")


def etiqueta_periodo(modelo: str, periodo: int) -> str:
    """Cómo se guarda el periodo de una presentación: «1T»…«4T» en los trimestrales y «0A» en los anuales (190, 390, 347)."""
    if modelo == "202":  # tres pagos fraccionados: «1P», «2P» y «3P»
        return f"{periodo}P"
    return "0A" if modelo in ("190", "180", "390", "347") else f"{periodo}T"


def hoy() -> date:
    return date.today()


def importe_del_nrc(sesion: Session, empresa_id: int, anio: int, periodo: int, nrc: str | None, resultado: Decimal, modelo: str = "303") -> Decimal | None:
    """Resultado con el que se anotó este NRC: el del borrador que ya lo tenía, o el de ahora si el NRC es nuevo (`None` sin NRC)."""
    if not nrc:
        return None
    anterior = sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == modelo, PresentacionAeat.anio == anio, PresentacionAeat.periodo == etiqueta_periodo(modelo, periodo),
               PresentacionAeat.estado.in_((BORRADOR, GENERADA)), PresentacionAeat.nrc == nrc, PresentacionAeat.nrc_importe.is_not(None))
        .order_by(PresentacionAeat.id.desc())
    ).first()
    return anterior.nrc_importe if anterior is not None else resultado


def lo_anterior(sesion: Session, empresa_id: int, anio: int, periodo: int, tipo_presentacion: str):
    """Para una rectificativa: (presentación que se rectifica, su resultado —casilla 69—). `(None, None)` si es normal o no hay nada presentado."""
    if tipo_presentacion == "normal":
        return None, None
    previa = presentada_del_periodo(sesion, empresa_id, anio, periodo)
    if previa is None:
        return None, None
    casillas = json.loads(previa.casillas or "{}")
    for clave in ("69", "71"):
        if clave in casillas:
            return previa, Decimal(str(casillas[clave]))
    return previa, previa.resultado


def _usuario() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - entornos sin usuario
        return "desconocido"


def presentada_del_periodo(sesion: Session, empresa_id: int, anio: int, periodo: int, modelo: str = "303"):
    """Última presentación del periodo: una nuestra `presentada` o, si no, la importada del programa anterior. `None` si el periodo aún no se presentó."""
    nuestra = sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == modelo, PresentacionAeat.anio == anio,
               PresentacionAeat.periodo == etiqueta_periodo(modelo, periodo), PresentacionAeat.estado == PRESENTADA)
        .order_by(PresentacionAeat.id.desc())
    ).first()
    if nuestra is not None:
        return nuestra
    return sesion.scalars(
        select(DeclaracionPresentada)
        .where(DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == modelo, DeclaracionPresentada.anio == anio, DeclaracionPresentada.periodo == periodo)
        .order_by(DeclaracionPresentada.tipo)
    ).first()


SUBTIPOS_QUE_NO_SON_OPERACIONES = ("A", "P", "R", "Z")  # apertura, liquidación de IVA, regularización y cierre


def _saldo_de_iva(sesion: Session, ejercicio: Ejercicio, desde, hasta, prefijo: str, *, de_facturas: bool) -> Decimal:
    """Debe − haber de las cuentas con ese prefijo (472 / 477) en el periodo, de los asientos de las facturas (`de_facturas`) o de los demás (sin apertura, liquidación ni cierre)."""
    en_facturas = Asiento.tipo.in_((1, 2))
    debe, haber = sesion.execute(
        select(func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta, Cuenta.codigo.startswith(prefijo),
               func.coalesce(Asiento.subtipo, "").not_in(SUBTIPOS_QUE_NO_SON_OPERACIONES), en_facturas if de_facturas else ~en_facturas)
    ).one()
    return (debe or CERO) - (haber or CERO)


def _usa_prorrata(sesion: Session, empresa_id: int, calculo: Calculo303) -> bool:
    """La empresa regulariza prorrata si lo hizo en alguna declaración anterior o tiene operaciones exentas (base en la casilla 150)."""
    if calculo[150]:
        return True
    for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == "303")):
        if Decimal(str(json.loads(d.casillas or "{}").get("44", 0))) != 0:
            return True
    return False


def _facturas_del_periodo(sesion: Session, ejercicio: Ejercicio, desde, hasta) -> list[Factura]:
    return list(sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.fecha_contable >= desde, Factura.fecha_contable <= hasta).order_by(Factura.sentido, Factura.numero)))


def controlar_303(
    sesion: Session, ejercicio: Ejercicio, periodo: int, calculo: Calculo303, *, tipo_presentacion: str = "normal", domiciliar: bool = True,
    iban: str | None = None, prorrata_dada: bool = False, bolsa_manual: bool = False, nrc: str | None = None, nrc_importe: Decimal | None = None,
) -> list[Hallazgo]:
    desde, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    empresa_id = ejercicio.empresa_id
    hallazgos: list[Hallazgo] = []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    # 1. Periodo ya presentado: sólo se rectifica con una rectificativa
    previa = presentada_del_periodo(sesion, empresa_id, ejercicio.anio, periodo)
    if tipo_presentacion not in TIPOS_DE_PRESENTACION:
        hallazgo("tipo_de_presentacion_desconocido", ERROR, f"Tipo de presentación desconocido: {tipo_presentacion}")
    elif tipo_presentacion == "normal" and previa is not None:
        hallazgo("periodo_ya_presentado", ERROR, f"El {periodo}T {ejercicio.anio} ya está presentado: sólo se puede rectificar con una autoliquidación rectificativa", f"{periodo}T")
    elif tipo_presentacion != "normal" and previa is None:
        hallazgo("rectificativa_sin_presentada", ERROR, f"No hay un {periodo}T {ejercicio.anio} presentado que rectificar", f"{periodo}T")
    elif tipo_presentacion != "normal":
        if not JUSTIFICANTE_VALIDO.fullmatch((previa.justificante or "").strip()):
            hallazgo("falta_justificante_anterior", ERROR, "La autoliquidación que se rectifica no tiene un nº de justificante de 13 dígitos: el fichero de una rectificativa lo lleva", f"{periodo}T")
        if (isinstance(previa, PresentacionAeat) and previa.tipo_presentacion != "normal") or (isinstance(previa, DeclaracionPresentada) and previa.tipo != 1):
            hallazgo("rectificativa_de_una_rectificativa", AVISO, "Es una segunda rectificativa: la AEAT explica sus casillas 70 y 111 aparte (anexos de las instrucciones); compruebe el resultado en la sede", f"{periodo}T")
        if calculo[111]:
            hallazgo("casilla_111", AVISO, f"Esta rectificativa devuelve ingreso de más: la casilla 111 sale con {calculo[111]}. Las instrucciones no dan su fórmula; compruébela al importar el fichero en la sede", "111")
        if sesion.scalar(select(PresentacionAeat.id).where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ejercicio.anio,
                                                          PresentacionAeat.periodo.in_([f"{p}T" for p in range(periodo + 1, 5)]), PresentacionAeat.estado == PRESENTADA).limit(1)) is not None:
            hallazgo("hay_trimestres_posteriores_presentados", AVISO, "Hay trimestres posteriores ya presentados: si esta rectificativa cambia las cuotas a compensar, habría que rectificarlos también", f"{periodo}T")


    # 2. Contabilidad de las facturas del periodo
    facturas = _facturas_del_periodo(sesion, ejercicio, desde, hasta)
    refs = {f"{f.sentido} {f.numero}" for f in facturas}
    prefijos = {f"{TIPO_DE_ASIENTO[f.sentido]}.{f.numero}" for f in facturas}

    def de_la_factura(ref: str) -> bool:
        return ref in refs or ref.split("/")[0] in prefijos

    en_periodo = {a.identificador for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta))}
    for h in auditoria.asientos_descuadrados(sesion, ejercicio):
        if h.referencia in en_periodo:
            hallazgos.append(h)
    for h in auditoria.facturas_y_sus_asientos(sesion, ejercicio):
        if h.gravedad == ERROR and de_la_factura(h.referencia):
            hallazgos.append(h)

    # 3. Justificantes: no son obligatorios, sólo se avisa
    con_fichero = set(sesion.scalars(select(Adjunto.factura_id).where(Adjunto.factura_id.is_not(None), Adjunto.sha256.is_not(None))))
    sin = [f for f in facturas if f.sentido == "R" and f.id not in con_fichero]
    if sin:
        hallazgo("facturas_sin_justificante", AVISO, f"{len(sin)} facturas recibidas del periodo no tienen justificante: " + ", ".join(f"R {f.numero}" for f in sin[:15]) + ("…" if len(sin) > 15 else ""))

    # 4. El 303 frente a las cuentas de IVA
    repercutido = -_saldo_de_iva(sesion, ejercicio, desde, hasta, "477", de_facturas=True)
    soportado = _saldo_de_iva(sesion, ejercicio, desde, hasta, "472", de_facturas=True)
    ded303 = calculo[29] + calculo[31] + calculo[41]
    if abs(calculo[27] - repercutido) > TOLERANCIA:
        hallazgo("devengado_distinto_de_la_contabilidad", ERROR, f"El IVA devengado del 303 ({calculo[27]}) no coincide con la cuenta 477 del periodo ({repercutido})")
    if abs(ded303 - soportado) > TOLERANCIA:
        hallazgo("deducible_distinto_de_la_contabilidad", ERROR, f"El IVA deducible del 303 ({ded303}) no coincide con la cuenta 472 del periodo ({soportado})")

    manuales = sorted({
        a.identificador for a in sesion.scalars(
            select(Asiento).join(Apunte, Apunte.asiento_id == Asiento.id).join(Cuenta, Cuenta.id == Apunte.cuenta_id)
            .where(Asiento.ejercicio_id == ejercicio.id, Asiento.fecha >= desde, Asiento.fecha <= hasta, Asiento.tipo.not_in((1, 2)),
                   func.coalesce(Asiento.subtipo, "").not_in(SUBTIPOS_QUE_NO_SON_OPERACIONES), or_(Cuenta.codigo.startswith("472"), Cuenta.codigo.startswith("477")))
        )
    })
    if manuales:
        hallazgo("asientos_manuales_en_cuentas_de_iva", AVISO, "Hay asientos que no son de facturas en las cuentas 472/477 del periodo y no entran en el 303: " + ", ".join(manuales), manuales[0])

    # 5. Compensación: se apoya en lo presentado en el trimestre anterior
    if periodo > 1:
        if presentada_del_periodo(sesion, empresa_id, ejercicio.anio, periodo - 1) is None:
            if bolsa_manual:
                hallazgo("bolsa_introducida_a_mano", AVISO, f"Las cuotas a compensar ({calculo[110]}) se han introducido a mano: el {periodo - 1}T {ejercicio.anio} no consta como presentado", f"{periodo - 1}T")
            else:
                hallazgo("trimestre_anterior_sin_presentar", ERROR, f"El {periodo - 1}T {ejercicio.anio} no consta como presentado: sin él no se sabe qué hay que compensar", f"{periodo - 1}T")

    # 6. Prorrata (casilla 44), que se introduce a mano
    if periodo == 4 and not prorrata_dada and _usa_prorrata(sesion, empresa_id, calculo):
        hallazgo("prorrata_sin_introducir", AVISO, "Es el último trimestre y la empresa aplica prorrata: ¿falta la regularización por el porcentaje definitivo (casilla 44)?", "44")

    # 7. Plazos y forma de pago
    plazo, dia = plazo_303(ejercicio.anio, periodo), hoy()
    if tipo_presentacion == "normal" and dia > plazo.fin:
        hallazgo("presentacion_fuera_de_plazo", AVISO, f"El plazo de presentación terminó el {plazo.fin:%d/%m/%Y}: presentarlo ahora es extemporáneo y puede llevar recargo", f"{periodo}T")
    if calculo[71] > 0 and domiciliar:
        if not (iban or "").strip():
            hallazgo("domiciliacion_sin_iban", ERROR, "Para domiciliar el pago hace falta el IBAN de la empresa (ficha de la empresa)")
        if dia > plazo.fin_domiciliacion:
            hallazgo(
                "domiciliacion_fuera_de_plazo", ERROR if plazo.confirmado else AVISO,
                f"El plazo para domiciliar terminó el {plazo.fin_domiciliacion:%d/%m/%Y}{'' if plazo.confirmado else ' (fecha estimada)'}: elija pagar con NRC", f"{periodo}T",
            )
    if nrc and not NRC_VALIDO.fullmatch(nrc):
        hallazgo("nrc_no_valido", ERROR, "El NRC son 22 caracteres (letras mayúsculas y números)")
    elif calculo[71] > 0 and not domiciliar and not nrc:
        hallazgo("nrc_pendiente", AVISO, "Falta el NRC: se obtiene pagando en la sede de la AEAT («Pago mediante cargo en cuenta») con el importe exacto, y hay que tenerlo para presentar", f"{periodo}T")
    elif nrc and (calculo[71] <= 0 or domiciliar):
        hallazgo("nrc_sin_importe_a_ingresar", AVISO, "Se ha indicado un NRC pero este periodo no se paga con NRC", f"{periodo}T")
    elif nrc and nrc_importe is not None and nrc_importe != calculo[71]:
        hallazgo(
            "nrc_de_otro_importe", ERROR,
            f"El NRC se anotó cuando el resultado era {nrc_importe} y ahora es {calculo[71]}: un NRC sólo vale para el importe exacto con el que se pagó. Obtenga otro NRC o revise qué ha cambiado", f"{periodo}T",
        )
    if tipo_de_declaracion(calculo[71], domiciliar=domiciliar) == "N" and not (calculo[27] or calculo[45]):
        hallazgo("periodo_sin_actividad", AVISO, "El periodo no tiene operaciones: saldrá como declaración sin actividad", f"{periodo}T")

    for aviso in calculo.avisos:
        hallazgo("aviso_del_calculo", AVISO, aviso)
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def crear_borrador(
    sesion: Session, ejercicio: Ejercicio, periodo: int, *, regularizacion_prorrata: Decimal | None = None, rectifican: set[int] | None = None, bolsa: Decimal | None = None,
    tipo_presentacion: str = "normal", domiciliar: bool = True, nrc: str | None = None, baja_domiciliacion: bool = False, usuario: str | None = None,
) -> tuple[PresentacionAeat, list[Hallazgo]]:
    """Calcula el 303 del trimestre y guarda un borrador con las casillas congeladas. Sustituye al borrador anterior del mismo periodo, si lo hay.

    Un periodo ya presentado sólo admite una rectificativa. Los errores de los controles no impiden crear el borrador (así se ve qué
    arreglar) pero sí generar el fichero y presentar (`hay_errores`).
    """
    empresa = ejercicio.empresa
    previa, anterior_69 = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, tipo_presentacion)
    calculo = calcular_303(sesion, ejercicio, periodo, regularizacion_prorrata=regularizacion_prorrata, rectifican=rectifican, bolsa=bolsa, anterior_69=anterior_69)
    importe_nrc = importe_del_nrc(sesion, empresa.id, ejercicio.anio, periodo, nrc, calculo[71])
    hallazgos = controlar_303(
        sesion, ejercicio, periodo, calculo, tipo_presentacion=tipo_presentacion, domiciliar=domiciliar, iban=empresa.iban,
        prorrata_dada=regularizacion_prorrata is not None, bolsa_manual=bolsa is not None, nrc=nrc, nrc_importe=importe_nrc,
    )
    bloqueantes = [h for h in hallazgos if h.codigo in ("periodo_ya_presentado", "rectificativa_sin_presentada", "tipo_de_presentacion_desconocido")]
    if bloqueantes:  # lo que impide crear el borrador, no el primer error que salga
        raise ErrorContable(bloqueantes[0].mensaje)
    quien = usuario or _usuario()
    for antiguo in sesion.scalars(
        select(PresentacionAeat).where(PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.modelo == "303", PresentacionAeat.anio == ejercicio.anio,
                                       PresentacionAeat.periodo == f"{periodo}T", PresentacionAeat.estado.in_((BORRADOR, GENERADA)))
    ):
        if antiguo.estado == BORRADOR:
            sesion.delete(antiguo)
        else:  # un fichero ya generado se conserva con su historia: puede que se haya llevado a la sede
            antiguo.estado = DESCARTADA
            antiguo.eventos.append(PresentacionEvento(usuario=quien, evento="descartada", detalle="Sustituida por un borrador nuevo", momento=datetime.now()))
    p = PresentacionAeat(
        empresa_id=empresa.id, modelo="303", anio=ejercicio.anio, periodo=f"{periodo}T", estado=BORRADOR, tipo_presentacion=tipo_presentacion,
        tipo_declaracion=tipo_de_declaracion(calculo[71], domiciliar=domiciliar, rectificacion=calculo[111]), resultado=calculo[71],
        casillas=json.dumps({str(k): str(v) for k, v in sorted(calculo.casillas.items())}), prorrata=regularizacion_prorrata, bolsa_inicial=calculo[110], bolsa_manual=bolsa is not None,
        rectifican=json.dumps(sorted(rectifican or ())), domiciliar=domiciliar, baja_domiciliacion=baja_domiciliacion, nrc=(nrc or None), nrc_importe=importe_nrc,
        anterior_id=previa.id if isinstance(previa, PresentacionAeat) else None, creada_por=quien,
    )
    p.eventos.append(PresentacionEvento(usuario=quien, evento="creada", detalle=f"{len(calculo.lineas)} líneas de factura; resultado {calculo[71]}"))
    sesion.add(p)
    sesion.flush()
    return p, hallazgos


def hay_errores(hallazgos: list[Hallazgo]) -> bool:
    return auditoria.hay_errores(hallazgos)


@dataclass
class PagoDelPeriodo:
    """Cómo va el pago del IVA de un trimestre en la contabilidad: el vencimiento de la liquidación y los movimientos de banco que lo saldan."""

    asiento: str
    fecha: date | None = None
    importe: Decimal = CERO  # a pagar (positivo)
    pendiente: Decimal = CERO
    pagos: list[tuple[date, str, Decimal, str]] = field(default_factory=list)  # (fecha, banco, importe, texto) de cada movimiento


def pago_del_periodo(sesion: Session, ejercicio: Ejercicio, periodo: int) -> PagoDelPeriodo | None:
    """El pago del trimestre si ya está liquidado en la contabilidad y tiene vencimiento (hay IVA a pagar); `None` si no."""
    _, hasta = periodo_de_fechas(ejercicio.anio, periodo)
    asiento = _asiento_de_liquidacion(sesion, ejercicio, hasta)
    if asiento is None:
        return None
    v = sesion.scalars(select(Vencimiento).join(Apunte, Apunte.id == Vencimiento.apunte_id).where(Apunte.asiento_id == asiento.id)).first()
    if v is None:
        return None
    pagos = [
        (m.fecha, m.banco.nombre, -p.importe, m.texto)
        for p, m in sesion.execute(select(Pago, MovimientoBanco).join(MovimientoBanco, MovimientoBanco.id == Pago.movimiento_id).where(Pago.vencimiento_id == v.id).order_by(MovimientoBanco.fecha))
    ]
    return PagoDelPeriodo(asiento.identificador, v.fecha, -v.importe, -pendiente(sesion, v), pagos)


def _prefijo_del_fichero(tipo_presentacion: str) -> str:
    return {"rectificativa": "R"}.get(tipo_presentacion, "")


def generar_fichero(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, usuario: str | None = None) -> Path:
    """Genera el fichero del 303 de un borrador y lo guarda en el almacén (`<empresa>/<año>/aeat/`), con su huella y la versión del diseño usada.

    Vuelve a calcular y a pasar los controles: si hay errores, o las facturas han cambiado desde que se creó el borrador, no se genera.
    """
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede volver a generar")
    empresa, periodo = ejercicio.empresa, int(presentacion.periodo[0])
    rectifican = set(json.loads(presentacion.rectifican or "[]"))
    previa, anterior_69 = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, presentacion.tipo_presentacion)
    calculo = calcular_303(sesion, ejercicio, periodo, regularizacion_prorrata=presentacion.prorrata, rectifican=rectifican, bolsa=presentacion.bolsa_inicial if presentacion.bolsa_manual else None, anterior_69=anterior_69)
    congeladas = json.loads(presentacion.casillas or "{}")
    if {str(k): str(v) for k, v in calculo.casillas.items()} != congeladas:
        raise ErrorContable("Las facturas o lo presentado han cambiado desde que se creó el borrador: guarde el borrador de nuevo")
    hallazgos = controlar_303(
        sesion, ejercicio, periodo, calculo, tipo_presentacion=presentacion.tipo_presentacion, domiciliar=presentacion.domiciliar, iban=empresa.iban,
        prorrata_dada=presentacion.prorrata is not None, bolsa_manual=presentacion.bolsa_manual, nrc=presentacion.nrc, nrc_importe=presentacion.nrc_importe,
    )
    errores = [h.mensaje for h in hallazgos if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    declaracion = desde_calculo(
        empresa, calculo, domiciliar=presentacion.domiciliar, iban=(empresa.iban or "").replace(" ", ""),
        justificante_anterior=(previa.justificante or "").strip() if previa is not None else None, baja_domiciliacion=presentacion.baja_domiciliacion,
    )
    texto = generar(declaracion)
    datos = texto.encode(CODIFICACION)
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, "303", ejercicio.anio, presentacion.periodo, presentacion.tipo_presentacion, "303")
    ruta = carpeta / f"{presentacion.id}_{nombre}"
    ruta.write_bytes(datos)
    quien = usuario or _usuario()
    presentacion.estado = GENERADA
    presentacion.tipo_declaracion = declaracion.tipo
    presentacion.diseno_version, presentacion.diseno_sha256 = DISENO_VERSION, DISENO_SHA256
    presentacion.fichero_nombre, presentacion.fichero_sha256 = nombre, hashlib.sha256(datos).hexdigest()
    presentacion.fichero_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    presentacion.eventos.append(PresentacionEvento(usuario=quien, evento="fichero_generado", detalle=f"{nombre} · {len(datos)} bytes · diseño {DISENO_VERSION}", momento=datetime.now()))
    sesion.flush()
    return ruta


JUSTIFICANTE_VALIDO = re.compile(r"\d{13}")
CSV_VALIDO = re.compile(r"[A-Z0-9]{16}")
MAXIMO_PDF = 10 * 1024 * 1024


def _carpeta_aeat(raiz_almacen: Path, ejercicio: Ejercicio) -> Path:
    return Path(raiz_almacen) / f"{ejercicio.empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"


def ruta_del_fichero(raiz_almacen: Path, presentacion: PresentacionAeat) -> Path | None:
    """Fichero generado de una presentación si está en el almacén y sin alterar (su huella coincide con la guardada)."""
    if not presentacion.fichero_ruta:
        return None
    raiz = Path(raiz_almacen).resolve()
    ruta = (raiz / presentacion.fichero_ruta).resolve()
    if raiz not in ruta.parents or not ruta.is_file():
        return None
    return ruta if hashlib.sha256(ruta.read_bytes()).hexdigest() == presentacion.fichero_sha256 else None


def registrar_presentacion(
    sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, pdf: bytes, justificante: str | None = None, csv: str | None = None,
    momento: datetime | None = None, usuario: str | None = None,
) -> PresentacionAeat:
    """Deja constancia de que el fichero generado se presentó en la sede, a partir del PDF que devuelve la AEAT.

    Del PDF se leen el nº de justificante, el CSV, la fecha y hora y, si se ingresó con NRC, el NRC; y se contrasta con lo que se generó (modelo, ejercicio, tipo de
    declaración, importe y NRC). Si el PDF no se puede leer, se aceptan esos datos tecleados (`justificante`, `csv` y `momento`).

    Desde aquí el trimestre queda presentado: ya no admite otro borrador normal, sólo una rectificativa, que deja la anterior como `sustituida`.
    """
    exigir_base_real(sesion, ejercicio.empresa_id, "registrar la presentación")
    if presentacion.estado != GENERADA:
        raise ErrorContable("Primero hay que generar el fichero: sólo se registra la presentación de un fichero generado")
    if not pdf.startswith(b"%PDF"):
        raise ErrorContable("El justificante debe ser el PDF que devuelve la sede")
    leido = leer_justificante(pdf)
    if leido is not None:
        if leido.modelo != presentacion.modelo:
            raise ErrorContable(f"El PDF es del modelo {leido.modelo}, no del {presentacion.modelo}")
        if not leido.registro.startswith(f"{presentacion.anio}{presentacion.modelo}"):
            raise ErrorContable(f"El PDF es de otro ejercicio o modelo (registro {leido.registro}): esta presentación es del {presentacion.periodo} {presentacion.anio}")
        for nombre, tecleado, del_pdf in (("justificante", justificante, leido.justificante), ("CSV", csv, leido.csv)):
            if (tecleado or "").strip() and tecleado.strip().upper() != del_pdf:
                raise ErrorContable(f"El {nombre} tecleado no coincide con el del PDF ({del_pdf})")
        if momento is not None and momento.replace(second=0, microsecond=0) != leido.momento.replace(second=0, microsecond=0):
            raise ErrorContable(f"La fecha y hora tecleadas no coinciden con las del PDF ({leido.momento:%d/%m/%Y %H:%M})")
        if leido.resultado and presentacion.tipo_declaracion != leido.resultado:
            raise ErrorContable(
                f"El PDF corresponde a una presentación de tipo {leido.resultado} y el fichero que se generó era de tipo {presentacion.tipo_declaracion}: "
                "¿se presentó otro fichero distinto del generado aquí?"
            )
        if leido.nrc:
            if presentacion.nrc and presentacion.nrc != leido.nrc:
                raise ErrorContable(f"El NRC del PDF ({leido.nrc}) no es el anotado en la ficha ({presentacion.nrc})")
            if leido.importe is not None and leido.importe != presentacion.resultado:
                raise ErrorContable(f"El PDF dice que se ingresaron {leido.importe} y esta presentación sale a {presentacion.resultado}")
            presentacion.nrc, presentacion.nrc_importe = leido.nrc, presentacion.resultado  # el NRC con el que se presentó es el del PDF
        justificante, csv, momento = leido.justificante, leido.csv, leido.momento
    elif not ((justificante or "").strip() and (csv or "").strip() and momento is not None):
        raise ErrorContable("No se reconoce el PDF como justificante de presentación de la AEAT: compruebe que es el PDF «Información de la presentación» o teclee a mano el justificante, el CSV y la fecha y hora")
    justificante, csv = (justificante or "").strip(), (csv or "").strip().upper()
    otra = sesion.scalar(select(PresentacionAeat.id).where(PresentacionAeat.justificante == justificante, PresentacionAeat.id != presentacion.id).limit(1))
    if otra is not None:
        raise ErrorContable(f"El justificante {justificante} ya está registrado en otra presentación")
    if not JUSTIFICANTE_VALIDO.fullmatch(justificante):
        raise ErrorContable("El número de justificante son 13 dígitos")
    if not CSV_VALIDO.fullmatch(csv):
        raise ErrorContable("El código seguro de verificación (CSV) son 16 caracteres, letras y números")
    if momento > datetime.now():
        raise ErrorContable("La fecha y hora de presentación no pueden ser futuras")
    if len(pdf) > MAXIMO_PDF:
        raise ErrorContable("El PDF del justificante pesa más de 10 MB")
    if ruta_del_fichero(raiz_almacen, presentacion) is None:
        raise ErrorContable("El fichero generado no está en el almacén o ha cambiado desde que se generó: genere el fichero de nuevo")
    previa = presentada_del_periodo(sesion, presentacion.empresa_id, presentacion.anio, int(presentacion.periodo[0]), presentacion.modelo)
    if presentacion.tipo_presentacion == "normal" and previa is not None:
        raise ErrorContable(f"El {presentacion.periodo} {presentacion.anio} ya consta como presentado: esta presentación tendría que ser una rectificativa")
    if presentacion.tipo_presentacion != "normal" and previa is None:
        raise ErrorContable("No hay una presentación anterior de este trimestre que rectificar")
    if presentacion.tipo_declaracion == "I" and presentacion.resultado > 0 and not presentacion.nrc:
        raise ErrorContable("Es un ingreso con NRC: anote el NRC con el que se pagó antes de registrar la presentación")
    if presentacion.nrc_importe is not None and presentacion.nrc and presentacion.nrc_importe != presentacion.resultado:
        raise ErrorContable("El NRC no corresponde al importe de esta presentación")
    quien = usuario or _usuario()
    carpeta = _carpeta_aeat(raiz_almacen, ejercicio)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{presentacion.id}_justificante_{justificante}.pdf"
    ruta.write_bytes(pdf)
    presentacion.respuesta_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    presentacion.respuesta_sha256 = hashlib.sha256(pdf).hexdigest()
    presentacion.justificante, presentacion.csv = justificante, csv
    presentacion.presentada_en, presentacion.presentada_por = momento, quien
    presentacion.estado = PRESENTADA
    presentacion.eventos.append(PresentacionEvento(
        usuario=quien, evento="presentada", momento=datetime.now(),
        detalle=f"Justificante {justificante} · CSV {csv} · {momento:%d/%m/%Y %H:%M} · resultado {presentacion.resultado} · fichero {presentacion.fichero_sha256[:12]}…",
    ))
    if presentacion.tipo_presentacion != "normal" and isinstance(previa, PresentacionAeat):
        previa.estado = SUSTITUIDA
        previa.eventos.append(PresentacionEvento(usuario=quien, evento="sustituida", momento=datetime.now(), detalle=f"Sustituida por la presentación {presentacion.id} (justificante {justificante})"))
    _copiar_justificante(sesion, presentacion, pdf)
    sesion.flush()
    from conta_pridalac.servicios.huellas import anotar_al_confirmar

    anotar_al_confirmar(sesion, raiz_almacen, ejercicio.empresa.codigo, f"presentación del modelo {presentacion.modelo} {presentacion.periodo} {presentacion.anio}")
    return presentacion


def _copiar_justificante(sesion: Session, presentacion: PresentacionAeat, pdf: bytes) -> None:
    """Un segundo ejemplar del PDF de la sede en la carpeta de la empresa (OneDrive…). Si falla, la presentación se registra igual: queda el aviso en `aviso_copia` y en el historial."""
    from conta_pridalac.db.modelos import Empresa
    from conta_pridalac.servicios.copia_justificantes import COPIADO, CON_SUFIJO, FALLO, aviso_de_copia, copiar_pdf, nombre_de

    empresa = sesion.get(Empresa, presentacion.empresa_id)
    copia = copiar_pdf(empresa, presentacion.anio, nombre_de(empresa, presentacion.modelo, presentacion.anio, presentacion.periodo, presentacion.tipo_presentacion), pdf)
    presentacion.aviso_copia = aviso_de_copia(copia)  # sólo para el mensaje de la pantalla: no se guarda
    if copia.estado in (COPIADO, CON_SUFIJO, FALLO):
        presentacion.eventos.append(PresentacionEvento(usuario=_usuario(), evento="copiada" if copia.estado != FALLO else "copia_fallida", momento=datetime.now(),
                                                      detalle=str(copia.destino) if copia.estado != FALLO else copia.mensaje))


def marcar_rechazada(sesion: Session, presentacion: PresentacionAeat, motivo: str, *, usuario: str | None = None) -> PresentacionAeat:
    """La sede rechazó el fichero (errores de validación): queda constancia del motivo y se puede preparar otro borrador."""
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede marcar como rechazada")
    if not (motivo or "").strip():
        raise ErrorContable("Indique el motivo del rechazo (los errores que muestra la sede)")
    presentacion.estado = RECHAZADA
    presentacion.observaciones = motivo.strip()
    presentacion.eventos.append(PresentacionEvento(usuario=usuario or _usuario(), evento="rechazada", detalle=motivo.strip(), momento=datetime.now()))
    sesion.flush()
    return presentacion


ESTADOS_BORRABLES = (BORRADOR, GENERADA, DESCARTADA, RECHAZADA)


def sin_presentar(sesion: Session, empresa_id: int, anio: int, periodo: int, modelo: str = "303") -> list[PresentacionAeat]:
    """Borradores, ficheros generados, descartados y rechazados de un trimestre: lo que no llegó a presentarse y se puede borrar."""
    return list(sesion.scalars(
        select(PresentacionAeat)
        .where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == modelo, PresentacionAeat.anio == anio, PresentacionAeat.periodo == etiqueta_periodo(modelo, periodo),
               PresentacionAeat.estado.in_(ESTADOS_BORRABLES))
        .order_by(PresentacionAeat.id)
    ))


def eliminar_presentacion(sesion: Session, presentacion: PresentacionAeat, raiz_almacen: Path) -> bool:
    """Borra una presentación que no llegó a presentarse, con su fichero del almacén. Devuelve si había fichero.

    Lo presentado (y lo sustituido por una rectificativa) nunca se borra: es la constancia de lo que se declaró.
    """
    if presentacion.estado not in ESTADOS_BORRABLES:
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede borrar: es la constancia de lo que se declaró")
    tenia_fichero = False
    if presentacion.fichero_ruta:
        raiz = Path(raiz_almacen).resolve()
        ruta = (raiz / presentacion.fichero_ruta).resolve()
        if raiz in ruta.parents and ruta.is_file():
            ruta.unlink()
            tenia_fichero = True
    sesion.delete(presentacion)
    sesion.flush()
    return tenia_fichero


def eliminar_sin_presentar(sesion: Session, empresa_id: int, anio: int, periodo: int, raiz_almacen: Path, modelo: str = "303") -> tuple[int, int]:
    """Borra todo lo no presentado de un trimestre. Devuelve (presentaciones borradas, ficheros borrados)."""
    pendientes = sin_presentar(sesion, empresa_id, anio, periodo, modelo)
    if not pendientes:
        raise ErrorContable(f"No hay borradores ni ficheros sin presentar en el {etiqueta_periodo(modelo, periodo)} {anio}")
    ficheros = sum(eliminar_presentacion(sesion, p, raiz_almacen) for p in pendientes)
    return len(pendientes), ficheros
