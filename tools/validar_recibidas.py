"""Valida la regla de asientos de facturas recibidas contra el Diario real.

Uso: python tools/validar_recibidas.py <carpeta_dbf>
Regenera cada asiento R desde Rec + Eriva (+ Ajustes) y lo compara con Diario.
"""
import sys
from collections import Counter, defaultdict

from dbfread import DBF


def leer(d, nombre):
    return list(DBF(f"{d}\\{nombre}.dbf", encoding="latin-1", ignore_missing_memofile=True))


def n(x):
    return x or 0


def main(d):
    dia, rec, eri, aj = (leer(d, t) for t in ("Diario", "Rec", "Eriva", "Ajustes"))
    iva = defaultdict(list)
    for e in eri:
        if e["TIPO"] == "S":  # soportado
            iva[e["FACTURA"]].append(e)
    ajustes = defaultdict(list)
    for a in aj:
        if a["TIPO"] == "R":
            ajustes[a["NUMERO"]].append(a)
    real = defaultdict(Counter)
    for r in dia:
        if r["TIPO"] == "R" and str(r["CUENTA"] or "").strip() and not r["MULTI"].strip():
            real[r["NUMERO"]][r["CUENTA"].strip()] += round(n(r["IMPORTE"]), 2)

    bien, mal = 0, []
    for f in rec:
        num, total = f["NUMERO"], n(f["TOTAL"])
        neto = total
        for e in iva[num]:
            if e["NODEDU"] != "S":
                neto -= n(e["IVA_TOTAL"]) + n(e["RE_TOTAL"])
        ap = Counter()
        ap[f["TOCUENTA"].strip()] += neto
        ap[f["PRCUENTA"].strip()] -= total
        for e in iva[num]:
            if e["NODEDU"] != "S":
                ap[e["IVA_CTA"].strip()] += n(e["IVA_TOTAL"])
                if n(e["RE_TOTAL"]):
                    ap[e["RE_CTA"].strip()] += n(e["RE_TOTAL"])
        for a in ajustes[num]:  # solo asiento 1 (sin CAMBIOAS)
            ap[a["CUENTA"].strip()] += n(a["IMPORTE"])
            fija = f["TOCUENTA"] if a["CONTRA"] == "G" else f["PRCUENTA"]
            ap[fija.strip()] -= n(a["IMPORTE"])
        a_ = {k: round(v, 2) for k, v in ap.items() if abs(v) > 0.001}
        b_ = {k: v for k, v in real[num].items() if abs(v) > 0.001}
        if a_ == b_:
            bien += 1
        else:
            mal.append((num, a_, b_))
    print(f"coinciden {bien} de {len(rec)}")
    for m in mal:
        print("difiere:", m)


if __name__ == "__main__":
    main(sys.argv[1])
