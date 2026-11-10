"""Depósito de las cuentas anuales en el Registro Mercantil: prepara lo que la aplicación D2 de Legalia2 abre (la carpeta del depósito con `DEPOSITO.XML` y `Documentos/MEMORIA.pdf`) a partir de la contabilidad.

`DEPOSITO.XML` es el formulario de D2 (el «Esquema» de códigos y valores): los datos de la sociedad, las fechas del ejercicio y los importes del balance y de la cuenta de pérdidas y ganancias del año y del anterior, más las respuestas por
defecto del cuestionario de la memoria. Los códigos salen del depósito de Empresa A de 2021 (los **confirmados**) y de la numeración correlativa de D2 (los **inferidos**: se avisa cuando llevan importe).
Conta no firma ni calcula la huella digital: la certificación del acuerdo de la junta, su huella, las firmas con el certificado y el envío los hace D2. Aquí sólo se deja constancia del acuse.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.servicios.exportar import nombre_corto
from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from conta_pridalac.db.modelos import ENVIADA, PREPARADA, Acta, DepositoCuentas, Ejercicio, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion import libros_pdf as pdf
from conta_pridalac.exportacion import xbrl_deposito as xb
from conta_pridalac.servicios import libros_oficiales as lo
from conta_pridalac.servicios.cuentas_anuales import ACTIVO, PASIVO, PYG, Estado, balance_pymes, ejercicio_anterior, pyg_pymes
from conta_pridalac.servicios.informes import NIVEL_SUBCUENTA, balance_sumas_y_saldos
from conta_pridalac.servicios.plazos import fin_del_deposito
from conta_pridalac.servicios.presentacion303 import _usuario

CERO = Decimal("0.00")
DESCRIPCION_ACUSE = "depósito de cuentas"

# (línea del balance o de la cuenta de resultados, código de D2, confirmado). El código del ejercicio anterior es el mismo con un 9 detrás (11000 → 110009).
# Confirmado: aparece en el depósito de Empresa A de 2021. Inferido: sigue la numeración de D2 (cada nivel suma 100 o 10) y no se ha visto en un fichero real.
CODIGOS_BALANCE = (
    ("TA", "10000", True), ("A", "11000", True), ("A.I", "11100", True), ("A.II", "11200", True), ("A.III", "11300", False), ("A.IV", "11400", False), ("A.V", "11500", False), ("A.VI", "11600", False),
    ("A.VII", "11700", False), ("B", "12000", True), ("B.I", "12200", True), ("B.II", "12300", True), ("B.II.1", "12380", True), ("B.II.1a", "12381", False), ("B.II.1b", "12382", True),
    ("B.II.2", "12370", True), ("B.II.3", "12390", True), ("B.III", "12400", False), ("B.IV", "12500", False), ("B.V", "12600", False), ("B.VI", "12700", True),
    ("PN", "20000", True), ("PN.1", "21000", True), ("PN.1.I", "21100", True), ("PN.1.I.1", "21110", True), ("PN.1.I.2", "21120", False), ("PN.1.II", "21200", False), ("PN.1.III", "21300", True),
    ("PN.1.III.2", "21360", True), ("PN.1.IV", "21400", False), ("PN.1.V", "21500", True), ("PN.1.VI", "21600", True), ("PN.1.VII", "21700", True), ("PN.1.VIII", "21800", False),
    ("PN.2", "22000", False), ("PN.3", "23000", False),
    ("PNC", "31000", False), ("PNC.I", "31200", False), ("PNC.II", "31300", False), ("PNC.II.1", "31320", False), ("PNC.II.2", "31330", False), ("PNC.II.3", "31390", False), ("PNC.III", "31400", False),
    ("PNC.IV", "31500", False), ("PNC.V", "31600", False),
    ("PC", "32000", True), ("PC.I", "32200", False), ("PC.II", "32300", True), ("PC.II.1", "32320", True), ("PC.II.2", "32330", True), ("PC.II.3", "32390", True), ("PC.III", "32400", False),
    ("PC.IV", "32500", True), ("PC.IV.1", "32580", False), ("PC.IV.1a", "32581", False), ("PC.IV.1b", "32582", False), ("PC.IV.2", "32590", True), ("PC.V", "32600", False), ("PC.VI", "32700", False),
    ("TP", "30000", True),
)
CODIGOS_PYG = (
    ("1", "40100", True), ("2", "40200", False), ("3", "40300", False), ("4", "40400", True), ("5", "40500", True), ("6", "40600", False), ("7", "40700", True), ("8", "40800", True),
    ("9", "40900", False), ("10", "41000", False), ("11", "41100", True), ("12", "41300", True), ("A", "49100", True), ("B", "49200", False), ("C", "49300", True), ("19", "41900", True),
    ("D", "49500", True),
)
# Las líneas que no están arriba (los ingresos y gastos financieros, p. ej.) no tienen código conocido: si llevan importe se avisa para escribirlas a mano en D2.
TOTALES_SIEMPRE = ("TA", "TP")  # los totales del balance se emiten aunque valgan cero; el resto de líneas, sólo si llevan importe (como D2)

# Respuestas fijas del cuestionario, tal como las lleva el DEPOSITO.xml del programa anterior de 2025 (el que D2 importó): «no aplica» en la memoria y el tipo de cuentas (8081010).
RESPUESTAS_FIJAS = (
    ("8099000", "1"), ("8080828", "1"), ("8080829", "2"), ("8009050", "1"), ("8080839", "0"), ("8080850", "1"), ("8080851", "1"), ("8080852", "1"), ("8080800", "1"), ("8080811", "1"),
    ("8080819", "1"), ("8080809", "1"), ("8080827", "1"), ("8081010", "333001001001E00010100000"), ("8080838", "0"),
)


@dataclass
class FilaImporte:
    codigo: str
    etiqueta: str
    actual: Decimal
    anterior: Decimal
    confirmado: bool
    id: str = ""  # la línea del balance o de la cuenta de resultados
    es_pyg: bool = False


@dataclass
class Importes:
    filas: list[FilaImporte]
    sin_codigo: list[tuple[str, str, Decimal, Decimal]]  # (id, etiqueta, actual, anterior) de las líneas con importe y sin código conocido
    estado_balance: Estado
    estado_pyg: Estado
    hay_anterior: bool


# ---------------------------------------------------------------------------------------------- importes

def _importe(estado: Estado | None, id_: str) -> Decimal:
    return estado.importe(id_) if estado is not None else CERO


def importes_de_las_cuentas(sesion: Session, ejercicio: Ejercicio) -> Importes:
    """Los importes del balance y de la cuenta de pérdidas y ganancias del ejercicio y del anterior, con el código de D2 de cada línea."""
    previo = ejercicio_anterior(sesion, ejercicio)
    balance, resultados = balance_pymes(sesion, ejercicio), pyg_pymes(sesion, ejercicio)
    balance_ant = balance_pymes(sesion, previo) if previo is not None else None
    resultados_ant = pyg_pymes(sesion, previo) if previo is not None else None
    etiquetas = {l.id: l.etiqueta for l in balance.lineas}
    etiquetas_pyg = {l.id: l.etiqueta for l in resultados.lineas}
    filas, con_codigo = [], set()
    for tabla, estado, ant, nombres in ((CODIGOS_BALANCE, balance, balance_ant, etiquetas), (CODIGOS_PYG, resultados, resultados_ant, etiquetas_pyg)):
        for id_, codigo, confirmado in tabla:
            actual, anterior = _importe(estado, id_), _importe(ant, id_)
            con_codigo.add((tabla is CODIGOS_PYG, id_))
            if actual or anterior or id_ in TOTALES_SIEMPRE:
                filas.append(FilaImporte(codigo, nombres[id_], actual, anterior, confirmado, id_, tabla is CODIGOS_PYG))
    sin_codigo = []
    propias = {(False, l.id) for l in (*ACTIVO, *PASIVO) if l.cuentas} | {(True, l.id) for l in PYG if l.cuentas}  # las sumas se calculan solas: sólo importan las líneas con cuentas propias
    for es_pyg, estado, ant in ((False, balance, balance_ant), (True, resultados, resultados_ant)):
        for l in estado.lineas:
            if (es_pyg, l.id) in con_codigo or (es_pyg, l.id) not in propias or not (l.importe or _importe(ant, l.id)):
                continue
            sin_codigo.append((l.id, l.etiqueta, l.importe or CERO, _importe(ant, l.id)))
    return Importes(filas, sin_codigo, balance, resultados, previo is not None)


def _numero(valor: Decimal) -> str:
    """El importe como lo escribe D2: con dos decimales (34580.00, -49135.52)."""
    texto = format(valor.quantize(Decimal("0.01")), "f")
    return "0.00" if texto == "-0.00" else texto


# ---------------------------------------------------------------------------------------------- datos de partida

def codigo_del_registro(empresa: Empresa) -> str:
    """El código del Registro Mercantil (28065 para el de Madrid); en otro registro, el código de municipio de la ficha."""
    if (empresa.registro_provincia or "").strip().upper().startswith("MADRID"):
        return "28065"
    return (empresa.municipio_ine or "").strip()


def nombre_de_la_carpeta(empresa: Empresa, anio: int) -> str:
    """El nombre del depósito en D2: las cuatro primeras letras de la sociedad y el año (CAPR2021)."""
    base = re.sub(r"[^A-Z0-9]", "", ((empresa.nombre_corto or "").strip() or re.sub(r"\b(S\.?L\.?U?\.?|S\.?A\.?)\s*$", "", empresa.nombre.strip(), flags=re.I)).upper())
    return f"{base[:4]}{anio}"


def acta_de_aprobacion(sesion: Session, ejercicio: Ejercicio) -> Acta | None:
    """El acta que aprobó las cuentas del ejercicio: la primera, dentro del año siguiente al cierre, que en sus acuerdos o su orden del día habla de aprobar las cuentas anuales."""
    inicio, fin = date(ejercicio.fecha_fin.year + 1, 1, 1), date(ejercicio.fecha_fin.year + 1, 12, 31)
    for a in sesion.scalars(select(Acta).where(Acta.empresa_id == ejercicio.empresa_id, Acta.fecha >= inicio, Acta.fecha <= fin).order_by(Acta.fecha, Acta.numero)):
        texto = f"{a.acuerdos or ''}\n{a.orden_del_dia or ''}".lower()
        if "cuentas anuales" in texto and str(ejercicio.anio) in texto:
            return a
    return None


def plazo_de_deposito(ejercicio: Ejercicio, aprobacion: date | None) -> date:
    """Un mes desde la aprobación de las cuentas; si aún no se conoce, el 30 de julio (las cuentas se aprueban antes del 30 de junio)."""
    return fin_del_deposito(ejercicio.anio, aprobacion)


# ---------------------------------------------------------------------------------------------- datos de cierre

PERSONAL = ("medio_fijo", "medio_no_fijo", "medio_discapacidad", "final_fijo_h", "final_fijo_m", "final_nofijo_h", "final_nofijo_m")
APLICACION = (("reserva_legal", "A reserva legal"), ("reservas_especiales", "A reservas especiales"), ("reservas_voluntarias", "A reservas voluntarias"), ("dividendos", "A dividendos"),
              ("remanente_y_otros", "A remanente y otros"), ("compensacion_perdidas", "A compensación de pérdidas de ej. anteriores"))
CLAVES_CIERRE = (*PERSONAL, "roac", "lei", "causa", "microempresa", "paginas", "fecha_emision", *(c for c, _ in APLICACION), "capital", "desembolsado", "participaciones", "valor_nominal", "impuesto", "ajustes",
                 "compensacion_bin", "base_imponible", "saldo_medio", "reparto_remanente", "reparto_voluntarias", "reparto_otras", "reformulacion")


def _dec(texto) -> Decimal:
    """Un importe escrito como «1.038,90» o «1038.90» (vacío = 0)."""
    t = str(texto or "").strip().replace(" ", "")
    if not t:
        return CERO
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except Exception:  # noqa: BLE001
        raise ErrorContable(f"«{texto}» no es un importe") from None


def compras_netas(sesion: Session, ejercicio: Ejercicio) -> Decimal:
    """Las compras netas y los gastos en servicios exteriores del ejercicio (grupos 60 y 62): el denominador del periodo medio de pago."""
    b = balance_sumas_y_saldos(sesion, ejercicio, nivel=NIVEL_SUBCUENTA, excluir_subtipos=("R", "Z"))
    return sum((f.debe - f.haber for f in b.filas if f.cuenta[:2] in ("60", "62")), CERO)


def propuesta_de_cierre(sesion: Session, ejercicio: Ejercicio, importes: Importes, socios: list[pdf.SocioLibro], aprobacion: date | None) -> dict[str, str]:
    """Lo que Conta sabe de los datos de cierre de D2: el capital, las participaciones, el resultado y la base imponible, y con un beneficio, su aplicación a reserva legal (lo que se ha hecho hasta ahora)."""
    resultado = importes.estado_pyg.importe("D")
    capital = lo.capital_social(sesion, ejercicio)
    participaciones = sum((s.total_participaciones for s in socios), 0)
    base, _ = lo.base_imponible(sesion, ejercicio, resultado)
    p = {"capital": _numero(capital), "desembolsado": _numero(capital), "base_imponible": _numero(base), "impuesto": "0.00", "ajustes": "0.00", "compensacion_bin": "0.00"}
    if participaciones:
        p["participaciones"] = str(participaciones)
        p["valor_nominal"] = _numero(capital / participaciones)
    if aprobacion:
        p["fecha_emision"] = f"{aprobacion:%d/%m/%Y}"
    if resultado > 0:
        p["reserva_legal"] = _numero(resultado)
        p["reparto_remanente"] = p["reparto_voluntarias"] = p["reparto_otras"] = "0.00"
    return p


def cierre_guardado(deposito: DepositoCuentas | None) -> dict[str, str]:
    try:
        return {k: str(v) for k, v in json.loads(deposito.cierre or "{}").items()} if deposito is not None else {}
    except ValueError:
        return {}


def cierre_efectivo(sesion: Session, ejercicio: Ejercicio, deposito: DepositoCuentas | None, importes: Importes | None = None) -> dict[str, str]:
    """Los datos de cierre: la propuesta de Conta y, encima, lo que se haya escrito."""
    importes = importes or importes_de_las_cuentas(sesion, ejercicio)
    socios, _ = lo.socios_del_libro(sesion, ejercicio.empresa, ejercicio.fecha_fin)
    aprobada = acta_de_aprobacion(sesion, ejercicio)
    aprobacion = deposito.fecha_aprobacion if deposito and deposito.fecha_aprobacion else (aprobada.fecha if aprobada else None)
    return {**propuesta_de_cierre(sesion, ejercicio, importes, socios, aprobacion), **{k: v for k, v in cierre_guardado(deposito).items() if v != ""}}


def total_aplicacion(cierre: dict[str, str]) -> Decimal:
    return sum((_dec(cierre.get(c)) for c, _ in APLICACION), CERO)


def total_reparto(cierre: dict[str, str]) -> Decimal:
    return total_aplicacion(cierre)


def personal_de(cierre: dict[str, str]) -> dict[str, str]:
    return {k: cierre.get(k, "") for k in PERSONAL}


def certificacion_de(sesion: Session, ejercicio: Ejercicio, deposito: DepositoCuentas, cierre: dict[str, str], importes: Importes) -> pdf.Certificacion:
    """Los datos de la certificación del acuerdo de la junta, con la huella que generó D2."""
    e = ejercicio.empresa
    texto = lambda v: (v or "").strip()  # noqa: E731
    firmante = " ".join(x for x in (texto(e.presentador_apellido1), texto(e.presentador_apellido2)) if x)
    firmante = _nombre_d2(f"{firmante}, {texto(e.presentador_nombre)}") if texto(e.presentador_nombre) else _nombre_d2(texto(e.representante_nombre))
    nif = texto(e.presentador_nif) or texto(e.representante_nif)
    try:
        emision = datetime.strptime(cierre.get("fecha_emision", ""), "%d/%m/%Y").date()
    except ValueError:
        emision = deposito.fecha_aprobacion or date.today()
    domicilio = ", ".join(x for x in (texto(e.domicilio), texto(e.poblacion), texto(e.provincia)) if x)
    return pdf.Certificacion(
        sociedad=e.nombre.strip(), nif_sociedad=texto(e.nif).upper(), domicilio=domicilio, cargo=(texto(e.forma_administracion) or "administrador").lower(), firmante=firmante, nif_firmante=nif.upper(),
        lugar=texto(e.poblacion), fecha_junta=deposito.fecha_aprobacion or emision, fecha_formulacion=deposito.fecha_formulacion, fecha_emision=emision, ejercicio=ejercicio.anio, fecha_cierre=ejercicio.fecha_fin,
        resultado=importes.estado_pyg.importe("D"), aplicacion=[(etiqueta, _dec(cierre.get(c))) for c, etiqueta in APLICACION], huella=deposito.huella_d2 or "",
        orden="JUS/616/2022, de 30 de junio" if ejercicio.anio >= 2021 and ejercicio.anio != 2021 else "JUS/794/2021, de 22 de julio",
        reformulacion=(cierre.get("reformulacion") == "1") if ejercicio.anio >= 2025 else None)  # desde las cuentas de 2025 (Resolución DGSJFP de 19/05/2026): se hace constar si se usó la reformulación del RDL 4/2025


def nombre_de_la_certificacion(empresa: Empresa, anio: int) -> str:
    return f"{codigo_del_registro(empresa)}{(empresa.nif or '').strip().upper()}{anio}0.CAC.pdf"  # como la nombra el programa anterior


# ---------------------------------------------------------------------------------------------- controles

def controlar(sesion: Session, ejercicio: Ejercicio, deposito: DepositoCuentas | None = None, *, pmp: tuple[int | None, int | None] | None = None) -> list[Hallazgo]:
    """Lo que falta o no cuadra antes de preparar el depósito. Los errores impiden prepararlo."""
    empresa, hallazgos = ejercicio.empresa, []

    def hallazgo(codigo, gravedad, mensaje, referencia=""):
        hallazgos.append(Hallazgo(codigo, gravedad, mensaje, referencia))

    if (empresa.tipo_plan or "pymes") != "pymes":
        hallazgo("deposito_plan_no_pymes", ERROR, "El depósito sólo está preparado para el plan de PYMES (las entidades sin fines lucrativos usan otro cuestionario de D2)", "tipo_plan")
    if not ejercicio.cerrado:
        hallazgo("ejercicio_sin_cerrar", ERROR, f"El ejercicio {ejercicio.anio} no está cerrado: las cuentas se depositan con el ejercicio cerrado (regularización y cierre hechos)", str(ejercicio.anio))
    for campo, nombre in (("nif", "el NIF"), ("domicilio", "el domicilio"), ("codigo_postal", "el código postal"), ("poblacion", "la población"), ("provincia_ine", "el código INE de la provincia")):
        if lo._falta(getattr(empresa, campo)):
            hallazgo("falta_dato_de_la_empresa", ERROR, f"Falta {nombre} de la empresa (ficha de la empresa)", campo)
    for campo, nombre in (("telefono", "el teléfono"), ("email", "el correo"), ("actividad", "la actividad"), ("registro_tomo", "el tomo del Registro"),
                          ("registro_folio", "el folio del Registro"), ("registro_hoja", "la hoja del Registro"), ("presentador_nombre", "el nombre de quien presenta"),
                          ("presentador_apellido1", "el primer apellido de quien presenta"), ("presentador_nif", "el NIF de quien presenta")):
        if lo._falta(getattr(empresa, campo)):
            hallazgo("falta_dato_del_deposito", AVISO, f"Falta {nombre} (ficha de la empresa): el formulario de D2 lo lleva vacío", campo)
    importes = importes_de_las_cuentas(sesion, ejercicio)
    if importes.estado_balance.sin_asignar:
        hallazgo("cuentas_sin_linea", ERROR, f"{len(importes.estado_balance.sin_asignar)} cuenta(s) con saldo no caen en ninguna línea del balance de PYMES (pantalla «Balance oficial»)", "balance")
    if importes.estado_pyg.sin_asignar:
        hallazgo("cuentas_sin_linea", ERROR, f"{len(importes.estado_pyg.sin_asignar)} cuenta(s) con saldo no caen en ninguna línea de la cuenta de pérdidas y ganancias (pantalla «PyG oficial»)", "pyg")
    activo, pasivo = importes.estado_balance.importe("TA"), importes.estado_balance.importe("TP")
    if activo != pasivo:
        hallazgo("balance_descuadrado", ERROR, f"El total del activo ({pdf.eur(activo)}) no coincide con el del patrimonio neto y pasivo ({pdf.eur(pasivo)})", "balance")
    resultado_pyg, resultado_balance = importes.estado_pyg.importe("D"), importes.estado_balance.importe("PN.1.VII")
    if resultado_pyg != resultado_balance:
        hallazgo("resultado_distinto_en_balance", ERROR, f"El resultado de la cuenta de pérdidas y ganancias ({pdf.eur(resultado_pyg)}) no coincide con el del balance ({pdf.eur(resultado_balance)}): las dos cuentas no pueden depositarse así", "pyg")
    ant_pyg = next((f.anterior for f in importes.filas if f.id == "D" and f.es_pyg), CERO)
    ant_balance = next((f.anterior for f in importes.filas if f.id == "PN.1.VII" and not f.es_pyg), CERO)
    if importes.hay_anterior and ant_pyg != ant_balance:
        hallazgo("resultado_anterior_distinto_en_balance", AVISO, f"En el ejercicio {ejercicio.anio - 1} el resultado de la cuenta de pérdidas y ganancias ({pdf.eur(ant_pyg)}) no coincide con el del balance ({pdf.eur(ant_balance)}): D2 lo señalará (PBL_007); revise los asientos de ese año (el impuesto sobre beneficios)", str(ejercicio.anio - 1))
    if not importes.hay_anterior:
        hallazgo("sin_ejercicio_anterior", AVISO, f"No hay ejercicio {ejercicio.anio - 1} en la base: la columna del ejercicio anterior sale a cero (escríbala a mano en D2)", str(ejercicio.anio - 1))
    for l in importes.filas:
        if not l.confirmado and (l.actual or l.anterior):
            hallazgo("codigo_inferido", AVISO, f"{l.etiqueta}: el código {l.codigo} de D2 no se ha visto en ningún fichero real; compruebe en D2 que el importe cae en esa casilla", l.codigo)
    sin_elemento = xb.lineas_sin_elemento([(f.id, f.etiqueta, f.actual, f.anterior, f.es_pyg) for f in importes.filas] + [(i, e, a, an, i in {l.id for l in PYG}) for i, e, a, an in importes.sin_codigo])
    if sin_elemento:
        hallazgo("xbrl_sin_elemento", ERROR, "Estas partidas llevan importe y todavía no sé escribirlas en el XBRL (no he visto su elemento en ningún depósito real): " + "; ".join(sin_elemento)
                 + ". Hace falta un DEPOSITO.xbrl del programa anterior que las lleve para copiar sus elementos", "xbrl")
    if ejercicio.anio != xb.VERSION_TAXONOMIA:
        hallazgo("taxonomia_de_otro_ano", AVISO, f"El XBRL sigue la taxonomía del ICAC de {xb.VERSION_TAXONOMIA} (v171): si la versión de D2 de {ejercicio.anio} trae otra, hay que revisarlo con un DEPOSITO.xbrl del programa anterior de ese año", "xbrl")
    for id_, etiqueta, actual, anterior in importes.sin_codigo:
        hallazgo("partida_sin_codigo", AVISO, f"{etiqueta}: {pdf.eur(actual)} (anterior {pdf.eur(anterior)}) no tiene código conocido de D2; escríbalo a mano en D2", id_)
    for aviso in importes.estado_balance.avisos[:3]:
        hallazgo("saldo_de_signo_contrario", AVISO, aviso, "balance")
    if len(importes.estado_balance.avisos) > 3:
        hallazgo("saldo_de_signo_contrario", AVISO, f"y {len(importes.estado_balance.avisos) - 3} cuenta(s) más con saldo de signo contrario al de su línea (pantalla «Balance oficial»)", "balance")
    pmp_actual, pmp_anterior = pmp if pmp is not None else ((deposito.pmp_actual, deposito.pmp_anterior) if deposito else (None, None))
    if pmp_actual is None or pmp_anterior is None:
        hallazgo("sin_periodo_medio_de_pago", AVISO, "Falta el periodo medio de pago a proveedores (días) del año y del anterior: la memoria debe informar de él", "pmp")
    cierre = cierre_efectivo(sesion, ejercicio, deposito, importes)
    if resultado_pyg > 0 and total_aplicacion(cierre) != resultado_pyg:
        hallazgo("aplicacion_distinta_del_resultado", ERROR, f"La aplicación del resultado ({pdf.eur(total_aplicacion(cierre))}) no coincide con el beneficio del ejercicio ({pdf.eur(resultado_pyg)})", "aplicacion")
    if deposito is None or deposito.miembros_organo is None or deposito.mujeres_organo is None:
        hallazgo("sin_organo_de_administracion", AVISO, "Faltan el número de miembros del órgano de administración y cuántas son mujeres (datos de cierre de D2)", "organo")
    aprobacion = deposito.fecha_aprobacion if deposito and deposito.fecha_aprobacion else (acta_de_aprobacion(sesion, ejercicio).fecha if acta_de_aprobacion(sesion, ejercicio) else None)
    if aprobacion is None:
        hallazgo("sin_fecha_de_aprobacion", AVISO, f"No consta la fecha en que la junta aprobó las cuentas de {ejercicio.anio} (cree el acta en «Libro de actas» o escríbala aquí): de ella corre el plazo del depósito", "aprobacion")
    if deposito is not None and deposito.estado == ENVIADA:
        hallazgo("ya_enviado", ERROR, f"El depósito de {ejercicio.anio} ya consta enviado al Registro Mercantil", str(ejercicio.anio))
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo, h.referencia))


# ---------------------------------------------------------------------------------------------- DEPOSITO.XML

def _fecha_d2(dia: date) -> str:
    return f"{dia:%d.%m.%Y}"


def _nombre_d2(nombre: str) -> str:
    """«Lopez García de Soto, Elena» → «lopez garcia de soto , elena»: como lo escribe el programa anterior."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s*,\s*", " , ", sin_tildes.strip().lower())


