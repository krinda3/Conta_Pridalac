"""Comprobantes (PDF/JPG) exportados del programa anterior: se enlazan con su asiento o factura por el nombre del fichero.

Nomenclatura (carpeta por año): `C<empresa 4 dígitos>_F<ejercicio>_<serie>_<nº de asiento>.PDF`. La serie y el número son los del
asiento del programa anterior (`EJE`, `SER`, `COD`): serie 1 = factura emitida, 2 = recibida (el comprobante cuelga de la `Factura`); 3, 4 y 9
(tesorería, manual, automático) cuelgan del `Asiento`. Los demás nombres (`C0001_303_2022_03`: modelo, año, periodo; o `CON_…`) son
documentos de declaraciones, que no tienen todavía dónde colgar: se listan en el informe para el Hito 3.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Asiento, DeclaracionPresentada, Ejercicio, Empresa, Factura
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos, adjuntar, nombre_seguro, sha256_de

PATRON_ASIENTO = re.compile(r"^C(\d{4})_F(\d{4})_(\d)_(\d+)\.(pdf|jpe?g)$", re.IGNORECASE)
PATRON_MODELO_303 = re.compile(r"^C(\d{4})_(C?)(303|111|190|347)_(\d{4})_(\d{2})\.pdf$", re.IGNORECASE)  # C303 = la complementaria; el 111 se enlaza igual
PATRON_EMPRESA = re.compile(r"^C(\d{4})_", re.IGNORECASE)


@dataclass
class ResumenComprobantes:
    ficheros: int = 0
    importados: int = 0
    a_declaraciones: int = 0
    declaraciones_sin_registro: list[str] = field(default_factory=list)  # PDF de un 303 que no está en las declaraciones importadas
    a_facturas: int = 0
    a_asientos: int = 0
    duplicados: list[str] = field(default_factory=list)  # mismo contenido ya adjunto al documento
    sin_asiento: list[str] = field(default_factory=list)  # nombre de asiento válido pero no existe en la base
    rechazados: list[str] = field(default_factory=list)  # `nombre: motivo` (PDF no válido, demasiado grande…)
    declaraciones: list[str] = field(default_factory=list)  # modelos y otros documentos sin asiento
    de_otra_empresa: list[str] = field(default_factory=list)
    facturas_sin_comprobante: dict[str, int] = field(default_factory=dict)  # `2024 recibidas` → nº


def importar_comprobantes(sesion: Session, almacen: AlmacenAdjuntos, empresa: Empresa, carpeta: str | Path) -> ResumenComprobantes:
    """Recorre `carpeta` (todas las subcarpetas) y adjunta al almacén cada comprobante que se pueda enlazar. No hace commit."""
    carpeta = Path(carpeta)
    res = ResumenComprobantes()
    ejercicios = {e.anio: e for e in sesion.scalars(select(Ejercicio).where(Ejercicio.empresa_id == empresa.id))}
    facturas = {(f.ejercicio_id, f.sentido, f.numero): f for f in sesion.scalars(select(Factura).where(Factura.ejercicio_id.in_([e.id for e in ejercicios.values()])))}
    asientos = {(a.ejercicio_id, a.tipo, a.numero): a for a in sesion.scalars(select(Asiento).where(Asiento.ejercicio_id.in_([e.id for e in ejercicios.values()]), Asiento.sub == 0))}
    con_comprobante: set[int] = set()
    declaraciones = {(d.modelo, d.anio, d.periodo, d.tipo): d for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo.in_(("303", "111"))))}

    for ruta in sorted(p for p in carpeta.rglob("*") if p.is_file()):
        rel = ruta.relative_to(carpeta).as_posix()
        res.ficheros += 1
        mt_empresa = PATRON_EMPRESA.match(ruta.name)
        if mt_empresa and int(mt_empresa.group(1)) != empresa.codigo:
            res.de_otra_empresa.append(rel)
            continue
        m303 = PATRON_MODELO_303.match(ruta.name)
        if m303:
            declaracion = declaraciones.get((m303.group(3), int(m303.group(4)), int(m303.group(5)), 2 if m303.group(2) else 1))
            if declaracion is None:
                res.declaraciones_sin_registro.append(rel)
            else:
                destino_pdf = f"{empresa.codigo:03d}/{declaracion.anio}/D/{declaracion.id:06d}_{nombre_seguro(ruta.name)}"
                final = almacen.raiz / destino_pdf
                final.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ruta, final)
                declaracion.pdf_nombre, declaracion.pdf_ruta, declaracion.pdf_sha256 = ruta.name, destino_pdf, sha256_de(final)
                res.a_declaraciones += 1
            continue
        m = PATRON_ASIENTO.match(ruta.name)
        if not m:
            res.declaraciones.append(rel)
            continue
        anio, serie, numero = int(m.group(2)), int(m.group(3)), int(m.group(4))
        ejercicio = ejercicios.get(anio)
        destino = None
        if ejercicio is not None:
            if serie in (1, 2):
                destino = facturas.get((ejercicio.id, "E" if serie == 1 else "R", numero))
            else:
                destino = asientos.get((ejercicio.id, serie, numero))
        if destino is None:
            res.sin_asiento.append(rel)
            continue
        try:
            r = adjuntar(sesion, almacen, ejercicio, destino, ruta, ignorar_cierre=True)
        except ErrorContable as ex:
            res.rechazados.append(f"{rel}: {ex}")
            continue
        if r.advertencias:
            res.duplicados.append(rel)
            continue
        res.importados += 1
        if isinstance(destino, Factura):
            res.a_facturas += 1
            con_comprobante.add(destino.id)
        else:
            res.a_asientos += 1

    for f in facturas.values():
        if f.id not in con_comprobante:
            clave = f"{next(a for a, e in ejercicios.items() if e.id == f.ejercicio_id)} {'emitidas' if f.sentido == 'E' else 'recibidas'}"
            res.facturas_sin_comprobante[clave] = res.facturas_sin_comprobante.get(clave, 0) + 1
    sesion.flush()
    return res


def informe(res: ResumenComprobantes, titulo: str) -> str:
    """Texto del informe de auditoría de comprobantes (para guardar en `datos_locales/salida`)."""
    def bloque(nombre: str, items: list[str], ayuda: str) -> list[str]:
        out = [f"\n== {nombre}: {len(items)} ==", ayuda]
        out += [f"  {x}" for x in items]
        return out

    lineas = [
        f"AUDITORÍA DE COMPROBANTES · {titulo}",
        f"Ficheros recorridos: {res.ficheros} · importados: {res.importados} (facturas {res.a_facturas}, asientos {res.a_asientos}) · modelos 303: {res.a_declaraciones} · duplicados: {len(res.duplicados)}",
    ]
    lineas += bloque("Comprobantes SIN ASIENTO en la base", res.sin_asiento, "El nombre apunta a un asiento (ejercicio/serie/número) que no existe en el respaldo. No se han importado.")
    lineas += bloque("Rechazados", res.rechazados, "Ficheros que el almacén no admite (no son PDF/JPG válidos, vacíos o de más de 25 MB).")
    lineas += bloque("Duplicados", res.duplicados, "Su contenido ya estaba adjunto al mismo documento.")
    lineas += bloque("PDF del 303 sin declaración en la base", res.declaraciones_sin_registro, "No hay declaración importada de ese periodo (falta en el respaldo): el PDF no se ha enlazado.")
    lineas += bloque("Documentos de declaraciones (sin destino todavía)", res.declaraciones, "Modelos 111, 190, 347…: se enlazarán cuando existan las declaraciones (Hito 3).")
    if res.de_otra_empresa:
        lineas += bloque("De otra empresa", res.de_otra_empresa, "El prefijo CXXXX del nombre no es el de esta empresa.")
    lineas.append("\n== Facturas sin comprobante en la carpeta ==")
    lineas += [f"  {k}: {v}" for k, v in sorted(res.facturas_sin_comprobante.items())]
    return "\n".join(lineas) + "\n"


def enlazar_pdfs_de_declaraciones(sesion: Session, almacen: AlmacenAdjuntos, empresa: Empresa, carpeta: str | Path, modelos: tuple[str, ...] = ("111",)) -> tuple[int, list[str]]:
    """Enlaza sólo los PDF de las declaraciones de esos modelos (p. ej. `C0002_111_2026_03.PDF`) con su declaración ya importada, sin tocar facturas ni asientos.
    Devuelve (enlazados, PDF sin declaración en la base). No hace commit."""
    declaraciones = {(d.modelo, d.anio, d.periodo, d.tipo): d for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa.id, DeclaracionPresentada.modelo.in_(modelos)))}
    enlazados, sin_registro = 0, []
    for ruta in sorted(p for p in Path(carpeta).rglob("*") if p.is_file()):
        m = PATRON_MODELO_303.match(ruta.name)
        if not m or int(m.group(1)) != empresa.codigo or m.group(3) not in modelos:
            continue
        declaracion = declaraciones.get((m.group(3), int(m.group(4)), int(m.group(5)), 2 if m.group(2) else 1))
        if declaracion is None:
            sin_registro.append(ruta.relative_to(carpeta).as_posix())
            continue
        destino_pdf = f"{empresa.codigo:03d}/{declaracion.anio}/D/{declaracion.id:06d}_{nombre_seguro(ruta.name)}"
        final = almacen.raiz / destino_pdf
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ruta, final)
        declaracion.pdf_nombre, declaracion.pdf_ruta, declaracion.pdf_sha256 = ruta.name, destino_pdf, sha256_de(final)
        enlazados += 1
    sesion.flush()
    return enlazados, sin_registro
