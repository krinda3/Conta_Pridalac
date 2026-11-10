"""Categorías de análisis del gasto (gas, electricidad, combustible, abonos, labores…).

No son cuentas ni cambian ningún asiento: son una etiqueta por factura para poder analizar el gasto por conceptos con sentido, también el de los ejercicios cerrados (cuyos diarios están
legalizados y cuyos modelos están presentados). Por eso fijar la categoría de una factura **no exige ejercicio abierto** ni trimestre sin presentar, y queda anotado en el registro de cambios.

Cómo se resuelve la categoría de cada línea de gasto:
1. la de la factura (`Factura.categoria_gasto_id`), con su reparto (`FacturaReparto`) si una parte va a otra categoría;
2. si la factura no tiene, la categoría cuyas `cuentas` (prefijos) encajan con la cuenta de la línea (el prefijo más largo gana): así las cuentas nuevas de 2026 en adelante enlazan solas;
3. si no hay ninguna, «Sin clasificar».

La carga inicial se hace con reglas «proveedor → categoría» (`clasificar_facturas`); ver `docs/12_categorias_de_gasto.md`.
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select, type_coerce
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    TIPO_RECIBIDAS,
    Apunte,
    Asiento,
    CategoriaGasto,
    Cuenta,
    Ejercicio,
    Factura,
    FacturaReparto,
    Tercero,
)
from conta_pridalac.db.tipos import Dinero, dinero
from conta_pridalac.domain.errores import ErrorContable

SIN_CLASIFICAR = "SIN_CLASIFICAR"
NETO = type_coerce(func.sum(Apunte.debe - Apunte.haber), Dinero)  # debe − haber, en euros (Decimal)
TIPOS = ("gasto", "inversion", "amortizacion", "impuesto", "excepcional", "financiero")
# lo que se considera «línea de gasto»: gasto (6), inmovilizado (20-21) y existencias (32) de las facturas recibidas; del resto de asientos sólo el grupo 6
_GRUPOS_FACTURA = ("6", "20", "21", "32")


def normalizar(texto: str | None) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (texto or "").upper()) if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ categorías

def _prefijos(categoria: CategoriaGasto) -> list[str]:
    return [p.strip() for p in (categoria.cuentas or "").split(",") if p.strip()]


def categorias_de(sesion: Session, empresa_id: int) -> list[CategoriaGasto]:
    return list(sesion.scalars(select(CategoriaGasto).where(CategoriaGasto.empresa_id == empresa_id).order_by(CategoriaGasto.orden, CategoriaGasto.nombre)))


def categoria_por_codigo(sesion: Session, empresa_id: int, codigo: str) -> CategoriaGasto | None:
    return sesion.scalars(select(CategoriaGasto).where(CategoriaGasto.empresa_id == empresa_id, CategoriaGasto.codigo == codigo)).first()


def crear_o_actualizar_categoria(sesion: Session, empresa_id: int, codigo: str, nombre: str, tipo: str = "gasto", cuentas: list[str] | None = None,
                                 orden: int = 0, amortizacion_anos: int | None = None, cuenta_destino: str | None = None) -> CategoriaGasto:
    if tipo not in TIPOS:
        raise ErrorContable(f"Tipo de categoría desconocido: {tipo!r}")
    c = categoria_por_codigo(sesion, empresa_id, codigo)
    if c is None:
        c = CategoriaGasto(empresa_id=empresa_id, codigo=codigo, nombre=nombre, tipo=tipo)
        sesion.add(c)
    c.nombre, c.tipo, c.orden = nombre, tipo, orden
    if cuentas is not None:
        c.cuentas = ",".join(sorted(set(cuentas))) or None
    if amortizacion_anos is not None:
        c.amortizacion_anos = amortizacion_anos
    if cuenta_destino is not None:
        c.cuenta_destino = cuenta_destino
    sesion.flush()
    return c


def importar_catalogo(sesion: Session, empresa_id: int, reglas: dict) -> list[str]:
    """Crea o actualiza las categorías de un fichero de reglas (`categorias`, más los prefijos de cuenta de `cuentas_prioritarias` y `cuenta_por_defecto`). Devuelve lo que ha hecho."""
    cuentas: dict[str, set[str]] = defaultdict(set)
    for prefijo, cat in reglas.get("cuentas_prioritarias", {}).items():
        cuentas[cat].add(prefijo)
    for codigo, cat in reglas.get("cuenta_por_defecto", {}).items():
        if cat not in (SIN_CLASIFICAR,):
            cuentas[cat].add(codigo)
    informe = []
    for orden, (codigo, datos) in enumerate(reglas["categorias"].items()):
        existia = categoria_por_codigo(sesion, empresa_id, codigo) is not None
        anos, destino = datos.get("amortizacion_anos"), datos.get("cuenta_destino")
        if destino:
            cuentas[codigo].add(destino)  # lo que se contabilice en la cuenta destino cae solo en su categoría
        crear_o_actualizar_categoria(sesion, empresa_id, codigo, datos["nombre"], datos.get("tipo", "gasto"), sorted(cuentas.get(codigo, ())), orden, anos, destino)
        informe.append(f"{'Actualizada' if existia else 'Creada'} la categoría {codigo}: {datos['nombre']}")
    return informe


# ------------------------------------------------------------------ resolución por reglas (carga inicial)

def categoria_segun_reglas(reglas: dict, proveedor: str | None, cuenta: str | None) -> tuple[str, str, bool]:
    """→ (código de categoría, origen, revisar). La cuenta de la factura manda en algunos casos (623, inversión…), luego el proveedor, luego la cuenta."""
    for prefijo, cat in reglas.get("cuentas_prioritarias", {}).items():
        if cuenta and cuenta.startswith(prefijo):
            return cat, f"cuenta {prefijo}", False
    nombre = normalizar(proveedor)
    for regla in reglas.get("reglas_proveedor", []):
        if any(normalizar(p) in nombre for p in regla["nombre_contiene"]):
            cat = regla["categoria"]
            if isinstance(cat, dict):
                cat = cat.get(cuenta) or reglas.get("cuenta_por_defecto", {}).get(cuenta, SIN_CLASIFICAR)
            return cat, "proveedor", bool(regla.get("revisar"))
    cat = reglas.get("cuenta_por_defecto", {}).get(cuenta)
    if cat:
        return cat, f"cuenta {cuenta}", cat == SIN_CLASIFICAR
    return SIN_CLASIFICAR, "sin regla", True


@dataclass
class ResultadoClasificacion:
    facturas: int = 0
    asignadas: int = 0          # facturas a las que se les ha fijado una categoría
    iguales: int = 0            # ya tenían esa categoría
    por_cuenta: int = 0         # su categoría sale sola de la cuenta: no hace falta fijarla
    sin_categoria: list[str] = field(default_factory=list)
    detalle: list[str] = field(default_factory=list)


def clasificar_facturas(sesion: Session, empresa_id: int, reglas: dict, *, sobrescribir: bool = False) -> ResultadoClasificacion:
    """Fija la categoría de las facturas recibidas según las reglas y las excepciones por factura. No hace commit. Las facturas que ya tienen categoría se respetan salvo `sobrescribir`."""
    categorias = {c.codigo: c for c in categorias_de(sesion, empresa_id)}
    excepciones = {(e["ejercicio"], e["asiento"]): e["categoria"] for e in reglas.get("excepciones_factura", [])}
    res = ResultadoClasificacion()
    filas = sesion.execute(
        select(Factura, Ejercicio.anio, Tercero.nombre, Cuenta.codigo)
        .join(Ejercicio, Ejercicio.id == Factura.ejercicio_id)
        .outerjoin(Tercero, Tercero.id == Factura.tercero_id)
        .outerjoin(Cuenta, Cuenta.id == Factura.cuenta_contrapartida_id)
        .where(Ejercicio.empresa_id == empresa_id, Factura.sentido == "R")
    ).all()
    for factura, anio, proveedor, cuenta in filas:
        res.facturas += 1
        codigo = excepciones.get((anio, f"{TIPO_RECIBIDAS}.{factura.numero}"))
        if codigo is None:
            codigo = categoria_segun_reglas(reglas, proveedor, cuenta)[0]
        destino = categorias.get(codigo)
        if destino is None:
            res.sin_categoria.append(f"{anio} {TIPO_RECIBIDAS}.{factura.numero} {proveedor}: la categoría {codigo!r} no existe")
            continue
        derivada = _categoria_por_cuenta(list(categorias.values()), cuenta)
        if factura.categoria_gasto_id is not None and not sobrescribir:
            res.iguales += 1
            continue
        if derivada is not None and derivada.id == destino.id:
            if factura.categoria_gasto_id is not None:
                factura.categoria_gasto_id = None
                res.asignadas += 1
            else:
                res.por_cuenta += 1
            continue
        if factura.categoria_gasto_id == destino.id:
            res.iguales += 1
            continue
        factura.categoria_gasto_id = destino.id
        res.asignadas += 1
    sesion.flush()
    return res


def _categoria_por_cuenta(categorias: list[CategoriaGasto], cuenta: str | None) -> CategoriaGasto | None:
    """La categoría cuyo prefijo de cuenta es el más largo que encaja con la cuenta."""
    if not cuenta:
        return None
    mejor, largo = None, -1
    for c in categorias:
        for p in _prefijos(c):
            if cuenta.startswith(p) and len(p) > largo:
                mejor, largo = c, len(p)
    return mejor


def categoria_de_factura(categorias: list[CategoriaGasto], factura: Factura, cuenta: str | None) -> CategoriaGasto | None:
    """La categoría que cuenta para una factura: la suya si la tiene y, si no, la que sale de su cuenta de gasto."""
    if factura.categoria_gasto_id is not None:
        return next((c for c in categorias if c.id == factura.categoria_gasto_id), None)
    return _categoria_por_cuenta(categorias, cuenta)


# ------------------------------------------------------------------ asignación a mano

def asignar_categoria(sesion: Session, factura: Factura, categoria: CategoriaGasto | None) -> bool:
    """Fija (o quita, con `None`) la categoría de una factura. Permitido en ejercicios cerrados y trimestres presentados: no es un dato contable. Devuelve si ha cambiado algo."""
    nuevo = categoria.id if categoria is not None else None
    if categoria is not None:
        ejercicio = sesion.get(Ejercicio, factura.ejercicio_id)
        if categoria.empresa_id != ejercicio.empresa_id:
            raise ErrorContable("La categoría es de otra empresa")
    if factura.categoria_gasto_id == nuevo:
        return False
    factura.categoria_gasto_id = nuevo
    sesion.flush()
    return True


def repartir_factura(sesion: Session, factura: Factura, partes: list[tuple[CategoriaGasto, Decimal, str | None]]) -> None:
    """Sustituye el reparto de la factura: cada parte (categoría, base, nota) va a su categoría y el resto, a la principal. No puede superar el gasto de la factura."""
    gasto = sum((d for _, d in _lineas_de_factura(sesion, factura)), Decimal("0"))
    if sum((p[1] for p in partes), Decimal("0")) > gasto:
        raise ErrorContable(f"El reparto ({sum(p[1] for p in partes)}) supera el gasto de la factura ({gasto})")
    for r in list(sesion.scalars(select(FacturaReparto).where(FacturaReparto.factura_id == factura.id))):
        sesion.delete(r)
    sesion.flush()
    for categoria, importe, nota in partes:
        sesion.add(FacturaReparto(factura_id=factura.id, categoria_gasto_id=categoria.id, importe=importe, nota=nota))
    sesion.flush()


def _lineas_de_factura(sesion: Session, factura: Factura) -> list[tuple[str, Decimal]]:
    filas = sesion.execute(
        select(Cuenta.codigo, NETO)
        .join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Asiento.ejercicio_id == factura.ejercicio_id, Asiento.tipo == TIPO_RECIBIDAS, Asiento.numero == factura.numero)
        .group_by(Cuenta.codigo)
    ).all()
    return [(codigo, Decimal(neto)) for codigo, neto in filas if codigo.startswith(_GRUPOS_FACTURA) and neto]


# ------------------------------------------------------------------ informe

@dataclass
class FilaCategoria:
    categoria: CategoriaGasto | None
    por_anio: dict[int, Decimal] = field(default_factory=dict)
    proveedores: dict[str, dict[int, Decimal]] = field(default_factory=dict)
    amortizacion_teorica: dict[int, Decimal] = field(default_factory=dict)

    @property
    def nombre(self) -> str:
        return self.categoria.nombre if self.categoria else "Sin clasificar"

    @property
    def tipo(self) -> str:
        return self.categoria.tipo if self.categoria else "gasto"

    @property
    def total(self) -> Decimal:
        return sum(self.por_anio.values(), Decimal("0"))


@dataclass
class InformeCategorias:
    anios: list[int]
    filas: list[FilaCategoria]

    def total_gasto(self, anio: int) -> Decimal:
        """Gasto corriente del año (sin inversión, amortizaciones, impuestos, partidas excepcionales ni financieras)."""
        return sum((f.por_anio.get(anio, Decimal("0")) for f in self.filas if f.tipo == "gasto"), Decimal("0"))


def informe_por_categoria(sesion: Session, empresa_id: int) -> InformeCategorias:
    """Gasto por categoría y año de todos los ejercicios de la empresa (base imponible más el IVA no deducible, como en los libros). Solo lectura."""
    categorias = categorias_de(sesion, empresa_id)
    por_id = {c.id: c for c in categorias}
    filas: dict[int | None, FilaCategoria] = {}

    def fila(categoria_id: int | None) -> FilaCategoria:
        if categoria_id not in filas:
            filas[categoria_id] = FilaCategoria(por_id.get(categoria_id))
        return filas[categoria_id]

    def sumar(categoria_id, anio, proveedor, importe):
        f = fila(categoria_id)
        f.por_anio[anio] = f.por_anio.get(anio, Decimal("0")) + importe
        p = f.proveedores.setdefault(proveedor, {})
        p[anio] = p.get(anio, Decimal("0")) + importe

    repartos: dict[int, list[tuple[int, Decimal]]] = defaultdict(list)
    for r in sesion.scalars(select(FacturaReparto).join(Factura, Factura.id == FacturaReparto.factura_id).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(Ejercicio.empresa_id == empresa_id)):
        repartos[r.factura_id].append((r.categoria_gasto_id, Decimal(r.importe)))

    # líneas de gasto de las facturas recibidas
    consulta = (
        select(Factura.id, Factura.categoria_gasto_id, Ejercicio.anio, Tercero.nombre, Cuenta.codigo, NETO)
        .join(Ejercicio, Ejercicio.id == Factura.ejercicio_id)
        .join(Asiento, (Asiento.ejercicio_id == Factura.ejercicio_id) & (Asiento.tipo == TIPO_RECIBIDAS) & (Asiento.numero == Factura.numero))
        .join(Apunte, Apunte.asiento_id == Asiento.id).join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .outerjoin(Tercero, Tercero.id == Factura.tercero_id)
        .where(Ejercicio.empresa_id == empresa_id, Factura.sentido == "R")
        .group_by(Factura.id, Cuenta.codigo)
    )
    pendientes: dict[int, list] = defaultdict(list)
    for fid, cat_factura, anio, proveedor, cuenta, neto in sesion.execute(consulta):
        if not cuenta.startswith(_GRUPOS_FACTURA) or not neto:
            continue
        pendientes[fid].append((cat_factura, anio, proveedor or "(sin proveedor)", cuenta, Decimal(neto)))
    for fid, lineas in pendientes.items():
        total = sum((l[4] for l in lineas), Decimal("0"))
        resto_a_repartir = sum((imp for _, imp in repartos.get(fid, ())), Decimal("0"))
        for cat_id, imp in repartos.get(fid, ()):  # primero lo repartido
            sumar(cat_id, lineas[0][1], lineas[0][2], imp)
        for cat_factura, anio, proveedor, cuenta, neto in lineas:
            parte = neto * (total - resto_a_repartir) / total if total else neto  # lo que queda para la categoría principal, en proporción a cada línea
            cat_id = cat_factura if cat_factura is not None else getattr(_categoria_por_cuenta(categorias, cuenta), "id", None)
            sumar(cat_id, anio, proveedor, parte)
    # el resto de asientos (manuales, amortizaciones, impuestos…): solo el grupo 6. Se dejan fuera los que consumen existencias (llevan a gasto una cuenta del grupo 3): ese gasto
    # ya se contó cuando se compró, y contarlo otra vez al consumirlo lo duplicaría.
    consumo_de_existencias = select(Apunte.asiento_id).join(Cuenta, Cuenta.id == Apunte.cuenta_id).where(Cuenta.codigo.like("3%"))
    consulta = (
        select(Ejercicio.anio, Cuenta.codigo, Cuenta.nombre, NETO)
        .join(Asiento, Asiento.ejercicio_id == Ejercicio.id).join(Apunte, Apunte.asiento_id == Asiento.id).join(Cuenta, Cuenta.id == Apunte.cuenta_id)
        .where(Ejercicio.empresa_id == empresa_id, Cuenta.codigo.like("6%"), Asiento.tipo != TIPO_RECIBIDAS, func.coalesce(Asiento.subtipo, "").notin_(("R", "Z", "A")),
               Asiento.id.notin_(consumo_de_existencias))
        .group_by(Ejercicio.anio, Cuenta.codigo)
    )
    for anio, cuenta, nombre, neto in sesion.execute(consulta):
        if neto:
            c = _categoria_por_cuenta(categorias, cuenta)
            sumar(c.id if c else None, anio, f"{cuenta} {nombre}", Decimal(neto))

    for f in filas.values():  # el reparto proporcional puede dejar fracciones de céntimo
        f.por_anio = {a: dinero(v) for a, v in f.por_anio.items()}
        f.proveedores = {p: {a: dinero(v) for a, v in d.items()} for p, d in f.proveedores.items()}
    anios = sorted({a for f in filas.values() for a in f.por_anio})
    for f in filas.values():
        if f.categoria is not None and f.categoria.amortizacion_anos:
            n = f.categoria.amortizacion_anos
            for a in anios:  # informativo: cada compra se reparte en `n` años a partir del año de compra
                f.amortizacion_teorica[a] = sum((imp / n for ac, imp in f.por_anio.items() if ac <= a < ac + n), Decimal("0"))
    orden = {c.id: i for i, c in enumerate(categorias)}
    lista = sorted(filas.values(), key=lambda f: (f.tipo != "gasto", orden.get(f.categoria.id if f.categoria else None, 10**6), -float(f.total)))
    return InformeCategorias(anios, lista)


# ------------------------------------------------------------------ cuentas con sentido (ejercicio abierto)

@dataclass
class ResultadoReclasificacion:
    cuentas_creadas: list[str] = field(default_factory=list)
    facturas_movidas: list[str] = field(default_factory=list)
    sin_cambio: int = 0
    sin_destino: list[str] = field(default_factory=list)      # su categoría no tiene cuenta destino
    con_reparto: list[str] = field(default_factory=list)      # con reparto entre categorías: se dejan para decidir a mano
    fichas: list[str] = field(default_factory=list)           # proveedores cuya cuenta de gasto por defecto cambia
    fichas_varias: list[str] = field(default_factory=list)    # proveedores con facturas de varias categorías: la ficha no se toca


def reclasificar_ejercicio(sesion: Session, empresa_id: int, ejercicio: Ejercicio, reglas: dict, *, actualizar_fichas: bool = True) -> ResultadoReclasificacion:
    """Pasa las facturas recibidas de un **ejercicio abierto** a la cuenta destino de su categoría y pone esa cuenta en la ficha de los proveedores.

    No cambia importes, IVA ni fechas (usa `cambiar_proveedor_y_gasto`, que regenera el asiento de la factura y no altera ningún 303 presentado). Crea las subcuentas de `cuentas_nuevas` que falten.
    No hace commit.
    """
    from conta_pridalac.servicios import cuentas as svc_cuentas
    from conta_pridalac.servicios.correcciones import cambiar_proveedor_y_gasto

    if ejercicio.cerrado:
        raise ErrorContable(f"El ejercicio {ejercicio.anio} está cerrado: las cuentas de sus facturas no se tocan (para analizarlo basta con las categorías)")
    res = ResultadoReclasificacion()
    for codigo, nombre in reglas.get("cuentas_nuevas", {}).items():
        if sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo)).first() is None:
            svc_cuentas.crear_cuenta(sesion, empresa_id, codigo, nombre)
            res.cuentas_creadas.append(f"{codigo} {nombre}")
    categorias = categorias_de(sesion, empresa_id)
    por_id = {c.id: c for c in categorias}
    cuentas = {c.codigo: c for c in sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id))}
    con_reparto = {r for r in sesion.scalars(select(FacturaReparto.factura_id))}
    filas = sesion.execute(
        select(Factura, Tercero.nombre, Cuenta.codigo).join(Tercero, Tercero.id == Factura.tercero_id, isouter=True).join(Cuenta, Cuenta.id == Factura.cuenta_contrapartida_id, isouter=True)
        .where(Factura.ejercicio_id == ejercicio.id, Factura.sentido == "R").order_by(Factura.fecha_contable, Factura.numero)
    ).all()
    for factura, proveedor, cuenta_actual in filas:
        etiqueta = f"{factura.fecha_contable:%d/%m/%Y} {TIPO_RECIBIDAS}.{factura.numero} {proveedor or '(sin proveedor)'} {factura.total} €"
        categoria = por_id.get(factura.categoria_gasto_id) or _categoria_por_cuenta(categorias, cuenta_actual)
        if factura.id in con_reparto:
            res.con_reparto.append(etiqueta)
            continue
        if categoria is None or not categoria.cuenta_destino:
            res.sin_destino.append(f"{etiqueta} · {categoria.nombre if categoria else 'sin categoría'}")
            continue
        destino = cuentas.get(categoria.cuenta_destino)
        if destino is None:
            raise ErrorContable(f"La cuenta destino {categoria.cuenta_destino} de «{categoria.nombre}» no existe: añádala a `cuentas_nuevas`")
        if factura.cuenta_contrapartida_id == destino.id:
            res.sin_cambio += 1
            continue
        cambiar_proveedor_y_gasto(sesion, ejercicio, factura, gasto=destino)
        res.facturas_movidas.append(f"{etiqueta}: {cuenta_actual} → {destino.codigo} ({categoria.nombre})")
    if actualizar_fichas:
        _actualizar_fichas(sesion, empresa_id, categorias, cuentas, res)
    sesion.flush()
    return res


def _actualizar_fichas(sesion: Session, empresa_id: int, categorias: list[CategoriaGasto], cuentas: dict[str, Cuenta], res: ResultadoReclasificacion) -> None:
    """La cuenta de gasto por defecto de cada proveedor: la de su categoría si todas sus facturas (de todos los años) son de la misma."""
    por_id = {c.id: c for c in categorias}
    cats_de_tercero: dict[int, set[int | None]] = defaultdict(set)
    filas = sesion.execute(
        select(Factura.tercero_id, Factura.categoria_gasto_id, Cuenta.codigo).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id)
        .join(Cuenta, Cuenta.id == Factura.cuenta_contrapartida_id, isouter=True).where(Ejercicio.empresa_id == empresa_id, Factura.sentido == "R", Factura.tercero_id.is_not(None))
    ).all()
    for tercero_id, categoria_id, cuenta in filas:
        cat = por_id.get(categoria_id) or _categoria_por_cuenta(categorias, cuenta)
        cats_de_tercero[tercero_id].add(cat.id if cat else None)
    for tercero in sesion.scalars(select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.clase == "P")):
        ids = cats_de_tercero.get(tercero.id)
        if not ids:
            continue
        if len(ids) > 1 or None in ids:
            res.fichas_varias.append(f"{tercero.nombre}: {', '.join(sorted(por_id[i].nombre for i in ids if i))}")
            continue
        categoria = por_id[next(iter(ids))]
        if categoria.tipo != "gasto":  # una inversión no se pone por defecto en la ficha: se decide factura a factura
            continue
        destino = cuentas.get(categoria.cuenta_destino or "")
        if destino is not None and tercero.cuenta_gasto_id != destino.id:
            res.fichas.append(f"{tercero.nombre} → {destino.codigo} ({categoria.nombre})")
            tercero.cuenta_gasto_id = destino.id


def regularizar_saldo(sesion: Session, empresa_id: int, ejercicio: Ejercicio, *, prefijo: str, a: str, fecha, concepto: str) -> list[str]:
    """Asiento general que lleva a gasto (`a`) el saldo de las cuentas que empiezan por `prefijo` (p. ej. el gasóleo que quedó en existencias, 321). Devuelve lo que hace. No hace commit."""
    from conta_pridalac.servicios.asientos import LineaAsiento, grabar_asiento
    from conta_pridalac.servicios.extras import siguiente_numero

    if ejercicio.cerrado:
        raise ErrorContable(f"El ejercicio {ejercicio.anio} está cerrado")
    filas = sesion.execute(
        select(Cuenta.codigo, NETO).join(Apunte, Apunte.cuenta_id == Cuenta.id).join(Asiento, Asiento.id == Apunte.asiento_id)
        .where(Cuenta.empresa_id == empresa_id, Cuenta.codigo.like(f"{prefijo}%"), Asiento.ejercicio_id == ejercicio.id, func.coalesce(Asiento.subtipo, "").notin_(("R", "Z"))).group_by(Cuenta.codigo)
    ).all()
    saldos = [(c, Decimal(s)) for c, s in filas if s]
    if not saldos:
        return [f"Las cuentas {prefijo}* no tienen saldo: no hace falta asiento"]
    total = sum((s for _, s in saldos), Decimal("0"))
    lineas = [LineaAsiento(a, total)] + [LineaAsiento(c, -s) for c, s in saldos]
    numero = siguiente_numero(sesion, ejercicio)
    grabar_asiento(sesion, ejercicio, tipo=4, numero=numero, fecha=fecha, lineas=lineas, concepto=concepto, subtipo="M")
    return [f"Asiento 4.{numero} ({fecha:%d/%m/%Y}): {total} € de {', '.join(c for c, _ in saldos)} → {a}"]
