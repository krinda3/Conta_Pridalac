"""Extractos del banco y de la tarjeta: lectura de lo que descarga cada banco, guardado línea a línea sin duplicados y cuadre con el Mayor.

Un extracto es un Excel con una tabla de movimientos. Cada banco pone las columnas a su manera, y a veces el fichero se recorta a mano; por eso se leen **por el nombre de la columna** y no por su posición:
la cabecera se busca en las primeras filas y lo que va antes (titular, cuenta, periodo) se ignora. Se entienden los cuatro formatos que se usan: BBVA, CaixaBank, Santander y la tarjeta (el extracto de
la tarjeta trae los gastos en positivo y sin saldo).

El importe de cada línea se guarda con el signo del Mayor de esa cuenta: positivo = entra dinero (debe), negativo = sale (haber). La columna de saldo, cuando existe, se usa de control: cada saldo debe ser
el anterior más el importe, y si no lo es falta una línea.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from itertools import groupby
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Apunte, Asiento, Banco, Ejercicio, Extracto, ExtractoLinea
from conta_pridalac.domain.errores import ErrorContable

CERO = Decimal("0.00")
SUBTIPOS_DE_CIERRE = ("A", "R", "Z")  # apertura, regularización y cierre no son movimientos del banco
FILAS_PARA_LA_CABECERA = 60
TOLERANCIA_DIAS = 5  # la fecha de un movimiento en el Mayor puede no ser la del extracto (operación, valor, contable)

# nombre de columna (en minúsculas, sin tildes ni signos) → campo
CAMPOS = {
    "fecha": {"fecha", "fcontable", "fechaoperacion", "fechadeoperacion"},
    "fecha_valor": {"fvalor", "fechavalor"},
    "concepto": {"movimiento", "concepto", "establecimiento"},
    "beneficiario": {"beneficiarioordenante"},
    "mas_datos": {"masdatos", "observaciones", "informacionadicional"},
    "importe": {"importe"},
    "saldo": {"saldo"},
    "tarjeta": {"tarjeta"},  # en el extracto de la tarjeta es el nº de tarjeta; en algún fichero recortado, la fecha valor
}


def _clave_de_texto(valor) -> str:
    t = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def _fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto[:10] if formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y") else texto, formato).date()
        except ValueError:
            continue
    return None


def _importe(valor) -> Decimal | None:
    """Un importe como lo entrega el banco: número, o texto con coma o punto decimal, miles y «EUR»."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return Decimal(repr(valor)).quantize(Decimal("0.01"))
    texto = str(valor).replace(" ", " ").upper().replace("EUR", "").replace("€", "").replace(" ", "").strip()
    if not texto or texto in ("-", "+"):
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".") if texto.rfind(",") > texto.rfind(".") else texto.replace(",", "")
    else:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


@dataclass
class LineaLeida:
    fecha: date
    importe: Decimal
    texto: str = ""
    mas_datos: str = ""
    fecha_valor: date | None = None
    saldo: Decimal | None = None
    fila: int = 0  # fila del Excel (la primera es la 1)


@dataclass
class Salto:
    """Un punto donde el saldo no encaja con el importe: falta alguna línea, o sobra o está mal."""

    antes: LineaLeida
    despues: LineaLeida
    esperado: Decimal
    diferencia: Decimal


@dataclass
class ExtractoLeido:
    formato: str
    lineas: list[LineaLeida]  # en orden cronológico
    saltos: list[Salto] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    invertido: bool = False  # los importes venían con el signo contrario (tarjeta) y se han dado la vuelta

    @property
    def desde(self) -> date | None:
        return self.lineas[0].fecha if self.lineas else None

    @property
    def hasta(self) -> date | None:
        return self.lineas[-1].fecha if self.lineas else None

    @property
    def saldo_inicial(self) -> Decimal | None:
        primera = next((l for l in self.lineas if l.saldo is not None), None)
        return primera.saldo - primera.importe if primera is not None else None

    @property
    def saldo_final(self) -> Decimal | None:
        ultima = next((l for l in reversed(self.lineas) if l.saldo is not None), None)
        return ultima.saldo if ultima is not None else None


