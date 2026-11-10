"""Borrador del modelo 390 (resumen anual del IVA), sus controles y su fichero (el mismo molde que el 190).

Se reutilizan de `presentacion303.py` el registro de la presentación con el PDF de la sede, el rechazo y el borrado de lo no presentado. Lo propio del 390: el cálculo anual
(`servicios/modelo390.py`), que el periodo es el ejercicio entero (`0A`), que lleva los datos fijos de la ficha de la empresa (actividades y representantes con poder) y que
la sede asigna el número de justificante (no va en el fichero). Se presenta entre el 1 y el 30 de enero del año siguiente.
La rectificación es la declaración **sustitutiva** (con el nº de justificante de la anterior).
"""
from __future__ import annotations

import hashlib
import json
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
from conta_pridalac.ficheros_aeat import fichero390
from conta_pridalac.ficheros_aeat.fichero390 import CODIFICACION, DISENO_SHA256, DISENO_VERSION, MAX_ACTIVIDADES, MAX_REPRESENTANTES, generar
from conta_pridalac.servicios.modelo390 import Calculo390, calcular_390
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion303 import JUSTIFICANTE_VALIDO, _usuario, hoy, presentada_del_periodo, registrar_presentacion
from conta_pridalac.servicios.entorno import exigir_base_real

MODELO = "390"
PERIODO = "0A"
TIPOS_DE_PRESENTACION = ("normal", "sustitutiva")
TIPO_DECLARACION = "X"  # el 390 es un resumen: no hay ingreso ni NRC
CERO = Decimal("0.00")
BLOQUEANTES = ("periodo_ya_presentado", "rectificativa_sin_presentada", "tipo_de_presentacion_desconocido")


def instantanea(empresa, calculo: Calculo390) -> dict:
    """Lo que se congela en el borrador: las casillas y los datos fijos de la ficha que van al fichero."""
    return {
        "casillas": {str(k): str(v) for k, v in sorted(calculo.casillas.items()) if v != 0},
        "actividades": [[a.descripcion, a.codigo or "", a.epigrafe or ""] for a in empresa.actividades],
        "representantes": [[r.nombre, r.nif or "", r.fecha_poder.isoformat() if r.fecha_poder else "", r.notaria or ""] for r in empresa.representantes],
    }


def lo_anterior(sesion: Session, empresa_id: int, anio: int, tipo_presentacion: str):
    if tipo_presentacion == "normal":
        return None
    return presentada_del_periodo(sesion, empresa_id, anio, 0, MODELO)


