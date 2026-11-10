"""Convierte los informes en `Tabla`, lista para exportar a PDF o a Excel (`conta_pridalac.exportacion`)."""
from __future__ import annotations

from decimal import Decimal

from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.exportacion.tabla import DINERO, ENTERO, FECHA, PORCENTAJE, Columna, Tabla
from conta_pridalac.servicios.bienes_iva import LineaLibroBienes
from conta_pridalac.servicios.informes import Balance, LibroDiario, LibroIva, Mayor, NIVEL_SUBCUENTA

CERO = Decimal("0.00")


def _periodo(ejercicio: Ejercicio, desde, hasta) -> str:
    d, h = desde or ejercicio.fecha_inicio, hasta or ejercicio.fecha_fin
    return f"{ejercicio.empresa.nombre} · ejercicio {ejercicio.anio} · del {d:%d/%m/%Y} al {h:%d/%m/%Y}"


def tabla_diario(libro: LibroDiario, ejercicio: Ejercicio, *, desde=None, hasta=None) -> Tabla:
    filas = []
    for a in libro.asientos:
        for ap in a.apuntes:
            filas.append([a.fecha, a.identificador, ap.cuenta.codigo, ap.cuenta.nombre, ap.concepto or a.concepto, ap.debe or None, ap.haber or None])
    columnas = [Columna("Fecha", FECHA, 1.1), Columna("Asiento", ancho=0.9), Columna("Cuenta", ancho=1.1), Columna("Nombre de la cuenta", ancho=3),
                Columna("Concepto", ancho=3), Columna("Debe", DINERO, 1.2), Columna("Haber", DINERO, 1.2)]
    return Tabla("Libro Diario", columnas, filas, _periodo(ejercicio, desde, hasta), totales=[None, None, None, None, "Totales", libro.total_debe, libro.total_haber])


def tabla_mayor(m: Mayor, ejercicio: Ejercicio, *, desde=None, hasta=None) -> Tabla:
    filas = []
    if m.saldo_anterior != 0:
        filas.append([None, "", "Saldo anterior", None, None, m.saldo_anterior])
    filas += [[l.fecha, l.asiento, l.concepto, l.debe or None, l.haber or None, l.saldo] for l in m.lineas]
    columnas = [Columna("Fecha", FECHA, 1.1), Columna("Asiento", ancho=0.9), Columna("Concepto", ancho=4), Columna("Debe", DINERO, 1.2),
                Columna("Haber", DINERO, 1.2), Columna("Saldo", DINERO, 1.3)]
    return Tabla(
        f"Mayor de {m.cuenta} {m.nombre}".strip(), columnas, filas, _periodo(ejercicio, desde, hasta),
        totales=[None, None, "Totales", m.total_debe, m.total_haber, m.saldo_final],
    )


def tabla_balance(b: Balance, ejercicio: Ejercicio, *, nivel: int = NIVEL_SUBCUENTA, desde=None, hasta=None) -> Tabla:
    filas = [[f.cuenta, f.nombre, f.debe, f.haber, f.saldo_deudor or None, f.saldo_acreedor or None] for f in b.filas]
    columnas = [Columna("Cuenta", ancho=1), Columna("Nombre", ancho=4), Columna("Debe", DINERO, 1.3), Columna("Haber", DINERO, 1.3),
                Columna("Saldo deudor", DINERO, 1.3), Columna("Saldo acreedor", DINERO, 1.3)]
    deudor = sum((f.saldo_deudor for f in b.filas), CERO)
    acreedor = sum((f.saldo_acreedor for f in b.filas), CERO)
    sufijo = "" if nivel >= 8 else f" (cuentas de {nivel} dígito{'s' if nivel > 1 else ''})"
    return Tabla(
        f"Balance de sumas y saldos{sufijo}", columnas, filas, _periodo(ejercicio, desde, hasta),
        totales=[None, "Totales", b.total_debe, b.total_haber, deudor, acreedor],
    )


def tabla_libro_iva(libro: LibroIva, ejercicio: Ejercicio, *, desde=None, hasta=None) -> Tabla:
    filas = [
        [l.fecha, l.numero, l.numero_factura, l.tercero, l.nif, l.base, l.pct_iva, l.cuota, l.cuota_recargo or None,
         "Sí" if l.deducible else "No", l.base + l.cuota + l.cuota_recargo]
        for l in libro.lineas
    ]
    columnas = [Columna("Fecha", FECHA, 1.1), Columna("Nº", ENTERO, 0.6), Columna("Nº factura", ancho=1.5), Columna("Tercero", ancho=3),
                Columna("NIF", ancho=1.2), Columna("Base", DINERO, 1.2), Columna("% IVA", PORCENTAJE, 0.8), Columna("Cuota", DINERO, 1.1),
                Columna("Recargo", DINERO, 1.0), Columna("Deducible", ancho=0.9), Columna("Total", DINERO, 1.2)]
    recargo = sum((l.cuota_recargo for l in libro.lineas), CERO)
    total = libro.total_base + libro.total_cuota
    nombre = "emitidas" if libro.sentido == "E" else "recibidas"
    notas = [f"{pct:.2f} %: base {b:.2f} · cuota {c:.2f}" for pct, (b, c) in libro.por_tipo().items()]
    return Tabla(
        f"Libro de IVA — facturas {nombre}", columnas, filas, _periodo(ejercicio, desde, hasta),
        totales=[None, None, None, "Totales", None, libro.total_base, None, libro.total_cuota - recargo, recargo or None, None, total],
        notas=notas,
    )


def tabla_libro_bienes_inversion(lineas: list[LineaLibroBienes], ejercicio: Ejercicio) -> Tabla:
    filas = [
        [l.bien.codigo, l.bien.descripcion, l.bien.numero_factura_compra or "", l.bien.fecha_adquisicion, l.bien.fecha_funcionamiento, l.base,
         l.iva_soportado, l.plazo, l.primer_anio, l.ultimo_anio, l.pct_deducible_inicial, l.pct_deducible_ejercicio, l.regularizacion]
        for l in lineas
    ]
    columnas = [Columna("Código", ENTERO, 0.7), Columna("Bien", ancho=3), Columna("Nº factura", ancho=1.3), Columna("Adquisición", FECHA, 1.1),
                Columna("Funcionamiento", FECHA, 1.2), Columna("Base", DINERO, 1.1), Columna("IVA soportado", DINERO, 1.1), Columna("Años", ENTERO, 0.6),
                Columna("Desde", ENTERO, 0.7), Columna("Hasta", ENTERO, 0.7), Columna("% inicial", PORCENTAJE, 0.8), Columna("% del año", PORCENTAJE, 0.8),
                Columna("Regularización", DINERO, 1.2)]
    notas = [f"{l.bien.descripcion}: {a}" for l in lineas for a in l.avisos]
    return Tabla(
        "Libro de bienes de inversión (IVA)", columnas, filas, _periodo(ejercicio, None, None),
        totales=[None, "Total", None, None, None, sum((l.base for l in lineas), CERO), sum((l.iva_soportado for l in lineas), CERO), None, None, None, None, None,
                 sum((l.regularizacion for l in lineas), CERO)],
        notas=notas,
    )
