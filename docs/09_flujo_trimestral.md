# 09 · Flujo trimestral dentro de Conta-Pridalac

Diseño acordado el 30/10/2026 para traer al programa de contabilidad el trabajo de cada trimestre, que hasta ahora se reparte entre **Verifactu** (reconocer PDF, conciliar con el banco) y **el programa anterior** (contabilizar y generar los modelos). Sustituye al punto 16 del backlog («Importar facturas conciliadas con el banco desde Verifactu»).

**Objetivo:** que el 4T de 2026 se haga entero en Conta-Pridalac (fases 1 a 5). El reconocimiento de PDF sigue en Verifactu hasta después (fase 6). El 3T de 2026, ya presentado con el programa anterior, sirve de ensayo en las dos empresas.

## 1. El flujo

**Facturas recibidas**
1. Ruta de las facturas del trimestre.
2. Ruta de los extractos (suele ser la misma carpeta). Regla por empresa con plantilla `<raíz>\<año>\<n>T`, deducida de la última carpeta usada: Empresa B `D:\OneDrive\EMPRESA B\Hacienda 2026\Facturas 3T`, Empresa A `D:\OneDrive\EMPRESA A\Facturas EMPRESA A\Facturas 2026\3T 2026`.
3. Reconocimiento: PDF de recibidas → moneda extranjera a euros → ajustes manuales → alta de proveedores nuevos (automática).
4. Conciliación con los bancos: automática → manual del resto, asistida por las palabras de conciliación → facturas que no están en ningún extracto, a la cuenta del socio → aplicar (limpio y sin errores).
5. Contabilizar los movimientos del extracto sin PDF: pagos de factura y pagos al socio.

**Facturas emitidas:** traerlas de Verifactu (todas las del trimestre) e identificar su cobro en el extracto.

**Verificación (condición para dar el trimestre por cerrado):** para cada banco y tarjeta, el extracto es igual al Mayor, **movimiento a movimiento y en el saldo final, desde el primer día del periodo hasta el último**. No puede quedar ninguna línea del extracto sin contabilizar ni ningún apunte del banco sin línea.

**Modelos:** 303 y 111 del trimestre; 202 cuando toca; 190 y 390 en enero; subirlos a la AEAT; registrar la presentación con el PDF de la sede.

**Copia de seguridad:** dentro del programa, y copiarla a su sitio en OneDrive.

Los modelos 347, 200 y el Registro Mercantil no cuelgan del trimestre: se rigen por el **control de presentación de modelos** (vigilancia de plazos y auditoría de integridad).

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Emitidas | Se traen de la base de datos de Verifactu (datos exactos), no se leen sus PDF. Todas las del trimestre, enviadas o no a la AEAT: Empresa A las envía (tres al año, hace de banco de pruebas) y Empresa B no está obligada. |
| Reconocimiento de PDF | Sólo recibidas, y cualquier emitida de otro origen. Con la API de Claude; quien lo use necesita su clave. |
| Fecha contable | Recibidas: siempre el último día del periodo. Emitidas: la fecha de la factura. |
| Moneda extranjera | El importe en euros es el realmente cargado en el extracto; se puede corregir a mano al revisar. |
| Cada factura y sus pagos | Normalmente un pago por factura, a veces dos; casi nunca más. |
| Factura sin extracto | Va a la cuenta del socio. En Empresa B hay una sola; en Empresa A hay dos (551): se elige en un desplegable. |
| Movimientos sin PDF | Se crea una factura, a veces con el justificante del banco adjunto y a veces sin él. La mayoría sin IVA: cuota de la comunidad, seguros, recibos de impuestos, comisiones del banco. Muy repetitivos: reglas por empresa. |
| Pagos al socio | Van a su cuenta 551. |
| Tarjeta de Empresa B (521) | Su liquidación sale en CaixaBank siempre con el concepto `V.NEGOCIOS CRED.`: es un traspaso entre banco y tarjeta, regla fija. |
| Clave de la API | Una por instalación, protegida como en Verifactu (validado): AES-256-GCM con una clave derivada por PBKDF2-HMAC-SHA256 de la contraseña del certificado, con sal y nonce aleatorios. Se guarda cifrada en la base de cada empresa y se abre al entrar en ella con esa contraseña; se teclea una vez y hay una opción para reutilizarla en la otra empresa. En Conta: 600.000 iteraciones y el NIF de la empresa como dato asociado, para que el cifrado no se pueda trasladar a otra empresa. |
| Justificante del banco adjunto a una factura sin PDF | Se guarda en la misma carpeta donde están las facturas recibidas del trimestre. |
| PDF de las emitidas | Javier los copia a la misma carpeta de las recibidas con el prefijo `Emitida`; Conta los une a su factura por el prefijo y el número. |
| Reglas | Se proponen a partir de lo ya contabilizado desde el programa anterior (qué texto del banco acabó en qué cuenta) y se confirman. |
| Plazo y orden | 202 de diciembre (1 al 20) con el programa anterior; 303 y 111 del 4T, 190 y 390 (hasta el 30 de enero) ya en Conta. |