def _formato(claves: set[str]) -> str:
    """El banco de origen, por las columnas que le son propias."""
    if "fcontable" in claves:
        return "bbva"
    if "movimiento" in claves:
        return "caixabank"
    if "fechaoperacion" in claves or "fechadeoperacion" in claves:
        return "santander"
    if "establecimiento" in claves:
        return "tarjeta"
    return "generico"


def _cabecera(filas: list[tuple]) -> tuple[int, dict[str, int], set[str]] | None:
    for i, fila in enumerate(filas[:FILAS_PARA_LA_CABECERA]):
        columnas: dict[str, int] = {}
        claves: set[str] = set()
        for j, celda in enumerate(fila):
            if not isinstance(celda, str):
                continue
            clave = _clave_de_texto(celda)
            claves.add(clave)
            for campo, nombres in CAMPOS.items():
                if clave in nombres and campo not in columnas:
                    columnas[campo] = j
        if "importe" in columnas and "fecha" in columnas and ("concepto" in columnas or "beneficiario" in columnas or "mas_datos" in columnas):
            return i, columnas, claves
    return None


def _leer_hoja(filas: list[tuple], nombre: str) -> tuple[str, list[LineaLeida], list[str]] | None:
    encontrada = _cabecera(filas)
    if encontrada is None:
        return None
    cabecera, c, claves = encontrada
    avisos: list[str] = []
    formato = _formato(claves)

    def celda(fila, campo):
        j = c.get(campo)
        return fila[j] if j is not None and j < len(fila) else None

    lineas: list[LineaLeida] = []
    for i, fila in enumerate(filas[cabecera + 1:], start=cabecera + 2):
        if fila is None or all(v is None or str(v).strip() == "" for v in fila):
            continue
        fecha, importe = _fecha(celda(fila, "fecha")), _importe(celda(fila, "importe"))
        if fecha is None or importe is None:
            if importe is not None or fecha is not None:
                avisos.append(f"Hoja «{nombre}», fila {i}: no se puede leer la fecha o el importe y se salta")
            continue
        concepto = str(celda(fila, "concepto") or "").strip()
        beneficiario = str(celda(fila, "beneficiario") or "").strip()
        texto = " · ".join(p for p in (concepto, beneficiario) if p)
        valor = _fecha(celda(fila, "fecha_valor")) or _fecha(celda(fila, "tarjeta"))
        lineas.append(LineaLeida(fecha=fecha, importe=importe, texto=texto, mas_datos=str(celda(fila, "mas_datos") or "").strip(), fecha_valor=valor,
                                 saldo=_importe(celda(fila, "saldo")), fila=i))
    if len(lineas) > 1 and lineas[0].fecha > lineas[-1].fecha:  # los bancos dan lo más reciente primero
        lineas.reverse()
    return formato, _ordenar_por_saldo(lineas), avisos


def _cadena_del_dia(dia: list[LineaLeida], saldo_previo: Decimal | None) -> list[LineaLeida]:
    """Las líneas de un día en el orden en que encadena el saldo, o tal como vienen si no se puede (porque falta alguna)."""
    if saldo_previo is not None:
        inicios = [l for l in dia if l.saldo == saldo_previo + l.importe]
    else:
        saldos = {l.saldo for l in dia}
        inicios = [l for l in dia if l.saldo - l.importe not in saldos]
    for inicio in inicios or dia:
        pendientes = list(dia)
        pendientes.remove(inicio)
        cadena = [inicio]
        while pendientes:
            siguiente = next((l for l in pendientes if l.saldo == cadena[-1].saldo + l.importe), None)
            if siguiente is None:
                break
            cadena.append(siguiente)
            pendientes.remove(siguiente)
        if not pendientes:
            return cadena
    return dia


