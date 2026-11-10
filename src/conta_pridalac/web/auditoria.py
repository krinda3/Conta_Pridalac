"""Auditoría de integridad en la web: todos los hallazgos con su explicación y cómo corregirlos.

Cada comprobación de `conta_pridalac.auditoria` tiene aquí su nombre legible, qué significa, cómo se corrige y en qué pantalla se arregla.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from sqlalchemy import select

from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo, auditar
from conta_pridalac.db.modelos import Asiento, Factura
from conta_pridalac.exportacion.tabla import DINERO, TEXTO, Columna, Tabla
from conta_pridalac.web.listados import Campo, Col, Contexto, Detalle, Fila, Listado

# código → (nombre, qué significa, cómo se corrige, pantalla donde se arregla)
CATALOGO: dict[str, tuple[str, str, str, str | None]] = {
    "asiento_descuadrado": ("Asiento descuadrado", "La suma del Debe no es igual a la del Haber.",
                            "Corrija los importes del asiento; si es de una factura o de un banco, corrija el documento (su asiento se regenera solo).", "asientos"),
    "apunte_en_cuenta_de_grupo": ("Apunte en una cuenta de grupo", "El apunte usa una cuenta con menos dígitos que las subcuentas (un grupo o una cuenta), que no admite apuntes.",
                                  "Cambie la cuenta del apunte por una subcuenta completa.", "cuentas"),
    "asiento_fuera_del_ejercicio": ("Asiento fuera del ejercicio", "La fecha del asiento no cae dentro del ejercicio.",
                                    "Corrija la fecha (en Asientos manuales, o en el documento de origen). Mientras tanto no se puede cerrar el ejercicio.", "asientos"),
    "factura_fuera_del_ejercicio": ("Factura fuera del ejercicio", "La fecha contable de la factura no cae dentro del ejercicio.",
                                    "Corrija la fecha contable de la factura.", "facturas-recibidas"),
    "factura_sin_asiento": ("Factura sin asiento", "La factura no tiene el asiento contable que le corresponde.",
                            "Abra la factura y guárdela de nuevo: el asiento se vuelve a generar.", "facturas-recibidas"),
    "factura_no_contabilizable": ("Factura que no se puede contabilizar", "Falta alguna cuenta (por ejemplo la de IVA) y no se puede generar su asiento.",
                                  "Abra la factura y complete la cuenta que falta.", "facturas-recibidas"),
    "asiento_distinto_del_regenerado": ("Asiento distinto del que corresponde", "El asiento guardado no coincide con el que resulta de su factura o de su movimiento de banco.",
                                        "Abra el documento y guárdelo de nuevo para regenerar el asiento. Si el asiento se cambió a propósito, conviene saber por qué.", "diario"),
    "movimiento_sin_asiento": ("Movimiento de banco sin asiento", "El movimiento tiene líneas pero no existe su asiento.",
                               "Abra el movimiento y guárdelo de nuevo.", "movimientos"),
    "asiento_de_movimiento_sobrante": ("Asiento de un movimiento que no lo necesita", "Existe el asiento de un movimiento de banco que no genera líneas contables.",
                                       "Guarde de nuevo el movimiento o borre el asiento sobrante.", "movimientos"),
    "movimiento_no_contabilizable": ("Movimiento de banco que no se puede contabilizar", "Falta alguna cuenta (la del banco o la de partidas pendientes de aplicar).",
                                     "Asigne la cuenta al banco, o defina la cuenta de partidas pendientes de aplicar.", "bancos"),
    "banco_sin_cuenta": ("Banco sin cuenta contable", "El banco no tiene cuenta contable y no se pueden generar los asientos de sus movimientos.",
                         "Asigne al banco su cuenta (por ejemplo 57200001).", "bancos"),
    "saldo_de_banco": ("El saldo del banco no cuadra", "El saldo contable de la cuenta del banco no coincide con su saldo inicial más los movimientos del banco.",
                       "Si el aviso nombra asientos manuales que mueven la cuenta del banco, páselos a «Movimientos de banco»: la línea del banco como movimiento y, en el asiento manual, lo demás. Si no, compare el saldo inicial del banco con el asiento de apertura y revise los movimientos; el Mayor de la cuenta ayuda a encontrar la diferencia.", "bancos"),
    "transferencia_sin_espejo": ("Transferencia incompleta", "Una de las dos mitades de una transferencia entre bancos ha desaparecido.",
                                 "Borre la transferencia que queda y créela de nuevo.", "movimientos"),
    "transferencia_importes": ("Transferencia con importes distintos", "Las dos mitades de la transferencia no tienen importes opuestos.",
                               "Borre la transferencia y créela de nuevo.", "movimientos"),
    "hueco_en_el_diario": ("Hueco en el libro diario", "Faltan números en la numeración del libro diario (se borraron asientos). No impide cerrar.",
                           "Si el libro diario va a legalizarse conviene que la numeración sea correlativa; decida con su asesor si hay que renumerar.", "diario"),
    "asiento_sin_documento": ("Asiento sin documento", "Es el asiento de una factura o de un movimiento de banco que ya no existe.",
                              "Borre el asiento huérfano o recupere el documento.", "diario"),
    "total_incoherente": ("Total de la factura incoherente", "El total no coincide con base + IVA + recargo + ajustes (por ejemplo una retención de IRPF).",
                          "Abra la factura y revise las líneas de IVA, los ajustes y el total: al guardar de nuevo se recalcula.", "facturas-recibidas"),
    "vencimiento_pagado_de_mas": ("Vencimiento pagado de más", "Se ha cobrado o pagado más de lo que importaba el vencimiento (el pendiente tiene el signo contrario).",
                                  "Revise los movimientos de banco que lo saldan y corrija el importe.", "vencimientos"),
    "justificante_ausente": ("Justificante que falta", "El justificante consta como adjuntado pero su fichero no está en el almacén.",
                             "Vuelva a subir el fichero en el documento, o quite el justificante si ya no existe.", None),
    "justificante_alterado": ("Justificante modificado", "El fichero del justificante ya no es el mismo que se adjuntó (su huella ha cambiado).",
                              "Compruebe si el cambio es legítimo; si no, recupere el original y sustitúyalo.", None),
    "fichero_huerfano": ("Fichero sin documento", "Hay un fichero en el almacén de justificantes que ningún documento utiliza.",
                         "Si es un justificante de verdad, adjúntelo al documento que corresponda; si sobra, bórrelo del almacén.", None),
    "gasto_sin_justificante": ("Gasto sin justificante", "La factura recibida no tiene ningún justificante (PDF o imagen) adjunto.",
                               "Adjunte la factura escaneada en el formulario de la factura.", "facturas-recibidas"),
    "amortizacion_del_ejercicio": ("Amortización que no cuadra con el cuadro", "La amortización contabilizada en el ejercicio en una cuenta de amortización acumulada no coincide con la dotación que dice el cuadro de los bienes de esa cuenta.",
                                   "Revise el cuadro del bien y los asientos de amortización del ejercicio («Amortizar los bienes de inversión», en el cierre, los genera). La amortización anterior a la primera apertura de Conta, la que trajo el programa anterior, no se compara.", "bienes"),
    "saldo_con_signo_raro": ("Saldo con signo raro", "Un cliente tiene saldo acreedor o un proveedor saldo deudor (suele ser un anticipo o un cobro o pago mal aplicado).",
                             "Revise el Mayor de la cuenta y los vencimientos del tercero.", "mayor"),
    "liquidacion_iva_desactualizada": ("Liquidación de IVA desactualizada", "Se contabilizaron facturas con fecha de un periodo ya liquidado, así que la liquidación grabada no coincide con el IVA actual.",
                                       "Abra el periodo en la liquidación del IVA y vuelva a liquidarlo si no se había presentado; si ya se presentó, consúltelo con su asesor.", "liquidacion-iva"),
    "liquidacion_distinta_de_la_presentada": ("Liquidación distinta de la presentada", "El asiento de liquidación del IVA no da el mismo resultado que la declaración (modelo 303) que se presentó.",
                                              "No se toca el asiento ni la declaración: consulte con su asesor si hace falta una complementaria o un asiento de regularización (por ejemplo, una prorrata no contabilizada).", "declaraciones"),
    "registro_de_cambios_roto": ("Registro de cambios alterado", "La cadena de huellas del registro de cambios no cuadra: alguien ha modificado o borrado una anotación (o el archivo de la base se ha tocado fuera del programa).",
                                 "No arregle nada encima: conserve la base tal cual, compárela con una copia de seguridad anterior y consulte con su asesor. Lo anotado a partir del fallo ya no es de fiar.", "auditoria"),
    "huellas_externas_no_coinciden": ("Huellas del registro fuera de la base", "Las huellas del registro de cambios que se guardaron fuera de la base (en cada copia, presentación o cierre) no coinciden con las de la base: se ha reescrito el registro, se ha vuelto a una copia anterior sin dejar constancia o el fichero de huellas se ha tocado.",
                                      "No arregle nada encima: conserve la base y el fichero huellas_registro tal cual, compárelos con una copia de seguridad anterior y consulte con su asesor.", "auditoria"),
    "normativa_por_revisar": ("Normativa por revisar", "Se ha abierto la época en que suele salir un diseño de registro, un calendario o una norma de los que depende Conta y no consta que se haya revisado.",
                              "Mírelo en «Normativa y diseños» y márquelo como revisado (o siga el procedimiento si hay cambios).", "normativa"),
    "normativa_cambio_en_la_sede": ("Cambio en un diseño de la sede", "La consulta a la sede de la AEAT indica que un diseño ha cambiado o que ya existe el del ejercicio siguiente.",
                                    "Siga el procedimiento de «Normativa y diseños»: bajar el diseño, compararlo con el anterior y adaptar el generador.", "normativa"),
    "plazo_deposito_proximo": ("Depósito de cuentas próximo a vencer", "Las cuentas anuales se depositan en el Registro Mercantil en el mes siguiente a su aprobación por la junta (que es antes del 30 de junio) y todavía no consta el envío.",
                               "Prepare el depósito en «Depósito de cuentas», ábralo con D2, envíelo y registre aquí el acuse.", "deposito-cuentas"),
    "plazo_deposito_ultima_semana": ("Depósito de cuentas a punto de vencer", "Queda una semana o menos para que venza el plazo del depósito de cuentas y no consta el envío.", "Deposítelas ya con D2 y registre el acuse.", "deposito-cuentas"),
    "plazo_deposito_vencido": ("Depósito de cuentas con el plazo vencido", "El plazo para depositar las cuentas ha vencido y no consta el envío: el Registro puede cerrar la hoja de la sociedad y la multa va de 1.200 a 60.000 €.",
                               "Deposítelas ya con D2 y registre el acuse.", "deposito-cuentas"),
    "plazo_libros_proximo": ("Legalización de libros próxima a vencer", "Los libros del ejercicio (diario, inventario y cuentas anuales, socios y actas) se legalizan en el Registro Mercantil en los cuatro meses siguientes al cierre y todavía no consta el envío.",
                             "Prepare los libros en «Legalización de libros», impórtelos en Legalia2, envíelos y registre aquí el acuse.", "legalizacion-libros"),
    "plazo_libros_ultima_semana": ("Legalización de libros a punto de vencer", "Queda una semana o menos para que venza el plazo de legalización de los libros y no consta el envío.", "Legalícelos ya y registre el acuse.", "legalizacion-libros"),
    "plazo_libros_vencido": ("Legalización de libros con el plazo vencido", "El plazo de cuatro meses para legalizar los libros ha vencido y no consta el envío: cuanto antes se haga, menos riesgo de sanción.", "Legalícelos ya con Legalia2 y registre el acuse.", "legalizacion-libros"),
    "plazo_modelo_proximo": ("Modelo de la AEAT próximo a vencer", "Un modelo (303, 111 o 190) todavía no consta presentado y su plazo vence dentro de dos meses o menos.",
                             "Prepare el borrador, genere el fichero y preséntelo en la sede; después registre la presentación subiendo el PDF que devuelve.", "modelos"),
    "plazo_modelo_ultima_semana": ("Modelo de la AEAT a punto de vencer", "Queda una semana o menos para que venza el plazo de un modelo que no consta presentado.",
                                   "Preséntelo ya. Para domiciliar el pago el plazo termina unos días antes que el de presentación.", "modelos"),
    "plazo_modelo_vencido": ("Modelo de la AEAT con el plazo vencido", "El plazo de un modelo ha vencido y no consta presentado: la presentación fuera de plazo puede llevar recargos y cuanto antes se haga, menos.",
                             "Preséntelo ya, aunque sea directamente en la sede de la AEAT, y registre después la presentación aquí (o impórtela) para que deje de aparecer.", "modelos"),
    "liquidacion_iva_no_calculable": ("Liquidación de IVA no calculable", "Faltan los parámetros del IVA (cuentas de Hacienda deudora y acreedora).",
                                      "Defínalos en «Parámetros del IVA», en la pantalla de liquidación.", "liquidacion-iva"),
}


PANTALLAS = {
    "asientos": "Asientos manuales", "cuentas": "Plan de cuentas", "facturas-recibidas": "Facturas recibidas", "diario": "Libro Diario", "movimientos": "Movimientos de banco",
    "facturas-emitidas": "Facturas emitidas", "bancos": "Bancos", "vencimientos": "Vencimientos pendientes", "bienes": "Bienes de inversión", "mayor": "Libro Mayor", "liquidacion-iva": "Liquidación del IVA", "declaraciones": "Declaraciones presentadas", "modelos": "Modelos de la AEAT (menú «Modelos de la AEAT» del panel)",
}


def nombre_de(codigo: str) -> str:
    return CATALOGO[codigo][0] if codigo in CATALOGO else codigo.replace("_", " ").capitalize()


def _clave(h: Hallazgo) -> str:
    return f"{h.codigo}~{hashlib.sha1((h.referencia + '|' + h.mensaje).encode('utf-8')).hexdigest()[:10]}"


def _hallazgos(ctx: Contexto) -> list[Hallazgo]:
    from conta_pridalac.servicios.normativa import hallazgos_de_normativa

    return sorted(auditar(ctx.sesion, ctx.ejercicio, almacen=ctx.config.almacen_de_adjuntos(), con_plazos=True) + hallazgos_de_normativa(ctx.config),
                  key=lambda h: (h.gravedad != "ERROR", h.codigo, h.referencia))


class ListadoAuditoria(Listado):
    nombre, titulo = "auditoria", "Auditoría de integridad"
    descripcion = "Comprobaciones de que la contabilidad es coherente. Los errores impiden cerrar el ejercicio; los avisos son cosas que conviene revisar. Doble clic para ver qué significa y cómo se corrige."
    columnas = [Col("gravedad", "Gravedad", TEXTO, 1), Col("comprobacion", "Comprobación", TEXTO, 2.5), Col("referencia", "Referencia", TEXTO, 1.5), Col("mensaje", "Qué ocurre", TEXTO, 6)]
    parametros = [
        Campo("gravedad", "Mostrar", "select", opciones=[("", "Errores y avisos"), ("ERROR", "Sólo errores"), ("AVISO", "Sólo avisos")]),
        Campo("comprobacion", "Comprobación", "select", opciones=[("", "Todas")] + sorted(((c, v[0]) for c, v in CATALOGO.items()), key=lambda x: x[1])),
    ]

    def filas(self, ctx, params):
        filas = []
        for h in _hallazgos(ctx):
            if params.get("gravedad") and h.gravedad != params["gravedad"]:
                continue
            if params.get("comprobacion") and h.codigo != params["comprobacion"]:
                continue
            filas.append(Fila(_clave(h), dict(gravedad="Error" if h.gravedad == ERROR else "Aviso", comprobacion=nombre_de(h.codigo), referencia=h.referencia, mensaje=h.mensaje),
                              clase="fila-error" if h.gravedad == ERROR else ""))
        return filas

    def resumen(self, ctx, filas):
        errores = sum(1 for f in filas if f.valores["gravedad"] == "Error")
        avisos = len(filas) - errores
        if not filas:
            return "✔ Sin hallazgos: la contabilidad pasa todas las comprobaciones."
        if ctx.ejercicio.cerrado:
            return f"{errores} error(es) y {avisos} aviso(s). Ejercicio cerrado: son sólo informativos, no se corrige la contabilidad de un ejercicio cerrado salvo que afecte al ejercicio en curso."
        return f"{errores} error(es) y {avisos} aviso(s)" + (" — hay que corregir los errores antes de cerrar el ejercicio (los de plazos de modelos no lo impiden, pero hay que presentarlos)." if errores else ".")

    def detalle(self, ctx, id):
        h = next((h for h in _hallazgos(ctx) if _clave(h) == id), None)
        if h is None:
            return None
        nombre, que, como, pantalla = CATALOGO.get(h.codigo, (nombre_de(h.codigo), "", "", None))
        m = re.fullmatch(r"(\d+)\.(\d+)(?:/(\d+))?", h.referencia or "")
        if m:  # si la referencia es un asiento, la pantalla donde se arregla depende de su tipo (factura, banco, manual…)
            pantalla = {1: "facturas-emitidas", 2: "facturas-recibidas", 3: "movimientos", 4: "asientos"}.get(int(m.group(1)), "diario")
        filas = [["Gravedad", ("Error: hay que actuar ya" if h.codigo.startswith("plazo_") else "Error: impide cerrar el ejercicio") if h.gravedad == ERROR else "Aviso: conviene revisarlo"], ["Comprobación", nombre], ["Referencia", h.referencia or "—"], ["Qué ocurre", h.mensaje]]
        if que:
            filas.append(["Qué significa", que])
        if como:
            filas.append(["Cómo se corrige", como])
        if pantalla:
            filas.append(["Dónde", f"Pantalla «{PANTALLAS.get(pantalla, pantalla)}»"])
        extras = []
        if m:  # la referencia es un asiento: se enseña su contenido
            a = ctx.sesion.scalars(select(Asiento).where(Asiento.ejercicio_id == ctx.ejercicio.id, Asiento.tipo == int(m.group(1)), Asiento.numero == int(m.group(2)), Asiento.sub == int(m.group(3) or 0))).first()
            if a is not None:
                lineas = [[ap.cuenta.codigo, ap.cuenta.nombre, ap.debe or None, ap.haber or None] for ap in a.apuntes]
                extras.append(Tabla(f"Asiento {a.identificador} · {a.fecha:%d/%m/%Y} · {a.concepto or 'sin concepto'}", [Columna("Cuenta", ancho=1.2), Columna("Nombre", ancho=3), Columna("Debe", DINERO, 1.2), Columna("Haber", DINERO, 1.2)], lineas))
        enlaces = []
        factura = self._factura_de(ctx, h.referencia, m)
        if factura is not None:  # el error es de una factura: se abre ella misma, no el listado
            destino = "facturas-emitidas" if factura.sentido == "E" else "facturas-recibidas"
            enlaces.append((f"Abrir la factura {'emitida' if factura.sentido == 'E' else 'recibida'} nº {factura.numero}", f"/e/{ctx.slug}/{ctx.ejercicio.anio}/{destino}?abrir={factura.id}"))
        if pantalla:
            enlaces.append((f"Ir a «{PANTALLAS.get(pantalla, pantalla)}»", {"normativa": "/normativa", "programa": "/programa"}.get(pantalla) or f"/e/{ctx.slug}/{ctx.ejercicio.anio}/{pantalla}"))
        return Detalle(
            ("Error" if h.gravedad == ERROR else "Aviso") + f": {nombre}",
            Tabla("Hallazgo", [Columna("Dato", ancho=1.3), Columna("Valor", ancho=6)], filas), [], extras, enlaces=enlaces,
        )

    @staticmethod
    def _factura_de(ctx, referencia: str, m) -> Factura | None:
        """La factura a la que se refiere un hallazgo: por «R 142» / «E 3» o por el asiento 2.142 (tipo 1 emitidas, 2 recibidas)."""
        sentido = numero = None
        if (r := re.fullmatch(r"([ER]) (\d+)", referencia or "")):
            sentido, numero = r.group(1), int(r.group(2))
        elif m and int(m.group(1)) in (1, 2):
            sentido, numero = "E" if int(m.group(1)) == 1 else "R", int(m.group(2))
        if sentido is None:
            return None
        return ctx.sesion.scalars(select(Factura).where(Factura.ejercicio_id == ctx.ejercicio.id, Factura.sentido == sentido, Factura.numero == numero)).first()

    def totales(self, filas):
        return None