## 3. Piezas nuevas

- **Cierre del trimestre:** pantalla asistente con los pasos y su estado, que se puede dejar a medias y retomar. Cada paso se puede repetir sin duplicar nada.
- **Extractos** guardados línea a línea, por banco, con un formato por banco y sin duplicados entre trimestres. Formatos: CaixaBank (cabecera en la fila 3, importe como texto), tarjeta de Empresa B (sin saldo, importe como `29,7 EUR`), BBVA y Santander (bloque de datos antes de la tabla). Los que traen saldo permiten comprobar que no falta ninguna línea.
- **Conciliación** con el motor de Verifactu: importe exacto con nombre o CIF; importe con céntimos si es único; divisa extranjera por texto y fecha (hasta 5 días); y lo que quede, manual. Más las palabras de conciliación (alias) y las excepciones de CIF, que pasan de ficheros a tablas editables por empresa.
- **Reglas** de líneas sin PDF: texto del movimiento → tercero, cuenta, tipo de IVA (casi siempre exento) y si lleva factura.
- **Copia a OneDrive:** carpeta de destino configurable, con comprobación de que la copia llegó entera.

## 4. Fases

| Fase | Contenido | Se prueba con |
|---|---|---|
| 1 | Extractos: importar los cuatro formatos, guardarlos y cuadrar cada banco con su Mayor | Extractos reales de 2026 frente a la contabilidad ya importada del programa anterior |
| 2 | Conciliación automática y manual, con los pagos aplicados de forma limpia | El Excel que hoy produce Verifactu; ensayo con el 3T |
| 3 | Líneas sin PDF: reglas, facturas desde el extracto, pagos al socio | 3T de las dos empresas |
| 4 | Emitidas desde Verifactu e identificación del cobro | Las 22 emitidas de 2026 |
| 5 | Asistente del trimestre, verificación, copia a OneDrive, modelos 202 y 390 | 4T de 2026, real |
| 6 | Reconocimiento de PDF dentro de Conta (clave de la API, moneda, proveedores nuevos) | Los 385 PDF de 2026 |

**Ensayo del 3T:** se restaura una copia de seguridad en una carpeta aparte y se ejecuta el flujo nuevo con los extractos y el Excel de Verifactu del 3T; se compara con lo presentado (303, 111) y con el Mayor de cada banco.

**Qué se trae de Verifactu, según la fase.** Fases 1 a 5: las emitidas (su base de datos) y el Excel de las recibidas ya reconocidas, que sigue produciendo Verifactu pero **sin la parte de pagos**, porque la conciliación se hace en Conta. Fase 6, cuando el reconocimiento de PDF también esté dentro: sólo las emitidas.

## 5. Lo que hay en Verifactu (sólo lectura)

- Programa de escritorio PySide6; sus datos reales están en `C:\Users\krind\AppData\Local\VeriFactu\DATOS` (`verifactu_facturas.db`: `emisores` 2, `facturas` emitidas 22, `facturas_recibidas` 385, `config_api`). La clave de la API se guarda cifrada con la contraseña del certificado; **no se lee ni se copia**.
- Ejemplos y trimestres reales en `D:\Proyectos\Claude_VERIFACTU\Conciliacion` y `DATOS` (`EXCEPCION CIFs.txt`, alias en `verifactu_config.json`).
- El Excel que importa Conta hoy (`importar_facturas`) tiene las columnas: nombre de archivo, empresa, CIF, fecha factura, nº factura, base, % IVA, monto IVA, total, ruta, fecha contable, IVA 2 y 3, fecha de pago, concepto de pago, subcuenta de pago.

## 6. Por decidir

- El nombre exacto de los PDF de emitidas (por ejemplo `Emitida 2026-014.pdf`): basta con que lleve el prefijo y el número de la factura tal como sale en Verifactu.

## 7. Fase 1 · extractos y cuadre (30/10/2026)

**Hecho.** `servicios/extractos.py`, `web/extractos.py` y las tablas `extracto` y `extracto_linea`. En Tesorería, dos opciones nuevas: **Extractos del banco** (las líneas importadas, con «Importar extracto» y borrado) y **Cuadre de bancos con su Mayor**.