def _ordenar_por_saldo(lineas: list[LineaLeida]) -> list[LineaLeida]:
    """Dentro de cada día, el orden de las líneas es el del saldo: cada banco ordena los movimientos de un mismo día a su manera (BBVA los da en orden cronológico dentro de un día
    que ya viene al revés), y de ese orden depende comprobar que no falta ninguna línea."""
    resultado: list[LineaLeida] = []
    saldo_previo = None
    for _, grupo in groupby(lineas, key=lambda l: l.fecha):
        dia = list(grupo)
        if len(dia) > 1 and all(l.saldo is not None for l in dia):
            dia = _cadena_del_dia(dia, saldo_previo)
        resultado += dia
        saldo_previo = dia[-1].saldo
    return resultado


def comprobar_saldos(lineas: list[LineaLeida]) -> list[Salto]:
    """Los puntos donde el saldo no es el anterior más el importe (líneas cronológicas)."""
    saltos = []
    anterior = None
    for l in lineas:
        if l.saldo is None:
            continue
        if anterior is not None:
            esperado = anterior.saldo + l.importe
            if esperado != l.saldo:
                saltos.append(Salto(anterior, l, esperado, l.saldo - esperado))
        anterior = l
    return saltos


def leer_extracto(contenido: bytes, invertir: bool | None = None) -> ExtractoLeido:
    """Lee un Excel de extracto. `invertir`: dar la vuelta al signo de los importes; sin indicarlo, se decide solo en el extracto de la tarjeta (gastos en positivo)."""
    try:
        libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    except Exception as ex:  # noqa: BLE001  (un fichero que no es un .xlsx)
        raise ErrorContable(f"No se puede abrir el Excel: {ex}") from None
    hojas = []
    for hoja in libro.worksheets:
        leida = _leer_hoja(list(hoja.iter_rows(values_only=True)), hoja.title)
        if leida is not None:
            hojas.append((hoja.title, leida))
    if not hojas:
        raise ErrorContable("No reconozco el formato del extracto: busco una tabla con las columnas de fecha, concepto o descripción e importe")
    _, (formato, lineas, avisos) = hojas[0]  # sólo la primera hoja con movimientos: las demás suelen ser apuntes sueltos
    avisos = list(avisos)
    if len(hojas) > 1:
        avisos.append("El fichero tiene otras hojas con movimientos (" + ", ".join(f"«{n}»" for n, _ in hojas[1:]) + "): se ignoran; si también hay que importarlas, guárdelas en otro fichero")
    saltos = comprobar_saldos(lineas)
    if not lineas:
        raise ErrorContable("El extracto no tiene ningún movimiento")
    if invertir is None:
        positivos, negativos = sum(1 for l in lineas if l.importe > 0), sum(1 for l in lineas if l.importe < 0)
        invertir = formato == "tarjeta" and positivos > negativos
    if invertir:
        for l in lineas:
            l.importe = -l.importe
    return ExtractoLeido(formato=formato, lineas=lineas, saltos=saltos, avisos=avisos, invertido=bool(invertir))


# ------------------------------------------------------------------------------------------------ guardar


@dataclass
class ResultadoExtracto:
    formato: str
    lineas: int
    nuevas: int
    repetidas: int
    desde: date | None
    hasta: date | None
    saltos: list[Salto]
    avisos: list[str]
    invertido: bool
    saldo_inicial: Decimal | None
    saldo_final: Decimal | None
    extracto_id: int | None = None


def _claves(banco_id: int, lineas: list[LineaLeida]) -> list[str]:
    """Una clave por línea que no depende del formato del fichero (así un extracto recortado y el original no se duplican): con saldo, fecha + importe + saldo; sin él, fecha + importe + texto.
    Las líneas idénticas del mismo día se numeran."""
    vistas: dict[str, int] = {}
    claves = []
    for l in lineas:
        base = f"{banco_id}|{l.fecha}|{l.importe}|" + (str(l.saldo) if l.saldo is not None else _clave_de_texto(l.texto))
        n = vistas[base] = vistas.get(base, 0) + 1
        claves.append(hashlib.sha1(f"{base}|{n}".encode()).hexdigest())
    return claves


