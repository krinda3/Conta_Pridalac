"""Inventario del diseño de registro del modelo 200 (`DR200e25.xls`) cruzado con los `.200` ya presentados.

Para cada una de las páginas del diseño cuenta los campos, dice si la página aparece en los ficheros reales y cuántos de sus campos llevan valor.
Genera dos ficheros en la carpeta de salida:
  - `inventario_DR200_resumen.md`: una fila por página (qué es, si se usa y qué falta por decidir);
  - `inventario_DR200_campos.csv`: una fila por campo (los ~6.800), para filtrar en Excel.

Uso:  python tools/inventario_dr200.py <DR200e25.xls> [carpeta_AEAT=AEAT] [salida=docs/modelo200]
Necesita `xlrd` (solo para leer el .xls; no es dependencia del proyecto): pip install xlrd
"""
from __future__ import annotations

import csv
import glob
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import xlrd
except ImportError:  # pragma: no cover
    sys.exit("Falta xlrd: pip install xlrd")

# Palabras del título que indican un régimen o entidad que no es el de Empresa A ni Empresa B (sociedades limitadas en régimen general)
NO_APLICA = {
    "cooperativ": "cooperativas", "zec": "zona especial canaria", "socimi": "SOCIMI", "naviera": "entidades navieras / buques", "buques": "entidades navieras / buques",
    "agrupaciones": "AIE / UTE", "u.t.e": "AIE / UTE", "ute": "AIE / UTE", "canarias": "régimen de Canarias (RIC/ZEC)", "balears": "régimen de Illes Balears (RIB)",
    "aseguradora": "entidades aseguradoras", "crédito": "entidades de crédito", "inversión colectiva": "instituciones de inversión colectiva", "garantía recíproca": "garantía recíproca",
    "no residentes": "no residentes", "establecimiento": "establecimientos permanentes", "fusiones": "reestructuraciones", "consolidación": "grupos fiscales / consolidación",
    "hidrocarburos": "hidrocarburos", "minería": "minería", "forales": "diputaciones forales / Navarra", "fondos de pensiones": "fondos de pensiones", "capital-riesgo": "capital-riesgo",
}


# Clasificación a mano de las páginas que no aparecen en ningún fichero real (código de página → decisión). Lo que no está aquí se trata como «SIN CLASIFICAR».
OPCIONALES = {  # pueden aplicar a una SL pyme algún año: se generan si hay datos (entrada manual; por defecto sin página)
    "15B00": "doble imposición interna (DT 23.ª)", "16000": "doble imposición internacional", "16C00": "límites de deducciones (si hay deducciones)",
    "17000": "deducciones por incentivos (I+D+i, innovación…)", "18000": "deducciones por incentivos", "18B00": "producciones cinematográficas extranjeras",
    "18C00": "donativos a entidades sin fines de lucro", "19000": "I+D+i excluidas de límite", "19B00": "I+D+i excluidas de límite",
    "20B00": "reserva de nivelación", "20C00": "conversión de activos por impuesto diferido en crédito exigible", "23000": "fusión, escisión, canje de valores",
    "25000": "transparencia fiscal internacional", "26B00": "cambio de criterios contables", "26C00": "pérdidas por deterioro (art. 13.1 LIS)",
    "26D00": "asimetrías híbridas", "26F00": "transparencia fiscal internacional (art. 100)", "26G00": "operaciones a plazos (DT 1.ª)",
}
NO_APLICAN = {  # por tipo de entidad o régimen: se omiten
    "16B00": "Canarias", "22000": "cooperativas", "22B00": "Illes Balears", "24000": "AIE y UTE", "26000": "tributación conjunta con Diputaciones Forales",
    "26E00": "exención de valores de entidades no residentes", **{f"{n}000": "entidades de crédito (contabilidad Banco de España)" for n in (27, 28, 29, 30, 31, 32, 33)}, "27B00": "entidades de crédito",
    **{f"{n}000": "entidades aseguradoras" for n in range(34, 44)}, **{f"{n}000": "instituciones de inversión colectiva" for n in range(44, 49)},
    **{f"{n}000": "sociedades de garantía recíproca" for n in range(49, 55)},
}
CABECERA = "DP200000"  # no es una página: el encabezado del fichero (<T2000…>, <AUX>…)


