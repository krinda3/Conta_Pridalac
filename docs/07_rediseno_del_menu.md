# Rediseño del menú

**Hecho el 29/10/2026** (primera versión): banda de pestañas con las cajas, siempre visible bajo la barra superior, que abre las opciones de la caja elegida (ver «Estado» al final). Aquí se guardan lo que se decidió y la estructura del menú del programa anterior, que sirve de referencia (capturas del 29/10/2026).

## Lo que quiere el usuario

- **No perder las explicaciones que se ven bajo cada opción**: cada opción del menú enseña su título y, debajo, para qué sirve (la descripción completa del listado o, en los modelos de la AEAT, un texto propio). Es una condición de cualquier rediseño futuro.
- Las cajas del panel (Facturas, Tesorería, Asientos, Inmovilizado, Datos, Contabilidad, Listados, IVA, Modelos de la AEAT, Registro Mercantil, Ejercicio…) **se expanden al pulsar en una banda con los títulos de las cajas**, como las pestañas del programa anterior: una banda de títulos y, debajo, el contenido de la caja elegida.
- **Todos los listados juntos** en una sola caja «Listados» (ya existe: facturación por cliente o proveedor, sumas y saldos, saldos acumulados, balance de situación, PyG, balance y PyG oficiales y estado de cambios en el patrimonio neto; faltan los que se vayan añadiendo, p. ej. diario y mayor si se quieren ahí).
- Las pestañas de **Impuesto sobre Sociedades** y de **Registro Mercantil** del programa anterior indican cómo habrá que organizar el modelo 200 y el depósito de cuentas (ver más abajo).

## Menú del programa anterior (2026.9 «Contabilidad», versión SaaS Profesional)

Doce pestañas; cada una con grupos de botones.

- **Definiciones**. Empresas: Gestión, Datos empresa, Parámetros · Tablas y ficheros: Periodos contables, I.V.A./retención, Conceptos de asientos · Plan de cuentas: Subcuentas, Tesorería, Existencias, Inmovilizado, Bienes usados · Listados: Bienes usados, Clientes/proveedores · Configuración: Cuentas anuales, Grupos 8 y 9, Predefinidos, Divisas · Agenda.
- **Asientos**. Apuntes de diario: General, Expedidas, Recibidas, Tesorería, Predefinidos · Cierre y apertura: Grupos 8 y 9, Amortización, P. y G., Existencias, Asiento IS, Cierre, Apertura · Utilidades: Borrado, Búsqueda, Digitalización.
- **Importaciones**. Nóminas (parámetros, retenciones, nóminas) · Facturación (parámetros, borrar enlace, contabilizar) · Importación desde fichero: Facturas, Asientos, Balances, Subcuentas, Asientos TXT.
- **Cobros / Pagos**. Vencimientos: Modalidad de pago, Tipos · Cobros: Manuales, Listado, Validación · Pagos: Manuales, Listado, Validación · Gestión de documentos de pago: Agrupar, Desagrupar, Documentos, Remesas.
- **Listados**. Diario: Detallado, Resumido · Generales: I.V.A., Sumas y saldos, Facturación, Balance, Mayor, Acumulados, Retenciones, P. y G. · **Estados contables PYMES**: Balance oficial, Balance detallado, P. y G. oficial, P. y G. detallado, ECPN · Otros planes: Configuración, Impresión, Detallado · Libros registro: E-Facturas expedidas, R-Facturas recibidas, Suplidos.
- **Liquidaciones**. Configuración: Parámetros · Declaraciones periódicas: 111, 202, 303, envío por lotes · Declaraciones informativas: 190, 347, 349, 390 · Gestión N.R.C.: Petición, Recepción.
- **Utilidades**. Gráficas: Análisis contable, Balance, P. y G., Saldos acumulados · Conciliación: Extracto, Automática, Listado, Manual · Procesos entre contabilidades: Asientos, Subcuentas, Consolidación · Generales: Dígitos del plan, Renumerar, Búsqueda de errores, Facturas duplicadas, Cambio de subcuentas, Bloquear movimientos.
- **R. Mercantil**. Configuración: Datos de cierre, Certificación, Memoria · Anexos de memoria: Inmovilizado, Activos financieros, Pasivos financieros, Partes vinculadas · Actas: Introducción, Libro de actas · Obligaciones mercantiles: Legalización de libros, Depósito de cuentas.
- **Impuesto Sociedades**. Liquidación: Caracteres, Datos de cierre, Correcciones, Retenciones y pagos, Titularidad real · Datos interanuales: Compensación de bases, Reinversión de beneficio, Donativos SFL · Deducciones: Incentivo de actividades, D.I. cooperativas, D.I. U.T.E., D.I. interna/internacional, Bonificaciones UTE · Información detalle: Calcular RIC/RIB, Detalle RIC/RIB, Establecimiento extranjero, Grupos de sociedades, No residentes, Partícipe UTE · Impuesto Sociedades: Precálculo, Modelo 200, Listado de control.
- **Procesos**. Utilidades del sistema: Informes, Asistencia remota, N.I.F. · Copias de seguridad: Realizar, Restaurar · Configuración: Puesto, Favoritos · Información: Acerca de · Programa: Novedades, Ampliaciones.
- **Favoritos**. Los accesos que el usuario elige (en su caso: Gestión de empresas, Datos empresa, Balance, Introducción de asientos, Facturas expedidas y recibidas, Tesorería, Diario, Mayor, I.V.A., Sumas y saldos, Búsqueda de asientos, Balance y P. y G. de PYMES, Búsqueda de errores).

