# Impuesto sobre Sociedades: modelos 202 y 200

El Impuesto sobre Sociedades tiene dos modelos: el **202**, los **pagos fraccionados** a cuenta durante el año, y el **200**, la **declaración anual** que se presenta en julio del año siguiente.

## Modelo 202: pagos fraccionados

[Modelo 202](pantalla:modelo-202): tres pagos al año, en **abril (1P), octubre (2P) y diciembre (3P)**, del 1 al 20 de cada mes. Es la modalidad del artículo 40.2 de la Ley del Impuesto (la de la mayoría de las pymes): el pago es el **18 %** de una base que es la **cuota del último Impuesto sobre Sociedades presentado cuyo plazo hubiera vencido** al empezar el periodo. Por eso el 1P de abril usa el IS de dos ejercicios atrás (el del año anterior se presenta en julio) y los pagos de octubre y diciembre, el del año anterior.

- La base se **lee del fichero `.200`** de ese Impuesto sobre Sociedades, no se teclea. Los de años anteriores a Conta se importan con la herramienta `tools/importar_is.py` (primero muestra qué haría; con `--aplicar` lo guarda). Si no hay Impuesto sobre Sociedades importado, el 202 no tiene de dónde sacar la base.
- La ficha de la empresa guarda el **tipo de gravamen** y si la cifra de negocios del periodo anterior fue inferior a un millón de euros (una marca del fichero).
- Se hace con los mismos tres botones que los demás modelos: [Los modelos de la AEAT](tema:modelos).
- La **modalidad B** (artículo 40.3, para empresas de más de 10 millones de cifra de negocios) no está hecha.

## Modelo 200: la declaración anual

[200 · Impuesto sobre Sociedades](pantalla:modelo-200): una fila por ejercicio. Doble clic abre la ficha, que reúne **lo que el modelo necesita y no sale de la contabilidad**, con el **cálculo paso a paso**.

### El cálculo

De arriba abajo:

1. **Resultado contable** del ejercicio (de los libros).
2. **Correcciones** al resultado: se **suman o restan** para llegar a lo que cuenta fiscalmente. Salen solas:
   - **Gastos no deducibles**: las cuentas que empiezan por `678` (multas y sanciones) se **suman a la base** como corrección permanente. La contabilidad no se toca: la multa sigue siendo gasto. Las cuentas que cuentan como no deducibles se pueden cambiar abajo («Cuentas no deducibles»).
   - **El gasto por el propio impuesto** (cuentas `630`, `633`, `638`) también se suma, porque no es deducible.
   - Las demás correcciones **todavía no se pueden introducir** (véase abajo).
3. **Base antes de compensar**.
4. **Compensación de bases imponibles negativas** de años anteriores, de la más antigua a la más reciente, con el límite legal (el 70 % de la base; 1 millón de euros en todo caso). Se desactiva con «Compensar las bases imponibles negativas».
5. **Base imponible**, el **tipo de gravamen** y la **cuota íntegra**.

La ficha enseña el cálculo hasta la **cuota íntegra**. Al **generar el fichero** se añaden las retenciones y los pagos fraccionados (los del 202 del ejercicio, tomados de las declaraciones presentadas) para llegar al **resultado**: a ingresar, a devolver o cero.

### Los datos de la ficha

| Apartado | Qué hay que poner |
|---|---|
| **Tipo de gravamen** | Normalmente nada: el programa lo propone. Marque «Aplicar siempre el tipo general del 25 %» para forzarlo |
| **Datos de cierre** | Personal fijo y no fijo, firmante (cargo, NIF, nombre), persona de contacto, «actividades agrícolas», y si se compensan bases negativas |
| **Correcciones** | Filas libres para otras correcciones (**aún no se escriben en el fichero**: véase Limitaciones) y las cuentas no deducibles |
| **Retenciones** | Las retenciones e ingresos a cuenta sufridos, por tipo, y otros importes (incremento por pérdida de beneficios fiscales, intereses de demora, abono de deducciones de I+D+i) |
| **Bases imponibles negativas** | Una fila por año en que se generó una base negativa, con lo ya aplicado. «Pendiente (manual)» solo si arrastra un saldo de otro programa. Una fila sin importe se borra al guardar |
| **Caracteres de la declaración** | Las marcas del modelo (entidad patrimonial, base imponible negativa o cero, incentivos de reducida dimensión…). Se abre la lista completa |

