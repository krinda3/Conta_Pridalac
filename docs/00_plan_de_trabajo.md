# 00 · Plan de trabajo — Conta-Pridalac

Versión 0.1 · borrador para revisión · basado en: tablas DBF 2021, 217.000 líneas de código Visual
Objects, manual de Gestión MGD (v3.5) y las decisiones de Javier.

## 1. Objetivo

Sustituir Gestión MGD (Visual Objects / DBF, Windows, sin mantenimiento) por una aplicación **web local en
Python** para llevar la contabilidad de una Pyme u ONG, y completar lo que el
programa nunca tuvo: presentación a la AEAT y gestión con el Registro Mercantil.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Usuarios | Uso propio; dos empresas: Empresa A y Empresa B |
| Alcance funcional | **Solo contabilidad.** Sin facturación, albaranes, pedidos ni stock (ya cubierto por Verifactu) |
| Interfaz | Web local (FastAPI + HTMX) |
| Datos de partida | Tablas 2021 de Gestión MGD (`BBDD 2021`, **Empresa A**); también existen los de Empresa B |
| Contabilidad desde 2022 | En **el programa anterior**; se puede extraer a Excel |
| Régimen fiscal | General de PYMES (IVA general, Sociedades general) en las dos empresas |
| Presentación | Cada empresa presenta con su certificado de representante |
| Código fuente | Es la **última versión** de Gestión MGD (4.0.3); solo el manual es de una versión anterior |
| Plan de cuentas | **8 dígitos** (como el programa anterior). MGD usaba 7: la migración inserta un `0` tras el 4.º dígito en Empresa A y tras el 3.º en Empresa B (`migracion/cuentas.py`) |
| IS | Pago fraccionado (202) por la modalidad habitual |
| Primer hito | Contabilidad completa funcionando con los datos de 2021 |

Recomendaciones técnicas (a confirmar al empezar el Hito 1):
- **Python 3.13**, FastAPI, SQLAlchemy 2 + Alembic, Jinja2 + HTMX, pytest.
- **SQLite** para dos empresas de uso propio (un fichero por empresa, copia de seguridad trivial).
  La capa de acceso permite pasar a PostgreSQL si algún día hace falta.
- **Importes con `Decimal`** (nunca `float`; el original sí usa `FLOAT` y compara con tolerancia de 3 decimales).
- Dominio contable **puro y sin I/O** (listas de `(cuenta, importe)`), probado con los datos reales.

## 3. Hitos

Tamaños relativos: S ≈ días, M ≈ 1–3 semanas, L ≈ 1–2 meses de trabajo a tiempo parcial.

### Hito 0 · Cimientos (S) — **en curso: esqueleto, esquema, cargador MGD, tesorería y bienes de inversión y adjuntos hechos y validados con Empresa A y Empresa B (55 tests); falta el importador del programa anterior**
- Repositorio, entorno, estructura de módulos, CI mínima con pytest.
- Esquema relacional objetivo (derivado de las 51 tablas; las `F_*` de facturación se descartan).
- **Cargador de DBF → modelo nuevo** (lee `BBDD 2021` tal cual, sin pasar por Excel).
- Cierra el pseudocódigo pendiente (§5).

### Hito 1 · Contabilidad con los datos de 2021 (L)  ← **el entregable principal**

**Estado (cuarto bloque: liquidación de IVA y cierre del ejercicio, 251 tests):** `servicios/iva.py` (liquidación por periodo,
compensación, vencimiento de pago; reproduce al céntimo las liquidaciones reales completas y detecta 2 desactualizadas) y
`servicios/cierre.py` (regularización, asiento de cierre, apertura del siguiente con vencimientos, `cerrar_ejercicio`,
`reabrir_ejercicio`); auditoría ampliada y saldos de banco por ejercicio. Ver [pseudocodigo/07_cierre_e_iva.md](pseudocodigo/07_cierre_e_iva.md).
**El motor contable está completo salvo la validación del cierre contra un año anterior de MGD (§6 de ese documento).**

**Estado (tercer bloque: asientos manuales y plantillas, 208 tests):** `domain/plantillas.py` (formato de plantilla, línea
de cuadre, título con `{año}/{mes}`, motor de reglas de fecha de vencimiento), `servicios/extras.py` (grabar, crear desde
plantilla, eliminar) y carga de las 45 plantillas reales; vencimientos de extras enlazados a su apunte; el servicio de asientos
reutiliza ahora los apuntes al regrabar. Probado regrabando los 14 extras reales (Diario y vencimientos idénticos). Ver
[pseudocodigo/06_extras_y_plantillas.md](pseudocodigo/06_extras_y_plantillas.md).

**Estado (segundo bloque: vencimientos y movimientos de banco como servicios, 140 tests):** `servicios/vencimientos.py` y
`servicios/tesoreria.py` (pagar, compensar, transferir, regenerar y borrar), probados regrabando todos los movimientos y
comprobando que el Diario, los saldos y la auditoría no cambian. Regla de vencimientos verificada en 268 facturas
(Σ vencimientos = total + retenciones; ver [pseudocodigo/02_tesoreria.md](pseudocodigo/02_tesoreria.md) §7 bis).

**Estado (primer bloque hecho, 115 tests):** entrada y validación de fechas (`domain/fechas.py`), servicio de asientos
(`servicios/asientos.py`: cuadre obligatorio, solo subcuentas, ejercicio abierto, idempotente, numeración del diario sin
recompactar), servicio de facturas (`servicios/facturas.py`: graba la factura y regenera sus asientos, avisos de fechas y
totales, no borra con pagos) y auditoría de integridad (`auditoria.py`, ver [05_auditoria_de_integridad.md](05_auditoria_de_integridad.md)).
Probado regrabando todas las facturas de las dos empresas (el Diario queda idéntico). **Pendiente:** informes (Diario, Mayor, balances, libros de IVA), bienes de inversión como
servicio, adjuntos como servicio y la interfaz web.
Módulos:
1. **Empresas y ejercicios**, parámetros, periodos contables.
2. **Plan de cuentas** (PGC Pymes, 8 dígitos), terceros (clientes, proveedores, acreedores, deudores).
3. **Facturas recibidas y emitidas** con IVA multitipo, recargo de equivalencia, IVA no deducible,
   bienes de inversión, ajustes (IRPF, retenciones) y asientos múltiples.
4. **Tesorería**: bancos, vencimientos, cobros y pagos, compensaciones, remesas, "pendiente de aplicación".
5. **Asientos extra** y plantillas (D/H/Cuadre), todos los tipos (apertura, regularización, cierre, IVA, amortización).
6. **Diario y Mayor**, regenerar asientos, numeración, detección de descuadres, renumerar.
7. **Bienes de inversión** y cuadros de amortización.
8. **Cierre del ejercicio**: existencias, amortización, regularización, cierre y apertura del siguiente ejercicio.
9. **Informes**: balance de sumas y saldos, balance de situación, PyG, extractos, libros de IVA.
10. Pantallas web mínimas para todo lo anterior, con entrada ágil por teclado. **Todos los listados siguen la norma de
    [03_principios_de_diseno.md](03_principios_de_diseno.md):** todos los campos visibles, doble clic para editar,
    columnas expandibles y ordenables, y acciones estándar de Añadir, Borrar, Exportar a PDF y Exportar a Excel.
    Se construye como un componente de tabla reutilizable.
11. **Auditoría de integridad contable** (búsqueda de errores). Informe con todas las comprobaciones, ejecutable
    a demanda y obligatorio antes de cerrar un ejercicio:
    - asientos descuadrados (el caso de la factura `2_194` del programa anterior);
    - huecos y duplicados en la numeración de asientos;
    - apuntes con cuenta inexistente, o sin cuenta de 8 dígitos;
    - fechas fuera del ejercicio/periodo contable del asiento;
    - facturas sin asiento, o asientos sin documento de origen (y al revés);
    - factura cuyo total no coincide con base + IVA + recargo + retenciones + suplidos/tasas;
    - IVA de las facturas ≠ saldo de las cuentas 472/477 en el periodo; cuadre del libro de IVA con el Diario;
    - saldo de una cuenta de tercero ≠ suma de sus vencimientos pendientes;
    - cobros/pagos sin vencimiento, vencimientos pagados dos veces, cuentas de tesorería con saldo anómalo;
    - saldos con signo inusual (clientes acreedores, proveedores deudores), cuentas 129/PyG tras la regularización;
    - apertura del ejercicio ≠ cierre del anterior; amortización acumulada > coste; adjuntos que faltan o están huérfanos.
12. **Entrada y validación de fechas** (todo el programa):
    - Se admite `DDMMAA`, `DDMMAAAA`, `D/M`, `D/M/AA`, `D-M-AAAA` y "hoy"; internamente es siempre una fecha (`date`).
    - Se valida al introducirla, no al grabar: fecha real del calendario (31/02 no existe), dentro del ejercicio y del
      periodo contable abierto, y coherente con el tipo de documento (fecha de factura ≤ fecha contable, etc.).
    - Si se sale del periodo, el programa avisa o bloquea (configurable) y nunca interpreta en silencio otro año.
    - Los ejercicios cerrados no admiten asientos nuevos sin reabrirlos explícitamente.
13. **Adjuntos de facturas recibidas y emitidas** (PDF y JPG): subir, ver al lado de los datos, reemplazar, quitar.
    Almacenamiento en disco por empresa/ejercicio con huella (SHA-256) y comprobación de que no falte ninguno.
    Las facturas de MGD ya tienen PDF (`011_R_00086_…`): el enlace está en la tabla `Etidat`, no en el número del nombre del
    fichero (ver [pseudocodigo/04_justificantes.md](pseudocodigo/04_justificantes.md)). Ya se importan 56 (Empresa A) y 162
    (Empresa B) justificantes, con su huella; los que MGD referencia y ya no existen quedan marcados como ausentes.
    Los adjuntos cuelgan de facturas, movimientos de banco o asientos.

**Criterios de aceptación (con datos 2021):**
- Los 103 asientos / 391 líneas del Diario se regeneran **idénticos** a partir de los documentos
  (hoy verificado: facturas recibidas 56/56).
- Saldos por cuenta idénticos a `Cuentas` (DEBE/HABER) y balance de sumas y saldos cuadrado.
- Regularización de IVA de T1 y T2 idéntica a los extras 2 y 3.
- Asiento de apertura del 2021 reproducible desde el cierre de 2020 si se dispone de datos.
- Informes de Balance y PyG iguales a los que imprimía Gestión MGD.
- La auditoría de integridad detecta el descuadre de la factura `2_194` del programa anterior (fixture de prueba) y no da falsos
  positivos en los ejercicios cerrados que cuadran.
- Pruebas de fechas: casos válidos/inválidos, fin de año, ejercicio cerrado, y entrada `DDMMAA` en todas las pantallas.
- **Validación cruzada** con los años que están en las dos fuentes (2014–2021): mismo diario, saldos y balance entre lo
  que carga el cargador de MGD y lo que carga el importador del programa anterior (tras convertir las cuentas a 8 dígitos).

### Hito 2 · Continuidad: carga desde el programa anterior (M)
- Importación desde **Excel exportado del programa anterior** (programa actual, 2022 en adelante). Ya hay ejemplos de
  Diario, Mayor, Facturas emitidas y Facturas recibidas (Empresa A, 2026). Ver §8 (Hallazgos).
- Conversión del plan de cuentas MGD (7 dígitos) → 8 dígitos para cargar 2021 (y Empresa B).
- Carga de Empresa B y de Empresa A desde 2022 y encadenado de cierres/aperturas con 2021.
- Ejecución en paralelo: comparar saldos y diario del programa actual y del nuevo.
- Lo que **no** exporta el Excel (vencimientos, movimientos de banco, retenciones, bienes de inversión): hay que pedir
  más listados al programa anterior o reconstruirlo desde el Diario.

### Hito 3 · AEAT: metodología común y modelo 303 (L)

El 303 es el modelo guía: lo que se resuelva aquí vale para el resto (111, 202, 390, 190, 347 y, aparte, el 200).

**Metodología común de cada modelo**
1. **Cálculo** desde los libros y los datos de la empresa, validado contra lo ya presentado.
2. **Fichero** para la AEAT según el diseño de registro vigente del ejercicio, validado contra los ficheros que presentó el programa anterior.
3. **Borrador y controles**: pantalla con las casillas, PDF de borrador (marcado como borrador) y comprobaciones antes de presentar.
4. **Estados y trazabilidad**: borrador → presentado → (rechazado) → complementaria o sustitutiva. Se guarda el fichero enviado, la respuesta de
   la AEAT, el justificante y el CSV, la fecha y hora, el usuario y la huella del fichero. Un periodo presentado queda **bloqueado**.