## Lo que enseñan las pestañas de Impuesto sobre Sociedades y de Registro Mercantil

**Modelo 200** (cuando se haga): hay que prever, además del cálculo, estos bloques de datos: *caracteres* de la entidad, *datos de cierre*, *correcciones* al resultado contable (ajustes extracontables), *retenciones y pagos a cuenta*, *titularidad real*, *compensación de bases imponibles negativas*, *reserva de nivelación / reinversión*, *deducciones* y *bonificaciones*, un **precálculo**, el propio modelo y un **listado de control**. El pago fraccionado (202) está en Liquidaciones.

**Registro Mercantil**: *datos de cierre*, *certificación* (de aprobación de cuentas), *memoria* con sus anexos (inmovilizado, activos financieros, pasivos financieros, partes vinculadas), *actas* (libro de actas), *legalización de libros* y *depósito de cuentas*. El balance, la PyG y el estado de cambios en el patrimonio neto de PYMES, que ya tenemos, son la base del depósito.

## Ideas para el diseño

- Banda de títulos de caja, siempre visible; al elegir una, se muestra su contenido; recordar la última abierta.
- ~~Caja de **Favoritos**~~: descartada, el usuario no la usa en el programa anterior.
- Agrupar por tarea y no por tabla: «Liquidaciones» (modelos periódicos e informativos), «Impuesto sobre Sociedades», «Registro Mercantil», «Listados», «Procesos».
- Hoy hay un panel con tarjetas (`panel.html`); se rehace sobre la misma lista de grupos (`GRUPOS_DE_MENU` en `web/definiciones.py`) y la sección de modelos de la AEAT, que está escrita a mano en la plantilla.

## Estado (29/10/2026)

- **Una sola estructura**: `CAJAS` en `web/definiciones.py` (id, título y entradas; una entrada es un listado, un listado con otro título, sus pantallas hermanas y otra descripción, o «~título|descripción» si todavía no está) y `construir_menu`/`caja_de` que la resuelven con los listados. Las plantillas `_menu.html` (banda y cajas), `base.html` (la incluye en todas las pantallas de una empresa) y `panel.html` (el inicio ya no repite las tarjetas) la usan; el comportamiento está en `app.js` y los estilos en `app.css`.
- **Cajas** (en este orden): Facturas, Tesorería, Asientos, Inmovilizado, Datos, Listados (todos los listados juntos, incluidos diario, mayor y los libros de IVA), Liquidaciones (liquidación del IVA, 303, 111, 190, 347 y, aún sin hacer, 202 y 390), Impuesto sobre Sociedades (200, sin hacer), Registro Mercantil (legalización de libros y depósito de cuentas, sin hacer) y Ejercicio (cierre, auditoría y copias). Cada opción es una tarjeta con su título y su explicación debajo; lo que no está se ve en gris con borde discontinuo, sin enlace y con «(próximamente)».
- **Comportamiento**: en la pantalla de una opción se abre su caja y la opción sale resaltada (las declaraciones presentadas de un modelo abren la caja de su modelo); pulsar una pestaña abre su caja y pulsarla otra vez la cierra; en el inicio se abre la última caja usada (se recuerda en el navegador).
- **Disposición** (botón «Opciones debajo / Opciones a la izquierda» de la barra, que se recuerda como el tema: no en el navegador, que puede borrar sus datos al cerrarse, sino en `datos_locales/bd/_preferencias.json` vía `POST /_preferencias`; lo mismo vale para el tema y la última caja abierta): la banda de pestañas va siempre arriba; las opciones de la pestaña abierta salen *debajo* de la banda, en rejilla, o en una *columna fija a la izquierda* (21 rem, una opción por fila) que deja todo el ancho al listado. En pantallas de menos de 800 px siempre van debajo. El servidor la pone en `<html data-menu>` al servir la página y el cuerpo va dentro de un `.marco`.
- **Pendiente**: repartir mejor las cajas cuando haya más contenido (Impuesto sobre Sociedades y Registro Mercantil, con los bloques de datos que enseñan las pestañas del programa anterior). El modelo 220, que citó el usuario, no está en el menú.