def _pais_d2(nacionalidad: str) -> str:
    return "ES" if (nacionalidad or "").strip().upper().startswith("ESP") else ""


def _persona_fisica(nif: str) -> bool:
    return bool(nif) and (nif[0].isdigit() or nif[0].upper() in "XYZKLM")


def claves_del_formulario(empresa: Empresa, ejercicio: Ejercicio, importes: Importes, *, pmp: tuple[int | None, int | None] = (None, None), organo: tuple[int | None, int | None, int | None, int | None] = (None,) * 4,
                          socios: list[pdf.SocioLibro] | None = None, hoy: date | None = None, paginas: int = 0, aplicacion: Decimal | None = None) -> list[tuple[str, str]]:
    """Los pares (código, valor) del formulario de D2, como los lleva el `DEPOSITO.xml` que el programa anterior generó para 2025."""
    fin, ini = ejercicio.fecha_fin, ejercicio.fecha_inicio
    ini_ant, fin_ant = date(ini.year - 1, ini.month, ini.day), date(fin.year - 1, fin.month, min(fin.day, 28 if fin.month == 2 else fin.day))
    texto = lambda v: (v or "").strip()  # noqa: E731
    cnae = str(int(texto(empresa.cnae))) if re.fullmatch(r"\d{3,4}", texto(empresa.cnae)) else ""  # D2 usa la CNAE-2025 sin el cero inicial: 0125 → 125 (vacío da «el CNAE no es válido» al importar)
    claves: list[tuple[str, str]] = [
        ("1012", "1"), ("1037", texto(empresa.email)), ("2009", texto(empresa.actividad)), ("2014", cnae), ("1010", texto(empresa.nif).upper()), ("1008", re.sub(r"\D", "", empresa.codigo_irus or "")),
        ("1020", empresa.nombre.strip()), ("1022", texto(empresa.domicilio)), ("1023", texto(empresa.poblacion)), ("1025", texto(empresa.provincia_ine)), ("1024", texto(empresa.codigo_postal)), ("1901", str(paginas)),  # 1901: nº de páginas presentadas (PID_023)
        ("1031", lo._telefono(empresa.telefono)), ("1902", "0"),
    ]
    mujeres, miembros, mujeres_ant, miembros_ant = organo
    claves += [(c, str(v)) for c, v in (("4212", mujeres), ("4213", miembros)) if v is not None]
    claves += [("11021", str(ini.year)), ("11022", str(ini.month)), ("11023", str(ini.day)), ("11011", str(fin.year)), ("11012", str(fin.month)), ("11013", str(fin.day)),
               ("110219", str(ini_ant.year)), ("110229", str(ini_ant.month)), ("110239", str(ini_ant.day)), ("110119", str(fin_ant.year)), ("110129", str(fin_ant.month)), ("110139", str(fin_ant.day))]
    if pmp[0] is not None:
        claves.append(("94705", _numero(Decimal(pmp[0]))))
    claves += [(c, str(v)) for c, v in (("42129", mujeres_ant), ("42139", miembros_ant)) if v is not None]
    if pmp[1] is not None:
        claves.append(("947059", _numero(Decimal(pmp[1]))))
    for l in importes.filas:
        claves += [(c, _numero(v)) for c, v in ((l.codigo, l.actual), (l.codigo + "9", l.anterior)) if v or l.codigo in ("10000", "30000")]
    resultado = next((f for f in importes.filas if f.id == "D" and f.es_pyg), None)
    if resultado is not None:  # la base de reparto y su aplicación (D2 las exige con beneficio, PID_034, y las exige vacías con pérdida): saldo de la PyG, total de la base, total aplicado
        for codigo, aplicado, importe in (("", aplicacion, resultado.actual), ("9", None, resultado.anterior)):
            if importe > 0:
                claves += [(f"91000{codigo}", _numero(importe)), (f"91004{codigo}", _numero(importe)), (f"91011{codigo}", _numero(aplicado if aplicado else importe)), (f"91012{codigo}", _numero(aplicado if aplicado else importe))]
    claves += list(RESPUESTAS_FIJAS[:3])
    socios = [s for s in (socios or []) if s.porcentaje > 25]  # solo los titulares reales: más del 25 % (D2 rechaza las filas con menos, PTR_0928…)
    if socios:  # los titulares: cada uno ocupa diez códigos (8230001…8230008, 8230011…8230018…)
        claves += [("8234001", str(len(socios))), ("8234002", _fecha_d2(hoy or date.today()))]
        for k, s in enumerate(socios):
            pais = _pais_d2(s.nacionalidad)
            for base in (8230001 + 10 * k, 8230101 + 10 * k):  # la tabla I.A (socios) y la I.B (titulares reales): D2 exige la segunda si se rellena la primera (PTR_1698)
                claves += [(str(base), _nombre_d2(s.nombre)), (str(base + 1), pais), (str(base + 2), "1" if _persona_fisica(s.nif) else "2"), (str(base + 3), s.nif.upper()),
                           (str(base + 4), s.nacimiento.replace("/", ".")), (str(base + 5), pais), (str(base + 6), pais), (str(base + 7), f"{s.porcentaje:.2f}")]
    claves += [RESPUESTAS_FIJAS[3]]
    claves += [("8081001", codigo_del_registro(empresa)), ("8081002", texto(empresa.registro_tomo)), ("8081003", texto(empresa.registro_folio)), ("8081004", texto(empresa.registro_hoja)),
               ("8080030", str(fin.day)), ("8080020", str(fin.month)), ("8080190", str(fin.year))]
    claves += list(RESPUESTAS_FIJAS[4:13]) + [RESPUESTAS_FIJAS[13]]
    apellidos = " ".join(x for x in (texto(empresa.presentador_apellido1), texto(empresa.presentador_apellido2)) if x)
    if texto(empresa.presentador_nombre):
        presentador = f"{apellidos} , {texto(empresa.presentador_nombre)}"
        claves += [("8081201", presentador.upper()), ("8081202", texto(empresa.presentador_nif).upper()), ("8081203", texto(empresa.presentador_domicilio)), ("8081204", texto(empresa.presentador_poblacion)),
                   ("8081205", texto(empresa.presentador_cp)), ("8081206", texto(empresa.provincia_ine)), RESPUESTAS_FIJAS[14], ("8081208", lo._telefono(empresa.presentador_telefono)),
                   ("8081209", texto(empresa.presentador_email)), ("8091001", presentador.lower())]
    vistos, unicas = set(), []
    for codigo, valor in claves:  # un código no se repite: vale el primero. Lo que no tiene valor no se emite, salvo el CNAE (D2 lo espera aunque vaya vacío)
        if codigo not in vistos and (valor != "" or codigo == "2014"):
            vistos.add(codigo)
            unicas.append((codigo, valor))
    return unicas


