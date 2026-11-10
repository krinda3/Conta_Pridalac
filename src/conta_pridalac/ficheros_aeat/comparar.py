"""Qué cambia entre dos versiones de un diseño de registro de la AEAT.

Trabaja sobre los JSON de `ficheros_aeat/` (`dr200_2025.json` y los demás `dr*.json`), que se sacan del Excel oficial con `tools/dr200_a_json.py` o `tools/extraer_diseno_aeat.py`.
Un diseño son páginas (hojas del Excel) con campos de posición fija. Se identifica cada campo por su **casilla** cuando la tiene y es única en la página, y por su **posición** si no;
así un campo que se mueve de sitio se detecta como «movido» y no como un alta y una baja.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Cambio:
    pagina: str
    clave: str  # «casilla 00552» o «posición 166»
    tipo: str  # alta · baja · movido · tamaño · tipo · texto · contenido
    antes: str = ""
    despues: str = ""
    descripcion: str = ""


@dataclass
class Informe:
    paginas_nuevas: list[str] = field(default_factory=list)
    paginas_quitadas: list[str] = field(default_factory=list)
    cambios: list[Cambio] = field(default_factory=list)
    paginas_iguales: int = 0

    @property
    def sin_cambios(self) -> bool:
        return not (self.paginas_nuevas or self.paginas_quitadas or self.cambios)

    def por_tipo(self) -> dict[str, int]:
        cuenta: dict[str, int] = {}
        for c in self.cambios:
            cuenta[c.tipo] = cuenta.get(c.tipo, 0) + 1
        return cuenta

    def texto(self, limite_por_pagina: int = 60) -> str:
        if self.sin_cambios:
            return "Los dos diseños son iguales (páginas, campos, posiciones, tipos y textos).\n"
        lineas = [f"Páginas iguales: {self.paginas_iguales} · nuevas: {len(self.paginas_nuevas)} · quitadas: {len(self.paginas_quitadas)} · campos con cambios: {len(self.cambios)} ({', '.join(f'{k} {v}' for k, v in sorted(self.por_tipo().items()))})", ""]
        if self.paginas_nuevas:
            lineas.append("Páginas NUEVAS: " + ", ".join(self.paginas_nuevas))
        if self.paginas_quitadas:
            lineas.append("Páginas QUITADAS: " + ", ".join(self.paginas_quitadas))
        por_pagina: dict[str, list[Cambio]] = {}
        for c in self.cambios:
            por_pagina.setdefault(c.pagina, []).append(c)
        for pagina, lista in por_pagina.items():
            lineas += ["", f"== {pagina}: {len(lista)} cambio(s)"]
            for c in lista[:limite_por_pagina]:
                detalle = f"{c.antes!r} → {c.despues!r}" if c.antes or c.despues else ""
                lineas.append(f"   {c.tipo:<9} {c.clave:<16} {detalle:<40} {c.descripcion[:90]}")
            if len(lista) > limite_por_pagina:
                lineas.append(f"   … y {len(lista) - limite_por_pagina} más")
        return "\n".join(lineas) + "\n"


def cargar(ruta: str | Path) -> dict[str, list[dict]]:
    """El diseño de un JSON de `ficheros_aeat/` como {página: [campos]}, sea del formato del 200 o de los demás."""
    crudo = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if "paginas" in crudo:  # formato del 200: {"version", "cabecera", "paginas": {código: {"hoja", "campos": [...]}}}
        return {codigo: p["campos"] for codigo, p in crudo["paginas"].items()}
    return {hoja: campos for hoja, campos in crudo.items() if isinstance(campos, list)}  # formato de los demás: {hoja: [campos]}


def _clave(campo: dict, casillas_unicas: set[str]) -> str:
    casilla = campo.get("casilla")
    return f"casilla {casilla}" if casilla and casilla in casillas_unicas else f"posición {campo['pos']}"


def _indice(campos: list[dict]) -> dict[str, dict]:
    cuenta: dict[str, int] = {}
    for c in campos:
        if c.get("casilla"):
            cuenta[c["casilla"]] = cuenta.get(c["casilla"], 0) + 1
    unicas = {k for k, v in cuenta.items() if v == 1}
    return {_clave(c, unicas): c for c in campos}


def _sin_ruido(texto: str | None) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def comparar(viejo: dict[str, list[dict]], nuevo: dict[str, list[dict]]) -> Informe:
    informe = Informe(paginas_nuevas=sorted(set(nuevo) - set(viejo)), paginas_quitadas=sorted(set(viejo) - set(nuevo)))
    for pagina in sorted(set(viejo) & set(nuevo)):
        antes, despues = _indice(viejo[pagina]), _indice(nuevo[pagina])
        cambios: list[Cambio] = []
        for clave in antes.keys() - despues.keys():
            cambios.append(Cambio(pagina, clave, "baja", str(antes[clave]["pos"]), "", _sin_ruido(antes[clave].get("desc"))))
        for clave in despues.keys() - antes.keys():
            cambios.append(Cambio(pagina, clave, "alta", "", str(despues[clave]["pos"]), _sin_ruido(despues[clave].get("desc"))))
        for clave in sorted(antes.keys() & despues.keys()):
            a, d = antes[clave], despues[clave]
            desc = _sin_ruido(d.get("desc"))
            if a["pos"] != d["pos"]:
                cambios.append(Cambio(pagina, clave, "movido", f"pos {a['pos']}", f"pos {d['pos']}", desc))
            if a["lon"] != d["lon"]:
                cambios.append(Cambio(pagina, clave, "tamaño", f"lon {a['lon']}", f"lon {d['lon']}", desc))
            if a["tipo"] != d["tipo"]:
                cambios.append(Cambio(pagina, clave, "tipo", a["tipo"], d["tipo"], desc))
            if _sin_ruido(a.get("contenido")) != _sin_ruido(d.get("contenido")) or _sin_ruido(a.get("validacion")) != _sin_ruido(d.get("validacion")):
                cambios.append(Cambio(pagina, clave, "contenido", _sin_ruido(a.get("contenido"))[:30], _sin_ruido(d.get("contenido"))[:30], desc))
            if _sin_ruido(a.get("desc")) != _sin_ruido(d.get("desc")):
                cambios.append(Cambio(pagina, clave, "texto", _sin_ruido(a.get("desc"))[:30], _sin_ruido(d.get("desc"))[:30], desc))
        if cambios:
            informe.cambios += sorted(cambios, key=lambda c: (c.clave, c.tipo))
        else:
            informe.paginas_iguales += 1
    return informe