5. **Pago**: domiciliación (lo habitual) y, si no se llega a tiempo, **NRC**; el pago se enlaza con su movimiento de banco.
6. **Presentación** en el entorno de pruebas de la AEAT y después en producción, siempre con confirmación explícita (nunca automática).
7. **Resguardo**: el PDF con el CSV que genera la AEAT se guarda con la declaración.
8. **Panel de plazos y modelos** (caja «Modelos de la AEAT» de la página principal): estado de cada modelo y periodo, plazos y avisos.

**Reglas decididas para el 303** (D13–D16)
- El periodo de una factura es el de su **fecha contable**, que es la de introducción: una factura atrasada que se mete después se contabiliza y declara en el
  periodo en que se introduce. Por eso no hace falta un «periodo de declaración» aparte; sí un control: no se puede grabar ni cambiar una factura con fecha
  contable en un periodo ya presentado.
- La **prorrata** se calcula a mano por ahora (regularización del 4T): el 303 admite el importe como dato introducido. Más adelante, funcionalidad propia.
- Se presenta siempre **con compensación**: el 303 aplica las cuotas a compensar de los trimestres anteriores del año, **tomadas de lo ya presentado** (casilla 87 de
  los 303 presentados, que ya están importados), y en el 4T se cierra el año con ellas.
- Pago: **domiciliación** si se llega a tiempo (y luego se registra a mano en tesorería); **NRC** cuando no (funcionalidad del programa anterior por estudiar e implementar).
  Aplica a 303, 111 (si no es negativo ni «sin actividad»), 202 y, quizá, 200.

**Resultado del paso A2** (`tools/comparar_303.py`, `servicios/modelo303.py`): calculado por fecha contable, el 303 reproduce 27 de las 42 declaraciones presentadas desde 2021
(céntimos de redondeo aparte). 13 más difieren por facturas que se declararon en otro trimestre que el de su fecha contable, por facturas cambiadas después de presentar
(las correcciones de 2026, la factura 142 de Empresa A) y 2 quedan sin explicar (Empresa A 2024-4T: una venta al 2 %; Empresa B 2022-4T: rectificativas de mayo declaradas en el 4T; y en el 2024-4T la
complementaria). Regla de las rectificativas: restan de las casillas 28 y 29 y sólo van a la 40 y 41 si rectifican deducciones de periodos anteriores (marca manual).
Regla de la compensación: ver `servicios/modelo303.py`.

**Resultado de la fase B** (`ficheros_aeat/fichero303.py`): el diseño de registro oficial vigente es `DR303e26v101.xlsx` (sede AEAT → Ayuda técnica del modelo 303; los el programa anterior de 2023-2025 siguen el `DR303e24v200`, sin el indicador de la posición 130 ni las filas del 0 % / 0,75 %, por eso las posiciones se desplazan). `tools/extraer_diseno_aeat.py` lo convierte en `dr303_2026.json` y el generador rellena cada campo por su casilla. Reproduce **byte a byte** los 6 ficheros presentados en 2026 (1T-3T de las dos empresas). El 4T añade la página 04000 (+998 posiciones). Hallazgo: desde 2026 los alquileres exentos de Empresa B se presentaron en la base de la casilla 150 (tipo 0 %); el cálculo lo reproduce — confirmar con el asesor que es lo correcto. Pendiente de la fase B: comprobar con el 4T 2026 real y el signo/compensación del 4T.

**Resultado de la fase C (puntos 1 y 2: datos y controles)**: tablas `presentacion_aeat` (estado borrador/generada/presentada/rechazada/sustituida, tipo normal/complementaria/sustitutiva, casillas congeladas, versión del diseño, huella del fichero, justificante/CSV/respuesta, quién y cuándo) y `presentacion_evento` (historial). `servicios/presentacion303.py`: `crear_borrador` y `controlar_303`. **Errores (bloquean)**: periodo ya presentado sin ser complementaria/sustitutiva · rectificativa sin nada presentado · asientos descuadrados o facturas sin su asiento en el periodo · 303 distinto de las cuentas 477/472 (sólo asientos de facturas) · trimestre anterior sin presentar (salvo bolsa introducida a mano) · domiciliar sin IBAN. **Avisos (no bloquean)**: facturas recibidas sin justificante (no son obligatorios) · asientos manuales en las cuentas de IVA · bolsa a mano · prorrata sin introducir en el 4T · periodo sin actividad · falta el justificante de la presentación anterior. La compensación toma lo presentado con este programa antes que lo importado del programa anterior. Probado con los datos reales de 2026: sin errores en las dos empresas.

**Resultado de la fase C, punto 3 (pantalla)**: listado «Modelo 303» (`web/modelo303.py`, menú «303 · IVA» del panel) con un renglón por trimestre y su estado (sin presentar · borrador · fichero generado · presentado · presentado el programa anterior). La ficha del trimestre enseña las casillas calculadas con su nombre oficial, los controles (errores y avisos), el desglose por factura de cada casilla y los datos a mano (prorrata 44, bolsa, tipo de presentación, domiciliación, rectificativas que van a la 40 y 41); botones: recalcular la vista, guardar borrador y generar el fichero (bloqueado con errores). El fichero se guarda en `<almacén>/<empresa>/<año>/aeat/` con su SHA-256 y la versión del diseño, y se descarga desde la ficha. La auditoría ya no lo trata como fichero huérfano. Falta (punto 4): marcar como presentada y bloquear el periodo, que llega con la fase E.

**Resultado de la fase D (pago, parte que no necesita a la AEAT)**: `servicios/plazos.py` (presentación: 1-20 de abril/julio/octubre y 1-30 de enero, prorrogada si es inhábil; domiciliación: 15 de abril, julio y octubre y 27 de enero de 2026, publicadas por la AEAT; para el resto, estimación con su regla «tres días hábiles o cinco naturales», que reproduce las cuatro publicadas, marcada como estimada). Controles nuevos: domiciliar fuera de plazo (error si la fecha es la publicada, aviso si es estimada) → elegir NRC; presentación fuera de plazo (aviso); NRC con formato no válido (error: 22 caracteres) o pendiente (aviso). La ficha del 303 tiene forma de pago (domiciliación / ingreso con NRC) y campo NRC (se guarda en el borrador; **no va en el fichero**, el diseño de registro no lo tiene: se da al presentar), enseña los plazos y el estado del pago en la contabilidad: vencimiento de la liquidación del IVA y movimientos de banco que lo saldan. En el programa anterior (`C000x440`) la forma de pago es MODPAG (3 = domiciliación, 2 = NRC con su NRC de 22 caracteres, p. ej. el 2T 2026 de Empresa B, presentado el 20/07 con NRC porque ya no se podía domiciliar). **Pendiente, va con la fase E**: obtener el NRC desde el programa. La AEAT lo genera en su pasarela de la sede («Autoliquidaciones - Pago mediante cargo en cuenta», con certificado, NIF, apellido, importe exacto e IBAN); no consta en su documentación pública un servicio web para programas de terceros, así que de momento se obtiene en la sede y se pega; automatizarlo es parte de investigar el servicio de presentación.

**Decisión D17 (NRC)**: el NRC se obtiene fuera del programa (banco o sede) y se pega en la ficha; la ficha da los datos para pedirlo (modelo, ejercicio, periodo, NIF, razón social, importe exacto de la casilla 71) y bloquea el fichero si el resultado cambia después de anotar el NRC (`nrc_de_otro_importe`: un NRC sólo vale para el importe con el que se pagó).

**Investigación de la fase E (envío a la AEAT)**, según el documento oficial para empresas de software «303 · Servicios de Ayuda a la Declaración», versión 7.02 de 2019 (aún por contrastar con la AEAT que sigue vigente en 2026): (1) **Validación y prueba**, sin certificado ni guardar datos, en el entorno de Pruebas para Externos (laborables 8:00-15:00): POST a `https://www6.aeat.es/wlpl/PFTW-PICW/ServVali` con `IDI=ES&LEV=000000000000&FIC=<fichero>&RUT=&PRG=&FIN=&EJF=<año>&MOD=303`; devuelve errores en HTML o el PDF «BORRADOR NO VÁLIDO». (2) **Presentación real**: POST autenticado con certificado de cliente (TLS; no se firma el fichero) a `https://www1.agenciatributaria.gob.es/wlpl/PFTW-PICW/PresBasica` con `FIRNIF`, `FIRNOMBRE` (titular del certificado = presentador), `NRC` (sólo tipo I), `IDI`, `F01=<fichero>` y `FIR=FirmaBasica`; el fichero va en ISO-8859-15, sin CRLF y urlencoded, con las variables en ese orden. Respuesta HTML con el PDF del justificante embebido, el CSV (16 caracteres), fecha, hora, nº de registro, nº de justificante y NRC en variables JavaScript y pseudoXML (si hay error: `ERROR` en el título y `E00`…`E99`). No se pueden anular las presentaciones grabadas. (3) **Pruebas con certificado**: la misma URL cambiando el dominio por `www7.aeat.es`; sin presentación en nombre de terceros (el declarante debe ser el titular del certificado); tras una presentación correcta, los envíos siguientes deben ser complementarias. (4) **Consulta**: POST a `https://www1.agenciatributaria.gob.es/wlpl/SCEJ-MANT/ConsultaExt` (NIF, ANR, MOD, EJF, PER, fechas) devuelve XML con el CSV y el expediente de lo presentado. Plan B: importar el fichero generado en el formulario de la sede (o «Presentación por lotes»). Siguiente paso propuesto: E1 validar los ficheros generados contra el servicio de validación sin certificado (esto envía datos fiscales reales a un servidor de la AEAT: sólo con confirmación expresa), E2 cliente de presentación con el certificado de la empresa en el entorno de pruebas, E3 producción con confirmación explícita y guardado del justificante.

**Decisión D18 (envío)**: la vía principal es el **plan B**: el programa deja el fichero generado y verificado, se importa en la sede con el certificado y se registra aquí lo que devuelve. Motivo: el entorno de pruebas para externos (`www6/www7.aeat.es`) no es accesible (no resuelve en DNS público: es para empresas de software con acuerdo) y una presentación real no se puede anular; el envío directo a `PresBasica` queda como experimento futuro (primero con una petición pensada para fallar y sólo con permiso expreso).

**Resultado del plan B**: con el fichero generado, la ficha del 303 enseña los pasos y la lista de datos a comprobar en la sede (tipo de declaración, NIF, razón social, casillas 27, 45, 46, 71 y 87, IBAN o NRC) con enlaces a la sede, y un formulario para registrar la presentación (nº de justificante de 13 dígitos, CSV de 16 caracteres, fecha y hora, PDF del justificante). `registrar_presentacion` comprueba que el fichero sigue en el almacén y sin alterar (SHA-256), que no haya otra presentación del trimestre (sólo complementaria o sustitutiva), que el ingreso con NRC lo lleve y que el NRC corresponda al importe; guarda el PDF en `<empresa>/<año>/aeat/`, pasa a «presentada» (el trimestre queda bloqueado para un borrador normal y alimenta la bolsa de compensación del siguiente) y deja la historia en el registro de eventos; una sustitutiva deja la anterior como «sustituida». «La sede lo ha rechazado» marca la presentación como rechazada con los errores que dio la sede; un borrador nuevo descarta el fichero generado anterior sin borrarlo. El justificante se ve desde la ficha. **Pendiente**: bloquear la edición de facturas con fecha contable de un trimestre presentado (hoy sólo avisa la auditoría, como con lo importado del programa anterior); lo mismo, al presentar, para 111, 202 y los demás modelos.

**Decisión D19 (bloqueo de lo presentado)**: una factura incluida en un trimestre con 303 presentado (con este programa o importado del programa anterior, o que figure en una declaración presentada aunque su fecha sea de otro trimestre) **no se modifica ni se borra**, y no se graban facturas nuevas con fecha contable de un trimestre presentado (las atrasadas se contabilizan con la fecha de introducción). Para corregir: factura rectificativa con fecha actual que anule la presentada y factura nueva. `servicios/bloqueo.py` lo aplica en `grabar_factura` y `eliminar_factura` (también al importar el Excel, con el nº de fila) y el formulario de facturas lo comprueba antes de tocar nada. Pendiente: otros modelos (111, 202…) con el mismo molde, y asientos manuales con fecha en un trimestre presentado (hoy sólo avisa la auditoría).

