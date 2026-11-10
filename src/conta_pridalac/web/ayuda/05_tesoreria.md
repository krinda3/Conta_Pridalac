# Tesorería: bancos, extractos y vencimientos

Tesorería responde a tres preguntas: **qué ha pasado en el banco** (extractos), **qué falta por cobrar o pagar** (vencimientos) y **si todo cuadra** (cuadre con el Mayor).

## Bancos

[Bancos](pantalla:bancos) lista las cuentas bancarias y las tarjetas con su saldo inicial, el saldo que resulta de sus movimientos y el saldo de su cuenta contable. **Los dos últimos deben coincidir.** Una tarjeta de empresa se trata como un banco más (con su cuenta, por ejemplo la 521 en Empresa B).

## Movimientos de banco

[Movimientos de banco](pantalla:movimientos) son los cobros, pagos y transferencias, con el saldo tras cada uno. Su **asiento se genera solo**. Normalmente no se teclean: salen de pagar una factura o de aceptar una línea del extracto. Si hay que corregir algo, se corrige el movimiento (o se hace un asiento manual) y no una cifra suelta.

## Vencimientos

Un **vencimiento** es lo que queda por cobrar (de una factura emitida) o por pagar (de una recibida). Se crean solos al grabar la factura y desaparecen al cobrarlos o pagarlos.

En [Vencimientos pendientes](pantalla:vencimientos), doble clic en uno para **cobrarlo, pagarlo, compensarlo o cambiar su fecha**. Al pagarlo se elige el banco o la tarjeta y la fecha, y se crea el movimiento. Una factura se puede pagar en **varios pagos**, y un pago puede cubrir **varias facturas**.

> **Dónde está lo pendiente:** si una factura aparece en [Recibidas del trimestre](pantalla:conciliacion) sin movimiento, al «Contabilizar el resto» pasa a vencimiento pendiente. Cuando encuentre su cargo en el extracto, se paga desde [Sugerencias de pago](pantalla:conciliar-pagos).

## Extractos

[Extractos del banco](pantalla:extractos) guarda **línea a línea** lo que el banco dice que pasó. Se importa el Excel del banco con **Importar extracto**: el programa reconoce el banco por sus columnas (CaixaBank, BBVA, Santander y la tarjeta de Empresa B) y **no repite líneas** aunque los ficheros se solapen. Si entre un fichero y el siguiente falta algún tramo, avisa.

El extracto no es contabilidad: es la **referencia** contra la que se comprueba la contabilidad.

## Conciliar: de la línea del extracto al asiento

Cada línea del extracto acaba de una de estas formas:

1. **Paga una factura** reconocida: se aplica desde [Recibidas del trimestre](pantalla:conciliacion) («Aplicar propuestas») o, si es un cobro, desde [Emitidas del trimestre](pantalla:emitidas-trimestre).
2. **Paga varios vencimientos** pendientes, o uno en varias veces: [Sugerencias de pago](pantalla:conciliar-pagos).
3. **Es otra cosa** (un ticket, un impuesto, un pago del socio, una comisión): [Líneas sin factura](pantalla:lineas-sin-factura).
4. **Ya estaba contabilizada** de otra forma (por ejemplo, un cobro de alquiler): **Enlazar con el extracto** une la línea con ese movimiento sin tocar ningún asiento.

## Líneas sin factura

[Líneas sin factura](pantalla:lineas-sin-factura) enseña todo lo que queda libre en el extracto. Para cada línea hay varias salidas:

- **A una cuenta**: la línea se lleva a una cuenta contable (la del socio, la de la liquidación de la tarjeta, la de Hacienda para un impuesto o una devolución). No necesita factura.
- **Como ticket**: se crea una factura sin IVA (0 %) de un proveedor genérico, numerada `TARJ-aammdd-n`, pagada por esa línea. Es lo normal para las compras pequeñas con tarjeta.
- **Crear factura con las marcadas**: marque una o varias líneas y cree una factura con ellas (IVA 21 % por defecto; el proveedor debe existir ya).
- **Pagar vencimientos con las marcadas**: si las líneas pagan facturas pendientes.

**Recordar** guarda la regla («los cargos con este texto van a esta cuenta»). Con reglas, **Aplicar sugerencias** contabiliza de golpe todas las líneas que las cumplen. El programa propone además reglas aprendidas de la contabilidad anterior.

> **Pagos del socio:** si el socio paga con su dinero una factura o un gasto, va a su cuenta (551). Las facturas ya contabilizadas se marcan en [Recibidas del trimestre](pantalla:conciliacion) con **Pagadas por el socio**.

## Cuadre de bancos

[Cuadre de bancos](pantalla:cuadre-bancos) compara, para un banco y un periodo, el **extracto** con el **Mayor de su cuenta**, movimiento a movimiento y en el saldo final. Enseña lo que está solo en uno de los lados. **Si no queda nada y los saldos coinciden, el banco cuadra.** Las fechas pueden diferir unos días entre el banco y el Mayor.

Si solo cuadran los movimientos y el saldo final no, la diferencia viene de un **periodo anterior** (un saldo inicial o un trimestre sin cerrar).

## Preguntas habituales

- **Una línea del extracto no aparece en el Mayor.** Falta contabilizarla: use Líneas sin factura o aplique su propuesta.
- **Un apunte del Mayor no está en el extracto.** Es un movimiento contabilizado que el banco no ha cargado (o con otra fecha). Compruebe si el extracto está completo.
- **Importé el mismo extracto dos veces.** No pasa nada: no se duplican las líneas.
