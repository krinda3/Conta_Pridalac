# 02 · Tesorería: bancos, vencimientos, cobros y pagos (pseudocódigo)

Origen (Visual Objects, `E_Edicion.prg`): `UnVto` (12960), `clVtos` (14784…15750), `ListaPagos` (11524),
`Vtos_Descripcion` (13777), `Vtos_Recalcula` (15630), `RecalculaSaldoBanco` (12761), `CPERX` (2798),
`RegeneraAsientos.UnMovBanco` (3910, ver doc 01 §6.3). Tablas: `Bancos`, `Movbanco`, `Pagos`, `Vtos`, `Tipovtos`.

Verificado con `BBDD 2021` (Empresa A) con `tools/validar_tesoreria.py`:

| Regla | Resultado |
|---|---|
| `Vtos.PENDIENTE = IMPORTE − Σ Pagos` | 59/59 |
| `Movbanco.TOTAL = Σ Pagos.IMPORTE` | 43/43 |
| `Movbanco.SALDONUE` = saldo corrido del banco | 43/43 |
| Asiento regenerado del movimiento = líneas `B` del Diario | **43/43** |

## 1. Modelo conceptual

```
documento (factura E/R, apunte de extra X, remesa B)
   └─ 1..n VENCIMIENTO (fecha, importe, cuenta de devengo, forma de pago, banco previsto)
         └─ 0..n PAGO (importe) ──┐
                                  ├─► MOVIMIENTO DE BANCO (banco, fecha, texto) ─► ASIENTO tipo 3 (tesorería)
   PAGO directo a subcuenta ──────┘
   PAGO pendiente de aplicar (sin vencimiento ni cuenta) → cuenta PTE_APLIC
```

- Un **vencimiento** nace al grabar un documento. Una factura puede tener varios; se pueden **dividir** en N plazos
  (importe/N, el primero absorbe el redondeo; las fechas se generan con una regla "D=M=A=" de separación).
- Un **movimiento de banco** agrupa uno o varios **pagos**; cada pago puede saldar (parcialmente) un vencimiento o ir
  directo a una subcuenta o quedar "pendiente de aplicar".
- El **asiento** del movimiento es derivado (se regenera, doc 01 §6.3). Cualquier cambio de pagos o de la cuenta de
  devengo del vencimiento obliga a regenerar los asientos de los movimientos afectados (`UnVto.GrabaContaBanco`).
- Signos: importe de vencimiento **positivo = a cobrar** (emitidas), **negativo = a pagar** (recibidas, p. ej. −108,75 de
  la retención IRPF de la factura 23). Un pago al banco con importe negativo es una salida; `Movbanco.TOTAL` = Σ pagos.

## 2. Tipos de vencimiento y su cuenta efectiva

`Vtos.TIPO` = origen: `E` emitida, `R` recibida, `X` apunte de un extra (`TPNUMERO` = `Exapun.NUMERO`), `B` remesa
(`TPNUMERO` = `Movbanco.NUMERO`). `Vtos.CUENTA` es la **cuenta de devengo** y puede ir vacía ("la normal"):

```
cuenta_efectiva(vto):
    si vto.cuenta no vacía      → vto.cuenta
    si vto.tipo == "B"          → vto.cuentadef            # remesa: cuenta por defecto guardada en el vencimiento
    si vto.tipo == "R"          → Rec.PRCUENTA  (cuenta del proveedor)
    si vto.tipo == "E"          → Emi.CLCUENTA  (cuenta del cliente)
    si vto.tipo == "X"          → Exapun.CUENTA (cuenta de ese apunte)
```
`Vtos.CUENTADEF` guarda la cuenta "normal" del documento al grabar el vencimiento (está rellena en los 59 de 2021);
`Vtos.CUENTA` solo se rellena cuando el usuario elige **otra diferente** (1 caso en 2021: la retención de IRPF de la
factura 23, que se devenga en una cuenta distinta a la del proveedor).
`PENTIDAD` = banco previsto; `PTIPO` = forma de cobro/pago (`Tipovtos`: 1 Giro, 2 Efecto, con indicador de por defecto
para clientes/proveedores). En 2021: 57 de 59 vencimientos son con efecto.

## 3. Pendiente de un vencimiento

```
pendiente(v) = v.importe − Σ pago.importe  para los pagos con pago.vto = v.numero         # Vtos_Recalcula
pendiente del documento = Σ pendientes de todos sus vencimientos (Vtos_Pendiente)
pagado del documento    = Σ (importe − pendiente)                                           # Vtos_Pagos tipoResp=1
```
Se recalcula cada vez que se graban los pagos de un movimiento (`ListaPagos.Graba` → `Vtos_RecalculaPendiente` de todos
los vencimientos tocados, incluidos los que dejaron de estar en el movimiento). En el sistema nuevo: **no se almacena**,
se calcula (o se mantiene por trigger) para que no pueda desincronizarse.

