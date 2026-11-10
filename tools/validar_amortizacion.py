"""Contrasta la regla de amortización lineal con los 12 bienes del programa anterior (Empresa A).

Datos (fecha de funcionamiento, precio, % anual, amortización contable acumulada a 2025) leídos de las
pantallas "Elementos de inmovilizado" del programa anterior. Uso: python tools/validar_amortizacion.py
Regla: cuota anual = precio × % (redondeada); primer año prorrateado por días/365; último año = resto.
"""
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal as D

BIENES = {
    1: (date(2021, 10, 29), "3756.46", 4, "627.38"),
    2: (date(2021, 2, 8), "8852.00", 4, "1733.54"),
    3: (date(2014, 4, 15), "1100.00", 4, "515.46"),
    4: (date(2015, 5, 14), "1000.00", 4, "425.42"),
    5: (date(2014, 10, 27), "11200.00", 4, "5009.00"),
    6: (date(2015, 12, 17), "4886.50", 4, "1962.63"),
    7: (date(2014, 1, 28), "7290.00", 4, "3477.62"),
    8: (date(2014, 7, 13), "7604.55", 10, "7604.55"),
    9: (date(2015, 6, 30), "900.00", 10, "900.00"),
    10: (date(2015, 3, 20), "1150.00", 4, "496.17"),
    11: (date(2015, 3, 14), "3044.48", 10, "3044.48"),
    12: (date(2016, 3, 10), "1100.00", 10, "1079.27"),
}


def redondea(x, modo=ROUND_HALF_UP):
    return x.quantize(D("0.01"), rounding=modo)


def cuadro(f, precio, pct, modo):
    p, anual, acum, y, out = D(precio), redondea(D(precio) * pct / 100), D(0), f.year, {}
    while acum < p - D("0.005"):
        imp = anual
        if y == f.year:
            imp = redondea(anual * ((date(y, 12, 31) - f).days + 1) / 365, modo)
        if acum + imp > p or p - acum - imp < D("0.005"):
            imp = p - acum  # el último año absorbe el resto
        out[y] = imp
        acum += imp
        y += 1
    return out


if __name__ == "__main__":
    for nombre, modo in (("half_up", ROUND_HALF_UP), ("truncar", ROUND_DOWN)):
        dif = []
        for k, (f, p, pct, acc) in BIENES.items():
            s = sum(v for y, v in cuadro(f, p, pct, modo).items() if y <= 2025)
            if s != D(acc):
                dif.append((k, str(s), acc))
        print(f"{nombre}: {12 - len(dif)}/12 exactos; difieren {dif}")
    c = cuadro(*BIENES[1][:3], ROUND_DOWN)
    print("bien 1:", {y: str(v) for y, v in list(c.items())[:2]}, "... último", list(c.items())[-1])
