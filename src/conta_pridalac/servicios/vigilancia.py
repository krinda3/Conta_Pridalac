"""Vigilancia de los plazos de presentación de los modelos de la AEAT (303, 111, 115, 202, 190, 180, 347 y 390).

Para cada modelo y periodo del ejercicio que no consta presentado (ni por este programa ni importado del programa anterior; lo anterior a la primera presentación que consta de ese modelo no se juzga):

- **aviso** desde dos meses antes de que venza el plazo (`plazo_modelo_proximo`);
- **error** en la última semana (`plazo_modelo_ultima_semana`) y a partir de que vence (`plazo_modelo_vencido`): si ha vencido, hay que presentarlo ya, aunque sea directamente en la sede de la AEAT.

El 303 y el 111 se presentan todos los trimestres (sin actividad si no hay nada) y el 202 en abril, octubre y diciembre (con resultado cero si no hay IS que pagar). El 115 sólo en los trimestres con retenciones por alquileres y el 180 sólo si las hubo en el año. El 190 sólo si en el año hubo retenciones, el 347 sólo si algún tercero superó el umbral y el 390 sólo si hubo IVA en el año (desde el ejercicio 2026). No es una comprobación de la contabilidad, así que `auditar` sólo la hace si se le pide
(`con_plazos=True`) y nunca impide cerrar un ejercicio.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from conta_pridalac.auditoria import AVISO, ERROR, Hallazgo
from sqlalchemy import select

from conta_pridalac.db.modelos import BORRADOR, ENVIADA, GENERADA, PRESENTADA, DeclaracionPresentada, DepositoCuentas, Ejercicio, Empresa, Legalizacion, PresentacionAeat
from conta_pridalac.servicios.empresa import modelos_de
from conta_pridalac.servicios.plazos import fin_del_deposito, plazo
from conta_pridalac.servicios.presentacion303 import etiqueta_periodo, presentada_del_periodo

ANTELACION_AVISO = timedelta(days=60)
ULTIMA_SEMANA = timedelta(days=7)
MODELOS_TRIMESTRALES = ("303", "111")
PRIMER_EJERCICIO_390 = 2026  # los 390 anteriores se presentaron desde el programa anterior y no están en el programa: no se juzgan
PRIMER_EJERCICIO_LIBROS = 2026  # los libros de 2025 y anteriores ya se legalizaron con el programa anterior
PRIMER_EJERCICIO_DEPOSITO = 2026  # las cuentas de 2025 y anteriores ya se depositaron con el programa anterior
PRIMER_PAGO_202 = (2026, 3)  # los 202 anteriores al 3P de 2026 se presentaron desde el programa anterior: no se juzgan (aunque se importen)


def hoy() -> date:
    return date.today()


def _situacion(sesion: Session, ejercicio: Ejercicio, modelo: str, periodo: int) -> str:
    """Qué hay hecho de ese periodo sin estar presentado, para decirlo en el mensaje."""
    pendiente = sesion.query(PresentacionAeat).filter(
        PresentacionAeat.empresa_id == ejercicio.empresa_id, PresentacionAeat.modelo == modelo, PresentacionAeat.anio == ejercicio.anio,
        PresentacionAeat.periodo == etiqueta_periodo(modelo, periodo), PresentacionAeat.estado.in_((BORRADOR, GENERADA)),
    ).order_by(PresentacionAeat.id.desc()).first()
    if pendiente is None:
        return "sin empezar"
    return "con el fichero generado pero sin registrar la presentación" if pendiente.estado == GENERADA else "con un borrador"


def _primera_presentacion(sesion: Session, empresa_id: int, modelo: str) -> tuple[int, int] | None:
    """(ejercicio, periodo) de la primera presentación que consta de ese modelo, nuestra o importada. Lo anterior no se puede juzgar: es de antes de los datos que tiene el programa."""
    conocidas = [(d.anio, d.periodo) for d in sesion.scalars(select(DeclaracionPresentada).where(DeclaracionPresentada.empresa_id == empresa_id, DeclaracionPresentada.modelo == modelo))]
    conocidas += [(p.anio, int(p.periodo[0])) for p in sesion.scalars(select(PresentacionAeat).where(
        PresentacionAeat.empresa_id == empresa_id, PresentacionAeat.modelo == modelo, PresentacionAeat.estado == PRESENTADA))]
    return min(conocidas) if conocidas else None


def debe_presentar_390(sesion: Session, ejercicio: Ejercicio) -> bool:
    """El 390 se presenta desde el ejercicio 2026 y sólo si hubo IVA en el año (sin IVA no hay resumen que presentar)."""
    if ejercicio.anio < PRIMER_EJERCICIO_390:
        return False
    from conta_pridalac.servicios.modelo390 import calcular_390

    casillas = calcular_390(sesion, ejercicio).casillas
    return bool(casillas.get(33) or casillas.get(64))


def _obligaciones(sesion: Session, ejercicio: Ejercicio) -> list[tuple[str, int, str]]:
    """(modelo, periodo, nombre del periodo) de lo que hay que presentar por este ejercicio."""
    obligaciones = [(m, t, f"{t}T {ejercicio.anio}") for m in MODELOS_TRIMESTRALES for t in (1, 2, 3, 4)]
    from conta_pridalac.servicios.modelo190 import calcular_190

    if calcular_190(sesion, ejercicio).perceptores:  # sin retenciones no hay resumen anual que presentar
        obligaciones.append(("190", 0, f"ejercicio {ejercicio.anio}"))
    from conta_pridalac.servicios.modelo115 import calcular_115
    from conta_pridalac.servicios.modelo180 import calcular_180

    obligaciones += [("115", t, f"{t}T {ejercicio.anio}") for t in (1, 2, 3, 4) if calcular_115(sesion, ejercicio, t).lineas]  # sin alquiler con retención no hay 115 que presentar
    if calcular_180(sesion, ejercicio).arrendadores:
        obligaciones.append(("180", 0, f"ejercicio {ejercicio.anio}"))
    if debe_presentar_390(sesion, ejercicio):
        obligaciones.append(("390", 0, f"ejercicio {ejercicio.anio}"))
    obligaciones += [("202", p, f"{p}P {ejercicio.anio}") for p in (1, 2, 3) if (ejercicio.anio, p) >= PRIMER_PAGO_202]
    from conta_pridalac.servicios.modelo347 import calcular_347

    if calcular_347(sesion, ejercicio).declarados:  # si nadie supera el umbral no hay declaración anual de operaciones
        obligaciones.append(("347", 0, f"ejercicio {ejercicio.anio}"))
    return obligaciones


def _plazo_de_los_libros(sesion: Session, ejercicio: Ejercicio, dia: date) -> list[Hallazgo]:
    """La legalización de los libros del ejercicio (cuatro meses desde el cierre): si no consta enviada al Registro Mercantil, avisa igual que con los modelos de la AEAT."""
    if ejercicio.anio < PRIMER_EJERCICIO_LIBROS:
        return []
    leg = sesion.scalar(select(Legalizacion).where(Legalizacion.empresa_id == ejercicio.empresa_id, Legalizacion.anio == ejercicio.anio))
    if leg is not None and leg.estado == ENVIADA:
        return []
    p = plazo("LIBROS", ejercicio.anio)
    if dia < p.fin - ANTELACION_AVISO:
        return []
    dias = (p.fin - dia).days
    situacion = "sin empezar" if leg is None else "con los libros preparados pero sin registrar el envío"
    referencia = f"libros {ejercicio.anio}"
    if dias < 0:
        return [Hallazgo("plazo_libros_vencido", ERROR, f"La legalización de los libros de {ejercicio.anio} NO está enviada y el plazo venció el {p.fin:%d/%m/%Y} (hace {-dias} día(s)), {situacion}. Legalícelos ya con Legalia2 y registre aquí el envío.", referencia)]
    if dias <= ULTIMA_SEMANA.days:
        return [Hallazgo("plazo_libros_ultima_semana", ERROR, f"URGENTE: la legalización de los libros de {ejercicio.anio} vence {'hoy' if dias == 0 else f'en {dias} día(s)'} ({p.fin:%d/%m/%Y}) y no está enviada, {situacion}.", referencia)]
    return [Hallazgo("plazo_libros_proximo", AVISO, f"La legalización de los libros de {ejercicio.anio} vence el {p.fin:%d/%m/%Y} (dentro de {dias} días) y todavía no está enviada, {situacion}.", referencia)]


def _plazo_del_deposito(sesion: Session, ejercicio: Ejercicio, dia: date) -> list[Hallazgo]:
    """El depósito de las cuentas del ejercicio (un mes desde su aprobación): si no consta enviado al Registro Mercantil, avisa igual que con los modelos de la AEAT."""
    if ejercicio.anio < PRIMER_EJERCICIO_DEPOSITO:
        return []
    dep = sesion.scalar(select(DepositoCuentas).where(DepositoCuentas.empresa_id == ejercicio.empresa_id, DepositoCuentas.anio == ejercicio.anio))
    if dep is not None and dep.estado == ENVIADA:
        return []
    fin = fin_del_deposito(ejercicio.anio, dep.fecha_aprobacion if dep is not None else None)
    if dia < fin - ANTELACION_AVISO:
        return []
    dias = (fin - dia).days
    situacion = "sin empezar" if dep is None or not dep.carpeta_ruta else "con la carpeta preparada pero sin registrar el envío"
    referencia = f"depósito {ejercicio.anio}"
    if dias < 0:
        return [Hallazgo("plazo_deposito_vencido", ERROR, f"El depósito de las cuentas de {ejercicio.anio} NO consta enviado y el plazo venció el {fin:%d/%m/%Y} (hace {-dias} día(s)), {situacion}. Deposítelas ya con D2 y registre aquí el envío.", referencia)]
    if dias <= ULTIMA_SEMANA.days:
        return [Hallazgo("plazo_deposito_ultima_semana", ERROR, f"URGENTE: el depósito de las cuentas de {ejercicio.anio} vence {'hoy' if dias == 0 else f'en {dias} día(s)'} ({fin:%d/%m/%Y}) y no consta enviado, {situacion}.", referencia)]
    return [Hallazgo("plazo_deposito_proximo", AVISO, f"El depósito de las cuentas de {ejercicio.anio} vence el {fin:%d/%m/%Y} (dentro de {dias} días) y todavía no consta enviado, {situacion}.", referencia)]


def plazos_de_modelos(sesion: Session, ejercicio: Ejercicio, dia: date | None = None) -> list[Hallazgo]:
    dia = dia or hoy()
    hallazgos = []
    presenta = modelos_de(sesion.get(Empresa, ejercicio.empresa_id))  # sólo se vigila lo que la empresa presenta (casillas de su ficha)
    primeras = {m: _primera_presentacion(sesion, ejercicio.empresa_id, m) for m in ("303", "111", "115", "202", "190", "180", "347", "390")}
    if "mercantil" in presenta:
        hallazgos += _plazo_de_los_libros(sesion, ejercicio, dia)
        hallazgos += _plazo_del_deposito(sesion, ejercicio, dia)
    for modelo, periodo, nombre in _obligaciones(sesion, ejercicio):
        if modelo not in presenta:
            continue
        if primeras[modelo] is not None and (ejercicio.anio, periodo) < primeras[modelo]:
            continue
        if presentada_del_periodo(sesion, ejercicio.empresa_id, ejercicio.anio, periodo, modelo) is not None:
            continue
        p = plazo(modelo, ejercicio.anio, periodo)
        if dia < p.fin - ANTELACION_AVISO:
            continue
        dias = (p.fin - dia).days
        situacion = _situacion(sesion, ejercicio, modelo, periodo)
        domiciliar = f" Para domiciliar el pago, hasta el {p.fin_domiciliacion:%d/%m/%Y}." if modelo in MODELOS_TRIMESTRALES + ("115", "202") and p.fin_domiciliacion and dia <= p.fin_domiciliacion else ""
        referencia = f"{modelo} {nombre}"
        if dias < 0:
            hallazgos.append(Hallazgo(
                "plazo_modelo_vencido", ERROR,
                f"El modelo {modelo} del {nombre} NO está presentado y el plazo venció el {p.fin:%d/%m/%Y} (hace {-dias} día(s)), {situacion}. Presente ya, aunque sea directamente en la sede de la AEAT, y registre después la presentación aquí.", referencia))
        elif dias <= ULTIMA_SEMANA.days:
            hallazgos.append(Hallazgo(
                "plazo_modelo_ultima_semana", ERROR,
                f"URGENTE: el modelo {modelo} del {nombre} vence {'hoy' if dias == 0 else f'en {dias} día(s)'} ({p.fin:%d/%m/%Y}) y no está presentado, {situacion}.{domiciliar}", referencia))
        else:
            hallazgos.append(Hallazgo(
                "plazo_modelo_proximo", AVISO,
                f"El modelo {modelo} del {nombre} vence el {p.fin:%d/%m/%Y} (dentro de {dias} días) y todavía no está presentado, {situacion}.{domiciliar}", referencia))
    return hallazgos


def plazos_de_la_empresa(sesion: Session, ejercicios: list[Ejercicio], dia: date | None = None) -> list[Hallazgo]:
    """Los plazos de este año y del anterior (el 4T y el 190 del año pasado vencen en enero), para avisar desde el panel aunque se esté en otro ejercicio."""
    dia = dia or hoy()
    hallazgos = []
    for ej in ejercicios:
        if ej.anio in (dia.year - 1, dia.year):
            hallazgos += plazos_de_modelos(sesion, ej, dia)
    return sorted(hallazgos, key=lambda h: (h.gravedad != ERROR, h.codigo != "plazo_modelo_vencido", h.referencia))