La base negativa de un año **se añade a mano** al terminar el ejercicio (el cálculo avisa: «Este ejercicio genera una base imponible negativa de… añádala abajo»).

### El tipo de gravamen

- **Tipo general: 25 %.**
- **Microempresas** (Ley 7/2024; cifra de negocios del periodo anterior **inferior a un millón de euros**): en 2025 **21 % hasta 50.000 € de base y 22 % el resto**; baja cada año hasta 2027 (19/21 % en 2026; 17/20 % desde 2027). El programa lo aplica solo y marca la casilla 00088.
- **No se aplica** si la entidad es **patrimonial** (casilla 00066: más de la mitad de su activo no está afecto a una actividad económica; por ejemplo, un inmueble alquilado sin empleado contratado a jornada completa) ni si se fuerza el 25 %.
- Si la cifra de negocios es de un millón o más, el programa aplica el 25 % y lo avisa (puede corresponder el tipo de entidad de reducida dimensión, que no está hecho).

> **Compruebe siempre** el motivo del tipo en la ficha («Se aplica…»): si usted considera que la entidad es patrimonial, marque la casilla 00066 y se aplicará el 25 %.

### Generar el fichero y validarlo en la sede

Abajo, el bloque **Fichero para la sede**, con sus controles y dos botones numerados:

1. **Generar el fichero**: guarda lo que haya en pantalla y crea el fichero del modelo 200.
2. **Copiar para presentar**: lo copia a la carpeta de descargas con un nombre que se entienda (por ejemplo `EMPRESA_A_AEAT_200_2025_0A.200`).

Después, en la sede: *Impuesto sobre Sociedades → Presentar mediante fichero*.

**Cómo se probó:** con los `.200` de 2025 presentados con el programa anterior, Conta genera ficheros idénticos campo a campo salvo cuatro diferencias explicadas (en `docs/modelo200/`), y la sede los validó sin errores propios: lo único que dijo es que el ejercicio **ya constaba presentado** (por eso, para un ejercicio ya presentado, el fichero sirve solo para comprobar: no vuelva a presentarlo).

### Limitaciones de hoy

- **Solo hay diseño del ejercicio 2025.** El de 2026 lo publica la AEAT en la primavera de 2027 (véase [Normativa y diseños](tema:cierre#normativa-y-disenos)); hasta entonces el programa no genera el 200 de 2026.
- **Registrar la presentación del 200** con el PDF de la sede **todavía no está** (se hará con el diseño de 2026). Guarde el PDF en la carpeta de justificantes de la empresa.
- **No están contrastados con la sede** (ninguna de las dos empresas los necesitaba en 2025): un resultado **a ingresar** (la página de domiciliación), las **correcciones manuales**, las **deducciones y bonificaciones**, la **reserva de nivelación** y las **operaciones con socios** del estado de patrimonio. Los controles **bloquean** el fichero si hay correcciones manuales, reinversión, donativos o deducciones, para no generar una declaración incoherente.
- El **CNAE** que se escribe es el de la ficha de la empresa; la sede pide el de la clasificación de 2025: compruebe que es el correcto.
- Las **entidades parcialmente exentas** y las sin fines lucrativos no tienen modelo 200.

## Si algo no cuadra

- **«Falta el IBAN»**: sale a devolver y la ficha de la empresa no tiene un IBAN válido. Complételo.
- **«Ya presentado»**: es un aviso, no un error: el ejercicio consta presentado con otro programa.
- **La sede dice que falta la persona de contacto, el CNAE o una página**: complete el dato en los datos de cierre o en la ficha de la empresa y genere de nuevo.
- **La base no es la que esperaba**: mire las correcciones del cálculo (las multas y el gasto por el impuesto se suman solos) y las bases negativas que se compensan.