def deposito_xml(empresa: Empresa, ejercicio: Ejercicio, claves: list[tuple[str, str]]) -> str:
    """`DEPOSITO.xml`: el «Esquema» de D2, con su cabecera y una clave por dato."""
    lineas = ['<?xml version="1.0" encoding="utf-8"?>', '<Esquema xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">', "  <Cabecera>", f"    <CIF>{escape((empresa.nif or '').strip().upper())}</CIF>",
              f"    <RazonSocial>{escape(empresa.nombre.strip())}</RazonSocial>", "    <TipoCuestionario>Pymes</TipoCuestionario>",
              "    <IdiomaCuestionario>Castellano</IdiomaCuestionario>", "    <MemoriaNormalizada>false</MemoriaNormalizada>", f"    <Ejercicio>{ejercicio.anio}</Ejercicio>", "  </Cabecera>", "  <Claves>"]
    for codigo, valor in claves:
        lineas += ["    <Clave>", f"      <Codigo>{codigo}</Codigo>", f"      <Valor>{escape(valor)}</Valor>", "    </Clave>"]
    lineas += ["  </Claves>", "</Esquema>"]
    return "\n".join(lineas)


def xbrl_del_deposito(empresa: Empresa, ejercicio: Ejercicio, importes: Importes, deposito: DepositoCuentas, cierre: dict[str, str] | None = None, paginas: int = 0) -> str:
    """El `DEPOSITO.xbrl` de este depósito: la identificación de la sociedad, el órgano de administración, el periodo medio de pago y los importes del balance y de la cuenta de pérdidas y ganancias."""
    texto = lambda v: (v or "").strip()  # noqa: E731
    cnae = f"{int(texto(empresa.cnae)):04d}" if re.fullmatch(r"\d{3,4}", texto(empresa.cnae)) else ""
    return xb.xbrl(nif=texto(empresa.nif).upper(), nombre=empresa.nombre.strip(), domicilio=texto(empresa.domicilio), poblacion=texto(empresa.poblacion), provincia_ine=texto(empresa.provincia_ine),
                   codigo_postal=texto(empresa.codigo_postal), telefono=lo._telefono(empresa.telefono), email=texto(empresa.email), actividad=texto(empresa.actividad), cnae=cnae,
                   inicio=ejercicio.fecha_inicio, fin=ejercicio.fecha_fin, balance=[(f.id, f.actual, f.anterior) for f in importes.filas if not f.es_pyg],
                   pyg=[(f.id, f.actual, f.anterior) for f in importes.filas if f.es_pyg], mujeres=deposito.mujeres_organo, miembros=deposito.miembros_organo,
                   mujeres_anterior=deposito.mujeres_organo_anterior, miembros_anterior=deposito.miembros_organo_anterior, pmp=deposito.pmp_actual, pmp_anterior=deposito.pmp_anterior,
                   personal={k: str(_dec(v)) for k, v in personal_de(cierre or {}).items()}, microempresa=(cierre or {}).get("microempresa") == "1", paginas=paginas,
                   aplicacion=elementos_de_aplicacion(importes, cierre or {}))


