"""Cargador de las tablas DBF de Gestión MGD al esquema nuevo.

Alcance H0: empresa y ejercicio, plan de cuentas, terceros, asientos y apuntes (el Diario), facturas recibidas y
emitidas con su IVA y sus ajustes, parámetros y tesorería (Tipovtos, Bancos, Vtos, Movbanco, Pagos). Quedan para
el Hito 1: bienes de inversión (Lbi) y adjuntos PDF.

El Diario se carga **tal cual está** (es lo contabilizado); la regeneración desde los documentos es trabajo del H1.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from dbfread import DBF
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    Adjunto,
    BANCO_COMPENSACION,
    BANCO_NORMAL,
    BANCO_REMESAS,
    TIPO_AUTOMATICO,
    TIPO_EMITIDAS,
    TIPO_GENERAL,
    TIPO_RECIBIDAS,
    TIPO_TESORERIA,
    Apunte,
    Asiento,
    AmortizacionPeriodo,
    Banco,
    BienInversion,
    Cuenta,
    Ejercicio,
    Empresa,
    Factura,
    FacturaAjuste,
    FacturaIva,
    FormaPago,
    MovimientoBanco,
    Pago,
    Parametro,
    Plantilla,
    PlantillaLinea,
    Tercero,
    TipoIva,
    Vencimiento,
)
from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.plantillas import leer_contenido
from conta_pridalac.migracion.cuentas import CERO_TRAS_POR_EMPRESA
from conta_pridalac.migracion.cuentas import ajustar_cuenta


@dataclass
class ResumenCarga:
    empresa_id: int = 0
    ejercicio_id: int = 0
    cuentas: int = 0
    terceros: int = 0
    asientos: int = 0
    apuntes: int = 0
    facturas: int = 0
    bancos: int = 0
    vencimientos: int = 0
    movimientos: int = 0
    pagos: int = 0
    bienes: int = 0
    plantillas: int = 0
    tipos_iva: int = 0
    cuentas_de_catalogo_inexistentes: list[str] = field(default_factory=list)  # citadas en Tipoiva y no creadas en el plan
    adjuntos: int = 0
    adjuntos_faltantes: list[str] = field(default_factory=list)  # referenciados en Etidat pero sin fichero
    adjuntos_huerfanos: list[str] = field(default_factory=list)  # ficheros de justificantes que nadie referencia
    avisos: list[str] = field(default_factory=list)


def leer_dbf(carpeta: str | Path, tabla: str) -> list[dict]:
    """Lee una tabla DBF/FPT de MGD (codificación Latin-1; los memos ausentes no son error)."""
    ruta = Path(carpeta) / f"{tabla}.dbf"
    if not ruta.exists():
        ruta = Path(carpeta) / f"{tabla}.DBF"
    return list(DBF(str(ruta), encoding="latin-1", ignore_missing_memofile=True))


def tipo_asiento(tipo_mgd: str, tpasiento: str | None) -> int:
    """TIPO/TPASIENTO de MGD → tipo de asiento nuevo (1 emitidas, 2 recibidas, 3 tesorería, 4 general, 9 automático)."""
    if tipo_mgd == "E":
        return TIPO_EMITIDAS
    if tipo_mgd == "R":
        return TIPO_RECIBIDAS
    if tipo_mgd == "B":
        return TIPO_TESORERIA
    if tipo_mgd == "X":
        return TIPO_AUTOMATICO if (tpasiento or "").strip() in ("A", "P") else TIPO_GENERAL
    raise ValueError(f"Tipo de asiento MGD desconocido: {tipo_mgd!r}")


def _texto(v) -> str:
    return (v or "").strip()


_PATRON_JUSTIFICANTE = re.compile(r"^\d{3}_[A-Z]_\d{5}_.+\.(pdf|jpg|jpeg)$", re.IGNORECASE)


def _justificantes_por_documento(filas: list[dict]) -> dict[tuple[str, int], list[str]]:
    """Recompone la lista de ficheros de cada documento (`clJustificantes.LeeDatos`, D_Comun.prg:13927).

    MGD guarda la lista separada por `;` y troceada en bloques de 64 caracteres, uno por fila de `Etidat`. Al leer, cada
    bloque se recorta por la derecha (`Trim`) y se concatenan. Se replica tal cual: si un bloque termina en espacio,
    MGD también lo pierde y no encuentra ese fichero.
    """
    cadenas: dict[tuple[str, int], str] = defaultdict(str)
    for fila in filas:
        if _texto(fila["CLAVE"]) != "?":
            continue
        cadenas[(fila["TIPO"], fila["NUMERO"])] += (fila["TEXTO"] or "").rstrip()
    return {k: [n for n in v.split(";") if n.strip()] for k, v in cadenas.items()}


def _mime_de(nombre: str) -> str | None:
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    return {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext)


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _numero_mgd(texto: str) -> Decimal:
    """`1.234,56` → Decimal('1234.56') (formato de los cuadros guardados en Lbi.CUADRO)."""
    return dinero(texto.strip().replace(".", "").replace(",", "."))


def _fecha_mgd(texto: str) -> date:
    """`15/04/14` → 2014-04-15. Año de 2 dígitos: se toma el siglo XXI (válido hasta 2099)."""
    dia, mes, anio = texto.strip().split("/")
    return date(2000 + int(anio) if len(anio) == 2 else int(anio), int(mes), int(dia))


def parsear_cuadro_mgd(texto: str | None) -> list[tuple[int, date, date, Decimal, str, str]]:
    """Cuadro de amortización guardado en `Lbi.CUADRO`: una línea por periodo, campos separados por `·`.

    `ejercicio · desde · hasta · previsto · ref · valor`; `ref` = `M` (importe amortizado, a mano) o `X` (nº del
    asiento extra que lo amortizó).
    """
    filas = []
    for linea in (texto or "").replace("\r", "").split("\n"):
        if not linea.strip():
            continue
        ejercicio, desde, hasta, previsto, ref, valor = linea.split("·")
        filas.append((int(ejercicio), _fecha_mgd(desde), _fecha_mgd(hasta), _numero_mgd(previsto), ref.strip(), valor))
    return filas


def digitos_del_plan(carpeta: str | Path) -> int:
    """Dígitos de las subcuentas de una copia de MGD: la longitud mayor de los códigos de su plan de cuentas (MGD los guarda todos con la misma)."""
    longitudes = [len((f["CUENTA"] or "").strip()) for f in leer_dbf(carpeta, "Cuentas")]
    return max([n for n in longitudes if n] or [7])


@dataclass
class CopiaMgd:
    """Lo que se puede saber de una copia de MGD antes de cargarla (para proponer los datos de la empresa nueva)."""

    anio: int | None  # el año de la mayoría de los apuntes del Diario
    codigo_empresa: int | None  # el número de empresa de MGD, del prefijo `011_` de sus justificantes
    nombre: str | None  # `ID_NOMBRE` de los parámetros (o el de `Empresas.dbf`, si lo tiene)
    digitos_cuenta: int
    asientos: int
    justificantes: int


def explorar_copia(carpeta: str | Path) -> CopiaMgd:
    """Mira una copia de MGD (la carpeta con sus `.dbf`) sin cargar nada. Falla si no es una copia: no tiene `Diario.dbf` y `Cuentas.dbf`."""
    carpeta = Path(carpeta)
    for tabla in ("Diario", "Cuentas"):
        if not ((carpeta / f"{tabla}.dbf").exists() or (carpeta / f"{tabla}.DBF").exists()):
            raise ValueError(f"No parece una copia de MGD: falta {tabla}.dbf en {carpeta}")
    anios = Counter(f["FECHA"].year for f in leer_dbf(carpeta, "Diario") if f.get("FECHA"))
    codigos = Counter(int(m.group(1)) for n in carpeta.iterdir() if (m := re.match(r"(\d{3})_[A-Za-z]_", n.name)))
    nombre = None
    try:
        nombre = next((_texto(f["TEXTO"]) for f in leer_dbf(carpeta, "Param") if _texto(f["ETIQUETA"]) == "ID_NOMBRE"), None)
        empresas = [_texto(f["NOMBRE"]) for f in leer_dbf(carpeta, "Empresas") if _texto(f["NOMBRE"])]
        nombre = (empresas[0] if empresas else None) or nombre
    except (OSError, KeyError, ValueError):
        pass
    justificantes = sum(1 for n in carpeta.iterdir() if n.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"))
    return CopiaMgd(
        anio=anios.most_common(1)[0][0] if anios else None, codigo_empresa=codigos.most_common(1)[0][0] if codigos else None, nombre=nombre or None,
        digitos_cuenta=digitos_del_plan(carpeta), asientos=len({f["ASIENTO"] for f in leer_dbf(carpeta, "Diario")}), justificantes=justificantes,
    )


def cargar_mgd(
    sesion: Session,
    carpeta: str | Path,
    *,
    codigo_empresa: int,
    nombre_empresa: str,
    anio: int,
    nif: str | None = None,
    carpeta_justificantes: str | Path | None = None,
    cero_tras: int | None = None,
    digitos_cuenta: int | None = None,
) -> ResumenCarga:
    """Carga una empresa-ejercicio de MGD en la sesión (no hace commit).

    `carpeta_justificantes`: dónde están los PDF/JPG referenciados en `Etidat` (en MGD, `<base>\\Justificantes`; en las
    copias de seguridad suelen estar junto a las tablas, que es el valor por defecto).
    `cero_tras`: dígito tras el cual se inserta el `0` al pasar las cuentas a 8 dígitos. Por defecto el de la empresa
    (`CERO_TRAS_POR_EMPRESA`: 4 en Empresa A, 3 en Empresa B; 3 si la empresa no está en la tabla). Ver `migracion/cuentas.py`.
    `digitos_cuenta`: dígitos de las subcuentas de la empresa nueva. Por defecto, 8 en Empresa A y Empresa B (las que pasaron al programa anterior) y, en
    cualquier otra empresa, los mismos que tiene su plan de MGD (`digitos_del_plan`): se migra con lo que hay, sin inventar cuentas.
    """
    tras = cero_tras or CERO_TRAS_POR_EMPRESA.get(codigo_empresa, 3)
    if digitos_cuenta is None:
        digitos_cuenta = 8 if (cero_tras or codigo_empresa in CERO_TRAS_POR_EMPRESA) else digitos_del_plan(carpeta)

    def cuenta_de_empresa(codigo):
        return ajustar_cuenta(codigo, digitos_cuenta, tras)

    res = ResumenCarga()

    empresa = Empresa(codigo=codigo_empresa, nombre=nombre_empresa, nif=nif, digitos_cuenta=digitos_cuenta)
    ejercicio = Ejercicio(anio=anio, fecha_inicio=date(anio, 1, 1), fecha_fin=date(anio, 12, 31), empresa=empresa)
    sesion.add_all([empresa, ejercicio])
    sesion.flush()
    res.empresa_id, res.ejercicio_id = empresa.id, ejercicio.id

    # --- Plan de cuentas
    cuentas: dict[str, Cuenta] = {}
    for fila in leer_dbf(carpeta, "Cuentas"):
        codigo = cuenta_de_empresa(fila["CUENTA"])
        if not codigo:
            continue
        if codigo in cuentas:  # dos cuentas de MGD que acaban con el mismo código
            res.avisos.append(f"Cuenta {fila['CUENTA'].strip()} de MGD coincide con otra con los dígitos de la empresa ({codigo}); se ignora")
            continue
        cuentas[codigo] = Cuenta(empresa_id=empresa.id, codigo=codigo, nombre=_texto(fila["TEXTO"]))
    sesion.add_all(cuentas.values())
    sesion.flush()
    res.cuentas = len(cuentas)

    def cuenta(c7: str | None) -> Cuenta | None:
        c8 = cuenta_de_empresa(c7)
        if not c8:
            return None
        if c8 not in cuentas:
            res.avisos.append(f"Cuenta {c8} (MGD {c7}) usada pero inexistente en el plan; se crea")
            cuentas[c8] = Cuenta(empresa_id=empresa.id, codigo=c8, nombre="(creada en la migración)")
            sesion.add(cuentas[c8])
            sesion.flush()
        return cuentas[c8]

    # --- Terceros
    terceros: dict[tuple[str, int], Tercero] = {}
    for clase, tabla in (("C", "Clientes"), ("P", "Proveed")):
        for fila in leer_dbf(carpeta, tabla):
            c = cuenta(fila["CUENTA"])
            irpf = cuenta(fila.get("CTAIRPF")) if clase == "P" else None
            t = Tercero(
                empresa_id=empresa.id,
                clase=clase,
                numero_origen=fila["NUMERO"],
                nombre=_texto(fila["NOMBRE"]),
                comercial=_texto(fila["COMERCIAL"]) or None,
                nif=_texto(fila["NIF"]) or None,
                cuenta_id=c.id if c else None,
                cuenta_irpf_id=irpf.id if irpf else None,
                domicilio=_texto(fila.get("DOMICILIO")) or None,
                poblacion=_texto(fila.get("LOCALIDAD")) or None,
                provincia=_texto(fila.get("PROVINCIA")) or None,
                codigo_postal=_texto(fila.get("COD_POSTAL")) or None,
                bic=_texto(fila.get("BIC")) or None,
                observaciones=_texto(fila.get("NOTAS")) or None,
                criterio_caja=_texto(fila.get("CCAJA")).upper() == "S",
            )
            terceros[(clase, fila["NUMERO"])] = t
            sesion.add(t)
    sesion.flush()
    res.terceros = len(terceros)

    # --- Diario → asientos y apuntes (cabecera = línea sin cuenta)
    grupos: dict[tuple, dict] = {}
    orden_aparicion: list[tuple] = []
    for fila in leer_dbf(carpeta, "Diario"):
        clave = (fila["TIPO"], fila["NUMERO"], _texto(fila["MULTI"]))
        if clave not in grupos:
            grupos[clave] = {"cab": None, "lineas": []}
            orden_aparicion.append(clave)
        if _texto(fila["CUENTA"]) == "":
            grupos[clave]["cab"] = fila
        else:
            grupos[clave]["lineas"].append(fila)

    for clave in orden_aparicion:
        tipo_mgd, numero, multi = clave
        g = grupos[clave]
        cab = g["cab"] or (g["lineas"][0] if g["lineas"] else None)
        if cab is None:
            continue
        sub = int(multi) if multi.isdigit() else 0
        asiento = Asiento(
            ejercicio_id=ejercicio.id,
            tipo=tipo_asiento(tipo_mgd, cab["TPASIENTO"]),
            numero=numero,
            sub=sub,
            numero_diario=cab["ASIENTO"] or None,
            fecha=cab["FECHA"],
            concepto="",
            subtipo=_texto(cab["TPASIENTO"]) or None,
        )
        for i, linea in enumerate(g["lineas"], start=1):
            importe = dinero(linea["IMPORTE"])
            asiento.apuntes.append(
                Apunte(
                    orden=i,
                    cuenta_id=cuenta(linea["CUENTA"]).id,
                    debe=importe if importe > 0 else dinero(0),
                    haber=-importe if importe < 0 else dinero(0),
                )
            )
        sesion.add(asiento)
        res.asientos += 1
        res.apuntes += len(asiento.apuntes)
    sesion.flush()

    # --- Facturas (Rec = recibidas, Emi = emitidas) con su IVA y ajustes
    por_clave: dict[tuple[str, int], Factura] = {}
    for sentido, tabla in (("R", "Rec"), ("E", "Emi")):
        for fila in leer_dbf(carpeta, tabla):
            if sentido == "R":
                tercero = terceros.get(("P", fila["PROVEEDOR"]))
                cta_tercero, cta_contra = cuenta(fila["PRCUENTA"]), cuenta(fila["TOCUENTA"])
                num_factura, f_factura = _texto(fila["PRFACTURA"]) or None, fila["PRFECHA"]
            else:
                # CLIENTE negativo = autofactura: el "cliente" es el proveedor -CLIENTE
                cod = fila["CLIENTE"]
                tercero = terceros.get(("P", -cod)) if cod < 0 else terceros.get(("C", cod))
                cta_tercero, cta_contra = cuenta(fila["CLCUENTA"]), cuenta(fila["TOCUENTA"])
                num_factura, f_factura = str(fila["CNUMERO"]), fila["FECHA"]
            factura = Factura(
                ejercicio_id=ejercicio.id,
                sentido=sentido,
                numero=fila["NUMERO"],
                fecha_contable=fila["FECHA"],
                fecha_factura=f_factura or fila["FECHA"],
                numero_factura=num_factura,
                tercero_id=tercero.id if tercero else None,
                cuenta_tercero_id=cta_tercero.id if cta_tercero else None,
                cuenta_contrapartida_id=cta_contra.id if cta_contra else None,
                total=dinero(fila["TOTAL"]),
            )
            sesion.add(factura)
            por_clave[(sentido, fila["NUMERO"])] = factura
    sesion.flush()
    res.facturas = len(por_clave)

    for fila in leer_dbf(carpeta, "Eriva"):
        # Eriva.TIPO: 'S' = IVA soportado (recibidas) · 'R' = repercutido (emitidas)
        sentido = "R" if fila["TIPO"] == "S" else "E"
        factura = por_clave.get((sentido, fila["FACTURA"]))
        if factura is None:
            res.avisos.append(f"Eriva sin factura: tipo {fila['TIPO']} nº {fila['FACTURA']}")
            continue
        c_iva, c_re = cuenta(fila["IVA_CTA"]), cuenta(fila["RE_CTA"])
        factura.ivas.append(
            FacturaIva(
                base=dinero(fila["BASE"]),
                pct_iva=dinero(fila["IVA"]),
                cuota_iva=dinero(fila["IVA_TOTAL"]),
                cuenta_iva_id=c_iva.id if c_iva else None,
                pct_recargo=dinero(fila["RE"]),
                cuota_recargo=dinero(fila["RE_TOTAL"]),
                cuenta_recargo_id=c_re.id if c_re else None,
                deducible=_texto(fila["NODEDU"]) != "S",
                bien_inversion=_texto(fila["BINVERSION"]) == "S",
            )
        )

    for orden, fila in enumerate(leer_dbf(carpeta, "Ajustes"), start=1):
        factura = por_clave.get((fila["TIPO"], fila["NUMERO"]))
        if factura is None:
            res.avisos.append(f"Ajuste sin factura: {fila['TIPO']} {fila['NUMERO']}")
            continue
        factura.ajustes.append(
            FacturaAjuste(
                orden=orden,
                cuenta_id=cuenta(fila["CUENTA"]).id,
                importe=dinero(fila["IMPORTE"]),
                contra=_texto(fila["CONTRA"]),
                cambio_asiento=_texto(fila["CAMBIOAS"]) == "S",
                afecta_iva=_texto(fila["AFECTAIVA"]) == "S",
                declaracion_terceros=_texto(fila["DECLTERC"]) == "S",
            )
        )
    sesion.flush()

    # --- Parámetros de empresa (PTE_APLIC, PYG, IVA_DEBE…). Se guardan todos tal cual.
    # Los parámetros que contienen una cuenta del plan (PTE_APLIC, PYG, IVA_DEBE…) se pasan a 8 dígitos.
    cuentas_mgd = {_texto(f["CUENTA"]) for f in leer_dbf(carpeta, "Cuentas")}
    for fila in leer_dbf(carpeta, "Param"):
        valor = _texto(fila["TEXTO"])
        if valor in cuentas_mgd:
            valor = cuenta_de_empresa(valor)
        sesion.add(Parametro(empresa_id=empresa.id, clave=_texto(fila["ETIQUETA"]), valor=valor))

    # --- Tesorería: formas de pago, bancos, vencimientos, movimientos y pagos
    formas: dict[int, FormaPago] = {}
    for fila in leer_dbf(carpeta, "Tipovtos"):
        formas[fila["NUMERO"]] = FormaPago(
            empresa_id=empresa.id,
            numero_origen=fila["NUMERO"],
            texto=_texto(fila["TEXTO"]),
            por_defecto_clientes=_texto(fila["CLIDEF"]) == "S",
            por_defecto_proveedores=_texto(fila["PROVDEF"]) == "S",
        )
    sesion.add_all(formas.values())

    bancos: dict[int, Banco] = {}
    for fila in leer_dbf(carpeta, "Bancos"):
        c = cuenta(fila["CUENTA"])
        if fila["NUMERO"] in bancos:
            res.avisos.append(f"Banco nº {fila['NUMERO']} duplicado en Bancos ({_texto(fila['NOMBRE'])}); se usa el último")
        bancos[fila["NUMERO"]] = Banco(
            empresa_id=empresa.id,
            numero=fila["NUMERO"],
            clase=BANCO_COMPENSACION if fila["NUMERO"] == -1 else BANCO_NORMAL,
            nombre=_texto(fila["NOMBRE"]),
            sucursal=_texto(fila["SUCURSAL"]) or None,
            iban=_texto(fila["NUMCTA"]) or None,
            bic=_texto(fila["BIC"]) or None,
            cuenta_id=c.id if c else None,
            saldo_inicial=dinero(fila["SALDOINI"]),
        )
    sesion.add_all(bancos.values())
    sesion.flush()

    movimientos_mgd = leer_dbf(carpeta, "Movbanco")
    if any(m["BANCO"] == -3 for m in movimientos_mgd) and -3 not in bancos:
        bancos[-3] = Banco(empresa_id=empresa.id, numero=-3, clase=BANCO_REMESAS, nombre="Remesas de vencimientos")
        sesion.add(bancos[-3])
        sesion.flush()

    # Asientos manuales (extras) por su número de MGD y apuntes de extras (Exapun) por el suyo: los vencimientos de tipo X
    # cuelgan de un apunte concreto (las líneas de la misma cuenta del extra se agrupan en el Diario, así que hay uno por cuenta).
    asientos_x = {
        a.numero: a
        for a in sesion.query(Asiento).filter(Asiento.ejercicio_id == ejercicio.id, Asiento.tipo.in_((TIPO_GENERAL, TIPO_AUTOMATICO)))
    }
    exapun = {f["NUMERO"]: (f["EXTRA"], f["CUENTA"]) for f in leer_dbf(carpeta, "Exapun")}
    vencimientos: dict[int, Vencimiento] = {}
    for fila in leer_dbf(carpeta, "Vtos"):
        tipo, numero_doc = fila["TIPO"], fila["TPNUMERO"]
        c, c_def = cuenta(fila["CUENTA"]), cuenta(fila["CUENTADEF"])
        c_origen, apunte_x = None, None
        if tipo == "X" and numero_doc in exapun:
            extra_num, cuenta_x = exapun[numero_doc]
            c_origen = cuenta(cuenta_x)
            asiento_x = asientos_x.get(extra_num)
            if asiento_x is not None:
                apunte_x = next((ap for ap in asiento_x.apuntes if ap.cuenta_id == c_origen.id), None)
            if apunte_x is None:
                res.avisos.append(f"Vencimiento {fila['NUMERO']}: no se encuentra el apunte del extra {extra_num} ({_texto(cuenta_x)})")
            else:
                numero_doc = extra_num  # en el sistema nuevo el origen es el asiento, no el nº de apunte de MGD (Exapun)
        factura = por_clave.get((tipo, numero_doc)) if tipo in ("E", "R") else None
        if tipo in ("E", "R") and factura is None:
            res.avisos.append(f"Vencimiento {fila['NUMERO']} sin factura {tipo} {numero_doc}")
        vencimientos[fila["NUMERO"]] = Vencimiento(
            ejercicio_id=ejercicio.id,
            numero_origen_mgd=fila["NUMERO"],
            origen_tipo=tipo,
            origen_numero=numero_doc,
            factura=factura,
            apunte=apunte_x,
            fecha=fila["FECHA"],
            importe=dinero(fila["IMPORTE"]),
            cuenta_id=c.id if c else None,
            cuenta_defecto_id=c_def.id if c_def else None,
            cuenta_origen_id=c_origen.id if c_origen else None,
            banco_previsto=bancos.get(fila["PENTIDAD"]),
            forma_pago=formas.get(fila["PTIPO"]),
        )
    sesion.add_all(vencimientos.values())

    movimientos: dict[int, MovimientoBanco] = {}
    for fila in movimientos_mgd:
        movimientos[fila["NUMERO"]] = MovimientoBanco(
            ejercicio_id=ejercicio.id,
            banco=bancos[fila["BANCO"]],
            numero=fila["NUMERO"],
            fecha=fila["FECHA"],
            clave=_texto(fila["CLAVE"]),
            texto=_texto(fila["TEXTO"]),
            texto_automatico=bool(fila["AUTOTEXT"]),
        )
    sesion.add_all(movimientos.values())

    pagos_por_mov: dict[int, int] = defaultdict(int)
    for fila in leer_dbf(carpeta, "Pagos"):
        mov = movimientos.get(fila["NUMERO"])
        if mov is None:
            res.avisos.append(f"Pago sin movimiento de banco nº {fila['NUMERO']}")
            continue
        directa = cuenta(fila["DIRSUBCTA"])
        pagos_por_mov[fila["NUMERO"]] += 1
        mov.pagos.append(
            Pago(
                orden=pagos_por_mov[fila["NUMERO"]],
                importe=dinero(fila["IMPORTE"]),
                vencimiento=vencimientos.get(fila["VTO"]) if fila["VTO"] else None,
                cuenta_directa_id=directa.id if directa else None,
                movimiento_contraparte=movimientos.get(fila["NUMEROT"]) if fila["NUMEROT"] else None,
                declaracion_terceros=_texto(fila["DECLTERC"]) == "S",
            )
        )
    sesion.flush()
    # --- Bienes de inversión (Lbi) con su cuadro de amortización
    for codigo, fila in enumerate(leer_dbf(carpeta, "Lbi"), start=1):
        factura_compra = por_clave.get(("R", fila["RECIBIDA"])) if fila["RECIBIDA"] else None
        c_bien, c_dota, c_amort = cuenta(fila["CUENBIEN"]), cuenta(fila["CUENDOTA"]), cuenta(fila["CUENAMORT"])
        periodos = fila["PERIODO"] or 0
        bien = BienInversion(
            empresa_id=empresa.id,
            codigo=codigo,
            descripcion=_texto(fila["NOMBRE"]),
            tercero_id=(terceros[("P", fila["PROVEEDOR"])].id if ("P", fila["PROVEEDOR"]) in terceros else None),
            factura_compra_id=factura_compra.id if factura_compra else None,
            fecha_adquisicion=fila["FECHA"],
            fecha_funcionamiento=fila["FECHA"],
            precio_compra=dinero(fila["COSTE"]),
            valor_residual=dinero(fila["RESIDUAL"]),
            periodos_vida=periodos or None,
            meses_periodo=fila["MESES"] or 12,
            coeficiente_pct=dinero(fila["COEFI"]),
            porcentaje_anual=dinero(100 / periodos) if periodos and (fila["MESES"] or 12) == 12 else None,
            iva_soportado=dinero(fila["IVA"]),
            cuenta_inmovilizado_id=c_bien.id if c_bien else None,
            cuenta_amortizacion_id=c_amort.id if c_amort else None,
            cuenta_dotacion_id=c_dota.id if c_dota else None,
            fecha_baja=fila["FBAJA"],
            causa_baja=_texto(fila["CBAJA"]) or None,
            notas=_texto(fila["NOTAS"]) or None,
        )
        for ejercicio_cuadro, desde, hasta, previsto, ref, valor in parsear_cuadro_mgd(fila["CUADRO"]):
            contable = None
            if ref == "M":
                importe = _numero_mgd(valor)
                contable = importe if importe != 0 else None  # "M 0,00" = todavía sin amortizar
            else:
                res.avisos.append(f"Bien {codigo}: amortización {ejercicio_cuadro} por extra nº {valor}; sin resolver")
            bien.amortizaciones.append(
                AmortizacionPeriodo(
                    anio=ejercicio_cuadro,
                    desde=desde,
                    hasta=hasta,
                    importe_previsto=previsto,
                    importe_contable=contable,
                    origen=ref,
                )
            )
        sesion.add(bien)
        res.bienes += 1
    sesion.flush()

    # --- Catálogo de tipos de IVA (Tipoiva): TIPO 'S' soportado → recibidas ('R') · 'R' repercutido → emitidas ('E')
    for fila in leer_dbf(carpeta, "Tipoiva"):
        # El catálogo puede nombrar cuentas que nunca se crearon: no se inventan, se dejan sin cuenta y se anotan.
        c_iva, c_re = (cuentas.get(cuenta_de_empresa(fila[k])) for k in ("CTA_IVA", "CTA_IVA_RE"))
        for k in ("CTA_IVA", "CTA_IVA_RE"):
            if _texto(fila[k]) and cuenta_de_empresa(fila[k]) not in cuentas:
                res.cuentas_de_catalogo_inexistentes.append(cuenta_de_empresa(fila[k]))
        sesion.add(
            TipoIva(
                empresa_id=empresa.id,
                sentido="R" if fila["TIPO"] == "S" else "E",
                numero=fila["NUMERO"],
                texto=_texto(fila["TEXTO"]),
                abreviatura=_texto(fila["ABREVIA"]) or None,
                pct_iva=dinero(fila["IVA"]),
                cuenta_iva_id=c_iva.id if c_iva else None,
                pct_recargo=dinero(fila["IVA_RE"]),
                cuenta_recargo_id=c_re.id if c_re else None,
                por_defecto=bool(fila["PORDEFECTO"]),
                inactivo=bool(fila["INACTIVO"]),
            )
        )
        res.tipos_iva += 1
    sesion.flush()

    # --- Plantillas de asientos manuales (Explant)
    for fila in leer_dbf(carpeta, "Explant"):
        lineas = leer_contenido(fila["CONTENIDO"])
        sesion.add(
            Plantilla(
                empresa_id=empresa.id,
                titulo=_texto(fila["TEXTO"]),
                lineas=[
                    PlantillaLinea(
                        orden=i,
                        cuenta=cuenta_de_empresa(l.cuenta),
                        ayuda=l.ayuda,
                        dhc=l.dhc,
                        importe=l.importe,
                        vencimientos=", ".join(l.vencimientos),
                    )
                    for i, l in enumerate(lineas, start=1)
                ],
            )
        )
        res.plantillas += 1
    sesion.flush()

    # --- Justificantes (PDF/JPG) de facturas, movimientos de banco y extras: tabla Etidat + carpeta de ficheros
    carpeta_j = Path(carpeta_justificantes) if carpeta_justificantes else Path(carpeta)
    referenciados: set[str] = set()
    for (tipo_doc, numero_doc), nombres in _justificantes_por_documento(leer_dbf(carpeta, "Etidat")).items():
        if tipo_doc in ("E", "R"):
            destino = {"factura": por_clave.get((tipo_doc, numero_doc))}
        elif tipo_doc == "B":
            destino = {"movimiento_banco": movimientos.get(numero_doc)}
        elif tipo_doc == "X":
            destino = {"asiento": asientos_x.get(numero_doc)}
        else:
            destino = {}
        objetivo = next(iter(destino.values()), None)
        if objetivo is None:
            res.avisos.append(f"Justificantes de un documento inexistente: {tipo_doc} {numero_doc}")
            continue
        clave_fk = {"factura": "factura_id", "movimiento_banco": "movimiento_banco_id", "asiento": "asiento_id"}[next(iter(destino))]
        for orden, nombre in enumerate(nombres, start=1):
            referenciados.add(nombre)
            mime = _mime_de(nombre)
            if mime is None:
                res.avisos.append(f"Justificante con extensión no admitida: {nombre}")
                continue
            ruta = carpeta_j / nombre
            sha, tamano = (_sha256(ruta), ruta.stat().st_size) if ruta.is_file() else (None, None)
            if sha is None:
                res.adjuntos_faltantes.append(nombre)
            sesion.add(
                Adjunto(
                    **{clave_fk: objetivo.id},
                    orden=orden,
                    nombre=nombre,
                    ruta_relativa=nombre,
                    tipo_mime=mime,
                    sha256=sha,
                    tamano=tamano,
                )
            )
            res.adjuntos += 1
    if carpeta_j.is_dir():
        res.adjuntos_huerfanos = sorted(
            f.name for f in carpeta_j.iterdir() if _PATRON_JUSTIFICANTE.match(f.name) and f.name not in referenciados
        )
    sesion.flush()

    # --- Conceptos de los asientos: el texto del extra o del movimiento de banco y «nº factura-tercero» en las facturas
    textos_extra = {f["NUMERO"]: _texto(f["TEXTO"]) for f in leer_dbf(carpeta, "Extra")}
    for numero_x, asiento_x in asientos_x.items():
        asiento_x.concepto = textos_extra.get(numero_x, "")[:255]
    for asiento_b in sesion.query(Asiento).filter(Asiento.ejercicio_id == ejercicio.id, Asiento.tipo == TIPO_TESORERIA):
        mov = movimientos.get(asiento_b.numero)
        asiento_b.concepto = (mov.texto if mov else "")[:255]
    tipo_de_sentido = {"R": TIPO_RECIBIDAS, "E": TIPO_EMITIDAS}
    asientos_facturas = {
        (a.tipo, a.numero): a
        for a in sesion.query(Asiento).filter(Asiento.ejercicio_id == ejercicio.id, Asiento.tipo.in_((TIPO_EMITIDAS, TIPO_RECIBIDAS)), Asiento.sub == 0)
    }
    for (sentido, numero_f), factura in por_clave.items():
        a = asientos_facturas.get((tipo_de_sentido[sentido], numero_f))
        if a is not None:
            nombre = factura.tercero.nombre if factura.tercero is not None else ""
            a.concepto = "-".join(p for p in (factura.numero_factura, nombre) if p)[:255]
    sesion.flush()

    res.bancos, res.vencimientos, res.movimientos = len(bancos), len(vencimientos), len(movimientos)
    res.pagos = sum(pagos_por_mov.values())
    return res