def importar_extracto(sesion: Session, empresa_id: int, banco: Banco, nombre_fichero: str, contenido: bytes, invertir: bool | None = None) -> ResultadoExtracto:
    """Guarda las líneas del extracto que todavía no estén (no hace `commit`). Importar dos veces el mismo fichero, o dos que se solapan, no repite nada."""
    leido = leer_extracto(contenido, invertir)
    avisos = list(leido.avisos)
    huella = hashlib.sha256(contenido).hexdigest()
    if sesion.scalar(select(Extracto.id).where(Extracto.banco_id == banco.id, Extracto.huella == huella)) is not None:
        avisos.append("Este fichero ya se había importado: no se añade nada")
    claves = _claves(banco.id, leido.lineas)
    existentes: set[str] = set()
    for i in range(0, len(claves), 500):
        existentes.update(sesion.scalars(select(ExtractoLinea.clave).where(ExtractoLinea.banco_id == banco.id, ExtractoLinea.clave.in_(claves[i:i + 500]))))
    nuevas = [(l, k) for l, k in zip(leido.lineas, claves) if k not in existentes]
    resultado = ResultadoExtracto(
        formato=leido.formato, lineas=len(leido.lineas), nuevas=len(nuevas), repetidas=len(leido.lineas) - len(nuevas), desde=leido.desde, hasta=leido.hasta, saltos=leido.saltos, avisos=avisos,
        invertido=leido.invertido, saldo_inicial=leido.saldo_inicial, saldo_final=leido.saldo_final,
    )
    if not nuevas:
        return resultado
    extracto = Extracto(empresa_id=empresa_id, banco_id=banco.id, fichero=nombre_fichero[:255], huella=huella, formato=leido.formato, desde=leido.desde, hasta=leido.hasta,
                        lineas=len(leido.lineas), nuevas=len(nuevas))
    sesion.add(extracto)
    sesion.flush()
    for orden, (l, k) in enumerate(nuevas):
        sesion.add(ExtractoLinea(extracto_id=extracto.id, empresa_id=empresa_id, banco_id=banco.id, orden=orden, fecha=l.fecha, fecha_valor=l.fecha_valor, texto=l.texto[:255],
                                 mas_datos=l.mas_datos[:255], importe=l.importe, saldo=l.saldo, clave=k))
    sesion.flush()
    resultado.extracto_id = extracto.id
    return resultado


# ------------------------------------------------------------------------------------------------ cuadre con el Mayor


@dataclass
class ApunteDelMayor:
    fecha: date
    importe: Decimal  # debe − haber
    asiento: str
    concepto: str


