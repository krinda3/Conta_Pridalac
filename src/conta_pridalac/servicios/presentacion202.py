"""Borrador del modelo 202 (pago fraccionado del Impuesto sobre Sociedades, art. 40.2 LIS), sus controles y su fichero (el mismo molde que el 111).

La base sale del último IS presentado cuyo plazo estuviera vencido el día 1 del periodo (`servicios/impuesto_sociedades.py`): cuota íntegra menos deducciones y retenciones. El pago es el 18 % de la base. El CNAE va en blanco, como en los 202 del programa anterior que la sede aceptó (desde 2026 pide el CNAE-2025 y el de la ficha puede ser aún el de 2009). Lo propio
del 202: tres periodos al año (1P abril, 2P octubre y 3P diciembre, del 1 al 20), que el periodo se guarda como «1P»… «3P», que si el resultado es cero el fichero va con el tipo N («negativa o resultado cero») y que
la rectificación es la declaración **complementaria** (con el nº de justificante y el resultado de la anterior).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import BORRADOR, DESCARTADA, GENERADA, DeclaracionPresentada, Ejercicio, PresentacionAeat, PresentacionEvento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat.fichero202 import CODIFICACION, DISENO_SHA256, DISENO_VERSION, Declaracion202, generar, pago
from conta_pridalac.servicios import impuesto_sociedades as isoc
from conta_pridalac.servicios.entorno import exigir_base_real
from conta_pridalac.servicios.plazos import plazo
from conta_pridalac.servicios.presentacion303 import JUSTIFICANTE_VALIDO, NRC_VALIDO, _usuario, hoy, importe_del_nrc, presentada_del_periodo

MODELO = "202"
TIPOS_DE_PRESENTACION = ("normal", "complementaria")
CERO = Decimal("0.00")
BLOQUEANTES = ("periodo_ya_presentado", "rectificativa_sin_presentada", "tipo_de_presentacion_desconocido", "falta_el_is_de_referencia")
TIPO_GRAVAMEN_POR_DEFECTO = "25"


@dataclass
class Calculo202:
    anio: int
    periodo: int
    anio_is: int  # el IS en que se apoya
    referencia: DeclaracionPresentada | None
    base: Decimal
    pago: Decimal  # el 18 % de la base (antes de restar lo ya ingresado si es complementaria)


def etiqueta(periodo: int) -> str:
    return f"{periodo}P"


def calcular_202(sesion: Session, ejercicio: Ejercicio, periodo: int) -> Calculo202:
    if periodo not in (1, 2, 3):
        raise ErrorContable("El 202 tiene tres pagos fraccionados: periodo 1 a 3")
    referencia = isoc.is_de_referencia(sesion, ejercicio.empresa_id, ejercicio.anio, periodo)
    anio_is = ejercicio.anio - 1 if periodo >= 2 else ejercicio.anio - 2
    base = isoc.base_de(referencia) if referencia is not None else CERO
    return Calculo202(ejercicio.anio, periodo, anio_is, referencia, base, pago(base))


def tipo_de_declaracion(a_ingresar: Decimal, *, domiciliar: bool) -> str:
    """N negativa / resultado cero · U domiciliación · I ingreso (con NRC)."""
    if a_ingresar <= 0:
        return "N"
    return "U" if domiciliar else "I"


def lo_anterior(sesion: Session, empresa_id: int, anio: int, periodo: int, tipo_presentacion: str):
    """Para una complementaria: (declaración que se complementa, lo que ingresó —casilla [03]—). `(None, CERO)` si es normal o no hay nada presentado."""
    if tipo_presentacion == "normal":
        return None, CERO
    previa = presentada_del_periodo(sesion, empresa_id, anio, periodo, MODELO)
    if previa is None:
        return None, CERO
    casillas = json.loads(previa.casillas or "{}")
    return previa, Decimal(str(casillas["3"])) if "3" in casillas else previa.resultado


def a_ingresar_de(calculo: Calculo202, anterior: Decimal) -> Decimal:
    return calculo.pago - anterior


def instantanea(calculo: Calculo202, anterior: Decimal, empresa) -> dict:
    """Lo que se congela en el borrador: el IS en que se apoya, la base y lo que va al fichero desde la ficha de la empresa."""
    return {
        "anio_is": calculo.anio_is, "base": str(calculo.base), "pago": str(calculo.pago), "anterior": str(anterior),
        "tipo_gravamen": (empresa.is_tipo_gravamen or TIPO_GRAVAMEN_POR_DEFECTO).strip(), "cifra_menor_1m": bool(empresa.is_cifra_menor_1m),
    }


def controlar_202(
    sesion: Session, ejercicio: Ejercicio, periodo: int, calculo: Calculo202, *, tipo_presentacion: str = "normal", anterior: Decimal = CERO, domiciliar: bool = True,
    nrc: str | None = None, nrc_importe: Decimal | None = None,
) -> list[Hallazgo]:
    empresa, hallazgos = ejercicio.empresa, []
    ref = f"{periodo}P"

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    previa = presentada_del_periodo(sesion, empresa.id, ejercicio.anio, periodo, MODELO)
    if tipo_presentacion not in TIPOS_DE_PRESENTACION:
        hallazgo("tipo_de_presentacion_desconocido", ERROR, f"Tipo de presentación desconocido: {tipo_presentacion}")
    elif tipo_presentacion == "normal" and previa is not None:
        hallazgo("periodo_ya_presentado", ERROR, f"El {ref} {ejercicio.anio} del 202 ya está presentado: sólo se puede rectificar con una declaración complementaria", ref)
    elif tipo_presentacion == "complementaria":
        if previa is None:
            hallazgo("rectificativa_sin_presentada", ERROR, f"No hay un 202 del {ref} {ejercicio.anio} presentado que complementar", ref)
        elif not JUSTIFICANTE_VALIDO.fullmatch((previa.justificante or "").strip()):
            hallazgo("falta_justificante_anterior", ERROR, "El 202 que se complementa no tiene un nº de justificante de 13 dígitos: el fichero de una complementaria lo lleva", ref)
        if calculo.pago - anterior < 0:
            hallazgo("complementaria_con_menos_pago", ERROR, f"La complementaria sale con {calculo.pago - anterior}: ya se ingresó más de lo que corresponde. Eso no se corrige con una complementaria del 202", ref)

    if calculo.referencia is None:
        hallazgo("falta_el_is_de_referencia", ERROR, f"No consta el Impuesto sobre Sociedades de {calculo.anio_is}, en el que se apoya el pago del {ref} {ejercicio.anio}: impórtelo (herramienta tools/importar_is.py) con el fichero .200 presentado", "200")
    if not (empresa.nif or "").strip():
        hallazgo("falta_nif", ERROR, "Falta el NIF de la empresa")
    if not empresa.is_cifra_menor_1m:
        hallazgo("cifra_de_negocios_no_inferior_a_1m", AVISO, "La ficha dice que la cifra de negocios del periodo anterior no es inferior a un millón de euros: el fichero no lleva esa marca. Si pasa de 10 millones el 202 es de la modalidad del art. 40.3 LIS, que este programa no prepara")

    p, dia = plazo(MODELO, ejercicio.anio, periodo), hoy()
    if tipo_presentacion == "normal":
        if dia < p.inicio:
            hallazgo("presentacion_antes_de_plazo", AVISO, f"El plazo de presentación empieza el {p.inicio:%d/%m/%Y}: hasta entonces no se puede presentar en la sede", ref)
        elif dia > p.fin:
            hallazgo("presentacion_fuera_de_plazo", AVISO, f"El plazo de presentación terminó el {p.fin:%d/%m/%Y}: presentarlo ahora es extemporáneo y puede llevar recargo", ref)
    a_ingresar = calculo.pago - anterior
    if a_ingresar > 0 and domiciliar:
        if not (empresa.iban or "").strip():
            hallazgo("domiciliacion_sin_iban", ERROR, "Para domiciliar el pago hace falta el IBAN de la empresa (ficha de la empresa)")
        if dia > p.fin_domiciliacion:
            hallazgo("domiciliacion_fuera_de_plazo", ERROR if p.confirmado else AVISO,
                     f"El plazo para domiciliar terminó el {p.fin_domiciliacion:%d/%m/%Y}{'' if p.confirmado else ' (fecha estimada)'}: elija pagar con NRC", ref)
    if nrc and not NRC_VALIDO.fullmatch(nrc):
        hallazgo("nrc_no_valido", ERROR, "El NRC son 22 caracteres (letras mayúsculas y números)")
    elif a_ingresar > 0 and not domiciliar and not nrc:
        hallazgo("nrc_pendiente", AVISO, "Falta el NRC: se obtiene pagando en la sede de la AEAT («Pago mediante cargo en cuenta») con el importe exacto, y hay que tenerlo para presentar", ref)
    elif nrc and (a_ingresar <= 0 or domiciliar):
        hallazgo("nrc_sin_importe_a_ingresar", AVISO, "Se ha indicado un NRC pero este periodo no se paga con NRC", ref)
    elif nrc and nrc_importe is not None and nrc_importe != a_ingresar:
        hallazgo("nrc_de_otro_importe", ERROR, f"El NRC se anotó cuando el resultado era {nrc_importe} y ahora es {a_ingresar}: un NRC sólo vale para el importe exacto con el que se pagó", ref)
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


def crear_borrador(
    sesion: Session, ejercicio: Ejercicio, periodo: int, *, tipo_presentacion: str = "normal", domiciliar: bool = True, nrc: str | None = None, usuario: str | None = None,
) -> tuple[PresentacionAeat, list[Hallazgo]]:
    """Calcula el 202 del periodo y guarda un borrador con lo calculado congelado (sustituye al borrador anterior del mismo periodo)."""
    empresa = ejercicio.empresa
    previa, anterior = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, tipo_presentacion)
    calculo = calcular_202(sesion, ejercicio, periodo)
    a_ingresar = a_ingresar_de(calculo, anterior)
    importe_nrc = importe_del_nrc(sesion, empresa.id, ejercicio.anio, periodo, nrc, a_ingresar, MODELO)
    hallazgos = controlar_202(sesion, ejercicio, periodo, calculo, tipo_presentacion=tipo_presentacion, anterior=anterior, domiciliar=domiciliar, nrc=nrc, nrc_importe=importe_nrc)
    bloqueantes = [h for h in hallazgos if h.codigo in BLOQUEANTES]
    if bloqueantes:
        raise ErrorContable(bloqueantes[0].mensaje)
    quien = usuario or _usuario()
    for antiguo in sesion.scalars(select(PresentacionAeat).where(
        PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ejercicio.anio, PresentacionAeat.periodo == etiqueta(periodo),
        PresentacionAeat.estado.in_((BORRADOR, GENERADA)),
    )):
        if antiguo.estado == BORRADOR:
            sesion.delete(antiguo)
        else:
            antiguo.estado = DESCARTADA
            antiguo.eventos.append(PresentacionEvento(usuario=quien, evento="descartada", detalle="Sustituida por un borrador nuevo", momento=datetime.now()))
    p = PresentacionAeat(
        empresa_id=empresa.id, modelo=MODELO, anio=ejercicio.anio, periodo=etiqueta(periodo), estado=BORRADOR, tipo_presentacion=tipo_presentacion,
        tipo_declaracion=tipo_de_declaracion(a_ingresar, domiciliar=domiciliar), resultado=a_ingresar, casillas=json.dumps(instantanea(calculo, anterior, empresa)),
        domiciliar=domiciliar, nrc=(nrc or None), nrc_importe=importe_nrc, anterior_id=previa.id if isinstance(previa, PresentacionAeat) else None, creada_por=quien,
    )
    p.eventos.append(PresentacionEvento(usuario=quien, evento="creada", detalle=f"base {calculo.base} (IS {calculo.anio_is}); a ingresar {a_ingresar}"))
    sesion.add(p)
    sesion.flush()
    return p, hallazgos


def generar_fichero(sesion: Session, ejercicio: Ejercicio, presentacion: PresentacionAeat, raiz_almacen: Path, *, usuario: str | None = None) -> Path:
    """Genera el fichero del 202 de un borrador y lo guarda en el almacén (`<empresa>/<año>/aeat/`) con su huella y la versión del diseño. Vuelve a calcular y a controlar."""
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    if presentacion.estado not in (BORRADOR, GENERADA):
        raise ErrorContable(f"Una presentación {presentacion.estado} no se puede volver a generar")
    empresa, periodo = ejercicio.empresa, int(presentacion.periodo[0])
    previa, anterior = lo_anterior(sesion, empresa.id, ejercicio.anio, periodo, presentacion.tipo_presentacion)
    calculo = calcular_202(sesion, ejercicio, periodo)
    if instantanea(calculo, anterior, empresa) != json.loads(presentacion.casillas or "{}"):
        raise ErrorContable("El IS de referencia o los datos de la ficha han cambiado desde que se creó el borrador: guarde el borrador de nuevo")
    hallazgos = controlar_202(sesion, ejercicio, periodo, calculo, tipo_presentacion=presentacion.tipo_presentacion, anterior=anterior, domiciliar=presentacion.domiciliar,
                              nrc=presentacion.nrc, nrc_importe=presentacion.nrc_importe)
    errores = [h.mensaje for h in hallazgos if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    a_ingresar = a_ingresar_de(calculo, anterior)
    tipo = tipo_de_declaracion(a_ingresar, domiciliar=presentacion.domiciliar)
    declaracion = Declaracion202(
        nif=(empresa.nif or "").strip(), nombre=empresa.nombre, ejercicio=ejercicio.anio, periodo=periodo, inicio=ejercicio.fecha_inicio, base=calculo.base, a_ingresar=a_ingresar, tipo=tipo,
        tipo_gravamen=(empresa.is_tipo_gravamen or TIPO_GRAVAMEN_POR_DEFECTO).strip(), cifra_menor_1m=bool(empresa.is_cifra_menor_1m),
        iban=(empresa.iban or "").replace(" ", "") if tipo == "U" else "", complementaria=previa is not None, justificante_anterior=(previa.justificante or "").strip() if previa is not None else "",
        resultado_anterior=anterior if previa is not None else CERO,
    )
    datos = generar(declaracion).encode(CODIFICACION)
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, "202", ejercicio.anio, presentacion.periodo, presentacion.tipo_presentacion, "202")
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
