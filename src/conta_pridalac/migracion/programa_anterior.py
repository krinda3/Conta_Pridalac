"""Cargador del respaldo del programa anterior (`C000X.SDB`, una base SQLite) al esquema nuevo.

Alcance (Hito 2, primera entrega): ficha de la empresa, ejercicios, plan de cuentas, terceros, el Diario completo (asientos y
apuntes) y las facturas emitidas y recibidas con su IVA. Quedan para las siguientes entregas: vencimientos y pagos, bancos,
bienes de inversión y declaraciones presentadas (ver `docs/00_plan_de_trabajo.md`, §9b).

El respaldo se abre **en modo sólo lectura** (nunca se modifica). Las tablas se llaman `C<empresa 4 dígitos><nº tabla 3 dígitos>`:
006 cabeceras de asiento, 007 líneas, 012 datos de la empresa, 020 ejercicios y 415 plan de cuentas con ficha.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import (
    AmortizacionPeriodo,
    Apunte,
    Asiento,
    Banco,
    BienInversion,
    Cuenta,
    DeclaracionLinea,
    DeclaracionPresentada,
    Ejercicio,
    Empresa,
    Factura,
    FacturaIva,
    MovimientoBanco,
    Pago,
    Parametro,
    Tercero,
    TipoIva,
    Vencimiento,
)
from conta_pridalac.db.tipos import dinero

CERO = Decimal("0.00")

# `TIPINT` de los asientos de la serie 9 (automáticos) → subtipo del modelo nuevo
SUBTIPO_POR_TIPINT = {3: "A", 4: "Z", 5: "R", 7: "P", 8: "Q"}  # apertura, cierre, regularización (PyG), liquidación de IVA, amortización


@dataclass
class ResumenSdb:
    empresa_id: int = 0
    ejercicios: int = 0
    cuentas: int = 0
    terceros: int = 0
    asientos: int = 0
    apuntes: int = 0
    facturas: int = 0
    declaraciones: int = 0
    declaraciones_111: int = 0
    bienes: int = 0
    bancos: int = 0
    movimientos: int = 0
    pagos: int = 0
    vencimientos: int = 0
    lineas_neteadas: int = 0  # importes negativos del programa anterior restados de otra línea de la misma cuenta y lado
    lineas_con_signo_negativo: int = 0  # los que no tenían con quién netear y se pasan al lado contrario
    descuadrados: list[str] = field(default_factory=list)  # asientos con Σdebe ≠ Σhaber, como `2026/2/57: 4,18`
    avisos: list[str] = field(default_factory=list)


def abrir_sdb(ruta: str | Path) -> sqlite3.Connection:
    """Abre el respaldo sin posibilidad de escritura."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def fecha_programa_anterior(valor) -> date | None:
    """`20240331` → 2024-03-31 (0 o vacío → None)."""
    if not valor:
        return None
    v = int(valor)
    return date(v // 10000, v // 100 % 100, v % 100)


def _t(v) -> str:
    return str(v if v is not None else "").strip()


def _dir(fila) -> str | None:
    partes = [_t(fila["VIAEMP"]), _t(fila["DOMEMP"]), _t(fila["NUMEMP"])]
    for etiqueta, clave in (("Esc.", "ESCEMP"), ("Piso", "PISEMP"), ("Pta.", "PUEEMP")):
        if _t(fila[clave]):
            partes.append(f"{etiqueta} {_t(fila[clave])}")
    return " ".join(p for p in partes if p) or None


def netear_lineas(filas: list[dict]) -> tuple[list[dict], int, int]:
    """Pasa las líneas de un asiento (`cta`, `deb`, `hab`, `des`) a importes no negativos, como exige el modelo.

    El programa anterior admite un importe negativo en el debe o en el haber (p. ej. una rectificación sobre la misma cuenta): sus sumas lo
    restan de ese lado. Para que los acumulados coincidan, un importe negativo se resta de otra línea de la **misma cuenta y el mismo
    lado** del asiento. Si no hay donde restarlo, pasa al lado contrario. Devuelve las líneas, cuántas se restaron y cuántas se pasaron.
    """
    filas = [dict(f) for f in filas]
    neteadas = pasadas = 0
    for lado, otro in (("deb", "hab"), ("hab", "deb")):
        for f in filas:
            if f[lado] >= 0:
                continue
            socio = next((g for g in filas if g is not f and g["cta"] == f["cta"] and g[lado] >= -f[lado]), None)
            if socio is not None:
                socio[lado] += f[lado]
                f[lado] = CERO
                neteadas += 1
            else:
                f[otro] += -f[lado]
                f[lado] = CERO
                pasadas += 1
    return [f for f in filas if f["deb"] != 0 or f["hab"] != 0], neteadas, pasadas


def cargar_sdb(sesion: Session, ruta_sdb: str | Path, *, codigo_empresa: int, desde: int | None = None, ficha: dict | None = None) -> ResumenSdb:
    """Carga una empresa en la sesión (todos sus ejercicios, o desde el año `desde`); no hace commit.

    `ficha`: datos de la empresa que el programa anterior no guarda (correo, IBAN, actividad…); sobrescriben los del respaldo."""
    con = abrir_sdb(ruta_sdb)
    p = f"C{codigo_empresa:04d}"
    res = ResumenSdb()

    # --- Empresa
    fe = con.execute(f"select * from {p}012").fetchone()
    empresa = Empresa(
        codigo=codigo_empresa,
        nombre=_t(fe["NOMEMP"]),
        nif=_t(fe["CIFEMP"]) or None,
        domicilio=_dir(fe),
        codigo_postal=_t(fe["POSEMP"]) or None,
        poblacion=_t(fe["POBEMP"]).upper() or None,
        provincia=_t(fe["PROEMP"]).upper() or None,
        telefono=_t(fe["TELEMP"]) or None,
        representante_nombre=_t(fe["PERCON"]) or None,
    )
    sesion.add(empresa)
    sesion.flush()
    res.empresa_id = empresa.id

    # --- Ejercicios
    ejercicios: dict[str, Ejercicio] = {}
    for f in con.execute(f"select COD, INI, FIN, CER from {p}020 order by COD"):
        if desde and int(f["COD"]) < desde:
            continue
        e = Ejercicio(empresa_id=empresa.id, anio=int(f["COD"]), fecha_inicio=fecha_programa_anterior(f["INI"]), fecha_fin=fecha_programa_anterior(f["FIN"]), cerrado=_t(f["CER"]) == "*")
        ejercicios[_t(f["COD"])] = e
        sesion.add(e)
    sesion.flush()
    res.ejercicios = len(ejercicios)

    # --- Plan de cuentas (415 trae la ficha completa: nombre, NIF, domicilio…)
    fichas = {_t(f["COD"]): f for f in con.execute(f"select * from {p}415")}
    cuentas: dict[str, Cuenta] = {}
    for codigo, f in fichas.items():
        cuentas[codigo] = Cuenta(empresa_id=empresa.id, codigo=codigo, nombre=_t(f["NOM"]))
    sesion.add_all(cuentas.values())
    sesion.flush()
    res.cuentas = len(cuentas)

    def cuenta(codigo: str) -> Cuenta:
        codigo = _t(codigo)
        if codigo not in cuentas:
            res.avisos.append(f"Cuenta {codigo} usada pero inexistente en el plan; se crea")
            cuentas[codigo] = Cuenta(empresa_id=empresa.id, codigo=codigo, nombre="(creada en la migración)")
            sesion.add(cuentas[codigo])
            sesion.flush()
        return cuentas[codigo]

    # --- Terceros: las subcuentas de proveedores/acreedores (40, 41) y de clientes/deudores (43, 44)
    terceros: dict[str, Tercero] = {}
    for codigo, f in fichas.items():
        if len(codigo) != 8 or codigo[:2] not in ("40", "41", "43", "44"):
            continue
        t = Tercero(
            empresa_id=empresa.id,
            clase="P" if codigo[:2] in ("40", "41") else "C",
            nombre=_t(f["NOM"]),
            comercial=_t(f["NOMCOM"]) or None,
            nif=_t(f["NIF"]) or None,
            cuenta_id=cuentas[codigo].id,
            domicilio=_t(f["DIR"]) or None,
            codigo_postal=_t(f["POS"]) if _t(f["POS"]) not in ("", "0") else None,
            poblacion=_t(f["POB"]) or None,
            provincia=_t(f["PRO"]) or None,
            pais=_t(f["PAI"]) or None,
            telefonos=_t(f["TEL"]) or None,
            email=_t(f["MAIL"]) or None,
            web=_t(f["WEB"]) or None,
            observaciones=_t(f["OBS"]) or None,
            no_incluir_347=_t(f["NO347"]) == "*",
            cuenta_gasto_id=cuentas[_t(f["CTAASO"])].id if _t(f["CTAASO"]) in cuentas else None,
        )
        terceros[codigo] = t
        sesion.add(t)
    sesion.flush()
    res.terceros = len(terceros)

    # --- Diario: cabeceras (006) y líneas (007)
    lineas: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for l in con.execute(f"select * from {p}007 order by EJE, SER, COD, LIN"):
        lineas[(_t(l["EJE"]), _t(l["SER"]), l["COD"])].append(l)

    asientos: dict[tuple, Asiento] = {}
    cabeceras: list[sqlite3.Row] = []
    for h in con.execute(f"select * from {p}006 order by EJE, SER, COD"):
        eje, ser = _t(h["EJE"]), _t(h["SER"])
        if eje not in ejercicios:
            if desde and int(eje) < desde:
                continue
            res.avisos.append(f"Asiento {eje}/{ser}/{h['COD']} de un ejercicio que no existe; se ignora")
            continue
        a = Asiento(
            ejercicio_id=ejercicios[eje].id, tipo=int(ser), numero=h["COD"], sub=0, numero_diario=h["ASI"] or None,
            fecha=fecha_programa_anterior(h["FEC"]), concepto=_t(h["DES"])[:255], subtipo=SUBTIPO_POR_TIPINT.get(h["TIPINT"]) if ser == "9" else "M",
        )
        debe_total = haber_total = CERO
        crudas = [{"cta": _t(l["CTA"]), "deb": dinero(l["DEB"]), "hab": dinero(l["HAB"]), "des": _t(l["DES"])[:255] or None} for l in lineas.get((eje, ser, h["COD"]), [])]
        netas, neteadas, pasadas = netear_lineas(crudas)
        res.lineas_neteadas += neteadas
        res.lineas_con_signo_negativo += pasadas
        for n, l in enumerate(netas, start=1):
            d, hb = l["deb"], l["hab"]
            debe_total, haber_total = debe_total + d, haber_total + hb
            a.apuntes.append(Apunte(orden=n, cuenta_id=cuenta(l["cta"]).id, debe=d, haber=hb, concepto=l["des"]))
        if debe_total != haber_total:
            res.descuadrados.append(f"{eje}/{ser}/{h['COD']}: debe {debe_total} · haber {haber_total} · diferencia {debe_total - haber_total}")
        asientos[(eje, ser, h["COD"])] = a
        cabeceras.append(h)
        sesion.add(a)
        res.asientos += 1
        res.apuntes += len(a.apuntes)
    sesion.flush()

    facturas_por_clave: dict[tuple, Factura] = {}
    # --- Facturas: los asientos de serie 1 (emitidas) y 2 (recibidas) llevan los datos de la factura en la cabecera
    for h in cabeceras:
        ser = _t(h["SER"])
        if ser not in ("1", "2"):
            continue
        eje, sentido = _t(h["EJE"]), "E" if ser == "1" else "R"
        a = asientos[(eje, ser, h["COD"])]
        lins = a.apuntes
        cta_tercero = cuentas.get(_t(h["CLIPRO"]))
        prefijo_iva = "477" if sentido == "E" else "472"
        lados = [x for x in lins if x.cuenta.codigo.startswith(prefijo_iva)]
        # la cuenta de gasto o ingreso se toma de las líneas del programa anterior (una factura sin base tiene la línea a 0, que no llega al apunte)
        brutas = [l for l in lineas.get((eje, ser, h["COD"]), []) if not _t(l["CTA"]).startswith(("472", "477", "475")) and _t(l["CTA"]) != _t(h["CLIPRO"])]
        lado_normal = (lambda l: l["HAB"] > 0) if sentido == "E" else (lambda l: l["DEB"] > 0)  # una rectificativa va por el lado contrario
        elegida = next((l for l in brutas if lado_normal(l)), brutas[0] if brutas else None)
        contra = cuentas.get(_t(elegida["CTA"])) if elegida is not None else None
        factura = Factura(
            ejercicio_id=ejercicios[eje].id, sentido=sentido, numero=h["COD"], fecha_contable=fecha_programa_anterior(h["FEC"]),
            fecha_factura=fecha_programa_anterior(h["FECFAC"]) or fecha_programa_anterior(h["FEC"]), numero_factura=_t(h["FAC"])[:40] or None,
            tercero_id=terceros[cta_tercero.codigo].id if cta_tercero and cta_tercero.codigo in terceros else None,
            cuenta_tercero_id=cta_tercero.id if cta_tercero else None, cuenta_contrapartida_id=contra.id if contra else None,
            total=dinero(h["TOTFAC"]), concepto=_t(h["DES"])[:255] or None,
        )
        for i in range(1, 9):
            base, cuota, pct = dinero(h[f"BIVA{i}"]), dinero(h[f"CIVA{i}"]), dinero(h[f"PIVA{i}"])
            cuota_re, pct_re = dinero(h[f"CREC{i}"]), dinero(h[f"PREC{i}"])
            if base == CERO and cuota == CERO:
                continue
            c_iva = next((x.cuenta_id for x in lados if cuota in (x.debe, x.haber)), lados[0].cuenta_id if lados else None)
            c_re = next((x.cuenta_id for x in lados if cuota_re in (x.debe, x.haber)), c_iva) if cuota_re else None
            factura.ivas.append(FacturaIva(base=base, pct_iva=pct, cuota_iva=cuota, cuenta_iva_id=c_iva, pct_recargo=pct_re, cuota_recargo=cuota_re, cuenta_recargo_id=c_re))
        sesion.add(factura)
        facturas_por_clave[(eje, ser, h["COD"])] = factura
        res.facturas += 1
    sesion.flush()

    # --- Parámetros que usan el cierre, el IVA y la tesorería (en el programa anterior están en la ficha de la empresa)
    parametros = {"PYG": _t(fe["PERGAN"]), "IVA_DEBE": _t(fe["IVADEU"]), "IVA_HABER": _t(fe["IVAACR"])}
    if "55500000" in cuentas:
        parametros["PTE_APLIC"] = "55500000"  # partidas pendientes de aplicar: no es un dato del programa anterior, se toma la cuenta del PGC
    for clave, valor in parametros.items():
        if valor:
            sesion.add(Parametro(empresa_id=empresa.id, clave=clave, valor=valor))
    sesion.flush()

    # --- Catálogo de tipos de IVA: el programa anterior no lo guarda (sólo las cuentas de IVA, tabla 401); se crean los tipos vigentes
    fila_iva = con.execute(f"select IVASOP, IVAREP from {p}401").fetchone()
    for sentido, columna in (("R", "IVASOP"), ("E", "IVAREP")):
        cuenta_iva = cuentas.get(_t(fila_iva[columna])) if fila_iva else None
        for numero, (texto, abreviatura, pct, recargo) in enumerate((("General", "G", 21, "5.20"), ("Reducido", "R", 10, "1.40"), ("Superreducido", "S", 4, "0.50"), ("Exento / no sujeto", "E", 0, "0.00")), start=1):
            sesion.add(TipoIva(empresa_id=empresa.id, sentido=sentido, numero=numero, texto=f"{texto} {pct}%" if pct else texto, abreviatura=abreviatura, pct_iva=dinero(pct),
                               cuenta_iva_id=cuenta_iva.id if cuenta_iva else None, pct_recargo=dinero(recargo), por_defecto=numero == 1))
    sesion.flush()

    for campo, valor in (ficha or {}).items():
        if campo not in ("domicilio", "codigo_postal", "poblacion", "provincia", "pais", "telefono", "email", "web", "iban", "actividad", "cnae", "representante_nombre", "representante_nif", "representante_cargo", "nombre", "nif", "certificado_ruta", "tipo_entidad", "forma_administracion", "codigo_irus", "fecha_constitucion", "registro_provincia", "registro_tomo", "registro_libro", "registro_folio", "registro_hoja", "registro_inscripcion"):
            res.avisos.append(f"Ficha: campo desconocido «{campo}»; se ignora")
            continue
        setattr(empresa, campo, date.fromisoformat(valor) if campo == "fecha_constitucion" and valor else (valor or None))
    sesion.flush()

    primer_anio = min((e.anio for e in ejercicios.values()), default=0)
    _cargar_bienes(sesion, con, p, empresa, cuentas, terceros, asientos, facturas_por_clave, ejercicios, primer_anio, res)
    _cargar_tesoreria(sesion, con, p, empresa, cuentas, asientos, facturas_por_clave, ejercicios, res)
    _cargar_declaraciones(sesion, con, p, empresa, asientos, facturas_por_clave, primer_anio, res)
    res.declaraciones_111 += cargar_declaraciones_111(sesion, con, p, empresa, primer_anio)
    sesion.flush()
    return res


def cargar_declaraciones_111(sesion, con, p, empresa, primer_anio: int) -> int:
    """Declaraciones del modelo 111 ya presentadas (tabla 199 del programa anterior; sus casillas CAS1…CAS30 son las del formulario). No repite las que ya están. Devuelve cuántas añade."""
    if con.execute("select 1 from sqlite_master where type = 'table' and name = ?", (f"{p}199",)).fetchone() is None:
        return 0  # un respaldo sin esa tabla (o sin declaraciones del 111)
    existentes = {(d.anio, d.periodo, d.tipo) for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo == "111"))}
    nuevas = 0
    for f in con.execute(f"select * from {p}199 where ANO >= ? order by ANO, PER, TIPDEC", (primer_anio,)):
        if (f["ANO"], f["PER"], f["TIPDEC"]) in existentes:
            continue
        casillas = {k[3:]: round(f[k], 2) for k in f.keys() if k.startswith("CAS") and isinstance(f[k], (int, float)) and f[k]}
        sesion.add(DeclaracionPresentada(
            empresa_id=empresa.id, modelo="111", anio=f["ANO"], periodo=f["PER"], tipo=f["TIPDEC"], fecha_emision=fecha_programa_anterior(f["FECEMI"]), fecha_envio=fecha_programa_anterior(f["FECENV"]),
            justificante=_t(f["NUMDEC"]) or None, resultado_liquidacion=dinero(f["CAS28"]), resultado=dinero(f["CAS30"]), a_compensar=CERO,
            casillas=json.dumps(casillas, ensure_ascii=False, sort_keys=True),
        ))
        nuevas += 1
    sesion.flush()
    return nuevas