@dataclass
class Cuadre:
    banco: Banco
    desde: date
    hasta: date
    emparejadas: int
    solo_extracto: list[ExtractoLinea]
    solo_mayor: list[ApunteDelMayor]
    saldo_extracto: Decimal | None  # el del extracto al final del periodo (None si el extracto no trae saldo)
    saldo_mayor: Decimal  # el del Mayor al final del periodo, con la apertura
    lineas_en_el_periodo: int
    fecha_distinta: list[tuple[ExtractoLinea, ApunteDelMayor]] = field(default_factory=list)  # emparejadas por la cantidad, con más días de diferencia que la tolerancia
    lineas_a_cero: int = 0  # líneas del banco sin importe (avisos, precios de servicio): no tienen efecto contable y no cuentan como diferencia
    cargos_extracto: Decimal = CERO  # suma de lo que sale (importes negativos) en el periodo, a cada lado
    cargos_mayor: Decimal = CERO
    abonos_extracto: Decimal = CERO  # y de lo que entra
    abonos_mayor: Decimal = CERO
    saldo_previo_extracto: Decimal | None = None  # el saldo del extracto justo antes de la primera línea del periodo
    saldo_previo_mayor: Decimal | None = None  # el del Mayor justo antes del periodo, con la apertura

    @property
    def diferencia_de_saldo(self) -> Decimal | None:
        return None if self.saldo_extracto is None else self.saldo_extracto - self.saldo_mayor

    @property
    def diferencia_previa(self) -> Decimal | None:
        """Lo que ya no cuadraba al empezar el periodo: viene de antes y no es de los movimientos que se comparan."""
        return None if self.saldo_previo_extracto is None or self.saldo_previo_mayor is None else self.saldo_previo_extracto - self.saldo_previo_mayor

    @property
    def cuadran_los_movimientos(self) -> bool:
        """Todos los movimientos del periodo están en los dos lados, con los mismos cargos y abonos, aunque el saldo no coincida por lo anterior."""
        return self.lineas_en_el_periodo > 0 and not self.solo_extracto and not self.solo_mayor

    @property
    def arrastra_una_diferencia(self) -> bool:
        """Los movimientos cuadran y toda la diferencia de saldo viene de antes del periodo."""
        return self.cuadran_los_movimientos and bool(self.diferencia_de_saldo) and self.diferencia_previa == self.diferencia_de_saldo

    @property
    def cuadra(self) -> bool:
        """El extracto es igual al Mayor: ninguna línea suelta y, si hay saldo, el mismo saldo final."""
        return self.lineas_en_el_periodo > 0 and not self.solo_extracto and not self.solo_mayor and not self.diferencia_de_saldo


def _emparejar(lineas: list[ExtractoLinea], apuntes: list[ApunteDelMayor], tolerancia: int):
    """Empareja cada línea con un apunte del mismo importe: primero la misma fecha, después la más cercana dentro de la tolerancia y, por último, lo que queda con la misma cantidad aunque la fecha
    sea otra (el Mayor puede llevar un pago a fin de trimestre, por ejemplo). Devuelve (emparejadas, líneas sin pareja, apuntes sin pareja, emparejadas con fecha distinta)."""
    por_importe: dict[Decimal, list[ApunteDelMayor]] = {}
    for a in apuntes:
        por_importe.setdefault(a.importe, []).append(a)
    emparejadas = 0
    pendientes: list[ExtractoLinea] = []
    for l in lineas:  # misma fecha exacta
        candidatos = por_importe.get(l.importe, [])
        i = next((i for i, a in enumerate(candidatos) if a.fecha == l.fecha), None)
        if i is None:
            pendientes.append(l)
        else:
            candidatos.pop(i)
            emparejadas += 1
    restantes: list[ExtractoLinea] = []
    for l in pendientes:  # la más cercana
        candidatos = por_importe.get(l.importe, [])
        cercanos = [(abs((a.fecha - l.fecha).days), i) for i, a in enumerate(candidatos) if abs((a.fecha - l.fecha).days) <= tolerancia]
        if cercanos:
            candidatos.pop(min(cercanos)[1])
            emparejadas += 1
        else:
            restantes.append(l)
    sin_pareja: list[ExtractoLinea] = []
    fecha_distinta: list[tuple[ExtractoLinea, ApunteDelMayor]] = []
    for l in restantes:  # la misma cantidad, a la fecha más cercana que quede
        candidatos = por_importe.get(l.importe, [])
        if candidatos:
            i = min(range(len(candidatos)), key=lambda k: abs((candidatos[k].fecha - l.fecha).days))
            fecha_distinta.append((l, candidatos.pop(i)))
        else:
            sin_pareja.append(l)
    sobrantes = sorted((a for lista in por_importe.values() for a in lista), key=lambda a: (a.fecha, a.asiento))
    return emparejadas + len(fecha_distinta), sin_pareja, sobrantes, fecha_distinta