**Corrección sobre las rectificativas del 303 (instrucciones 2026)**: el diseño de 2026 no distingue «complementaria» de «sustitutiva»: cualquier nueva presentación de un periodo ya presentado es una **autoliquidación rectificativa** (marca X, nº de justificante de la anterior —13 dígitos—, motivo «Rectificaciones», y opcionalmente modificar o dar de baja la domiciliación de la anterior). Casillas: **70** = resultado (69) de la anterior si es positivo, esté ingresado o no; **71 = 69 − 70 + 109** (la 109, devoluciones acordadas, queda en blanco porque siempre se compensa); **111** = la parte negativa de la 71 que corresponde a lo ya ingresado (las instrucciones no dan su fórmula: aviso para comprobarla en la sede), y entonces el tipo de declaración se calcula sin esa parte. Una rectificativa presentada deja la anterior como «sustituida»; las segundas rectificativas avisan (tienen anexos propios en las instrucciones) y hay aviso si hay trimestres posteriores presentados (su compensación podría cambiar). El tipo de presentación del programa pasa a ser `normal` o `rectificativa`; los ficheros se llaman `C000X_R303_<año>_<n>T.303`.

**Registro automático desde el PDF de la sede**: `servicios/justificante_aeat.py` lee la primera página del PDF «Información de la presentación de la declaración» (fecha y hora, nº de registro, CSV, nº de justificante, presentador, resultado y, con NRC, el NRC y su importe; comprobado con los 30 justificantes de 2023-2026 que hay del programa anterior). Al registrar una presentación basta subir el PDF: se contrasta con lo generado (modelo, ejercicio del registro, tipo de declaración, NRC e importe), no se admite un justificante repetido y, si el PDF no se reconoce, se pueden teclear a mano justificante, CSV y fecha. **Dónde está lo que se prepara**: la presentación (borrador, fichero, estado e historial) vive en la tabla `presentacion_aeat` de la base de la empresa y el fichero generado en `<almacén>/<empresa:03>/<año>/aeat/<id>_C000X_[R]303_<año>_<n>T.303` (almacén por defecto `datos_locales/justificantes`); sobre un trimestre ya presentado el listado del 303 enseña debajo una fila con la rectificativa pendiente y su fichero, y la ficha dice la ruta.

**Validación real del fichero (27/10/2026)**: la rectificativa del 3T 2026 de Empresa A generada por el programa se importó en el formulario de la sede (A303-FWME/E2026) **sin errores**; la sede sólo dio dos avisos informativos (31190: revisar «Información adicional»; 32006: la casilla 110 no debe haberse aplicado ya en un periodo posterior) y mostró bien el tipo (régimen general), la casilla 71, la marca de rectificativa, el nº de justificante de la anterior (coincide con el presentado) y el motivo «Rectificaciones». Queda validado el camino plan B para el 303; el mismo molde servirá para el 111.

**Decisión D20 (una sola entrada del 303)**: el panel tiene una única opción «303 · IVA» que abre «Modelo 303»: arriba los trimestres (con la rectificativa o el borrador pendientes bajo el trimestre presentado) y debajo las declaraciones presentadas (`Listado.bloque_inferior`). La ficha del fichero generado enseña su ruta, un botón para abrir la carpeta y un desplegable con lo que lleva (datos y casillas leídos del propio fichero).

**Norma D21 (higiene de las pruebas)**: todo lo preparado y **no presentado** (borradores, ficheros generados, descartados y rechazados) se puede borrar, con su fichero del almacén, para no dejar rastro de pruebas; lo **presentado** (y lo sustituido por una rectificativa) no se borra nunca, porque es la constancia de lo declarado. Ficha del 303: «Eliminar lo no presentado (N)» del trimestre; listado: «Borrar» sobre una fila pendiente o sobre el trimestre. `servicios/presentacion303.py` (`sin_presentar`, `eliminar_presentacion`, `eliminar_sin_presentar`) trabaja con `PresentacionAeat`, así que el 111 y los demás modelos heredan la norma. No borra nada fuera del almacén.

**Ajuste del borrado (D21)**: el listado del 303 no ofrece casilla de selección en lo presentado (sólo en lo pendiente), así que ni se intenta; el servidor sigue rechazándolo por si acaso.

**Corrección de la restauración (28/10/2026)**: al restaurar una copia, Windows no deja renombrar la carpeta de justificantes si otro programa la tiene abierta (p. ej. el Explorador): daba un error 500 sin mensaje y dejaba una copia previa inútil por intento. Ahora los justificantes se **sincronizan en el sitio** (sin renombrar carpetas; lo que ya es igual no se toca), cualquier fichero bloqueado se explica por su nombre («ciérrelo y vuelva a intentarlo»), si algo falla se devuelve todo a como estaba y la copia previa sólo se conserva si la restauración se hizo; también `hacer_copia` explica un fichero bloqueado. El resultado de restaurar se queda en el diálogo (no es un aviso que desaparece) y la aplicación avisa siempre de un error del servidor o de red (antes la pantalla se quedaba muda).

**Decisión D22 (arranque con icono)**: primer paso hacia un programa «instalable» sin servidor visible: `conta_pridalac.lanzador` arranca el servidor sin ventana (registro en `web.log`) y abre el navegador, o sólo lo abre si ya está en marcha; `--parar` y el botón «Cerrar el programa» de la barra lo cierran (`POST /_apagar`, sólo desde el propio equipo y con cabecera propia); `tools/crear_acceso_directo.py` crea el icono (Windows `.lnk` con `pythonw`; Linux `.desktop`) en el escritorio, el menú y/o el arranque de la sesión; icono propio (`web/static/icono.ico/png`, generado por `tools/generar_icono.py`). Siguiente paso, si hace falta llevarlo a otro ordenador: instalador (PyInstaller + Inno Setup) con ventana propia y datos en una carpeta de usuario separada del programa.

**Modelo 111 · fases A y B (28/10/2026)**. Reconocimiento: los dos clientes presentan el 111 casi siempre **negativa / sin actividad** (tipo N, todo a cero). Sólo Empresa A tiene retenciones, una vez al año en el 4T (compras a agricultores, 2 %): 2023 con 3 perceptores y 32,28 €, 2024 con 1 y 30,91 €, 2025 con 1 y 38,08 €, presentadas con domiciliación (U). En los libros salen de asientos manuales de compra (no de facturas con ajuste) que abonan la 4751; los pagos a Hacienda cargan la 4751 en un movimiento de banco. (La tabla 431 del programa anterior, con importes trimestrales al 18 %, no es el 111: es el pago fraccionado del 202.) **Diseño**: `DR111e16v18` (v1.8, vale para 2019 y siguientes; la sede lo publica como `.xls`), una sola página de 1.000 posiciones; `tools/extraer_diseno_111.py` (necesita `xlrd`) lo pasa a `ficheros_aeat/dr111_v18.json` con las casillas 01-30 y `ficheros_aeat/fichero111.py` lo genera: reproduce **byte a byte los 38 ficheros presentados** (los de las dos empresas, 2022-2026). **Cálculo** (`servicios/modelo111.py`, regla en su cabecera): retención = abono neto a la 4751 en los asientos del trimestre (sin banco, apertura, cierre ni liquidaciones); percepción = lo devengado al perceptor antes de retener (total de la factura con su IVA, como se ha presentado); perceptores = cuentas de acreedor distintas; todo a actividades económicas dinerarias (07-09). `tools/comparar_111.py`: coinciden 17 de 17 trimestres de Empresa B y 18 de 19 de Empresa A; la diferencia es el 4T de 2023 (el programa anterior declaró 3 perceptores y los libros tienen 2; y 1 céntimo de redondeo). Pendiente por decidir: ese 3 frente a 2, si las percepciones deben llevar o no el IVA, y el plazo de presentación y de domiciliación del 4T (el 111 del 4T es del 1 al 20 de enero, no hasta el 30 como el 303). Siguen las fases C a E con la misma infraestructura que el 303.

**Norma D23 (copiar el fichero para presentarlo)**: el fichero generado se queda en el almacén (`<empresa>/<año>/aeat/<id>_…`), pero «Copiar para presentar» (ficha del trimestre y botón «Copiar fichero para presentar…» del listado) lo copia a una carpeta dedicada, `Descargas\\Conta Pridalac` (la Descargas que diga Windows —la tuya está redirigida a OneDrive—, o `CONTA_DESCARGAS`), como `<EMPRESA>_AEAT_<modelo>_<año>_<periodo>[_rectificativa].<extensión>`, p. ej. `EMPRESA_A_AEAT_303_2026_1T_rectificativa.303`. El prefijo sale del «Nombre corto» de la ficha de la empresa (si está vacío, la razón social sin S.L./S.A.). No pisa un fichero distinto con el mismo nombre (guarda `_2`, `_3`…) y no repite uno igual; sólo copia si el original sigue sin alterar; botón para abrir la carpeta. `servicios/exportar.py` es genérico: lo usarán el 111, el 190, el 347, el 200 y lo del Registro Mercantil.

**Calendario contrastado con la sede (28/10/2026)** y cargado en `servicios/plazos.py` para 303, 111, 115, 202, 390, 190 y 347: 303 hasta el 20 de abril, julio y octubre y el 30 de enero; **111 y 115 hasta el 20 de abril, julio, octubre y 20 de enero**; 202 hasta el 20 de abril, octubre y diciembre; 390 hasta el 30 de enero; 190 hasta el 31 de enero (2 de febrero de 2026 por ser sábado); 347 hasta el último día de febrero (2 de marzo de 2026); los plazos que caen en inhábil pasan al siguiente día hábil. Domiciliación publicada por la AEAT: 303 y 130/131 hasta el 27 de enero (4T) y el 15 de abril, julio y octubre; 111 y otros trimestrales hasta el 15 de enero, abril, julio y octubre; 202 el 15 de abril, el 15 de octubre y el 16 de diciembre; 390 y 190 no figuran en esa tabla. Lo no publicado (otros años) se estima con la regla de tres días hábiles o cinco naturales y se marca como estimado. Al salir el calendario de cada año (diciembre) hay que revisar la tabla.

**Respuestas sobre el 111 (28/10/2026)**: el 4T de 2023 declaró 3 perceptores y los libros tienen 2 (Ulpiano Martín López y Luis Javier García Hernández): el tercero no existe en los libros; el ejercicio 2023 está cerrado y no se toca. Las percepciones se siguen presentando con IVA (como hasta ahora) para el 2023; **queda pendiente confirmar con el asesor** si de aquí en adelante deben ir sin IVA, antes del 4T de 2026. Plazos: validados arriba.

**Modelo 111 · fases C, D y E (29/10/2026)**, con la misma infraestructura que el 303: tabla `presentacion_aeat` con `modelo = '111'` (borrador, fichero, estados, historial, NRC), `servicios/presentacion111.py` (borrador, controles y fichero), `web/modelo111.py` (pantalla «Modelo 111» con los trimestres y, debajo, las declaraciones presentadas; «Copiar para presentar»; registro de la presentación subiendo el PDF de la sede; borrado de lo no presentado) y las rutas de fichero, justificante y copia, que sirven a los dos modelos. Lo que cambia respecto al 303: no hay compensación ni prorrata; la rectificación se llama **complementaria** (casilla «Declaración complementaria» + justificante de la anterior, y la casilla 29 resta lo ya ingresado; si saldría menos que antes, error: eso no se corrige con una complementaria); sin retenciones el trimestre sale «negativa / sin actividad» (tipo N); el pago se comprueba en la contabilidad (cargos a la 4751 hasta dos meses después del trimestre, también en el ejercicio siguiente). Controles: periodo ya presentado, justificante de la anterior, asientos descuadrados, avisos del cálculo (retención no habitual, perceptor sin NIF), plazos (el 111 del 4T es hasta el 20 de enero), IBAN y NRC. **Importación de lo ya presentado**: la tabla 199 del programa anterior es el 111 (`migracion/programa_anterior.cargar_declaraciones_111`, también en la carga completa) y `tools/importar_111_presentados.py` la añade a una base ya cargada y enlaza sus PDF (sin tocar nada más y sin duplicar); sin ese paso el programa no sabría qué trimestres del 111 están presentados. Arreglo de paso: al crear un borrador de un trimestre presentado el mensaje era el de otro error (p. ej. plazo de domiciliación) y no el de «ya está presentado»; también en el 303. Pendiente del 111: la casilla de percepciones con o sin IVA (asesor, antes del 4T de 2026), el 190 anual y los datos de los perceptores que pide.

