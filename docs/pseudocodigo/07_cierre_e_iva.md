# 07 · Liquidación del IVA y cierre del ejercicio

Origen (Visual Objects, `F_Contabilidad.prg`): `ResumenIVA.GeneraAsientoIVA` (1788), `RegulIngresosGastos` (1), `CierreContable`
(19401…21200: `AcumulaDatosDiario`, `AsientoCierre`, `AsientoAperturaMisma`, `AsientoAperturaOtra`, `AANNuevo`, `AANRehacer`,
`ControlIngresosGastosCero`). Código: `servicios/iva.py` y `servicios/cierre.py`. Tests: `tests/test_iva.py`, `tests/test_cierre.py`.

## 1. Liquidación del IVA (asiento de regularización, tipo 9 subtipo `P`)

Para un periodo [desde, hasta] (trimestral por defecto; bimestral o mensual configurables):
1. Saldo (debe − haber) de las cuentas de IVA **472** (soportado) y **477** (repercutido) con los movimientos **del periodo**, sin
   contar las liquidaciones (`P`). Es el saldo del periodo, no el acumulado.
2. El asiento cancela cada cuenta con saldo: lo soportado (deudor) al haber, lo repercutido (acreedor) al debe.
3. Diferencia: si el soportado supera al repercutido → **debe** de Hacienda deudora (`IVA_DEBE`, 4700…) «a compensar o devolver». Si no →
   **haber** de Hacienda acreedora (`IVA_HABER`, 4750…) «a pagar», con un **vencimiento** (negativo) en el día de pago.
4. Si hay saldo a favor de periodos anteriores en la cuenta deudora, se **compensa** contra el IVA a pagar (opcional): parte del
   pago pasa a un haber de la cuenta deudora, y el vencimiento es solo por lo que queda.
5. Texto: `REGUL. IVA 2 TRIM/2021`. Fecha del asiento = último día del periodo. Idempotente: se sustituye.

**Día de pago**: el día `DiasIVA[i]` del primer mes tras el periodo; por defecto 25 (MGD rellena todos con 25; el 4.º trimestre de
la AEAT vence el 30 de enero, así que conviene configurarlo: `IVA_DIAS_PAGO = 20,20,20,30`).

**Verificado con MGD 2021**: reproduce al céntimo, incluidos los vencimientos, las liquidaciones hechas con el periodo completo
(Empresa A 1T; Empresa B 2T y 3T). Las otras dos salen **distintas** porque se contabilizaron facturas del periodo después de liquidar:

| Liquidación | Diferencia con el saldo actual del periodo |
|---|---|
| Empresa A 2T | 18,87 € de IVA soportado en `47210701` sin declarar (MGD 4721701) |
| Empresa B 1T | 337,90 € de IVA soportado sin declarar (`47202101`: 334,76 · `47201001`: 2,62 · `47200402`: 0,52) |

Esas cuotas **nunca se liquidan** después (la liquidación del trimestre siguiente solo cuenta sus propios movimientos). Merece
revisarse con tu asesor si se incluyeron en un modelo 303 posterior o quedaron sin deducir. La auditoría las marca
(`liquidacion_iva_desactualizada`).

Notas: el catálogo `Tipoiva` (21 y 14 tipos) nombra algunas cuentas que no son de liquidación (p. ej. la 4751 de retenciones) y
otra (`4770002` de Empresa A) que nunca se creó; la regla de «472 y 477» es la que reproduce las liquidaciones reales.

## 2. Regularización de ingresos y gastos (subtipo `R`)

Suma, por cuenta, los movimientos de los grupos de gastos (`G_GASTOS`, 6) e ingresos (`G_INGRESOS`, 7) hasta la fecha de cierre, sin contar
regularizaciones ni cierres anteriores. El asiento salda cada cuenta y lleva el resultado a Pérdidas y Ganancias (`PYG`, 12900000):
pérdida al debe, beneficio al haber. Texto «REGUL. DE INGRESOS Y GASTOS». Idempotente.

## 3. Asiento de cierre (subtipo `Z`)

Antes de cerrar: el Diario debe cuadrar y las cuentas de ingresos y gastos deben estar a cero (si no, «probablemente está pendiente la
regularización»). El asiento salda **todas** las cuentas con saldo (sin contar un cierre anterior). Texto «ASIENTO DE CIERRE».

## 4. Apertura del ejercicio siguiente (subtipo `A`, nº 1)

- Fecha = día siguiente al cierre. El ejercicio nuevo se crea si no existe.
- Cada cuenta se abre con el saldo **previo al cierre** (incluida la regularización: P y G queda con el resultado del año).
- **Vencimientos pendientes** (pendiente ≠ 0): cada uno va en una línea de su cuenta efectiva con su texto (`R 48 PROVEEDOR`), su fecha y su
  importe pendiente; la línea base de la cuenta baja en ese importe. Si la cuenta no tiene saldo, se compensa con una línea
  «COMPENSACION …». Si tras agrupar la cuenta queda a cero, sus vencimientos no se pueden colgar de ningún apunte: se **avisa** y no se arrastran.
- En el Diario las líneas de una misma cuenta se agrupan; de ahí que el signo de un vencimiento no se deduzca del apunte.
- Saldo inicial de un banco = lo que la apertura pone en su cuenta (se comprueba por ejercicio en la auditoría).

## 5. Cierre completo

`cerrar_ejercicio`: auditoría **sin errores** → regulariza si hace falta → asiento de cierre → abre el siguiente → marca el ejercicio
cerrado (ya no admite movimientos). `reabrir_ejercicio` lo deshace del todo —asiento de cierre, **regularización** y apertura— si el ejercicio siguiente solo tiene la apertura;
al volver a cerrar se regulariza de nuevo (la regularización es idempotente y se rehace siempre que haya ingresos o gastos sin regularizar).

Con los datos de 2021: Empresa A se cierra y se abre 2022 sin problemas; **Empresa B no se puede cerrar** hasta corregir los 6 asientos
fechados en 2020 (la auditoría los marca como error). Todo el proceso se probó también sobre ambas empresas saltándose la
auditoría: las cuentas quedan a cero, la apertura reproduce los saldos, se arrastran los vencimientos y no hay errores en 2022.

## 6. Qué NO está validado contra MGD

Las datos de 2021 no contienen asientos `R`, `Z` ni la apertura generada por el programa (la apertura de 2021 se hizo en el ejercicio
anterior y es un dato de entrada). Estas reglas se verificaron por **invariantes** (las cuentas quedan a cero, la apertura reproduce
los saldos, todo cuadra) y siguiendo el código, no comparando con la salida real de MGD. **Para validarlas al céntimo hace falta una
copia de MGD de un año anterior (p. ej. 2020) y comparar su cierre con el asiento de apertura de 2021 que ya tenemos.**

## 7. Pendiente

Cambio de plan contable en el cierre (`CambioPGCNueva/Otra`), conversión a euros, inventario de existencias de facturación
(`GuardaInventario`, fuera de alcance), amortización fiscal, y la presentación del modelo 303 (Hito 3).