## 4. Pagos inmediatos al grabar un vencimiento (`UnVto.Graba`)

```
grabar(vto):
    si borrado → GrabaBorra: quita la referencia de sus pagos (pago.vto = 0), regenera el asiento de cada
                 movimiento afectado (esos pagos pasan a "pendiente de aplicar") y borra el vencimiento
    alta/modificación: guarda fecha, importe, pentidad(banco), cuenta, cuentadef, ptipo,
                       pendiente = importe − pagos ya hechos
    si ya existía y cambió la cuenta de devengo (o se pide rehacer): regenerar los asientos de sus pagos
    si queda pendiente ≠ 0 y tiene fecha:
        si "pago directo" (siPagoDirecto) → PIDirecto
        si no, si tiene cuenta de compensación → PICompensacion
```

**Pago inmediato directo** (`PIDirecto`): crea un movimiento en el banco del vencimiento, con fecha del vencimiento y
clave `ZZZ` (queda el último del día), importe = el pendiente, un pago ligado al vencimiento, texto automático,
numeración propia del banco si está activada, regenera el asiento (`UnMovBanco`), recalcula el saldo del banco desde ese
movimiento y deja el vencimiento a pendiente 0.

**Pago por compensación** (`PICompensacion`): crea un movimiento en el banco especial **−1 "Compensación de
vencimientos"** con **dos pagos**: `+pendiente` ligado al vencimiento y `−pendiente` a la subcuenta de compensación
(`DIRSUBCTA`). El total del movimiento es 0 (no pasa por tesorería real); su asiento salda la cuenta del vencimiento
contra la de compensación. Requiere que exista el banco −1 (`CompruebaBancoCompVtos`; en 2021 su cuenta es `5550000`).

## 5. Movimiento de banco y su asiento

Banco especial `−1` = compensación; `−3` = remesas (`BANCO_REMESAS`, el asiento va contra la cuenta de destino del primer
pago, no contra la de un banco). El resto de bancos tienen `Bancos.CUENTA` (cuenta 572…/551…).

```
asiento_movimiento(mov):                                                   # ListaPagos.Asiento + UnMovBanco
    cuenta_banco = (si banco == remesas: DIRSUBCTA del 1.º pago) o Bancos.cuenta
    total = Σ pagos
    apuntes = []
    si total ≠ 0: apuntes += (cuenta_banco, +total)
    para cada pago:
        cuenta = (si pago.vto>0)  cuenta_efectiva(vencimiento)
                 (si no, y pago.dirsubcta no vacía) dirsubcta
                 (si no)           param.PTE_APLIC                       # "5550000" en 2021
        apuntes += (cuenta, −pago.importe)
    Graba("B", mov.numero, mov.fecha, "M", mov.clave, apuntes, ...)       # doc 01 §4 (agrupa líneas de misma cuenta)
```
Los cobros son entradas (+) al banco y salidas del vencimiento (−) en la cuenta del cliente; los pagos al revés.

## 6. Saldo del banco

```
saldo(movimiento) = saldo del movimiento anterior del mismo banco + movimiento.total      # parte de 0
orden = (fecha, clave, número)        # clave de 3 caracteres, "ZZZ" para los automáticos
Bancos.SALDOACT = saldo del último movimiento = Σ totales de los movimientos
```
Verificado con 2021 (43/43): `Movbanco.SALDONUE` y `Bancos.SALDOACT` acumulan **solo los movimientos**, sin el saldo de
apertura. El saldo real del banco es `Bancos.SALDOINI + SALDOACT` y coincide con el saldo de su cuenta en el Diario
(banco 1: 6.371,57 − 3.264,48 = 3.107,09 ✓; bancos 2 y 3 también). `SALDOINI` es el apunte de apertura de esa cuenta.
→ **Invariante para la auditoría**: `saldo contable de la cuenta del banco = saldo inicial + Σ movimientos`.
Tras cambiar un movimiento se recalcula **desde ese movimiento** (`RSB_DESDE_EL_ACTUAL`) o todo el banco
(`RSB_DESDE_EL_PRINCIPIO`).

## 7. Otras reglas de pantalla y listados útiles

