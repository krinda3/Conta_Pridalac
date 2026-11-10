"""Legalización de los libros en el Registro Mercantil: prepara lo que Legalia2 importa (el ZIP con los libros) a partir de la contabilidad.

Se generan los PDF de los cuatro libros: el **diario**, el **inventario y cuentas anuales** (balances de sumas y saldos del inicio, de cada trimestre y del inventario, más la memoria), el **registro de socios**
y el **registro de actas**. El ZIP con `DATOS.TXT` y `NOMBRES.TXT` para Legalia2 sale de esos mismos libros. Nada se envía desde aquí: Legalia2 firma y presenta.
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac import auditoria
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import ENVIADA, PREPARADA, Acta, DeclaracionPresentada, Ejercicio, Empresa, Legalizacion, LibroLegalizacion, Socio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.memoria_pymes import TEXTO
from conta_pridalac.exportacion import libros_pdf as pdf
from conta_pridalac.servicios.informes import balance_sumas_y_saldos, libro_diario
from conta_pridalac.servicios.presentacion303 import _usuario

CERO = Decimal("0.00")
# (orden, clave, nombre en DATOS.TXT, prefijo del PDF)
LIBROS = (
    (1, "diario", "Diario", "DIARIO"),
    (2, "inventario", "Inventario y cuentas anuales", "INV_CUEN"),
    (3, "socios", "Libro registro de socios", "SOCIOS"),
    (4, "actas", "Libro registro de actas", "ACTASCON"),
)
GENERADOS = ("diario", "inventario", "socios", "actas")  # los cuatro se generan desde Conta
SUBE_CADA_ANIO = ("diario", "inventario")  # los demás conservan su número de libro
NIVELES = (1, 2, 3, 4)


def nombre_fichero(prefijo: str, numero: int) -> str:
    return f"{prefijo}_{numero:03d}.PDF"


def carpeta_de_libros(raiz_almacen: Path, empresa: Empresa, anio: int) -> Path:
    return Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(anio) / "libros"


# ---------------------------------------------------------------------------------------------- números de libro

def numeros_propuestos(sesion: Session, empresa_id: int, anio: int) -> dict[str, tuple[int, date | None]]:
    """Por libro: (nº de libro, fin del ejercicio de la legalización anterior). El diario y el inventario suben uno cada año; los de socios y actas siguen con el suyo."""
    resultado: dict[str, tuple[int, date | None]] = {}
    for _, clave, _, _ in LIBROS:
        previo = sesion.execute(
            select(LibroLegalizacion.numero, Legalizacion.anio).join(Legalizacion, Legalizacion.id == LibroLegalizacion.legalizacion_id)
            .where(Legalizacion.empresa_id == empresa_id, Legalizacion.anio < anio, LibroLegalizacion.clave == clave).order_by(Legalizacion.anio.desc()).limit(1)
        ).first()
        if previo is None:
            resultado[clave] = (1, None)
        else:
            resultado[clave] = (previo[0] + 1 if clave in SUBE_CADA_ANIO else previo[0], date(previo[1], 12, 31))
    return resultado


# ---------------------------------------------------------------------------------------------- datos de la empresa

def cabecera_de(empresa: Empresa) -> pdf.Cabecera:
    cp_poblacion = " ".join(x for x in ((empresa.codigo_postal or "").strip(), (empresa.poblacion or "").strip()) if x)
    return pdf.Cabecera((empresa.domicilio or "").strip(), cp_poblacion, (empresa.provincia or "").strip(), (empresa.nif or "").strip(), empresa.nombre.strip())


def _falta(valor) -> bool:
    return not (valor or "").strip()


def controlar(sesion: Session, ejercicio: Ejercicio, almacen=None) -> list[Hallazgo]:
    """Lo que falta o no cuadra antes de preparar los libros. Los errores impiden generarlos."""
    empresa, hallazgos = ejercicio.empresa, []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    if not ejercicio.cerrado:
        hallazgo("ejercicio_sin_cerrar", ERROR, f"El ejercicio {ejercicio.anio} no está cerrado: los libros se legalizan con el ejercicio cerrado (regularización y cierre hechos)", str(ejercicio.anio))
    for campo, nombre in (("nif", "el NIF"), ("domicilio", "el domicilio"), ("codigo_postal", "el código postal"), ("poblacion", "la población"), ("provincia", "la provincia")):
        if _falta(getattr(empresa, campo)):
            hallazgo("falta_dato_de_la_empresa", ERROR, f"Falta {nombre} de la empresa (ficha de la empresa)", campo)
    for campo, nombre in (("registro_provincia", "el Registro Mercantil"), ("registro_tomo", "el tomo"), ("registro_folio", "el folio"), ("registro_hoja", "la hoja")):
        if _falta(getattr(empresa, campo)):
            hallazgo("falta_dato_del_registro", AVISO, f"Falta {nombre} de la inscripción en el Registro Mercantil (ficha de la empresa): hace falta para el ZIP de Legalia2", campo)
    for campo, nombre in (("municipio_ine", "el código INE del municipio"), ("provincia_ine", "el código INE de la provincia"), ("presentador_nombre", "el nombre de quien presenta"),
                          ("presentador_apellido1", "el primer apellido de quien presenta"), ("presentador_nif", "el NIF de quien presenta"), ("presentador_email", "el correo de quien presenta")):
        if _falta(getattr(empresa, campo)):
            hallazgo("falta_dato_de_legalia", AVISO, f"Falta {nombre} (ficha de la empresa, «Registro Mercantil: legalización de libros»): hace falta para el ZIP de Legalia2", campo)
    # la contabilidad
    errores = [h for h in auditoria.auditar(sesion, ejercicio, almacen=almacen) if h.gravedad == ERROR]
    if errores:
        hallazgo("auditoria_con_errores", ERROR, f"La auditoría de {ejercicio.anio} tiene {len(errores)} error(es): arréglelos antes de legalizar (pantalla «Auditoría de integridad»)", "auditoria")
    sin_numero = sum(1 for a in libro_diario(sesion, ejercicio).asientos if a.numero_diario is None)
    if sin_numero:
        hallazgo("asientos_sin_numero_de_diario", ERROR, f"{sin_numero} asiento(s) sin número de diario: el libro diario necesita numeración correlativa", "diario")
    socios, capital_socios = socios_del_libro(sesion, empresa, ejercicio.fecha_fin)
    if not socios:
        hallazgo("sin_socios", ERROR, "No hay socios en el libro registro de socios (pantalla «Libro de socios»)", "socios")
    elif capital_socios != capital_social(sesion, ejercicio):
        hallazgo("capital_distinto_del_de_socios", AVISO, f"El capital del libro de socios ({pdf.eur(capital_socios)} €) no coincide con el de la contabilidad, cuenta 100 ({pdf.eur(capital_social(sesion, ejercicio))} €)", "socios")
    if not actas_del_ejercicio(sesion, ejercicio):
        hallazgo("sin_actas", ERROR, (f"No hay ningún acta con fecha dentro del ejercicio {ejercicio.anio}: el libro de actas de {ejercicio.anio} lleva las reuniones celebradas en {ejercicio.anio} (la de marzo de {ejercicio.anio}, "
                                      f"que aprobó las cuentas de {ejercicio.anio - 1}). Créela en la pantalla «Libro de actas» con el ejercicio {ejercicio.anio} abierto"), "actas")
    anterior = sesion.scalar(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id, Ejercicio.anio == ejercicio.anio - 1))
    if anterior is not None and not anterior.cerrado:
        hallazgo("ejercicio_anterior_sin_cerrar", AVISO, f"El ejercicio {anterior.anio} no está cerrado: el balance inicial de {ejercicio.anio} puede cambiar", str(anterior.anio))
    previa = sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == empresa.id, Legalizacion.anio == ejercicio.anio))
    if previa is not None and previa.estado == ENVIADA:
        hallazgo("ya_enviada", ERROR, f"Los libros de {ejercicio.anio} ya constan enviados al Registro Mercantil", str(ejercicio.anio))
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


# ---------------------------------------------------------------------------------------------- contenido de los libros

CONCEPTO_DE_LOS_AUTOMATICOS = {"A": "Apertura del ejercicio", "R": "Regularización de ingresos y gastos", "Z": "Cierre del ejercicio"}


def asientos_del_diario(sesion: Session, ejercicio: Ejercicio) -> list[pdf.AsientoDiario]:
    """Los asientos del ejercicio para el libro diario; los de apertura, regularización y cierre sin concepto llevan el suyo."""
    resultado = []
    for a in libro_diario(sesion, ejercicio).asientos:
        automatico = a.subtipo in CONCEPTO_DE_LOS_AUTOMATICOS  # en la apertura, la regularización y el cierre todas las líneas llevan el concepto del asiento
        por_defecto = CONCEPTO_DE_LOS_AUTOMATICOS.get(a.subtipo or "", "")
        resultado.append(pdf.AsientoDiario(a.numero_diario or 0, a.fecha, [
            pdf.LineaAsiento(ap.cuenta.codigo, ap.cuenta.nombre, (a.concepto or por_defecto) if automatico else (ap.concepto or a.concepto or ""), ap.debe, ap.haber) for ap in a.apuntes]))
    return resultado


def _texto_de(valor: str | None) -> str:
    return (valor or "").strip()


def socios_del_libro(sesion: Session, empresa: Empresa, hasta: date) -> tuple[list[pdf.SocioLibro], Decimal]:
    """Los socios con participaciones a la fecha `hasta`, con sus movimientos hasta esa fecha, y el capital social que suman."""
    por_socio = []
    for s in sesion.scalars(select(Socio).where(Socio.empresa_id == empresa.id).order_by(Socio.orden, Socio.id)):
        movimientos = [pdf.MovimientoLibro(m.fecha, m.tipo, _texto_de(m.concepto), m.participaciones, m.desde, m.hasta, m.valor_nominal,
                                           (m.participaciones * Decimal(m.valor_nominal)).quantize(Decimal("0.01"))) for m in s.movimientos if m.fecha <= hasta]
        if not movimientos:
            continue
        por_socio.append((s, movimientos))
    total = sum(sum(m.participaciones for m in ms) for _, ms in por_socio)
    libros = []
    for s, ms in por_socio:
        propias = sum(m.participaciones for m in ms)
        libros.append(pdf.SocioLibro(
            _texto_de(s.nif), s.nombre, _texto_de(s.nacionalidad), s.fecha_nacimiento.strftime("%d/%m/%Y") if s.fecha_nacimiento else "", _texto_de(s.domicilio), _texto_de(s.poblacion),
            _texto_de(s.provincia), _texto_de(s.profesion), _texto_de(s.estado_civil), ms, propias, sum((m.importe for m in ms), CERO),
            (Decimal(propias) * 100 / total).quantize(Decimal("0.01")) if total else CERO))
    return libros, sum((s.total_importe for s in libros), CERO)


def actas_del_ejercicio(sesion: Session, ejercicio: Ejercicio) -> list[Acta]:
    return list(sesion.scalars(select(Acta).where(Acta.empresa_id == ejercicio.empresa_id, Acta.fecha >= ejercicio.fecha_inicio, Acta.fecha <= ejercicio.fecha_fin).order_by(Acta.fecha, Acta.numero)))


def _lineas(texto: str | None) -> list[str]:
    return [l.strip() for l in (texto or "").splitlines() if l.strip()]


def actas_del_libro(sesion: Session, ejercicio: Ejercicio) -> list[pdf.ActaLibro]:
    empresa, resultado = ejercicio.empresa, []
    for a in actas_del_ejercicio(sesion, ejercicio):
        clase = (a.clase or "Ordinaria").strip()
        resultado.append(pdf.ActaLibro(
            titulo=f"ACTA Nº {a.numero}. Reunión {clase} de la {a.organo}", asistentes=_lineas(a.asistentes),
            apertura=(f"Siendo las {a.hora_inicio or '—'}h del {a.fecha:%d/%m/%Y} se reúnen los arriba citados en sesión {clase.lower()} para tratar el siguiente Orden del Día de la {a.organo} de {empresa.nombre}."),
            orden_del_dia=_lineas(a.orden_del_dia), resumen=_lineas(a.resumen), intervenciones=_lineas(a.intervenciones), acuerdos=_lineas(a.acuerdos), votaciones=_lineas(a.votaciones),
            cierre=(f"No habiendo más asuntos que tratar, se levanta la sesión siendo las {a.hora_fin or '—'}h del día citado, de todo lo cual doy fe como secretario y firmo la presente con el Vº Bº del presidente."),
            presidente=(_texto_de(a.presidente_nombre), _texto_de(a.presidente_nif)), secretario=(_texto_de(a.secretario_nombre), _texto_de(a.secretario_nif))))
    return resultado


def registro_mercantil_texto(empresa: Empresa) -> str:
    return f"{empresa.registro_provincia or '—'} tomo {empresa.registro_tomo or '—'}, folio {empresa.registro_folio or '—'}, hoja {empresa.registro_hoja or '—'}"


def _fin_de_trimestre(inicio: date, trimestre: int) -> date:
    """El último día del trimestre `trimestre` de un ejercicio que empieza en `inicio`."""
    mes0 = inicio.month - 1 + 3 * trimestre
    anio, mes = inicio.year + mes0 // 12, mes0 % 12 + 1
    return date(anio, mes, min(inicio.day, calendar.monthrange(anio, mes)[1])) - timedelta(days=1)


def _seccion(sesion: Session, ejercicio: Ejercicio, titulo: str, **filtros) -> pdf.SeccionSumas:
    digitos = ejercicio.empresa.digitos_cuenta or 8
    filas: dict[str, pdf.FilaSumas] = {}
    for nivel in (*NIVELES, digitos):
        if nivel > digitos:
            continue
        b = balance_sumas_y_saldos(sesion, ejercicio, nivel=nivel, **filtros)
        for f in b.filas:
            if f.debe == 0 and f.haber == 0:
                continue
            filas.setdefault(f.cuenta, pdf.FilaSumas(f.cuenta, f.nombre, f.debe, f.haber, f.saldo_deudor, f.saldo_acreedor, nivel=0 if nivel == digitos else nivel))
    ordenadas = [filas[c] for c in sorted(filas)]
    completas = [f for f in ordenadas if f.nivel == 0]
    totales = (sum((f.debe for f in completas), CERO), sum((f.haber for f in completas), CERO), sum((f.deudor for f in completas), CERO), sum((f.acreedor for f in completas), CERO))
    return pdf.SeccionSumas(titulo, ordenadas, totales)


def secciones_de_sumas_y_saldos(sesion: Session, ejercicio: Ejercicio) -> list[pdf.SeccionSumas]:
    """Inicial (sólo la apertura), acumulado a cada trimestre y del inventario (el ejercicio sin la regularización ni el cierre), como los del programa anterior."""
    anio, sin_cierre = ejercicio.anio, ("R", "Z")
    secciones = [_seccion(sesion, ejercicio, f"Balance de sumas y saldos inicial Ejercicio {anio}", solo_subtipos=("A",))]
    for t in (1, 2, 3, 4):
        secciones.append(_seccion(sesion, ejercicio, f"Balance de sumas y saldos trimestre {t} Ejercicio {anio}", hasta=_fin_de_trimestre(ejercicio.fecha_inicio, t), excluir_subtipos=sin_cierre))
    secciones.append(_seccion(sesion, ejercicio, f"Balance de sumas y saldos inventario Ejercicio {anio}", excluir_subtipos=sin_cierre))
    return secciones


def resultado_contable(sesion: Session, ejercicio: Ejercicio) -> Decimal:
    """Ingresos menos gastos del ejercicio (grupos 7 y 6, sin la regularización)."""
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=1, excluir_subtipos=("R", "Z"))
    return sum((f.haber - f.debe for f in b.filas if f.cuenta in ("6", "7")), CERO)


def base_imponible(sesion: Session, ejercicio: Ejercicio, resultado: Decimal) -> tuple[Decimal, bool]:
    """(base imponible, si es la presentada). Sin el IS presentado del ejercicio se toma el resultado contable, sin ajustes."""
    d = sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == ejercicio.empresa_id, DeclaracionPresentada.modelo == "200", DeclaracionPresentada.anio == ejercicio.anio, DeclaracionPresentada.tipo == 1)).first()
    if d is not None and "552" in json.loads(d.casillas or "{}"):
        return Decimal(json.loads(d.casillas)["552"]), True
    return resultado, False


def capital_social(sesion: Session, ejercicio: Ejercicio) -> Decimal:
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=3, excluir_subtipos=("R", "Z"))
    return sum((f.haber - f.debe for f in b.filas if f.cuenta == "100"), CERO)


def memoria(sesion: Session, ejercicio: Ejercicio, *, participaciones: int | None = None) -> tuple[list[pdf.Bloque], list[str]]:
    """Los bloques de la memoria y los avisos sobre lo que se ha tomado por defecto."""
    empresa, avisos = ejercicio.empresa, []
    resultado = resultado_contable(sesion, ejercicio)
    base, presentada = base_imponible(sesion, ejercicio, resultado)
    if not presentada:
        avisos.append(f"Sin el Impuesto sobre Sociedades de {ejercicio.anio} presentado, la base imponible de la memoria es el resultado contable, sin ajustes")
    if participaciones is None:
        participaciones = int(capital_social(sesion, ejercicio))
        avisos.append(f"El número de participaciones ({participaciones}) sale de la cuenta de capital con valor nominal de 1 €")
    constituida = empresa.fecha_constitucion.strftime("%d/%m/%Y") if empresa.fecha_constitucion else "—"
    actividad = (empresa.actividad or "").strip()
    sustituciones = {
        "@ENCABEZADO": f"MEMORIA ANUAL DE LA SOCIEDAD {empresa.nombre}, CORRESPONDIENTE AL EJERCICIO {ejercicio.anio}",
        "@SOCIEDAD": (f"La sociedad {empresa.nombre}, con N.I.F. {empresa.nif or '—'} es una sociedad bajo fórmula juridica de {empresa.tipo_entidad or 'Sociedad Limitada'}, que fue constituida el {constituida} y "
                      f"está inscrita en el Registro Mercantil de {empresa.registro_provincia or '—'} en tomo {empresa.registro_tomo or '—'}, folio {empresa.registro_folio or '—'} y hoja número "
                      f"{empresa.registro_hoja or '—'}. Tiene su domicilio social y fiscal en {empresa.domicilio or '—'} y desarrolla sus actividades en {empresa.poblacion or '—'}, {empresa.provincia or '—'}."),
        "@ACTIVIDAD": f"Dicha sociedad tiene como actividad principal {actividad}." if actividad else "",
    }
    bloques: list[pdf.Bloque] = []
    for tipo, texto in TEXTO:
        if texto in sustituciones:
            if sustituciones[texto]:
                bloques.append(pdf.Bloque("p", sustituciones[texto]))
        elif texto == "@VIDA_UTIL":
            bloques.append(pdf.Bloque("tabla", filas=[["", "Años de vida útil estimada"], ["Construcciones", "De 35 a 50"], ["Instalaciones técnicas y maquinaria", "De 5 a 15"], ["Utillaje y herramientas", "De 4 a 8"],
                                                    ["Mobiliario y enseres", "De 5 a 15"], ["Equipos informáticos", "De 4 a 8"], ["Elementos de transporte", "De 6 a 12"]]))
        elif texto == "@CONCILIACION":
            bloques.append(pdf.Bloque("renglon", filas=[["Resultado contable después de impuesto", pdf.eur(resultado)], ["Impuesto sobre Sociedades", ""], ["Resto de ajustes extracontables", ""],
                                                        ["Compensación bases imponibles negativas", ""], ["Base imponible del ejercicio", pdf.eur(base)]]))
        else:
            bloques.append(pdf.Bloque(tipo, texto.replace("{participaciones}", str(participaciones))))
    return bloques, avisos


# ---------------------------------------------------------------------------------------------- generar

def _huella(datos: bytes) -> str:
    return base64.b64encode(hashlib.sha256(datos).digest()).decode()


def _fecha_anterior(clave: str, numero: int, ejercicio: Ejercicio, libro: LibroLegalizacion | None, propuestos: dict, anteriores: dict[str, date | None] | None) -> date | None:
    """La fecha hasta la que se legalizó antes el libro: la que se pide; si no, la guardada o la del libro anterior; si no, el fin del año anterior cuando no es el primero (nº > 1)."""
    if anteriores is not None and clave in anteriores:
        return anteriores[clave]
    if libro is not None and libro.fecha_ejercicio_anterior is not None:
        return libro.fecha_ejercicio_anterior
    return propuestos[clave][1] or (date(ejercicio.anio - 1, 12, 31) if numero > 1 else None)


def generar_libros(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, numeros: dict[str, int] | None = None, anteriores: dict[str, date | None] | None = None,
                   usuario: str | None = None) -> Legalizacion:
    """Genera los PDF de los libros que Conta ya prepara (diario e inventario) y deja anotada la legalización. Sustituye lo generado antes mientras no esté enviada. No hace commit."""
    empresa = ejercicio.empresa
    errores = [h.mensaje for h in controlar(sesion, ejercicio) if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se pueden preparar los libros: " + "; ".join(errores))
    propuestos = numeros_propuestos(sesion, empresa.id, ejercicio.anio)
    legalizacion = sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == empresa.id, Legalizacion.anio == ejercicio.anio))
    if legalizacion is None:
        legalizacion = Legalizacion(empresa_id=empresa.id, anio=ejercicio.anio, estado=PREPARADA)
        sesion.add(legalizacion)
    legalizacion.preparada_en, legalizacion.preparada_por = datetime.now(), usuario or _usuario()
    carpeta = carpeta_de_libros(raiz_almacen, empresa, ejercicio.anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    cab = cabecera_de(empresa)
    existentes = {l.clave: l for l in legalizacion.libros}
    for orden, clave, _, prefijo in LIBROS:
        if clave not in GENERADOS:
            continue
        pedido = (numeros or {}).get(clave)
        numero = pedido or (existentes[clave].numero if clave in existentes else propuestos[clave][0])
        anterior = _fecha_anterior(clave, numero, ejercicio, existentes.get(clave), propuestos, anteriores)
        if numero > 1 and anterior is None:  # Legalia2 lo exige en todo libro que no es el primero (falta «fecha cierre último legalizado»)
            nombre_libro = next(n for _, c, n, _ in LIBROS if c == clave)
            raise ErrorContable(f"El libro «{nombre_libro}» lleva el nº {numero}, que no es el primero: indique «Legalizado antes hasta» (el fin del ejercicio de su legalización anterior, por ejemplo 31/12/{ejercicio.anio - 1}); Legalia2 lo exige")
        nombre = nombre_fichero(prefijo, numero)
        ruta = carpeta / nombre
        if clave == "diario":
            paginas = pdf.pdf_diario(ruta, cab, ejercicio.anio, asientos_del_diario(sesion, ejercicio))
        elif clave == "socios":
            socios, capital = socios_del_libro(sesion, empresa, ejercicio.fecha_fin)
            paginas = pdf.pdf_socios(ruta, cab, ejercicio.anio, registro_mercantil_texto(empresa), socios, capital)
        elif clave == "actas":
            paginas = pdf.pdf_actas(ruta, cab, ejercicio.anio, actas_del_libro(sesion, ejercicio))
        else:
            bloques, _ = memoria(sesion, ejercicio)
            paginas = pdf.pdf_inventario(ruta, cab, ejercicio.anio, secciones_de_sumas_y_saldos(sesion, ejercicio), bloques)
        libro = existentes.get(clave) or LibroLegalizacion(orden=orden, clave=clave)
        if existentes.get(clave) is None:
            legalizacion.libros.append(libro)
        elif libro.fichero_ruta and libro.fichero_nombre != nombre:
            (Path(raiz_almacen) / libro.fichero_ruta).unlink(missing_ok=True)  # el número de libro ha cambiado: se quita el PDF con el nombre antiguo
        libro.numero, libro.fecha_ejercicio_anterior = numero, anterior
        libro.fichero_nombre, libro.fichero_ruta, libro.paginas = nombre, ruta.relative_to(Path(raiz_almacen)).as_posix(), paginas
        libro.sha256_base64 = _huella(ruta.read_bytes())
    legalizacion.fecha_presentacion = date.today()
    sesion.flush()
    if not datos_que_faltan_para_el_zip(empresa):
        preparar_zip(legalizacion, ejercicio, raiz_almacen)
    else:
        legalizacion.zip_nombre = legalizacion.zip_ruta = legalizacion.zip_sha256 = None
    sesion.flush()
    return legalizacion


# ---------------------------------------------------------------------------------------------- DATOS.TXT de Legalia2

# código de DATOS.TXT → campo de la ficha de la empresa (la presentación: 301 a 311)
CODIGOS_DE_LA_FICHA = {
    "109": "provincia_ine", "112": "municipio_ine", "301": "presentador_nombre", "302": "presentador_apellido1", "303": "presentador_apellido2", "304": "presentador_nif", "305": "presentador_domicilio",
    "306": "presentador_poblacion", "307": "presentador_cp", "308": None, "310": "presentador_telefono", "311": "presentador_email",
}


def leer_datos_txt(texto: str) -> dict[str, str]:
    """`DATOS.TXT` de Legalia2: una línea por dato, con el código (3 cifras, o 5 en los libros) pegado al valor."""
    datos: dict[str, str] = {}
    for linea in texto.splitlines():
        if len(linea) >= 3 and linea[:3].isdigit() and not linea.startswith("00"):
            datos.setdefault(linea[:3], linea[3:].strip())
    return datos


def precargar_ficha(empresa: Empresa, datos: dict[str, str]) -> list[tuple[str, str]]:
    """Rellena la ficha con los datos de un `DATOS.TXT` anterior (el del programa anterior), sin pisar lo que ya esté escrito. Devuelve [(campo, valor)] de lo que ha puesto. No hace commit."""
    if datos.get("105", "").strip().upper() != (empresa.nif or "").strip().upper():
        raise ErrorContable(f"El DATOS.TXT es del NIF {datos.get('105', '—')}, no del de la empresa ({empresa.nif or '—'})")
    puestos = []
    for codigo, campo in CODIGOS_DE_LA_FICHA.items():
        valor = datos.get(codigo, "").strip()
        if campo and valor and not (getattr(empresa, campo) or "").strip():
            setattr(empresa, campo, valor)
            puestos.append((campo, valor))
    return puestos


# ---------------------------------------------------------------------------------------------- el ZIP para Legalia2

def datos_que_faltan_para_el_zip(empresa: Empresa) -> list[str]:
    """Los datos de la ficha que `DATOS.TXT` necesita y todavía no están."""
    pedidos = (("nif", "NIF"), ("domicilio", "domicilio"), ("codigo_postal", "código postal"), ("poblacion", "población"), ("telefono", "teléfono"), ("municipio_ine", "código INE del municipio"),
               ("provincia_ine", "código INE de la provincia"), ("registro_provincia", "Registro Mercantil"), ("registro_tomo", "tomo"), ("registro_folio", "folio"), ("registro_hoja", "hoja"),
               ("presentador_nombre", "nombre de quien presenta"), ("presentador_apellido1", "primer apellido de quien presenta"), ("presentador_nif", "NIF de quien presenta"),
               ("presentador_domicilio", "domicilio de quien presenta"), ("presentador_poblacion", "población de quien presenta"), ("presentador_cp", "código postal de quien presenta"),
               ("presentador_telefono", "teléfono de quien presenta"), ("presentador_email", "correo de quien presenta"))
    return [nombre for campo, nombre in pedidos if _falta(getattr(empresa, campo))]


def irus_para_desc(empresa: Empresa) -> str:
    """El IRUS de la ficha, completo (13 cifras, con la de control): Legalia2 lo toma tal cual de `DESC.TXT` y no le añade la cifra que el programa anterior dejaba fuera."""
    cifras = re.sub(r"\D", "", empresa.codigo_irus or "")
    return cifras if len(cifras) >= 12 else ""


def nombre_del_zip(empresa: Empresa, anio: int) -> str:
    return f"LL{(empresa.provincia_ine or '').strip()}{anio % 1000:03d}{(empresa.nif or '').strip().upper()}.ZIP"


def _telefono(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def datos_txt(empresa: Empresa, ejercicio: Ejercicio, fecha_presentacion: date, libros: list[LibroLegalizacion]) -> str:
    """`DATOS.TXT` de Legalia2, como lo hace el programa anterior: una línea por dato, con su código pegado al valor, y los datos de cada libro."""
    registro = re.sub(r"\s+[IVX]+$", "", (empresa.registro_provincia or "").strip()).upper()
    lineas = [
        ("100", registro), ("101", f"{fecha_presentacion:%d%m%Y}"), ("102", empresa.nombre.strip()), ("105", empresa.nif.strip().upper()), ("106", empresa.domicilio.strip()), ("107", empresa.poblacion.strip().upper()),  # en mayúsculas, como lo guarda la propia Legalia2 (el municipio se elige por su nombre en la lista)
        
        ("108", empresa.codigo_postal.strip()), ("109", empresa.provincia_ine.strip()), ("111", _telefono(empresa.telefono)), ("112", empresa.municipio_ine.strip()), ("201", empresa.registro_tomo.strip()),
        ("204", empresa.registro_folio.strip()), ("205", "REGISTRO MERCANTIL"), ("206", empresa.registro_hoja.strip()), ("301", empresa.presentador_nombre.strip()),
        ("302", empresa.presentador_apellido1.strip()), ("303", _texto_de(empresa.presentador_apellido2)), ("304", empresa.presentador_nif.strip().upper()), ("305", empresa.presentador_domicilio.strip()),
        ("306", empresa.presentador_poblacion.strip()), ("307", empresa.presentador_cp.strip()), ("308", empresa.provincia_ine.strip()), ("310", _telefono(empresa.presentador_telefono)),
        ("311", empresa.presentador_email.strip()), ("401", "NO"), ("501", str(len(libros))),
    ]
    nombres = {clave: nombre for _, clave, nombre, _ in LIBROS}
    for i, libro in enumerate(libros, 1):
        lineas += [(f"00{i}01", nombres[libro.clave]), (f"00{i}02", str(libro.numero)), (f"00{i}03", f"{ejercicio.fecha_inicio:%d%m%Y}"), (f"00{i}04", f"{ejercicio.fecha_fin:%d%m%Y}")]
        if libro.fecha_ejercicio_anterior:
            lineas.append((f"00{i}05", f"{libro.fecha_ejercicio_anterior:%d%m%Y}"))
        lineas.append((f"00{i}06", libro.sha256_base64 or ""))
    return "".join(f"{codigo}{valor}\r\n" for codigo, valor in lineas if not (codigo == "303" and not valor))


def nombres_txt(libros: list[LibroLegalizacion]) -> str:
    return "".join(f"{l.fichero_nombre}\r\n" for l in libros)


def preparar_zip(legalizacion: Legalizacion, ejercicio: Ejercicio, raiz_almacen: Path) -> Path:
    """El ZIP que se importa en Legalia2: los PDF de los libros, `DATOS.TXT`, `NOMBRES.TXT` y, si la ficha tiene el IRUS, `DESC.TXT` (de ahí lo toma Legalia2 para rellenar el IRUS de la entidad)."""
    empresa = ejercicio.empresa
    faltan = datos_que_faltan_para_el_zip(empresa)
    if faltan:
        raise ErrorContable("Faltan datos de la ficha de la empresa para el ZIP de Legalia2: " + ", ".join(faltan))
    libros = [l for l in legalizacion.libros if l.fichero_ruta]
    if len(libros) != len(LIBROS):
        raise ErrorContable("Primero hay que generar los cuatro libros")
    carpeta = carpeta_de_libros(raiz_almacen, empresa, ejercicio.anio)
    ruta = carpeta / nombre_del_zip(empresa, ejercicio.anio)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for l in libros:
            z.write(Path(raiz_almacen) / l.fichero_ruta, l.fichero_nombre)
        z.writestr("DATOS.TXT", datos_txt(empresa, ejercicio, legalizacion.fecha_presentacion or date.today(), libros).encode("latin-1", errors="replace"))
        z.writestr("NOMBRES.TXT", nombres_txt(libros).encode("latin-1"))
        if irus_para_desc(empresa):  # Legalia2 saca de aquí el IRUS de la entidad; sin él el formulario de la legalización lo deja vacío
            z.writestr("DESC.TXT", f"{empresa.nif.strip().upper()}\r\nIRUS= {irus_para_desc(empresa)}\r\n".encode("latin-1"))
    legalizacion.zip_nombre, legalizacion.zip_ruta = ruta.name, ruta.relative_to(Path(raiz_almacen)).as_posix()
    legalizacion.zip_sha256 = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return ruta


# ---------------------------------------------------------------------------------------------- el envío al Registro

def leer_acuse(pdf: bytes) -> dict:
    """Los datos del «Acuse de recibo» que devuelve el Registro Mercantil al recibir la legalización: identificador del trámite, referencia del documento, nº de entrada y fecha."""
    import io

    from pypdf import PdfReader

    try:
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    except Exception as e:  # noqa: BLE001 - un PDF ilegible no debe tumbar la pantalla
        raise ErrorContable(f"No se puede leer el PDF del acuse: {e}") from None
    if "ACUSE DE RECIBO" not in texto.upper():
        raise ErrorContable("El PDF no es un «Acuse de recibo» del Registro Mercantil")

    def campo(patron: str) -> str | None:
        m = re.search(patron, texto, re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    fecha = campo(r"N.mero de entrada.*?Fecha\s*(\d{2}/\d{2}/\d{4})")
    return {"identificador": campo(r"Identificador\s+(\S+)"), "referencia": campo(r"Referencia del documento\s+(\S+)"), "entrada": campo(r"N.mero de entrada\s+([\d /]+?)\s*(?:Fecha|\n)"),
            "fecha": date(int(fecha[6:]), int(fecha[3:5]), int(fecha[:2])) if fecha else None}


def registrar_envio(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, pdf: bytes | None = None, fecha: date | None = None, referencia: str | None = None,
                    usuario: str | None = None) -> Legalizacion:
    """Deja constancia de que los libros del ejercicio se enviaron al Registro. Con el PDF del acuse se leen la fecha, la referencia y el nº de entrada y se guarda el PDF; sin él, se necesita la fecha. No hace commit."""
    empresa = ejercicio.empresa
    leida = leer_acuse(pdf) if pdf else {}
    if pdf and not pdf.startswith(b"%PDF"):
        raise ErrorContable("El acuse debe ser el PDF que devuelve el Registro")
    if pdf and len(pdf) > 10 * 1024 * 1024:
        raise ErrorContable("El PDF del acuse pesa más de 10 MB")
    referencia = (referencia or leida.get("referencia") or "").strip() or None
    if referencia and leida.get("referencia") and referencia != leida["referencia"]:
        raise ErrorContable(f"La referencia tecleada ({referencia}) no coincide con la del acuse ({leida['referencia']})")
    esperada = f"{(empresa.nif or '').strip().upper()}{ejercicio.anio}"
    if leida.get("referencia") and leida["referencia"].upper() != esperada:
        raise ErrorContable(f"El acuse es de otro ejercicio o de otra empresa (referencia {leida['referencia']}; la de estos libros sería {esperada})")
    fecha = fecha or leida.get("fecha")
    if fecha is None:
        raise ErrorContable("Falta la fecha del envío (se lee sola del PDF del acuse)")
    if fecha > date.today():
        raise ErrorContable("La fecha del envío no puede ser futura")
    leg = sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == empresa.id, Legalizacion.anio == ejercicio.anio))
    if leg is None:  # libros legalizados fuera de Conta: queda constancia igualmente
        leg = Legalizacion(empresa_id=empresa.id, anio=ejercicio.anio)
        sesion.add(leg)
    if pdf:
        carpeta = carpeta_de_libros(raiz_almacen, empresa, ejercicio.anio)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{re.sub(r'[^A-Za-z0-9]', '', referencia or 'Legalizacion')}_Acuse_Entrada.pdf"
        ruta.write_bytes(pdf)
        leg.acuse_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    leg.estado, leg.enviada_en, leg.referencia = ENVIADA, fecha, referencia
    leg.numero_entrada = leida.get("entrada") or leg.numero_entrada
    sesion.flush()
    from conta_pridalac.servicios.huellas import anotar_al_confirmar

    anotar_al_confirmar(sesion, raiz_almacen, empresa.codigo, f"envío de la legalización de libros {ejercicio.anio}")
    return leg
