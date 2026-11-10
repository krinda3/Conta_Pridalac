"""Conciliar pagos en la web: los vencimientos pendientes de pago con las líneas del extracto que no han pagado nada (`servicios/pagos_extracto.py`).

La lista enseña las sugerencias del motor; con doble clic en una se abre su resumen (qué se paga, con qué líneas, la diferencia) y se confirma. «Conciliar a mano» deja marcar vencimientos y líneas
a gusto y lleva al mismo resumen.
"""
from __future__ import annotations

import re
from decimal import Decimal

from conta_pridalac.db.modelos import ExtractoLinea, Vencimiento
from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, TEXTO
from conta_pridalac.servicios import pagos_extracto as svc
from conta_pridalac.servicios import trimestre as tri
from conta_pridalac.web.comun import cuentas_para_listas
from conta_pridalac.web.listados import Col, Fila, Listado

CERO = Decimal("0.00")
MOTIVOS = {
    "importe_y_texto": "Misma cantidad y el nombre coincide", "importe_unico": "Cantidad con céntimos que sólo tiene un movimiento", "importe_y_fecha": "Misma cantidad el mismo día",
    "varias_facturas_un_cargo": "Varias facturas en un solo cargo", "dos_pagos": "Pagada en varias veces", "acumulado": "Cargos de la tarjeta que suman exactamente la factura", "importe_distinto": "Mismo nombre y fecha, pero otro importe",
}


def _clave(ids_v: list[int], ids_l: list[int]) -> str:
    return "v" + "-".join(map(str, ids_v)) + "_l" + "-".join(map(str, ids_l))


def _ids(clave: str) -> tuple[list[int], list[int]]:
    m = re.fullmatch(r"v(\d+(?:-\d+)*)_l(\d+(?:-\d+)*)", clave or "")
    if m is None:
        raise ErrorContable("La conciliación pedida no es válida")
    return [int(x) for x in m.group(1).split("-")], [int(x) for x in m.group(2).split("-")]


class ListadoConciliarPagos(Listado):
    nombre, titulo = "conciliar-pagos", "Sugerencias de pago"
    descripcion = ("Los vencimientos pendientes de pago de las facturas recibidas con los cargos del extracto que parecen haberlos pagado: una factura pagada en varias veces, varias facturas en un cargo, "
                   "los cargos de la tarjeta que suman justo una factura de Solred… Doble clic en una sugerencia para verla y confirmarla. Lo que no se sugiere se concilia desde «Líneas sin factura»: marque las "
                   "líneas y pulse «Pagar vencimientos con las marcadas».")
    formulario_propio = True
    editable = True
    columnas = [
        Col("motivo", "Sugerencia", TEXTO, 2.5), Col("facturas", "Facturas pendientes", TEXTO, 4), Col("pendiente", "Pendiente", DINERO, 1.2), Col("lineas", "Líneas del extracto", TEXTO, 4),
        Col("pagado", "Importe extracto", DINERO, 1.3), Col("diferencia", "Diferencia", DINERO, 1.1),
    ]

    def texto_vacio(self, ctx, params):
        return "No hay sugerencias. Si quedan vencimientos pendientes y líneas libres del extracto, concílielos desde «Líneas sin factura»"

    def filas(self, ctx, params):
        filas = []
        for s in svc.sugerir(ctx.sesion, ctx.ejercicio, tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id)):
            pte, pagado, dif = svc.resumen(ctx.sesion, s.vencimientos, s.lineas)
            filas.append(Fila(s.clave, dict(
                motivo=MOTIVOS.get(s.regla, s.regla), facturas=" + ".join(f"{svc._nombre(v)} {v.factura.numero_factura or ''}".strip() for v in s.vencimientos), pendiente=pte,
                lineas=" + ".join(f"{l.fecha:%d/%m} {l.texto}" for l in s.lineas), pagado=pagado, diferencia=dif or None), clase="aviso-fila" if dif else ""))
        return filas

    def totales(self, filas):
        return {"pendiente": sum((f.valores["pendiente"] for f in filas), CERO), "pagado": sum((f.valores["pagado"] for f in filas), CERO)}

    # ---- el resumen de una conciliación (de una sugerencia o hecha a mano)
    def _cargar(self, ctx, clave: str):
        ids_v, ids_l = _ids(clave)
        vencimientos = [v for v in (ctx.sesion.get(Vencimiento, i) for i in ids_v) if v is not None and v.ejercicio_id == ctx.ejercicio.id]
        lineas = [l for l in (ctx.sesion.get(ExtractoLinea, i) for i in ids_l) if l is not None and l.empresa_id == ctx.empresa.id]
        if len(vencimientos) != len(ids_v) or len(lineas) != len(ids_l):
            raise ErrorContable("Alguno de los vencimientos o de las líneas ya no existe")
        return vencimientos, lineas

    def formulario(self, ctx, id, estado=None, errores=None, valores=None):
        vencimientos, lineas = self._cargar(ctx, id)
        pte, pagado, dif = svc.resumen(ctx.sesion, vencimientos, lineas)
        return "_conciliar_pagos.html", dict(
            clave=id, vencimientos=[(v, -svc.pendiente(ctx.sesion, v)) for v in vencimientos], lineas=lineas, pte=pte, pagado=pagado, dif=dif, errores=errores or [],
            valores=valores or {"modo": svc.PARCIAL if dif > 0 else svc.CON_DIFERENCIA, "cuenta": ""}, cuentas=cuentas_para_listas(ctx), proveedor_de=svc._nombre)

    def guardar_formulario(self, ctx, items, ficheros):
        datos = {k: v for k, v in items if isinstance(v, str)}
        clave = datos.get("clave", "")
        try:
            vencimientos, lineas = self._cargar(ctx, clave)
            r = svc.conciliar_pagos(ctx.sesion, ctx.ejercicio, vencimientos, lineas, modo=datos.get("modo", svc.PARCIAL), cuenta_diferencia=datos.get("cuenta"))
            ctx.sesion.commit()
        except ErrorContable as ex:
            ctx.sesion.rollback()
            plantilla, contexto = self.formulario(ctx, clave, errores=[str(ex)], valores={"modo": datos.get("modo", svc.PARCIAL), "cuenta": datos.get("cuenta", "")})
            return None, plantilla, contexto, []
        return clave, None, None, r.avisos

    def trimestre_de_trabajo(self, ctx):
        return tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio} · trabajando en {tri.etiqueta_del_trimestre(tri.trimestre_de_trabajo(ctx.sesion, ctx.empresa.id))}"
