# Los modelos de la AEAT

Conta calcula el **303**, **111**, **115**, **190**, **180**, **347** y **390** a partir de los libros, los controla, genera el fichero y registra lo presentado. El **202** y el **200** (Impuesto sobre Sociedades) tienen su propio tema: [Impuesto sobre Sociedades](tema:sociedades).

> **No todas las empresas presentan los mismos modelos.** En la ficha de la empresa, **Modelos que presenta**, se marca lo que le corresponde: de lo que no se marque no salen plazos en el panel, avisos en la auditoría, pasos en el trimestre ni opciones en el menú (los modelos que ya tienen presentaciones registradas siguen a la vista). Al crear una empresa se propone una selección según su plan de cuentas; cámbiela si no es la suya, y si duda de qué le corresponde, consúltelo con su asesor.
>
> **El programa nunca envía nada a la AEAT.** Genera el fichero; usted lo sube en la sede con su certificado y después registra aquí la presentación con el PDF que le devuelve la sede.

## Cómo es cada pantalla (todas iguales)

Cada modelo tiene su pantalla en la caja **Liquidaciones**. Doble clic en un periodo (un trimestre, o el ejercicio) abre la ficha, con:

- **Cálculo y casillas**: lo que sale de los libros, casilla a casilla, y las facturas que hay detrás de cada una (en el 303).
- **Controles**: los **errores** impiden generar el fichero; los **avisos** son cosas que conviene mirar (una factura sin NIF, una cifra rara, un plazo vencido).
- **Datos que se introducen a mano**, en los modelos que los necesitan (por ejemplo, la regularización de la prorrata del 303).
- Tres botones **numerados, en este orden**:

1. **Generar el fichero.** Guarda el borrador, lo comprueba y crea el fichero de la sede. Queda en el almacén, con su huella para detectar si alguien lo toca.
2. **Copiar para presentar.** Copia el fichero a su carpeta de descargas con un nombre que se entienda (por ejemplo `EMPRESA_A_AEAT_303_2026_1T.303`; `_rectificativa` si lo es). Así lo encuentra fácilmente al subirlo. «Abrir la carpeta de copias» la abre en el Explorador.
3. **Registrar la presentación.** Cuando la sede le dé el justificante, suba el PDF **«Información de la presentación»**: de él se leen el **número de justificante**, el **CSV** y la **fecha**, y la presentación queda registrada con su PDF. No se teclean a mano.

Los botones se marcan con ✓ cuando el paso ya está dado.

Para **guardar sin generar** use «Guardar borrador»; «Recalcular la vista» enseña el cálculo con lo que acaba de escribir sin guardar nada.

### Estados

| Estado | Qué significa |
|---|---|
| Borrador | Calculado y guardado, sin fichero |
| Sin presentar | Hay fichero generado pendiente de presentar |
| Presentado | Registrado con su justificante: ya no se puede tocar ni regenerar |
| Rechazado | La sede lo rechazó. **«Marcar como rechazada»** permite preparar un borrador nuevo |

Lo que no está presentado se puede **eliminar** («Eliminar lo que no se presentó»). Lo presentado, no: queda como registro.

### Qué hacer en la sede

1. En la sede, el modelo, **Presentar mediante fichero**, y suba el que copió. La sede lo valida y le da errores o avisos; si hay errores, no se presenta nada.
2. Si todo va bien, presente con su certificado y descargue el PDF **Información de la presentación**.
3. Vuelva aquí y use el botón 3.

Si la sede rechaza el fichero, copie el mensaje (el código y el texto): casi siempre indica la casilla o el dato que falla.

### Rectificar una declaración

Si ya presentó y hay un error, se presenta una **rectificativa** (303), una **complementaria** (111 y 202) o una **sustitutiva** (390, 190 y 347): el tipo de presentación se elige en la ficha del periodo. El fichero lleva el número de justificante de la presentación anterior, que ya está registrado.

## Plazos

Cada modelo tiene su plazo y, para el 303, 111, 202, etc., también un plazo más corto si se **domicilia** el pago:

| Modelo | Plazo de presentación |
|---|---|
| 303 | Hasta el 20 de abril, julio y octubre; el 4T, hasta el 30 de enero |
| 111 | Hasta el 20 de abril, julio y octubre; el 4T, hasta el 20 de enero |
| 115 | Hasta el 20 de abril, julio y octubre; el 4T, hasta el 20 de enero |
| 190 | Hasta el 31 de enero |
| 180 | Hasta el 31 de enero |
| 390 | Hasta el 30 de enero |
| 347 | Hasta el último día de febrero |
| 202 | Del 1 al 20 de abril, octubre y diciembre |
| 200 | En julio (25 días naturales desde los seis meses del cierre) |

Si el último día cae en sábado o domingo, pasa al primer día hábil siguiente (los festivos no se conocen: compruebe el suyo). Las fechas de **domiciliación** son las que publica la AEAT cada diciembre en su calendario; las de años en que todavía no se han publicado se estiman y salen como **no confirmadas**. El programa vigila los plazos y los avisa en el inicio de la empresa y en la auditoría.