- **Previsión de tesorería**: vencimientos pendientes por fecha + saldo de cada banco tras cada movimiento.
- **Pendiente de aplicar**: cobro/pago de origen desconocido: pago sin vencimiento ni cuenta; contabiliza en `PTE_APLIC`.
- **Plantillas de cobros/pagos** (concepto + cuentas) para repetir asientos de banco.
- **Transferencias entre bancos** (`BANCOT`, `NUMEROT` en `Pagos`): son **dos movimientos espejo**, uno en cada banco, con un
  pago único cada uno, importes opuestos y `NUMEROT` apuntando al otro movimiento. Un lado lleva como cuenta directa
  (`DIRSUBCTA`) la cuenta del **otro** banco y genera el asiento (banco propio contra banco ajeno); el otro lleva la de su
  **propio** banco, las dos líneas se anulan y **no hay asiento**. Lo normal es que genere el asiento el lado de salida
  (44 de 47 parejas en Empresa B), pero 3 se registraron desde el banco que recibe. Verificado con Empresa B 2021 (94 pagos,
  47 parejas, 320/320 asientos); en Empresa A no hay ninguna.
  Invariantes para la auditoría: cada transferencia tiene su espejo, importes opuestos, bancos distintos y exactamente un lado
  con la cuenta ajena.
- **Bancos especiales duplicados**: la tabla `Bancos` de Empresa B repite la fila `−1 Compensación de vencimientos`. El cargador
  lo avisa y se queda con una; la clave `numero` es única por empresa en el sistema nuevo.
- **Comprobación de fecha contable** (`ControlFechaContable`): un pago inmediato exige que su fecha esté en periodo contable
  válido (se enlaza con la validación de fechas del Hito 1).
- **Advertencia de orden de fechas** en facturas (`MiraFechaER`): avisa si la fecha de una factura es menor que la de la
  anterior (por número) o mayor que la de la siguiente. A incorporar en las facturas del sistema nuevo.

## 7 bis. Vencimientos de una factura: regla verificada

Con las dos empresas de 2021 (268 facturas):
- **Σ vencimientos de la factura = total + retenciones** (el total que se paga al tercero más lo que se ingresa a Hacienda). Sin
  ajustes, Σ = total. En 267 de 268 el total coincide exactamente; la que no es la de la retención de IRPF, donde se añade un
  vencimiento aparte por la retención (importe del ajuste, **con su propia cuenta de devengo**: 4751…, `Vtos.CUENTA` rellena).
- Signo: a cobrar positivo (emitidas), a pagar negativo (recibidas).
- Una factura tiene casi siempre un vencimiento (267 de 268; una tiene dos). Cada vencimiento tiene 0 o 1 pago: no hay pagos
  parciales en estos datos.
- 9 vencimientos de Empresa B **no tienen fecha** (a determinar): la fecha es opcional.
- `CUENTADEF` se rellena siempre con la cuenta del tercero de la factura; `CUENTA` solo cuando el usuario elige otra.

## 7 ter. Servicios implementados (Hito 1)

`servicios/vencimientos.py`: `plazos_por_defecto`, `repartir_en_plazos` (dividir en N con el primero absorbiendo el redondeo),
`definir_vencimientos` (exige que sumen lo que pide la factura; no deja quitar uno con pagos).
`servicios/tesoreria.py`: `registrar_movimiento` (crea o reemplaza pagos y regenera su asiento), `pagar_vencimiento` (pago
inmediato directo), `compensar_vencimiento` (banco especial de compensación, dos pagos que suman 0), `transferir` (dos movimientos
espejo; solo la salida genera asiento), `eliminar_movimiento` (una transferencia se borra entera), `regenerar_asiento`.
Un pago de más no se impide —como en MGD— pero devuelve una **advertencia**, y la auditoría lo lista (`vencimiento_pagado_de_mas`).
Todo lo que lleva fecha se valida contra el ejercicio: un movimiento fechado fuera del ejercicio (los 3 de 2020 de Empresa B) no
se puede regenerar ni reemplazar; hay que corregirle la fecha antes.

## 8. Implicaciones para el sistema nuevo

- `pendiente` y `saldo` **derivados**, no almacenados.
- `cuenta efectiva` del vencimiento calculada con la regla del §2; guardar solo la cuenta explícita.
- Un pago a un vencimiento pagado dos veces o por más que el pendiente debe avisar (el original no lo impide: solo una
  advertencia opcional "editar un vencimiento ya pagado").
- Auditoría: movimientos cuyo asiento ≠ regenerado; vencimientos con pendiente ≠ importe − pagos; saldo de la cuenta de
  proveedor ≠ Σ vencimientos pendientes; banco con saldo contable ≠ saldo del último movimiento.
- Sin cobertura de pruebas en 2021 (Empresa A ni Empresa B): remesas (`−3`) y varios vencimientos por factura con pagos parciales.
  Sí cubiertos con Empresa B: transferencias entre bancos y vencimientos de apuntes de extras (18 con tipo `X`).
  Habrá que buscar el resto en los años 2014–2020 de MGD.