def cuadrar_banco(sesion: Session, ejercicio: Ejercicio, banco: Banco, desde: date, hasta: date, tolerancia: int = TOLERANCIA_DIAS) -> Cuadre:
    """Compara los movimientos del extracto con los del Mayor de la cuenta del banco entre dos fechas, y sus saldos finales.

    El saldo del Mayor incluye la apertura del ejercicio; ni éste ni los movimientos cuentan la regularización ni el cierre (el cierre pone a cero la cuenta).
    """
    if banco.cuenta_id is None:
        raise ErrorContable(f"El banco «{banco.nombre}» no tiene cuenta contable")
    lineas = list(sesion.scalars(
        select(ExtractoLinea).where(ExtractoLinea.banco_id == banco.id, ExtractoLinea.fecha >= desde, ExtractoLinea.fecha <= hasta).order_by(ExtractoLinea.fecha, ExtractoLinea.id)
    ))
    filas = sesion.execute(
        select(Asiento.fecha, Apunte.debe, Apunte.haber, Asiento.tipo, Asiento.numero, Asiento.sub, Asiento.subtipo, Apunte.concepto, Asiento.concepto)
        .join(Apunte, Apunte.asiento_id == Asiento.id)
        .where(Asiento.ejercicio_id == ejercicio.id, Apunte.cuenta_id == banco.cuenta_id, Asiento.fecha <= hasta)
    ).all()
    saldo_mayor = sum((debe - haber for _, debe, haber, _t, _n, _s, subtipo, *_ in filas if subtipo not in ("R", "Z")), CERO)
    saldo_previo_mayor = sum((debe - haber for fecha, debe, haber, _t, _n, _s, subtipo, *_ in filas if fecha < desde and subtipo not in ("R", "Z")), CERO)
    apuntes = [
        ApunteDelMayor(fecha, debe - haber, f"{tipo}.{numero}" + (f"/{sub}" if sub else ""), concepto_apunte or concepto_asiento or "")
        for fecha, debe, haber, tipo, numero, sub, subtipo, concepto_apunte, concepto_asiento in filas
        if fecha >= desde and subtipo not in SUBTIPOS_DE_CIERRE
    ]
    con_importe = [l for l in lineas if l.importe != 0]
    emparejadas, solo_extracto, solo_mayor, fecha_distinta = _emparejar(con_importe, apuntes, tolerancia)
    con_saldo = [l for l in lineas if l.saldo is not None]
    saldo_extracto = None
    if con_saldo:  # la última línea del último día, que es la de mayor id al importarse en orden cronológico
        ultima_fecha = max(l.fecha for l in con_saldo)
        saldo_extracto = max((l for l in con_saldo if l.fecha == ultima_fecha), key=lambda l: l.id).saldo
    primera = next((l for l in lineas if l.saldo is not None), None)  # la primera línea (por fecha e id): su saldo menos su importe es el de antes
    saldo_previo_extracto = primera.saldo - primera.importe if primera is not None else None
    return Cuadre(banco=banco, desde=desde, hasta=hasta, emparejadas=emparejadas, solo_extracto=solo_extracto, solo_mayor=solo_mayor, saldo_extracto=saldo_extracto, saldo_mayor=saldo_mayor,
                  lineas_en_el_periodo=len(lineas), fecha_distinta=fecha_distinta, lineas_a_cero=len(lineas) - len(con_importe),
                  cargos_extracto=sum((l.importe for l in con_importe if l.importe < 0), CERO), cargos_mayor=sum((a.importe for a in apuntes if a.importe < 0), CERO),
                  abonos_extracto=sum((l.importe for l in con_importe if l.importe > 0), CERO), abonos_mayor=sum((a.importe for a in apuntes if a.importe > 0), CERO),
                  saldo_previo_extracto=saldo_previo_extracto, saldo_previo_mayor=saldo_previo_mayor)