def leer_diseno(ruta_xls: Path) -> dict[str, dict]:
    libro = xlrd.open_workbook(str(ruta_xls))
    paginas: dict[str, dict] = {}
    for nombre in libro.sheet_names():
        hoja = libro.sheet_by_name(nombre)
        filas = [[str(c.value).replace("\n", " ").strip() for c in hoja.row(r)] for r in range(hoja.nrows)]
        cabecera = next((f for f in filas if f and f[0] == "Nº"), [])
        con_com = "Com" in cabecera  # algunas hojas llevan una columna «Com» entre el tipo y la descripción
        campos, codigo, notas = [], None, []
        for fila in filas:
            fila = fila + [""] * 9
            if con_com:
                fila = fila[:4] + fila[5:]
            try:
                n, pos, lon = int(float(fila[0])), int(float(fila[1])), int(float(fila[2]))
            except ValueError:
                texto = " ".join(x for x in fila if x).strip()
                if texto and not texto.startswith(("Nº", "Agencia Tributaria", "Modelo 200", "vers.", "Impuesto sobre")):
                    notas.append(texto)
                continue
            campos.append(dict(n=n, pos=pos, lon=lon, tipo=fila[3], desc=fila[4], validacion=fila[5], contenido=fila[6]))
            if codigo is None and "Página" in fila[4] and "Constante" in fila[6]:
                m = re.search(r'"(\w+)"', fila[6])
                codigo = m.group(1) if m else None
        paginas[nombre.strip()] = dict(hoja=nombre.strip(), codigo=codigo, campos=campos, notas=notas)
    return paginas


def titulo(campos: list[dict], hoja: str) -> str:
    primeros = Counter(c["desc"].split(" - ")[0].strip() for c in campos if " - " in c["desc"])
    return primeros.most_common(1)[0][0] if primeros else f"({hoja})"


def leer_reales(carpeta: Path) -> dict[str, list[tuple[str, str]]]:
    """{código de página: [(fichero, texto de la página)]} de todos los .200 de la carpeta."""
    salida: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for f in sorted(glob.glob(str(carpeta / "C000?_200_20??.200"))):
        cuerpo = open(f, encoding="latin-1").read()
        cuerpo = cuerpo[cuerpo.index("</AUX>") + 6:]
        for m in re.finditer(r"<T200(\w{5})>(.*?)</T200\1>", cuerpo, flags=re.S):
            salida[m.group(1)].append((Path(f).name[:5] + Path(f).name[10:14], "<T200" + m.group(1) + ">" + m.group(2)))
    return salida


def con_valor(tipo: str, texto: str) -> bool:
    limpio = texto.strip()
    if not limpio:
        return False
    if tipo.startswith(("N", "Num")) and not limpio.strip("0+-N "):
        return False
    return True