def _cargar_declaraciones(sesion, con, p, empresa, asientos, facturas, primer_anio, res) -> None:
    """Declaraciones de IVA ya presentadas (440) con las facturas de cada una (444). Se enlazan con el asiento de liquidación con que se contabilizaron."""
    lineas: dict[tuple, list] = defaultdict(list)
    for f in con.execute(f"select * from {p}444 where ANO >= ? order by ANO, PER, TIPDEC, LIN", (primer_anio,)):
        lineas[(f["ANO"], f["PER"], f["TIPDEC"])].append(f)
    for f in con.execute(f"select * from {p}440 where ANO >= ? order by ANO, PER, TIPDEC", (primer_anio,)):
        casillas = {k[3:]: round(f[k], 2) for k in f.keys() if k.startswith("CAS") and isinstance(f[k], (int, float)) and f[k]}
        asiento = asientos.get((_t(f["EJECON"]), _t(f["SER"]), f["DOC"])) if _t(f["SER"]) == "9" and f["DOC"] else None
        d = DeclaracionPresentada(
            empresa_id=empresa.id, modelo="303", anio=f["ANO"], periodo=f["PER"], tipo=f["TIPDEC"], fecha_emision=fecha_programa_anterior(f["FECEMI"]), fecha_envio=fecha_programa_anterior(f["FECENV"]),
            justificante=_t(f["NUMDEC"]) or None, resultado_liquidacion=dinero(f["CAS46"]), resultado=dinero(f["CAS71"]), a_compensar=dinero(f["CAS87"]),
            casillas=json.dumps(casillas, ensure_ascii=False, sort_keys=True), asiento_id=asiento.id if asiento is not None else None,
        )
        for l in lineas.get((f["ANO"], f["PER"], f["TIPDEC"]), []):
            factura = facturas.get((_t(l["EJE"]), _t(l["SER"]), l["COD"]))
            d.lineas.append(DeclaracionLinea(
                factura_id=factura.id if factura is not None else None, numero_factura=_t(l["NUMFAC"])[:40] or None, fecha_factura=fecha_programa_anterior(l["FECFAC"]),
                fecha_fiscal=fecha_programa_anterior(l["FECFIS"]), casilla=_t(l["CAS"]) or None, base=dinero(l["BAS"]), porcentaje=dinero(l["POR"]), cuota=dinero(l["CUO"]),
            ))
        sesion.add(d)
        res.declaraciones += 1


