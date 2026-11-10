# 01 · Asientos y Diario (pseudocódigo)

Origen: `E_Edicion.prg` (clases `Asientos`, `RegeneraAsientos`, `EdicionAsientos`, `ListaPagos`),
`D_Comun.prg` (`BaseApuntesER`), `F_Contabilidad.prg` (`RegulIngresosGastos`, `DiarioDescuadrado`,
`OrdenarAsientos`). Las referencias `fichero:línea` son del código VO original.

Estado de verificación: reglas contrastadas con `BBDD 2021` (ver §9). Lo no leído se lista en §10.

---

## 1. Idea central

El **Diario no se teclea**: es una tabla *derivada*. Cada documento de origen (factura emitida,
factura recibida, movimiento de banco, asiento "extra"/manual) genera su asiento en el Diario, y
`RegeneraAsientos` puede borrar y rehacer todos los asientos desde los documentos. Consecuencias
para el diseño nuevo:

- El documento de origen es la fuente de verdad; el Diario se puede reconstruir.
- Cada línea del Diario guarda su origen: `(TIPO, NUMERO, MULTI)`.
- Grabar un asiento es una operación **idempotente**: "deja el asiento de este documento así".

| TIPO | Origen | Tabla origen | TPASIENTO observado |
|---|---|---|---|
| `E` | Factura emitida | `Emi` | `M` |
| `R` | Factura recibida | `Rec` | `M` |
| `B` | Movimiento de banco / cobro-pago / remesa / compensación | `Movbanco` + `Pagos` | `M` |
| `X` | Extra (manual, apertura, regularización, cierre…) | `Extra` + `Exapun` | el `TIPO` del extra: `A` apertura, `R` regularización de ingresos/gastos, `Z` cierre, `P` regularización de IVA (F_Contabilidad:1857; verificado con los datos 2021). `M` asiento normal/de plantilla (F_Contabilidad:20976) y `Q` amortización de bienes de inversión (E_Edicion:27064), ver doc 03 |

## 2. Convenciones de datos

- `IMPORTE` con signo: **positivo = Debe, negativo = Haber**. La suma del Diario es 0 (verificado 2021).
- Cada asiento tiene una **línea cabecera**: `CUENTA` vacía e `IMPORTE` 0. Va primero. Aporta el
  texto del asiento (`DiarioTexto`) y es el marcador de cambio de asiento (lo usa `DiarioDescuadrado`).
- Dentro de un asiento: primero todas las líneas con importe ≥ 0 (Debe), luego las negativas (Haber).
  Verificado en 103/103 asientos de 2021.
- `ASIENTO`: número correlativo **por periodo contable** (no por año natural).
- `MULTI`: `" "` para el asiento principal; `"1"`, `"2"`… para asientos adicionales de una misma factura.
- `CLAVE`: 3 caracteres que solo se rellenan al reordenar asientos de un día (vacío en todo 2021).
- `CLAVE_ORI`: número de la factura (`NumeroC4(cnumero)`) o `tipo+clave` del extra.
- `DiarioTxt` (`TIPO, NUMERO, CUENTA, MULTI`): texto, documento y notas **por cuenta** del asiento.
- Cuentas: `xCuenta()` normaliza a longitud fija (`gnCuenta`, 7 en estos datos).
- Decimales: `gParam:Decimales`; con 0, base/IVA/RE se truncan a entero al leer el IVA de una factura.

## 3. `ReduceApuntes(apuntes, tipo)` — consolidar líneas  (E_Edicion:5591)

```
entrada: lista de (cuenta, importe)
reduce = True
si param.noReduceApuntes:
    reduce = True  si tipo en {E,R}
             (n_apuntes < 3) si tipo == B
             False si tipo == X
salida = []
para i en 1..n-1:
    cuenta_i = xCuenta(cuenta_i)
    si importe_i ≠ 0:
        si reduce: para j en i+1..n: si misma cuenta → importe_i += importe_j ; importe_j = 0
        si importe_i ≠ 0: salida.añadir(cuenta_i, importe_i)
última línea: si importe ≠ 0: salida.añadir
```
Resultado: líneas con la misma cuenta se suman; las de importe 0 desaparecen.

## 4. `Graba(...)` — grabar un asiento  (E_Edicion:4295)

