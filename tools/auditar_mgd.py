"""Carga una copia de Gestión MGD en una base temporal y ejecuta la auditoría de integridad.

Uso:
    python tools/auditar_mgd.py <carpeta_dbf> <codigo_empresa> <nombre> <anio> [informe.txt]

Imprime el resumen por pantalla y, si se indica `informe.txt`, escribe ahí todos los hallazgos. El informe puede contener
datos de negocio: guárdelo en `datos_locales/` (ignorada por git), no en el repositorio.
"""
import sys
from collections import Counter

from conta_pridalac.auditoria import ERROR, auditar
from conta_pridalac.db.modelos import Ejercicio
from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion
from conta_pridalac.migracion.mgd import cargar_mgd


def main(carpeta, codigo, nombre, anio, informe=None):
    motor = crear_motor(None)
    crear_esquema(motor)
    sesion = nueva_sesion(motor)
    carga = cargar_mgd(sesion, carpeta, codigo_empresa=int(codigo), nombre_empresa=nombre, anio=int(anio))
    sesion.commit()
    hallazgos = auditar(sesion, sesion.get(Ejercicio, carga.ejercicio_id))

    por_codigo = Counter((h.gravedad, h.codigo) for h in hallazgos)
    errores = sum(1 for h in hallazgos if h.gravedad == ERROR)
    lineas = [
        f"AUDITORÍA DE INTEGRIDAD · {nombre} · ejercicio {anio}",
        f"Cargados: {carga.asientos} asientos, {carga.facturas} facturas, {carga.movimientos} movimientos de banco, {carga.adjuntos} justificantes",
        f"Hallazgos: {len(hallazgos)} ({errores} errores, {len(hallazgos) - errores} avisos)",
        "",
    ]
    for (gravedad, codigo_h), n in sorted(por_codigo.items(), key=lambda kv: (kv[0][0] != ERROR, kv[0][1])):
        lineas.append(f"[{gravedad}] {codigo_h}: {n}")
        lineas += [f"    {h.referencia:<14} {h.mensaje}" for h in hallazgos if (h.gravedad, h.codigo) == (gravedad, codigo_h)]
    texto = "\n".join(lineas)
    print(texto if len(texto) < 6000 else "\n".join(lineas[:4] + [f"[{g}] {c}: {n}" for (g, c), n in por_codigo.items()]))
    if informe:
        with open(informe, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
        print(f"\nInforme completo en {informe}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
