# El cierre del trimestre

Cada trimestre se hace lo mismo, en este orden. La caja **Trimestre** (la primera del menú) lo lleva por usted: es una lista de pasos, cada uno marcado **Hecho**, **Pendiente**, **Revisar** o **Sin datos**, que se calcula en el momento con la contabilidad (no guarda nada aparte, así que si hace algo por otra pantalla, el paso lo refleja al volver). **Doble clic en un paso** explica qué hacer y abre su pantalla.

> **Cuidado:** haga los pasos **en el orden en que salen**. Aplicar propuestas antes de elegir los proveedores o contabilizar el resto antes de marcar lo que pagó el socio da asientos que luego cuesta deshacer.

## Antes de empezar

1. **Elija el trimestre** con el que trabaja («Cambiar de trimestre», en la pantalla Trimestre). Todas las pantallas del trimestre (recibidas, emitidas, líneas sin factura, sugerencias) se limitan a sus fechas.
2. Tenga a mano, en una carpeta: los **extractos** de cada banco y de cada tarjeta del trimestre (Excel del banco), el **Excel de facturas recibidas** y el **Excel de facturas emitidas** (el que produce Verifactu; si no lo usa, véase [las plantillas de Excel](tema:facturas#plantillas-de-excel)) y los PDF de las facturas.
3. Si es la primera vez o quiere ensayar, trabaje sobre una **copia de ensayo** (véase [Copia de ensayo](tema:cierre#copia-de-ensayo)): no genera ficheros para la sede ni registra presentaciones.

## Los pasos

### 1. Importar los extractos

En [Extractos del banco](pantalla:extractos), **Importar extracto** con el Excel de cada banco y de cada tarjeta. El programa reconoce el banco por las columnas y no repite líneas aunque los ficheros se solapen. Si le falta alguna línea entre un fichero y el siguiente, se lo dice.

### 2. Cargar las facturas recibidas

En [Recibidas del trimestre](pantalla:conciliacion), **Cargar facturas** con el Excel de recibidas. Sale una fila por factura, con el movimiento del extracto que parece haberla pagado. Las dudosas y las que no tienen movimiento se señalan.

### 3. Quitar las duplicadas

**Quitar duplicadas**: el reconocimiento de PDF a veces trae la misma factura dos veces (la factura y su justificante de pago). Revise las parejas y confirme.

### 4. Elegir los proveedores nuevos

Doble clic en la fila: elija el proveedor que ya tiene en Conta o marque **crear el proveedor nuevo**. Si un NIF debe ir siempre al mismo proveedor, «Recordar» guarda la correspondencia ([Correspondencias de proveedor](pantalla:correspondencias)). **Mientras queden proveedores por decidir, no se pueden aplicar las propuestas.**

### 5. Aplicar las propuestas con extracto

**Aplicar propuestas** crea la factura y su pago con la línea del extracto, cuando hay una sola factura para un movimiento del mismo importe. Es el paso que más trabajo ahorra.

### 6. Marcar las pagadas por el socio

**Pagadas por el socio**: marque las facturas que pagó con su dinero y elija su cuenta y el día. No tienen movimiento en el banco de la empresa.

### 7. Aplicar de nuevo

**Aplicar propuestas** otra vez: ahora contabiliza también las pagadas por el socio.

### 8. Contabilizar el resto como pendientes de pago

Hágalo **al final**: **Contabilizar el resto** deja las facturas sin movimiento como **vencimientos pendientes de pago** (aparecen en [Vencimientos](pantalla:vencimientos)).

### 9. Pagar los vencimientos con el extracto

En [Sugerencias de pago](pantalla:conciliar-pagos): el programa propone qué cargo del extracto pagó qué vencimiento (una factura pagada en varias veces, varias facturas en un cargo…). Acepte las correctas. Lo que no se sugiere se concilia desde las líneas sin factura.

### 10. Cargar y aplicar las emitidas

En [Emitidas del trimestre](pantalla:emitidas-trimestre): **Cargar emitidas**, luego **Aplicar propuestas** (crea las facturas nuevas con su cobro) y **Contabilizar el resto** (lo demás queda pendiente de cobro). Las que Conta ya tenía contabilizadas no se repiten: salen en «Hechas».

### 11. Enlazar el extracto con lo ya contabilizado

**Enlazar con el extracto**: une las líneas libres del extracto con movimientos que ya estaban contabilizados (por ejemplo, ingresos de alquileres). No cambia ningún asiento.

### 12. Decidir las líneas sin factura

En [Líneas sin factura](pantalla:lineas-sin-factura) queda todo lo que no es una factura reconocida: tickets de la tarjeta, la liquidación de la tarjeta, pagos del socio, impuestos, comisiones. Para cada línea, doble clic y elija qué es; **Recordar** guarda la regla para la próxima vez, y **Aplicar sugerencias** contabiliza de golpe las que ya tienen regla. Los detalles están en [Tesorería](tema:tesoreria#lineas-sin-factura).

### 13. Comprobar que cada banco cuadra

En [Cuadre de bancos](pantalla:cuadre-bancos), elija cada banco y el periodo del trimestre: tiene que salir **CUADRA**, con el mismo saldo final que el extracto. Esta es la prueba de que el trimestre está bien: **no puede quedar ninguna línea del extracto sin contabilizar ni ningún apunte del banco sin línea**. Si solo cuadran los movimientos, la diferencia de saldo viene de un periodo anterior.

### 14. Pasar la auditoría

En [Auditoría de integridad](pantalla:auditoria): los **errores** impiden cerrar el ejercicio y conviene arreglarlos antes de presentar los modelos; los **avisos** son cosas que conviene mirar. Doble clic en cada hallazgo para ver qué significa y cómo se corrige. Todos están explicados en [Cierre y control](tema:cierre#auditoria-de-integridad).

### 15. Presentar los modelos

En la caja **Liquidaciones**: el [303](pantalla:modelo-303) y el [111](pantalla:modelo-111) del trimestre. En enero, el [390](pantalla:modelo-390) (con el 4T) y el [190](pantalla:modelo-190). Cada uno se hace en tres botones numerados (generar, copiar para presentar, registrar la presentación): [Los modelos de la AEAT](tema:modelos).

### 16. Cuando toca: 202, libros y depósito

El asistente añade solo los pasos que tocan por fecha: el **[202](pantalla:modelo-202)** (pago fraccionado del Impuesto sobre Sociedades) en abril (2T) y en octubre y diciembre (4T); la **[legalización de libros](pantalla:legalizacion-libros)** del año anterior hasta el 30 de abril (1T); y el **[depósito de cuentas](pantalla:deposito-cuentas)** del año anterior en el 2T. Véanse [Impuesto sobre Sociedades](tema:sociedades) y [Registro Mercantil](tema:mercantil).

### 17. Copiar los justificantes y hacer la copia de seguridad

Lo último, con todo presentado: **Copiar justificantes** lleva los PDF de los modelos presentados a la carpeta de la empresa (la que se indica en su ficha, con `{año}` donde va el año), y **Copia de seguridad en OneDrive** hace la copia, la verifica, la lleva a la carpeta y allí la vuelve a verificar.

## Cuándo se da el trimestre por cerrado

Cuando **todos los pasos** salen «Hecho» (o «Sin datos», si ese paso no aplica este trimestre) y **cada banco cuadra con su Mayor**, movimiento a movimiento y en el saldo final. El resto del año quedan los modelos anuales y el Registro Mercantil.

## El año de un vistazo

| Cuándo | Qué |
|---|---|
| Cada trimestre | 303 y 111, hasta el 20 de abril, julio y octubre; los del 4T, el 303 hasta el 30 de enero y el 111 hasta el 20 de enero |
| Enero | 190 (hasta el 31 de enero), 390 (hasta el 30 de enero) |
| Febrero | 347 (hasta el último día de febrero) |
| Abril | 202 (1P, del 1 al 20), libros (hasta el 30 de abril) |
| Junio-julio | Cuentas aprobadas por la junta (antes del 30 de junio); Impuesto sobre Sociedades (modelo 200, en julio); depósito de cuentas (un mes desde la aprobación) |
| Octubre y diciembre | 202 (2P y 3P) |

Si un plazo cae en sábado o domingo, pasa al siguiente día hábil (los festivos no se conocen). El programa **vigila los plazos** y los muestra en el inicio de la empresa y en la auditoría.