ELEMENTOS_APLICACION = {"reserva_legal": "PropuestaResultadoAplicacionAReservaLegal", "reservas_especiales": "PropuestaAplicacionAReservasEspeciales", "reservas_voluntarias": "PropuestaAplicacionAReservasVoluntarias",
                        "dividendos": "PropuestaAplicacionADividendos", "remanente_y_otros": "PropuestaAplicacionARemanenteYOtros", "compensacion_perdidas": "PropuestaAplicacionACompensacionPerdidasEjerciciosAnteriores"}
ELEMENTOS_BASE = {"reparto_remanente": "BaseRepartoResultadoRemanente", "reparto_voluntarias": "BaseRepartoResultadoReservasVoluntarias", "reparto_otras": "RepartoOtrasReservasLibreDisposicion"}


def elementos_de_aplicacion(importes: Importes, cierre: dict[str, str]) -> list[tuple[str, str, Decimal]]:
    """La base de reparto y la aplicación del resultado como los lleva el XBRL (con pérdida no se escribe nada: PID_034). Los nombres salen de los depósitos reales del programa anterior."""
    resultado = next((f for f in importes.filas if f.id == "D" and f.es_pyg), None)
    salida: list[tuple[str, str, Decimal]] = []
    if resultado is None:
        return salida
    if resultado.actual > 0:
        base = [(n, _dec(cierre.get(c))) for c, n in ELEMENTOS_BASE.items() if _dec(cierre.get(c))]
        total_base = resultado.actual + sum((v for _, v in base), CERO)
        aplicado = [(n, _dec(cierre.get(c))) for c, n in ELEMENTOS_APLICACION.items() if _dec(cierre.get(c))]
        total_aplicado = sum((v for _, v in aplicado), CERO)
        salida += [("BaseRepartoResultadoSaldoCuentaPerdidasGanancias", "D.ACTUAL", resultado.actual), *((n, "D.ACTUAL", v) for n, v in base),
                   ("BaseTotalBaseRepartoResultadoTotalAplicacion", "D.ACTUAL", total_base), *((n, "D.ACTUAL", v) for n, v in aplicado),
                   ("PropuestaAplicacionATotalAplicacionTotalBaseReparto", "D.ACTUAL", total_aplicado)]
    if resultado.anterior > 0:  # el desglose del año anterior no lo conoce Conta: solo el saldo y el total de la base
        salida += [("BaseRepartoResultadoSaldoCuentaPerdidasGanancias", "D.ANTERIOR", resultado.anterior), ("BaseTotalBaseRepartoResultadoTotalAplicacion", "D.ANTERIOR", resultado.anterior)]
    return salida