def controlar_390(sesion: Session, ejercicio: Ejercicio, calculo: Calculo390, *, tipo_presentacion: str = "normal") -> list[Hallazgo]:
    empresa, hallazgos = ejercicio.empresa, []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    previa = presentada_del_periodo(sesion, empresa.id, ejercicio.anio, 0, MODELO)
    if tipo_presentacion not in TIPOS_DE_PRESENTACION:
        hallazgo("tipo_de_presentacion_desconocido", ERROR, f"Tipo de presentación desconocido: {tipo_presentacion}")
    elif tipo_presentacion == "normal" and previa is not None:
        hallazgo("periodo_ya_presentado", ERROR, f"El 390 de {ejercicio.anio} ya está presentado: sólo se puede rectificar con una declaración sustitutiva", "390")
    elif tipo_presentacion == "sustitutiva":
        if previa is None:
            hallazgo("rectificativa_sin_presentada", ERROR, f"No hay un 390 de {ejercicio.anio} presentado que sustituir", "390")
        elif not JUSTIFICANTE_VALIDO.fullmatch((previa.justificante or "").strip()):
            hallazgo("falta_justificante_anterior", ERROR, "El 390 que se sustituye no tiene un nº de justificante de 13 dígitos: el fichero de una sustitutiva lo lleva", "390")

    # datos fijos de la ficha de la empresa
    if not (empresa.nif or "").strip():
        hallazgo("falta_nif", ERROR, "Falta el NIF de la empresa")
    if not empresa.actividades:
        hallazgo("falta_actividad", ERROR, "Falta la actividad principal: se escribe en la ficha de la empresa («Actividades (modelo 390)»)")
    elif len(empresa.actividades) > MAX_ACTIVIDADES:
        hallazgo("demasiadas_actividades", ERROR, f"El 390 admite {MAX_ACTIVIDADES} actividades como máximo")
    if not empresa.representantes:
        hallazgo("falta_representante", ERROR, "Falta al menos un representante con poder: se escribe en la ficha de la empresa («Representantes con poder (modelo 390)»)")
    elif len(empresa.representantes) > MAX_REPRESENTANTES:
        hallazgo("demasiados_representantes", ERROR, f"El 390 admite {MAX_REPRESENTANTES} representantes como máximo")
    for r in empresa.representantes:
        if not r.fecha_poder or not (r.notaria or "").strip():
            hallazgo("poder_incompleto", AVISO, f"{r.nombre}: faltan en la ficha la fecha del poder o la notaría", r.nif or "")

    # lo que dice el cálculo y la contabilidad del año
    for k in calculo.controles:
        if k.gravedad != "ok":
            hallazgo("control_contra_los_303", ERROR if k.gravedad == "error" else AVISO, k.texto)
    for aviso in calculo.avisos:
        hallazgo("aviso_del_calculo", AVISO, aviso)
    en_el_ano = {a.identificador for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ejercicio.id))}
    for h in auditoria.asientos_descuadrados(sesion, ejercicio):
        if h.referencia in en_el_ano:
            hallazgos.append(h)

    p, dia = plazo(MODELO, ejercicio.anio), hoy()
    if tipo_presentacion == "normal":
        if dia < p.inicio:
            hallazgo("presentacion_antes_de_plazo", AVISO, f"El plazo de presentación empieza el {p.inicio:%d/%m/%Y}: hasta entonces no se puede presentar en la sede", "390")
        elif dia > p.fin:
            hallazgo("presentacion_fuera_de_plazo", AVISO, f"El plazo de presentación terminó el {p.fin:%d/%m/%Y}: presentarlo ahora es extemporáneo y puede llevar recargo", "390")
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def crear_borrador(sesion: Session, ejercicio: Ejercicio, *, tipo_presentacion: str = "normal", usuario: str | None = None) -> tuple[PresentacionAeat, list[Hallazgo]]:
    empresa = ejercicio.empresa
    previa = lo_anterior(sesion, empresa.id, ejercicio.anio, tipo_presentacion)
    calculo = calcular_390(sesion, ejercicio)
    hallazgos = controlar_390(sesion, ejercicio, calculo, tipo_presentacion=tipo_presentacion)
    bloqueantes = [h for h in hallazgos if h.codigo in BLOQUEANTES]
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
        resultado=calculo.casillas.get(86, CERO), casillas=json.dumps(instantanea(empresa, calculo)), domiciliar=False, anterior_id=previa.id if isinstance(previa, PresentacionAeat) else None, creada_por=quien,
    )
    p.eventos.append(PresentacionEvento(usuario=quien, evento="creada", detalle=f"resultado de la liquidación anual {calculo.casillas.get(86, CERO)}"))
    sesion.add(p)
    sesion.flush()
    return p, hallazgos


def generar_fichero(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, usuario: str | None = None) -> Path:
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede volver a generar")
    empresa = ejercicio.empresa
    previa = lo_anterior(sesion, empresa.id, ejercicio.anio, presentacion.tipo_presentacion)
    calculo = calcular_390(sesion, ejercicio)
    if instantanea(empresa, calculo) != json.loads(presentacion.casillas or "{}"):
        raise ErrorContable("Los asientos o los datos de la ficha han cambiado desde que se creó el borrador: guarde el borrador de nuevo")
    errores = [h.mensaje for h in controlar_390(sesion, ejercicio, calculo, tipo_presentacion=presentacion.tipo_presentacion) if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    declaracion = fichero390.desde_calculo(empresa, calculo, sustitutiva=previa is not None, justificante_anterior=(previa.justificante or "").strip() if previa is not None else "")
    datos = generar(declaracion).encode(CODIFICACION)
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, "390", ejercicio.anio, presentacion.periodo, presentacion.tipo_presentacion, "390")
    ruta = carpeta / f"{presentacion.id}_{nombre}"
    ruta.write_bytes(datos)
    quien = usuario or _usuario()
    presentacion.estado = GENERADA
    presentacion.diseno_version, presentacion.diseno_sha256 = DISENO_VERSION, DISENO_SHA256
    presentacion.fichero_nombre, presentacion.fichero_sha256 = nombre, hashlib.sha256(datos).hexdigest()
    presentacion.fichero_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    presentacion.eventos.append(PresentacionEvento(usuario=quien, evento="fichero_generado", detalle=f"{nombre} · {len(datos)} bytes", momento=datetime.now()))
    sesion.flush()
    return ruta


def registrar(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, pdf: bytes, **kw) -> PresentacionAeat:
    """Registra la presentación con el PDF de la sede (de él se leen el justificante, el CSV y la fecha; el justificante lo asigna la sede)."""
    return registrar_presentacion(sesion, ejercicio, presentacion, raiz_almacen, pdf=pdf, **kw)