```
Graba(tipo, numero, fecha, tpasiento, clave_ori, apuntes, textos, lineas_previas, multi=" "):
    actual = ReduceApuntes(apuntes, tipo)
    si actual no vacío:
        insertar cabecera al principio: (cuenta="", importe=0)
        # número de asiento
        si tipo=="X" y tpasiento=="A": n_asiento = 1          # apertura siempre es el 1
        si no:                         n_asiento = NumeroAsiento(fecha)
        si alguna línea previa tiene ASIENTO>0: n_asiento = esa     # se conserva el número al regenerar
        # escritura: Debe primero, Haber después
        para pasada en (Debe: importe ≥ -0.001 ; Haber: importe < -0.001):   # ver nota
            para cada línea de la pasada:
                reutilizar el registro previo nº k si existe, si no, nuevo
                grabar ASIENTO, FECHA, TPASIENTO, CLAVE_ORI, TIPO, NUMERO, IMPORTE, CUENTA, MULTI
                si hay texto para esa cuenta (DiarioTxt): grabarlo (tipo, fecha, numero, cuenta, texto, docu, notas, multi, negativo)
    borrar las líneas previas no reutilizadas
    borrar los textos previos no reutilizados
```
Nota sobre las pasadas: la condición del código es `Debe: saltar si importe < -0.001` y
`Haber: saltar si importe > -0.001`. El importe 0 cae en Debe; por eso la cabecera (0) sale primera.

Detalle de diseño: el VO reutiliza registros para no fragmentar el DBF. En un modelo relacional basta
con *borrar y reinsertar en una transacción conservando el `ASIENTO` previo*.

## 5. `NumeroAsiento(fecha)`  (E_Edicion:6174)

```
periodo_f = param.NumPeriodoContable(fecha)
si periodo_f == 0: param.GrabarPeriodosContables(); recalcular; si sigue 0 → devolver 1
recorrer el Diario hacia atrás (índice ASIENTO por año), empezando por el último del año de la fecha
    (si no hay del año, desde el último registro del diario)
primer registro cuyo periodo contable == periodo_f → devolver su ASIENTO + 1
si ninguno → 1
```
Equivalente SQL: `max(asiento)+1` entre las líneas cuyo `fecha` cae en el mismo periodo contable.
Atención: asignar número a un asiento **intermedio en fecha** no renumera; el número es de orden de
creación, por eso existe `OrdenarAsientos` / `RenumerarHastaFinal`.

## 6. Generadores de asientos por origen (`RegeneraAsientos`)

### 6.1 Factura recibida `R`  (E_Edicion:3832)  — **verificado 56/56 (Empresa A) y 190/190 (Empresa B)**
Implementado en `domain/facturas.py` (`asientos_de_factura`), también para emitidas: 1/1 y 21/21.
```
aIva = LeeIvaFactura("R", num)            # filas de Eriva con TIPO="S" (soportado)
neto = total - Σ (IVA_TOTAL + RE_TOTAL) de las filas con NODEDU ≠ "S"
apuntes = [ (toCuenta,  neto),            # gasto/compra
            (prCuenta, -total) ]          # proveedor
para cada fila IVA con NODEDU ≠ "S":
    si IVA_TOTAL ≠ 0: añadir (IVA_CTA,  IVA_TOTAL)
    si RE_TOTAL  ≠ 0: añadir (RE_CTA,   RE_TOTAL)
# El IVA no deducible NO tiene línea: queda dentro del gasto (neto = total - solo IVA deducible)
ajustes = BaseApuntesER("R").Lee(num)
si hay ajustes: ajustes.Contabilidad(apuntes, 1)       # ver §7
Graba("R", num, fecha, "M", NumeroC4(cnumero), apuntes, ..., multi=" ")
para i en 2..ajustes.NumAsientos:                       # asientos adicionales
    apuntes = [(toCuenta,0),(prCuenta,0)] ; ajustes.Contabilidad(apuntes, i)
    Graba(..., multi=str(i-1))
```

### 6.2 Factura emitida `E`  (E_Edicion:4470)
Misma estructura, signos invertidos:
```
neto = total - Σ (IVA_TOTAL + RE_TOTAL) de filas NODEDU ≠ "S"       # Eriva TIPO="R" (repercutido)
apuntes = [ (clCuenta, total), (toCuenta, -neto) ] + por fila IVA: (IVA_CTA, -IVA_TOTAL), (RE_CTA, -RE_TOTAL)
```
Si `Emi.cliente < 0`, es una **autofactura**: el "cliente" es en realidad el proveedor `-cliente`
(`DiarioTexto`, E_Edicion:4016). Solo hay 4 asientos E en los datos de 2021 → **sin cobertura de prueba**.