def huella_del_zip(datos: bytes) -> str:
    """El SHA-256 del fichero ZIP en base64: así calcula D2 la «huella digital» (de su propio ZIP, que reconstruye al importar; por eso la de Conta no sirve para la certificación)."""
    return base64.b64encode(hashlib.sha256(datos).digest()).decode()


def empaquetar(ruta: Path, xbrl: str, xml: str, memoria: bytes) -> str:
    """El ZIP que D2 importa (`DEPOSITO.xbrl`, `DEPOSITO.xml` y `MEMORIA.pdf`, como el del programa anterior), igual cada vez que sale el mismo contenido (fechas fijas): devuelve su huella."""
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in (("DEPOSITO.xbrl", xbrl.encode("utf-8")), ("DEPOSITO.xml", xml.encode("utf-8")), ("MEMORIA.pdf", memoria)):
            info = zipfile.ZipInfo(nombre, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, datos)
    return huella_del_zip(ruta.read_bytes())


# ---------------------------------------------------------------------------------------------- preparar

def carpeta_del_deposito(raiz_almacen: Path, empresa: Empresa, anio: int) -> Path:
    return Path(raiz_almacen) / f"{empresa.codigo:03d}" / str(anio) / "deposito"


def nombre_del_zip(empresa: Empresa, anio: int) -> str:
    return f"{nombre_corto(empresa)}_DEPOSITO_{anio}.zip"  # EMPRESA_A_DEPOSITO_2025.zip


