"""Control de cambios normativos: de qué normas y diseños de registro depende Conta, cuándo hay que mirar si han cambiado y qué hacer si cambian.

Cada `Fuente` es algo que la AEAT, el Registro Mercantil o el BOE pueden cambiar y que Conta tiene implementado a mano: el diseño de registro de un modelo (200, 202, 303, 390…), el calendario
de plazos, la taxonomía del depósito de cuentas o el plan contable. De cada una se guarda con qué versión se implementó y cuándo suele salir la siguiente (la «ventana»).

Cuatro mecanismos, de menos a más automático:
1. **Calendario**: a partir de la ventana de cada fuente, y mientras nadie la haya marcado como «revisada» después, sale un aviso (en la pantalla de Normativa y en la auditoría).
2. **Sondeo**: una consulta `HEAD` a la sede (sin descargar nada) compara el tamaño y la fecha de modificación del diseño con los de cuando se implementó, y mira si ya existe el diseño del ejercicio siguiente.
3. **BOE**: para lo que nace de una resolución (los modelos de cuentas anuales del Registro Mercantil, de los que depende el D2), se consulta la API pública y oficial del BOE (`datosabiertos/api/boe/sumario`)
   en la época del año en que suelen salir (abril a julio) y se buscan títulos con las palabras clave de la fuente. Es incremental (no repite días ya vistos) y se identifica como Conta. Lo hallado se enseña
   con su enlace para que lo lea una persona.
4. **Comparación**: `tools/comparar_disenos.py` dice qué páginas, campos y casillas cambian entre dos versiones de un diseño; el procedimiento completo está en `docs/11_control_de_cambios_normativos.md`.

Las revisiones, el último sondeo y lo visto en el BOE se guardan en `_normativa.json`, junto a las bases de datos (como las preferencias): no son datos contables y valen para todas las empresas.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from conta_pridalac.auditoria import AVISO, Hallazgo
from conta_pridalac.web.config import Configuracion

BASE_DISENOS = "https://sede.agenciatributaria.gob.es/static_files/Sede/Disenyo_registro/"
REFERENCIA_INICIAL = date(2026, 11, 3)  # el día en que se fijó el estado de cada fuente (se tomaron entonces el tamaño y la fecha de cada diseño)


@dataclass(frozen=True)
class Fuente:
    clave: str
    nombre: str
    version: str  # con qué versión está implementado
    ejercicio: int  # a qué ejercicio corresponde esa versión
    ventana: tuple[int, int]  # (mes, día) desde el que, cada año, suele salir lo nuevo y hay que mirar
    donde: str  # qué módulos de Conta dependen de ello
    que_hacer: str  # procedimiento si hay cambios
    url: str | None = None  # ruta del diseño bajo BASE_DISENOS, si se puede sondear
    siguiente: str | None = None  # plantilla de la ruta del diseño del ejercicio siguiente ({yy} dos cifras, {aaaa} cuatro)
    tamano: int | None = None  # bytes del diseño cuando se implementó
    modificado: str | None = None  # cabecera Last-Modified en ese momento
    oficial: str = "Sede electrónica de la AEAT → Ayuda → Diseños de registro"
    boe: tuple[str, ...] = ()  # palabras que tiene que llevar (todas) el título de una disposición del BOE para que cuente como novedad de esta fuente
    boe_meses: tuple[int, int] = (1, 12)  # meses (primero y último) del año en que se busca en el BOE


def _version(modulo: str, atributo: str = "DISENO_VERSION") -> str:
    try:
        import importlib

        return str(getattr(importlib.import_module(f"conta_pridalac.ficheros_aeat.{modulo}"), atributo))
    except Exception:  # pragma: no cover - un módulo que no carga no debe tumbar la pantalla
        return "?"


CATALOGO: tuple[Fuente, ...] = (
    Fuente("200", "Modelo 200 · Impuesto sobre Sociedades", _version("fichero200"), 2025, (4, 1),
           "ficheros_aeat/fichero200.py, dr200_2025.json, servicios/impuesto_sociedades_200*.py",
           "Bajar el diseño nuevo, `tools/dr200_a_json.py`, `tools/comparar_disenos.py` contra el anterior, crear `dr200_AAAA.json` y ajustar el generador; comprobarlo en la sede con `tools/comparar_200.py` y la importación sin presentar.",
           "DR_200_299/archivos_25/DR200e25.xls", "DR_200_299/archivos_{yy}/DR200e{yy}.xls", 11527168, "Fri, 19 Jun 2026 13:39:33 GMT"),
    Fuente("202", "Modelo 202 · Pago fraccionado", _version("fichero202"), 2025, (1, 15), "ficheros_aeat/fichero202.py, dr202_2025.json, servicios/presentacion202.py",
           "El diseño es «2025 y siguientes»: mirar solo si cambia su versión (v1.3). Si cambia, `tools/extraer_diseno_aeat.py` y comparar.",
           "DR_200_299/archivos_25/DR202e25.xlsx", None, 134404, "Tue, 14 Jul 2026 11:16:59 GMT"),
    Fuente("303", "Modelo 303 · IVA", _version("fichero303"), 2026, (1, 5), "ficheros_aeat/fichero303.py, dr303_2026.json, servicios/presentacion303.py",
           "Cada enero y cuando la AEAT lo cambie en el año (en 2026 cambió desde el 2T): `tools/extraer_diseno_aeat.py`, comparar y ajustar casillas.",
           "DR_300_399/archivos_26/DR303e26v101.xlsx", "DR_300_399/archivos_{yy}/DR303e{yy}.xlsx", 386926, "Wed, 28 Jan 2026 13:11:00 GMT"),
    Fuente("390", "Modelo 390 · Resumen anual del IVA", _version("fichero390"), 2026, (10, 15), "ficheros_aeat/fichero390.py, dr390_2026.json, servicios/presentacion390.py",
           "Sale en otoño para el ejercicio siguiente: extraer, comparar con el anterior (en 2026 cambió con la Orden HAC/27/2026) y ajustar. Se presenta en enero.",
           "DR_300_399/archivos_26/dr390e2026.xlsx", "DR_300_399/archivos_{yy}/dr390e{aaaa}.xlsx", 556940, "Mon, 26 Oct 2026 09:05:48 GMT"),
    Fuente("190", "Modelo 190 · Resumen anual de retenciones", _version("fichero190"), 2025, (12, 1), "ficheros_aeat/fichero190.py, servicios/presentacion190.py",
           "Diseño lógico anual (se presenta en enero): mirar en diciembre si hay uno nuevo; comparar con el anterior."),
    Fuente("347", "Modelo 347 · Operaciones con terceros", _version("fichero347"), 2025, (12, 1), "ficheros_aeat/fichero347.py, servicios/presentacion347.py",
           "Diseño anual (se presenta en febrero): mirar en diciembre si hay uno nuevo; comparar con el anterior."),
    Fuente("111", "Modelo 111 · Retenciones", _version("fichero111"), 2016, (1, 15), "ficheros_aeat/fichero111.py, servicios/presentacion111.py",
           "Diseño estable desde 2016 (v18): mirar cada enero si cambia su versión."),
    Fuente("115", "Modelo 115 · Retenciones por alquileres", _version("fichero115"), 2019, (1, 15), "ficheros_aeat/fichero115.py, servicios/presentacion115.py",
           "Diseño estable desde 2019 (v1.3): mirar cada enero si cambia su versión."),
    Fuente("180", "Modelo 180 · Resumen anual de retenciones por alquileres", _version("fichero180"), 2023, (12, 1), "ficheros_aeat/fichero180.py, servicios/presentacion180.py",
           "Diseño lógico anual (se presenta en enero): mirar en diciembre si hay uno nuevo que el de 2023 y comparar con él; el último que tenemos es `DR_Mod_180_2023.pdf`."),
    Fuente("plazos", "Calendario del contribuyente (plazos y domiciliación)", "Calendario 2026", 2026, (12, 1), "servicios/plazos.py (tabla PUBLICADAS)",
           "El calendario del año siguiente sale en diciembre: añadir las fechas de domiciliación a `PUBLICADAS` y comprobar las de los modelos anuales."),
    Fuente("d2", "Depósito de cuentas · D2 y taxonomía XBRL", "Taxonomía PGC 2007 v171", 2025, (2, 1), "exportacion/xbrl_deposito.py, servicios/deposito_cuentas.py",
           "Cada año el BOE publica (abril a junio) la resolución de la Dirección General de Seguridad Jurídica y Fe Pública con los modelos de cuentas anuales, y después el Registro actualiza D2: leer la resolución, "
           "revisar los datos de identificación (p. ej. el CNAE) y los modelos que cambian, y probar la importación de los ZIP en D2 sin enviar. "
           "Revisada la Resolución de 19/05/2026 (BOE-A-2026-11581): CNAE solo 2025 (ya lo estaba) y mención de la reformulación del RDL 4/2025 en la certificación.",
           oficial="Aplicación D2 (Registradores) y sede de los Registradores", boe=("modelos", "registro mercantil", "cuentas anuales"), boe_meses=(4, 7)),
    Fuente("legalia", "Legalización de libros · Legalia2", "Formato LL (DATOS.TXT) 2025", 2025, (2, 1), "servicios/libros_oficiales.py",
           "Antes de abril: comprobar que Legalia2 sigue importando el ZIP en la carpeta de prueba (sin enviar).", oficial="Aplicación Legalia2 (Registradores)"),
    Fuente("pgc", "Plan General de Contabilidad (PYMES) y modelos de cuentas anuales", "RD 1514/2007 y RD 1515/2007 (mod. RD 602/2016)", 2026, (12, 15),
           "servicios/cuentas_anuales.py, domain/memoria_pymes.py, servicios/deposito_cuentas.py",
           "Mirar en el BOE si hay un real decreto o una resolución del ICAC nuevos que cambien cuentas o modelos de cuentas anuales; si los hay, revisar las líneas del balance, la PyG y la memoria.",
           oficial="BOE (boe.es) y web del ICAC"),
)
POR_CLAVE = {f.clave: f for f in CATALOGO}


# ------------------------------------------------------------------------------------------------ calendario

def apertura_vigente(fuente: Fuente, hoy: date) -> date:
    """La última vez (hasta hoy) que se abrió la ventana en que suele salir lo nuevo."""
    mes, dia = fuente.ventana
    este_ano = date(hoy.year, mes, dia)
    return este_ano if este_ano <= hoy else date(hoy.year - 1, mes, dia)


def proxima_apertura(fuente: Fuente, hoy: date) -> date:
    mes, dia = fuente.ventana
    este_ano = date(hoy.year, mes, dia)
    return este_ano if este_ano > hoy else date(hoy.year + 1, mes, dia)


@dataclass
class Estado:
    fuente: Fuente
    revisada: date  # la última vez que se miró (o el día de referencia, si nunca)
    por_revisar: bool
    apertura: date  # la ventana vigente
    proxima: date
    sondeo: dict = field(default_factory=dict)  # lo último que dijo la sede: ver `sondear`
    revision_explicita: date | None = None  # el día en que alguien la marcó como revisada (None = nunca)

    @property
    def novedades_boe(self) -> list[dict]:
        """Disposiciones del BOE halladas y publicadas **después** de la última revisión. Si nunca se ha marcado como revisada, cuentan todas las del ejercicio siguiente al implementado."""
        corte = self.revision_explicita or date(self.fuente.ejercicio + 1, 1, 1)
        return [h for h in (self.sondeo.get("boe") or {}).get("encontradas", []) if (_fecha(h.get("fecha")) or corte) > corte]

    @property
    def cambio_detectado(self) -> bool:
        return bool(self.sondeo.get("cambiado") or self.sondeo.get("siguiente_existe") or self.novedades_boe)


def estados(config: Configuracion | None = None, hoy: date | None = None) -> list[Estado]:
    hoy = hoy or date.today()
    datos = _leer(config or Configuracion())
    resultado = []
    for f in CATALOGO:
        revisada = _fecha(datos["revisadas"].get(f.clave)) or REFERENCIA_INICIAL
        apertura = apertura_vigente(f, hoy)
        resultado.append(Estado(f, revisada, revisada < apertura, apertura, proxima_apertura(f, hoy), datos["sondeos"].get(f.clave, {}), _fecha(datos["revisadas"].get(f.clave))))
    return resultado


def hallazgos_de_normativa(config: Configuracion | None = None, hoy: date | None = None) -> list[Hallazgo]:
    """Los avisos de la auditoría: lo que está por revisar o lo que la sede dice que ha cambiado. No es contabilidad: nunca impide nada."""
    salida = []
    for e in estados(config, hoy):
        if e.novedades_boe and not (e.sondeo.get("cambiado") or e.sondeo.get("siguiente_existe")):
            h = e.novedades_boe[-1]
            salida.append(Hallazgo("normativa_novedad_en_el_boe", AVISO, f"{e.fuente.nombre}: el BOE ha publicado el {_fecha(h['fecha']):%d/%m/%Y} «{h['titulo'][:160]}» ({h['id']}). {e.fuente.que_hacer}", e.fuente.clave))
        elif e.cambio_detectado:
            que = "ha cambiado el diseño" if e.sondeo.get("cambiado") else f"ya hay diseño del ejercicio {e.fuente.ejercicio + 1}"
            salida.append(Hallazgo("normativa_cambio_en_la_sede", AVISO, f"{e.fuente.nombre}: la sede indica que {que} (consulta del {e.sondeo.get('fecha', '')}). {e.fuente.que_hacer}", e.fuente.clave))
        elif e.por_revisar:
            salida.append(Hallazgo("normativa_por_revisar", AVISO, f"{e.fuente.nombre}: desde el {e.apertura:%d/%m/%Y} puede haber novedades y no consta revisado (última revisión {e.revisada:%d/%m/%Y}). {e.fuente.que_hacer}", e.fuente.clave))
    return salida


# ------------------------------------------------------------------------------------------------ sondeo

Abridor = Callable[[str], tuple[int | None, str | None]]  # ruta completa → (tamaño, modificado) o (None, None) si no existe


def _head(url: str) -> tuple[int | None, str | None]:
    """(tamaño, Last-Modified) del fichero de la sede, o (None, None) si no existe (404). Cualquier otro fallo (sin red, tiempo agotado) sube como `OSError`."""
    peticion = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (Conta-Pridalac)"})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            tam = r.headers.get("Content-Length")
            return (int(tam) if tam and tam.isdigit() else None), r.headers.get("Last-Modified")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise OSError(f"La sede respondió {e.code} a {url}") from e
    except urllib.error.URLError as e:
        raise OSError(f"No se pudo consultar la sede: {e.reason}") from e


AbridorBoe = Callable[[date], dict | None]  # día → sumario del BOE de ese día (JSON ya leído) o None si ese día no hubo BOE
BOE_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{dia:%Y%m%d}"
MAX_DIAS_BOE = 150  # tope de consultas al BOE en una pasada: si hay más, se sigue en la siguiente (se guarda hasta dónde se llegó)


def _boe_dia(dia: date) -> dict | None:
    """El sumario del BOE de un día, por la API de datos abiertos (pública y oficial). 404 = ese día no hubo BOE. Cualquier otro fallo sube como `OSError`."""
    peticion = urllib.request.Request(BOE_SUMARIO.format(dia=dia), headers={"Accept": "application/json", "User-Agent": "Conta-Pridalac (control de normativa)"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise OSError(f"El BOE respondió {e.code} para el {dia:%d/%m/%Y}") from e
    except (urllib.error.URLError, ValueError) as e:
        raise OSError(f"No se pudo consultar el BOE: {getattr(e, 'reason', e)}") from e


def _disposiciones(sumario: dict):
    """Todas las disposiciones (con título e identificador) de un sumario del BOE, esté donde esté en su árbol."""
    pila = [sumario]
    while pila:
        x = pila.pop()
        if isinstance(x, dict):
            if "titulo" in x and "identificador" in x:
                yield x
            pila.extend(x.values())
        elif isinstance(x, list):
            pila.extend(x)


def _normalizar(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _ventanas_boe(fuente: Fuente, hasta_dia: date) -> list[tuple[date, date]]:
    """Los tramos de fechas que hay que mirar en el BOE: cada año, desde el ejercicio siguiente al implementado, entre los meses de `boe_meses`, y sin pasar de hoy."""
    m1, m2 = fuente.boe_meses
    tramos = []
    for anio in range(fuente.ejercicio + 1, hasta_dia.year + 1):
        ultimo = date(anio + (m2 == 12), (m2 % 12) + 1, 1) - timedelta(days=1)
        ini, fin = date(anio, m1, 1), min(ultimo, hasta_dia)
        if ini <= fin:
            tramos.append((ini, fin))
    return tramos


def sondear_boe(fuente: Fuente, abrir: AbridorBoe | None = None, hoy: date | None = None, previo: dict | None = None) -> dict:
    """Busca en el BOE las disposiciones cuyo título lleve las palabras de `fuente.boe`, sin repetir los días ya vistos (`previo`). Devuelve
    `{"hasta": último día mirado, "encontradas": [{"id", "fecha", "titulo", "url"}], "error": None|texto, "consultas": n}`; si falla a medias, conserva lo hallado y hasta dónde llegó."""
    abrir = abrir or _boe_dia
    hoy = hoy or date.today()
    previo = previo or {}
    visto = _fecha(previo.get("hasta"))
    encontradas = {h["id"]: h for h in previo.get("encontradas", [])}
    palabras = [_normalizar(p) for p in fuente.boe]
    hasta, error, consultas = visto, None, 0
    try:
        for ini, fin in _ventanas_boe(fuente, hoy):
            dia = max(ini, visto + timedelta(days=1)) if visto else ini
            while dia <= fin:
                if dia.weekday() != 6:  # el BOE no se publica los domingos
                    if consultas >= MAX_DIAS_BOE:
                        raise OSError("Se ha mirado una parte; vuelva a consultar para seguir")
                    consultas += 1
                    sumario = abrir(dia)
                    for d in _disposiciones(sumario or {}):
                        if all(p in _normalizar(d["titulo"]) for p in palabras):
                            url = (d.get("url_pdf") or {}).get("texto") or d.get("url_html") or ""
                            encontradas[d["identificador"]] = {"id": d["identificador"], "fecha": dia.isoformat(), "titulo": d["titulo"].strip(), "url": url}
                hasta = dia
                dia += timedelta(days=1)
    except OSError as e:
        error = str(e)
    return {"hasta": hasta.isoformat() if hasta else None, "encontradas": sorted(encontradas.values(), key=lambda h: (h["fecha"], h["id"])), "error": error, "consultas": consultas}


def sondear(fuente: Fuente, abrir: Abridor = _head, hoy: date | None = None, abrir_boe: AbridorBoe | None = None, previo: dict | None = None) -> dict:
    """Pregunta a la sede por el diseño de la fuente y por el del ejercicio siguiente. Devuelve:
    `{"fecha", "cambiado": bool|None, "tamano", "modificado", "siguiente_existe": bool|None, "error"}` (None = no se puede saber)."""
    hoy = hoy or date.today()
    r: dict = {"fecha": hoy.isoformat(), "cambiado": None, "tamano": None, "modificado": None, "siguiente_existe": None, "error": None}
    try:
        if fuente.url:
            tam, mod = abrir(BASE_DISENOS + fuente.url)
            r.update(tamano=tam, modificado=mod)
            r["cambiado"] = True if tam is None else (tam != fuente.tamano or (fuente.modificado is not None and mod != fuente.modificado))
        if fuente.siguiente:
            aaaa = fuente.ejercicio + 1
            tam, _ = abrir(BASE_DISENOS + fuente.siguiente.format(yy=f"{aaaa % 100:02d}", aaaa=aaaa))
            r["siguiente_existe"] = tam is not None
    except OSError as e:
        r["error"] = str(e)
    if fuente.boe:
        r["boe"] = sondear_boe(fuente, abrir_boe, hoy, (previo or {}).get("boe"))
        r["error"] = r["error"] or r["boe"]["error"]
    return r


def guardar_sondeo(config: Configuracion, clave: str, resultado: dict) -> None:
    datos = _leer(config)
    datos["sondeos"][clave] = resultado
    _escribir(config, datos)


def sondear_todo(config: Configuracion | None = None, abrir: Abridor = _head, hoy: date | None = None, abrir_boe: AbridorBoe | None = None) -> dict[str, dict]:
    """Sondea las fuentes que tienen dirección o palabras para el BOE y guarda el resultado."""
    config = config or Configuracion()
    anteriores = _leer(config)["sondeos"]
    resultados = {f.clave: sondear(f, abrir, hoy, abrir_boe, anteriores.get(f.clave)) for f in CATALOGO if f.url or f.siguiente or f.boe}
    datos = _leer(config)
    datos["sondeos"].update(resultados)
    _escribir(config, datos)
    return resultados


# ------------------------------------------------------------------------------------------------ revisiones

def marcar_revisada(config: Configuracion, clave: str, dia: date | None = None) -> date:
    if clave not in POR_CLAVE:
        raise ValueError(f"Fuente desconocida: {clave}")
    dia = dia or date.today()
    datos = _leer(config)
    datos["revisadas"][clave] = dia.isoformat()
    _escribir(config, datos)
    return dia


def _ruta(config: Configuracion) -> Path:
    return config.datos / "_normativa.json"


def _fecha(texto: str | None) -> date | None:
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date() if texto else None
    except ValueError:
        return None


def _leer(config: Configuracion) -> dict:
    try:
        crudo = json.loads(_ruta(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        crudo = {}
    return {"revisadas": dict(crudo.get("revisadas") or {}), "sondeos": dict(crudo.get("sondeos") or {})}


def _escribir(config: Configuracion, datos: dict) -> None:
    ruta = _ruta(config)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