### 6.3 Movimiento de banco `B`  (E_Edicion:3910 + `ListaPagos.Asiento` 11704)
```
bancos = [ compensación(-1), remesas(BANCO_REMESAS), + cada banco con NUMERO>0 ]
clave de banco en Movbanco = str(banco + 100, 3)
UnMovBanco:
    pagos = ListaPagos(banco, mov.numero)
    si banco == REMESAS: si no hay pagos → salir ; cuenta = cuenta de destino (DIRSUBCTA) del 1.er pago
    si no: cuenta = Bancos.cuenta
    apuntes = pagos.Asiento(cuenta):
        total = Σ pagos
        si total ≠ 0: [(cuenta_banco, total)]
        por cada pago:
            cuenta = (si tiene vencimiento) cuenta del vencimiento (Vtos_Descripcion→CPERX_CUENTA)
                     si no, si DIRSUBCTA vacío → param.pteAplic (cuenta "pendiente de aplicar")
                     si no, DIRSUBCTA
            añadir (xCuenta(cuenta), -importe)
    Graba("B", mov.numero, mov.fecha, "M", mov.clave, ...)
```
Los cobros/pagos de vencimientos (`Vtos`/`Pagos`) contabilizan contra la cuenta del vencimiento.
Compensaciones (banco −1) y remesas son variantes del mismo mecanismo.

### 6.4 Extra `X`  (E_Edicion:4440)
```
apuntes = [ (Exapun.cuenta, +importe si DH="D" ; -importe si DH="H") para cada Exapun del extra ]
Graba("X", extra.numero, extra.fecha, extra.tipo, extra.tipo + extra.clave, apuntes)
```
`ReduceApuntes` no reduce en tipo `X` si `noReduceApuntes` está activo (los asientos manuales se
respetan tal como se teclearon).

## 7. Ajustes de factura (`BaseApuntesER`, D_Comun:12584)

Tabla `Ajustes` (`TIPO, NUMERO, CUENTA, IMPORTE, CONTRA, CAMBIOAS, AFECTAIVA, DECLTERC`): líneas extra
sobre una factura (IRPF, retenciones, suplidos…).

- `CONTRA` indica contra qué línea fija se compensa: en `E`, `C`=cliente (pos. 1), `I`=ingreso (pos. 2);
  en `R`, `G`=gasto (1), `P`=proveedor (2).
- `CAMBIOAS = "S"` → esta línea y las siguientes pasan a un **asiento nuevo** (otro `MULTI`).
- `Contabilidad(apuntes, n)`: recorre los ajustes; en el asiento `n` añade `(cuenta, importe)` y
  resta `importe` de la línea fija indicada en `CONTRA`:
  `apuntes[pos(CONTRA)].importe -= importe`.
- `AFECTAIVA`: el ajuste suma a la base del IVA. `DECLTERC`: suma para la declaración de terceros (347).
- IRPF: `IRPF()` deduce el % a partir de importe/base (redondeos a 0/1 decimales, busca la cuenta o
  cualquier cuenta cuyo texto contenga "IRPF"). Para `R` el % se toma en valor absoluto.

Verificado: factura recibida nº 23: 616,25 de gasto + ajuste IRPF −108,75 (`4751000`, `CONTRA=G`)
→ gasto 725,00 y 4751000 a −108,75. Coincide con el Diario.

## 8. Otros procesos del Diario (F_Contabilidad)

### 8.1 `DiarioDescuadrado`  (F_Contabilidad:245)
```
saldo = 0
para cada línea del Diario en orden de fecha:
    si es cabecera (cuenta vacía): si saldo ≠ 0 → avisar del asiento anterior ("Texto del asiento", fecha…)
    saldo += importe
```
Límite del original: el **último asiento no se comprueba** (no hay cabecera siguiente) y el saldo es
acumulado, no por asiento. En el sistema nuevo: `GROUP BY asiento HAVING sum(importe) ≠ 0`.

### 8.2 `OrdenarAsientos`  (F_Contabilidad:160)
Reordena los asientos de un día: el usuario fija el orden de las cabeceras; a cada asiento se le asigna
`CLAVE` = 3 caracteres incrementales (`C3Mas`) y, si el primero tenía número, se renumeran `ASIENTO`
correlativos a partir de él.

