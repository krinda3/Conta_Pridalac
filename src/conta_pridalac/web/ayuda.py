"""La ayuda del programa: temas escritos en Markdown (`web/ayuda/NN_tema.md`), un buscador y dos partes que genera el propio programa para no desfasarse
(las pantallas del menú con su explicación y los avisos de la auditoría con lo que significan y cómo se corrigen).

Cada tema es un fichero `NN_slug.md`: el número da el orden, el slug la dirección (`/ayuda/trimestre`) y el primer título `# …` el nombre. Dentro de un tema:
- `@@MENU@@` y `@@AUDITORIA@@` se sustituyen por lo que genera el programa;
- los enlaces `[texto](tema:slug)` o `[texto](tema:slug#ancla)` van a otro tema; `[texto](pantalla:nombre)` va a esa pantalla del programa (si se está dentro de una empresa);
- el Markdown admitido es el básico: títulos `##` y `###` (con ancla), párrafos, listas con `-` o `1.`, tablas con `|`, citas `>` (avisos), bloques de código, **negrita**, *cursiva* y `código`.
Todo lo demás se escapa: el contenido nunca puede meter HTML.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

DIRECTORIO = Path(__file__).with_name("ayuda")

# pantalla → tema de la ayuda que la explica (lo que no está aquí va al índice)
TEMA_DE_CAJA = {"trimestre": "trimestre", "facturas": "facturas", "tesoreria": "tesoreria", "asientos": "contabilidad", "inmovilizado": "contabilidad", "datos": "facturas", "listados": "contabilidad",
                "liquidaciones": "modelos", "sociedades": "sociedades", "mercantil": "mercantil", "ejercicio": "cierre"}
PANTALLAS_GLOBALES = {"normativa": "/normativa", "programa": "/programa", "datos": "/datos"}  # pantallas de toda la instalación (véase `web/sistema.py`)
TEMA_DE_PANTALLA = {"extractos": "tesoreria", "conciliacion": "trimestre", "emitidas-trimestre": "trimestre", "conciliar-pagos": "tesoreria", "lineas-sin-factura": "tesoreria", "cuadre-bancos": "tesoreria",
                    "correspondencias": "facturas", "modelo-202": "sociedades", "liquidacion-iva": "modelos", "auditoria": "cierre", "normativa": "cierre", "programa": "cierre"}


@dataclass(frozen=True)
class Tema:
    slug: str
    titulo: str
    texto: str  # el Markdown tal como está en el fichero


@lru_cache(maxsize=1)
def temas() -> tuple[Tema, ...]:
    salida = []
    for ruta in sorted(DIRECTORIO.glob("*.md")):
        texto = ruta.read_text(encoding="utf-8")
        titulo = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), ruta.stem)
        salida.append(Tema(re.sub(r"^\d+_", "", ruta.stem), titulo, texto))
    return tuple(salida)


def tema(slug: str) -> Tema | None:
    return next((t for t in temas() if t.slug == slug), None)


def tema_de_pantalla(nombre: str | None, caja: str | None = None) -> str | None:
    if not nombre:
        return None
    return TEMA_DE_PANTALLA.get(nombre) or TEMA_DE_CAJA.get(caja or "")


def url_de_ayuda(ctx, listado=None, caja: str | None = None) -> str:
    """El enlace del botón «Ayuda»: el tema de la pantalla en la que se está, o el índice."""
    base = f"/e/{ctx.slug}/{ctx.ejercicio.anio}/ayuda" if ctx else "/ayuda"
    slug = tema_de_pantalla(getattr(listado, "nombre", None), caja)
    return f"{base}/{slug}" if slug else base


# ------------------------------------------------------------------------------------------------ partes que genera el programa

def menu_en_markdown(menu, base_pantallas: str | None) -> str:
    """Las cajas del menú con cada pantalla y su explicación, como Markdown. Con `base_pantallas` (dentro de una empresa) cada pantalla es un enlace."""
    lineas = []
    for caja in menu:
        lineas += [f"### {caja.titulo}", ""]
        for o in caja.opciones:
            nombre = f"[{o.titulo}]({base_pantallas}/{o.nombre})" if base_pantallas and o.nombre and not o.proximamente else f"**{o.titulo}**"
            lineas.append(f"- {nombre} — {o.descripcion}".rstrip(" —") + (" *(próximamente)*" if o.proximamente else ""))
        lineas.append("")
    return "\n".join(lineas)


def auditoria_en_markdown(catalogo: dict) -> str:
    """Los avisos de la auditoría (código → (título, qué significa, qué hacer, pantalla)), como Markdown, por orden alfabético del título."""
    lineas = ["| Aviso | Qué significa | Qué hacer |", "|---|---|---|"]
    for codigo, (titulo, significa, hacer, _) in sorted(catalogo.items(), key=lambda kv: _normalizar(kv[1][0])):
        lineas.append(f"| **{titulo}** | {significa} | {hacer} |".replace("\n", " "))
    return "\n".join(lineas)


def con_partes_generadas(texto: str, menu, base_pantallas: str | None, catalogo_auditoria: dict) -> str:
    return texto.replace("@@MENU@@", menu_en_markdown(menu, base_pantallas)).replace("@@AUDITORIA@@", auditoria_en_markdown(catalogo_auditoria))


# ------------------------------------------------------------------------------------------------ Markdown → HTML

def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()).strip()


def ancla(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalizar(re.sub(r"[`*]", "", texto))).strip("-") or "apartado"


def _enlace(destino: str, base_ayuda: str, base_pantallas: str | None) -> str | None:
    if destino.startswith("tema:"):
        slug, _, a = destino[5:].partition("#")
        return f"{base_ayuda}/{slug}" + (f"#{a}" if a else "")
    if destino.startswith("pantalla:"):
        if destino[9:] in PANTALLAS_GLOBALES:  # no son de una empresa: sirven desde cualquier sitio
            return PANTALLAS_GLOBALES[destino[9:]]
        return f"{base_pantallas}/{destino[9:]}" if base_pantallas else None
    if destino.startswith(("http://", "https://")):
        return destino
    return None


def _en_linea(texto: str, base_ayuda: str, base_pantallas: str | None) -> str:
    codigos: list[str] = []

    def guardar(m: re.Match) -> str:
        codigos.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codigos) - 1}\x00"

    texto = re.sub(r"`([^`]+)`", guardar, texto)
    texto = html.escape(texto, quote=False)

    def enlace(m: re.Match) -> str:
        destino = _enlace(html.unescape(m.group(2)), base_ayuda, base_pantallas)
        if destino is None:
            return m.group(1)  # un enlace a una pantalla fuera de una empresa o desconocido: solo el texto
        externo = ' target="_blank" rel="noopener noreferrer"' if destino.startswith("http") else ""
        return f'<a href="{html.escape(destino, quote=True)}"{externo}>{m.group(1)}</a>'

    texto = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", enlace, texto)
    texto = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", texto)
    return re.sub(r"\x00(\d+)\x00", lambda m: codigos[int(m.group(1))], texto)


def _celdas(linea: str) -> list[str]:
    return [c.strip() for c in linea.strip().strip("|").split("|")]


def a_html(texto: str, base_ayuda: str = "/ayuda", base_pantallas: str | None = None) -> tuple[str, list[tuple[int, str, str]]]:
    """(HTML, índice de títulos [(nivel, ancla, texto)]) de un Markdown."""
    def en(t: str) -> str:
        return _en_linea(t, base_ayuda, base_pantallas)

    salida: list[str] = []
    indice: list[tuple[int, str, str]] = []
    lineas = texto.splitlines()
    i = 0
    usadas: dict[str, int] = {}
    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
        elif linea.startswith("```"):
            i += 1
            bloque = []
            while i < len(lineas) and not lineas[i].startswith("```"):
                bloque.append(lineas[i])
                i += 1
            i += 1
            salida.append(f"<pre><code>{html.escape(chr(10).join(bloque))}</code></pre>")
        elif m := re.match(r"(#{1,4}) +(.+)", linea):
            nivel, titulo = len(m.group(1)), m.group(2).strip()
            a = ancla(titulo)
            usadas[a] = usadas.get(a, 0) + 1
            a = a if usadas[a] == 1 else f"{a}-{usadas[a]}"
            if nivel > 1:
                indice.append((nivel, a, re.sub(r"[`*]", "", titulo)))
            salida.append(f'<h{nivel} id="{a}">{en(titulo)}</h{nivel}>')
            i += 1
        elif linea.lstrip().startswith("|") and i + 1 < len(lineas) and re.match(r"\s*\|?\s*:?-{2,}", lineas[i + 1]):
            cabecera = _celdas(linea)
            i += 2
            filas = []
            while i < len(lineas) and lineas[i].lstrip().startswith("|"):
                filas.append(_celdas(lineas[i]))
                i += 1
            salida.append("<table class=\"lineas\"><thead><tr>" + "".join(f"<th>{en(c)}</th>" for c in cabecera) + "</tr></thead><tbody>"
                          + "".join("<tr>" + "".join(f"<td>{en(c)}</td>" for c in f) + "</tr>" for f in filas) + "</tbody></table>")
        elif linea.startswith(">"):
            cita = []
            while i < len(lineas) and lineas[i].startswith(">"):
                cita.append(lineas[i][1:].strip())
                i += 1
            texto_cita = " ".join(cita)
            clase = "warning" if texto_cita.lower().startswith(("**cuidado", "**ojo", "**importante")) else "info"
            salida.append(f'<div class="aviso {clase}">{en(texto_cita)}</div>')
        elif re.match(r"\s*([-*]|\d+\.) +", linea):
            ordenada = bool(re.match(r"\s*\d+\.", linea))
            elementos: list[str] = []
            while i < len(lineas) and (re.match(r"\s*([-*]|\d+\.) +", lineas[i]) or (lineas[i].startswith("  ") and lineas[i].strip() and elementos)):
                cuerpo = re.sub(r"^\s*([-*]|\d+\.) +", "", lineas[i])
                if re.match(r"\s*([-*]|\d+\.) +", lineas[i]):
                    elementos.append(cuerpo)
                else:
                    elementos[-1] += " " + lineas[i].strip()  # continuación de un elemento
                i += 1
            etiqueta = "ol" if ordenada else "ul"
            salida.append(f"<{etiqueta}>" + "".join(f"<li>{en(e)}</li>" for e in elementos) + f"</{etiqueta}>")
        else:
            parrafo = []
            while i < len(lineas) and lineas[i].strip() and not re.match(r"(#{1,4} |```|>|\s*([-*]|\d+\.) +|\s*\|)", lineas[i]):
                parrafo.append(lineas[i].strip())
                i += 1
            if not parrafo:  # una línea que parece lista o tabla sin serlo
                parrafo.append(lineas[i].strip())
                i += 1
            salida.append(f"<p>{en(' '.join(parrafo))}</p>")
    return "\n".join(salida), indice


# ------------------------------------------------------------------------------------------------ buscador

def buscar(consulta: str, textos: list[Tema] | None = None, limite: int = 30) -> list[dict]:
    """Los apartados (por título `##`/`###`) cuyo texto contiene todas las palabras de la consulta, sin importar mayúsculas ni acentos. Devuelve tema, apartado, ancla y un extracto."""
    palabras = [p for p in _normalizar(consulta).split() if len(p) > 1]
    if not palabras:
        return []
    resultados = []
    for t in textos or temas():
        apartados: list[tuple[str, str, list[str]]] = [(t.titulo, "", [])]
        for linea in t.texto.splitlines():
            if m := re.match(r"#{2,3} +(.+)", linea):
                apartados.append((re.sub(r"[`*]", "", m.group(1)), ancla(m.group(1)), []))
            elif not linea.startswith("# "):
                apartados[-1][2].append(linea)
        for titulo, a, cuerpo in apartados:
            texto = " ".join(cuerpo)
            plano = _normalizar(titulo + " " + texto)
            if all(p in plano for p in palabras):
                resultados.append(dict(slug=t.slug, tema=t.titulo, apartado=titulo, ancla=a, extracto=_extracto(texto, palabras), puntos=sum(_normalizar(titulo).count(p) * 5 + plano.count(p) for p in palabras)))
    return sorted(resultados, key=lambda r: -r["puntos"])[:limite]


def _extracto(texto: str, palabras: list[str], ancho: int = 190) -> str:
    limpio = re.sub(r"[`*|>]|\[([^\]]+)\]\([^)]*\)", lambda m: m.group(1) or "", texto)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    plano = _normalizar(limpio)  # misma longitud solo si no hay acentos: se busca la posición en el original por aproximación
    pos = next((plano.find(p) for p in palabras if p in plano), 0)
    pos = max(0, min(pos, len(limpio)) - 40)
    corte = limpio[pos:pos + ancho]
    return ("…" if pos else "") + corte + ("…" if pos + ancho < len(limpio) else "")


# ------------------------------------------------------------------------------------------------ rutas

def registrar(app, render, contexto) -> None:
    """Añade las pantallas de ayuda: `/ayuda[/{tema}]` (sin empresa) y `/e/{slug}/{anio}/ayuda[/{tema}]` (dentro de una empresa, con su menú). Hay que llamarla antes de las rutas genéricas de listados."""
    from conta_pridalac.db.modelos import Ejercicio
    from conta_pridalac.web.auditoria import CATALOGO
    from conta_pridalac.web.definiciones import construir_menu

    def vista(request: Request, nombre_tema: str | None, q: str, ctx):
        base_ayuda = f"/e/{ctx.slug}/{ctx.ejercicio.anio}/ayuda" if ctx else "/ayuda"
        base_pantallas = f"/e/{ctx.slug}/{ctx.ejercicio.anio}" if ctx else None
        menu = construir_menu(request.app.state.listados)
        todos = [Tema(t.slug, t.titulo, con_partes_generadas(t.texto, menu, base_pantallas, CATALOGO)) for t in temas()]
        actual = next((t for t in todos if t.slug == nombre_tema), None) if nombre_tema else None
        if nombre_tema and actual is None:
            raise HTTPException(404, f"No existe el tema de ayuda «{nombre_tema}»")
        cuerpo, indice = a_html(actual.texto, base_ayuda, base_pantallas) if actual else ("", [])
        resultados = buscar(q, todos) if q.strip() else None
        ejercicios = list(ctx.sesion.scalars(select(Ejercicio).order_by(Ejercicio.anio.desc()))) if ctx else []
        return render(request, "ayuda.html", ctx=ctx, listado=None, listados=request.app.state.listados, ejercicios=ejercicios, temas=[(t.slug, t.titulo) for t in todos], actual=actual, cuerpo=cuerpo,
                      indice=indice, q=q, resultados=resultados, base_ayuda=base_ayuda)

    @app.get("/ayuda", response_class=HTMLResponse)
    @app.get("/ayuda/{nombre_tema}", response_class=HTMLResponse)
    def ayuda_general(request: Request, nombre_tema: str | None = None, q: str = ""):
        return vista(request, nombre_tema, q, None)

    @app.get("/e/{slug}/{anio}/ayuda", response_class=HTMLResponse)
    @app.get("/e/{slug}/{anio}/ayuda/{nombre_tema}", response_class=HTMLResponse)
    def ayuda_de_empresa(request: Request, nombre_tema: str | None = None, q: str = "", ctx=Depends(contexto)):
        return vista(request, nombre_tema, q, ctx)
