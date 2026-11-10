# Control y gestión de cambios normativos

Conta tiene implementadas a mano cosas que la AEAT, el Registro Mercantil o el BOE cambian cada año: los diseños de registro de los modelos, el calendario de plazos, la taxonomía del depósito
de cuentas y el plan contable. Este documento dice cómo se vigila que no se quede nada desactualizado y qué hacer cuando algo cambia. Código: `servicios/normativa.py` (catálogo, calendario, sondeo),
`ficheros_aeat/comparar.py` (comparación de diseños), pantalla **Normativa y diseños** (en la pantalla de empresas) y avisos en **Auditoría**.

## Cómo se vigila

1. **Calendario.** Cada fuente tiene una «ventana»: el día del año a partir del cual suele salir lo nuevo (200: 1 de abril; 390: 15 de octubre; 190, 347 y calendario: 1 de diciembre; 303: 5 de enero;
   111 y 202: 15 de enero; D2 y Legalia2: 1 de febrero; plan contable: 15 de diciembre). Desde la ventana, y mientras nadie la marque como revisada, sale un aviso en Auditoría y la fila se marca «Por revisar».
2. **Sondeo de la sede.** «Consultar la sede» (o `python tools/sondear_normativa.py`) pide a la AEAT, con una petición `HEAD` y sin descargar nada, el tamaño y la fecha de modificación de los diseños
   del 200, 202, 303 y 390 y los compara con los de cuando se implementaron. También busca el diseño del ejercicio siguiente (`…/archivos_26/DR200e26.xls`). Un cambio sale como «¡Cambio en la sede!».
   Los modelos 190, 347 y 111 y lo que no es de la AEAT (D2, Legalia2, BOE) no tienen sondeo automático: solo calendario.
3. **Revisión.** «Marcar como revisada hoy» apaga el aviso hasta la ventana del año siguiente. Las revisiones y el último sondeo se guardan en `_normativa.json`, junto a las bases de datos.

Estado fijado el 03/11/2026: todo revisado; la sede confirma que los diseños del 200, 202, 303 y 390 son los implementados y que todavía no existen los del ejercicio siguiente.

## Qué hacer cuando cambia un diseño de la AEAT

Ejemplo con el modelo 200; los demás siguen el mismo camino con `tools/extraer_diseno_aeat.py` en lugar de `tools/dr200_a_json.py`.

1. **Bajar el diseño** de la sede (Ayuda → Diseños de registro) a una carpeta de trabajo. Es un fichero de la AEAT: se baja con la autorización de Javier y se guarda en `datos_locales/diseno_200/`, no en git.
2. **Convertirlo a JSON**: `python tools/dr200_a_json.py DR200e26.xls src/conta_pridalac/ficheros_aeat/dr200_2026.json` (necesita `xlrd`: `pip install xlrd`).
3. **Compararlo con el anterior**: `python tools/comparar_disenos.py src/conta_pridalac/ficheros_aeat/dr200_2025.json src/conta_pridalac/ficheros_aeat/dr200_2026.json --salida docs/modelo200/cambios_2025_2026.txt`.
   El informe lista páginas nuevas y quitadas y, por campo (identificado por su casilla): altas, bajas, movimientos, cambios de tamaño, de tipo y de texto. Lo que no aparece, no ha cambiado.
4. **Adaptar el generador** solo en lo que cambia: casillas nuevas o movidas en `impuesto_sociedades_200*.py`, tablas de líneas en `impuesto_sociedades_200_estados.py`, páginas nuevas. Hoy `fichero200.py` conoce un solo diseño
   (`EJERCICIO = 2025`); con el de 2026 habrá que elegirlo por ejercicio (como ya hace la lectura de `.200` en `impuesto_sociedades.py`).
5. **Comprobar contra la realidad**: con un `.200` presentado del año anterior, `tools/comparar_200.py`; y, antes de presentar, **importar el fichero en la sede sin firmar** (el 2025 sirvió para encontrar la página 13, el CNAE y la página 21).
6. **Actualizar el catálogo** (`CATALOGO` en `servicios/normativa.py`: versión, ejercicio, tamaño y fecha de referencia del diseño nuevo) y marcar la fuente como revisada.

Cuando el 390 de 2026 se presente en enero de 2027 hay que repetir el paso 5 (la sede no admitía el ejercicio 2026 hasta entonces).

## Otras fuentes