**Arranque y cierre (29/10/2026)**: «Abrir la carpeta» del fichero copiado pasaba a Explorer la ruta mal entrecomillada y, con espacios (`Descargas\Conta Pridalac`), abría Documentos; ahora una sola función (`exportar.abrir_en_el_explorador`) sirve a las dos rutas. Procesos que quedaban vivos: al cerrar la pestaña nadie apagaba el servidor lanzado por el icono, y seguía ocupando el puerto. Ahora el servidor del icono arranca con `--autoapagar` (la página avisa a `/_latido` cada 15 s; sin avisos durante 3 minutos se cierra solo), acaba con `os._exit` tras parar para no dejar procesos, y si el puerto está ocupado lo dice con un mensaje claro. Puerto configurable (`--puerto` o `CONTA_PUERTO`); no se usan puertos distintos por defecto para que no puedan abrirse dos copias sobre las mismas bases.

**Modelo 190 · fase A: fichero (29/10/2026)**: `ficheros_aeat/fichero190.py` (diseño `DISENOS_LOGICOS_190_2025.pdf`: registro 1 de declarante + un registro 2 por percepción, 500 posiciones y CR LF). Reproduce byte a byte los 8 ficheros presentados (Empresa B 2021–2024, sin perceptores; Empresa A 2022–2025: 2 perceptores en 2023, Ulpiano y Javier García, y sólo Javier en 2024 y 2025, clave H subclave 03, provincia 13). La zona numérica del final del registro 2 crece con el diseño (2023: hasta la posición 387; 2024: 388; 2025: 394). Sólo claves de actividades económicas (G, H, I); las del trabajo no están. Los 190 de Empresa A y de Empresa B están en `AEAT/` (del 190 de Empresa A 2021 sólo hay el PDF de la sede; falta el .190) y los PDF de la sede en `OneDrive\...\Hacienda <empresa>\AEAT <año>`. Siguiente: cálculo desde los asientos por perceptor y clave (reutilizando el del 111), comparación con lo presentado, datos fiscales del perceptor (provincia, clave y subclave) y pantalla.

**Modelo 190 · fase B: cálculo y datos del perceptor (29/10/2026)**: `servicios/modelo190.py` suma los cuatro 111 del año agrupando por perceptor (misma regla de percepciones con IVA y retenciones) y señala lo que falta en cada ficha. `tools/comparar_190.py` lo contrasta con los 190 presentados: coinciden los 8 casos (Empresa A 2022–2025 y Empresa B 2021–2024; Empresa B 2025 no se presentó). La ficha del proveedor gana tres campos (`provincia_190`, `clave_190`, `subclave_190`, validados) en la sección «Perceptor de retenciones (modelo 190)»; la base los añade sola al abrirla. `tools/datos_perceptor_190.py` los rellena desde los 190 presentados (13 / H / 03 para Javier y Ulpiano); sólo escribe con `--aplicar` y nunca pisa lo ya escrito. Siguiente: pantalla del 190 (borrador, controles, fichero, copia para presentar, registro con el PDF de la sede) y la importación de lo presentado.

**Modelo 190 · fase C: presentación (29/10/2026)**: mismo molde que el 303 y el 111 (`servicios/presentacion190.py`, `web/modelo190.py`, `_modelo190.html`), con tres diferencias. El periodo es el ejercicio entero (`0A` en `presentacion_aeat`, 0 en `declaracion_presentada`; `presentacion303.etiqueta_periodo`). Es informativo: sin pago, NRC ni domiciliación. El número de justificante lo genera el programa y va dentro del fichero (posiciones 108-120; la sede lo respeta), así que al registrar la presentación se exige que el PDF de la sede diga el mismo número. Rectificar es la declaración sustitutiva (con el identificativo de la anterior); la complementaria no está. Controles: ya presentado, datos del declarante (teléfono y representante de la ficha de la empresa), perceptor incompleto (NIF, provincia, clave, subclave), asientos descuadrados, cuadre con los cuatro 111 presentados (la AEAT los cruza) y plazo (31 de enero; 2 de febrero de 2026). `tools/importar_190_presentados.py` añade a una base ya cargada los 190 presentados a partir de los ficheros de `AEAT/` (justificante, perceptores e importes) y enlaza sus PDF; es seguro repetirlo. Sólo claves G, H e I (actividades económicas). Pendiente: probar la presentación real (Empresa B 2025, sin perceptores) y, en el 4T de 2026, decidir si las percepciones llevan IVA.

**Vigilancia de plazos de los modelos (29/10/2026)**: `servicios/vigilancia.py` comprueba el 303 y el 111 de cada trimestre y el 190 del año (sólo si hubo retenciones) y avisa si no constan presentados: **aviso** desde dos meses antes del vencimiento, **error** en la última semana («URGENTE») y **error** desde que vence (hay que presentarlo ya, aunque sea directamente en la sede). Sale en la pantalla de Auditoría (`auditar(..., con_plazos=True)`; el cierre del ejercicio no lo pide, no es contabilidad) y en un recuadro arriba del panel de la empresa, que mira este año y el anterior (el 4T y el 190 vencen en enero del año siguiente). Lo anterior a la primera presentación que consta de cada modelo no se juzga (son años sin datos importados). Primer resultado con los datos reales: Empresa A 303 4T 2025 (se presentó el 12/01/2026 y se complementó el 23/01/2026, pero el programa anterior no lo tiene en su tabla y falta importarlo) y Empresa B 111 1T y 2T de 2022 (sin ficheros: a confirmar si se presentaron).

**Declaraciones que faltaban en lo importado (29/10/2026)**: la vigilancia de plazos destapó dos huecos del programa anterior. **Empresa A 303 4T 2025** (presentado el 12/01/2026 y complementado el 23/01/2026) no está en su tabla 440: `tools/importar_declaracion_pdf.py` lo registra desde el PDF de la sede (justificante, fecha y presentador; los importes no se leen y quedan vacíos). **Empresa B 2022**: el programa anterior numeró por mes algunos trimestres (03 = 1T, 06 = 2T), así que el 2T quedó como periodo 6 y el 1T y el 3T se mezclaron en el periodo 3 (la fecha de emisión es la del 1T y el justificante y el envío, los del 3T); `tools/corregir_periodo_declaracion.py` pasa el periodo 6 a 2 (con simulación previa) y el 1T se registra desde su PDF, que sólo trae las etiquetas (`--sin-lectura`: queda presentado, sin justificante). `servicios/justificante_aeat.py` lee también el formato antiguo de la sede (2022 y anteriores: etiquetas juntas y valores después). **El 303 de Empresa B de 2022** tiene la misma mezcla: 1T presentado el 14/04/2022 (3033015265052, sin justificante en la base), 2T con cuatro presentaciones (original 17/07 a las 11:22, 3033010499820, solicitud de devolución; complementaria a compensar 17/07 a las 11:27, 3033015825734, guardada como periodo 6; reenvío corregido 15/09, 3033004402732; y otra fila del 22/07 sin justificante que no se identifica), 3T y 4T correctos. `tools/corregir_periodo_declaracion.py` (ahora también cambia el tipo) y `tools/completar_declaracion.py` (rellena justificante y fechas desde el PDF, sin pisar) lo dejan ordenado.

**Modelo 347 · fases A y B (29/10/2026)**: `ficheros_aeat/fichero347.py` (diseño oficial `347.pdf` de la sede: registro 1 de declarante y un registro 2 por declarado, hoja D; los de inmueble no están) reproduce byte a byte los 8 ficheros presentados (Empresa B y Empresa A, 2022–2025); desde 2025 el registro lleva ceros hasta la posición 305 (BDNS). `servicios/modelo347.py` calcula por tercero y clave (A compras, B ventas) lo operado con IVA por trimestre, con la **fecha contable** (con la de la factura fallan 3 de los 8 años) y el umbral de 3.005,06 €; omite los terceros marcados «No incluir en el 347» y avisa de los que operan por encima del umbral sin NIF o sin código postal (la provincia son sus dos primeros dígitos). `tools/comparar_347.py`: coinciden 6 de los 8 años; las dos diferencias son datos (Empresa A 2023: dos ventas a «Pistachos del Sol» en un cliente sin NIF; Empresa B 2024: la factura 25 a Loches está en la base por 2,66 € más de lo presentado). La provincia sale del código postal o, si no hay, del nombre de la provincia de la ficha (`ficheros_aeat/provincias.py`, con la lista oficial); `tools/provincia_terceros.py` rellena las fichas que no la tienen a partir de los 347 presentados (con simulación previa). Pendiente: fase C (borrador, controles, pantalla, copia para presentar, registro con el PDF, importación de lo presentado y plazo: finales de febrero).
**Backlog del usuario (29/10/2026)**: 347 (en curso); cambiar el menú; listados (sumas y saldos, saldos acumulados por mes, facturación por cliente o proveedor en un rango de fechas, balance de situación y PyG por rango, balance y PyG oficiales, estado de cambios del patrimonio neto); entorno Windows y Linux (requisitos y dependencias); ayuda; añadir empresa o autónomo (con su PGC: empresa, autónomo, ONG, pyme); seguimiento de cambios de normativa contable y de modelos (sobre todo 200 y Registro Mercantil); importar desde un backup de MGD; compartir el programa con otra persona (desde cero o con MGD). El listado de facturación por tercero sale casi gratis del cálculo del 347.

**Modelo 347 · fase C: presentación (29/10/2026)**: mismo molde que el 190 (`servicios/presentacion347.py`, `web/modelo347.py`, `_modelo347.html`, `migracion/declaraciones347.py`, `tools/importar_347_presentados.py`): periodo `0A`, informativo, justificante = identificativo del fichero (la sede lo conserva: se comprueba contra el PDF al registrar), rectificar con sustitutiva. Controles: ya presentado, teléfono y representante de la empresa, declarado sin provincia, tercero por encima del umbral sin NIF, trimestres negativos (aviso), asientos descuadrados y plazo (finales de febrero; 2 de marzo de 2026). La vigilancia de plazos incluye el 347 (sólo si algún tercero supera el umbral). Para que el programa sepa qué 347 están presentados hay que importarlos: `tools/importar_347_presentados.py --nombre <empresa> --comprobantes ...` (con copia hecha y el programa cerrado).

**Listado «Facturación por cliente o proveedor» (29/10/2026)**: `servicios/facturacion_terceros.py` y `web/facturacion.py` (menú Facturas). Lo facturado a cada cliente (emitidas) y proveedor (recibidas) por rango de fecha contable, de más a menos, con filtros por tipo, nombre o NIF e importe mínimo; «total con IVA» es el importe que cuenta para el 347 y «neto» el de las facturas con sus retenciones. Doble clic: las facturas de ese tercero en el mismo rango. Comprobado con los datos reales: los terceros por encima de 3.005,06 € de 2025 son exactamente los del 347 presentado de Empresa A (3) y de Empresa B (7).

**Listados contables de gestión (29/10/2026)**: `servicios/estados_contables.py` y `web/estados.py` (menú Contabilidad): **saldos acumulados de un mes** (saldo anterior, movimiento del mes y saldo acumulado por cuenta, a 1, 2, 3 u 8 dígitos), **balance de situación** por rango de fechas (grupos 2 y 3 al activo, grupo 1 al patrimonio neto y pasivo, y los grupos 4 y 5 según el signo del saldo de cada cuenta, con el resultado del ejercicio; la última línea es la diferencia activo − pasivo) y **pérdidas y ganancias** por rango (ingresos del grupo 7, gastos del grupo 6, por subgrupo, cuenta o subcuenta). Por defecto excluyen la regularización y el cierre (R y Z). Con los datos reales el balance cuadra en los 12 ejercicios de Empresa A y Empresa B. El «balance de sumas y saldos» con rango de fechas ya existía. Pendiente: balance, PyG y estado de cambios del patrimonio neto **oficiales** (asignar cada cuenta a su línea del modelo normal o abreviado; sirven también para el depósito de cuentas del Registro Mercantil) y decidir si los listados tienen una caja propia en el menú.

