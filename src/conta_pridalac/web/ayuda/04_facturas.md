# Facturas, proveedores y clientes

Las facturas son el origen de casi toda la contabilidad: de cada una salen **solos** su asiento, su IVA para los modelos y sus vencimientos de cobro o de pago. Por eso la regla es: **si una factura está mal, se corrige la factura**, no el asiento.

## Facturas recibidas y emitidas

- **[Facturas recibidas](pantalla:facturas-recibidas)**: compras y gastos. **[Facturas emitidas](pantalla:facturas-emitidas)**: ventas e ingresos.
- Normalmente no se teclean una a una: se **cargan** desde los Excel del trimestre (véase [El cierre del trimestre](tema:trimestre)) y se completan aquí si hace falta. También se pueden dar de alta a mano.
- **Doble clic** en una factura la abre para ver y editar. Al grabar, el asiento y los vencimientos se regeneran.

### Qué lleva una factura

| Apartado | Qué es |
|---|---|
| Proveedor o cliente, nº de factura, fecha | Quién y cuándo. El nº de factura se usa para detectar duplicadas |
| Fecha contable | El día en que cuenta en la contabilidad y en el IVA. En las recibidas del trimestre es el último día del periodo; en las emitidas, la fecha de la factura |
| Cuenta de gasto o de ingreso, y cuenta del tercero | A dónde va el importe (por ejemplo 62900000) y la cuenta del proveedor o cliente (4000…, 4300…) |
| Líneas de IVA | Una por tipo de IVA: base, porcentaje y cuota. Admite varios tipos, exentas y recargo de equivalencia |
| Ajustes y retenciones | Retención de IRPF (la cuota va al modelo 111) u otros ajustes |
| Vencimientos | Cuándo se cobra o se paga, y por qué banco o tarjeta. Quedan en [Vencimientos](pantalla:vencimientos) hasta que se pagan |
| Justificante | El PDF o la imagen de la factura, que se guarda con ella |

### Duplicadas

Al grabar una factura, si ya hay otra con el mismo tercero, número e importe, el programa avisa de una **posible duplicada** y no graba hasta que lo confirme («grabar de todos modos»). En la carga del trimestre hay además un paso específico, **Quitar duplicadas**.

### Categoría de gasto

Cada factura recibida tiene una **categoría de análisis** (gas, electricidad, combustible, peajes, abonos, labores subcontratadas…). Es la que usa el listado [Gastos por categoría](pantalla:gastos-categoria) para ver en qué se va el dinero, año a año y por proveedor.

- **No es una cuenta y no cambia ningún asiento.** Por eso se puede cambiar también en un **ejercicio cerrado** o con el **trimestre presentado**: no altera libros ni modelos. Cada cambio queda en el [Registro de cambios](pantalla:registro-cambios).
- **Si la factura no tiene una categoría propia, sale sola de su cuenta de gasto**: una factura en la cuenta de electricidad cuenta como electricidad. Por eso, desde 2026, basta con elegir la cuenta de gasto correcta (la ficha del proveedor ya la propone) y no hay que hacer nada más.
- **Para cambiarla**, marque una o varias facturas en [Facturas recibidas](pantalla:facturas-recibidas) y pulse **Categoría de las marcadas…**. La opción «la que sale de su cuenta de gasto» quita la categoría propia. Se usa sobre todo en los ejercicios cerrados, donde la cuenta ya no se puede cambiar.
- **Las inversiones no son gasto corriente.** Una categoría de inversión (maquinaria, obras) sale aparte en el listado y no entra en el «gasto corriente».

### Retenciones y el 111

Las facturas con retención de IRPF (alquileres, profesionales) alimentan el [modelo 111](tema:modelos#modelo-111) y el [190](tema:modelos#modelo-190). Si el proveedor es un perceptor de retenciones, compruebe sus datos (NIF, clave y subclave) en [Proveedores](pantalla:proveedores).

## Proveedores y clientes

[Proveedores](pantalla:proveedores) y [Clientes](pantalla:clientes) guardan su cuenta contable y los datos que se proponen en cada factura (cuenta de gasto habitual, IVA, forma de pago…). Se crean al cargar una factura de un tercero nuevo (el programa lo pide al elegir los proveedores) o a mano.

- Si cambia el nombre o el NIF de un tercero, se corrige aquí una sola vez.
- **Correspondencias de proveedor**: cuando una factura llega con un NIF, el programa la asigna al proveedor que se «recordó» para ese NIF. Si un NIF no debe ir siempre al mismo proveedor (una cadena con parking y restaurante, por ejemplo), se borra en [Correspondencias](pantalla:correspondencias) y se elige a mano en cada factura.
- [Facturación por cliente o proveedor](pantalla:facturacion-terceros) muestra lo facturado a cada uno en un rango de fechas. La columna «Total con IVA» es la que cuenta para el **modelo 347** (más de 3.005,06 € en el año).

## Plantillas de Excel

Para cargar facturas sin depender de otro programa, descargue la plantilla en el cuadro de **Cargar facturas** (en Recibidas del trimestre) y **Cargar emitidas** (en Emitidas del trimestre): enlace «Descargar plantilla». Es un Excel con las columnas exactas que el programa lee y una hoja de instrucciones.

**Recibidas:** Empresa (nombre del proveedor), CIF, FechaFactura, NumFactura, BaseImponible, IVA, MontoIVA, MontoTotal, y opcionalmente RutaCompleta (el PDF), FechaContable y los pares IVA2/MontoIVA2 e IVA3/MontoIVA3 si la factura tiene más de un tipo. Son **obligatorios** el nombre, la fecha y el total; ponga siempre el **número de factura**, porque con él se detectan las duplicadas.

**Emitidas:** N Factura, Fecha Expedición, Emisor NIF, Cliente Nombre, Cliente NIF, Base Imponible, IVA, Cuota IVA, Total y Estado.

> **Ojo:** las columnas se reconocen por su nombre, sin importar mayúsculas, tildes ni signos, pero deben existir. Si falta alguna obligatoria, el programa lo dice y no carga nada.
