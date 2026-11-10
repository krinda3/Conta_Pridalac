"""Asientos de facturas recibidas y emitidas (docs/pseudocodigo/01_asientos_diario.md §6.1, §6.2 y §7).

Función pura sobre el modelo: devuelve, por cada asiento de la factura, `{código de cuenta: importe}` con signo
(positivo = debe). Las líneas de la misma cuenta se agrupan y las de importe 0 desaparecen (MGD con
`NO_REDUCE_APUNTES = 'N'`, que es la configuración de las dos empresas).

Verificado con MGD 2021: facturas recibidas 56/56 (Empresa A) y 190/190 (Empresa B); emitidas 1/1 y 21/21.
No cubierto por los datos: autofacturas, IVA no deducible, recargo de equivalencia ni varios asientos por factura.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from conta_pridalac.db.modelos import Factura
from conta_pridalac.domain.errores import ErrorContable

CERO = Decimal("0.00")

# Posición fija de las dos líneas base: en emitidas Cliente (1.ª) e Ingreso (2.ª); en recibidas Gasto (1.ª) y Proveedor (2.ª)
_CONTRA = {"E": "CI", "R": "GP"}


def total_esperado(factura: Factura) -> Decimal | None:
    """Total que deben dar las líneas: Σ (base + IVA + recargo) y, en recibidas, + los ajustes (p. ej. retención de IRPF, negativa).

    Verificado con la factura recibida nº 23 de Empresa A: 877,25 + (−108,75) = 768,50. Devuelve `None` si no hay líneas de IVA
    o si es una emitida con ajustes (su efecto sobre el total no está verificado con datos).
    """
    if not factura.ivas:
        return None
    if factura.sentido == "E" and factura.ajustes:
        return None
    suma = sum((i.base + i.cuota_iva + i.cuota_recargo for i in factura.ivas), CERO)
    if factura.sentido == "R":
        suma += sum((a.importe for a in factura.ajustes), CERO)
    return suma


def asientos_de_factura(factura: Factura) -> list[Counter]:
    """Un `Counter` por asiento: el 1.º es el principal (`sub = 0`); los siguientes, `sub = 1, 2…`."""
    if factura.cuenta_tercero is None or factura.cuenta_contrapartida is None:
        raise ErrorContable("Falta la cuenta del tercero o la de gasto/ingreso")
    tercero, contra = factura.cuenta_tercero.codigo, factura.cuenta_contrapartida.codigo
    ivas_computables = [i for i in factura.ivas if i.deducible]
    iva_total = sum((i.cuota_iva + i.cuota_recargo for i in ivas_computables), CERO)
    neto = factura.total - iva_total

    # Líneas base [primera cuenta, segunda cuenta]: cuentas e importes con signo
    if factura.sentido == "R":
        base = [[contra, neto], [tercero, -factura.total]]
        signo_iva = 1
    else:
        base = [[tercero, factura.total], [contra, -neto]]
        signo_iva = -1

    ajustes_por_asiento = _repartir_ajustes(factura)
    numero_asientos = max(len(ajustes_por_asiento), 1)

    resultados: list[Counter] = []
    for n in range(numero_asientos):
        if n == 0:
            lineas = [(base[0][0], base[0][1]), (base[1][0], base[1][1])]
            for i in ivas_computables:
                if i.cuota_iva:
                    if i.cuenta_iva is None:
                        raise ErrorContable(f"Falta la cuenta de IVA del tipo {i.pct_iva}% (cuota {i.cuota_iva})")
                    lineas.append((i.cuenta_iva.codigo, signo_iva * i.cuota_iva))
                if i.cuota_recargo:
                    if i.cuenta_recargo is None:
                        raise ErrorContable(f"Falta la cuenta de recargo de equivalencia del tipo {i.pct_recargo}%")
                    lineas.append((i.cuenta_recargo.codigo, signo_iva * i.cuota_recargo))
        else:
            lineas = [(base[0][0], CERO), (base[1][0], CERO)]
        importes = {0: lineas[0][1], 1: lineas[1][1]}
        extra = []
        for ajuste in ajustes_por_asiento[n] if ajustes_por_asiento else []:
            extra.append((ajuste.cuenta.codigo, ajuste.importe))
            pos = _CONTRA[factura.sentido].index(ajuste.contra)
            importes[pos] -= ajuste.importe
        lineas[0], lineas[1] = (lineas[0][0], importes[0]), (lineas[1][0], importes[1])
        resultados.append(_reducir(lineas + extra))
    return resultados


def _repartir_ajustes(factura: Factura) -> list[list]:
    """Agrupa los ajustes por asiento: un ajuste con `cambio_asiento` abre el siguiente asiento (BaseApuntesER)."""
    if not factura.ajustes:
        return []
    grupos: list[list] = [[]]
    for ajuste in sorted(factura.ajustes, key=lambda a: a.orden):
        if ajuste.cambio_asiento:
            grupos.append([])
        grupos[-1].append(ajuste)
    return grupos


def _reducir(lineas: list[tuple[str, Decimal]]) -> Counter:
    total: Counter = Counter()
    for cuenta, importe in lineas:
        total[cuenta] += importe
    return Counter({c: v for c, v in total.items() if v != 0})