def _deposito(sesion: Session, ejercicio: Ejercicio) -> DepositoCuentas | None:
    return sesion.scalar(select(DepositoCuentas).where(DepositoCuentas.empresa_id == ejercicio.empresa_id, DepositoCuentas.anio == ejercicio.anio))


def organo_anterior(sesion: Session, ejercicio: Ejercicio) -> DepositoCuentas | None:
    """El depósito del año anterior, de donde se toman por defecto los datos del órgano de administración."""
    return sesion.scalar(select(DepositoCuentas).where(DepositoCuentas.empresa_id == ejercicio.empresa_id, DepositoCuentas.anio == ejercicio.anio - 1))


def preparar_deposito(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, fecha_formulacion: date | None = None, fecha_aprobacion: date | None = None, pmp_actual: int | None = None,
                      pmp_anterior: int | None = None, mujeres_organo: int | None = None, miembros_organo: int | None = None, mujeres_organo_anterior: int | None = None,
                      miembros_organo_anterior: int | None = None, cierre: dict[str, str] | None = None, solo_guardar: bool = False, usuario: str | None = None) -> DepositoCuentas:
    """Genera el ZIP del depósito para D2 (`DEPOSITO.xml` y `MEMORIA.pdf`) con su huella, y deja anotado el depósito. Sustituye lo generado antes mientras no esté enviado. No hace commit."""
    empresa = ejercicio.empresa
    deposito = _deposito(sesion, ejercicio)
    if deposito is None:
        deposito = DepositoCuentas(empresa_id=empresa.id, anio=ejercicio.anio, estado=PREPARADA)
        sesion.add(deposito)
    deposito.fecha_formulacion = fecha_formulacion if fecha_formulacion is not None else deposito.fecha_formulacion
    aprobada = acta_de_aprobacion(sesion, ejercicio)
    deposito.fecha_aprobacion = fecha_aprobacion or deposito.fecha_aprobacion or (aprobada.fecha if aprobada else None)
    for campo, valor in (("pmp_actual", pmp_actual), ("pmp_anterior", pmp_anterior), ("mujeres_organo", mujeres_organo), ("miembros_organo", miembros_organo),
                         ("mujeres_organo_anterior", mujeres_organo_anterior), ("miembros_organo_anterior", miembros_organo_anterior)):
        if valor is not None:
            setattr(deposito, campo, valor)
    previo = organo_anterior(sesion, ejercicio)
    if previo is not None and previo.miembros_organo is not None:  # el año anterior: lo que se depositó entonces, salvo que se haya escrito otra cosa
        deposito.mujeres_organo_anterior = deposito.mujeres_organo_anterior if mujeres_organo_anterior is not None else previo.mujeres_organo
        deposito.miembros_organo_anterior = deposito.miembros_organo_anterior if miembros_organo_anterior is not None else previo.miembros_organo
    if deposito.miembros_organo_anterior is None:  # el órgano rara vez cambia: sin otro dato, el del año anterior es el de este (D2 lo pide: PID_044 y PID_046)
        deposito.mujeres_organo_anterior, deposito.miembros_organo_anterior = deposito.mujeres_organo, deposito.miembros_organo
    if cierre is not None:
        guardado = cierre_guardado(deposito)
        guardado.update({k: v.strip() for k, v in cierre.items() if k in CLAVES_CIERRE})
        for c in [c for c in (*PERSONAL, "paginas", "participaciones") if guardado.get(c, "") != ""]:
            _dec(guardado[c])  # que sean números
        socios_cierre, _ = lo.socios_del_libro(sesion, empresa, ejercicio.fecha_fin)
        propuesta = propuesta_de_cierre(sesion, ejercicio, importes_de_las_cuentas(sesion, ejercicio), socios_cierre, deposito.fecha_aprobacion)
        for c in [c for c, v in guardado.items() if c in CLAVES_CIERRE and (v == "" or v == propuesta.get(c))]:
            del guardado[c]  # vacío o igual a lo que propone Conta: no se guarda, para que siga a las cuentas
        deposito.cierre = json.dumps(guardado, ensure_ascii=False)
    if solo_guardar:
        sesion.flush()
        return deposito
    errores = [h.mensaje for h in controlar(sesion, ejercicio, deposito) if h.gravedad == ERROR]
    if errores:
        raise ErrorContable("No se puede preparar el depósito: " + "; ".join(errores))
    importes = importes_de_las_cuentas(sesion, ejercicio)
    cierre_final = cierre_efectivo(sesion, ejercicio, deposito, importes)
    carpeta = carpeta_del_deposito(raiz_almacen, empresa, ejercicio.anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    socios, _ = lo.socios_del_libro(sesion, empresa, ejercicio.fecha_fin)
    particip = int(cierre_final["participaciones"]) if cierre_final.get("participaciones", "").isdigit() else None
    bloques, _ = lo.memoria(sesion, ejercicio, participaciones=particip)
    memoria = carpeta / "MEMORIA.pdf"
    paginas_memoria = pdf.pdf_memoria(memoria, lo.cabecera_de(empresa), ejercicio.anio, bloques)
    paginas = int(_dec(cierre_final["paginas"])) if cierre_final.get("paginas", "") != "" else paginas_memoria + 1  # la memoria y la certificación (una página)
    claves = claves_del_formulario(empresa, ejercicio, importes, pmp=(deposito.pmp_actual, deposito.pmp_anterior), socios=socios, paginas=paginas, hoy=deposito.fecha_aprobacion,
                                   organo=(deposito.mujeres_organo, deposito.miembros_organo, deposito.mujeres_organo_anterior, deposito.miembros_organo_anterior), aplicacion=total_aplicacion(cierre_final))
    xml =deposito_xml(empresa, ejercicio, claves)
    xbrl = xbrl_del_deposito(empresa, ejercicio, importes, deposito, cierre_final, paginas)
    (carpeta / "DEPOSITO.xml").write_bytes(xml.encode("utf-8"))
    (carpeta / "DEPOSITO.xbrl").write_bytes(xbrl.encode("utf-8"))
    zip_ruta = carpeta / nombre_del_zip(empresa, ejercicio.anio)
    anterior_zip = deposito.zip_huella
    deposito.zip_huella = empaquetar(zip_ruta, xbrl, xml, memoria.read_bytes())
    deposito.zip_nombre = zip_ruta.name
    cac = carpeta / nombre_de_la_certificacion(empresa, ejercicio.anio)
    if anterior_zip is not None and anterior_zip != deposito.zip_huella:  # el ZIP ha cambiado: lo importado en D2 y su huella ya no valen
        deposito.huella_d2 = None
        cac.unlink(missing_ok=True)
    if deposito.huella_d2:  # la certificación depende de datos que no están en el ZIP (fechas, aplicación del resultado): se rehace
        pdf.pdf_certificacion(cac, certificacion_de(sesion, ejercicio, deposito, cierre_final, importes))
    deposito.estado = PREPARADA if deposito.estado != ENVIADA else deposito.estado
    deposito.preparado_en, deposito.preparado_por = datetime.now(), usuario or _usuario()
    deposito.carpeta_ruta = carpeta.relative_to(Path(raiz_almacen)).as_posix()
    deposito.xml_sha256 = hashlib.sha256(xml.encode("utf-8")).hexdigest()
    sesion.flush()
    return deposito


# ---------------------------------------------------------------------------------------------- la huella de D2 y la certificación

def leer_huella(texto: str | None = None, pdf_o_txt: bytes | None = None) -> str:
    """La huella (SHA-256 en base64: 43 caracteres y un «=») escrita a mano o dentro del `Huella.pdf` / `Huella.txt` que genera D2."""
    if pdf_o_txt:
        if pdf_o_txt.startswith(b"%PDF"):
            import io

            from pypdf import PdfReader

            try:
                texto = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_o_txt)).pages)
            except Exception as e:  # noqa: BLE001
                raise ErrorContable(f"No se puede leer el PDF de la huella: {e}") from None
        else:
            texto = pdf_o_txt.decode("utf-8-sig", errors="replace")
    m = re.search(r"[A-Za-z0-9+/]{43}=", texto or "")
    if m is None:
        raise ErrorContable("No encuentro la huella (43 letras o cifras y un «=», como OPk+H1A/cxIJBa73Vn5Nmx7x36jzO6ngE5NZzP4vpZw=)")
    return m.group(0)


