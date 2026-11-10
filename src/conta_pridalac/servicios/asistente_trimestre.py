"""Asistente del trimestre: los pasos del cierre trimestral en orden, cada uno con lo que queda por hacer.

No guarda nada: cada paso se calcula en el momento con los datos de la propia contabilidad (la lista de trabajo, los extractos, los vencimientos, las declaraciones), siempre dentro del trimestre de trabajo
que se haya elegido. Así no hay un registro aparte que se quede desactualizado: si se hace algo por otra pantalla, el paso lo refleja al volver. Un paso sin datos de partida no se da por «hecho»: se dice que
todavía no hay nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conta_pridalac.auditoria import ERROR
from conta_pridalac.db.modelos import ENVIADA, Banco, Ejercicio, Empresa, DepositoCuentas, ExtractoLinea, FacturaTrimestre, Legalizacion
from conta_pridalac.servicios import copia_justificantes, pagos_extracto
from conta_pridalac.servicios import trimestre as tri
from conta_pridalac.servicios.extractos import cuadrar_banco
from conta_pridalac.servicios.empresa import modelos_de
from conta_pridalac.servicios.presentacion303 import presentada_del_periodo
from conta_pridalac.servicios.vigilancia import PRIMER_EJERCICIO_DEPOSITO, PRIMER_EJERCICIO_LIBROS, PRIMER_PAGO_202, debe_presentar_390
from conta_pridalac.servicios.tesoreria import ORDEN_DE_BANCOS

HECHO, PENDIENTE, REVISAR, VACIO = "hecho", "pendiente", "revisar", "vacio"
ROTULO = {HECHO: "✔ Hecho", PENDIENTE: "● Pendiente", REVISAR: "⚠ Revisar", VACIO: "— Sin datos"}
SIN_RECIBIDAS = "Todavía no hay facturas recibidas cargadas del trimestre"
SIN_EXTRACTO = "Todavía no hay extractos importados del trimestre"


@dataclass
class Paso:
    numero: int
    titulo: str
    estado: str
    detalle: str
    pantalla: str  # nombre de la pantalla donde se hace
    ayuda: str  # qué hacer en esa pantalla, en una o dos frases

    @property
    def rotulo(self) -> str:
        return ROTULO[self.estado]


def _euros(valor: Decimal) -> str:
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def pasos(sesion: Session, empresa: Empresa, ejercicio: Ejercicio, periodo: tuple[date, date], estado_303: str, estado_111: str, raiz_almacen: Path | None = None, hallazgos: list | None = None, copia_externa=None, estado_115: str | None = None, hay_alquileres: bool = True) -> list[Paso]:
    """Los pasos del trimestre `periodo` (primer y último día) con su estado. `estado_303` y `estado_111` son los textos de la pantalla de cada modelo («Presentado», «Borrador», «Sin presentar»…)."""
    desde, hasta = periodo
    trimestre, anio = (desde.month - 1) // 3 + 1, desde.year
    eid = empresa.id
    presenta = modelos_de(empresa)  # sólo salen los pasos de lo que la empresa presenta
    resultado: list[Paso] = []

    def paso(titulo: str, estado: str, detalle: str, pantalla: str, ayuda: str) -> None:
        resultado.append(Paso(len(resultado) + 1, titulo, estado, detalle, pantalla, ayuda))

    # ---- extractos
    con_extracto = {b for b in sesion.scalars(select(ExtractoLinea.banco_id).where(ExtractoLinea.empresa_id == eid).distinct())}
    en_el_trimestre = dict(sesion.execute(select(ExtractoLinea.banco_id, func.count(ExtractoLinea.id)).where(ExtractoLinea.empresa_id == eid, ExtractoLinea.fecha >= desde, ExtractoLinea.fecha <= hasta)
                                          .group_by(ExtractoLinea.banco_id)).all())
    nombres = {b.id: b.nombre for b in sesion.scalars(select(Banco).where(Banco.empresa_id == eid))}
    faltan = [nombres[b] for b in sorted(con_extracto) if b in nombres and not en_el_trimestre.get(b)]
    lineas = sum(en_el_trimestre.values())
    hay_extracto = lineas > 0
    paso("Importar los extractos del trimestre", PENDIENTE if not lineas else (REVISAR if faltan else HECHO),
         "No hay ningún extracto importado del trimestre" if not lineas else f"{lineas} líneas importadas de {len(en_el_trimestre)} bancos o tarjetas" + (f"; sin líneas en el trimestre: {', '.join(faltan)}" if faltan else ""),
         "extractos", "Pulse «Importar extracto» con el Excel de cada banco y de la tarjeta; Conta reconoce el banco por las columnas.")

    # ---- recibidas
    del_trimestre = list(sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == eid, FacturaTrimestre.sentido == "R", FacturaTrimestre.descartada.is_(False),
                                                                      FacturaTrimestre.fecha_factura >= desde, FacturaTrimestre.fecha_factura <= hasta)))
    hay_recibidas = bool(del_trimestre)
    pendientes = tri.facturas_pendientes(sesion, eid, "R", periodo)
    paso("Cargar las facturas recibidas", HECHO if del_trimestre else PENDIENTE,
         f"{len(del_trimestre)} facturas del trimestre en la lista de trabajo ({sum(1 for f in del_trimestre if f.factura_id)} ya contabilizadas)" if del_trimestre
         else "No hay ninguna cargada: exporte el Excel de recibidas de Verifactu y cárguelo",
         "conciliacion", "Pulse «Cargar facturas» y elija el Excel de facturas recibidas de Verifactu.")
    propuestas = tri.proponer(sesion, eid, sentido="R", periodo=periodo)
    duplicadas = tri.posibles_duplicadas(pendientes)
    paso("Quitar las duplicadas de Verifactu", VACIO if not hay_recibidas else (REVISAR if duplicadas else HECHO),
         SIN_RECIBIDAS if not hay_recibidas else (f"{len(duplicadas)} posibles duplicadas por revisar" if duplicadas else "Ninguna duplicada pendiente"),
         "conciliacion", "Pulse «Quitar duplicadas», revise las parejas y confirme.")
    sin_decidir = [f for f in propuestas.facturas.values() if tri.resolver_proveedor(sesion, f).tercero is None and not f.crear_proveedor]
    paso("Elegir los proveedores nuevos", VACIO if not hay_recibidas else (REVISAR if sin_decidir else HECHO),
         SIN_RECIBIDAS if not hay_recibidas else (f"{len(sin_decidir)} facturas con un proveedor que Conta no tiene: elija uno o marque crearlo" if sin_decidir else "Todos los proveedores están decididos"),
         "conciliacion", "Doble clic en la fila: elija el proveedor de Conta o marque «crear el proveedor nuevo».")
    preparadas = tri.preparar(sesion, ejercicio, propuestas)
    con_linea = preparadas.con_extracto
    paso("Aplicar las propuestas con extracto", VACIO if not hay_recibidas else (PENDIENTE if con_linea else HECHO),
         SIN_RECIBIDAS if not hay_recibidas else (f"{len(con_linea)} facturas por aplicar con su pago del extracto" + (f"; {len(preparadas.omitidas)} se dejan fuera" if preparadas.omitidas else "")
                                                    if con_linea else "No queda ninguna propuesta segura por aplicar"),
         "conciliacion", "Pulse «Aplicar propuestas»: crea la factura y su pago con la línea del extracto.")
    sin_movimiento = propuestas.resultado.sin_conciliar
    paso("Marcar las pagadas por el socio", VACIO if not hay_recibidas else (REVISAR if sin_movimiento else HECHO),
         SIN_RECIBIDAS if not hay_recibidas else (f"{len(sin_movimiento)} facturas sin movimiento en el extracto: ¿las pagó el socio?" + (f" ({len(propuestas.pagadas_por_banco)} ya marcadas)" if propuestas.pagadas_por_banco else "")
                                                   if sin_movimiento else "No hay facturas sin movimiento"),
         "conciliacion", "Pulse «Pagadas por el socio», marque las que pagó con su dinero y elija su cuenta y el día.")
    paso("Aplicar de nuevo las pagadas por el socio", VACIO if not hay_recibidas else (PENDIENTE if preparadas.sin_extracto else HECHO),
         SIN_RECIBIDAS if not hay_recibidas else (f"{len(preparadas.sin_extracto)} por aplicar" if preparadas.sin_extracto else "No queda ninguna"),
         "conciliacion", "Pulse «Aplicar propuestas» otra vez: ahora contabiliza también las pagadas por el socio.")
    resto = tri.preparar_pendientes(sesion, ejercicio, propuestas)
    paso("Contabilizar el resto como pendientes de pago", VACIO if not hay_recibidas else (PENDIENTE if resto.aplicables else (REVISAR if resto.omitidas else HECHO)),
         SIN_RECIBIDAS if not hay_recibidas else ((f"{len(resto.aplicables)} facturas por contabilizar sin pago" + (f"; {len(resto.omitidas)} se dejan fuera" if resto.omitidas else "")) if resto.aplicables
                                                   else (f"{len(resto.omitidas)} facturas que no se pueden contabilizar: revise el motivo" if resto.omitidas else "No queda nada en la lista")),
         "conciliacion", "Hágalo al final: pulse «Contabilizar el resto». Quedan como vencimientos pendientes de pago.")
    por_pagar = pagos_extracto.vencimientos_a_pagar(sesion, ejercicio)
    sugerencias = pagos_extracto.sugerir(sesion, ejercicio, periodo)
    paso("Pagar los vencimientos con el extracto", VACIO if not (hay_recibidas or sugerencias) else (REVISAR if sugerencias else HECHO),
         SIN_RECIBIDAS if not (hay_recibidas or sugerencias) else (f"{len(por_pagar)} vencimientos pendientes de pago ({_euros(sum((p for _, p in por_pagar), Decimal('0')))}); {len(sugerencias)} sugerencias del extracto"
                                                                    if por_pagar else "No hay vencimientos pendientes de pago"),
         "conciliar-pagos", "Revise las sugerencias y acepte las que sean correctas; el resto, desde «Líneas sin factura».")

    # ---- emitidas
    emitidas = list(sesion.scalars(select(FacturaTrimestre).where(FacturaTrimestre.empresa_id == eid, FacturaTrimestre.sentido == "E", FacturaTrimestre.descartada.is_(False),
                                                                 FacturaTrimestre.fecha_factura >= desde, FacturaTrimestre.fecha_factura <= hasta)))
    por_aplicar = [f for f in emitidas if f.factura_id is None]
    paso("Cargar y aplicar las facturas emitidas", PENDIENTE if (not emitidas or por_aplicar) else HECHO,
         "No hay ninguna cargada: exporte el Excel de emitidas de Verifactu y cárguelo" if not emitidas else (f"{len(por_aplicar)} de {len(emitidas)} por contabilizar" if por_aplicar else f"{len(emitidas)} emitidas, todas contabilizadas"),
         "emitidas-trimestre", "Pulse «Cargar emitidas», luego «Aplicar propuestas» y «Contabilizar el resto».")

    # ---- extracto
    enlaces = pagos_extracto.enlazables(sesion, eid, periodo)
    paso("Enlazar el extracto con lo ya contabilizado", VACIO if not hay_extracto else (PENDIENTE if enlaces.pares else HECHO),
         SIN_EXTRACTO if not hay_extracto else (f"{len(enlaces.pares)} líneas coinciden con un movimiento ya contabilizado" + (f" ({enlaces.ambiguos} ambiguas)" if enlaces.ambiguos else "") if enlaces.pares else "No hay líneas por enlazar"),
         "conciliacion", "Pulse «Enlazar con el extracto» y confirme: no cambia ningún asiento.")
    libres = pagos_extracto.lineas_libres(sesion, eid, desde, hasta, con_abonos=True)
    paso("Decidir las líneas sin factura", VACIO if not hay_extracto else (PENDIENTE if libres else HECHO),
         SIN_EXTRACTO if not hay_extracto else (f"{len(libres)} líneas del extracto sin contabilizar" if libres else "Todas las líneas del extracto están contabilizadas"),
         "lineas-sin-factura", "Doble clic en cada línea (o «Aplicar sugerencias» si tiene regla): tickets, socio, impuestos, liquidación de la tarjeta…")

    # ---- comprobación de los bancos
    no_cuadran, arrastran, comprobados = [], [], 0
    for banco in sesion.scalars(select(Banco).where(Banco.empresa_id == eid, Banco.cuenta_id.is_not(None)).order_by(*ORDEN_DE_BANCOS)):
        if en_el_trimestre.get(banco.id):
            comprobados += 1
            c = cuadrar_banco(sesion, ejercicio, banco, desde, hasta)
            if c.arrastra_una_diferencia:
                arrastran.append(f"{banco.nombre} ({_euros(c.diferencia_previa)} de antes del {desde:%d/%m/%Y})")
            elif not c.cuadra:
                no_cuadran.append(banco.nombre)
    detalle_bancos = []
    if no_cuadran:
        detalle_bancos.append(f"No cuadran los movimientos de: {', '.join(no_cuadran)}")
    if arrastran:
        detalle_bancos.append(f"Los movimientos cuadran, pero el saldo arrastra una diferencia anterior al trimestre: {'; '.join(arrastran)}")
    paso("Comprobar que cada banco cuadra con su Mayor", VACIO if not comprobados else (REVISAR if detalle_bancos else HECHO),
         "No hay extractos del trimestre" if not comprobados else (". ".join(detalle_bancos) if detalle_bancos else f"{comprobados} bancos o tarjetas cuadran con el extracto"),
         "cuadre-bancos", "Elija cada banco y el periodo del trimestre: tiene que quedar «CUADRA» con el mismo saldo final. Si sólo cuadran los movimientos, la diferencia de saldo viene de un periodo anterior.")

    # ---- auditoría, antes de presentar nada
    if hallazgos is None:
        paso("Pasar la auditoría de integridad", VACIO, "No se ha podido calcular", "auditoria", "Abra la auditoría: los errores impiden cerrar el ejercicio y conviene arreglarlos antes de presentar los modelos.")
    else:
        errores = sum(1 for h in hallazgos if h.gravedad == ERROR)
        avisos = len(hallazgos) - errores
        paso("Pasar la auditoría de integridad", REVISAR if hallazgos else HECHO,
             f"{errores} errores y {avisos} avisos: revíselos antes de presentar los modelos" if hallazgos else "Sin errores ni avisos",
             "auditoria", "Abra la auditoría, doble clic en cada hallazgo para ver qué significa y cómo se corrige.")

    # ---- modelos
    for modelo, texto, pantalla in (("303", estado_303, "modelo-303"), ("111", estado_111, "modelo-111")):
        if modelo not in presenta:
            continue
        paso(f"Presentar el modelo {modelo}", HECHO if texto.startswith("Presentado") else PENDIENTE, f"{trimestre}T {anio}: {texto}", pantalla,
             "Doble clic en el trimestre: revise el cálculo y los controles, genere el fichero y registre la presentación.")
    if estado_115 is not None and "115" in presenta:  # el 115 sólo sale si hubo retenciones por alquileres en el trimestre (o ya está presentado)
        if estado_115.startswith("Presentado") or hay_alquileres:
            paso("Presentar el modelo 115 (retenciones por alquileres)", HECHO if estado_115.startswith("Presentado") else PENDIENTE, f"{trimestre}T {anio}: {estado_115}", "modelo-115",
                 "Doble clic en el trimestre: revise el cálculo y los controles, genere el fichero y registre la presentación.")

    # ---- el resumen anual del IVA, con el 4T (a partir del ejercicio 2026 y sólo si hubo IVA en el año)
    if trimestre == 4 and "390" in presenta and debe_presentar_390(sesion, ejercicio):
        presentado = presentada_del_periodo(sesion, eid, anio, 0, "390")
        paso("Presentar el modelo 390 (resumen anual del IVA)", HECHO if presentado is not None else PENDIENTE,
             f"Ejercicio {anio}: " + ("presentado" + (f", justificante {presentado.justificante}" if getattr(presentado, "justificante", None) else "") if presentado is not None else "sin presentar"),
             "modelo-390", "Pulse «Generar fichero y presentar…»: revise los controles, genere el fichero, súbalo a la sede y registre la presentación con su PDF. Antes complete en la ficha de la empresa las actividades y los representantes.")

    # ---- el pago fraccionado del IS (202): el 1P se presenta en abril (2T) y el 2P y el 3P en octubre y diciembre (4T)
    for pago in {2: (1,), 4: (2, 3)}.get(trimestre, ()):
        if (anio, pago) < PRIMER_PAGO_202 or "202" not in presenta:
            continue
        presentado = presentada_del_periodo(sesion, eid, anio, pago, "202")
        paso(f"Presentar el modelo 202 ({pago}P · pago fraccionado del IS)", HECHO if presentado is not None else PENDIENTE,
             f"{pago}P {anio}: " + ("presentado" + (f", justificante {presentado.justificante}" if getattr(presentado, "justificante", None) else "") if presentado is not None else "sin presentar"),
             "modelo-202", "Doble clic en el pago: revise la base (sale del IS presentado), genere el fichero, súbalo a la sede y registre la presentación con su PDF. Se presenta del 1 al 20 del mes.")

    # ---- los libros del ejercicio anterior se legalizan en el Registro Mercantil hasta el 30 de abril (1T)
    if trimestre == 1 and "mercantil" in presenta and anio - 1 >= PRIMER_EJERCICIO_LIBROS:
        legalizacion = sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == eid, Legalizacion.anio == anio - 1))
        enviada = legalizacion is not None and legalizacion.estado == ENVIADA
        paso(f"Legalizar los libros de {anio - 1} en el Registro Mercantil", HECHO if enviada else PENDIENTE,
             f"Ejercicio {anio - 1}: " + (f"enviados el {legalizacion.enviada_en:%d/%m/%Y}" if enviada else ("libros preparados, sin registrar el envío" if legalizacion is not None else "sin preparar")) + f" (plazo hasta el 30/04/{anio})",
             "legalizacion-libros", "Con el ejercicio cerrado: «Generar los libros», importe el ZIP en Legalia2, envíelo y suba aquí el acuse de recibo.")

    # ---- las cuentas del ejercicio anterior se depositan en el Registro Mercantil un mes después de aprobarlas, antes del 30 de julio (2T)
    if trimestre == 2 and "mercantil" in presenta and anio - 1 >= PRIMER_EJERCICIO_DEPOSITO:
        deposito = sesion.scalar(select(DepositoCuentas).where(DepositoCuentas.empresa_id == eid, DepositoCuentas.anio == anio - 1))
        depositado = deposito is not None and deposito.estado == ENVIADA
        paso(f"Depositar las cuentas de {anio - 1} en el Registro Mercantil", HECHO if depositado else PENDIENTE,
             f"Ejercicio {anio - 1}: " + (f"depositadas el {deposito.enviado_en:%d/%m/%Y}" if depositado else ("carpeta preparada para D2, sin registrar el envío" if deposito is not None and deposito.carpeta_ruta else "sin preparar")) + f" (plazo: un mes desde la aprobación, como tarde el 30/07/{anio})",
             "deposito-cuentas", "Con las cuentas aprobadas por la junta: «Preparar el depósito», ábralo con D2 (certificación, firmas y envío) y suba aquí el acuse de recibo.")

    # ---- copia de los justificantes
    if copia_justificantes.carpeta_de(empresa, anio) is None or raiz_almacen is None:
        paso("Copiar los justificantes de Hacienda a la carpeta de la empresa", VACIO, "Sin configurar: indique la carpeta de copia en los datos de la empresa", "empresa", "Los datos de la empresa llevan la carpeta (por ejemplo, la de OneDrive) con {año} donde va el año.")
    else:
        copias = copia_justificantes.revisar_copias(sesion, empresa, anio, raiz_almacen, trimestre).copias
        por_copiar = [c for c in copias if c.estado in (copia_justificantes.COPIADO, copia_justificantes.CON_SUFIJO)]
        paso("Copiar los justificantes de Hacienda a la carpeta de la empresa", VACIO if not copias else (PENDIENTE if por_copiar else HECHO),
             f"No hay modelos presentados del {trimestre}T {anio}" if not copias else (f"{len(por_copiar)} de {len(copias)} justificantes sin copiar" if por_copiar else f"{len(copias)} justificantes copiados"),
             "trimestre", "Pulse «Copiar justificantes» en esta pantalla: copia los PDF de los modelos presentados que aún no estén en la carpeta.")

    # ---- el respaldo, lo último: con todo hecho y presentado
    if copia_externa is None or copia_externa.carpeta is None:
        paso("Hacer la copia de seguridad y llevarla a la carpeta de la empresa", VACIO, "Sin configurar: indique la carpeta de las copias en los datos de la empresa", "empresa",
             "Los datos de la empresa llevan la carpeta (por ejemplo, la de copias en OneDrive).")
    else:
        u = copia_externa.ultima
        paso("Hacer la copia de seguridad y llevarla a la carpeta de la empresa", HECHO if copia_externa.al_dia else PENDIENTE,
             f"La última copia, del {u.momento:%d/%m/%Y %H:%M}, es posterior al último cambio" if copia_externa.al_dia
             else (f"Hay cambios posteriores a la última copia ({u.momento:%d/%m/%Y %H:%M})" if u else f"No hay ninguna copia en {copia_externa.carpeta}"),
             "trimestre", "Pulse «Copia de seguridad en OneDrive» en esta pantalla: hace la copia, la verifica, la lleva a la carpeta y allí la vuelve a verificar.")
    return resultado
