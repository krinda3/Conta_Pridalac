"""Generador del fichero del modelo 200 (Impuesto sobre Sociedades, ejercicio 2025) a partir de la contabilidad y de los datos de `impuesto_sociedades_datos`.

Se construye por páginas, cada una con su función, y se comprueba contra los `.200` presentados de Empresa A y Empresa B con `tools/comparar_200.py` (con `--como-programa-anterior --forzar-25` los dos salen
idénticos salvo lo que se explica en `docs/modelo200/`). Páginas: identificación (01000), tipo de estados (01B00), administradores, socios, titulares reales y representantes (02000, 02B00),
balance y cuenta de pérdidas y ganancias (03000–08000) y estado de cambios del patrimonio neto (09000–11000), ambos en `impuesto_sociedades_200_estados.py`, liquidación (12000, 13000, 14000, 14B00),
bases negativas (15000), límite de gastos financieros (20000), aplicación del resultado (20D00) y cuenta bancaria y devolución (DID00).

Lo que NO está probado con ningún fichero real (ninguno de los dos de 2025 lo necesita) y debe validarse en la sede antes de presentar: un resultado a ingresar (la página bancaria de domiciliación),
las correcciones manuales al resultado, las deducciones y bonificaciones, la reserva de nivelación, y las operaciones con socios en el estado de cambios del patrimonio neto.

Las casillas de cada campo se buscan por su número de casilla en el diseño de registro (`fichero200`), no por posición.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import DeclaracionPresentada, Ejercicio
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.ficheros_aeat import fichero200 as f200
from conta_pridalac.ficheros_aeat.fichero200 import Fichero200, Pagina
from conta_pridalac.servicios import cuentas_anuales, impuesto_sociedades_200_estados as estados, impuesto_sociedades_datos as isd
from conta_pridalac.servicios.impuesto_sociedades_datos import DatosIS, Precalculo

CERO = Decimal("0.00")
TIPO_ESTADOS_PYMES = 3  # «Balance, ECPN y pérdidas y ganancias: modelo PYMES»
GASTOS_FINANCIEROS_MINIMO = Decimal("1000000")  # límite total de deducibilidad de gastos financieros: 1 M€ como mínimo (art. 16.1 LIS)
CASILLAS_CORRECCION = {"impuesto": (301, 302), "multas": (1815, None)}  # (aumentos, disminuciones) en la página 12000


def _mayusculas(texto: str, largo: int | None = None) -> str:
    limpio = unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode().upper()
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio[:largo] if largo else limpio


def _digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def _n(p: Pagina, casilla: int) -> int:
    return p.n_de_casilla(casilla)


def _poner(p: Pagina, n: int, valor) -> None:
    """Un texto o un número en el campo `n`, según su tipo (`A`/`An` texto, `Num` entero con ceros a la izquierda)."""
    if f200._CAMPOS[p.codigo][n]["tipo"] in ("A", "An"):
        p.poner_texto(n, str(valor))
    else:
        p.poner_numero(n, int(valor or 0))


def _importe_n(p: Pagina, n: int, valor: Decimal) -> None:
    p.poner_importe(n, valor)


def _importe(p: Pagina, casilla: int, valor: Decimal) -> None:
    p.poner_importe(_n(p, casilla), valor)


def pagos_fraccionados(sesion: Session, ejercicio: Ejercicio) -> dict[int, Decimal]:
    """Lo ingresado en los pagos fraccionados del ejercicio (modelo 202, periodos 1 a 3), de las declaraciones presentadas."""
    filas = sesion.scalars(select(DeclaracionPresentada).where(
        DeclaracionPresentada.empresa_id == ejercicio.empresa_id, DeclaracionPresentada.modelo == "202", DeclaracionPresentada.anio == ejercicio.anio, DeclaracionPresentada.tipo == 1))
    return {f.periodo: f.resultado for f in filas if f.periodo in (1, 2, 3)}


# ------------------------------------------------------------------------------------------------ las páginas

def _tipo_de_declaracion(resultado: Decimal) -> str:
    """N sin cuota a ingresar ni a devolver, D solicitud de devolución, I ingreso."""
    return "N" if resultado == 0 else ("D" if resultado < 0 else "I")


def pagina_identificacion(ejercicio: Ejercicio, datos: DatosIS, p: Precalculo, resultado: Decimal) -> Pagina:
    empresa, pag = ejercicio.empresa, Pagina.nueva("01000")
    pag.poner_texto(6, _tipo_de_declaracion(resultado))
    pag.poner_texto(7, (empresa.nif or "").strip().upper())
    pag.poner_texto(8, _mayusculas(empresa.nombre, 80))
    pag.poner_numero(9, ejercicio.anio)
    for n, valor in zip((11, 12, 13), (ejercicio.fecha_inicio.year, ejercicio.fecha_inicio.month, ejercicio.fecha_inicio.day)):
        pag.poner_numero(n, valor)
    for n, valor in zip((14, 15, 16), (ejercicio.fecha_fin.year, ejercicio.fecha_fin.month, ejercicio.fecha_fin.day)):
        pag.poner_numero(n, valor)
    pag.poner_numero(17, 1)  # ejercicio de 12 meses natural
    pag.poner_numero(19, 1 if datos.agricola else 0)
    _poner(pag, 20, _digitos(empresa.telefono)[-9:])
    cnae = _digitos(empresa.cnae)
    if 3 <= len(cnae) <= 4:
        _poner(pag, 18, cnae.zfill(4))  # CNAE-2025 de la actividad principal (el de la ficha: confirmar que es el de la clasificación nueva)
    marcas = set(datos.marcas)
    if p.base_imponible <= 0:
        marcas.add(isd.CASILLA_BASE_NEGATIVA)  # «Base imponible negativa o cero»
    if p.tipo.marcar_00088:
        marcas.add(isd.CASILLA_TIPO_REDUCIDO_1M)
    for casilla in marcas:
        pag.poner_numero(_n(pag, casilla), 1)
    pag.poner_numero(102, 1)  # cifra de negocios de los doce meses anteriores: menos de 20 millones
    pag.poner_texto(107, _mayusculas(datos.contacto_nombre or " ".join(x for x in (empresa.presentador_nombre, empresa.presentador_apellido1, empresa.presentador_apellido2) if x), 50))
    _poner(pag, 108, _digitos(datos.contacto_telefono or empresa.telefono)[-9:])
    return pag


def pagina_tipo_de_estados() -> Pagina:
    pag = Pagina.nueva("01B00")
    for n in (14, 15, 16):
        pag.poner_numero(n, TIPO_ESTADOS_PYMES)
    return pag


def pagina_liquidacion_1(p: Precalculo) -> Pagina:
    pag = Pagina.nueva("12000")
    _importe(pag, 500, p.resultado)
    aumento_is = sum((c.aumento for c in p.correcciones if c.concepto.startswith("Impuesto sobre Sociedades")), CERO)
    disminucion_is = sum((c.disminucion for c in p.correcciones if c.concepto.startswith("Impuesto sobre Sociedades")), CERO)
    _importe(pag, 301, aumento_is)
    _importe(pag, 302, disminucion_is)
    _importe(pag, 501, p.resultado + aumento_is - disminucion_is)
    multas = sum((c.aumento for c in p.correcciones if c.concepto.startswith("Gasto no deducible")), CERO)
    if multas:
        _importe(pag, 1815, multas)
    return pag


def pagina_liquidacion_2(p: Precalculo) -> Pagina:
    """Los totales de las correcciones al resultado (aumentos y disminuciones del detalle de la página 12, sin las del propio impuesto, que van en sus casillas); la sede los recalcula y los compara."""
    pag = Pagina.nueva("13000")
    detalle = [c for c in p.correcciones if not c.concepto.startswith("Impuesto sobre Sociedades")]
    aumentos, disminuciones = sum((c.aumento for c in detalle), CERO), sum((c.disminucion for c in detalle), CERO)
    if aumentos:
        _importe(pag, 417, aumentos)
    if disminuciones:
        _importe(pag, 418, disminuciones)
    return pag


def pagina_actividades_agricolas(sesion: Session, ejercicio: Ejercicio, datos: DatosIS) -> Pagina | None:
    """Comunicación del importe neto de la cifra de negocios de las actividades agrícolas y/o ganaderas (la sede la pide si la entidad las realiza). Se toma toda la cifra de negocios y los otros ingresos de explotación."""
    if not datos.agricola:
        return None
    pag = Pagina.nueva("21000")
    _importe(pag, 1897, isd.cifra_de_negocios(sesion, ejercicio))
    otros = cuentas_anuales.pyg_pymes(sesion, ejercicio).importe("5")
    if otros:
        _importe(pag, 1901, otros)
    return pag


def pagina_liquidacion_3(p: Precalculo) -> Pagina:
    pag = Pagina.nueva("14000")
    _importe(pag, 550, p.base_previa)
    _importe(pag, 547, p.compensacion)
    _importe(pag, 552, p.base_imponible)
    _importe(pag, 1330, p.base_imponible)  # sin reserva de nivelación
    pag.poner_numero(_n(pag, 558), int(p.tipo.campo))
    _importe(pag, 562, p.cuota_integra)
    _importe(pag, 582, p.cuota_integra)
    return pag


def pagina_liquidacion_4(p: Precalculo, datos: DatosIS, pagos: dict[int, Decimal]) -> tuple[Pagina, Decimal]:
    pag = Pagina.nueva("14B00")
    cuota_liquida = p.cuota_integra  # sin bonificaciones ni deducciones
    _importe(pag, 592, cuota_liquida)
    retenciones = sum(datos.retenciones.values(), CERO)
    if retenciones:
        _importe(pag, 1766, retenciones)
    a_ingresar = cuota_liquida - retenciones
    _importe(pag, 599, a_ingresar)
    for casilla, periodo in ((601, 1), (603, 2), (605, 3)):
        _importe(pag, casilla, pagos.get(periodo, CERO))
    diferencial = a_ingresar - sum(pagos.values(), CERO)
    _importe(pag, 611, diferencial)
    resultado = diferencial + datos.incremento_perdida_beneficios_fiscales + datos.intereses_demora - datos.abono_deducciones_idi
    if datos.incremento_perdida_beneficios_fiscales:
        _importe(pag, 615, datos.incremento_perdida_beneficios_fiscales)
    if datos.intereses_demora:
        _importe(pag, 617, datos.intereses_demora)
    if datos.abono_deducciones_idi:
        _importe(pag, 1234, datos.abono_deducciones_idi)
    _importe(pag, 1586, resultado)
    _importe(pag, 621, resultado)
    return pag, resultado


_FILAS_BASES = {}  # año → {"principio": n, "aplicado": n, "futuros": n} en la página 15000
for _c in f200.DISENO["paginas"]["15000"]["campos"]:
    _m = re.search(r"bases imponibles negativas - (\d{4}) - (Pendiente aplicaci.n a principio|Aplicado en esta liquidaci.n|Pendiente aplicaci.n en per.odos futuros)", _c["desc"])
    if _m:
        _clave = {"Pe": "principio", "Ap": "aplicado"}.get(_m.group(2)[:2], "futuros")
        _clave = "futuros" if "futuros" in _m.group(2) else _clave
        _FILAS_BASES.setdefault(int(_m.group(1)), {})[_clave] = _c["n"]


def pagina_bases_negativas(sesion: Session, ejercicio: Ejercicio, p: Precalculo) -> Pagina | None:
    """El detalle de la compensación de bases negativas: una fila por año de origen. Va si hay bases pendientes o se genera una este año."""
    pendientes = {b.anio: b.pendiente for b in isd.bases_negativas(sesion, ejercicio.empresa_id) if b.anio < ejercicio.anio and b.pendiente > 0}
    if not pendientes and not p.base_negativa_generada:
        return None
    pag = Pagina.nueva("15000")
    aplicadas = dict(p.compensaciones)
    for anio, pendiente in pendientes.items():
        fila = _FILAS_BASES.get(anio)
        if fila is None:
            raise ErrorContable(f"El modelo 200 de {ejercicio.anio} no tiene fila para la base negativa de {anio}")
        pag.poner_importe(fila["principio"], pendiente)
        pag.poner_importe(fila["aplicado"], aplicadas.get(anio, CERO))
        pag.poner_importe(fila["futuros"], pendiente - aplicadas.get(anio, CERO))
    total = sum(pendientes.values(), CERO)
    _importe(pag, 670, total)
    _importe(pag, 547, p.compensacion)
    _importe(pag, 671, total - p.compensacion)
    if p.base_negativa_generada:
        fila = _FILAS_BASES[ejercicio.anio]
        pag.poner_importe(fila["principio"], p.base_negativa_generada)
        pag.poner_importe(fila["futuros"], p.base_negativa_generada)
    return pag


def pagina_gastos_financieros(sesion: Session, ejercicio: Ejercicio) -> Pagina:
    """Límite a la deducibilidad de gastos financieros (art. 16.1 y 16.2 LIS): el 30 % del beneficio operativo; como límite total, 1 M€ como mínimo."""
    pyg = cuentas_anuales.pyg_pymes(sesion, ejercicio)
    explotacion, amortizacion, subvenciones = pyg.importe("A"), pyg.importe("8"), pyg.importe("9")  # la amortización va en negativo, como en el PyG
    beneficio_operativo = explotacion - amortizacion - subvenciones
    pag = Pagina.nueva("20000")
    _importe(pag, 1250, explotacion)
    _importe(pag, 1251, amortizacion)
    if subvenciones:
        _importe(pag, 1252, subvenciones)
    _importe(pag, 1249, (beneficio_operativo * Decimal("0.30")).quantize(Decimal("0.01"), ROUND_HALF_UP))
    _importe(pag, 2369, GASTOS_FINANCIEROS_MINIMO)
    return pag


def pagina_aplicacion_resultado(p: Precalculo, aplicacion_a_reservas: Decimal | None = None) -> Pagina | None:
    """Base de reparto y aplicación del resultado: solo con beneficio. Por defecto todo a «otras reservas»."""
    if p.resultado <= 0:
        return None
    pag = Pagina.nueva("20D00")
    _importe(pag, 650, p.resultado)  # pérdidas y ganancias (sin remanente ni reservas a repartir)
    _importe(pag, 653, p.resultado)
    aplicado = aplicacion_a_reservas if aplicacion_a_reservas is not None else p.resultado
    _importe(pag, 654, aplicado)
    _importe(pag, 1522, aplicado)
    _importe(pag, 666, aplicado)
    return pag


def pagina_cuenta_bancaria(ejercicio: Ejercicio, p: Precalculo, resultado: Decimal) -> Pagina:
    empresa, pag = ejercicio.empresa, Pagina.nueva("DID00")
    _poner(pag, 6, 0)  # cuenta corriente tributaria: no
    _poner(pag, 7, ejercicio.anio)
    _poner(pag, 8, 1)
    _poner(pag, 9, "0A")
    for n, valor in zip((10, 11, 12), (ejercicio.fecha_inicio.day, ejercicio.fecha_inicio.month, ejercicio.fecha_inicio.year % 100)):
        pag.poner_numero(n, valor)
    for n, valor in zip((13, 14, 15), (ejercicio.fecha_fin.day, ejercicio.fecha_fin.month, ejercicio.fecha_fin.year % 100)):
        pag.poner_numero(n, valor)
    pag.poner_texto(16, (empresa.nif or "").strip().upper())
    pag.poner_texto(17, _mayusculas(empresa.nombre, 80))
    _importe(pag, 552, p.base_imponible)
    if p.cuota_integra:
        _importe(pag, 562, p.cuota_integra)
    if resultado:
        _importe(pag, 1586, resultado)
        _importe(pag, 621, resultado)
    if resultado < 0:
        pag.poner_texto(23, "D")
        pag.poner_importe(24, -resultado)
        pag.poner_numero(26, 1)
        pag.poner_texto(27, (empresa.iban or "").replace(" ", "").upper())
    elif resultado == 0:
        pag.poner_numero(41, 1)  # resultado cero
    return pag


# ------------------------------------------------------------------------------------------------ administradores, socios y titulares reales (páginas 02000 y 02B00)

FILAS_ADMINISTRADORES, FILAS_SOCIOS = 5, 6  # cuántos caben en una página 02000
UMBRAL_TITULAR_REAL = Decimal("25")  # más del 25 % del capital (como en el depósito de cuentas)


def _es_juridica(nif: str) -> bool:
    return bool(re.match(r"[ABCDEFGHJNPQRSUVW]\d", (nif or "").upper()))


def _fecha8(texto: str | None) -> int:
    """«14/04/1960» → 19600414 (el fichero lleva AAAAMMDD)."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto or "")
    return int(m.group(3) + m.group(2) + m.group(1)) if m else 0


