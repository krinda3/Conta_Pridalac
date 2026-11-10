"""Plantillas de asientos manuales (MGD `Explant`, `vNuevoExtra`, `vPlConcreta`).

Formato de cada línea del memo `CONTENIDO` (campos separados por `|`):
    cuenta | ayuda | D/H/C | importe de muestra | reglas de vencimiento (separadas por comas)

`C` (cuadre) es la línea que equilibra el asiento: sale por el Haber si el resto deja Debe de más y por el Debe si no.
Una plantilla no puede tener más de una línea de cuadre. El título admite `{año}`, `{mes}`, `{cmes}`, `{trimestre}`…
y operaciones, p. ej. `NOMINA {mes}/{año}` o `{mes-1}`.

Reglas de vencimiento: `D<op><n> M<op><n> A<op><n> [PT|PM|PL] [DP<lista>]` (ver `fecha_de_vencimiento`).
"""
from __future__ import annotations

import ast
import calendar
import operator
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from conta_pridalac.db.tipos import dinero
from conta_pridalac.domain.errores import ErrorContable

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


# ------------------------------------------------------------------------------------------------ texto


_TOKEN = re.compile(r"cuatrimestre|trimestre|año|cmes|mes|cdia|dia", re.IGNORECASE)
_OPERADORES = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _calcular(expresion: str):
    """Evalúa una operación aritmética sencilla sin usar `eval`. Devuelve `None` si no es una operación."""

    def nodo(n):
        if isinstance(n, ast.Expression):
            return nodo(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPERADORES:
            return _OPERADORES[type(n.op)](nodo(n.left), nodo(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -nodo(n.operand) if isinstance(n.op, ast.USub) else nodo(n.operand)
        raise ValueError

    try:
        valor = nodo(ast.parse(expresion.strip(), mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None
    return int(valor) if float(valor).is_integer() else valor


def evaluar_texto(texto: str, fecha: date) -> str:
    """Sustituye los `{…}` del título por valores de la fecha. `NOMINA {mes}/{año}` con 05/03/2026 → `NOMINA 3/2026`."""

    def valor(token: str) -> str:
        t = token.lower()
        if t == "año":
            return str(fecha.year)
        if t == "mes":
            return str(fecha.month)
        if t == "dia":
            return str(fecha.day)
        if t == "trimestre":
            return str((fecha.month - 1) // 3 + 1)
        if t == "cuatrimestre":
            return str((fecha.month - 1) // 4 + 1)
        nombre = MESES[fecha.month - 1] if t == "cmes" else DIAS[fecha.weekday()]
        return nombre.upper() if token.isupper() else nombre.lower() if token.islower() else nombre

    salida, resto = [], texto
    while (i := resto.find("{")) >= 0:
        salida.append(resto[:i])
        resto = resto[i + 1 :]
        j = resto.find("}")
        if j < 0:  # llave sin cerrar: MGD descarta la llave y deja el resto tal cual
            break
        dentro, resto = resto[:j], resto[j + 1 :]
        if dentro == "":
            salida.append("{")
            continue
        sustituido = _TOKEN.sub(lambda m: valor(m.group(0)), dentro)
        calculado = _calcular(sustituido) if re.fullmatch(r"[\d\s+\-*/().]+", sustituido) else None
        salida.append(str(calculado) if calculado is not None else sustituido)
    return "".join(salida) + resto


# ------------------------------------------------------------------------------------------------ fechas


def _fecha_real(anio: int, mes: int, dia: int) -> date:
    """Fecha con el mes normalizado (el 13 es enero del año siguiente) y el día recortado al fin de mes."""
    anio += (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def _dias_de_pago(lista: str) -> list[tuple[int, int, int]]:
    """`5,25,12-27`, `12-`, `-25` → [(tipo, n1, n2)] (`CadenaNumerosCad2Array`)."""
    resultado = []
    for parte in lista.split(","):
        if not parte or parte == "-" or parte.count("-") > 1:
            raise ValueError(lista)
        if "-" not in parte:
            resultado.append((1, int(parte), 0))
        else:
            a, b = parte.split("-")
            if not b:
                resultado.append((2, int(a), 0))
            elif not a:
                resultado.append((4, int(b), 0))
            elif int(b) < int(a):
                raise ValueError(lista)
            else:
                resultado.append((3, int(a), int(b)))
    return resultado


def _esta_en(lista: list[tuple[int, int, int]], n: int) -> bool:
    for tipo, a, b in lista:
        if (tipo == 1 and n == a) or (tipo == 2 and n >= a) or (tipo == 3 and a <= n <= b) or (tipo == 4 and n <= a):
            return True
    return False


def fecha_de_vencimiento(modelo: str, fecha: date) -> date | None:
    """Fecha de vencimiento que resulta de aplicar una regla a la fecha del asiento (`VtoAutomatico2Fecha`).

    Bloques: `D`, `M`, `A` (día, mes, año) más opcionales. Con `=` fijan el valor (`D=25`); con `+`/`-` suman o restan
    (`M+1`); sin número (`M=`) no cambian. Opciones: `PT` primer día del trimestre siguiente, `PM` próximo miércoles,
    `PL` próximo lunes y `DP<lista>` primer día de pago de la lista (`DP5,20`, `DP12-`, `DP-3`) a partir de esa fecha.
    Devuelve `None` si la regla no tiene al menos los tres bloques D, M y A.

    Dos supuestos no verificados con los datos (el original llama a una función `ConDateReal`): un día que no existe se
    recorta al último del mes, y `D-n` resta días (MGD lee el número sin signo).
    """
    bloques = modelo.split()
    if len(bloques) < 3:
        return None
    a, m, d = fecha.year, fecha.month, fecha.day

    if len(bloques) > 3 and bloques[3] == "PT":
        m = ((m - 1) // 3 + 1) * 3 + 1
        if m > 12:
            m, a = 1, a + 1
        d = 1

    def _num(b: str) -> int:
        return int(b[2:])

    if len(bloques[2]) > 2:
        a = _num(bloques[2]) if bloques[2][1] == "=" else a + (_num(bloques[2]) if bloques[2][1] != "-" else -_num(bloques[2]))
    if len(bloques[1]) > 2:
        if bloques[1][1] == "=":
            m = _num(bloques[1])
        else:
            m += _num(bloques[1]) if bloques[1][1] != "-" else -_num(bloques[1])
            a += (m - 1) // 12
            m = (m - 1) % 12 + 1
    if len(bloques[0]) > 2:
        if bloques[0][1] == "=":
            dia_base, d = d, _num(bloques[0])
            if _fecha_real(a, m, d) < _fecha_real(a, m, dia_base):  # el día ya ha pasado este mes → el mes siguiente
                f = _fecha_real(a, m + 1, d)
                a, m = f.year, f.month
        else:
            n = _num(bloques[0]) * (-1 if bloques[0][1] == "-" else 1)
            f = _fecha_real(a, m, d) + timedelta(days=n)
            a, m, d = f.year, f.month, f.day
    f = _fecha_real(a, m, d)

    opciones = bloques[3:]
    if opciones and opciones[0] == "PM":
        while f.weekday() != 2:
            f += timedelta(days=1)
    elif opciones and opciones[0] == "PL":
        while f.weekday() != 0:
            f += timedelta(days=1)
    for b in opciones:
        if b.startswith("DP") and len(b) > 2:
            lista = _dias_de_pago(b[2:])
            for j in range(31):
                if _esta_en(lista, (f + timedelta(days=j)).day):
                    f += timedelta(days=j)
                    break
    return f


# ------------------------------------------------------------------------------------------------ plantillas


@dataclass
class LineaPlantilla:
    cuenta: str
    ayuda: str
    dhc: str  # "D", "H" o "C"
    importe: Decimal
    vencimientos: list[str]


@dataclass
class LineaExtra:
    """Línea de un asiento manual ya calculada: el importe es siempre positivo y `dh` dice el lado."""

    cuenta: str
    dh: str
    importe: Decimal
    ayuda: str = ""
    vencimientos: tuple[str, ...] = ()


def _importe_mgd(texto: str) -> Decimal:
    t = texto.strip().replace(".", "").replace(",", ".")
    return dinero(t) if t else Decimal("0.00")


def leer_contenido(contenido: str | None) -> list[LineaPlantilla]:
    """Lee el memo de una plantilla de MGD (`Explant.CONTENIDO`)."""
    lineas = []
    for texto in (contenido or "").replace("\r", "").split("\n"):
        if not texto.strip():
            continue
        campos = texto.split("|")
        campos += [""] * (5 - len(campos))
        dhc = campos[2].strip().upper()
        if dhc not in ("D", "H", "C"):
            raise ErrorContable(f"Línea de plantilla con tipo «{campos[2].strip()}» (debe ser D, H o C): {texto.strip()[:60]}")
        lineas.append(
            LineaPlantilla(
                cuenta=campos[0].strip(),
                ayuda=campos[1].strip(),
                dhc=dhc,
                importe=_importe_mgd(campos[3]),
                vencimientos=[v.strip() for v in campos[4].split(",") if v.strip()],
            )
        )
    return lineas


def validar_plantilla(lineas: list[LineaPlantilla]) -> None:
    if not lineas:
        raise ErrorContable("La plantilla no tiene líneas")
    cuadres = sum(1 for l in lineas if l.dhc == "C")
    if cuadres > 1:
        raise ErrorContable(f"Hay {cuadres} apuntes de cuadre; no tiene sentido que haya más de uno")


def aplicar_plantilla(lineas: list[LineaPlantilla], importes: list[Decimal]) -> list[LineaExtra]:
    """Convierte una plantilla y los importes tecleados (uno por línea; el de la línea de cuadre se ignora) en las líneas del asiento.

    Las líneas con importe 0 se omiten; un importe negativo cambia de lado (`vNuevoExtra`). La línea de cuadre se calcula.
    """
    validar_plantilla(lineas)
    if len(importes) != len(lineas):
        raise ErrorContable(f"La plantilla tiene {len(lineas)} líneas y se han dado {len(importes)} importes")
    debe = haber = Decimal("0.00")
    calculadas: list[list] = []  # [línea, dh, importe]
    cuadre = None
    for linea, importe in zip(lineas, importes):
        if linea.dhc == "C":
            cuadre = [linea, "H", Decimal("0.00")]
            calculadas.append(cuadre)
            continue
        importe = dinero(importe)
        debe, haber = (debe + importe, haber) if linea.dhc == "D" else (debe, haber + importe)
        calculadas.append([linea, linea.dhc, importe])
    if cuadre is not None:
        diferencia = debe - haber
        cuadre[1], cuadre[2] = ("H", diferencia) if diferencia >= 0 else ("D", -diferencia)

    resultado = []
    for linea, dh, importe in calculadas:
        if importe == 0:
            continue
        if importe < 0:
            importe, dh = -importe, "H" if dh == "D" else "D"
        resultado.append(LineaExtra(linea.cuenta, dh, importe, linea.ayuda, tuple(linea.vencimientos)))
    return resultado
