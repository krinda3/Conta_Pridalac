"""Borrador del modelo 190 (resumen anual de retenciones), sus controles y su fichero (el mismo molde que el 303 y el 111).

Se reutilizan de `presentacion303.py` el registro de la presentación con el PDF de la sede, el rechazo y el borrado de lo no presentado. Lo propio del 190: el cálculo por perceptor
(`servicios/modelo190.py`), que es informativo (no hay ingreso ni NRC), que el periodo es el ejercicio entero (`0A`) y que el **número de justificante** lo lleva ya el propio fichero
(posiciones 108-120): la sede lo respeta, así que al registrar la presentación se comprueba que el PDF dice el mismo.
La rectificación es la declaración **sustitutiva** (anula y sustituye a la anterior, con su número identificativo); la complementaria, que sólo añade percepciones omitidas, no está.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac import auditoria
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import BORRADOR, DESCARTADA, GENERADA, Asiento, Ejercicio, PresentacionAeat, PresentacionEvento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero190 import CODIFICACION, DISENO_VERSION, Declaracion190, Percepcion190, generar, leer
from conta_pridalac.servicios.modelo190 import Calculo190, calcular_190
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion303 import JUSTIFICANTE_VALIDO, _usuario, hoy, presentada_del_periodo, registrar_presentacion, ruta_del_fichero
from conta_pridalac.servicios.entorno import exigir_base_real

MODELO = "190"
PERIODO = "0A"
TIPOS_DE_PRESENTACION = ("normal", "sustitutiva")
TIPO_DECLARACION = "X"  # informativa: no hay resultado que ingresar
CERO = Decimal("0.00")


def instantanea(calculo: Calculo190) -> dict:
    """Lo que se congela en el borrador: los perceptores con sus datos y sus importes."""
    return {
        "perceptores": [[p.nif, p.nombre, p.provincia, p.clave, p.subclave, str(p.percepcion), str(p.retencion)] for p in calculo.perceptores],
        "percepciones": str(calculo.percepciones), "retenciones": str(calculo.retenciones),
    }


def lo_anterior(sesion: Session, empresa_id: int, anio: int, tipo_presentacion: str):
    if tipo_presentacion == "normal":
        return None
    return presentada_del_periodo(sesion, empresa_id, anio, 0, MODELO)


def retenido_en_los_111(sesion: Session, empresa_id: int, anio: int) -> tuple[Decimal, Decimal, list[int]]:
    """(percepciones, retenciones, trimestres sin 111 presentado) según los 111 presentados del año."""
    percepciones = retenciones = CERO
    sin_presentar = []
    for t in (1, 2, 3, 4):
        previa = presentada_del_periodo(sesion, empresa_id, anio, t, "111")
        if previa is None:
            sin_presentar.append(t)
            continue
        casillas = json.loads(previa.casillas or "{}")
        percepciones += Decimal(str(casillas.get("8", 0)))
        retenciones += Decimal(str(casillas.get("9", 0)))
    return percepciones, retenciones, sin_presentar


def controlar_190(sesion: Session, ejercicio: Ejercicio, calculo: Calculo190, *, tipo_presentacion: str = "normal") -> list[Hallazgo]:
    empresa, hallazgos = ejercicio.empresa, []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    previa = presentada_del_periodo(sesion, empresa.id, ejercicio.anio, 0, MODELO)
    if tipo_presentacion not in TIPOS_DE_PRESENTACION:
        hallazgo("tipo_de_presentacion_desconocido", ERROR, f"Tipo de presentación desconocido: {tipo_presentacion}")
    elif tipo_presentacion == "normal" and previa is not None:
        hallazgo("periodo_ya_presentado", ERROR, f"El 190 de {ejercicio.anio} ya está presentado: sólo se puede rectificar con una declaración sustitutiva", "190")
    elif tipo_presentacion == "sustitutiva":
        if previa is None:
            hallazgo("rectificativa_sin_presentada", ERROR, f"No hay un 190 de {ejercicio.anio} presentado que sustituir", "190")
        elif not JUSTIFICANTE_VALIDO.fullmatch((previa.justificante or "").strip()):
            hallazgo("falta_justificante_anterior", ERROR, "El 190 que se sustituye no tiene un nº de justificante de 13 dígitos: el fichero de una sustitutiva lo lleva", "190")

    # datos de quien declara: el 190 pide teléfono y nombre de la persona de contacto
    if len(re.sub(r"\D", "", empresa.telefono or "")) < 9:
        hallazgo("falta_telefono", ERROR, "Falta el teléfono de la empresa (9 cifras): el 190 pide uno de contacto")
    if not (empresa.representante_nombre or "").strip():
        hallazgo("falta_contacto", ERROR, "Falta el nombre del representante en la ficha de la empresa: el 190 pide una persona de contacto")
    if not (empresa.nif or "").strip():
        hallazgo("falta_nif", ERROR, "Falta el NIF de la empresa")

    # perceptores completos
    for p in calculo.perceptores:
        if p.faltan:
            hallazgo("perceptor_incompleto", ERROR, f"{p.nombre}: faltan en su ficha {', '.join(p.faltan)}", p.cuenta)
    if not calculo.perceptores:
        hallazgo("sin_perceptores", AVISO, "No hay retenciones en el año: no hay nada que declarar. Si se presenta, irá sin perceptores", "190")

    # contabilidad del año
    en_el_ano = {a.identificador for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id))}
    for h in auditoria.asientos_descuadrados(sesion, ejercicio):
        if h.referencia in en_el_ano:
            hallazgos.append(h)
    for aviso in calculo.avisos:
        if "faltan en su ficha" not in aviso:
            hallazgo("aviso_del_calculo", AVISO, aviso)

    # cuadre con los 111 del año: la AEAT lo cruza
    percepciones, retenciones, faltan = retenido_en_los_111(sesion, empresa.id, ejercicio.anio)
    if faltan and calculo.retenciones:
        hallazgo("111_sin_presentar", AVISO, f"No consta presentado el 111 de {', '.join(f'{t}T' for t in faltan)}: el 190 tiene que cuadrar con los cuatro", "190")
    if not faltan and retenciones != calculo.retenciones:
        hallazgo("no_cuadra_con_los_111", AVISO, f"Las retenciones ({calculo.retenciones}) no coinciden con las de los 111 presentados ({retenciones}): la AEAT cruza ambos modelos", "190")
    if not faltan and percepciones != calculo.percepciones:
        hallazgo("no_cuadra_con_los_111_percepciones", AVISO, f"Las percepciones ({calculo.percepciones}) no coinciden con las de los 111 presentados ({percepciones})", "190")

    p, dia = plazo(MODELO, ejercicio.anio), hoy()
    if tipo_presentacion == "normal" and dia > p.fin:
        hallazgo("presentacion_fuera_de_plazo", AVISO, f"El plazo de presentación terminó el {p.fin:%d/%m/%Y}: presentarlo ahora es extemporáneo y puede llevar recargo", "190")
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def crear_borrador(sesion: Session, ejercicio: Ejercicio, *, tipo_presentacion: str = "normal", usuario: str | None = None) -> tuple[PresentacionAeat, list[Hallazgo]]:
    empresa = ejercicio.empresa
    previa = lo_anterior(sesion, empresa.id, ejercicio.anio, tipo_presentacion)
    calculo = calcular_190(sesion, ejercicio)
    hallazgos = controlar_190(sesion, ejercicio, calculo, tipo_presentacion=tipo_presentacion)
    bloqueantes = [h for h in hallazgos if h.codigo in ("periodo_ya_presentado", "rectificativa_sin_presentada", "tipo_de_presentacion_desconocido")]
    if bloqueantes:
        raise ErrorContable(bloqueantes[0].mensaje)
    quien = usuario or _usuario()
    for antiguo in sesion.scalars(select(PresentacionAeat).where(
        PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ejercicio.anio, PresentacionAeat.periodo == PERIODO,
        PresentacionAeat.estado.in_((BORRADOR, GENERADA)),
    )):
        if antiguo.estado == BORRADOR:
            sesion.delete(antiguo)
        else:
            antiguo.estado = DESCARTADA
            antiguo.eventos.append(PresentacionEvento(usuario=quien, evento="descartada", detalle="Sustituida por un borrador nuevo", momento=datetime.now()))
    p = PresentacionAeat(
        empresa_id=empresa.id, modelo=MODELO, anio=ejercicio.anio, periodo=PERIODO, estado=BORRADOR, tipo_presentacion=tipo_presentacion, tipo_declaracion=TIPO_DECLARACION,
        resultado=calculo.retenciones, casillas=json.dumps(instantanea(calculo)), domiciliar=False, anterior_id=previa.id if isinstance(previa, PresentacionAeat) else None, creada_por=quien,
    )
    p.eventos.append(PresentacionEvento(usuario=quien, evento="creada", detalle=f"{len(calculo.perceptores)} perceptor(es); retenciones {calculo.retenciones}"))
    sesion.add(p)
    sesion.flush()
    return p, hallazgos


def _identificativo(sesion: Session) -> str:
    """Número de 13 cifras que identifica la declaración («190» y diez cifras al azar); la sede lo conserva como número de justificante."""
    while True:
        n = "190" + "".join(str(secrets.randbelow(10)) for _ in range(10))
        if sesion.scalar(select(PresentacionAeat.id).where(PresentacionAeat.justificante == n).limit(1)) is None:
            return n


def generar_fichero(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, usuario: str | None = None) -> Path:
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede volver a generar")
    empresa = ejercicio.empresa
    previa = lo_anterior(sesion, empresa.id, ejercicio.anio, presentacion.tipo_presentacion)
    calculo = calcular_190(sesion, ejercicio)
    if instantanea(calculo) != json.loads(presentacion.casillas or "{}"):
        raise ErrorContable("Los asientos o los datos de los perceptores han cambiado desde que se creó el borrador: guarde el borrador de nuevo")
    errores = [h.mensaje for h in controlar_190(sesion, ejercicio, calculo, tipo_presentacion=presentacion.tipo_presentacion) if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    declaracion = Declaracion190(
        nif=empresa.nif.strip(), nombre=empresa.nombre, ejercicio=ejercicio.anio, contacto_telefono=re.sub(r"\D", "", empresa.telefono)[-9:], contacto_nombre=empresa.representante_nombre,
        identificativo=_identificativo(sesion), email=(empresa.email or "")[:50], sustitutiva=previa is not None, identificativo_anterior=(previa.justificante or "").strip() if previa is not None else "",
        percepciones=[Percepcion190(p.nif, p.nombre, p.provincia, p.clave, p.subclave, p.percepcion, p.retencion) for p in calculo.perceptores],
    )
    datos = generar(declaracion).encode(CODIFICACION)
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, "190", ejercicio.anio, presentacion.periodo, presentacion.tipo_presentacion, "190")
    ruta = carpeta / f"{presentacion.id}_{nombre}"
    ruta.write_bytes(datos)
    quien = usuario or _usuario()
    presentacion.estado = GENERADA
    presentacion.diseno_version, presentacion.diseno_sha256 = DISENO_VERSION, None
    presentacion.fichero_nombre, presentacion.fichero_sha256 = nombre, hashlib.sha256(datos).hexdigest()
    presentacion.fichero_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    presentacion.eventos.append(PresentacionEvento(usuario=quien, evento="fichero_generado", detalle=f"{nombre} · {len(datos)} bytes · identificativo {declaracion.identificativo}", momento=datetime.now()))
    sesion.flush()
    return ruta


def identificativo_del_fichero(raiz_almacen: Path, presentacion: PresentacionAeat) -> str | None:
    ruta = ruta_del_fichero(raiz_almacen, presentacion)
    return leer(ruta.read_bytes().decode(CODIFICACION)).identificativo if ruta is not None else None


def registrar(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, pdf: bytes, **kw) -> PresentacionAeat:
    """Registra la presentación con el PDF de la sede, tras comprobar que su número de justificante es el que lleva el fichero generado."""
    from conta_pridalac.servicios.justificante_aeat import leer_justificante

    esperado = identificativo_del_fichero(raiz_almacen, presentacion)
    leido = leer_justificante(pdf)
    if esperado and leido is not None and leido.justificante != esperado:
        raise ErrorContable(f"El PDF tiene el justificante {leido.justificante} y el fichero generado lleva el {esperado}: ¿se presentó otro fichero distinto del generado aquí?")
    return registrar_presentacion(sesion, ejercicio, presentacion, raiz_almacen, pdf=pdf, **kw)