- **Lectura por nombre de columna**, no por posición: sirve tanto la descarga original del banco como el fichero recortado a mano. Se reconocen BBVA, CaixaBank, Santander y la tarjeta; fechas e importes en texto (`29,7 EUR`, `-658.14`) se entienden sin tocar el fichero. La tarjeta trae los gastos en positivo y se da la vuelta sola (se puede forzar). Sólo se lee la primera hoja con movimientos.
- **Sin duplicados:** la clave de una línea no depende del formato del fichero (fecha, importe y saldo; o texto en la tarjeta), así que un extracto recortado y el original, o dos que se solapan, no repiten nada.
- **Control del saldo:** si el extracto trae saldo, cada saldo debe ser el anterior más el importe; si no, se dice entre qué fechas falta una línea y por cuánto.
- **Cuadre:** empareja cada línea con un apunte del Mayor del mismo importe (primero la misma fecha y luego la más cercana, hasta 5 días), compara los saldos finales (con la apertura, sin la regularización ni el cierre) y los totales de cargos y abonos. Las líneas sin importe no cuentan.

**Con los extractos reales de Verifactu, sobre copias de las bases del programa anterior ya importadas** (las originales no se tocaron):

| Banco y periodo | Resultado |
|---|---|
| Empresa A · BBVA, 12/01–11/02/2026 | **Cuadra:** 7 de 7 movimientos y el mismo saldo (10.047,85) |
| Empresa A · Santander, 08/01–11/02/2026 | 34 de 35; los cargos suman lo mismo (−4.099,09). Un cargo de 153,38 € figura en el Mayor el 20/01 (asiento 3.107, «BANCO JAVIER») y en el banco el 02/02 |
| Empresa B · CaixaBank, 4T de 2025 | 59 de 60 y los abonos iguales; el saldo difiere en **2,70 €**: Securitas se pagó por 165,51 € y la factura está contabilizada por 168,21 € (asiento 3.370) |
| Empresa B · tarjeta, 4T de 2025 | Los cargos del banco superan en 23,33 € a los del Mayor. Los abonos del Mayor (1.823,98 €) son las liquidaciones de la tarjeta, que en el extracto salen en CaixaBank como `V.NEGOCIOS CRED.` |

**Lo que enseña para la fase 2.**
- En la tarjeta, varios cargos de tickets (taxi, aparcamiento) se contabilizan como **una sola factura**: la conciliación necesitará relacionar **varias líneas del extracto con una factura**, además del uno a uno y del uno a dos que ya se esperaba.
- La liquidación de la tarjeta debe emparejarse con el cargo `V.NEGOCIOS CRED.` de CaixaBank (regla fija) para cuadrar la 521.
- El extracto de ejemplo de la tarjeta trae una fila con la palabra «Importe» donde iba la cifra: el programa la señala y no la importa; hay que corregirla en el Excel.

**Primeras pruebas del 3T de 2026 (30/10/2026).**
- **Empresa A cerró la cuenta del Santander en mayo de 2026:** desde entonces su único banco es el BBVA (más las cuentas de los socios, 551). El Santander sólo cuenta para el primer trimestre.
- **Fallo corregido: falsos «faltan líneas» en BBVA.** BBVA da los días de más reciente a más antiguo, pero las líneas de un mismo día en orden cronológico, y el lector las invertía todas: el 3T de Empresa A daba 32 saltos de saldo que no existían. Ahora, dentro de cada día, el orden lo marca la cadena del saldo (y si de verdad falta una línea, se sigue avisando). El BBVA del 3T de Empresa A queda con 0 saltos y saldo de 22.316,20 a 12.075,41.
- **Mejora: misma cantidad, otra fecha.** Si una línea no tiene pareja dentro de los 5 días pero sí otra de la misma cantidad en el Mayor (un pago llevado al último día del trimestre, por ejemplo), se empareja y se lista aparte como aviso: no cuenta como diferencia.
- **Resultado del BBVA de Empresa A, 3T:** 40 de 41 emparejadas y una diferencia, **el recibo de BBVA Allianz Seguros del 22/09/2026, 1.021,06 €, que no está en la contabilidad** (no hay ningún apunte de esa cantidad ni facturas de Allianz en 2026). Es un gasto sin registrar en un trimestre ya presentado.
- **La tarjeta de Empresa B no tiene por qué cuadrar todavía.** El Mayor lleva las liquidaciones (`V.NEGOCIOS CRED.`), que el extracto de la tarjeta no trae, y una regularización de saldo a 30/09. Además: dos facturas de Renfe (66,10 + 36,95) por un único cargo de 103,05; y dos cargos de Solred contabilizados 2,33 € y 2,21 € por encima de lo que cargó la tarjeta. El cuadre propio de la tarjeta se hará con las liquidaciones de CaixaBank (fase 3).


