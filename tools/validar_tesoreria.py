"""Contrasta las reglas de tesorería de Gestión MGD con los datos DBF.

Uso: python tools/validar_tesoreria.py <carpeta_dbf>

1. Vtos.PENDIENTE = Vtos.IMPORTE - Σ Pagos.IMPORTE (por vencimiento)           [Vtos_RecalculaPendiente]
2. Movbanco.TOTAL = Σ Pagos.IMPORTE del movimiento                              [UnVto.PIDirecto]
3. Movbanco.SALDONUE = saldo acumulado del banco (orden fecha, clave, nº)       [RecalculaSaldoBanco]
4. Asiento del movimiento (ListaPagos.Asiento) = líneas B del Diario            [RegeneraAsientos.UnMovBanco]
"""
import sys
from collections import Counter, defaultdict
from decimal import Decimal as D

from dbfread import DBF


def leer(d, n):
    return list(DBF(f"{d}\\{n}.dbf", encoding="latin-1", ignore_missing_memofile=True))


def c(x):
    return D(str(round(x or 0, 2))).quantize(D("0.01"))


def main(d):
    vtos, pagos, mov, bancos = (leer(d, t) for t in ("Vtos", "Pagos", "Movbanco", "Bancos"))
    rec, emi, exa, dia = (leer(d, t) for t in ("Rec", "Emi", "Exapun", "Diario"))
    cta = lambda s: (s or "").strip()

    por_vto = defaultdict(D)
    por_mov = defaultdict(D)
    for p in pagos:
        por_vto[p["VTO"]] += c(p["IMPORTE"])
        por_mov[p["NUMERO"]] += c(p["IMPORTE"])

    # 1
    mal = [v["NUMERO"] for v in vtos if c(v["IMPORTE"]) - por_vto[v["NUMERO"]] != c(v["PENDIENTE"])]
    print(f"1. Vtos: pendiente = importe - pagos → {len(vtos) - len(mal)}/{len(vtos)} ; difieren {mal[:8]}")
    print("   tipos de vencimiento:", dict(Counter(v["TIPO"] for v in vtos)), "| signos importe:",
          dict(Counter((v["TIPO"], v["IMPORTE"] > 0) for v in vtos)))

    # 2
    mal = [m["NUMERO"] for m in mov if c(m["TOTAL"]) != por_mov[m["NUMERO"]]]
    print(f"2. Movbanco: total = Σ pagos → {len(mov) - len(mal)}/{len(mov)} ; difieren {mal[:8]}")

    # 3
    mal = 0
    for b in {m["BANCO"] for m in mov}:
        saldo = D(0)
        for m in sorted((m for m in mov if m["BANCO"] == b), key=lambda m: (m["FECHA"], m["CLAVE"] or "", m["NUMERO"])):
            saldo += c(m["TOTAL"])
            if saldo != c(m["SALDONUE"]):
                mal += 1
    print(f"3. Saldo corrido por banco: {len(mov) - mal}/{len(mov)} movimientos coinciden con SALDONUE")
    print("   bancos:", [(b["NUMERO"], cta(b["CUENTA"]), float(b["SALDOINI"] or 0), float(b["SALDOACT"] or 0)) for b in bancos])

    # 4
    cuenta_banco = {b["NUMERO"]: cta(b["CUENTA"]) for b in bancos}
    doc_cuenta = {}
    for r in rec:
        doc_cuenta[("R", r["NUMERO"])] = cta(r["PRCUENTA"])
    for e in emi:
        doc_cuenta[("E", e["NUMERO"])] = cta(e["CLCUENTA"])
    for x in exa:
        doc_cuenta[("X", x["NUMERO"])] = cta(x["CUENTA"])
    vto = {v["NUMERO"]: v for v in vtos}
    # Cuenta "pendiente de aplicar" (gParam:pteAplic) para pagos sin vencimiento ni cuenta directa
    pte_aplic = next(cta(r["TEXTO"]) for r in leer(d, "Param") if r["ETIQUETA"] == "PTE_APLIC")
    esperado = defaultdict(Counter)
    for m in mov:
        ps = [p for p in pagos if p["NUMERO"] == m["NUMERO"]]
        if m["BANCO"] == -3 and ps:
            banco_cta = cta(ps[0]["DIRSUBCTA"])
        else:
            banco_cta = cuenta_banco.get(m["BANCO"], "")
        total = c(m["TOTAL"])
        if total != 0:
            esperado[m["NUMERO"]][banco_cta] += total
        for p in ps:
            v = vto.get(p["VTO"])
            if p["VTO"] and v:
                cuenta = cta(v["CUENTA"]) or (cta(v["CUENTADEF"]) if v["TIPO"] == "B" else doc_cuenta.get((v["TIPO"], v["TPNUMERO"]), "?"))
            elif cta(p["DIRSUBCTA"]):
                cuenta = cta(p["DIRSUBCTA"])
            else:
                cuenta = pte_aplic
            esperado[m["NUMERO"]][cuenta] -= c(p["IMPORTE"])
    real = defaultdict(Counter)
    for r in dia:
        if r["TIPO"] == "B" and cta(r["CUENTA"]):
            real[r["NUMERO"]][cta(r["CUENTA"])] += c(r["IMPORTE"])
    bien, mal = 0, []
    for n in set(esperado) | set(real):
        a = {k: v for k, v in esperado[n].items() if v != 0}
        b = {k: v for k, v in real[n].items() if v != 0}
        if a == b:
            bien += 1
        else:
            mal.append((n, {k: str(v) for k, v in a.items()}, {k: str(v) for k, v in b.items()}))
    print(f"4. Asientos B regenerados = Diario → {bien}/{bien + len(mal)} ; difieren:")
    for m in mal[:6]:
        print("  ", m)


if __name__ == "__main__":
    main(sys.argv[1])