def _cargar_bienes(sesion, con, p, empresa, cuentas, terceros, asientos, facturas, ejercicios, primer_anio, res) -> None:
    """Bienes de inversión (051) y su cuadro de amortización (052). Un año con asiento «Amortización N.» queda contabilizado;
    los anteriores al primer ejercicio cargado se dan por amortizados (no hay asiento que lo pruebe); los demás, pendientes."""
    amortizaciones: dict[tuple[int, int], Asiento] = {}  # (año, nº de bien) → asiento
    for h in con.execute(f"select EJE, COD, DES from {p}006 where SER = '9' and TIPINT = 8"):
        m = re.search(r"(\d+)\.", _t(h["DES"]))
        if m and _t(h["EJE"]) in ejercicios:
            amortizaciones[(int(h["EJE"]), int(m.group(1)))] = asientos[(_t(h["EJE"]), "9", h["COD"])]
    cuadro: dict[int, list] = defaultdict(list)
    for f in con.execute(f"select * from {p}052 order by COD, ANO"):
        cuadro[f["COD"]].append(f)
    for f in con.execute(f"select * from {p}051 order by COD"):
        def cta(campo):
            c = cuentas.get(_t(f[campo]))
            return c.id if c else None

        compra = facturas.get((_t(f["EJECOM"]), _t(f["SERCOM"]), f["DOCCOM"])) if f["DOCCOM"] else None
        adquisicion = fecha_programa_anterior(f["FECCOM"]) or fecha_programa_anterior(f["FECDIS"])
        puesta = fecha_programa_anterior(f["FECDIS"]) or adquisicion
        bien = BienInversion(
            empresa_id=empresa.id, codigo=f["COD"], descripcion=_t(f["NOM"]), tercero_id=terceros[_t(f["PROVEE"])].id if _t(f["PROVEE"]) in terceros else None,
            numero_factura_compra=_t(f["FACCOM"]) or None, fecha_adquisicion=adquisicion, fecha_funcionamiento=puesta, precio_compra=dinero(f["PRE"]),
            valor_residual=dinero(f["VALRES"]), valor_suelo=dinero(f["VALSUE"]), porcentaje_anual=dinero(f["PORAMO"]), coeficiente_pct=dinero(f["PORAMO"]),
            periodos_vida=int(100 / f["PORAMO"]) if f["PORAMO"] else None, meses_periodo=12,
            iva_soportado=dinero(f["CIVAC"]), cuenta_inmovilizado_id=cta("CUEIN2"), cuenta_amortizacion_id=cta("CUEAM2"), cuenta_dotacion_id=cta("CUEDO2"),
            fecha_baja=fecha_programa_anterior(f["FECVEN"]), causa_baja=_t(f["CAUBAJ"]) or None, factura_compra_id=compra.id if compra else None,
        )
        for q in cuadro.get(f["COD"], []):
            anio = int(q["ANO"])
            desde = puesta if puesta and puesta.year == anio else date(anio, 1, 1)
            asiento = amortizaciones.get((anio, f["COD"]))
            contable, origen = None, None
            if asiento is not None:
                dotacion = cuentas.get(_t(f["CUEDO2"]))
                contable = sum((x.debe for x in asiento.apuntes if dotacion and x.cuenta_id == dotacion.id), CERO) or dinero(q["IMPAMO"])
                origen = "X"
            elif anio < primer_anio:
                contable, origen = dinero(q["IMPAMO"]), "M"
            bien.amortizaciones.append(AmortizacionPeriodo(
                anio=anio, desde=desde, hasta=date(anio, 12, 31), importe_previsto=dinero(q["IMPAMO"]), importe_contable=contable,
                importe_fiscal=dinero(q["IMPAFI"]) if q["IMPAFI"] else None, origen=origen, asiento_id=asiento.id if asiento else None,
            ))
        sesion.add(bien)
        res.bienes += 1