def main() -> None:
    ruta_xls = Path(sys.argv[1])
    carpeta_aeat = Path(sys.argv[2] if len(sys.argv) > 2 else "AEAT")
    salida = Path(sys.argv[3] if len(sys.argv) > 3 else "docs/modelo200")
    salida.mkdir(parents=True, exist_ok=True)
    diseno, reales = leer_diseno(ruta_xls), leer_reales(carpeta_aeat)
    n_ficheros = len(glob.glob(str(carpeta_aeat / "C000?_200_20??.200")))
    resumen, filas_csv = [], []
    for hoja, p in diseno.items():
        codigo, campos = p["codigo"], p["campos"]
        instancias = reales.get(codigo or "", [])
        ficheros = sorted({f for f, _ in instancias})
        tit = titulo(campos, hoja)
        con_val = 0
        for c in campos:
            constante = c["contenido"].startswith(("Constante", "BLANCOS", "En blanco"))
            ejemplos, en = [], set()
            for fichero, texto in instancias:
                v = texto[c["pos"] - 1: c["pos"] - 1 + c["lon"]]
                if con_valor(c["tipo"], v):
                    en.add(fichero)
                    if len(ejemplos) < 2:
                        ejemplos.append(v.strip()[:30])
            casilla = (re.search(r"\[(\d{5})\]", c["desc"]) or [None, ""])[1]
            if not instancias:
                clase = "página no usada"
            elif constante:
                clase = "constante"
            elif en:
                clase = "con valor en los reales"
            else:
                clase = "siempre cero/blanco en los reales"
            con_val += bool(en) and not constante
            filas_csv.append([hoja, codigo or "", tit, c["n"], c["pos"], c["lon"], c["tipo"], casilla, c["desc"], c["validacion"], c["contenido"], clase, len(en), " | ".join(ejemplos)])
        if hoja == CABECERA:
            decision = "CABECERA del fichero (no es una página): se escribe siempre"
        elif instancias:
            decision = "SE USA: rellenar todos sus campos"
        elif codigo in OPCIONALES:
            decision = f"OPCIONAL, entrada manual ({OPCIONALES[codigo]}): solo si hay datos"
        elif codigo in NO_APLICAN:
            decision = f"NO APLICA ({NO_APLICAN[codigo]}): se omite"
        else:
            decision = "SIN CLASIFICAR: hay que decidir"
        resumen.append((hoja, codigo or "-", tit, len(campos), len(ficheros), con_val, len(p["notas"]), decision))
    with open(salida / "inventario_DR200_campos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["hoja", "página", "título", "nº", "posición", "longitud", "tipo", "casilla", "descripción", "validación", "contenido", "clase", "ficheros_con_valor", "ejemplos"])
        w.writerows(filas_csv)
    usadas = [r for r in resumen if r[4]]
    no_usadas = [r for r in resumen if not r[4]]
    lineas = [
        f"# Inventario del diseño de registro del modelo 200 (`{ruta_xls.name}`)", "",
        f"Cruzado con {n_ficheros} ficheros `.200` presentados (Empresa A y Empresa B, 2021–2025). Detalle campo a campo en `inventario_DR200_campos.csv` (filtrar por `clase`).", "",
        f"- Hojas (páginas) del diseño: **{len(resumen)}**; campos: **{sum(r[3] for r in resumen)}**.",
        f"- Páginas que aparecen en algún fichero real: **{len(usadas)}** ({sum(r[3] for r in usadas)} campos).",
        f"- Páginas que no aparecen en ninguno: **{len(no_usadas)}** ({sum(r[3] for r in no_usadas)} campos).", "",
        "## Páginas que aparecen en los ficheros reales", "",
        "| Hoja | Página | Título | Campos | Ficheros | Con valor | Notas | Decisión |", "|---|---|---|---:|---:|---:|---:|---|",
    ]
    lineas += [f"| {h} | {c} | {t} | {n} | {fi}/{n_ficheros} | {cv} | {no} | {d} |" for h, c, t, n, fi, cv, no, d in usadas]
    lineas += ["", "## Páginas que no aparecen en ninguno", "", "| Hoja | Página | Título | Campos | Notas | Decisión |", "|---|---|---|---:|---:|---|"]
    lineas += [f"| {h} | {c} | {t} | {n} | {no} | {d} |" for h, c, t, n, fi, cv, no, d in no_usadas]
    (salida / "inventario_DR200_resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    sin = [r for r in no_usadas if r[7].startswith("SIN CLASIFICAR")]
    print(f"{len(resumen)} hojas; usadas {len(usadas)}; no usadas {len(no_usadas)} (sin clasificar: {len(sin)}); campos {len(filas_csv)}")


if __name__ == "__main__":
    main()
