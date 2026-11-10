# Asientos, inmovilizado y listados

## Qué se genera solo y qué se teclea

Casi todos los asientos **se crean solos**: los de las facturas, los de los movimientos de banco, los de la liquidación del IVA y los del cierre del ejercicio. No se editan a mano: se corrige su origen y el asiento se regenera. La auditoría vigila que un asiento generado no se haya tocado por otro camino ([Cierre y control](tema:cierre#auditoria-de-integridad)).

Se teclean a mano solo los que **no tienen factura ni banco**: nóminas, seguros, cuotas, amortizaciones puntuales, regularizaciones.

## Asientos manuales y plantillas

- [Asientos manuales](pantalla:asientos) lista los asientos tecleados o creados desde una plantilla. **Doble clic** para editar; el botón «Desde plantilla» crea uno nuevo a partir de un modelo.
- Un asiento **debe cuadrar** (suma del debe igual a la del haber) y sus cuentas deben ser subcuentas del plan; el programa no deja grabar otra cosa.
- [Plantillas de asientos](pantalla:plantillas) guarda los asientos que se repiten (nóminas, cuotas, seguros…). Cada línea lleva la cuenta, si va al **Debe**, al **Haber** o es la que **cuadra** (calcula la diferencia), y una explicación. Al usarla se completan los importes.
- Los asientos de **apertura** (con el saldo del ejercicio anterior) y de **cierre** los crea el programa al cerrar y abrir ejercicio.

## Plan de cuentas, proveedores y clientes

[Plan de cuentas](pantalla:cuentas) lista las subcuentas con sus sumas del ejercicio. Las subcuentas tienen los **dígitos que se eligieron al crear la empresa** (8 por defecto). Doble clic para editar el nombre o crear una nueva. [Proveedores](pantalla:proveedores) y [Clientes](pantalla:clientes) llevan la cuenta de cada uno ([Facturas](tema:facturas)).

## Inmovilizado

- [Bienes de inversión](pantalla:bienes): cada bien con su **cuadro de amortización**. Doble clic para ver y editar el bien, **amortizar sus periodos** o **darlo de baja**. «Amortizar el ejercicio» genera las amortizaciones que tocan.
- [Libro de bienes de inversión (IVA)](pantalla:bienes-iva): los bienes de **más de 3.005,06 €** con IVA soportado y su periodo de **regularización de deducciones** (5 años; 10 en terrenos y edificios). Sirve para la regularización de las deducciones del IVA.
- La auditoría compara la dotación de amortización del año con la del cuadro y avisa si no coinciden.

## Listados y estados contables

Hay dos clases, que no son lo mismo:

**Listados de gestión** (para trabajar):

| Listado | Para qué sirve |
|---|---|
| [Libro Diario](pantalla:diario) | Un renglón por apunte, por orden de fecha y número. Doble clic para ver el asiento |
| [Libro Mayor](pantalla:mayor) | Todos los movimientos de una cuenta (`57200001`) o de un grupo (`572`), con su saldo acumulado |
| [Balance de sumas y saldos](pantalla:balance) | Sumas y saldos por cuenta, agrupables a 1, 2 o 3 dígitos o por subcuenta |
| [Saldos acumulados](pantalla:saldos-acumulados) | Por cuenta, el saldo hasta el mes anterior, lo movido en el mes y el acumulado |
| [Balance de situación](pantalla:balance-situacion) y [Pérdidas y ganancias](pantalla:perdidas-ganancias) | Por cuenta, para ver cómo va el año. **No** son el modelo oficial |
| [Libros de IVA](pantalla:iva-recibidas) (recibidas y emitidas) | Una línea por tipo de IVA de cada factura: el 303 y el 390 se calculan con estas mismas facturas |

**Estados oficiales** (los de las cuentas anuales):

| Estado | Qué es |
|---|---|
| [Balance oficial](pantalla:balance-oficial) y [PyG oficial](pantalla:pyg-oficial) | Según el modelo de **PYMES** (o de entidades sin fines lucrativos), con las líneas del modelo y el ejercicio anterior. Las cuentas con saldo de signo contrario al de su línea se restan dentro de ella (como hacía el programa anterior) y se avisa |
| [Estado de cambios en el patrimonio neto](pantalla:estado-cambios-pn) | Del saldo final del año anterior al del actual, con una columna por componente. «Operaciones con socios» recoge capital, prima, acciones propias, aportaciones y dividendo a cuenta; «Otras variaciones» es lo que falta (normalmente, la aplicación del resultado del año anterior) |

Los estados oficiales **no incluyen la regularización ni el cierre**: salen igual antes y después de cerrar. Son los que se usan para el modelo 200 y el depósito de cuentas.

## Liquidación del IVA

[Liquidación del IVA](pantalla:liquidacion-iva) tiene un renglón por periodo: doble clic para ver el cálculo, **liquidarlo** (crea el asiento de regularización del IVA del periodo), volver a liquidarlo o **deshacer** la liquidación. La presentación del modelo es aparte: [Los modelos de la AEAT](tema:modelos).
