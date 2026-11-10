"""Componente de listado reutilizable (principios de diseño §1).

Cada listado sólo declara sus columnas, sus campos de edición y cómo obtener, guardar y borrar; el comportamiento (filtro, orden,
selección, doble clic para editar, exportación a PDF y Excel respetando lo que se ve) es el mismo en todas las pantallas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Ejercicio, Empresa
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.domain.fechas import introducir_fecha
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, PORCENTAJE, TEXTO, Columna, Tabla, formatear


@dataclass
class Contexto:
    """Dónde estamos: la empresa, el ejercicio y la sesión de base de datos de esta petición."""

    sesion: Session
    empresa: Empresa
    ejercicio: Ejercicio
    slug: str
    config: object = None
    ensayo: bool = False  # la base es una copia de ensayo (se mira al empezar la petición: una restauración cambia la base a mitad)


@dataclass
class Col:
    clave: str
    titulo: str
    tipo: str = TEXTO
    ancho: float = 1.0


@dataclass
class Campo:
    """Un campo de formulario (o de parámetros de un informe). `tipo`: texto, textarea, numero, dinero, fecha, select, checkbox."""

    nombre: str
    titulo: str
    tipo: str = "texto"
    requerido: bool = False
    opciones: list[tuple[str, str]] | Callable[[Contexto], list[tuple[str, str]]] | None = None
    ayuda: str = ""
    solo_alta: bool = False  # sólo se puede escribir al crear
    defecto: str = ""
    sugerencias: Callable[[Contexto], list[tuple[str, str]]] | None = None  # valores propuestos para un campo de texto (datalist)
    seccion: str = ""  # el campo empieza una sección nueva del formulario con este título
    ancho: int = 1  # columnas que ocupa en el formulario (1 o 2)
    lista: str = ""  # id de la lista de sugerencias si se comparte entre campos (por defecto la del propio campo)

    def lista_de_opciones(self, ctx: Contexto) -> list[tuple[str, str]]:
        return self.opciones(ctx) if callable(self.opciones) else list(self.opciones or [])


@dataclass
class Fila:
    id: str | None
    valores: dict
    clase: str = ""  # clase CSS opcional de la fila (p. ej. "aviso")
    borrable: bool = True  # en un listado con «Borrar», si la fila ofrece su casilla de selección (lo que no se puede borrar ni se ofrece)


@dataclass
class Detalle:
    """Vista de sólo lectura de una fila (doble clic en un listado no editable)."""

    titulo: str
    tabla: Tabla
    datos: list[tuple[str, str]] = field(default_factory=list)  # pares «campo: valor» que se muestran encima de la tabla
    extras: list[Tabla] = field(default_factory=list)  # tablas adicionales (asientos, vencimientos, justificantes…)
    enlaces: list[tuple[str, str]] = field(default_factory=list)  # (texto, dirección) de pantallas relacionadas


class Listado:
    nombre = ""
    titulo = ""
    descripcion = ""
    columnas: list[Col] = []
    campos: list[Campo] = []  # formulario de alta y edición
    parametros: list[Campo] = []  # filtros propios del listado (nivel de un balance, cuenta de un mayor…)
    anadir = False
    borrar = False
    editable = False
    formulario_propio = False  # el listado trae su propio formulario (facturas): ver `web/facturas.py`
    bloque_inferior = ""  # nombre de otro listado que se enseña debajo de éste, en la misma pantalla (p. ej. las declaraciones presentadas bajo el 303)
    acciones_extra: list[tuple[str, str]] = []  # botones propios de la barra: (texto, ruta bajo el listado), p. ej. «Desde plantilla»
    acciones_con_seleccion: list[tuple[str, str]] = []  # botones que actúan sobre las filas marcadas: (texto, ruta bajo el listado); reciben los ids marcados (campo «ids») por POST y están desactivados mientras no haya ninguna marcada

    # ---- a implementar -----------------------------------------------------------------------------------
    def filas(self, ctx: Contexto, params: dict) -> list[Fila]:
        raise NotImplementedError

    def valores_formulario(self, ctx: Contexto, id: str) -> dict:
        raise NotImplementedError

    def guardar(self, ctx: Contexto, id: str | None, datos: dict) -> str:
        raise NotImplementedError

    def eliminar(self, ctx: Contexto, ids: list[str]) -> None:
        raise NotImplementedError

    def detalle(self, ctx: Contexto, id: str) -> Detalle | None:
        return None

    def totales(self, filas: list[Fila]) -> dict | None:
        return None

    def resumen(self, ctx: Contexto, filas: list[Fila]) -> str | None:
        """Una línea sobre lo que se está viendo (p. ej. «3 errores y 5 avisos»), encima de la tabla."""
        return None

    def cabecera_de_formulario(self, ctx: Contexto, id: str | None) -> list[tuple[str, str]]:
        """Lo que el formulario de una fila enseña arriba para que se vea qué se está decidiendo (la línea del banco, la factura…): pares (nombre, valor)."""
        return []

    def enlaces_de_formulario(self, ctx: Contexto, id: str | None) -> list[tuple[str, str]]:
        """Enlaces que el formulario de una fila ofrece arriba (se abren en otra pestaña): (texto, dirección). Por ejemplo, el PDF de la factura."""
        return []

    def texto_vacio(self, ctx: Contexto, params: dict) -> str:
        return "No hay filas"

    def trimestre_de_trabajo(self, ctx: Contexto) -> str | None:
        """«4T 2026» en las pantallas que trabajan con un trimestre (se enseña arriba, con el enlace para cambiarlo); `None` en las demás."""
        return None

    def subtitulo(self, ctx: Contexto, params: dict) -> str:
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio}"

    # ---- común --------------------------------------------------------------------------------------------
    def abre_con_doble_clic(self) -> bool:
        return self.editable or type(self).detalle is not Listado.detalle


# ------------------------------------------------------------------------------------------------ orden y filtro


def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFD", str(texto).lower()).encode("ascii", "ignore").decode()).strip()


def _clave_orden(valor, tipo: str):
    if valor is None or valor == "":
        return (1, 0)
    if tipo == TEXTO:
        return (0, normalizar(valor))
    return (0, valor)


def ordenar(filas: list[Fila], columnas: list[Col], clave: str | None, descendente: bool) -> list[Fila]:
    col = next((c for c in columnas if c.clave == clave), None)
    if col is None:
        return filas
    con = [f for f in filas if f.valores.get(col.clave) not in (None, "")]
    sin = [f for f in filas if f.valores.get(col.clave) in (None, "")]
    try:
        con.sort(key=lambda f: _clave_orden(f.valores.get(col.clave), col.tipo), reverse=descendente)
    except TypeError:  # tipos mezclados en una columna: se ordena por su texto
        con.sort(key=lambda f: normalizar(f.valores.get(col.clave)), reverse=descendente)
    return con + sin  # los vacíos van siempre al final


def filtrar(filas: list[Fila], columnas: list[Col], consulta: str) -> list[Fila]:
    palabras = normalizar(consulta).split()
    if not palabras:
        return filas
    resultado = []
    for f in filas:
        texto = normalizar(" ".join(formatear(f.valores.get(c.clave), c.tipo) for c in columnas))
        if all(p in texto for p in palabras):
            resultado.append(f)
    return resultado


# ------------------------------------------------------------------------------------------------ formularios


def parsear_dinero(texto: str) -> Decimal:
    t = (texto or "").strip().replace(" ", "").replace("€", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t).quantize(Decimal("0.01"))
    except InvalidOperation as e:
        raise ValueError(f"«{texto}» no es un importe válido") from e


def leer_formulario(campos: list[Campo], formulario: dict, ctx: Contexto, *, alta: bool) -> tuple[dict, list[str]]:
    """Convierte el texto del formulario a valores Python. Devuelve (datos, errores)."""
    datos, errores = {}, []
    for c in campos:
        if c.solo_alta and not alta:
            continue
        bruto = formulario.get(c.nombre)
        texto = (bruto or "").strip() if isinstance(bruto, str) or bruto is None else str(bruto)
        if c.tipo == "checkbox":
            datos[c.nombre] = bruto in ("on", "true", "1", True)
            continue
        if not texto:
            if c.requerido:
                errores.append(f"Falta «{c.titulo}»")
            datos[c.nombre] = None
            continue
        try:
            if c.tipo == "fecha":
                datos[c.nombre] = introducir_fecha(texto, ctx.ejercicio)
            elif c.tipo == "dinero":
                datos[c.nombre] = parsear_dinero(texto)
            elif c.tipo == "numero":
                datos[c.nombre] = int(texto)
            elif c.tipo == "select":
                if texto not in {v for v, _ in c.lista_de_opciones(ctx)}:
                    raise ValueError(f"«{c.titulo}»: opción no válida")
                datos[c.nombre] = texto
            else:
                datos[c.nombre] = texto
        except ErrorContable as e:
            errores.append(f"«{c.titulo}»: {e}")
        except ValueError as e:
            errores.append(str(e) if "válid" in str(e) else f"«{c.titulo}»: valor no válido")
    return datos, errores


def a_texto_de_formulario(valor, tipo: str) -> str:
    """Cómo se rellena un campo al editar."""
    if valor is None:
        return ""
    if tipo == "fecha" and isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if tipo == "dinero":
        return f"{Decimal(valor):.2f}".replace(".", ",")
    return str(valor)


# ------------------------------------------------------------------------------------------------ exportación


def tabla_de_listado(
    listado: Listado, ctx: Contexto, filas: list[Fila], params: dict, ocultas: set[str] | None = None
) -> Tabla:
    """La tabla que se exporta: las columnas visibles y las filas filtradas y ordenadas tal como se ven en pantalla."""
    ocultas = ocultas or set()
    cols = [c for c in listado.columnas if c.clave not in ocultas]
    exportables = [Columna(c.titulo, c.tipo, c.ancho) for c in cols]
    datos = [[f.valores.get(c.clave) for c in cols] for f in filas]
    totales = listado.totales(filas)
    fila_totales = None
    if totales:
        fila_totales = [totales.get(c.clave) for c in cols]
        primera_texto = next((i for i, c in enumerate(cols) if c.tipo == TEXTO), None)
        if primera_texto is not None and fila_totales[primera_texto] is None:
            fila_totales[primera_texto] = "Totales"
    return Tabla(listado.titulo, exportables, datos, listado.subtitulo(ctx, params), totales=fila_totales)


TIPOS_NUMERICOS = (DINERO, ENTERO, PORCENTAJE)