**Balance y PyG oficiales de PYMES (29/10/2026)**: el modelo que usa el programa anterior es el de PYMES (PGC de Pymes, RD 1515/2007), no el abreviado. `servicios/cuentas_anuales.py` asigna cada cuenta a su línea por el prefijo más largo (tablas `ACTIVO`, `PASIVO` y `PYG`) y `web/estados.py` ofrece «Balance oficial (PYMES)» y «Pérdidas y ganancias oficial (PYMES)» con el ejercicio anterior al lado. Validado contra los listados oficiales del programa anterior de Empresa A 2025 y 2024: coinciden todas las líneas del balance de 2025 y de la PyG de 2025 y 2024, y el activo de 2024 (129.549,23 €). Política de saldos de signo contrario como el programa anterior: se restan dentro de su línea (un 410 con saldo deudor resta de «Otros acreedores») y se avisa de dónde lo llevaría el PGC; las cuentas sin línea salen aparte, nunca se pierden. No incluyen regularización ni cierre. Con los datos reales cuadran los 12 ejercicios de las dos empresas, sin cuentas sin línea. Aviso de datos: la 118 de Empresa A tiene saldo deudor, y en varios ejercicios la 129 arrastra un resultado sin aplicar (la línea «Resultado del ejercicio» del balance no coincide con la PyG). La reserva de capitalización queda sin cuentas (no se usa). **Para el modelo 200**: el resultado del ejercicio se lleva a su cuenta específica hacia marzo del año siguiente, y es entonces cuando se cierra el ejercicio; mientras tanto la 129 arrastra el resultado del año anterior en el balance del siguiente. Hay que definir cómo se presenta eso (antes y después de aplicar el resultado) cuando se haga el 200. Menú: nueva caja «Listados» (facturación por tercero, sumas y saldos, saldos acumulados, balance de situación, PyG y los dos oficiales). Pendiente: estado de cambios en el patrimonio neto.

**Estado de cambios en el patrimonio neto de PYMES (29/10/2026)**: `cuentas_anuales.estado_cambios_pn` y listado «Estado de cambios en el patrimonio neto (PYMES)» (caja Listados). Una columna por componente (capital, no exigido, prima, reservas, acciones propias, resultados anteriores, otras aportaciones, resultado, dividendo a cuenta, ajustes, subvenciones) y total; filas: saldo final del año anterior, ajustes (en blanco), saldo ajustado, ingresos y gastos reconocidos (el resultado del año), operaciones con socios (movimiento de capital, prima, acciones propias, aportaciones y dividendo) y otras variaciones (lo que falta hasta el saldo final: la aplicación del resultado del año anterior), saldo final. Se calcula sobre las líneas del balance de PYMES, cuyas cuentas coinciden con la «Configuración de cuentas anuales (PYME)» del programa anterior. Validado con el listado del programa anterior de Empresa A 2025: coinciden todas las cifras (saldo final 2024 de −154.876,45, resultado −14.532,46, aplicación del resultado 17.580,03 y saldo final 2025 de −169.408,91). Las filas duplicadas y las de 2026 con signo contrario que imprime el programa anterior no se copian. Dato a revisar: en Empresa A 2024 «Otras variaciones» suma 2.834,31 €, es decir, resultados anteriores varió en 2024 más que la aplicación del resultado de 2023 (¿un ajuste de ejercicios anteriores?). Pendiente: pasar a validar las líneas del balance y de la PyG con las configuraciones del programa anterior.

**Configuración de cuentas anuales del programa anterior, contrastada (29/10/2026)**: con las capturas de la «Configuración de cuentas anuales (PYME)» se ha comparado la asignación de cuentas del balance. Coincide casi toda; se han añadido 544 (otros deudores), 502 y 507 (deuda con características especiales a corto plazo), 1034, 1044, 190, 192, 194, 500, 505, 506 y 509 (otras deudas a corto plazo), 296 y 2935 (inversiones a largo plazo) y se han repartido 2933/2934 (grupo) y 2935 (largo plazo). **Un asterisco delante de una cuenta (`*551`, `*5523`) significa «según el signo del saldo»**: al activo si es deudora y al pasivo si es acreedora; está implementado (la 551, cuenta corriente con socios, va a «Otras deudas a corto plazo» si es acreedora y a «Inversiones financieras a corto plazo» si es deudora). Lo que no lleva asterisco (como la 410) se resta dentro de su línea, y por eso el activo de 2024 de Empresa A es 129.549,23 €. Con los desgloses de los puntos suspensivos se completó el activo: las inversiones en empresas del grupo a corto plazo llevan 5933, 5934, 5943, 5944, 5953 y 5954 (no 5593 y 5594), las cuentas 553 a 555 no son «según signo» en el activo, y los deterioros 5935, 5945, 5955, 597 y 598 de las inversiones financieras a corto plazo son un supuesto (la lista está cortada tras la 593). **PyG**: las líneas 4, 5, 6, 7, 11, 13b, 14 y 17 de la configuración del programa anterior coinciden con las del programa; sólo faltaba la 7957 en gastos de personal. Con los desgloses del pasivo corriente se cerró también «Otras deudas a corto plazo» (1034, 1044, 190, 192, 194, 500, 505, 506, 509, 5115, 5135, 5145, 521, 522, 523, 525, 526, 528, *551, *5525, 555, 5565, 5566, 5595, 560, 561) y «Deudas con empresas del grupo a corto plazo» (5103, 5104, 5113, 5114, 5123, 5124, 5133, 5134, 5143, 5144, *5523, *5524, 5563, 5564): de las 55x, sólo la 551 y la 5525 (y la 5523 y la 5524 en las del grupo) van según el signo; la 553 y la 554 quedan como respaldo del pasivo, no figuran en el programa anterior. Lo último que faltaba también está cerrado: la lista completa de «Inversiones financieras a corto plazo» sólo añade la 596 a lo supuesto, y la configuración de la PyG del programa anterior (todas las líneas) coincide con las del programa. La PyG oficial de Empresa A 2025 coincide línea a línea con el programa anterior; la de 2026 (listado del 28/10/2026) coincide en las líneas 1, 4 y 5 y difiere en la 7, «Otros gastos de explotación» (−14.325,53 en el programa anterior frente a −14.329,71 en la base: 4,18 €), seguramente por algún apunte de 2026 cambiado en el programa anterior después de la última exportación. **Menú**: ver `docs/07_rediseno_del_menu.md` (idea del usuario y estructura del menú del programa anterior).

**Menú en cajas (29/10/2026)**: banda de pestañas bajo la barra superior en todas las pantallas de una empresa; cada pestaña abre las opciones de su caja (Facturas, Tesorería, Asientos, Inmovilizado, Datos, Listados, Liquidaciones, Impuesto sobre Sociedades, Registro Mercantil y Ejercicio); en el inicio se abre la última usada y en cada pantalla, la suya. Los modelos y obligaciones que faltan salen en gris. El inicio ya no repite tarjetas: sólo los avisos de plazos. Detalle y pendientes en `docs/07_rediseno_del_menu.md`.

**Fases (paso a paso, cada una se revisa antes de seguir)**
- **A. Cálculo del 303, sin conexión.** Casillas del régimen general (devengado por tipos, deducible, resultado, compensación). Se valida reproduciendo
  casilla a casilla las 45 declaraciones ya importadas (23 de Empresa B y 22 de Empresa A); toda diferencia queda explicada.
- **B. Fichero del 303.** Generación según el diseño de registro vigente, validada **byte a byte** contra los `AEAT/*.303` del programa anterior (37 ficheros).
  Aprovechan también el 111, 202, 390, 347, 190 y 200 como ficheros de referencia (D5).
- **C. Borrador, controles, estados y trazabilidad**, con los controles: NIF e IBAN válidos, importes coherentes, resultado coherente con las cuentas de
  IVA, periodo no presentado ya, ejercicio y datos de la empresa completos.
- **D. Pago**: domiciliación y enlace con el movimiento de banco; después NRC.
- **E. Envío**: pruebas de la AEAT y producción, y guardado del resguardo. Antes, verificar en la documentación vigente de 2026 el formato y los
  servicios de presentación (no reutilizar formatos de memoria) y confirmar cómo se firma (certificado de la empresa, ya en la ficha).
- **F. Panel de plazos y modelos**, que puede ir en paralelo desde la fase C.
- Después, con el mismo molde: **111** (retenciones; el caso habitual es «sin actividad»), **202**, **390**, **190** y **347**. El **200** será un capítulo
  aparte por su complejidad (Hito 5).
- Asiento de regularización de IVA automático: ya existe y las liquidaciones presentadas quedan como definitivas.

### Hito 4 · Modelos anuales 390 y 190 (M)
- Resumen anual de IVA (390) y de retenciones (190), sobre lo ya calculado en el Hito 3.
- Declaración de terceros (347) si procede; el original solo daba el listado.

### Hito 5 · Impuesto sobre Sociedades: 200 y 202 (L)
- Modelo 200: resultado contable → base imponible (ajustes, bases negativas, reservas, amortización fiscal, deducciones).
- Modelo 202 (pagos fraccionados).
- Es el más sensible de todos: requiere decidir con tu asesor qué ajustes extracontables se automatizan.

### Hito 6 · Registro Mercantil (L)
- **6a. Legalización de libros** (Diario, Mayor, inventario…): integración con **Legalia**. Investigar formato,
  firma y límites de tamaño.
- **6b. Depósito de cuentas**: generar el fichero **ZIP que consume el programa D2** (cuentas anuales
  en el formato oficial, con memoria y certificaciones).
  **Hecho (1/11/2026)**: `servicios/deposito_cuentas.py`, `web/deposito.py`, pantalla «Depósito de cuentas». Conta prepara la carpeta que abre D2 (`DEPOSITO.XML`, el «Esquema» de códigos y valores con los datos de la sociedad, las fechas y los importes del balance y de la cuenta de pérdidas y ganancias del año y del anterior, y `Documentos/MEMORIA.pdf`); la certificación del acuerdo de la junta, su huella digital, las firmas y el envío los hace D2 con Legalia2. Se registra el acuse (fecha, referencia y nº de entrada), el plazo (un mes desde la aprobación, como tarde el 30 de julio) y el paso del asistente (2T). Los códigos confirmados salen del depósito de Empresa A de 2021 (`D:\OneDrive\Legalia2\CAPR2021`); los demás siguen la numeración de D2 y se marcan «inferidos» hasta ver un fichero real con esas partidas (deudas a largo plazo, partidas financieras…).

## 4. Orden y dependencias

```
H0 ─► H1 ─► H2 ─► H3 ─► H4 ─► H5 ─► H6a ─► H6b
              └──────────────► (H6a puede adelantarse tras H1)
```
Los Hitos 6a y 6b solo dependen de H1 (libros y cuentas anuales) y podrían intercalarse antes si
el calendario mercantil aprieta (la legalización y el depósito tienen plazos anuales).

## 5. Trabajo previo: pseudocódigo que falta leer (antes o durante H0)

| Pendiente | Dónde | Necesario para |
|---|---|---|
| Regeneración completa de asientos | `RegeneraAsientos.TodosSC` (E_Edicion:5529) | H1.6 |
| Cierre / apertura / cambio de PGC | `CierreContable` (F_Contabilidad:19401) | H1.8 |
| Asiento de regularización de IVA y resumen | `ResumenIVA` (F_Contabilidad:1011) | H1.9, H3 |
| Vencimientos y descripción de pagos | `Vtos_Descripcion`, `ListaPagos` | H1.4 |
| Amortizaciones y bienes de inversión | `AmortUno`, `PlContabiliza`, tabla `Lbi` | H1.7 |
| Libros de registro y declaraciones de terceros | `LibrosRegistro`, `ControlDeclaracionTerceros` | H1.9, H4 |
| Motor de informes (balance, PyG) | `impInformes`, tablas `Informes`/`Infapun` | H1.9 |
| Formato de los `IVA_*.dat` | ficheros `.dat` | H3 |

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| La normativa y los formatos de modelos AEAT cambian cada año | Validar contra la documentación oficial vigente al implementar cada modelo; no reutilizar formatos de memoria |
| Los datos de 2021 cubren pocos casos (4 facturas emitidas, 1 ajuste de IRPF) | Hay datos de **MGD 2014–2021** y de **el programa anterior 2014–2026**: usarlos como corpus de pruebas; completar con casos sintéticos si faltan supuestos |
| Errores en presentaciones con efecto legal | Entorno de pruebas de AEAT primero; en cada modelo, cotejar con la declaración presentada de años anteriores |
| Régimen fiscal | Resuelto: general de PYMES en ambas. Empresa A tiene actividad agraria; comprobar con el asesor que no aplica REAGP u otro régimen especial en alguna operación |
| Certificado digital y credenciales | Almacenarlos fuera del repositorio y del código; acceso solo local |
| Licencia del código original | Solo se usa como especificación del comportamiento; no copiar código. Consultar al autor si algún día se publica |
| Datos reales en el repositorio | `.gitignore` ya excluye muestras y manual; el repositorio no debe contener datos fiscales |

## 7. Dudas

