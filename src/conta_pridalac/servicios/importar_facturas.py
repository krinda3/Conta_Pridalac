"""Importación de facturas desde el Excel de conciliación de Verifactu (facturas recibidas y emitidas con su pago o cobro).

El Excel trae una fila por factura: proveedor o cliente y su NIF, fechas, número, base y cuota (hasta tres tipos de IVA), total, la ruta del
PDF y, si ya está pagada o cobrada, la fecha, el concepto y la subcuenta del banco. La importación tiene dos pasos:

1. `leer_excel` + `planificar` no tocan la base de datos: dicen, fila a fila, qué se haría (factura nueva, proveedor nuevo, duplicada…) y qué
   impide importarla.
2. `importar` graba las filas que no tienen errores —factura, asiento, vencimiento, movimiento de banco con su pago y el PDF— en una sola transacción.

Reglas:
- El tercero se busca por NIF (sin espacios ni guiones) y, si no, por nombre; si no existe, se crea con su subcuenta y la de gasto o ingreso elegida.
- Una factura con el mismo tercero y el mismo número que otra ya grabada, o repetida en el propio Excel, es **duplicada** y no se importa.
- Lo que el total tiene de más sobre «base + IVA» (suplidos, tasas, importes exentos) se añade como línea de IVA al 0 %; de menos, es un error.
- Si hay fecha de pago, se crea un único vencimiento a esa fecha y un movimiento del banco de la subcuenta indicada que lo salda.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Banco, Cuenta, Ejercicio, Factura, FacturaIva, TipoIva, Tercero
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import adjuntos as svc_adjuntos
from conta_pridalac.servicios import cuentas as svc_cuentas
from conta_pridalac.servicios.facturas import grabar_factura
from conta_pridalac.servicios.tesoreria import LineaPago, registrar_movimiento
from conta_pridalac.servicios.vencimientos import PlazoVencimiento, definir_vencimientos

CERO = Decimal("0.00")
CUENTA_IVA_POR_DEFECTO = {"R": "47200000", "E": "47700000"}
CUENTA_GASTO_POR_DEFECTO = {"R": "62900000", "E": "70500000"}

# nombre de columna (sin tildes, espacios ni signos) → campo
ALIAS = {
    "nombrearchivo": "archivo", "empresa": "nombre", "proveedor": "nombre", "cliente": "nombre", "clientenombre": "nombre", "cif": "nif", "nif": "nif", "clientenif": "nif",
    "fechafactura": "fecha_factura", "fecha": "fecha_factura", "numfactura": "numero", "numerofactura": "numero", "nfactura": "numero",
    "baseimponible": "base", "base": "base", "iva": "pct1", "montoiva": "cuota1", "cuotaiva": "cuota1", "montototal": "total", "total": "total", "rutacompleta": "ruta",
    "fechacontable": "fecha_contable", "iva2": "pct2", "montoiva2": "cuota2", "iva3": "pct3", "montoiva3": "cuota3",
    "fechapago": "fecha_pago", "fechacobro": "fecha_pago", "conceptopago": "concepto", "conceptocobro": "concepto",
    "subcuentadepago": "subcuenta", "subcuentadecobro": "subcuenta", "subcuentadepagocobro": "subcuenta", "subcuenta": "subcuenta", "descsubcuenta": "desc_subcuenta",
}
OBLIGATORIAS = ("nombre", "numero", "total", "fecha_factura")


@dataclass
class FilaExcel:
    fila: int  # número de fila en el Excel (la 1 es la cabecera)
    nombre: str = ""
    nif: str = ""
    fecha_factura: date | None = None
    fecha_contable: date | None = None
    numero: str = ""
    lineas: list[tuple[Decimal, Decimal, Decimal]] = field(default_factory=list)  # (base, % IVA, cuota)
    total: Decimal | None = None
    ruta: str | None = ""  # None si el Excel no tiene columna de PDF (el de facturas emitidas)
    fecha_pago: date | None = None
    concepto: str = ""
    subcuenta: str = ""
    problemas: list[str] = field(default_factory=list)  # lo que no se ha podido leer de la fila
    tercero_id: int | None = None  # el proveedor o cliente ya elegido (la conciliación del trimestre): no se busca por NIF ni por nombre
    cuenta_gasto_id: int | None = None  # la subcuenta de gasto o ingreso elegida, en lugar de la del tercero


def clave_de_tercero(f: FilaExcel) -> str:
    """Identifica al tercero de una fila: su NIF normalizado o, si no lo tiene, su nombre."""
    return normalizar_nif(f.nif) or _clave(f.nombre)


@dataclass
class PlanFila:
    fila: FilaExcel
    estado: str = "nueva"  # nueva · duplicada · error
    tercero: Tercero | None = None
    crear_tercero: bool = False
    lineas: list[FacturaIva] = field(default_factory=list)  # ya con sus cuentas; se convierten al grabar
    banco: Banco | None = None
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    detalle: str = ""  # qué la hace duplicada

    @property
    def importable(self) -> bool:
        return self.estado == "nueva" and not self.errores


@dataclass
class ResultadoImportacion:
    importadas: list[tuple[int, int]] = field(default_factory=list)  # (fila del Excel, nº de factura)
    movimientos: int = 0
    terceros_nuevos: list[str] = field(default_factory=list)
    pdfs: int = 0
    avisos: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------------------------ lectura


def _clave(texto) -> str:
    s = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def normalizar_nif(nif) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(nif or "").upper())


def _numero(valor) -> Decimal | None:
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, (int, float, Decimal)):
        return dinero(valor if not isinstance(valor, float) else round(valor, 4))
    texto = str(valor).strip().replace("€", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return dinero(Decimal(texto))
    except InvalidOperation:
        raise ValueError(f"«{valor}» no es un importe") from None


def _fecha(valor) -> date | None:
    if valor is None or str(valor).strip() == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"«{valor}» no es una fecha (se espera DD/MM/AAAA)")


def leer_excel(contenido: bytes) -> list[FilaExcel]:
    """Lee la primera hoja del Excel. Las columnas se reconocen por su nombre; cada fila trae lo leído y los problemas de lectura."""
    try:
        libro = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    except Exception as ex:  # fichero que no es un .xlsx
        raise ErrorContable(f"No se puede abrir el Excel: {ex}") from None
    hoja = libro.worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    cabecera = next(filas, None)
    if cabecera is None:
        raise ErrorContable("El Excel está vacío")
    columnas: dict[str, int] = {}
    for i, titulo in enumerate(cabecera):
        campo = ALIAS.get(_clave(titulo))
        if campo and campo not in columnas:
            columnas[campo] = i
    faltan = [c for c in OBLIGATORIAS if c not in columnas]
    if faltan:
        raise ErrorContable("Al Excel le faltan columnas: " + ", ".join({"nombre": "Empresa", "numero": "Num. factura", "total": "Monto total", "fecha_factura": "Fecha factura"}[c] for c in faltan))

    def celda(r, campo):
        i = columnas.get(campo)
        return r[i] if i is not None and i < len(r) else None

    resultado = []
    for n, r in enumerate(filas, start=2):
        if r is None or all(v is None or str(v).strip() == "" for v in r):
            continue
        f = FilaExcel(fila=n, nombre=str(celda(r, "nombre") or "").strip(), nif=str(celda(r, "nif") or "").strip(), numero=str(celda(r, "numero") or "").strip(),
                      ruta=(str(celda(r, "ruta") or "").strip() if "ruta" in columnas else None), concepto=str(celda(r, "concepto") or "").strip(), subcuenta=str(celda(r, "subcuenta") or "").strip().split(".")[0])
        for campo in ("fecha_factura", "fecha_contable", "fecha_pago"):
            try:
                setattr(f, campo, _fecha(celda(r, campo)))
            except ValueError as ex:
                f.problemas.append(f"{campo.replace('_', ' ')}: {ex}")
        try:
            f.total = _numero(celda(r, "total"))
            base, pct1, cuota1 = _numero(celda(r, "base")), _numero(celda(r, "pct1")), _numero(celda(r, "cuota1"))
            if base is not None:
                f.lineas.append((base, pct1 or CERO, cuota1 or CERO))
            for n_linea in ("2", "3"):  # el Excel sólo trae la cuota y el %; la base se deduce
                pct, cuota = _numero(celda(r, f"pct{n_linea}")), _numero(celda(r, f"cuota{n_linea}"))
                if cuota is not None and cuota != 0 and pct:
                    f.lineas.append(((cuota * 100 / pct).quantize(Decimal("0.01")), pct, cuota))
        except ValueError as ex:
            f.problemas.append(str(ex))
        resultado.append(f)
    return resultado


# ------------------------------------------------------------------------------------------------ plan


NIF_REAL = re.compile(r"^([A-Z]\d{7}[A-Z0-9]|\d{8}[A-Z]|[XYZ]\d{7}[A-Z])$")  # un NIF, CIF o NIE de verdad; «VARIOSTAXI» o «MANUTENCION» son genéricos


def _palabras(texto: str) -> set[str]:
    sin = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]{4,}", sin) if w not in {"s", "sociedad", "limitada", "espana", "anonima"}}


def _tercero_por_nif_o_nombre(sesion: Session, empresa_id: int, clase: str, nif: str, nombre: str) -> tuple[Tercero | None, str | None]:
    """Busca el tercero por NIF y, si no, por nombre. Devuelve también un aviso cuando la coincidencia no es segura:
    varios terceros con el mismo NIF (se elige el de nombre más parecido) o un NIF de verdad cuyo tercero no se parece al nombre del Excel."""
    terceros = list(sesion.scalars(select(Tercero).where(Tercero.empresa_id == empresa_id, Tercero.clase == clase)))
    nif_n = normalizar_nif(nif)
    candidatos = [t for t in terceros if nif_n and normalizar_nif(t.nif) == nif_n]
    if candidatos:
        palabras = _palabras(nombre)
        elegido = max(candidatos, key=lambda t: (_clave(t.nombre) == _clave(nombre), len(palabras & _palabras(t.nombre))))
        aviso = None
        if NIF_REAL.match(nif_n) and nombre and not (palabras & _palabras(elegido.nombre)) and _clave(elegido.nombre) != _clave(nombre):
            aviso = f"El NIF {nif_n} es de «{elegido.nombre}» pero el Excel dice «{nombre}»: revise que sea el mismo {'proveedor' if clase == 'P' else 'cliente'}"
        elif len(candidatos) > 1:
            aviso = f"Hay {len(candidatos)} terceros con el NIF {nif_n}: se usa «{elegido.nombre}»"
        return elegido, aviso
    nombre_n = _clave(nombre)
    if nombre_n:
        for t in terceros:
            if _clave(t.nombre) == nombre_n:
                return t, None
    return None, None


def buscar_duplicada(sesion: Session, empresa_id: int, sentido: str, tercero_id: int | None, numero: str) -> Factura | None:
    """Factura ya grabada (de cualquier ejercicio de la empresa) con el mismo tercero y el mismo número de factura."""
    if tercero_id is None or not numero.strip():
        return None
    return sesion.scalars(
        select(Factura).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(
            Ejercicio.empresa_id == empresa_id, Factura.sentido == sentido, Factura.tercero_id == tercero_id, func.upper(func.trim(Factura.numero_factura)) == numero.strip().upper()
        )
    ).first()


def buscar_parecida(sesion: Session, empresa_id: int, sentido: str, numero: str, total: Decimal | None) -> Factura | None:
    """Factura de cualquier tercero con el mismo número y el mismo total: casi seguro es la misma con el tercero mal puesto (p. ej. un NIF equivocado)."""
    if total is None or not numero.strip():
        return None
    return sesion.scalars(
        select(Factura).join(Ejercicio, Ejercicio.id == Factura.ejercicio_id).where(
            Ejercicio.empresa_id == empresa_id, Factura.sentido == sentido, func.upper(func.trim(Factura.numero_factura)) == numero.strip().upper(), Factura.total == total
        )
    ).first()


def _gasto_por_defecto(sesion: Session, empresa_id: int, sentido: str) -> str:
    """La subcuenta de gasto (o ingreso) que se usa si el tercero no tiene una: la del PGC con los dígitos de la empresa."""
    return svc_cuentas.cuenta_estandar(CUENTA_GASTO_POR_DEFECTO[sentido], svc_cuentas.digitos_de(sesion, empresa_id))


def _cuenta_de_iva(sesion: Session, empresa_id: int, sentido: str, pct: Decimal) -> Cuenta | None:
    tipo = sesion.scalars(select(TipoIva).where(TipoIva.empresa_id == empresa_id, TipoIva.sentido == sentido, TipoIva.pct_iva == pct, TipoIva.inactivo.is_(False))).first()
    if tipo is not None and tipo.cuenta_iva is not None:
        return tipo.cuenta_iva
    return sesion.scalars(select(Cuenta).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == svc_cuentas.cuenta_estandar(CUENTA_IVA_POR_DEFECTO[sentido], svc_cuentas.digitos_de(sesion, empresa_id)))).first()


def planificar(sesion: Session, ejercicio: Ejercicio, sentido: str, filas: list[FilaExcel]) -> list[PlanFila]:
    """Decide qué pasaría con cada fila sin grabar nada."""
    empresa_id = ejercicio.empresa_id
    clase = "P" if sentido == "R" else "C"
    bancos = {b.cuenta.codigo: b for b in sesion.scalars(select(Banco).where(Banco.empresa_id == empresa_id, Banco.clase == "B")) if b.cuenta is not None}
    vistas: set[tuple[str, str]] = set()
    planes = []
    for f in filas:
        p = PlanFila(f)
        planes.append(p)
        p.errores += f.problemas
        if not f.nombre:
            p.errores.append("Falta el nombre del proveedor" if sentido == "R" else "Falta el nombre del cliente")
        if not f.numero:
            p.errores.append("Falta el número de factura")
        if f.total is None:
            p.errores.append("Falta el importe total")
        if f.fecha_factura is None and not any("fecha factura" in x for x in f.problemas):
            p.errores.append("Falta la fecha de la factura")
        contable = f.fecha_contable or f.fecha_factura
        if contable is not None and not (ejercicio.fecha_inicio <= contable <= ejercicio.fecha_fin):
            p.errores.append(f"La fecha contable {contable:%d/%m/%Y} no es del ejercicio {ejercicio.anio}")
        if contable is not None and ejercicio.cerrado:
            p.errores.append(f"El ejercicio {ejercicio.anio} está cerrado")
        if f.fecha_pago is not None and not (ejercicio.fecha_inicio <= f.fecha_pago <= ejercicio.fecha_fin):
            p.errores.append(f"La fecha de pago {f.fecha_pago:%d/%m/%Y} no es del ejercicio {ejercicio.anio}")
        # --- tercero
        if f.tercero_id is not None:
            p.tercero, aviso_tercero = sesion.get(Tercero, f.tercero_id), None
        else:
            p.tercero, aviso_tercero = _tercero_por_nif_o_nombre(sesion, empresa_id, clase, f.nif, f.nombre) if (f.nombre or f.nif) else (None, None)
        if aviso_tercero:
            p.avisos.append(aviso_tercero)
        if p.tercero is None and f.nombre:
            p.crear_tercero = True
            p.avisos.append(f"Se creará el {'proveedor' if sentido == 'R' else 'cliente'} «{f.nombre}»" + (f" ({f.nif})" if f.nif else "") + " con su subcuenta")
        elif p.tercero is not None and p.tercero.cuenta_id is None:
            p.errores.append(f"«{p.tercero.nombre}» no tiene subcuenta contable")
        elif p.tercero is not None and p.tercero.cuenta_gasto_id is None:
            p.avisos.append(f"«{p.tercero.nombre}» no tiene subcuenta de {'gasto' if sentido == 'R' else 'ingreso'}: se usará {_gasto_por_defecto(sesion, ejercicio.empresa_id, sentido)}")
        # --- duplicadas
        clave = (normalizar_nif(f.nif) or _clave(f.nombre), f.numero.strip().upper())
        existente = buscar_duplicada(sesion, empresa_id, sentido, p.tercero.id if p.tercero else None, f.numero)
        parecida = None if existente is not None else buscar_parecida(sesion, empresa_id, sentido, f.numero, f.total)
        if existente is not None:
            p.estado, p.detalle = "duplicada", f"Ya existe la factura {'recibida' if sentido == 'R' else 'emitida'} nº {existente.numero} de {existente.fecha_contable:%d/%m/%Y}"
        elif parecida is not None:
            quien = parecida.tercero.nombre if parecida.tercero is not None else "otro tercero"
            p.estado, p.detalle = "duplicada", (f"Parece la misma que la {'recibida' if sentido == 'R' else 'emitida'} nº {parecida.numero} de «{quien}»: mismo número ({f.numero}) y mismo importe ({f.total}). "
                                                f"Si no lo es, importe esa fila con otro número")
        elif clave in vistas and f.numero:
            p.estado, p.detalle = "duplicada", "Repetida en este mismo Excel"
        vistas.add(clave)
        # --- importes
        suma = CERO
        for base, pct, cuota in f.lineas:
            cuenta = _cuenta_de_iva(sesion, empresa_id, sentido, pct) if pct != 0 else None
            if pct != 0 and cuenta is None:
                p.errores.append(f"No hay subcuenta de IVA para el {pct} %")
                continue
            p.lineas.append(FacturaIva(base=base, pct_iva=pct, cuota_iva=cuota, cuenta_iva_id=cuenta.id if cuenta else None))
            suma += base + cuota
        if not f.lineas:
            p.errores.append("La factura no trae base imponible")
        if f.total is not None and f.lineas:
            diferencia = f.total - suma
            if abs(diferencia) <= Decimal("0.02") and diferencia != 0:  # redondeo de céntimos: se absorbe en la base
                b, pc, cu = f.lineas[0]
                p.lineas[0].base = b + diferencia
                p.avisos.append(f"Diferencia de {diferencia} € de redondeo ajustada en la base")
            elif diferencia > 0:
                p.lineas.append(FacturaIva(base=diferencia, pct_iva=CERO, cuota_iva=CERO))
                p.avisos.append(f"El total supera a base + IVA en {diferencia} €: se añade como línea sin IVA (suplido, tasa o importe exento)")
            elif diferencia < 0:
                p.errores.append(f"El total ({f.total}) es menor que base + IVA ({suma})")
        # --- pago o cobro
        if f.fecha_pago is not None or f.subcuenta:
            if f.fecha_pago is None:
                p.errores.append("Hay subcuenta de pago pero falta la fecha de pago")
            elif not f.subcuenta:
                p.errores.append("Hay fecha de pago pero falta la subcuenta del banco")
            else:
                p.banco = bancos.get(f.subcuenta)
                if p.banco is None:
                    p.errores.append(f"La subcuenta {f.subcuenta} no es ningún banco de la empresa")
        # --- PDF
        if f.ruta and not Path(f.ruta).is_file():
            p.avisos.append("No se encuentra el PDF: se importa la factura sin justificante")
        elif f.ruta == "":
            p.avisos.append("La fila no trae ruta de PDF")
        if p.estado == "duplicada":
            p.errores = []
    return planes


# ------------------------------------------------------------------------------------------------ importación


def importar(
    sesion: Session, almacen, ejercicio: Ejercicio, sentido: str, planes: list[PlanFila], *, cuentas_de_gasto: dict[str, str] | None = None, origen: str = "Excel"
) -> ResultadoImportacion:
    """Graba las filas importables. No hace commit: si algo falla lanza la excepción y quien llama debe hacer rollback (todo o nada).

    `cuentas_de_gasto`: para los terceros nuevos, `{NIF normalizado o nombre: subcuenta de gasto o ingreso}`.
    """
    clase = "P" if sentido == "R" else "C"
    cuentas_de_gasto = cuentas_de_gasto or {}
    res = ResultadoImportacion()
    por_orden = sorted((p for p in planes if p.importable), key=lambda p: (p.fila.fecha_contable or p.fila.fecha_factura, p.fila.fecha_factura, p.fila.fila))
    grupo = _grupo_de_terceros(sesion, ejercicio.empresa_id, clase)
    creados: dict[str, Tercero] = {}
    for p in por_orden:
        f = p.fila
        tercero = p.tercero
        if tercero is None:
            clave = clave_de_tercero(f)
            tercero = creados.get(clave)
            if tercero is None:
                elegida = sesion.get(Cuenta, f.cuenta_gasto_id).codigo if f.cuenta_gasto_id else None
                gasto = cuentas_de_gasto.get(clave) or elegida or _gasto_por_defecto(sesion, ejercicio.empresa_id, sentido)
                tercero = svc_cuentas.crear_tercero(sesion, ejercicio.empresa_id, clase, f.nombre.strip().upper(), nif=normalizar_nif(f.nif) or None, grupo_cuenta=grupo, cuenta_gasto=gasto)
                creados[clave] = tercero
                res.terceros_nuevos.append(f"{tercero.nombre} ({sesion.get(Cuenta, tercero.cuenta_id).codigo})")
        contra = f.cuenta_gasto_id or tercero.cuenta_gasto_id or _id_de_cuenta(sesion, ejercicio.empresa_id, _gasto_por_defecto(sesion, ejercicio.empresa_id, sentido))
        if contra is None:
            raise ErrorContable(f"Fila {f.fila}: no hay subcuenta de {'gasto' if sentido == 'R' else 'ingreso'} para «{tercero.nombre}»")
        factura = Factura(
            sentido=sentido, fecha_contable=f.fecha_contable or f.fecha_factura, fecha_factura=f.fecha_factura, numero_factura=f.numero[:40], tercero_id=tercero.id,
            cuenta_tercero_id=tercero.cuenta_id, cuenta_contrapartida_id=contra, total=f.total, notas=f"Importada de {origen} (fila {f.fila})",
            ivas=[FacturaIva(base=l.base, pct_iva=l.pct_iva, cuota_iva=l.cuota_iva, cuenta_iva_id=l.cuenta_iva_id) for l in p.lineas],
        )
        try:
            grabar_factura(sesion, ejercicio, factura)
        except ErrorContable as ex:
            raise ErrorContable(f"Fila {f.fila}: {ex}") from None
        fecha_vto = f.fecha_pago or f.fecha_factura or factura.fecha_contable
        vencimientos = definir_vencimientos(sesion, ejercicio, factura, [PlazoVencimiento(importe=factura.total, fecha=fecha_vto)])
        if p.banco is not None:
            signo = -1 if sentido == "R" else 1
            registrar_movimiento(sesion, ejercicio, p.banco, f.fecha_pago, [LineaPago(importe=signo * factura.total, vencimiento=vencimientos[0])], texto=f.concepto)
            res.movimientos += 1
        if f.ruta and Path(f.ruta).is_file():
            try:
                svc_adjuntos.adjuntar(sesion, almacen, ejercicio, factura, f.ruta)
                res.pdfs += 1
            except ErrorContable as ex:
                res.avisos.append(f"Fila {f.fila}: {ex}")
        res.importadas.append((f.fila, factura.numero))
    return res


def _id_de_cuenta(sesion: Session, empresa_id: int, codigo: str) -> int | None:
    return sesion.scalar(select(Cuenta.id).where(Cuenta.empresa_id == empresa_id, Cuenta.codigo == codigo))


def _grupo_de_terceros(sesion: Session, empresa_id: int, clase: str) -> str:
    """El grupo de 3 dígitos (400, 410, 430…) que más usan los terceros de esa clase: ahí se crean las subcuentas nuevas."""
    cuentas = sesion.scalars(select(Cuenta.codigo).join(Tercero, Tercero.cuenta_id == Cuenta.id).where(Tercero.empresa_id == empresa_id, Tercero.clase == clase)).all()
    cuenta = {}
    for c in cuentas:
        cuenta[c[:3]] = cuenta.get(c[:3], 0) + 1
    return max(cuenta, key=cuenta.get) if cuenta else svc_cuentas.GRUPO_POR_DEFECTO[clase]