### 8.3 `RegulIngresosGastos(fecha_cierre)`  (F_Contabilidad:1)
```
pyg = param.PyG (cuenta de Pérdidas y Ganancias; error si no existe)
desde = inicio del periodo contable de fecha_cierre
cuentas_IG = cuentas de los grupos param.GGastos + param.GIngresos
para cada línea del Diario en [desde, fecha_cierre]:
    si cuenta ∈ cuentas_IG y tpasiento ∉ {Z (cierre), R (regularización)}:   # idempotente
        saldo[cuenta] += importe ; total += importe
saldo[pyg] = -total
borrar la regularización anterior de esa fecha (pregunta al usuario)
crear Extra (tipo "R", texto "REGUL. DE INGRESOS Y GASTOS") con Exapun:
    saldo < 0 → línea D por |saldo| ; saldo > 0 → línea H por saldo
RegeneraAsientos.UnExtra()    # lo contabiliza en el Diario
```
Es decir: salda cada cuenta de gasto/ingreso contra la 129/PyG y deja PyG con el resultado.

## 9. Validación contra `BBDD 2021`  (`tools/validar_recibidas.py`)

| Comprobación | Resultado |
|---|---|
| Σ importes del Diario | 0,00 |
| Asientos / líneas | 103 asientos (num. máx. 106), 391 líneas, 103 cabeceras |
| Orden Debe→Haber dentro del asiento | 103/103 |
| Facturas recibidas regeneradas desde `Rec`+`Eriva`+`Ajustes` idénticas al Diario | **56/56** |
| Sin aplicar `Ajustes` | 55/56 (la nº 23 lleva un ajuste de IRPF, §7) |
| `CLAVE` | vacía en todas |
| Tipos | R/M 218 líneas, B/M 129, X/A 32, X/P 8, E/M 4 |

El hueco de numeración (103 asientos, máx. 106) indica asientos borrados que dejan huecos: el número
no se recompacta salvo con `RenumerarHastaFinal`.

## 10. Pendiente de leer / dudas abiertas

No leído todavía (necesario para cerrar el núcleo contable):
1. `RegeneraAsientos.TodosSC` (E_Edicion:5529) — orquestación de la regeneración completa y qué se borra antes.
2. `CierreContable` (F_Contabilidad:19401) — asiento de cierre, apertura del ejercicio siguiente, cambio de PGC.
3. `vDiario`/`EdicionDiario` — edición manual, `BorraAsientos`, `RenumerarHastaFinal`.
4. `Vtos_Descripcion` y vencimientos (`Vtos`, `Rec`) — de dónde sale la cuenta de cada pago.
5. `ResumenIVA.GeneraAsientoIVA` (F_Contabilidad:1788) — asiento de liquidación del IVA (entra en el flujo 303).
6. `PlContabiliza`/`AmortUno` — asientos de amortización (`Lbi`).

Dudas para ti (las pantallas lo resuelven en minutos):
- ~~`TPASIENTO` `P`~~ → resuelto: regularización de IVA (cuenta 4700000 contra 4721xxx). `M` = asiento normal/de plantilla y `Q` = amortización (resuelto, ver doc 03).
- ~~`param.noReduceApuntes`~~ → resuelto: `NO_REDUCE_APUNTES = 'N'` en `Param.dbf`; se agrupan las líneas de la misma cuenta.
- ¿Había facturas emitidas con autofactura o con IVA no deducible (`NODEDU="S"`)? Solo hay 4 emitidas en 2021, no se puede probar con estos datos.

## 11. Implicaciones para el diseño en Python

- Núcleo puro y testeable: `reduce_apuntes`, `asiento_factura_recibida`, `asiento_factura_emitida`,
  `asiento_banco`, `asiento_extra`, `aplicar_ajustes`, `numero_asiento`, `regularizar`, `descuadres`.
  Entrada y salida son listas de `(cuenta, importe)`; nada de I/O.
- `grabar_asiento(tipo, numero, multi, …)` idempotente y transaccional; mantener el `asiento` previo.
- Restricción en BD: `sum(importe) = 0` por asiento (el original solo lo revisa a posteriori).
- Mantener `(tipo, numero, multi)` como clave de origen para poder regenerar y para la trazabilidad
  que exige la auditoría.
- Tests de regresión: el corpus 2021 (más otros años si existen) como "golden files".
