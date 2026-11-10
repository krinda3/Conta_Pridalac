"""`python -m conta_pridalac.web` arranca la aplicación en http://127.0.0.1:8000 (sólo accesible desde este equipo)."""
import argparse
import os
import socket
import sys
import threading
import time

import uvicorn

from conta_pridalac.web import datos as datos_web
from conta_pridalac.web.app import crear_app
from conta_pridalac.web.config import Configuracion

GRACIA_INICIAL = 180  # segundos que se espera a que se abra la primera página antes de cerrarse sola (con --autoapagar)
SIN_LATIDO = 180  # segundos sin señal de ninguna página abierta para cerrarse sola (con --autoapagar); el navegador avisa cada 15 s, pero ralentiza las pestañas ocultas


def puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", puerto))
        except OSError:
            return False
    return True


def vigilar(app, servidor: uvicorn.Server) -> None:
    """Cierra el programa cuando ya no hay ninguna página abierta (la señal la manda `app.js`)."""
    inicio = time.monotonic()
    while not servidor.should_exit:
        time.sleep(5)
        ultimo = getattr(app.state, "ultimo_latido", None)
        if (ultimo is None and time.monotonic() - inicio > GRACIA_INICIAL) or (ultimo is not None and time.monotonic() - ultimo > SIN_LATIDO):
            servidor.should_exit = True


def main() -> None:
    p = argparse.ArgumentParser(description="Conta Pridalac — contabilidad local")
    p.add_argument("--datos", help="Carpeta con las bases <empresa>.sqlite (por defecto datos_locales/bd o la variable CONTA_DATOS)")
    p.add_argument("--almacen", help="Carpeta de los justificantes (por defecto junto a las bases)")
    p.add_argument("--puerto", type=int, default=int(os.environ.get("CONTA_PUERTO", "8000")))
    p.add_argument("--sin-certificado", action="store_true", help="No exigir certificado digital para trabajar con una empresa (sólo para pruebas)")
    p.add_argument("--sin-candado", action="store_true", help="No poner el candado de la carpeta de datos (sólo para pruebas: permite abrir los mismos datos desde dos sitios a la vez)")
    p.add_argument("--autoapagar", action="store_true", help="Se cierra sola cuando se cierra la última pestaña del programa (lo usa el icono del escritorio)")
    a = p.parse_args()
    if not puerto_libre(a.puerto):
        print(f"El puerto {a.puerto} ya está ocupado: seguramente el programa ya está en marcha (ábralo en http://127.0.0.1:{a.puerto}) "
              f"o puede cerrarlo con `python -m conta_pridalac.lanzador --parar --puerto {a.puerto}`. Para otra copia, use --puerto con otro número.", file=sys.stderr)
        raise SystemExit(1)
    config = Configuracion(**({"datos": a.datos} if a.datos else {}), **({"almacen": a.almacen} if a.almacen else {}), exigir_certificado=not a.sin_certificado, usar_candado=not a.sin_candado)
    app = crear_app(config)
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.puerto, timeout_graceful_shutdown=3))
    app.state.servidor = servidor  # para poder cerrar el programa desde su pantalla o con `conta_pridalac.lanzador --parar`
    if a.autoapagar:
        threading.Thread(target=vigilar, args=(app, servidor), daemon=True).start()
    try:
        servidor.run()
    finally:
        datos_web.soltar(app)  # al cerrar el programa se suelta el candado de la carpeta de datos (si lo tiene este programa)
    os._exit(0)  # nada se queda a medias (cada petición confirma sus cambios); así no quedan procesos vivos que mantengan el puerto o la base abiertos


if __name__ == "__main__":
    main()