def registrar_huella(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, huella: str | None = None, pdf_o_txt: bytes | None = None) -> DepositoCuentas:
    """Guarda la huella que generó D2 al importar el ZIP y prepara la certificación del acuerdo de la junta con ella. No hace commit."""
    deposito = _deposito(sesion, ejercicio)
    if deposito is None or not deposito.zip_nombre:
        raise ErrorContable("Primero hay que preparar el depósito y importar su ZIP en D2")
    if deposito.estado == ENVIADA:
        raise ErrorContable("El depósito ya consta enviado")
    deposito.huella_d2 = leer_huella(huella, pdf_o_txt)
    importes = importes_de_las_cuentas(sesion, ejercicio)
    carpeta = carpeta_del_deposito(raiz_almacen, ejercicio.empresa, ejercicio.anio)
    pdf.pdf_certificacion(carpeta / nombre_de_la_certificacion(ejercicio.empresa, ejercicio.anio), certificacion_de(sesion, ejercicio, deposito, cierre_efectivo(sesion, ejercicio, deposito, importes), importes))
    sesion.flush()
    return deposito


# ---------------------------------------------------------------------------------------------- el envío al Registro

def registrar_envio(sesion: Session, ejercicio: Ejercicio, raiz_almacen: Path, *, pdf_acuse: bytes | None = None, fecha: date | None = None, referencia: str | None = None) -> DepositoCuentas:
    """Deja constancia de que las cuentas se depositaron. Con el PDF del acuse se leen la fecha, la referencia y el nº de entrada y se guarda el PDF; sin él, se necesita la fecha. No hace commit."""
    empresa = ejercicio.empresa
    if pdf_acuse and not pdf_acuse.startswith(b"%PDF"):
        raise ErrorContable("El acuse debe ser el PDF que devuelve el Registro")
    if pdf_acuse and len(pdf_acuse) > 10 * 1024 * 1024:
        raise ErrorContable("El PDF del acuse pesa más de 10 MB")
    leida = lo.leer_acuse(pdf_acuse) if pdf_acuse else {}
    referencia = (referencia or leida.get("referencia") or "").strip() or None
    if referencia and leida.get("referencia") and referencia != leida["referencia"]:
        raise ErrorContable(f"La referencia tecleada ({referencia}) no coincide con la del acuse ({leida['referencia']})")
    esperada = f"{(empresa.nif or '').strip().upper()}{ejercicio.anio}"
    if leida.get("referencia") and esperada not in leida["referencia"].upper():
        raise ErrorContable(f"El acuse es de otro ejercicio o de otra empresa (referencia {leida['referencia']}; la del depósito de estas cuentas contendría {esperada})")
    fecha = fecha or leida.get("fecha")
    if fecha is None:
        raise ErrorContable("Falta la fecha del envío (se lee sola del PDF del acuse)")
    if fecha > date.today():
        raise ErrorContable("La fecha del envío no puede ser futura")
    deposito = _deposito(sesion, ejercicio)
    if deposito is None:  # cuentas depositadas fuera de Conta: queda constancia igualmente
        deposito = DepositoCuentas(empresa_id=empresa.id, anio=ejercicio.anio)
        sesion.add(deposito)
    if pdf_acuse:
        carpeta = carpeta_del_deposito(raiz_almacen, empresa, ejercicio.anio)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{re.sub(r'[^A-Za-z0-9]', '', referencia or 'Deposito')}_Acuse_Entrada.pdf"
        ruta.write_bytes(pdf_acuse)
        deposito.acuse_ruta = ruta.relative_to(Path(raiz_almacen)).as_posix()
    deposito.estado, deposito.enviado_en, deposito.referencia = ENVIADA, fecha, referencia
    deposito.numero_entrada = leida.get("entrada") or deposito.numero_entrada
    sesion.flush()
    from conta_pridalac.servicios.huellas import anotar_al_confirmar

    anotar_al_confirmar(sesion, raiz_almacen, empresa.codigo, f"envío del {DESCRIPCION_ACUSE} {ejercicio.anio}")
    return deposito