- **Calendario del contribuyente (diciembre).** Añadir las fechas de domiciliación del año nuevo a `PUBLICADAS` en `servicios/plazos.py` y comprobar los plazos de los modelos anuales. Hasta entonces las fechas estimadas salen «no confirmadas».
- **Depósito de cuentas (D2) y taxonomía.** Antes de junio: abrir D2, importar el ZIP de prueba (sin enviar) y ver si pide otra versión de la taxonomía o cambia alguna validación.
- **Legalización (Legalia2).** Antes de abril: importar el ZIP en la carpeta de prueba (sin enviar).
- **Plan contable y cuentas anuales (BOE).** Cada diciembre, mirar el BOE y la web del ICAC por reales decretos o resoluciones que cambien el balance, la PyG o la memoria de PYMES; si los hay, revisar `cuentas_anuales.py`, `memoria_pymes.py` y el mapeo de casillas del 200.

## Vigilancia del BOE (depósito de cuentas)

Los cambios del depósito de cuentas empiezan siempre en una **resolución de la Dirección General de Seguridad Jurídica y Fe Pública** que aprueba los modelos de cuentas anuales (se publica en el BOE entre abril y junio; en 2026, la de 19 de mayo, en el BOE del 29 de mayo) y después el Registro actualiza D2. La página de descargas del Registro es una aplicación web dinámica y no se puede consultar de forma sencilla; el BOE sí tiene una **API pública y oficial** (`https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD`), así que la fuente «Depósito de cuentas · D2» se vigila por ahí.

- **Qué hace:** «Consultar la sede» (en la pantalla de empresas → Normativa y diseños) mira, día a día y sin domingos, los sumarios del BOE de **abril a julio** de cada año posterior al ejercicio implementado, y guarda las disposiciones cuyo título lleva *modelos*, *Registro Mercantil* y *cuentas anuales*.
- **Incremental:** recuerda hasta qué día ha mirado y solo consulta lo nuevo. La primera vez son unas 60 consultas (unos 15 segundos); después, las de los días que faltan. Tiene un tope de 150 por pasada: si se corta, se pulsa otra vez.
- **Educado:** se identifica como «Conta-Pridalac (control de normativa)», pide solo JSON y no repite días.
- **Qué enseña:** en la ficha de la fuente, las disposiciones halladas con su enlace al PDF; y un **aviso en la auditoría** («el BOE ha publicado el…») mientras no se marque la fuente como revisada **después** de esa fecha.
- **Qué hacer con el aviso:** leer la resolución, revisar lo que Conta tenga implementado (datos de identificación como el **CNAE**, los modelos que cambian y la casilla de información país por país en el modelo normal), adaptar, probar la importación en D2 sin enviar y **marcar la fuente como revisada hoy**.
- **Ampliable:** cualquier fuente puede llevar `boe=(palabras…)` y `boe_meses=(mes inicial, mes final)` en `CATALOGO`.

Los tests nunca consultan el BOE de verdad (`tests/conftest.py` corta la función de red); el de extremo a extremo se hace a mano con `sondear_boe`.

## Qué no hace esto

No descarga ni aplica nada solo: avisa, enseña la disposición del BOE y compara, y la decisión de adaptar el programa es de Javier. Tampoco ve cambios que la AEAT haga sin cambiar el tamaño ni la fecha del fichero, ni los de la normativa
que no es un diseño de registro (por eso el calendario y el BOE llevan su aviso periódico).

## Vigilancia mensual desde el móvil (rutina de la app Claude)

Conta comprueba por sí mismo la sede **cuando se abre la pantalla Normativa y diseños** y se pulsa «Consultar la sede». Para enterarse **sin abrir Conta**, la app Claude del móvil tiene una rutina mensual (la misma que vigila los modelos de la aplicación del autónomo). Para que también cubra los modelos de Conta, el texto de esa rutina puede ser:

> Cada día 3 de mes, revisa en la sede de la Agencia Tributaria (Ayuda → Diseños de registro y novedades de modelos) si hay **cambios o diseños nuevos** de los modelos **200, 202, 303, 390, 111, 190 y 347** (y 130 si procede), y si hay novedades en el calendario del contribuyente, en el depósito de cuentas (D2), en la legalización de libros (Legalia2) o en el Plan General Contable de PYMES (BOE/ICAC).
> Contesta solo con lo que haya cambiado desde el mes anterior: modelo, qué cambia, desde qué ejercicio y el enlace. Si no hay nada nuevo, di solo «Sin novedades».
> Si hay un diseño nuevo, recuérdame: «Abrir Conta → Normativa y diseños → Consultar la sede, y pedirle a Claude Code que lo adapte (procedimiento: docs/11_control_de_cambios_normativos.md). Después, en cada equipo: Ejercicio → Programa → Actualizar ahora.»

El camino completo es: **aviso** (móvil o pantalla Normativa) → **adaptar** el diseño con Claude Code y pasar los tests → commit y push → en cada equipo, **Programa → Actualizar ahora**.
