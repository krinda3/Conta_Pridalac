"""El registro de cambios en la web (`db/registro.py`): todo lo que se ha dado de alta, cambiado o borrado en los datos contables, con su fecha y su huella, y la comprobación de que la cadena sigue íntegra."""
from __future__ import annotations

import json

from sqlalchemy import select

from conta_pridalac.db.registro import ALTA, ALTA_LOTE, BAJA, CAMBIO, INICIO, RegistroCambio, ultima_huella, verificar
from conta_pridalac.exportacion.tabla import ENTERO, TEXTO, Columna, Tabla
from conta_pridalac.web.listados import Campo, Col, Detalle, Fila, Listado

OPERACIONES = {ALTA: "Alta", CAMBIO: "Cambio", BAJA: "Baja", ALTA_LOTE: "Alta en lote", INICIO: "Situación de partida"}
MAXIMO = 3000  # las anotaciones más recientes que se enseñan sin filtrar: el registro completo sigue en la base


def _texto(valor) -> str:
    if valor is None:
        return "—"
    return str(valor)


def _resumen(a: RegistroCambio) -> str:
    datos = json.loads(a.datos)
    if a.operacion == INICIO:
        return f"{sum(datos['filas'].values())} filas en {len(datos['filas'])} tablas al empezar a registrar"
    if a.operacion == ALTA_LOTE:
        return f"{datos['filas']} filas de golpe (importación)"
    if a.operacion == CAMBIO:
        return "; ".join(f"{campo}: {_texto(v[0])} → {_texto(v[1])}" for campo, v in datos.items())
    mostrados = [f"{campo}: {_texto(v)}" for campo, v in datos.items() if v not in (None, "") and campo != "id"][:4]
    return "; ".join(mostrados)


class ListadoRegistroCambios(Listado):
    nombre, titulo = "registro-cambios", "Registro de cambios"
    descripcion = ("Todo lo que se ha dado de alta, cambiado o borrado en los datos contables, con su fecha y usuario. Cada anotación lleva una huella que depende de la anterior: si alguien toca el registro, la cadena se rompe y aquí se avisa. "
                   "Sólo se puede consultar. Doble clic en una anotación para ver sus datos.")
    columnas = [Col("numero", "Nº", ENTERO, 0.7), Col("fecha", "Fecha y hora", TEXTO, 1.7), Col("usuario", "Usuario", TEXTO, 1.1), Col("tabla", "Tabla", TEXTO, 1.4), Col("fila", "Fila", TEXTO, 0.9),
                Col("operacion", "Operación", TEXTO, 1.2), Col("resumen", "Qué cambió", TEXTO, 6)]
    parametros = [
        Campo("operacion", "Operación", "select", opciones=[("", "Todas")] + [(k, v) for k, v in OPERACIONES.items()]),
        Campo("tabla", "Tabla", "texto"),
    ]

    def texto_vacio(self, ctx, params):
        return "Todavía no hay anotaciones: se empieza a registrar con el primer cambio."

    def _consulta(self, params):
        consulta = select(RegistroCambio).order_by(RegistroCambio.id.desc())
        if params.get("operacion"):
            consulta = consulta.where(RegistroCambio.operacion == params["operacion"])
        if (tabla := (params.get("tabla") or "").strip()):
            consulta = consulta.where(RegistroCambio.tabla.like(f"%{tabla}%"))
        return consulta

    def filas(self, ctx, params):
        return [
            Fila(str(a.id), dict(numero=a.id, fecha=f"{a.momento[8:10]}/{a.momento[5:7]}/{a.momento[:4]} {a.momento[11:19]}", usuario=a.usuario, tabla=a.tabla, fila=a.fila,
                                 operacion=OPERACIONES.get(a.operacion, a.operacion), resumen=_resumen(a)),
                 clase="aviso-fila" if a.operacion == BAJA else "")
            for a in ctx.sesion.scalars(self._consulta(params).limit(MAXIMO))
        ]

    def resumen(self, ctx, filas):
        numero, huella = ultima_huella(ctx.sesion)
        if not numero:
            return "Todavía no hay anotaciones."
        problemas = verificar(ctx.sesion)
        if problemas:
            return f"⚠ CADENA ROTA: {problemas[0]}. Conserve la base tal cual y compárela con una copia anterior."
        recorte = f" Se enseñan las {MAXIMO} más recientes: use los filtros para ver otras." if len(filas) >= MAXIMO else ""
        return f"✔ Cadena íntegra: {numero} anotaciones. Última huella: {huella[:16]}…{recorte}"

    def totales(self, filas):
        return None

    def detalle(self, ctx, id):
        try:
            a = ctx.sesion.get(RegistroCambio, int(id))
        except ValueError:
            a = None
        if a is None:
            return None
        datos = json.loads(a.datos)
        cabecera = [["Nº", a.id], ["Fecha y hora", a.momento.replace("T", " ")], ["Usuario", a.usuario], ["Tabla", a.tabla], ["Fila", a.fila], ["Operación", OPERACIONES.get(a.operacion, a.operacion)],
                    ["Huella", a.huella], ["Huella anterior", a.huella_anterior or "— (primera anotación)"]]
        extras = []
        if a.operacion == CAMBIO:
            extras.append(Tabla("Lo que cambió", [Columna("Campo", ancho=2), Columna("Antes", ancho=3), Columna("Después", ancho=3)], [[c, _texto(v[0]), _texto(v[1])] for c, v in datos.items()]))
        elif a.operacion == INICIO:
            extras.append(Tabla("Filas de cada tabla al empezar a registrar", [Columna("Tabla", ancho=3), Columna("Filas", ENTERO, 1)], [[t, n] for t, n in datos["filas"].items()]))
        elif a.operacion == ALTA_LOTE:
            extras.append(Tabla("Importación", [Columna("Dato", ancho=2), Columna("Valor", ancho=6)], [["Filas", datos["filas"]], ["Huella de las filas (SHA-256)", datos["sha256"]]]))
        else:
            extras.append(Tabla("Fila borrada" if a.operacion == BAJA else "Fila creada", [Columna("Campo", ancho=2), Columna("Valor", ancho=6)], [[c, _texto(v)] for c, v in datos.items()]))
        return Detalle(f"Anotación {a.id} · {OPERACIONES.get(a.operacion, a.operacion)} en {a.tabla}", Tabla("Anotación", [Columna("Dato", ancho=1.3), Columna("Valor", ancho=6)], cabecera), [], extras)
