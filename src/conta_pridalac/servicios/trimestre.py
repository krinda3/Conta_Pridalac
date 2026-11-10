"""Lista de trabajo del trimestre: las facturas que Verifactu ha reconocido, a la espera de conciliarse con el extracto.

El Excel de «facturas recibidas» de Verifactu se lee **por el nombre de la columna**. Cada fila pasa a `FacturaTrimestre`; no se contabiliza nada todavía. Cargar el mismo Excel dos veces (o uno
que se solape con otro) no repite facturas: la clave es NIF + nº de factura + fecha + total. Las propuestas se calculan con `servicios/conciliacion.py` cada vez que se piden, así que cambiar un
extracto o una palabra de conciliación se nota al momento.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Banco, CorrespondenciaTercero, Cuenta, Ejercicio, Empresa, ExtractoLinea, Factura, FacturaTrimestre, PalabraConciliacion, Pago, Tercero, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.conciliacion import FacturaPorConciliar, LineaPorConciliar, ResultadoConciliacion, coincide_el_texto, conciliar
from conta_pridalac.servicios.extractos import _clave_de_texto, _fecha
from conta_pridalac.servicios.importar_facturas import FilaExcel, _tercero_por_nif_o_nombre, importar, normalizar_nif, planificar

CERO = Decimal("0.00")
MARGEN_ANTES, MARGEN_DESPUES = 10, 60  # días de extracto que se miran antes de la primera factura y después de la última

# nombre de columna del Excel de Verifactu (en minúsculas, sin tildes ni signos) → campo
COLUMNAS = {
    "nombre": "empresa", "nif": "cif", "fecha_factura": "fechafactura", "numero_factura": "numfactura", "base": "baseimponible", "porcentaje_iva": "iva", "cuota_iva": "montoiva",
    "total": "montototal", "ruta_pdf": "rutacompleta", "fecha_contable": "fechacontable", "porcentaje_iva2": "iva2", "cuota_iva2": "montoiva2", "porcentaje_iva3": "iva3", "cuota_iva3": "montoiva3",
    "pago_fecha": "fechapago", "pago_concepto": "conceptopago", "pago_subcuenta": "subcuentadepago",
}
OBLIGATORIAS = ("nombre", "fecha_factura", "total")


COLUMNAS_EMITIDAS = {  # campo → nombres de columna posibles del Excel de facturas emitidas de Verifactu (en minúsculas, sin tildes ni signos)
    "numero": ("nfactura", "nofactura", "numfactura", "numerofactura"), "fecha": ("fechaexpedicion", "fecha"), "emisor_nif": ("emisornif",), "nombre": ("clientenombre", "cliente"),
    "nif": ("clientenif", "cifcliente"), "base": ("baseimponible",), "porcentaje_iva": ("iva",), "cuota_iva": ("cuotaiva",), "total": ("total",), "estado": ("estado",),
}


@dataclass
class ResultadoCarga:
    fichero: str
    leidas: int = 0
    nuevas: int = 0
    repetidas: int = 0
    recuperadas: int = 0  # las que el usuario había borrado de la lista y vuelven al cargar el Excel otra vez
    avisos: list[str] = field(default_factory=list)


def _dinero(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor).replace(",", ".")).quantize(CERO)
    except InvalidOperation:
        return None


def _texto(valor) -> str:
    return str(valor).strip() if valor is not None else ""


def leer_recibidas_verifactu(contenido: bytes) -> list[dict]:
    """Las filas del Excel de facturas recibidas de Verifactu, como diccionarios con los campos de `COLUMNAS`. Lanza `ErrorContable` si no es ese Excel."""
    try:
        hoja = load_workbook(BytesIO(contenido), data_only=True, read_only=True).worksheets[0]
    except Exception as e:  # noqa: BLE001 - un fichero que no es Excel puede fallar de muchas maneras
        raise ErrorContable(f"No se puede leer el Excel: {e}") from e
    filas = hoja.iter_rows(values_only=True)
    cabecera = next(filas, None)
    if not cabecera:
        raise ErrorContable("El Excel está vacío")
    posicion = {_clave_de_texto(c): i for i, c in enumerate(cabecera) if c is not None}
    falta = [c for c in OBLIGATORIAS if COLUMNAS[c] not in posicion]
    if falta:
        raise ErrorContable("No parece el Excel de facturas recibidas de Verifactu: faltan las columnas " + ", ".join(COLUMNAS[c] for c in falta))
    leidas = []
    for fila in filas:
        if not any(v is not None for v in fila):
            continue
        d = {campo: (fila[posicion[col]] if col in posicion and posicion[col] < len(fila) else None) for campo, col in COLUMNAS.items()}
        leidas.append(d)
    return leidas


def leer_emitidas_verifactu(contenido: bytes) -> list[dict]:
    """Las filas del Excel de facturas emitidas de Verifactu (un Excel por empresa), como diccionarios con los campos de `COLUMNAS_EMITIDAS`. Lanza `ErrorContable` si no es ese Excel."""
    try:
        hoja = load_workbook(BytesIO(contenido), data_only=True, read_only=True).worksheets[0]
    except Exception as e:  # noqa: BLE001
        raise ErrorContable(f"No se puede leer el Excel: {e}") from e
    filas = hoja.iter_rows(values_only=True)
    cabecera = next(filas, None)
    if not cabecera:
        raise ErrorContable("El Excel está vacío")
    posicion = {}
    for i, c in enumerate(cabecera):
        if c is not None:
            posicion.setdefault(_clave_de_texto(c), i)
    columna = {campo: next((posicion[n] for n in nombres if n in posicion), None) for campo, nombres in COLUMNAS_EMITIDAS.items()}
    falta = [c for c in ("numero", "fecha", "nombre", "total") if columna[c] is None]
    if falta:
        raise ErrorContable("No parece el Excel de facturas emitidas de Verifactu: faltan las columnas " + ", ".join(COLUMNAS_EMITIDAS[c][0] for c in falta))
    return [{campo: (fila[i] if i is not None and i < len(fila) else None) for campo, i in columna.items()} for fila in filas if any(v is not None for v in fila)]


def cargar_emitidas(sesion: Session, empresa_id: int, fichero: str, contenido: bytes) -> ResultadoCarga:
    """Guarda en la lista de trabajo las facturas emitidas del Excel que todavía no están y enlaza las que Conta ya tiene contabilizadas. No hace commit."""
    resultado = ResultadoCarga(fichero=fichero)
    propio = normalizar_nif(getattr(sesion.get(Empresa, empresa_id), "nif", ""))
    existentes = set(sesion.scalars(select(FacturaTrimestre.clave).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == "E")))
    recuperables = {f.clave: f for f in sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == "E", FacturaTrimestre.descartada.is_(True),
                                                                                          FacturaTrimestre.factura_id.is_(None), FacturaTrimestre.descartada_por.is_distinct_from("duplicada")))}
    for n, d in enumerate(leer_emitidas_verifactu(contenido), start=2):
        resultado.leidas += 1
        emisor = normalizar_nif(_texto(d["emisor_nif"]))
        if propio and emisor and emisor != propio:
            raise ErrorContable(f"Fila {n}: la factura es de la empresa con NIF {d['emisor_nif']} y esta empresa tiene el {propio}. Cargue el Excel de esta empresa (Verifactu saca uno por empresa)")
        fecha, total = _fecha(d["fecha"]), _dinero(d["total"])
        if fecha is None or total is None or not _texto(d["nombre"]):
            resultado.avisos.append(f"Fila {n}: falta el cliente, la fecha o el total; no se carga")
            continue
        nif, numero = _texto(d["nif"]), _texto(d["numero"])
        clave = clave_de(nif, numero, fecha, total)
        if clave in existentes:
            if clave in recuperables:  # la había borrado el usuario: vuelve a la lista
                fila = recuperables.pop(clave)
                fila.descartada, fila.descartada_por = False, None
                resultado.recuperadas += 1
            else:
                resultado.repetidas += 1
            continue
        existentes.add(clave)
        estado = _texto(d["estado"])
        if estado and any(m in estado.lower() for m in ("error", "anulad", "rechaz")):
            resultado.avisos.append(f"Fila {n}: la factura {numero} está en estado «{estado}» en Verifactu; se carga igualmente, revísela")
        sesion.add(FacturaTrimestre(empresa_id=empresa_id, sentido="E", clave=clave, fichero=fichero, nombre=_texto(d["nombre"]), nif=nif, fecha_factura=fecha, numero_factura=numero,
                                    base=_dinero(d["base"]), porcentaje_iva=_dinero(d["porcentaje_iva"]), cuota_iva=_dinero(d["cuota_iva"]), total=total, iva_extra=""))
        resultado.nuevas += 1
    if not resultado.leidas:
        raise ErrorContable("El Excel no trae ninguna factura")
    sesion.flush()
    vincular_emitidas_contabilizadas(sesion, empresa_id)
    return resultado


def vincular_emitidas_contabilizadas(sesion: Session, empresa_id: int) -> int:
    """Marca como hechas las emitidas de la lista que Conta ya tiene (migradas del programa anterior o dadas de alta a mano): mismo nº de factura y fecha, o, si Conta no tiene el número, mismo cliente, fecha y total."""
    ya = list(sesion.scalars(select(Factura).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(Ejercicio.empresa_id == empresa_id, Factura.sentido == "E")))
    por_numero = {(_numero(f.numero_factura or ""), f.fecha_factura): f for f in ya if _numero(f.numero_factura or "")}
    por_datos = {(normalizar_nif(f.tercero.nif if f.tercero else ""), f.fecha_factura, f.total): f for f in ya if f.tercero is not None}
    n = 0
    for fac in sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == "E", FacturaTrimestre.factura_id.is_(None))):
        f = por_numero.get((_numero(fac.numero_factura), fac.fecha_factura)) if _numero(fac.numero_factura) else None
        f = f or por_datos.get((normalizar_nif(fac.nif), fac.fecha_factura, fac.total))
        if f is not None:
            fac.factura_id, n = f.id, n + 1
    return n


def clave_de(nif: str, numero: str, fecha: date, total: Decimal) -> str:
    return f"{_clave_de_texto(nif)}|{_clave_de_texto(numero)}|{fecha:%Y%m%d}|{total}"


def cargar_recibidas(sesion: Session, empresa_id: int, fichero: str, contenido: bytes) -> ResultadoCarga:
    """Guarda en la lista de trabajo las facturas del Excel que todavía no están. No hace commit."""
    resultado = ResultadoCarga(fichero=fichero)
    propio = normalizar_nif(getattr(sesion.get(Empresa, empresa_id), "nif", ""))
    existentes = set(sesion.scalars(select(FacturaTrimestre.clave).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == "R")))
    recuperables = {f.clave: f for f in sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == "R", FacturaTrimestre.descartada.is_(True),
                                                                                          FacturaTrimestre.factura_id.is_(None), FacturaTrimestre.descartada_por.is_distinct_from("duplicada")))}
    for n, d in enumerate(leer_recibidas_verifactu(contenido), start=2):
        resultado.leidas += 1
        fecha, total = _fecha(d["fecha_factura"]), _dinero(d["total"])
        if fecha is None or total is None or not _texto(d["nombre"]):
            resultado.avisos.append(f"Fila {n}: falta el nombre, la fecha o el total; no se carga")
            continue
        nif, numero = _texto(d["nif"]), _texto(d["numero_factura"])
        if propio and normalizar_nif(nif) == propio:
            resultado.avisos.append(f"Fila {n}: Verifactu trae como NIF del proveedor el de la propia empresa ({nif}), que es el del destinatario de la factura. Se ignora y el proveedor se busca por nombre")
        clave = clave_de(nif, numero, fecha, total)
        if clave in existentes:
            if clave in recuperables:  # la había borrado el usuario: vuelve a la lista
                fila = recuperables.pop(clave)
                fila.descartada, fila.descartada_por = False, None
                resultado.recuperadas += 1
            else:
                resultado.repetidas += 1
            continue
        existentes.add(clave)
        extra = ";".join(f"{_dinero(d[f'porcentaje_iva{k}'])} {_dinero(d[f'cuota_iva{k}'])}" for k in (2, 3) if _dinero(d[f"porcentaje_iva{k}"]) is not None)
        sesion.add(FacturaTrimestre(
            empresa_id=empresa_id, sentido="R", clave=clave, fichero=fichero, nombre=_texto(d["nombre"]), nif=nif, fecha_factura=fecha, numero_factura=numero, base=_dinero(d["base"]),
            porcentaje_iva=_dinero(d["porcentaje_iva"]), cuota_iva=_dinero(d["cuota_iva"]), total=total, iva_extra=extra, ruta_pdf=_texto(d["ruta_pdf"]), fecha_contable=_fecha(d["fecha_contable"]),
            pago_fecha=_fecha(d["pago_fecha"]), pago_concepto=_texto(d["pago_concepto"]), pago_subcuenta=_texto(d["pago_subcuenta"]),
        ))
        resultado.nuevas += 1
    if not resultado.leidas:
        raise ErrorContable("El Excel no trae ninguna factura")
    return resultado


GRUPOS_DE_GASTO = ("6", "2", "3")  # gastos, inversiones y existencias: lo que puede ser la contrapartida de una factura recibida
DIAS_ENTRE_COPIAS = 30  # una factura y su justificante de pago no se separan más que esto
MIN_CARACTERES_DE_NUMERO = 4


def _numero(texto: str) -> str:
    """El nº de factura sin signos, sin mayúsculas y sin ceros a la izquierda: «119 / 2026» y «119/2026» son el mismo."""
    return _clave_de_texto(texto).lstrip("0")


def _mismo_numero(a: str, b: str) -> bool:
    a, b = _numero(a), _numero(b)
    if not a or not b:
        return False
    corto, largo = sorted((a, b), key=len)
    return corto == largo or (len(corto) >= MIN_CARACTERES_DE_NUMERO and (corto in largo or largo.startswith(corto)))


def posibles_duplicadas(facturas: list[FacturaTrimestre]) -> dict[int, FacturaTrimestre]:
    """Verifactu reconoce a veces la factura y también el justificante de su pago, y salen dos filas con el mismo importe. Devuelve `{id de la copia: factura original}`.

    Dos facturas son la misma si tienen el mismo total, el mismo proveedor (por nombre o por NIF), fechas a menos de un mes y un número parecido (uno contiene al otro: «FUS2607C00300545» y
    «2607C00300545»). Se exige el número para no confundir facturas distintas del mismo importe (el recibo mensual de la alarma). La copia es la de fecha posterior, que es la del justificante.
    """
    copias: dict[int, FacturaTrimestre] = {}
    ordenadas = sorted(facturas, key=lambda f: (f.fecha_factura, f.id))
    for i, original in enumerate(ordenadas):
        for otra in ordenadas[i + 1:]:
            if otra.id in copias or original.id in copias or otra.total != original.total or not original.total:
                continue
            if (otra.fecha_factura - original.fecha_factura).days > DIAS_ENTRE_COPIAS or not _mismo_numero(original.numero_factura, otra.numero_factura):
                continue
            if _clave_de_texto(original.nif) == _clave_de_texto(otra.nif) or coincide_el_texto(original.nombre, otra.nombre):
                copias[otra.id] = original
    return copias


@dataclass
class Propuestas:
    """El resultado de conciliar la lista de trabajo con los extractos, con los objetos de base de datos a mano para pintarlos."""

    resultado: ResultadoConciliacion
    facturas: dict[str, FacturaTrimestre]
    lineas: dict[str, ExtractoLinea]
    desde: date | None = None
    hasta: date | None = None
    duplicadas: dict[int, FacturaTrimestre] = field(default_factory=dict)  # copia → original; no entran en la conciliación
    pagadas_por_banco: list[FacturaTrimestre] = field(default_factory=list)  # las que el usuario ha dicho que pagó un socio u otro banco sin extracto: tampoco se concilian con el extracto
    sentido: str = "R"  # R recibidas (el dinero sale) o E emitidas (entra)
    periodo: tuple[date, date] | None = None  # el trimestre al que pertenece todo lo que se ve


def limites_del_trimestre(dia: date) -> tuple[date, date]:
    """Primer y último día del trimestre natural que contiene `dia`."""
    q = (dia.month - 1) // 3
    desde = date(dia.year, q * 3 + 1, 1)
    siguiente = date(dia.year + 1, 1, 1) if q == 3 else date(dia.year, q * 3 + 4, 1)
    return desde, siguiente - timedelta(days=1)


def trimestre_de_trabajo(sesion: Session, empresa_id: int, sentido: str = "R") -> tuple[date, date]:
    """El trimestre con el que se trabaja: el que el usuario ha elegido o, si no ha elegido ninguno, el de la factura más reciente de la lista (y si no hay ninguna, el de hoy). Todo se limita a sus fechas."""
    elegido = sesion.scalar(select(Empresa.trimestre_trabajo).where(Empresa.id == empresa_id))
    if elegido and re.fullmatch(r"\d{4}-[1-4]", elegido):
        return limites_del_trimestre(date(int(elegido[:4]), (int(elegido[5]) - 1) * 3 + 1, 1))
    ultima = sesion.scalar(select(func.max(FacturaTrimestre.fecha_factura)).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == sentido, FacturaTrimestre.descartada.is_(False)))
    return limites_del_trimestre(ultima or date.today())


def etiqueta_del_trimestre(periodo: tuple[date, date]) -> str:
    """«4T 2026»."""
    return f"{(periodo[0].month - 1) // 3 + 1}T {periodo[0].year}"


def fijar_trimestre_de_trabajo(sesion: Session, empresa: Empresa, anio: int, trimestre: int) -> None:
    """Elige el trimestre con el que se trabaja. No hace commit."""
    if trimestre not in (1, 2, 3, 4) or not 2000 <= anio <= 2100:
        raise ErrorContable("El trimestre no es válido")
    empresa.trimestre_trabajo = f"{anio}-{trimestre}"


def facturas_pendientes(sesion: Session, empresa_id: int, sentido: str = "R", periodo: tuple[date, date] | None = None) -> list[FacturaTrimestre]:
    consulta = select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.sentido == sentido, FacturaTrimestre.factura_id.is_(None), FacturaTrimestre.descartada.is_(False))
    if periodo is not None:
        consulta = consulta.where(FacturaTrimestre.fecha_factura >= periodo[0], FacturaTrimestre.fecha_factura <= periodo[1])
    return list(sesion.scalars(consulta.order_by(FacturaTrimestre.fecha_factura, FacturaTrimestre.id)))


def descartar(sesion: Session, empresa_id: int, ids: list[int]) -> int:
    """Quita facturas de la lista de trabajo (siguen guardadas, para que volver a cargar el Excel no las devuelva). No toca las ya aplicadas."""
    n = 0
    for f in sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.id.in_(ids), FacturaTrimestre.factura_id.is_(None))):
        f.descartada, f.descartada_por, n = True, "borrada", n + 1
    return n


def quitar_duplicadas(sesion: Session, empresa_id: int) -> list[tuple[FacturaTrimestre, FacturaTrimestre]]:
    """Descarta las posibles duplicadas y devuelve las parejas (copia, original). No hace commit."""
    pendientes = facturas_pendientes(sesion, empresa_id)
    por_id = {f.id: f for f in pendientes}
    quitadas = [(por_id[i], original) for i, original in posibles_duplicadas(pendientes).items()]
    for copia, _ in quitadas:
        copia.descartada, copia.descartada_por = True, "duplicada"
    return quitadas


def proponer(sesion: Session, empresa_id: int, bancos: list[Banco] | None = None, sentido: str = "R", periodo: tuple[date, date] | None = None) -> Propuestas:
    """Concilia las facturas recibidas sin aplicar con las líneas de extracto (de los bancos dados, o de todos) que caen alrededor de sus fechas."""
    periodo = periodo or trimestre_de_trabajo(sesion, empresa_id, sentido)  # sólo el trimestre en que se trabaja: lo pendiente de trimestres anteriores no se mezcla
    todas = facturas_pendientes(sesion, empresa_id, sentido, periodo)
    duplicadas = posibles_duplicadas(todas) if sentido == "R" else {}
    pagadas = [f for f in todas if f.id not in duplicadas and f.pagada_por_id is not None]
    pendientes = [f for f in todas if f.id not in duplicadas and f.pagada_por_id is None]
    desde, hasta = periodo[0] - timedelta(days=MARGEN_ANTES), periodo[1] + timedelta(days=MARGEN_DESPUES)  # las facturas del trimestre se pagan unos días antes o semanas después
    consulta = (select(ExtractoLinea).where(ExtractoLinea.empresa_id == empresa_id, ExtractoLinea.fecha >= desde, ExtractoLinea.fecha <= hasta, ExtractoLinea.movimiento_id.is_(None))
                .order_by(ExtractoLinea.fecha, ExtractoLinea.id))  # las que ya pagaron una factura aplicada no vuelven a ofrecerse
    if bancos:
        consulta = consulta.where(ExtractoLinea.banco_id.in_([b.id for b in bancos]))
    lineas = list(sesion.scalars(consulta))
    alias = [(a.nombre, a.palabra) for a in sesion.scalars(select(PalabraConciliacion).where(PalabraConciliacion.empresa_id == empresa_id))]
    resultado = conciliar(
        [FacturaPorConciliar(str(f.id), f.nombre, f.nif, f.fecha_factura, f.total) for f in pendientes],
        [LineaPorConciliar(str(l.id), l.fecha, f"{l.texto} {l.mas_datos}".strip(), l.importe, l.fecha_valor) for l in lineas],
        sentido, alias,
    )
    resultado.libres = [l for l in resultado.libres if periodo[0] <= l.fecha <= periodo[1]]  # las líneas de otros trimestres no se enseñan como «sin factura»
    return Propuestas(resultado, {str(f.id): f for f in pendientes}, {str(l.id): l for l in lineas}, desde, hasta, duplicadas, pagadas, sentido, periodo)


# ---------------------------------------------------------------------------- aplicar: crear la factura y el pago con la línea del extracto


@dataclass
class Proveedor:
    """El proveedor de Conta que le toca a una factura de la lista de trabajo y por qué."""

    tercero: Tercero | None
    origen: str  # «elegido», «correspondencia», «NIF o nombre» o «nuevo»
    cuenta_gasto_id: int | None = None  # sólo si se quiere otra que la del proveedor


def resolver_proveedor(sesion: Session, f: FacturaTrimestre) -> Proveedor:
    """Por este orden: lo elegido para esa factura, la correspondencia guardada para el NIF de Verifactu, el proveedor de Conta con ese NIF o nombre, y si no hay nada, un proveedor nuevo."""
    if f.tercero_id is not None and (t := sesion.get(Tercero, f.tercero_id)) is not None:
        return Proveedor(t, "elegido", f.cuenta_gasto_id)
    propio = normalizar_nif(getattr(sesion.get(Empresa, f.empresa_id), "nif", ""))
    nif = normalizar_nif(f.nif)
    nif = "" if nif == propio else nif  # el NIF de la propia empresa es el del destinatario, no el del proveedor: no sirve para buscarlo
    if nif:
        c = sesion.scalars(select(CorrespondenciaTercero).where(CorrespondenciaTercero.empresa_id == f.empresa_id, CorrespondenciaTercero.nif == nif)).first()
        if c is not None:
            return Proveedor(c.tercero, "correspondencia", f.cuenta_gasto_id or c.cuenta_gasto_id)
    t, _ = _tercero_por_nif_o_nombre(sesion, f.empresa_id, "P" if f.sentido == "R" else "C", "" if not nif else f.nif, f.nombre)
    if t is not None:
        return Proveedor(t, "NIF o nombre", f.cuenta_gasto_id)
    return Proveedor(None, "nuevo", f.cuenta_gasto_id)


def fijar_proveedor(sesion: Session, f: FacturaTrimestre, *, tercero: Tercero | None = None, cuenta_gasto: Cuenta | None = None, crear: bool = False, recordar: bool = False) -> int:
    """Guarda lo elegido para la factura y, con `recordar`, para todas las pendientes con el mismo NIF y para las siguientes cargas. Devuelve a cuántas facturas afecta."""
    if cuenta_gasto is not None and f.sentido == "E" and cuenta_gasto.codigo[:1] != "7":
        raise ErrorContable(f"La subcuenta {cuenta_gasto.codigo} ({cuenta_gasto.nombre}) no es de ingresos: una factura emitida va a una cuenta del grupo 7")
    if cuenta_gasto is not None and f.sentido == "R" and cuenta_gasto.codigo[:1] not in GRUPOS_DE_GASTO:
        raise ErrorContable(f"La subcuenta {cuenta_gasto.codigo} ({cuenta_gasto.nombre}) no es de gasto: una factura recibida va a una cuenta del grupo 6 (o 2 si es una inversión, 3 si son existencias). Si quiere cambiar de proveedor, hágalo en el campo «Proveedor de Conta»")
    if tercero is None and not crear:
        raise ErrorContable("Elija el proveedor de Conta o marque «crear el proveedor nuevo»")
    if tercero is not None and crear:
        raise ErrorContable("O se elige un proveedor de Conta o se crea uno nuevo, no las dos cosas")
    f.tercero_id, f.cuenta_gasto_id, f.crear_proveedor = (tercero.id if tercero else None), (cuenta_gasto.id if cuenta_gasto else None), crear
    afectadas = 1
    nif = normalizar_nif(f.nif)
    if recordar and nif and tercero is not None:
        c = sesion.scalars(select(CorrespondenciaTercero).where(CorrespondenciaTercero.empresa_id == f.empresa_id, CorrespondenciaTercero.nif == nif)).first()
        # sólo se recuerda el proveedor, no la subcuenta de gasto: un mismo NIF puede llevar gastos distintos según la factura (un parking y un restaurante de la misma cadena)
        if c is None:
            sesion.add(CorrespondenciaTercero(empresa_id=f.empresa_id, nif=nif, tercero_id=tercero.id))
        else:
            c.tercero_id, c.cuenta_gasto_id = tercero.id, None
        for otra in facturas_pendientes(sesion, f.empresa_id, f.sentido):  # las que no tienen una decisión propia pasan a usar la correspondencia
            if otra.id != f.id and normalizar_nif(otra.nif) == nif and otra.tercero_id is None and not otra.crear_proveedor:
                afectadas += 1
    return afectadas


@dataclass
class Aplicacion:
    """Una factura de la lista de trabajo y cómo se pagó: con una línea del extracto, o (sin línea) con el banco o cuenta de socio y el día elegidos para ella."""

    factura: FacturaTrimestre
    linea: ExtractoLinea | None = None
    banco: Banco | None = None  # sólo sin línea
    fecha: date | None = None  # sólo sin línea


@dataclass
class ResultadoAplicar:
    facturas: list[tuple[int, int]] = field(default_factory=list)  # (id en la lista de trabajo, nº de factura en la contabilidad)
    movimientos: int = 0
    terceros_nuevos: list[str] = field(default_factory=list)
    pdfs: int = 0
    avisos: list[str] = field(default_factory=list)


def fila_de(sesion: Session, f: FacturaTrimestre, linea: ExtractoLinea | None = None, banco: Banco | None = None, *, fecha: date | None = None) -> FilaExcel:
    """La misma fila que traería el Excel de Verifactu, para reutilizar la importación de facturas. Con `banco`, la factura sale pagada por ese banco el día de la línea del extracto, o el `fecha` dado."""
    lineas = []
    if f.base is not None:
        lineas.append((f.base, f.porcentaje_iva or CERO, f.cuota_iva or CERO))
    for trozo in filter(None, f.iva_extra.split(";")):
        pct, cuota = (Decimal(x) for x in trozo.split())
        if pct:
            lineas.append(((cuota * 100 / pct).quantize(CERO), pct, cuota))
    proveedor = resolver_proveedor(sesion, f)
    propio = normalizar_nif(getattr(sesion.get(Empresa, f.empresa_id), "nif", ""))
    fila = FilaExcel(fila=f.id, nombre=f.nombre, nif="" if normalizar_nif(f.nif) == propio else f.nif, fecha_factura=f.fecha_factura, fecha_contable=f.fecha_contable, numero=f.numero_factura, lineas=lineas, total=f.total, ruta=f.ruta_pdf,
                     tercero_id=proveedor.tercero.id if proveedor.tercero else None, cuenta_gasto_id=proveedor.cuenta_gasto_id)
    if banco is not None and banco.cuenta is not None and (linea is not None or fecha is not None):
        fila.fecha_pago, fila.subcuenta, fila.concepto = ((linea.fecha_valor or linea.fecha) if linea is not None else fecha), banco.cuenta.codigo, (linea.texto if linea is not None else "")
    return fila


def _fila_de_aplicacion(sesion: Session, a: Aplicacion, bancos: dict[int, Banco]) -> FilaExcel:
    if a.linea is not None:
        return fila_de(sesion, a.factura, a.linea, bancos.get(a.linea.banco_id))
    return fila_de(sesion, a.factura, None, a.banco, fecha=a.fecha)


def _comprobar(a: Aplicacion) -> None:
    if a.factura.factura_id is not None or a.factura.descartada:
        raise ErrorContable(f"La factura {a.factura.numero_factura} de {a.factura.nombre} ya no está pendiente")
    if a.linea is None and a.banco is None and a.fecha is None:
        return  # sin pago: se contabiliza con su vencimiento pendiente
    if a.linea is None:
        if a.banco is None or a.banco.cuenta is None or a.fecha is None:
            raise ErrorContable(f"{a.factura.nombre} {a.factura.numero_factura}: falta el banco o la cuenta de socio que la pagó, o el día del pago")
        return
    if a.linea.movimiento_id is not None:
        raise ErrorContable(f"El movimiento del {a.linea.fecha:%d/%m/%Y} ({a.linea.texto}) ya pagó otra factura")
    esperado = a.factura.total if a.factura.sentido == "E" else -a.factura.total
    if a.linea.importe != esperado:
        raise ErrorContable(f"{a.factura.nombre} {a.factura.numero_factura}: la factura es de {a.factura.total} € y el movimiento del banco de {abs(a.linea.importe)} €")


def aplicar(sesion: Session, almacen, ejercicio: Ejercicio, aplicaciones: list[Aplicacion], *, cuentas_de_gasto: dict[str, str] | None = None) -> ResultadoAplicar:
    """Crea la factura recibida, su vencimiento y el movimiento de banco con la fecha y el importe del extracto, todo o nada (no hace commit: si falla, quien llama hace rollback).

    De momento sólo una factura pagada por un movimiento del mismo importe; el resto de casos (varias facturas en un cargo, dos pagos, importes distintos) se resuelven a mano.
    """
    if not aplicaciones:
        raise ErrorContable("No hay nada que aplicar")
    usadas: set[int] = set()
    for a in aplicaciones:
        _comprobar(a)
        if a.linea is not None and a.linea.id in usadas:
            raise ErrorContable(f"El movimiento del {a.linea.fecha:%d/%m/%Y} ({a.linea.texto}) se ha elegido para dos facturas")
        if a.linea is not None:
            usadas.add(a.linea.id)
    bancos = {b.id: b for b in sesion.scalars(select(Banco).where(Banco.empresa_id == ejercicio.empresa_id))}
    sentido = aplicaciones[0].factura.sentido
    filas = [_fila_de_aplicacion(sesion, a, bancos) for a in aplicaciones]
    planes = planificar(sesion, ejercicio, sentido, filas)
    malas = [f"{p.fila.nombre} {p.fila.numero}: " + ("; ".join(p.errores) if p.errores else p.detalle) for p in planes if not p.importable]
    if malas:
        raise ErrorContable("No se puede aplicar:\n" + "\n".join(malas))
    importada = importar(sesion, almacen, ejercicio, sentido, planes, cuentas_de_gasto=cuentas_de_gasto, origen="conciliación del trimestre")
    resultado = ResultadoAplicar(movimientos=importada.movimientos, terceros_nuevos=importada.terceros_nuevos, pdfs=importada.pdfs, avisos=importada.avisos)
    numero_de = {fila: numero for fila, numero in importada.importadas}
    for a in aplicaciones:
        factura = sesion.scalars(select(Factura).where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == sentido, Factura.numero == numero_de[a.factura.id])).one()
        a.factura.factura_id = factura.id
        movimiento_id = sesion.scalar(select(Pago.movimiento_id).join(Vencimiento, Vencimiento.id == Pago.vencimiento_id).where(Vencimiento.factura_id == factura.id))
        if a.linea is not None:
            a.linea.movimiento_id = movimiento_id
        resultado.facturas.append((a.factura.id, factura.numero))
    sesion.flush()
    return resultado


def _es_aviso_de_importe(texto: str) -> bool:
    """Los avisos de la importación que cambian lo contabilizado respecto al Excel: un importe sin IVA o un ajuste de redondeo."""
    return "sin IVA" in texto or "redondeo" in texto


REGLAS_SEGURAS = ("importe_y_texto", "importe_unico", "importe_y_fecha")  # una factura, una línea, mismo importe; lo demás se confirma a mano


@dataclass
class Preparadas:
    """Lo que se puede aplicar de golpe y lo que se deja fuera, con el motivo."""

    aplicables: list[Aplicacion] = field(default_factory=list)
    omitidas: list[tuple[FacturaTrimestre, str]] = field(default_factory=list)
    avisos: list[tuple[FacturaTrimestre, str]] = field(default_factory=list)  # lo que el programa ajusta por su cuenta y conviene revisar (p. ej. importes sin IVA)
    sin_aplicar: int = 0  # (sólo en «contabilizar el resto») facturas con propuesta segura o marcadas como pagadas por un socio que todavía no se han aplicado

    @property
    def con_extracto(self) -> list[Aplicacion]:
        return [a for a in self.aplicables if a.linea is not None]

    @property
    def sin_extracto(self) -> list[Aplicacion]:
        return [a for a in self.aplicables if a.linea is None]


def preparar(sesion: Session, ejercicio: Ejercicio, propuestas: Propuestas) -> Preparadas:
    """Las propuestas seguras (una factura pagada por una línea del mismo importe) que además se pueden contabilizar: las que ya están en la contabilidad o dan error se dejan fuera."""
    candidatas = [Aplicacion(propuestas.facturas[e.facturas[0].id], propuestas.lineas[e.lineas[0].id])
                  for e in propuestas.resultado.emparejadas if e.regla in REGLAS_SEGURAS and len(e.facturas) == 1 and len(e.lineas) == 1]
    bancos = {b.id: b for b in sesion.scalars(select(Banco).where(Banco.empresa_id == ejercicio.empresa_id))}
    resultado = Preparadas()
    for f in propuestas.pagadas_por_banco:  # las que el usuario ha dicho que pagó un socio u otro banco, sin línea de extracto
        candidatas.append(Aplicacion(f, None, bancos.get(f.pagada_por_id), f.pagada_fecha or f.fecha_factura))
    buenas = []
    for a in candidatas:
        try:
            _comprobar(a)
        except ErrorContable as e:
            resultado.omitidas.append((a.factura, str(e)))
            continue
        if resolver_proveedor(sesion, a.factura).tercero is None and not a.factura.crear_proveedor:
            resultado.omitidas.append((a.factura, f"{'Proveedor' if a.factura.sentido == 'R' else 'Cliente'} nuevo: elija el {'proveedor' if a.factura.sentido == 'R' else 'cliente'} de Conta de «{a.factura.nombre}» o decida crearlo"))
            continue
        buenas.append(a)
    planes = planificar(sesion, ejercicio, propuestas.sentido, [_fila_de_aplicacion(sesion, a, bancos) for a in buenas])
    for a, plan in zip(buenas, planes):
        if plan.importable:
            resultado.aplicables.append(a)
            resultado.avisos += [(a.factura, t) for t in plan.avisos if _es_aviso_de_importe(t)]
        else:
            resultado.omitidas.append((a.factura, "; ".join(plan.errores) if plan.errores else plan.detalle))
    return resultado


def marcar_pagadas_por(sesion: Session, empresa_id: int, ids: list[int], banco: Banco | None, fecha: date | None = None) -> int:
    """Dice que un socio (o un banco sin extracto) pagó estas facturas: `fecha` es el día del pago, o el de cada factura si no se da. Con `banco=None` se quita. Devuelve cuántas cambian."""
    if banco is not None and (banco.empresa_id != empresa_id or banco.cuenta_id is None):
        raise ErrorContable("Elija un banco o una cuenta de socio de esta empresa que tenga subcuenta")
    n = 0
    for f in sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == empresa_id, FacturaTrimestre.id.in_(ids), FacturaTrimestre.factura_id.is_(None), FacturaTrimestre.descartada.is_(False))):
        f.pagada_por_id = banco.id if banco else None
        f.pagada_fecha = (fecha or f.fecha_factura) if banco else None
        n += 1
    return n


def preparar_pendientes(sesion: Session, ejercicio: Ejercicio, propuestas: Propuestas) -> Preparadas:
    """Lo que queda en la lista de trabajo tras las propuestas seguras y las del socio: se contabiliza sin pago, con su vencimiento pendiente. Se dejan fuera las duplicadas de Verifactu, las que
    tienen un proveedor nuevo sin decidir y las que no se pueden contabilizar (ya existen, IVA mal…), cada una con su motivo."""
    ya = {a.factura.id for a in preparar(sesion, ejercicio, propuestas).aplicables}
    resto = [f for f in propuestas.facturas.values() if f.id not in ya]
    resultado = Preparadas(sin_aplicar=len(ya))
    buenas = []
    for f in resto:
        if resolver_proveedor(sesion, f).tercero is None and not f.crear_proveedor:
            resultado.omitidas.append((f, f"{'Proveedor' if f.sentido == 'R' else 'Cliente'} nuevo: elija el {'proveedor' if f.sentido == 'R' else 'cliente'} de Conta de «{f.nombre}» o decida crearlo"))
        else:
            buenas.append(Aplicacion(f))
    planes = planificar(sesion, ejercicio, propuestas.sentido, [fila_de(sesion, a.factura) for a in buenas])
    for a, plan in zip(buenas, planes):
        if plan.importable:
            resultado.aplicables.append(a)
            resultado.avisos += [(a.factura, t) for t in plan.avisos if _es_aviso_de_importe(t)]
        else:
            resultado.omitidas.append((a.factura, "; ".join(plan.errores) if plan.errores else plan.detalle))
    return resultado
