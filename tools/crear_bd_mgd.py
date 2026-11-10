"""Crea las bases SQLite de la aplicación (una por empresa) desde las copias de Gestión MGD.

Uso: python tools/crear_bd_mgd.py [carpeta_de_bases]
Por defecto escribe en datos_locales/bd (no se versiona). Las carpetas de origen son las de los tests (variable CONTA_MGD_2021 y
las subcarpetas de cada empresa); si no están, avisa. Si la base ya existe se sustituye.
"""
import os
import sys
from pathlib import Path

from conta_pridalac.db.sesion import crear_esquema, crear_motor, nueva_sesion  # noqa: E402
from conta_pridalac.migracion.mgd import cargar_mgd  # noqa: E402
from conta_pridalac.servicios.adjuntos import AlmacenAdjuntos, trasladar_a_almacen  # noqa: E402
from conta_pridalac.db.modelos import Ejercicio  # noqa: E402


RAIZ = Path(__file__).resolve().parents[1]
EMPRESAS_MGD_2021 = {
    "empresa_a": {"codigo": 11, "nombre": "Empresa A"},
    "empresa_b": {"codigo": 12, "nombre": "Empresa B"},
}


def _carpeta_empresa(clave: str) -> Path:
    """Dónde está la copia de MGD de cada empresa (las mismas variables de entorno que usan los tests)."""
    if clave == "empresa_a":
        return Path(os.environ.get("CONTA_MGD_2021", r"D:\Proyectos\GestionMGD Access\BBDD 2021"))
    return Path(os.environ.get("CONTA_MGD_EMPRESA_B_2021", RAIZ / "datos_locales" / "mgd_empresa_b_2021"))


def main(destino: str | None = None) -> None:
    carpeta = Path(destino) if destino else RAIZ / "datos_locales" / "bd"
    carpeta.mkdir(parents=True, exist_ok=True)
    almacen = AlmacenAdjuntos(carpeta.parent / "justificantes")
    for clave, datos in EMPRESAS_MGD_2021.items():
        origen = _carpeta_empresa(clave)
        if not (origen / "Diario.dbf").exists():
            print(f"{clave}: no hay datos MGD en {origen}")
            continue
        fichero = carpeta / f"{clave}.sqlite"
        fichero.unlink(missing_ok=True)
        motor = crear_motor(fichero)
        crear_esquema(motor)
        sesion = nueva_sesion(motor)
        r = cargar_mgd(sesion, origen, codigo_empresa=datos["codigo"], nombre_empresa=datos["nombre"], anio=2021)
        copiados = trasladar_a_almacen(sesion, almacen, sesion.get(Ejercicio, r.ejercicio_id), origen)
        sesion.commit()
        print(f"{clave}: {r.asientos} asientos, {r.adjuntos} justificantes ({copiados} copiados) -> {fichero}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