## 8. Fase 2a · motor de conciliación (30/10/2026)

`servicios/conciliacion.py` es un servicio puro (sin base de datos ni pantalla) que, dadas las facturas pendientes y las líneas del extracto, propone qué línea pagó cada factura. Tests en `tests/test_conciliacion.py`.

**Reglas, por orden:** `importe_y_texto` (misma cantidad y el nombre se parece al concepto del banco, o un alias del usuario); `importe_unico` (cantidad con céntimos que sólo tiene una línea); `importe_y_fecha` (cantidad redonda, mismo día, sin otra factura que compita); `varias_facturas_un_cargo` (2 a 4 facturas del mismo tercero suman un cargo); `dos_pagos` (una factura pagada en dos movimientos dentro de 60 días). Lo que no encaja queda como **dudosa** (otro importe parecido, posible factura repetida, varios movimientos iguales) o **sin conciliar**; las líneas que sobran se listan como **libres**.

**Detalles:** el reparto es global por cercanía de fecha (para que dos facturas gemelas no se roben la línea); la fecha de pago es la fecha valor si el banco la da; dos líneas idénticas son intercambiables. El parecido de nombres es el de Verifactu (siglas, cuatro primeras letras, una palabra dentro de otra), así que «Naturgy Iberia» y «Iberdrola» comparten «iber» y se consideran parecidos: el usuario lo corrige con una palabra de conciliación.

**Medición contra el 3T de 2026** (92 facturas pagadas por banco o tarjeta, comparadas con los pagos que Verifactu ya asignó): unas 81 propuestas idénticas (Empresa A 16 de 20, Empresa B 65 de 72). El resto se debe a los datos: importes distintos, líneas que faltan en el extracto, facturas probablemente repetidas (Hotel Palace 57,00; Multiservicios Mapfre 1.331,00; Securitas 165,66; Jardinería 847,00) y enlaces manuales o por IA de Verifactu. Las facturas pagadas por el socio quedan sin conciliar, como debe ser.

**Pendiente:** que `dos_pagos` y `varias_facturas_un_cargo` pidan confirmación en pantalla (riesgo de falso positivo, p. ej. PLENERGY 155,58); lista de trabajo del trimestre desde el Excel de Verifactu; conciliación manual con alias; «aplicar» atómico (factura + movimiento de banco con la fecha y el importe del extracto).

## 9. Fase 2 · conciliación de facturas con el extracto (29-30/10/2026)

**Flujo en pantalla (Tesorería → Conciliación):** 1) *Cargar facturas* del Excel de recibidas de Verifactu (sólo se usa eso de Verifactu; sus columnas de pago no hacen falta); 2) *Quitar duplicadas* (Verifactu reconoce a veces la
factura y también el justificante de su pago); 3) elegir el proveedor de Conta de las que no coincidan (doble clic; «Recordar» guarda la correspondencia por NIF de Verifactu; un proveedor nuevo hay que decidirlo antes de aplicar);
4) *Aplicar propuestas* (una factura, una línea del extracto del mismo importe: crea factura, vencimiento y movimiento de banco con la fecha valor del extracto); 5) *Pagadas por el socio* (marca las que no tienen movimiento y las
paga un socio con su dinero); 6) *Contabilizar el resto* (sin pago: factura con su vencimiento pendiente); 7) **Conciliar pagos** (vencimientos pendientes con líneas libres del extracto: sugerencias y «a mano», con pago parcial o
saldando una diferencia a una cuenta); 8) comprobación final en *Vencimientos pendientes* y en el cuadre de bancos.

**Reglas que conviene recordar**
- El NIF de la propia empresa que Verifactu lee como el del proveedor es el del destinatario: se ignora.
- Las correcciones de proveedor y gasto de facturas ya contabilizadas (aunque su trimestre esté presentado, porque no cambian IVA, importes ni fechas) se hacen con `tools/corregir_proveedores.py`; nunca en ejercicios cerrados.
- Ensayo con copias del 3T (`tools/quitar_trimestre.py` + `tools/comparar_trimestre.py`, simulan por defecto): Empresa A 33 y Empresa B 78 facturas idénticas al programa anterior; el resto son pagos con tarjeta, tickets y casos manuales (fase 3).

**Pendiente:** facturas emitidas y sus cobros (fase 4); tarjeta y líneas sin factura (fase 3); asistente del trimestre y verificación banco = Mayor (fase 5).