Resueltas:
- **D1.** `BBDD 2021` es de Empresa A. Los datos de MGD de Empresa B 2021 (ZIP "Copia EMPRESA B 2021 3T", empresa 012)
  ya están cargados y validados: 495 asientos, 211 facturas, 320 movimientos de banco. Las reglas de asientos de facturas
  (190/190 recibidas, 21/21 emitidas) y de tesorería (230/230 vencimientos, 320/320 movimientos, saldos y asientos)
  se cumplen también en Empresa B, que además cubre transferencias entre bancos y vencimientos de extras.
- **D2.** La contabilidad desde 2022 está en el programa anterior, exportable a Excel (Hito 2).
- **D3.** IVA general y Sociedades general en las dos empresas.
- **D4.** Cada empresa presenta con su certificado de representante. El certificado nunca entra en el repositorio.
- **D5.** Hay acceso a Legalia y D2, y existen los ficheros que ya se presentan desde el programa anterior: sirven como
  **ficheros de referencia** para H3 a H6 (formato real, no teórico).
- **D6.** `NO_REDUCE_APUNTES = 'N'` en `Param.dbf`: el programa agrupa las líneas de la misma cuenta dentro de cada asiento.

Abiertas:
- **D7.** ~~Tipos de asiento `M` y `Q`~~ → `M` normal/plantilla y `Q` amortización (doc `pseudocodigo/03_bienes_inversion.md`).
- **D8.** ~~Ejemplos de Excel del programa anterior~~ → recibidos (§8). Faltan, para el Hito 2: listados de vencimientos, bancos/tesorería,
  retenciones y bienes de inversión, y una exportación de Empresa B.
- **D9.** ~~Ficheros 303/111 del programa anterior~~ → sí se tienen (carpeta `AEAT/`, fuera de git): 303, 111, 202, 200, 390, 347 y 190 ya presentados.
  Son los ficheros de referencia; el formato se confirma además con la documentación vigente de la AEAT (diseños de registro y servicios web).
- **D10.** ~~202~~ → modalidad habitual. **111:** ver aclaración abajo.
- **D11.** ~~Factura `2_194`~~ → causa confirmada con la captura: la factura incluye una **tasa D.G.T. de 4,18 €** fuera de base e IVA
  (base 30,38 + IVA 6,39 + tasa 4,18 = 40,95) y no se imputó a ningún gasto. Javier la corregirá en el programa anterior.
- **D13.** El periodo de una factura es el de su fecha contable (la de introducción): ver Hito 3.
- **D14.** Prorrata: manual por ahora (importe introducido en la casilla 44); funcionalidad propia más adelante. Método de la hoja de Javier (`Calculo prorrata IVA <año>.xlsx`,
  sólo Empresa B, que tiene alquileres exentos): % de prorrata (celda C10, a mano) aplicado al IVA soportado de todo el año (E = D × %); casilla 44 = E total − soportado total
  + rectificación de deducciones (negativa = se deduce menos), que se lleva al 303 del 4T. Comprobado: da −1.050,08 € en 2022 (78 %) y −792,51 € en 2025 (80 %), igual a lo
  presentado. Según el PDF de prorrata (arts. 104-105 LIVA): el % provisional de cada año es el **definitivo del año anterior** (redondeado por exceso); en el 4T se calcula el % definitivo del año (operaciones con derecho a deducir / total, redondeado por exceso), se aplica al soportado del 4T y se regulariza (casilla 44, con signo menos) la deducción de los 3 primeros trimestres: soportado 1T-3T × (% provisional − % definitivo). Pendiente: la hoja 2025 aplica 80 % también al 4T y no usa el 47,18 % (48 %) que ella misma calcula; confirmar con el asesor si el 80 % es el definitivo de 2024 y si 2025 debe regularizarse con 48 % (diferencia estimada ≈ 1.289 €), y qué operaciones entran en el denominador.
- **D15.** El 303 se presenta siempre con compensación; las cuotas a compensar de los trimestres anteriores salen de lo presentado.
- **D16.** Pago de los modelos: domiciliación; NRC cuando no se llega a tiempo (303, 111, 202 y quizá 200).
- **D12.** ~~111~~ → el 111 se genera a partir de las **retenciones registradas en facturas recibidas**; normalmente no hay y sale
  "sin actividad". Alcance del Hito 3 para el 111: soportar retenciones por factura y generar el modelo, con el caso habitual
  "sin actividad" como prueba principal.

## 8. Hallazgos de las exportaciones del programa anterior (Empresa A, ejercicio 2026)

Ficheros en `docs/Exportaciones del programa anterior/` (excluidos de git: son datos fiscales reales).

| Fichero | Contenido | Utilidad para el Hito 2 |
|---|---|---|
| `Diario.xlsx` | 1.053 líneas, enero–septiembre 2026, columnas: Serie, Fecha, Asiento, Doble, Subcuenta, Nombre, Concepto, Debe, Haber | Verdad contable. **La columna Asiento viene siempre a 0**: el asiento hay que reconstruirlo por (Serie, Fecha) |
| `Mayor.xlsx` | 112 cuentas con saldo a 01/01 y movimientos | Control de saldos |
| `Facturas recibidas.xlsx` | Libro registro: documento, fecha fiscal, fecha factura, nº factura, cuenta, nombre, CIF, base, %IVA, cuota, %recargo, total; **una fila por tipo de IVA** | Detalle de IVA por factura |
| `Facturas emitidas.xlsx` | Igual (solo 1 factura en 2026) | Idem |

Observaciones:
1. **Enlace factura ↔ asiento:** el documento `2_194` del libro de facturas corresponde a la Serie `2.194` del Diario.
   Javier confirma que **Serie y Asiento son lo mismo** (identificador `tipo.número`); la columna "Asiento" del Excel no se usa.
   Por los datos de 2026, el primer número es el tipo de movimiento así: `1` facturas emitidas (3 líneas, `2026/01-UNIO FRUITS`),
   `2` facturas recibidas (178 asientos), `3` tesorería (233 asientos: bancos, compras con tarjeta), `4` general (resultado,
   liquidación de IVA 4T, limpieza de cuentas) y `9` automáticos (apertura del ejercicio, liquidaciones trimestrales de IVA).
   **Confirmado con la pantalla de tipos de asiento del programa anterior:** 1 Facturas expedidas, 2 Facturas recibidas, 3 Tesorería,
   4 General, 9 Asientos automáticos. Equivale a los tipos de MGD: `E`, `R`, `B`, `X` (más los automáticos).
2. **Descuadre real:** el Diario del programa anterior no cuadra. Todos los grupos (serie, fecha) cuadran salvo uno: `2.194`,
   factura de ITV de 40,95 € con base 30,38 + IVA 6,39 = 36,77. Causa (captura de pantalla del programa anterior): hay una tasa D.G.T.
   de 4,18 € fuera de base que no se contabilizó. El programa anterior dejó grabar la factura así.
   El sistema nuevo **no debe permitir** un asiento descuadrado (restricción de BD) y la importación debe señalar este tipo de casos.
2b. **Lo que enseña la pantalla "Introducción de facturas recibidas" del programa anterior** (requisitos para nuestro modelo de factura):
   - Fechas distintas: *fecha de introducción* (30/09, la fiscal/contable) y *fecha de factura* (08/09); más *periodo contable* y *documento*.
   - **IVA con dos líneas** por factura (base, %, cuota) y bloque de **retención** (tipo, base, %, cuota).
   - **Contrapartidas múltiples** (subcuenta de gasto + concepto + importe), más allá de base e IVA.
   - Bloque **"Pago factura"**: se registra el pago (subcuenta de banco, fecha, concepto, importe) al introducir la factura y
     genera su propio asiento (aquí el pago del 08/09 contra `55100002`). También hay pestaña de **Vencimientos**.
   - Imagen de la factura (PDF) al lado de los datos; "Ficha proveedor" y "Saldo a la fecha" del proveedor.
   - Menú del programa anterior como guía de módulos: Definiciones, Asientos (general, expedidas, recibidas, tesorería; cierre y apertura:
     grupos 8 y 9, existencias, amortización, P. y G., asiento IS, cierre, apertura), Importaciones, Cobros/Pagos, Listados,
     Liquidaciones, R. Mercantil, Impuesto de Sociedades, Procesos.
3. **Faltan datos** en estos Excel para sustituir el programa: no traen vencimientos, bancos ni retenciones/IRPF por factura.
   Javier añade `Bienes de Inversion.xlsx`: es un **informe de las amortizaciones ejecutadas** (59 líneas, 12 inmovilizados,
   ejercicios 2021–2025; fecha de generación, asiento `año.nº`, importe, nombre), **no la ficha del bien**. Falta coste, fecha de
   alta, vida útil, valor residual y cuentas (en MGD están en `Lbi`: 22 registros en 2021). Detalles útiles: la amortización de
   un año se regeneró varias veces (p. ej. 2023 se regeneró en febrero de 2026) y el bien nº 8 baja de 760,46 a 402,06 en 2024 y
   no aparece en 2025.
   **Pantalla "Elementos de inmovilizado" del programa anterior** (captura): código, subcuenta, descripción, fecha de funcionamiento,
   precio de compra, amortización contable, **amortización fiscal** (columna aparte, vacía hoy), valor neto contable y fecha de
   baja; filtros de amortizados/no amortizados, clasificación y "ficha de inmovilizado". Hay 12 elementos (el siguiente código
   libre es el 13). Los bienes 8, 9 y 11 están totalmente amortizados. Esto define el modelo de datos del bien de inversión y
   anticipa el Hito 5 (el modelo 200 necesita la diferencia entre amortización contable y fiscal). Falta pedir al programa anterior el
   listado "ficha de inmovilizado" (vida útil, valor residual, cuentas de amortización) para tener la ficha completa.
4. **Cuentas 7 → 8 dígitos:** **no hay regla única** (corregido tras ver los asientos automáticos de 2022 del programa anterior). En Empresa A el `0`
   se inserta tras el 4.º dígito (`2811000` → `28110000`) y en Empresa B tras el 3.º (`4108123` → `41008123`); en proveedores,
   clientes y bancos coinciden. Está en `migracion/cuentas.py` (`CERO_TRAS_POR_EMPRESA`) y contrastado por `tests/test_mapa_cuentas_programa_anterior.py`.
   Para años posteriores hará falta una tabla de equivalencias por empresa (Hito 2).
5. **Datos de Empresa B:** los ZIP `Copia EMPRESA B 2021 3T` (empresa 012) y `Copia EMPRESA A 2021 3T` (empresa 011) son
   **copias de Gestión MGD**, no exportaciones del programa anterior. La de Empresa A es la misma `BBDD 2021`. Incluyen los PDF de las facturas.
   Empresa B tiene 144 PDF frente a 49 de Empresa A.

### Ficha de inmovilizado del programa anterior (capturas del bien nº 1) y regla de amortización

**Ficha** (pestañas *Relación*, *Datos inmovilizado*, *Detalle amortización*):
- Generales: tipo de elemento (p. ej. "Edificios industriales"), clasificación (inmovilizado material), código y descripción, fotografía, observaciones.
- Compra: proveedor, fecha de adquisición, fecha de funcionamiento, nº de factura de compra, precio de compra, valor residual, valor del suelo, tipo (nuevo/usado).
- Amortización: método (lineal), periodicidad (anual), % anual, "aplicar incentivos fiscales", subcuenta del inmovilizado, de la amortización acumulada y del gasto/dotación (21100000 / 28110000 / 68100000 en el ejemplo).
- Baja: fecha, causa y "no amortizar en el ejercicio de baja". Resumen: valor neto contable y amortización acumulada.
- **Detalle**: por año, previsión (% e importe) y amortización contable realizada (importe, acumulada, valor neto, **nº de asiento** con formato `ejercicio.tipo.nº`, p. ej. `2021.9.6`: tipo 9 = automáticos).

**Regla verificada** (`tools/validar_amortizacion.py`, 12 bienes, acumulado a 2025):
- Cuota anual = precio × % anual, redondeada a 2 decimales (bien 1: 3.756,46 × 4 % = 150,26).
- Primer año prorrateado por días naturales desde la fecha de funcionamiento (bien 1: 64 días → 26,34).
- Último año = lo que falta hasta el precio (bien 1: 2046 → 123,88; la suma de la previsión da exactamente 3.756,46).
- Resultado (truncando el primer año): **9 de 12 bienes exactos al céntimo**; los otros 3 difieren por el redondeo del primer
  año (bienes 2 y 10: 0,01 €; bien 12, primer año en 2016, bisiesto: 0,23 €). Redondeando "half-up" salen 8 de 12. El redondeo
  exacto del programa anterior no está resuelto (el bien 1 se explica truncando y el bien 2 redondeando hacia arriba). Decisión provisional: los años ya contabilizados **se importan tal cual**
  (el Diario manda); la regla solo se usa para años futuros y la validación acepta ±0,01 €, con el bien 12 como caso a investigar.