def _cargar_tesoreria(sesion, con, p, empresa, cuentas, asientos, facturas, ejercicios, res) -> None:
    """Bancos, movimientos (asientos de la serie 3), vencimientos (027) y pagos (076).

    Banco = cuenta usada como cobro o pago en 027/076, o de la 572. Cada asiento de tesorería es un movimiento del banco que
    aparece en él; si hay dos bancos (transferencia), el movimiento es el del que sale el dinero y el otro es la cuenta directa.
    Un pago de 076 salda el vencimiento de 027 de la misma factura (el de igual importe, o el primero con pendiente); si la
    factura no tiene vencimiento en 027 (ya liquidado), se crea uno por pago, con la fecha del pago.
    """
    cuentas_banco = {_t(r[0]) for r in con.execute(f"select CTAPAG from {p}076")} | {_t(r[0]) for r in con.execute(f"select COBPAG from {p}027")}
    usadas = {x.cuenta.codigo for (_, ser, _), a in asientos.items() if ser == "3" for x in a.apuntes}  # sólo cuentas que mueven dinero en tesorería
    cuentas_banco = ({c for c in cuentas_banco if c in cuentas} | {c for c in cuentas if c.startswith("572")}) & usadas
    bancos: dict[str, Banco] = {}
    compensaciones = 0
    for codigo in sorted(cuentas_banco):
        if codigo.startswith("5"):  # banco, tarjeta o cuenta corriente con socios
            bancos[codigo] = Banco(empresa_id=empresa.id, numero=len(bancos) + 1, clase="B", nombre=cuentas[codigo].nombre[:64], cuenta_id=cuentas[codigo].id)
        else:  # el programa anterior salda con otras cuentas (subvenciones, Hacienda deudora…): son compensaciones, no bancos
            compensaciones += 1
            bancos[codigo] = Banco(empresa_id=empresa.id, numero=-compensaciones, clase="C", nombre=("COMPENSACIÓN " + cuentas[codigo].nombre)[:64], cuenta_id=cuentas[codigo].id)
    sesion.add_all(bancos.values())
    res.bancos = sum(1 for b in bancos.values() if b.clase == "B")

    vencimientos: dict[tuple, list[Vencimiento]] = defaultdict(list)
    por_movimiento_027: dict[tuple, Vencimiento] = {}
    for f in con.execute(f"select * from {p}027 order by EJE, SER, DOC, NUM"):
        clave = (_t(f["EJE"]), _t(f["SER"]), f["DOC"])
        factura = facturas.get(clave)
        if factura is None:
            continue
        importe = dinero(f["IMP"]) * (1 if clave[1] == "1" else -1)  # positivo = a cobrar, negativo = a pagar
        if importe == 0:  # el programa anterior deja a 0 el vencimiento ya cobrado o pagado: el pago crea el suyo
            continue
        v = Vencimiento(
            ejercicio_id=factura.ejercicio_id, origen_tipo="E" if clave[1] == "1" else "R", origen_numero=f["DOC"], factura=factura,
            fecha=fecha_programa_anterior(f["VEN"]), importe=importe, banco_previsto=bancos.get(_t(f["COBPAG"])),
        )
        vencimientos[clave].append(v)
        if _t(f["CONTA"]) == "*" and f["DOCCON"]:
            por_movimiento_027[(_t(f["EJECON"]), f["DOCCON"])] = v
        sesion.add(v)
        res.vencimientos += 1
    pagos_076: dict[tuple, sqlite3.Row] = {}
    for f in con.execute(f"select * from {p}076 where SERPAG = '3' order by EJE, SER, DOC, LIN"):
        pagos_076[(_t(f["EJEPAG"]), f["DOCPAG"])] = f

    movimientos_de = sorted((k, a) for k, a in asientos.items() if k[1] == "3")
    for (anio, _, numero), a in movimientos_de:
        lineas_banco = [x for x in a.apuntes if x.cuenta.codigo in bancos]
        if not lineas_banco:
            res.avisos.append(f"Tesorería {anio}/3/{numero}: ninguna de sus cuentas es un banco; queda como asiento sin movimiento")
            continue
        reales = [x for x in lineas_banco if bancos[x.cuenta.codigo].clase == "B"] or lineas_banco
        principal = next((x for x in reales if x.haber > x.debe), reales[0])
        movimiento = MovimientoBanco(ejercicio_id=a.ejercicio_id, banco=bancos[principal.cuenta.codigo], numero=numero, fecha=a.fecha, clave="", texto=a.concepto or "")
        info = pagos_076.get((anio, numero))
        v027 = por_movimiento_027.get((anio, numero))
        for orden, x in enumerate((x for x in a.apuntes if x is not principal), start=1):
            importe = x.haber - x.debe  # positivo = entra dinero en el banco
            pago = Pago(orden=orden, importe=importe)
            vencimiento = None
            if info is None and v027 is not None and x.cuenta_id == v027.factura.cuenta_tercero_id:  # sin pago en 076: lo dice el propio vencimiento
                vencimiento = v027
            elif info is not None:
                clave = (_t(info["EJE"]), _t(info["SER"]), info["DOC"])
                factura = facturas.get(clave)
                if factura is not None and x.cuenta_id == factura.cuenta_tercero_id:
                    vencimiento = _vencimiento_para(sesion, vencimientos, clave, factura, importe, a.fecha, res)
            if vencimiento is not None:
                pago.vencimiento = vencimiento
            else:
                pago.cuenta_directa_id = x.cuenta_id
            movimiento.pagos.append(pago)
            res.pagos += 1
        sesion.add(movimiento)
        res.movimientos += 1


def _vencimiento_para(sesion, vencimientos, clave, factura, importe, fecha, res) -> Vencimiento:
    """Vencimiento de la factura que salda este pago: uno al que le quede justo ese importe, el primero al que le quepa o uno nuevo."""
    def pendiente(v: Vencimiento) -> Decimal:
        return v.importe - sum((p.importe for p in v.pagos), CERO)

    libres = [v for v in vencimientos[clave] if pendiente(v) != 0 and abs(pendiente(v)) >= abs(importe) and (pendiente(v) > 0) == (importe > 0)]
    elegido = next((v for v in libres if pendiente(v) == importe), libres[0] if libres else None)
    if elegido is None:
        elegido = Vencimiento(ejercicio_id=factura.ejercicio_id, origen_tipo=factura.sentido, origen_numero=factura.numero, factura=factura, fecha=fecha, importe=importe)
        vencimientos[clave].append(elegido)
        sesion.add(elegido)
        res.vencimientos += 1
    return elegido