def _pais(texto: str | None) -> str:
    """Código de país de dos letras; en blanco o «ESPAÑA» es ES."""
    limpio = _mayusculas(texto or "")
    return limpio if re.fullmatch(r"[A-Z]{2}", limpio) else "ES"


def paginas_sociedad(sesion: Session, ejercicio: Ejercicio) -> list[Pagina]:
    """02000: administradores y socios; 02B00: titulares reales (uno por página) y, en la primera, el secretario y los representantes legales."""
    from conta_pridalac.servicios import libros_oficiales as lo

    empresa = ejercicio.empresa
    socios, _ = lo.socios_del_libro(sesion, empresa, ejercicio.fecha_fin)
    capital = cuentas_anuales.balance_pymes(sesion, ejercicio).importe("PN.1.I.1")
    total_participaciones = sum(s.total_participaciones for s in socios)
    representantes = list(empresa.representantes)
    provincia = (empresa.provincia_ine or "").strip()
    paginas: list[Pagina] = []
    # 02000: la relación de administradores (el primer representante con poder) y los socios, de seis en seis
    grupos = [socios[i:i + FILAS_SOCIOS] for i in range(0, len(socios), FILAS_SOCIOS)] or [[]]
    for numero, grupo in enumerate(grupos):
        pag = Pagina.nueva("02000", complementaria=numero > 0)
        if numero == 0 and representantes:
            admin = representantes[0]
            _poner(pag, 6, (admin.nif or "").upper())
            _poner(pag, 7, "J" if _es_juridica(admin.nif) else "F")
            _poner(pag, 8, 0)
            _poner(pag, 9, _mayusculas(admin.nombre, 40))
        for i, socio in enumerate(grupo):
            base = 100 + 7 * i
            _poner(pag, base, (socio.nif or "").upper())
            _poner(pag, base + 1, 0)
            _poner(pag, base + 2, "J" if _es_juridica(socio.nif) else "F")
            _poner(pag, base + 3, _mayusculas(socio.nombre, 37))
            _poner(pag, base + 4, provincia)
            _importe_n(pag, base + 5, (capital * socio.total_participaciones / total_participaciones).quantize(Decimal("0.01"), ROUND_HALF_UP) if total_participaciones else CERO)
            _poner(pag, base + 6, int((socio.porcentaje * 100).to_integral_value()))
        paginas.append(pag)
    # 02B00: un titular real (más del 25 %) por página, por orden alfabético; el secretario y los representantes, en la primera
    titulares = sorted((s for s in socios if s.porcentaje > UMBRAL_TITULAR_REAL), key=lambda s: _mayusculas(s.nombre))
    for numero, titular in enumerate(titulares or [None]):
        pag = Pagina.nueva("02B00", complementaria=numero > 0)
        if titular is not None:
            _poner(pag, 145, 1)
            _poner(pag, 146, (titular.nif or "").upper())
            _poner(pag, 147, _mayusculas(titular.nombre, 40))
            _poner(pag, 149, _fecha8(titular.nacimiento))
            _poner(pag, 150, "ES")
            _poner(pag, 151, _pais(titular.nacionalidad))
        if numero == 0 and representantes:
            _poner(pag, 152, _mayusculas(representantes[0].nombre, 21))
            _poner(pag, 153, (representantes[0].nif or "").upper())
            for i, rep in enumerate(representantes[:3]):
                base = 154 + 4 * i
                _poner(pag, base, _mayusculas(rep.nombre, 36))
                _poner(pag, base + 1, (rep.nif or "").upper())
                _poner(pag, base + 2, int(rep.fecha_poder.strftime("%Y%m%d")) if rep.fecha_poder else 0)
                _poner(pag, base + 3, _mayusculas(rep.notaria or "", 12))
        paginas.append(pag)
    return paginas