## Modelo 303

Autoliquidación trimestral del **IVA**. Se calcula con los libros de IVA de las facturas del trimestre. Tipos de declaración: **ingreso** (con NRC), **domiciliación** (el IBAN va en el fichero), **devolución**, **compensación** y **sin actividad / resultado cero**.

Datos que se introducen a mano: la **regularización de la prorrata**, las **cuotas a compensar** de periodos anteriores (si el trimestre anterior no consta presentado en Conta) y si se domicilia o se paga con **NRC**. Debajo de la lista de trimestres están las [declaraciones presentadas](pantalla:declaraciones) tal como se presentaron, con las facturas de cada casilla (solo lectura).

La ficha incluye un apartado **Plazos y pago** con el último día para presentar y para domiciliar.

## Modelo 111

Retenciones e ingresos a cuenta del **IRPF**, trimestral. Casi siempre se presenta **sin actividad** (si no hay retenciones). Si las hay, se calculan con las facturas con retención del trimestre.

## Modelo 115

Retenciones por el **alquiler de locales y otros inmuebles urbanos** (el 19 % de la renta, sin IVA), trimestral. Se calcula con los asientos del trimestre que **cargan la cuenta 621** (arrendamientos) y abonan la 4751 (retenciones): la base es la renta sin IVA, la retención lo abonado a la 4751 y los arrendadores son las cuentas de acreedor (40 y 41) de esos asientos. **Las retenciones de alquileres no se cuentan en el 111**, y al revés.

Los trimestres sin alquiler con retención **no hay que presentarlos**: el asistente del trimestre lo dice así. Si un alquiler no lleva retención (arrendador exento, por ejemplo con rentas de hasta 900 € al año) sale un aviso por si se olvidó retener. Los arrendadores sin NIF en su ficha también salen avisados, porque harán falta para el resumen anual (modelo 180). El resto de la pantalla (borrador, fichero, copia, registro con el PDF de la sede y complementaria) es igual que la del 111.

## Modelo 190

Resumen **anual** de retenciones: lo retenido a cada **perceptor** en el ejercicio. Los datos de cada perceptor (NIF, clave y subclave de percepción) están en la ficha del [proveedor](pantalla:proveedores). Se presenta en enero.

## Modelo 180

Resumen anual de las retenciones por **alquileres** (el 115 del año entero), que se presenta en enero. Es la **suma de los cuatro 115** agrupada por arrendador: la renta del año sin IVA, el porcentaje (el último del año) y lo retenido. Es informativo: no hay nada que pagar.

Además de la renta, la AEAT pide en cada arrendador los datos del **inmueble** (situación, referencia catastral y dirección). No salen de la contabilidad: se escriben en la ficha del proveedor, en el apartado **«Inmueble que alquila (modelo 180)»**, y la provincia del arrendador en «Perceptor de retenciones». Sin ellos se puede guardar el borrador pero no generar el fichero. Si el mismo arrendador alquila dos inmuebles, hace falta una cuenta de proveedor para cada uno, porque el programa no puede repartir la renta entre ellos.

El número de justificante lo lleva ya el propio fichero (empieza por 180); al registrar la presentación se comprueba que el PDF de la sede dice el mismo. La rectificación es la declaración sustitutiva. Pantalla, fichero, copia y registro con el PDF son iguales que los del 190.

## Modelo 347

Declaración **anual** de operaciones con terceros: los clientes y proveedores con **más de 3.005,06 €** en el año, por trimestres. El importe que cuenta es el «Total con IVA» de [Facturación por cliente o proveedor](pantalla:facturacion-terceros). Se presenta en febrero.

## Modelo 390

Resumen **anual** del IVA, con las mismas facturas que los cuatro 303. Arriba salen los **controles contra los 303** (lo que la AEAT cruza) y debajo, las casillas por apartado. Antes de generarlo, complete en la **ficha de la empresa** las **actividades** (hasta seis, con su código) y los **representantes con poder** (hasta tres, con fecha del poder y notaría). Se presenta con el 4T, en enero.

> **Ojo con el año:** en las pruebas de octubre de 2026, la sede de la AEAT todavía no admitía ficheros del ejercicio 2026 (decía que faltaba el año del ejercicio). El fichero del 390 de 2026 se puede generar y revisar ya, pero su validación en la sede hay que repetirla en enero.

## Lo ya presentado con otro programa

[Declaraciones presentadas](pantalla:declaraciones) (y las equivalentes de cada modelo) guardan lo presentado tal como se presentó, con su PDF, aunque se hiciera con el programa anterior. Sirven para comparar, para calcular los periodos siguientes (la bolsa de cuotas a compensar del 303, la base del 202) y para el control de duplicados: un periodo ya presentado no se vuelve a generar «normal».

## Normativa: cuándo cambian los diseños

La AEAT cambia los diseños de registro de los modelos casi todos los años. El programa lleva el control: [Cierre y control: Normativa y diseños](tema:cierre#normativa-y-disenos).
