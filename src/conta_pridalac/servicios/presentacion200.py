"""Controles y fichero del modelo 200 (Impuesto sobre Sociedades) para la sede de la AEAT.

Sobre el generador (`impuesto_sociedades_200`) añade lo que necesita para entregarse: los controles previos (lo que impide generar, lo que hay que mirar), el fichero guardado en el almacén con
su huella y el registro de la presentación (`PresentacionAeat`, modelo «200», periodo «0A»). El registro de la presentación con el PDF de la sede viene cuando haya diseño del ejercicio 2026:
hoy solo hay diseño de 2025, que ya está presentado con el programa anterior, así que el fichero sirve para **validarlo en la sede, no para presentarlo de nuevo**.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import DESCARTADA, GENERADA, PRESENTADA, DeclaracionPresentada, Ejercicio, PresentacionAeat, PresentacionEvento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero200
from conta_pridalac.ficheros_aeat.fichero200 import CODIFICACION, DISENO_SHA256, DISENO_VERSION
from conta_pridalac.servicios import impuesto_sociedades_200 as gen
from conta_pridalac.servicios import impuesto_sociedades_datos as isd
from conta_pridalac.servicios.entorno import exigir_base_real
from conta_pridalac.servicios.exportar import nombre_para_presentar
from conta_pridalac.servicios.presentacion303 import _usuario

MODELO = "200"
PERIODO = "0A"
CERO = Decimal("0.00")


def _hallazgo(lista: list[Hallazgo], codigo: str, gravedad: str, mensaje: str) -> None:
    lista.append(Hallazgo(codigo, gravedad, mensaje, MODELO))


def controlar_200(sesion: Session, ejercicio: Ejercicio, datos: isd.DatosIS | None = None) -> list[Hallazgo]:
    """Lo que impide generar el fichero (ERROR) y lo que conviene mirar antes de usarlo (AVISO)."""
    hallazgos: list[Hallazgo] = []
    empresa = ejercicio.empresa
    datos = datos if datos is not None else isd.datos_del_ejercicio(sesion, ejercicio)
    if ejercicio.anio != fichero200.EJERCICIO:
        _hallazgo(hallazgos, "sin_diseno_del_ejercicio", ERROR, f"Solo hay diseño del modelo 200 de {fichero200.EJERCICIO}: el de {ejercicio.anio} no se publica hasta la primavera siguiente")
        return hallazgos
    if not (empresa.nif or "").strip() or not (empresa.nombre or "").strip():
        _hallazgo(hallazgos, "falta_dato_de_la_empresa", ERROR, "Faltan el NIF o el nombre de la empresa en su ficha")
    # lo que el generador todavía no escribe en el fichero: se rechaza para no presentar una declaración incoherente
    if any(c.aumento or c.disminucion for c in datos.correcciones):
        _hallazgo(hallazgos, "correccion_manual_sin_casilla", ERROR, "Las correcciones manuales al resultado todavía no tienen casilla asignada en el fichero: la base imponible no cuadraría con el detalle. Quítelas o pídalo")
    if any((datos.reinversion, datos.donativos, datos.deducciones)):
        _hallazgo(hallazgos, "apartados_opcionales_sin_generar", ERROR, "La reinversión de beneficios, los donativos y las deducciones todavía no se escriben en el fichero")
    p = isd.precalculo(sesion, ejercicio, datos)
    resultado_aprox = p.cuota_integra - sum(datos.retenciones.values(), CERO) - sum(gen.pagos_fraccionados(sesion, ejercicio).values(), CERO)
    if resultado_aprox < 0 and not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", (empresa.iban or "").replace(" ", "").upper()):
        _hallazgo(hallazgos, "devolucion_sin_iban", ERROR, "Sale a devolver y la ficha de la empresa no tiene un IBAN válido para la devolución")
    if resultado_aprox > 0:
        _hallazgo(hallazgos, "resultado_a_ingresar_sin_contrastar", AVISO, "Sale a ingresar: la página de domiciliación no se ha contrastado con ningún fichero real; valídelo en la sede antes de presentar")
    if p.tipo.marcar_00088:
        _hallazgo(hallazgos, "tipo_reducido_de_microempresa", AVISO, f"Se aplica el tipo reducido de microempresas ({p.tipo.campo[:2]} % / {p.tipo.campo[2:]} %). Confirme que la entidad no es patrimonial (casilla 00066) o fuerce el 25 %")
    elif not datos.forzar_25 and not datos.patrimonial:
        _hallazgo(hallazgos, "tipo_general", AVISO, f"Se aplica el tipo general del 25 %: {p.tipo.motivo}")
    if not ejercicio.cerrado:
        _hallazgo(hallazgos, "ejercicio_sin_cerrar", AVISO, "El ejercicio todavía está abierto: las cifras pueden cambiar")
    ya = sesion.scalar(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == ejercicio.empresa_id, DeclaracionPresentada.modelo == MODELO, DeclaracionPresentada.anio == ejercicio.anio))
    if ya is not None:
        _hallazgo(hallazgos, "ya_presentado", AVISO, f"El Impuesto sobre Sociedades de {ejercicio.anio} ya consta presentado (resultado {ya.resultado} €): este fichero sirve para comprobarlo en la sede, no para presentarlo de nuevo")
    if not empresa.representantes:
        _hallazgo(hallazgos, "sin_representantes", AVISO, "La ficha no tiene representantes con poder: la relación de administradores y los representantes legales irán vacíos")
    if not (datos.contacto_nombre or empresa.presentador_nombre):
        _hallazgo(hallazgos, "sin_persona_de_contacto", AVISO, "No hay persona de contacto para incidencias (ni en los datos de cierre ni en el presentador de la ficha)")
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo))


def hay_errores(hallazgos: list[Hallazgo]) -> bool:
    return any(h.gravedad == ERROR for h in hallazgos)


def generar_fichero(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, con_correcciones_automaticas: bool = True, usuario: str | None = None) -> tuple[PresentacionAeat, Path, list[str]]:
    """Genera el fichero, lo guarda en el almacén y lo registra como la presentación generada del ejercicio (las generadas antes quedan descartadas). Devuelve (presentación, ruta, avisos del generador)."""
    exigir_base_real(sesion, ejercicio.empresa_id, "generar el fichero para la sede")
    errores = [h.mensaje for h in controlar_200(sesion, ejercicio) if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede generar el fichero: " + "; ".join(errores))
    fichero = gen.generar(sesion, ejercicio, con_correcciones_automaticas=con_correcciones_automaticas)
    texto = fichero.escribir()
    if fichero200.Fichero200.leer(texto).escribir() != texto:  # lo que se guarda se lee igual: si no, el diseño y el generador no coinciden
        raise ErrorContable("El fichero generado no se lee igual que se escribió: no se guarda")
    datos = texto.encode(CODIFICACION)
    empresa, quien = ejercicio.empresa, usuario or _usuario()
    ident = next(p for p in fichero.paginas if p.codigo == "01000")
    liquidacion = next(p for p in fichero.paginas if p.codigo == "14B00")
    resultado = liquidacion.importe(liquidacion.n_de_casilla(621))
    for antigua in sesion.scalars(select(PresentacionAeat).where(PresentacionAeat.empresa_id == empresa.id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == ejercicio.anio,
                                                                 PresentacionAeat.estado == GENERADA)):
        antigua.estado = DESCARTADA
        antigua.eventos.append(PresentacionEvento(usuario=quien, evento="descartada", detalle="Sustituida por un fichero nuevo", momento=datetime.now()))
    p = PresentacionAeat(empresa_id=empresa.id, modelo=MODELO, anio=ejercicio.anio, periodo=PERIODO, estado=GENERADA, tipo_presentacion="normal", tipo_declaracion=ident.texto(6), resultado=resultado,
                         casillas=json.dumps({"resultado": str(resultado), "paginas": [x.codigo for x in fichero.paginas]}), domiciliar=False, creada_por=quien)
    sesion.add(p)
    sesion.flush()
    carpeta = Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(ejercicio.anio) / "aeat"
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_para_presentar(empresa, MODELO, ejercicio.anio, PERIODO, "normal", "200")
    ruta = carpeta / f"{p.id}_{nombre}"
    ruta.write_bytes(datos)
    p.diseno_version, p.diseno_sha256 = DISENO_VERSION, DISENO_SHA256
    p.fichero_nombre, p.fichero_sha256 = nombre, hashlib.sha256(datos).hexdigest()
    p.fichero_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    p.eventos.append(PresentacionEvento(usuario=quien, evento="fichero_generado", detalle=f"{nombre} · {len(datos)} bytes · {len(fichero.paginas)} páginas · diseño {DISENO_VERSION}", momento=datetime.now()))
    sesion.flush()
    return p, ruta, fichero.avisos


def ultima_generada(sesion: Session, empresa_id: int, anio: int) -> PresentacionAeat | None:
    return sesion.scalar(select(PresentacionAeat).where(PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == MODELO, PresentacionAeat.anio == anio,
                                                        PresentacionAeat.fichero_ruta.is_not(None), PresentacionAeat.estado.in_((GENERADA, PRESENTADA))).order_by(PresentacionAeat.id.desc()))
