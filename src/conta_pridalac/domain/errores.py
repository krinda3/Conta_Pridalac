"""Errores de las reglas contables. Los mensajes están pensados para mostrarse tal cual al usuario."""


class ErrorContable(Exception):
    """Base de los errores que impiden grabar algo contablemente incorrecto."""


class FechaInvalida(ErrorContable):
    """El texto no es una fecha válida del calendario."""


class FechaFueraDePeriodo(ErrorContable):
    """La fecha no pertenece al ejercicio contable de trabajo."""


class EjercicioCerrado(ErrorContable):
    """El ejercicio está cerrado: no admite asientos nuevos sin reabrirlo."""


class AsientoDescuadrado(ErrorContable):
    """La suma del debe no es igual a la del haber."""


class CuentaNoAdmiteApuntes(ErrorContable):
    """La cuenta no existe o es de grupo (menos de 8 dígitos): solo las subcuentas admiten apuntes."""


class DocumentoConPagos(ErrorContable):
    """No se puede borrar o modificar un documento que ya tiene cobros o pagos aplicados."""
