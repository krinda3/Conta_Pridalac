"""Genera el icono del programa (`web/static/icono.ico` y `icono.png`) con el mismo dibujo que el favicon: un brote blanco sobre fondo verde.

    python tools/generar_icono.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

DESTINO = Path(__file__).resolve().parents[1] / "src" / "conta_pridalac" / "web" / "static"
VERDE = (140, 179, 62, 255)
BLANCO = (255, 255, 255, 255)


def _hoja(base, punta, bulto, k):
    """Polígono en forma de hoja (dos curvas de Bézier entre la base y la punta)."""
    (x0, y0), (x1, y1) = base, punta
    mx, my, dx, dy = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    largo = (dx * dx + dy * dy) ** 0.5
    nx, ny = -dy / largo * bulto, dx / largo * bulto
    puntos = []
    for lado in (1, -1):
        cx, cy = mx + lado * nx, my + lado * ny
        tramo = [((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x1, (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y1) for s in [i / 24 for i in range(25)]]
        puntos += tramo if lado == 1 else tramo[::-1]
    return [(x * k, y * k) for x, y in puntos]


def dibujar(lado: int = 512) -> Image.Image:
    k = lado / 32  # el favicon está dibujado en una cuadrícula de 32
    img = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=int(7 * k), fill=VERDE)
    d.line([(16 * k, 27 * k), (16 * k, 13 * k)], fill=BLANCO, width=max(int(2.2 * k), 1))  # tallo
    d.polygon(_hoja((16, 15), (25.5, 5), 3.4, k), fill=BLANCO)  # hoja derecha, grande
    d.polygon(_hoja((16, 21), (7, 13), 2.8, k), fill=BLANCO)  # hoja izquierda, más pequeña
    return img


def main() -> None:
    img = dibujar()
    DESTINO.mkdir(parents=True, exist_ok=True)
    img.save(DESTINO / "icono.png")
    img.save(DESTINO / "icono.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Iconos escritos en", DESTINO)


if __name__ == "__main__":
    main()