# ------------------------------------------------------------------------------------------------ el fichero

def generar(sesion: Session, ejercicio: Ejercicio, datos: DatosIS | None = None, *, con_correcciones_automaticas: bool = True) -> Fichero200:
    """El fichero del modelo 200 del ejercicio. `con_correcciones_automaticas=False` reproduce lo que hacía el programa anterior (sin sumar multas ni el gasto por el impuesto): solo para comparar."""
    if ejercicio.anio != f200.EJERCICIO:
        raise ErrorContable(f"Hoy solo hay diseño del modelo 200 de {f200.EJERCICIO}, no de {ejercicio.anio}")
    datos = datos if datos is not None else isd.datos_del_ejercicio(sesion, ejercicio)
    p = isd.precalculo(sesion, ejercicio, datos)
    if not con_correcciones_automaticas:
        p = isd.precalculo(sesion, ejercicio, datos, con_automaticas=False)
    pagos = pagos_fraccionados(sesion, ejercicio)
    liquidacion_4, resultado = pagina_liquidacion_4(p, datos, pagos)
    paginas_estados, avisos = estados.paginas_de_estados(sesion, ejercicio)
    paginas_ecpn, avisos_ecpn = estados.paginas_ecpn(sesion, ejercicio)
    avisos += avisos_ecpn
    paginas = [pagina_identificacion(ejercicio, datos, p, resultado), pagina_tipo_de_estados(), *paginas_sociedad(sesion, ejercicio), pagina_liquidacion_1(p), pagina_liquidacion_3(p), liquidacion_4,
               pagina_bases_negativas(sesion, ejercicio, p), pagina_gastos_financieros(sesion, ejercicio), pagina_aplicacion_resultado(p), pagina_cuenta_bancaria(ejercicio, p, resultado), *paginas_estados, *paginas_ecpn, pagina_liquidacion_2(p), pagina_actividades_agricolas(sesion, ejercicio, datos)]
    fichero = Fichero200(ejercicio=ejercicio.anio, paginas=[x for x in paginas if x is not None], avisos=avisos)
    fichero.paginas.sort(key=lambda x: f200.ORDEN[x.codigo])
    return fichero