## 9. Próximo paso propuesto

Arrancar el **Hito 0**: estructura del repositorio, cargador DBF y esquema objetivo. En paralelo, ir cerrando los
pseudocódigos de §5 empezando por cierre y regularización de IVA, que son los que más condicionan el diseño del
modelo de datos.

**Validación del cierre (2020):** con los `Diario.dbf` de 2020 (ejercicio cerrado en MGD) la regularización (R) y el cierre (Z) que genera el motor coinciden
línea a línea con los de MGD en Empresa A (14 y 31 líneas) y en Empresa B (18 y 32). `tools/validar_cierre_mgd.py` y `tests/test_cierre_mgd_2020.py`.
El *Balance de sumas y saldos 2020* del programa anterior (PDF) coincide con las sumas del Diario de MGD en las 33 cuentas de 3 dígitos de Empresa A y las 36 de Empresa B (`tools/comparar_balance_programa_anterior.py`, `tests/test_balance_programa_anterior_2020.py`).

**Informes (Hito 1):** `servicios/informes.py` — libro Diario, Mayor (con saldo anterior y saldo corrido; admite grupos), balance de sumas y saldos a 1–8 dígitos y libros de IVA emitidas/recibidas. Sólo lectura. Con los datos de 2021 el Mayor de cada cuenta cuadra con el balance, el balance con el Diario y la cuota del libro de IVA recibidas con los asientos de las facturas. Hallazgo: en Empresa A las facturas 56 y 57 (18/08/2021, 2,80 € y 4,50 €) llevan el IVA a la cuenta `47110604`, no a una 472.

**Exportación (Hito 1):** `exportacion/` define una `Tabla` neutra (columnas tipadas, filas, totales, notas) y la escribe en **Excel** (importes y fechas como valores reales, cabecera fija, autofiltro) y en **PDF** (A4 apaisado, cabecera repetida, importes `1.234,56`, número de página). `servicios/tablas_informes.py` convierte Diario, Mayor, balance y libros de IVA en `Tabla`. El mismo objeto servirá para el componente de listado web. Dependencias nuevas: `reportlab` (PDF) y `pypdf` (sólo para tests y herramientas de lectura). Los balances agrupados (1–3 dígitos) usan los nombres del catálogo PGC (`domain/pgc.py`: grupos y subgrupos escritos a mano; 310 cuentas de 3 dígitos generadas por `tools/generar_pgc.py` desde los «Listado de cuentas» de MGD, tomando la primera entrada de cada `XXX.0.0` y descartando las subcuentas propias de cada empresa). MGD conserva algún título del PGC antiguo (520 «Préstamos a corto plazo…» frente a «Deudas a corto plazo…» en el programa anterior).

## 9b. Hallazgos del respaldo del programa anterior (`C0002.SDB`, Empresa A, 2014–2026)

El respaldo del programa anterior **es una base SQLite estándar** (`SQLite format 3`, 5,1 MB, 1.264 páginas; los ficheros `.SDB` se abren con `sqlite3`, sin driver propietario).
No se versiona (datos fiscales y personales reales): se lee en modo sólo lectura desde fuera del repositorio. Las tablas se llaman `C<empresa 4 dígitos><nº de tabla 3 dígitos>`
(`C0002…` = empresa 2, Empresa A) y las columnas son abreviaturas de tres a seis letras; de las 275 tablas sólo 65 tienen datos.

| Tabla | Filas | Contenido | Para qué |
|---|---|---|---|
| `C0002020` | 13 | Ejercicios 2014–2026 (inicio, fin, cerrado `CER`, defecto `DEF`, nº de asientos de apertura/cierre/regularización) | Ejercicios y cierres |
| `C0002006` | 2.935 | **Cabeceras de asiento**: ejercicio `EJE`, serie `SER` (1 emitidas, 2 recibidas, 3 tesorería, 4 manual, 9 automático), `COD`, fecha, concepto, y en facturas: CIF, nombre, nº de factura, bases/% /cuotas de IVA (`BIVA1…`), total, `FECFAC`, `CLIPRO`… | Diario y facturas |
| `C0002007` | 7.976 | **Líneas de asiento** (`LIN`, cuenta a 8 dígitos, debe, haber, concepto, contrapartida) | Diario |
| `C0002415` | 924 | **Plan de cuentas con ficha**: 8 dígitos (`COD`), nombre, NIF, domicilio, teléfono… (152 con NIF; 222 en 400/410) | Cuentas y terceros |
| `C0002449` / `C0002411-13` | 648 / … | Plan de cuentas oficial, grupos y subgrupos | Catálogo PGC |
| `C0002027` / `C0002076` | 482 / 734 | **Vencimientos** (cuenta, fecha, importe, cobro/pago, `CONTA`) y **pagos** aplicados a cada uno | Tesorería |
| `C0002051` / `C0002052` | 12 / 252 | **Bienes de inversión** y su cuadro de amortización (cuentas `CUEIN2/CUEAM2/CUEDO2`, IVA de la compra, % , periodos) | Inmovilizado |
| `C0002012` | 1 | **Datos de la empresa** (`NOMEMP`, domicilio, CP, población, provincia, teléfono, `CIFEMP`, persona de contacto) y parámetros de IVA | Ficha de la empresa |
| `C0002033`, `C0002046`, `C0002267` | 2 / 2 / 4 | **Socios y administradores** (NIF, domicilio, % de participación, cargos, poder notarial, fechas) | Representante, Registro Mercantil |
| `C0002049` | 1 | Actividad (epígrafe/CNAE 0125, fecha de inicio, régimen de IVA) | Ficha de la empresa |
| `C0002440`, `C0002441`, `C0002444` | 22 / 69 / 664 | **Declaraciones de IVA** presentadas (periodos 2021-1T a 2026-3T), sus líneas y las facturas incluidas | Validar el 303 (Hito 3) |
| `C0002190/191`, `C0002425/426`, `C0002431` | 5 / 5 / 5 / 15 / 16 | Modelos 190, 347 y otros presentados | Validar 190 y 347 |
| `C0002021`–`C0002023` | 462 / 414 / 196 | Saldos por periodo y cuenta (debe/haber acumulados) | Control de saldos |

Comprobaciones hechas (sólo lectura): todos los ejercicios 2014–2025 cuadran (debe = haber) en cabeceras y en líneas; **2026 (hasta septiembre) está descuadrado 4,18 €** (cabeceras de la serie 2:
22.473,07 debe frente a 22.477,25 haber; líneas 495.090,12 frente a 495.094,30), así que hay un asiento descuadrado que la auditoría deberá señalar. Las cuentas ya vienen a 8 dígitos (no hay que convertir
MGD 7→8 desde 2022). El 2021 del programa anterior tiene más asientos que la copia de MGD que usamos (71 frente a 56 en facturas recibidas), así que la copia de MGD es anterior o parcial: para 2021 en adelante
la fuente buena es el programa anterior.

## 10. Backlog (ideas apuntadas, sin fecha)

**Backlog de la interfaz del Hito 1: terminado.** Decisiones sobre la contraseña de empresa (punto 2): se guarda sólo la *ruta* del `.pfx`; la contraseña se comprueba abriendo el certificado (como Verifactu), nunca se guarda y se mantiene en memoria por navegador y empresa (cookie de sesión) hasta «Cerrar la empresa» o parar el programa; una empresa sin certificado se abre sin contraseña; la base de datos **no** se cifra (pendiente de decidir si hace falta y qué pasa si se pierde el certificado).

Interfaz web del Hito 1: **completa** (cuentas, terceros, informes, facturas, asientos manuales, plantillas, tesorería, bienes de inversión,
liquidación del IVA, cierre y apertura del ejercicio y auditoría).

Añadido a petición del usuario (no es prioritario ahora):

1. ✅ **HECHO · Ficha de la empresa editable** desde la pantalla de selección de empresa. Son varios datos (razón social, NIF, domicilio,
   representante, actividad, datos registrales…) que se usarán en los envíos a la AEAT (Hito 4) y en el depósito de cuentas y la
   legalización de libros del Registro Mercantil (Hito 6). Hoy `Empresa` sólo guarda código, nombre y NIF: habrá que ampliar el modelo
   y decidir qué campos exige cada trámite antes de diseñar la pantalla.
2. ✅ **HECHO · Contraseña por empresa = contraseña de su certificado digital**, como en Verifactu. Pensamientos para cuando se aborde:
   - la contraseña no se guarda en claro ni en el repositorio ni en la base de datos; mejor pedirla al entrar en la empresa y
     mantenerla sólo en memoria de la sesión (o guardar únicamente lo necesario para comprobarla);
   - sirve a la vez para abrir la empresa y para firmar los envíos a la AEAT y al Registro, así que el certificado (`.pfx`) vive fuera
     del repositorio y de `datos_locales/` versionado (ya ignorado por git);
   - hace falta decidir si además cifra la base de datos de la empresa y qué pasa si se pierde la contraseña;
   - revisar cómo lo resuelve Verifactu para reutilizar el mismo mecanismo (el código de esa aplicación está en `D:\Proyectos\Claude_VERIFACTU`).

Backlog anotado el 27/10/2026 (sin orden fijado; se intercala con los hitos):

9. **Modelo 347 de la AEAT** (operaciones con terceros): implementarlo. Ya existen las marcas *no incluir en el 347* de la ficha de terceros y los libros de IVA; cae de
   forma natural dentro del Hito 3/4.
10. ✅ **HECHO (29/10/2026) · Detección de facturas duplicadas al dar de alta o editar**: `servicios/facturas.buscar_posible_duplicada` y el aviso del formulario (`web/facturas._aviso_de_duplicada`). Avisa, sin impedirlo: la factura no se graba hasta marcar «Grabar de todos modos». Reglas: mismo tercero y mismo número (en cualquier ejercicio de la empresa, sin distinguir mayúsculas ni espacios); en las **emitidas**, el mismo número con otro cliente en el mismo ejercicio (la numeración es propia y no se repite); y el mismo número y total con otro tercero (casi seguro la misma factura con el tercero mal elegido). Al editar no se vuelve a avisar si no cambian ni el número ni el tercero. **Corregido de paso (29/10/2026): el recargo de equivalencia.** Al probar las duplicadas se vio que el formulario aplicaba a toda línea nueva el recargo (5,20 % en el General 21 %) que el catálogo de tipos de IVA lleva de serie, aunque el tercero no estuviera en ese régimen, y pedía una cuenta de recargo. Ahora el recargo sólo se aplica si la ficha del tercero tiene marcado «Recargo de equivalencia»; al elegir tercero, sus líneas se ajustan. **Vencimientos del formulario de facturas (29/10/2026):** se quitó el «Repartir en N plazos, cada M meses», que no se usa; los vencimientos son líneas que se añaden con «＋ Vencimiento», y la línea nueva trae lo que falta para cuadrar con la factura y la fecha de la anterior (la suma debe coincidir con el total, como antes). La columna «Forma de pago» pasó a «Pago con» y lista los bancos y tarjetas de las cuentas 572, 551 y 521 (los de la tabla de bancos; un banco ya previsto en el vencimiento, aunque sea de otra cuenta, se conserva); se guarda en el banco previsto del vencimiento. De paso se corrigieron dos pérdidas: editar una factura borraba el banco previsto de sus vencimientos, y elegir banco en un vencimiento que sigue al total lo deshacía al recalcular. La forma de pago de la ficha del tercero se sigue respetando, pero ya no se elige aquí. Original del pendiente: **Detección de facturas duplicadas al dar de alta**: avisar (o impedir) cuando ya existe una factura con el mismo NIF/CIF del tercero y el mismo número de factura
    (hoy sólo hay aviso de justificantes duplicados). Aplicar tanto a recibidas como a emitidas y también al editar.
11. **Listados e informes nuevos** (pantalla, Excel y PDF como el resto):
    - Sumas y saldos (ya existe un balance de sumas y saldos: revisar qué falta respecto al del programa anterior, p. ej. por rango de fechas).
    - Saldos acumulados de un mes (1 al 12).
    - Facturación por cliente o proveedor para un rango de fechas.
    - Balance de situación por rango de fechas.
    - Pérdidas y ganancias por rango de fechas.
    - Balance oficial y PyG oficial (modelo del Registro Mercantil, normal/abreviado: se enlaza con el Hito 6).
    - Estado de cambios en el patrimonio neto de un año dado.
