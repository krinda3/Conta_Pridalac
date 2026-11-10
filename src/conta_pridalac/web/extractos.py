"""Extractos del banco en la web: las líneas importadas, la importación de un fichero y el cuadre de cada banco con su Mayor (`servicios/extractos.py`)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select

from conta_pridalac.db.modelos import Banco, Extracto, ExtractoLinea
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, FECHA, TEXTO
from conta_pridalac.servicios import extractos as svc
from conta_pridalac.servicios.tesoreria import ORDEN_DE_BANCOS
from conta_pridalac.web.comun import texto_dinero
from conta_pridalac.web.listados import Campo, Col, Fila, Listado
from conta_pridalac.web.tesoreria import _bancos

FORMATOS = {"bbva": "BBVA", "caixabank": "CaixaBank", "santander": "Santander", "tarjeta": "Tarjeta", "generico": "Otro"}
MAX_BYTES = 10 * 1024 * 1024


def _opciones_de_bancos(ctx) -> list[tuple[str, str]]:
    return [(str(b.id), b.nombre) for b in _bancos(ctx) if b.cuenta_id]


class ListadoExtractos(Listado):
    nombre, titulo = "extractos", "Extractos del banco"
    descripcion = ("Las líneas de los extractos del banco y de la tarjeta que se han importado, sin repetirse aunque los ficheros se solapen. Sirven para comprobar que cada banco coincide con su Mayor "
                   "(opción «Cuadre de bancos»). Un fichero se importa con «Importar extracto»: se reconoce el banco por sus columnas y se avisa si falta alguna línea.")
    columnas = [
        Col("banco", "Banco", TEXTO, 2), Col("fecha", "Fecha", FECHA, 1.1), Col("valor", "F. valor", FECHA, 1.1), Col("texto", "Concepto", TEXTO, 4), Col("mas", "Más datos", TEXTO, 3),
        Col("importe", "Importe", DINERO, 1.3), Col("saldo", "Saldo", DINERO, 1.3), Col("fichero", "Fichero", TEXTO, 2.5),
    ]
    parametros = [Campo("banco", "Banco", "select", opciones=_opciones_de_bancos), Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]
    borrar = True
    acciones_extra = [("⇪ Importar extracto", "accion/importar")]

    def texto_vacio(self, ctx, params):
        return "No hay extractos importados: use «Importar extracto»"

    def filas(self, ctx, params):
        consulta = (
            select(ExtractoLinea, Banco.nombre, Extracto.fichero).join(Banco, Banco.id == ExtractoLinea.banco_id).join(Extracto, Extracto.id == ExtractoLinea.extracto_id)
            .where(ExtractoLinea.empresa_id == ctx.empresa.id).order_by(*ORDEN_DE_BANCOS, ExtractoLinea.fecha.desc(), ExtractoLinea.id.desc())
        )
        if params.get("banco"):
            consulta = consulta.where(ExtractoLinea.banco_id == int(params["banco"]))
        if params.get("desde"):
            consulta = consulta.where(ExtractoLinea.fecha >= params["desde"])
        if params.get("hasta"):
            consulta = consulta.where(ExtractoLinea.fecha <= params["hasta"])
        return [Fila(str(l.id), dict(banco=banco, fecha=l.fecha, valor=l.fecha_valor, texto=l.texto, mas=l.mas_datos, importe=l.importe, saldo=l.saldo, fichero=fichero))
                for l, banco, fichero in ctx.sesion.execute(consulta)]

    def totales(self, filas):
        return {"importe": sum((f.valores["importe"] for f in filas), svc.CERO)}

    def eliminar(self, ctx, ids):
        ids = [int(i) for i in ids]
        ctx.sesion.execute(delete(ExtractoLinea).where(ExtractoLinea.empresa_id == ctx.empresa.id, ExtractoLinea.id.in_(ids)))
        vacios = select(Extracto.id).where(Extracto.empresa_id == ctx.empresa.id, ~Extracto.id.in_(select(ExtractoLinea.extracto_id)))
        ctx.sesion.execute(delete(Extracto).where(Extracto.id.in_(vacios)))

    # ---- importar un fichero
    def accion(self, ctx, accion, items):
        if accion != "importar":
            raise ErrorContable("Acción desconocida")
        contexto = dict(bancos=[(int(i), n) for i, n in _opciones_de_bancos(ctx)], errores=[], resultado=None, formatos=FORMATOS)
        if items is None:
            return "_extracto_importar.html", contexto
        datos = {k: v for k, v in items if isinstance(v, str)}
        fichero = next((v for k, v in items if k == "fichero" and getattr(v, "filename", "")), None)
        try:
            banco = ctx.sesion.get(Banco, int(datos["banco"])) if datos.get("banco", "").isdigit() else None
            if banco is None or banco.empresa_id != ctx.empresa.id or not banco.cuenta_id:
                raise ErrorContable("Elija el banco o la tarjeta del extracto")
            if fichero is None:
                raise ErrorContable("Elija el fichero Excel (.xlsx) del extracto")
            contenido = fichero.file.read()
            if len(contenido) > MAX_BYTES:
                raise ErrorContable("El Excel pesa más de 10 MB")
            signo = {"si": True, "no": False}.get(datos.get("signo", ""), None)
            resultado = svc.importar_extracto(ctx.sesion, ctx.empresa.id, banco, fichero.filename, contenido, invertir=signo)
            ctx.sesion.commit()
        except ErrorContable as e:
            ctx.sesion.rollback()
            contexto["errores"] = [str(e)]
            return "_extracto_importar.html", contexto
        contexto["resultado"] = dict(r=resultado, banco=banco.nombre, fichero=fichero.filename)
        return "_extracto_importar.html", contexto


class ListadoCuadreBancos(Listado):
    nombre, titulo = "cuadre-bancos", "Cuadre de bancos con su Mayor"
    descripcion = ("Para un banco o tarjeta y un periodo, compara el extracto con el Mayor de su cuenta, movimiento a movimiento y en el saldo final. Enseña lo que está sólo en uno de los lados; "
                   "si no queda nada y los saldos coinciden, el banco cuadra. Las fechas pueden diferir unos días entre el banco y el Mayor.")
    columnas = [Col("origen", "Dónde está", TEXTO, 2), Col("fecha", "Fecha", FECHA, 1.1), Col("texto", "Concepto", TEXTO, 5), Col("asiento", "Asiento", TEXTO, 1.1), Col("importe", "Importe", DINERO, 1.4)]
    parametros = [Campo("banco", "Banco", "select", opciones=_opciones_de_bancos), Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]

    def _periodo(self, ctx, params):
        """((banco, desde, hasta), "") o (None, por qué no hay nada que cuadrar). Por defecto, el periodo de los extractos importados dentro del ejercicio."""
        con_extracto = set(ctx.sesion.scalars(select(ExtractoLinea.banco_id).where(ExtractoLinea.empresa_id == ctx.empresa.id).distinct()))
        posibles = [b for b in _bancos(ctx) if b.cuenta_id]
        banco = ctx.sesion.get(Banco, int(params["banco"])) if params.get("banco") else next((b for b in posibles if b.id in con_extracto), next(iter(posibles), None))
        if banco is None or banco.empresa_id != ctx.empresa.id:
            return None, "Esta empresa no tiene bancos con cuenta contable"
        primera, ultima = ctx.sesion.execute(select(func.min(ExtractoLinea.fecha), func.max(ExtractoLinea.fecha)).where(ExtractoLinea.banco_id == banco.id)).one()
        if primera is None:
            return None, f"«{banco.nombre}» no tiene extractos importados"
        return (banco, max(params.get("desde") or primera, ctx.ejercicio.fecha_inicio), min(params.get("hasta") or ultima, ctx.ejercicio.fecha_fin)), ""

    def texto_vacio(self, ctx, params):
        return self._periodo(ctx, params)[1] or "No hay nada que cuadrar en este periodo"

    def filas(self, ctx, params):
        periodo, _ = self._periodo(ctx, params)
        if periodo is None:
            return []
        banco, desde, hasta = periodo
        c = svc.cuadrar_banco(ctx.sesion, ctx.ejercicio, banco, desde, hasta)
        resumen = "CUADRA" if c.cuadra else ("CUADRAN LOS MOVIMIENTOS (el saldo arrastra una diferencia de antes)" if c.arrastra_una_diferencia else "NO CUADRA")
        filas = [Fila(None, dict(origen=f"{resumen} · {banco.nombre}", fecha=None, texto=f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}: {c.lineas_en_el_periodo} líneas en el extracto"
                                 + (f" ({c.lineas_a_cero} sin importe, que no cuentan)" if c.lineas_a_cero else "") + f"; {c.emparejadas} emparejadas con el Mayor", importe=None), clase="resumen total")]
        if c.diferencia_previa is not None:
            filas += [Fila(None, dict(origen="Saldo inicial", texto=f"Antes del {desde:%d/%m/%Y}: extracto {texto_dinero(c.saldo_previo_extracto)} · Mayor {texto_dinero(c.saldo_previo_mayor)}", importe=c.diferencia_previa),
                           clase="aviso-fila" if c.diferencia_previa else "resumen")]
        if c.saldo_extracto is not None:
            filas += [Fila(None, dict(origen="Saldo final", texto="Del extracto", importe=c.saldo_extracto), clase="resumen"), Fila(None, dict(origen="Saldo final", texto="Del Mayor", importe=c.saldo_mayor), clase="resumen"),
                      Fila(None, dict(origen="Saldo final", texto="Diferencia", importe=c.diferencia_de_saldo), clase="resumen")]
        else:
            filas.append(Fila(None, dict(origen="Saldo final", texto="Este extracto no trae saldo: se comparan los totales", importe=None), clase="resumen"))
        filas += [
            Fila(None, dict(origen="Cargos (lo que sale)", texto=f"Extracto {texto_dinero(c.cargos_extracto)} · Mayor {texto_dinero(c.cargos_mayor)}", importe=c.cargos_extracto - c.cargos_mayor), clase="resumen"),
            Fila(None, dict(origen="Abonos (lo que entra)", texto=f"Extracto {texto_dinero(c.abonos_extracto)} · Mayor {texto_dinero(c.abonos_mayor)}", importe=c.abonos_extracto - c.abonos_mayor), clase="resumen"),
        ]
        filas += [Fila(None, dict(origen="Misma cantidad, otra fecha", fecha=l.fecha, texto=f"Banco {l.fecha:%d/%m/%Y} · Mayor {a.fecha:%d/%m/%Y} · {a.concepto or l.texto}", asiento=a.asiento, importe=l.importe), clase="aviso-fila")
                  for l, a in c.fecha_distinta]
        filas += [Fila(f"e{l.id}", dict(origen="Sólo en el extracto", fecha=l.fecha, texto=" · ".join(p for p in (l.texto, l.mas_datos) if p), asiento="", importe=l.importe)) for l in c.solo_extracto]
        filas += [Fila(None, dict(origen="Sólo en el Mayor", fecha=a.fecha, texto=a.concepto, asiento=a.asiento, importe=a.importe)) for a in c.solo_mayor]
        return filas

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio}"
