"""Listados «de gestión» de contabilidad por rango de fechas: saldos acumulados de un mes, balance de situación y pérdidas y ganancias (`servicios/estados_contables.py`)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.exportacion.tabla import DINERO, TEXTO
from conta_pridalac.servicios.cuentas_anuales import COLUMNAS_PN
from conta_pridalac.servicios.estados_contables import balance_de_situacion, cuenta_de_perdidas_y_ganancias, saldos_acumulados
from conta_pridalac.web.listados import Campo, Col, Contexto, Fila, Listado

CERO = Decimal("0.00")
MESES = [("1", "Enero"), ("2", "Febrero"), ("3", "Marzo"), ("4", "Abril"), ("5", "Mayo"), ("6", "Junio"), ("7", "Julio"), ("8", "Agosto"), ("9", "Septiembre"), ("10", "Octubre"), ("11", "Noviembre"), ("12", "Diciembre")]
PARAMETROS_FECHAS = [Campo("desde", "Desde", "fecha"), Campo("hasta", "Hasta", "fecha")]
CIERRE = Campo("cierre", "Regularización y cierre", "select", opciones=[("no", "Sin incluir (estado previo al cierre)"), ("si", "Incluidos")], defecto="no")
CLASES = {"titulo": "resumen", "subtotal": "resumen", "total": "resumen total"}


def _mes_por_defecto(ctx: Contexto) -> str:
    """El mes de hoy si está en el ejercicio; si no, diciembre (un ejercicio ya terminado)."""
    hoy = date.today()
    return str(hoy.month) if hoy.year == ctx.ejercicio.anio else "12"


class ListadoSaldosAcumulados(Listado):
    nombre, titulo = "saldos-acumulados", "Saldos acumulados de un mes"
    descripcion = "Por cuenta, el saldo hasta el mes anterior, lo movido en el mes elegido y el saldo acumulado a final de ese mes (desde el inicio del ejercicio)."
    columnas = [
        Col("cuenta", "Cuenta", TEXTO, 1), Col("nombre", "Nombre", TEXTO, 4), Col("anterior", "Saldo anterior", DINERO, 1.3), Col("debe", "Debe del mes", DINERO, 1.3),
        Col("haber", "Haber del mes", DINERO, 1.3), Col("deudor", "Saldo deudor", DINERO, 1.3), Col("acreedor", "Saldo acreedor", DINERO, 1.3),
    ]
    parametros = [
        Campo("mes", "Mes", "select", opciones=MESES, defecto="12"),
        Campo("nivel", "Agrupar a", "select", opciones=[("12", "Subcuentas (código completo)"), ("3", "3 dígitos (cuentas)"), ("2", "2 dígitos (subgrupos)"), ("1", "1 dígito (grupos)")], defecto="12"), CIERRE,
    ]

    def filas(self, ctx, params):
        mes = int(params.get("mes") or _mes_por_defecto(ctx))
        return [
            Fila(f.cuenta, dict(cuenta=f.cuenta, nombre=f.nombre, anterior=f.anterior or None, debe=f.debe or None, haber=f.haber or None, deudor=f.deudor or None, acreedor=f.acreedor or None))
            for f in saldos_acumulados(ctx.sesion, ctx.ejercicio, mes, nivel=int(params.get("nivel") or 12), incluir_cierre=params.get("cierre") == "si")
        ]

    def subtitulo(self, ctx, params):
        mes = int(params.get("mes") or _mes_por_defecto(ctx))
        return f"{ctx.empresa.nombre} · ejercicio {ctx.ejercicio.anio} · acumulado a fin de {dict(MESES)[str(mes)].lower()}"

    def totales(self, filas):
        return {k: sum((f.valores.get(k) or CERO for f in filas), CERO) for k in ("debe", "haber", "deudor", "acreedor")}


class ListadoPerdidasYGanancias(Listado):
    nombre, titulo = "perdidas-ganancias", "Pérdidas y ganancias"
    descripcion = "Ingresos (grupo 7) y gastos (grupo 6) del rango de fechas, por subgrupo o por cuenta, y su resultado. Es un listado de gestión, no el modelo oficial del Registro Mercantil."
    columnas = [Col("cuenta", "Cuenta", TEXTO, 1), Col("concepto", "Concepto", TEXTO, 6), Col("importe", "Importe", DINERO, 1.5)]
    parametros = [Campo("nivel", "Detalle", "select", opciones=[("2", "Por subgrupo (2 dígitos)"), ("3", "Por cuenta (3 dígitos)"), ("12", "Por subcuenta (código completo)")], defecto="2"), CIERRE] + PARAMETROS_FECHAS

    def filas(self, ctx, params):
        lineas = cuenta_de_perdidas_y_ganancias(ctx.sesion, ctx.ejercicio, desde=params.get("desde"), hasta=params.get("hasta"), nivel=int(params.get("nivel") or 2), incluir_cierre=params.get("cierre") == "si")
        return [Fila(None, dict(cuenta=l.codigo if l.tipo == "cuenta" else "", concepto=l.nombre, importe=l.importe), clase=CLASES.get(l.tipo, "")) for l in lineas]

    def texto_vacio(self, ctx, params):
        return "No hay ingresos ni gastos en esas fechas"


class ListadoBalanceSituacion(Listado):
    nombre, titulo = "balance-situacion", "Balance de situación"
    descripcion = ("Activo y patrimonio neto y pasivo por cuenta, con el resultado del ejercicio. Los saldos de los grupos 4 y 5 van al activo o al pasivo según su signo. "
                   "Es un listado de gestión, no el modelo oficial del Registro Mercantil.")
    columnas = [Col("cuenta", "Cuenta", TEXTO, 1), Col("concepto", "Concepto", TEXTO, 6), Col("importe", "Importe", DINERO, 1.5)]
    parametros = PARAMETROS_FECHAS + [CIERRE]

    def filas(self, ctx, params):
        lineas = balance_de_situacion(ctx.sesion, ctx.ejercicio, desde=params.get("desde"), hasta=params.get("hasta"), incluir_cierre=params.get("cierre") == "si")
        return [Fila(None, dict(cuenta=l.codigo, concepto=l.nombre, importe=l.importe), clase=CLASES.get(l.tipo, "")) for l in lineas]

    def texto_vacio(self, ctx, params):
        return "No hay movimientos en esas fechas"


# ------------------------------------------------------------------------------------------------ modelos oficiales (PYMES y entidades sin fines lucrativos)


def _solo_pymes(ctx: Contexto, que: str) -> None:
    """El estado de cambios en el patrimonio neto es el del PGC de PYMES: una entidad sin fines lucrativos no lo tiene aparte (va en su cuenta de resultados)."""
    if ctx.empresa.tipo_plan != "pymes":
        raise ErrorContable(f"{que} es un modelo del PGC de pequeñas y medianas empresas y no corresponde al plan de cuentas de esta empresa "
                            "(entidad sin fines lucrativos): sus cambios en el patrimonio neto van dentro de la cuenta de resultados, en las secciones B a I.")


def _estados_oficiales(ctx: Contexto, funcion):
    """El estado del ejercicio y el del anterior (si existe), línea a línea."""
    from conta_pridalac.servicios.cuentas_anuales import ejercicio_anterior

    actual = funcion(ctx.sesion, ctx.ejercicio)
    anterior_ej = ejercicio_anterior(ctx.sesion, ctx.ejercicio)
    return actual, (funcion(ctx.sesion, anterior_ej) if anterior_ej is not None else None), anterior_ej


def _filas_oficiales(actual, anterior) -> list[Fila]:
    previas = {l.id: l.importe for l in anterior.lineas} if anterior is not None else {}
    filas = []
    for l in actual.lineas:
        sangria = "\u00a0" * (4 * l.nivel)
        mostrar = lambda v: v if v else None  # noqa: E731  (el modelo imprime en blanco lo que es cero)
        filas.append(Fila(None, dict(concepto=sangria + l.etiqueta, actual=mostrar(l.importe), anterior=mostrar(previas.get(l.id))), clase="resumen total" if l.total and l.nivel == 0 else ("resumen" if l.total else "")))
    return filas


class _ListadoOficial(Listado):
    funciones: dict = {}  # tipo de plan → función que calcula el estado

    def _funcion(self, ctx):
        return type(self).funciones[ctx.empresa.tipo_plan]

    columnas = [Col("concepto", "Concepto", TEXTO, 8), Col("actual", "Ejercicio", DINERO, 1.6), Col("anterior", "Ejercicio anterior", DINERO, 1.6)]

    def filas(self, ctx, params):
        actual, anterior, _ = _estados_oficiales(ctx, self._funcion(ctx))
        return _filas_oficiales(actual, anterior)

    def subtitulo(self, ctx, params):
        from conta_pridalac.servicios.cuentas_anuales import ejercicio_anterior

        previo = ejercicio_anterior(ctx.sesion, ctx.ejercicio)
        return f"{ctx.empresa.nombre} · {ctx.empresa.nif or ''} · ejercicio {ctx.ejercicio.anio}" + (f" (comparado con {previo.anio})" if previo else "")

    def resumen(self, ctx, filas):
        actual, _, _ = _estados_oficiales(ctx, self._funcion(ctx))
        notas = []
        if actual.sin_asignar:
            notas.append(f"{len(actual.sin_asignar)} cuenta(s) con saldo sin línea en el modelo: " + ", ".join(f"{c} ({s})" for c, _, s in actual.sin_asignar[:5]))
        notas += actual.avisos[:3]
        if len(actual.avisos) > 3:
            notas.append(f"y {len(actual.avisos) - 3} aviso(s) más")
        return " · ".join(notas) if notas else None


def _balance(sesion, ejercicio):
    from conta_pridalac.servicios.cuentas_anuales import balance_pymes

    return balance_pymes(sesion, ejercicio)


def _pyg(sesion, ejercicio):
    from conta_pridalac.servicios.cuentas_anuales import pyg_pymes

    return pyg_pymes(sesion, ejercicio)


def _balance_esfl(sesion, ejercicio):
    from conta_pridalac.servicios.cuentas_anuales_esfl import balance_esfl

    return balance_esfl(sesion, ejercicio)


def _resultados_esfl(sesion, ejercicio):
    from conta_pridalac.servicios.cuentas_anuales_esfl import cuenta_resultados_esfl

    return cuenta_resultados_esfl(sesion, ejercicio)


class ListadoBalanceOficial(_ListadoOficial):
    nombre, titulo = "balance-oficial", "Balance oficial (PYMES y ONG)"
    descripcion = ("Balance del ejercicio según el modelo oficial de su plan de cuentas (PYMES, o pequeñas y medianas entidades sin fines lucrativos), con las líneas del modelo y el ejercicio anterior. "
                   "Las cuentas con saldo de signo contrario al de su línea se restan dentro de ella, como en el programa anterior, y se avisa. No incluye regularización ni cierre.")
    funciones = {"pymes": _balance, "esfl": _balance_esfl}


class ListadoPyGOficial(_ListadoOficial):
    nombre, titulo = "pyg-oficial", "Pérdidas y ganancias oficial (PYMES y ONG)"
    descripcion = ("Cuenta de pérdidas y ganancias (en una entidad sin fines lucrativos, cuenta de resultados con las variaciones del patrimonio neto) del ejercicio según el modelo oficial de su plan de cuentas, "
                   "con las líneas del modelo y el ejercicio anterior (gastos en negativo). No incluye regularización ni cierre.")
    funciones = {"pymes": _pyg, "esfl": _resultados_esfl}


class ListadoEstadoCambiosPN(Listado):
    nombre, titulo = "estado-cambios-pn", "Estado de cambios en el patrimonio neto (PYMES)"
    descripcion = ("Del saldo final del ejercicio anterior al saldo final de éste, con una columna por componente del patrimonio neto. «Operaciones con socios» recoge capital, prima, acciones propias, aportaciones y dividendo a cuenta; "
                   "«Otras variaciones» es lo que falta hasta el saldo final (normalmente, la aplicación del resultado del año anterior). Las cuentas de cada columna son las del balance oficial.")
    columnas = [Col("concepto", "Concepto", TEXTO, 5)] + [Col(k, t, DINERO, 1.3) for k, t, _ in COLUMNAS_PN] + [Col("total", "TOTAL", DINERO, 1.4)]

    def filas(self, ctx, params):
        from conta_pridalac.servicios.cuentas_anuales import COLUMNAS_PN, estado_cambios_pn

        _solo_pymes(ctx, self.titulo)
        return [
            Fila(None, dict(concepto=f.etiqueta, **{k: (f.valores.get(k) or None) for k, _, _ in COLUMNAS_PN}, total=f.suma or None), clase="resumen total" if f.total else "")
            for f in estado_cambios_pn(ctx.sesion, ctx.ejercicio).filas
        ]

    def subtitulo(self, ctx, params):
        return f"{ctx.empresa.nombre} · {ctx.empresa.nif or ''} · ejercicio {ctx.ejercicio.anio}"

    def resumen(self, ctx, filas):
        from conta_pridalac.servicios.cuentas_anuales import estado_cambios_pn

        if ctx.empresa.tipo_plan != "pymes":
            return None
        avisos = estado_cambios_pn(ctx.sesion, ctx.ejercicio).avisos
        return " · ".join(avisos) if avisos else None