12. **Entorno de ejecución en Windows y Linux**: requisitos y dependencias (versión de Python, `requirements`/lock, instalación, arranque, rutas, el selector de ficheros
    usa `tkinter`, que en Linux es un paquete aparte), y un procedimiento de instalación documentado.
    **Windows, hecho (29/10/2026)**: `instalar.bat` (busca Python 3.11+, crea `.venv`, instala, comprueba e instala los iconos) y `docs/08_instalacion.md`; probado en un clon limpio con entorno nuevo (tests, arranque con datos vacíos, lanzador, icono). Falta Linux, el instalador sin Python y, sobre todo, el alta de empresa (punto 15) con importación de MGD: sin ella, un equipo nuevo arranca pero no puede crear empresas.
13. ✅ **HECHO · Copia de seguridad y restauración** (28/10/2026). Pantalla «Copias de seguridad» (menú Ejercicio) y `tools/copia_seguridad.py`. Una copia es un `.zip` por empresa con la base de datos (copia coherente por la API de SQLite, con la aplicación abierta), su carpeta del almacén de justificantes y un `manifest.json` con la huella SHA-256 de cada fichero y el recuento de las tablas principales; **se verifica al hacerla** (huellas, `integrity_check` de SQLite y recuento) y se descarta si falla. Se guardan en `datos_locales/copias` (o `CONTA_COPIAS`). **Restaurar** exige escribir RESTAURAR, vuelve a verificar la copia, comprueba que es de la misma empresa (código y NIF), hace antes una copia del estado actual (`…_antes_de_restaurar.zip`, para poder deshacer), y sustituye base y justificantes; si algo falla, todo queda como estaba. Descargar y borrar copias desde la pantalla. Aviso en pantalla: una copia en el mismo disco no protege de un fallo del disco; hay que copiar los `.zip` a otro sitio. Sigue pendiente decidir si se cifra la base y las copias.
14. **Ayuda del programa**: ayuda integrada (por pantalla y general).
15. **Añadir empresa (autónomo)**: alta de una empresa nueva desde la aplicación, incluido el caso de un autónomo (persona física: sin Impuesto sobre Sociedades, con
    modelos y obligaciones distintos). Hoy las empresas se crean con herramientas de línea de comandos.
    **Hecho el 29/10/2026, parte 1: dígitos de las subcuentas por empresa.** `Empresa.digitos_cuenta` (8 por defecto; entre 4 y 12) se fija al crear la empresa y ya no se cambia. Todo lo que daba por hecho 8 dígitos lo lee de la empresa: validación de altas y de asientos, siguiente cuenta libre de un grupo, auditoría de integridad, cuentas por defecto (IVA, gasto, pérdidas y beneficios del inmovilizado: los tres primeros dígitos del PGC y ceros), etiquetas y agrupaciones de los listados («Subcuentas (código completo)»). El cargador de MGD conserva los dígitos del plan de la copia (`digitos_del_plan`) salvo en Empresa A y Empresa B, que siguen pasando a 8. Comprobado cargando la copia de Empresa A como empresa nueva de 7 dígitos: 103 asientos, todas las pantallas sin error y balance, PyG y estado de cambios en el patrimonio neto idénticos a los de Empresa A a 8 dígitos. Falta la pantalla de alta, donde se elegirán los dígitos, y el asistente de importación de MGD.
    **Parte 2 (29/10/2026): `tools/importar_mgd.py`**, una herramienta genérica que crea una empresa desde un `.zip` o carpeta de MGD (`explorar_copia` propone año, número de empresa, nombre y dígitos; sin `--aplicar` sólo informa; nunca sustituye una empresa; no deja una a medias si falla). Es el germen del asistente de la pantalla de alta. **Parte 3 (29/10/2026): pantalla «Añadir empresa»** (`/empresa-nueva`, desde el inicio). Dos caminos: *empresa nueva* (`servicios/alta_empresa.crear_empresa_nueva`: una subcuenta por cada cuenta de tres dígitos del PGC más las 4700, 4709, 4730, 4750 y 4751, rellenas con ceros hasta los dígitos elegidos; parámetros PYG, IVA_DEBE, IVA_HABER y PTE_APLIC; ocho tipos de IVA con sus cuentas 472 y 477) y *desde una copia de MGD* (se sube el `.zip`, se examina y se enseña lo que contiene antes de crear nada; la copia subida se guarda en un temporal y se borra al confirmar o cancelar). Con certificado obligatorio se lleva a la ficha de la empresa para indicarlo. La herramienta de línea de órdenes usa el mismo servicio. **Hecho (29/10/2026): el tipo de plan.** `Empresa.tipo_plan` («pymes» o «esfl») se elige en el alta. El plan de **entidades sin fines lucrativos** sale de `domain/pgc_esfl.py`, generado por `tools/generar_pgc_esfl.py` desde el cuadro de cuentas en Excel de la ONG del amigo y el BOE (Resolución del ICAC de 26-3-2013, PGC de pequeñas y medianas entidades sin fines lucrativos): 354 cuentas de tres dígitos y 381 de cuatro, con el nombre del BOE donde el Excel tenía erratas. Los listados agrupados usan los nombres del plan de la empresa; el balance y la PyG «oficiales» y el estado de cambios en el patrimonio neto, que son los de PYMES, **avisan de que no corresponden** a una ONG en lugar de dar números equivocados. **Hecho (29/10/2026): balance y cuenta de resultados de la ONG** (`servicios/cuentas_anuales_esfl.py`, con el motor genérico de `cuentas_anuales`: `balance_con_modelo` y `resultados_con_modelo`). Las líneas y las cuentas de cada una son las del BOE (tercera parte, «Balance de PYMESFL» y «Cuenta de resultados de PYMESFL»); las pantallas «Balance oficial» y «Pérdidas y ganancias oficial» eligen el modelo por el plan de la empresa, y el estado de cambios en el patrimonio neto de PYMES avisa de que una ONG no lo tiene aparte (va en las secciones B a I de su cuenta de resultados). Se comprobó que todas las cuentas del cuadro, rellenas con ceros a 6, 7, 8 y 10 dígitos, caen en alguna línea, salvo la 137 (el BOE no la sitúa; sale como «sin asignar» para decidirlo con datos reales). **Supuestos míos, a confirmar con los estados reales de la ONG**: la 473 va con los deudores (el BOE la omite); la 678 y la 778 (excepcionales), con «Otros gastos de la actividad» (el modelo no tiene «Otros resultados»); la 795, con el exceso de provisiones; las cuentas padre 293-295 y 593-595, con las inversiones financieras; la 552, 554 y 556, con las deudas a corto plazo (la 552 según el signo). Las secciones B a H de la cuenta de resultados se obtienen del balance (este plan no usa los grupos 8 y 9): B y C, de la variación de la 130, 131 y 132 y de lo traspasado (745, 746, 748); G, de la variación de la dotación fundacional; H es lo que falta hasta I, la variación del patrimonio neto; E y F no se calculan. **Pendiente: validarlos** con la copia de MGD de la ONG y su balance y cuenta de resultados en PDF, y la memoria. Después, el modelo 200 de una entidad parcialmente exenta y las demás obligaciones, a confirmar con su asesor o con la AEAT (no hay fuente aún).
16. ➜ **Sustituido por el flujo trimestral completo (30/10/2026)**, diseñado en [09_flujo_trimestral.md](09_flujo_trimestral.md): extractos guardados, conciliación, líneas sin PDF, emitidas desde Verifactu, verificación banco = Mayor, asistente del trimestre y, al final, el reconocimiento de PDF. Objetivo: el 4T de 2026 entero en Conta. **Fase 1 hecha (30/10/2026): extractos y cuadre de cada banco con su Mayor** (ver §7 del documento). Original: **Importar facturas conciliadas con el banco desde Verifactu**: traer las facturas emitidas (y sus cobros) desde el programa de facturación; el Excel de conciliación ya
    se importa (Hito 2, `/importar`), falta decidir si se enlaza directamente con la base de Verifactu. Es clave para los cierres trimestrales.
17. **Seguimiento de los cambios de normativa y de modelos de la AEAT**: sobre todo el Impuesto sobre Sociedades (modelo 200) y el Registro Mercantil. Fuente de referencia:
    El programa anterior, que ya recoge los cambios. Enlaza con la comprobación de la versión del diseño de registro antes de cada envío (idea del Hito 3).

Pendientes de la interfaz anotados tras probar los listados (a hacer más adelante):

3. ✅ **HECHO · Cabeceras de los listados siempre visibles.** El scroll debe actuar sólo sobre los datos de la tabla; la cabecera (y el menú
   lateral, ya fijo) no se pierden. Hoy se desplaza toda la página y la cabecera de columnas queda pegada bajo la barra superior sólo
   mientras la tabla es más alta que la pantalla: conviene que la tabla tenga su propio contenedor con scroll vertical y altura ajustada
   a la ventana (y también en el diálogo de factura/asiento).
4. ✅ **HECHO · Número de cuenta automático al dar de alta un cliente o proveedor.** El programa propone la siguiente subcuenta libre del grupo
   (p. ej. `43000005` para el siguiente cliente, `41000231` para el siguiente acreedor) y crea la cuenta contable con el tercero.
5. ✅ **HECHO · Más datos en la ficha de clientes y proveedores** (campos del programa actual, el programa anterior):
   - Proveedor: NIF y tipo de identificador, nombre comercial, domicilio, código postal, población, provincia, país, teléfonos, correo,
     página web, observaciones, divisa; marcas *recargo de equivalencia*, *no incluir en 347*, *proveedor genérico*, *criterio de caja*,
     *REAGP (agricultura)*; **por defecto en facturas**: tipos de IVA (hasta tres), tipo de retención, % IVA deducible, tipo de operación,
     **subcuenta de gasto** y subcuenta de suplidos; **datos de pago**: pago directo en factura, subcuenta de pago por defecto, tipo de
     vencimiento, IBAN/CCC.
   - Cliente: los mismos datos generales (con *cliente genérico*), tipos de IVA y de retención por defecto, tipo de operación, tipo de
     exención de IVA, **subcuenta de ingreso** y de suplidos; **datos de cobro**: cobro directo en factura, subcuenta de cobro por
     defecto, tipo de vencimiento, IBAN/CCC.
   - Prioridad: al menos la subcuenta de gasto (proveedores) y la de ingreso (clientes), que además se usarán para proponer la cuenta
     en la factura. El resto sirve para el 347, el 303/390 y los pagos por banco.

6. **Vencimientos pendientes al migrar desde el programa anterior.** En la copia de MGD de 2021 quedan vencimientos pendientes y vencidos (ejercicio
   prescrito, datos de prueba). Cuando se migren los datos desde el programa anterior hay que revisar la cartera: en principio no debería quedar
   ninguno pendiente y, si queda alguno, será un dato por depurar (no un fallo del programa).
7. ✅ **HECHO · Editar a mano un periodo del cuadro de amortización** (importe previsto o contabilizado), como permitía MGD: el edificio de Empresa B
   tiene el primer periodo y los importes fijados a mano. Hoy se ven («importe fijado a mano») pero no se editan. Además, en ese edificio
   el periodo 2020 figura sin contabilizar mientras la apertura de 2021 recoge 18 periodos (2002–2019): conviene revisarlo al migrar.
8. ✅ **HECHO · Aclarar la pantalla de vencimientos** (dudas al usarla). Hay dos conceptos que no se entienden a primera vista y necesitan ayuda en
   pantalla (texto explicativo o desplegable):
   - **Compensar el pendiente**: salda el vencimiento *sin mover dinero por el banco*, contra otra cuenta. Se usa, por ejemplo, para
     cruzar una factura de un proveedor con una de un cliente que es la misma persona (en la cuenta se escribe la del otro lado, p. ej. la
     del cliente), o para saldar contra la cuenta corriente con socios. Si no es el caso, no se toca. Valorar ocultarlo tras un enlace
     «Otras formas de saldarlo» y poner ejemplos.
   - **Banco previsto**: el banco por el que se piensa cobrar o pagar; es sólo informativo (sale en la cartera y sirve para planificar la
     tesorería) y no genera ningún asiento. Al registrar el cobro o el pago se propone ese banco. Aclarar el rótulo («Banco previsto para
     el cobro/pago») y valorar rellenarlo por defecto con el banco habitual del tercero.

