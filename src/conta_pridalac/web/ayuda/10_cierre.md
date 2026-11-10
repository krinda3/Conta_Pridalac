# Cierre del ejercicio y control

Esta caja (**Ejercicio**) reúne lo que garantiza que la contabilidad es correcta y que no se pierde. Lo que mantiene al día el programa y las normas (**Programa** y **Normativa y diseños**) no es de una empresa: está en la **pantalla de empresas**, la primera que se ve al abrir Conta, y se explica al final de este tema.

## Cierre y reapertura del ejercicio

[Cierre del ejercicio](pantalla:ejercicios) lista los ejercicios de la empresa. Doble clic en uno abre su **lista de comprobación previa al cierre**: la auditoría, el IVA, las amortizaciones y la cartera de vencimientos, más el **resultado provisional**.

- **Cerrar el ejercicio** hace cuatro cosas: **regulariza** los ingresos y gastos (los lleva a la cuenta de pérdidas y ganancias), crea el **asiento de cierre**, **abre el ejercicio siguiente** con sus asientos de apertura (se puede desmarcar) y marca el ejercicio como cerrado.
- **El cierre exige una auditoría sin errores.** Los avisos no lo impiden, pero conviene mirarlos.
- Un ejercicio **cerrado no admite cambios**: facturas, asientos y banco quedan bloqueados.
- **Reabrir** deshace el cierre completo: borra el asiento de cierre, la regularización y la apertura del ejercicio siguiente (solo si éste no tiene más movimientos que su apertura). Al volver a cerrar se regulariza de nuevo con lo que haya.
- **Nuevo ejercicio** crea uno vacío cuando hace falta (por ejemplo, el primero de una empresa).

> **Cierre solo cuando todo esté presentado.** Cerrar un ejercicio y reabrirlo queda anotado en el registro de cambios, así que no es peligroso, pero evite reabrir uno ya presentado: los modelos que usted presentó dejarían de coincidir con los libros.

## Auditoría de integridad

[Auditoría de integridad](pantalla:auditoria) comprueba que la contabilidad es coherente. Doble clic en un hallazgo para ver **qué significa y cómo se corrige**.

- Los **errores** son incoherencias reales (un asiento descuadrado, un asiento generado que no coincide con su factura, una cadena del registro de cambios rota…): impiden cerrar el ejercicio y conviene arreglarlos antes de presentar nada.
- Los **avisos** son cosas que conviene revisar (un gasto sin justificante, un plazo próximo, una normativa por revisar…): no impiden nada.
- La auditoría incluye también la **vigilancia de plazos** de los modelos, del depósito de cuentas y de la legalización de libros.

Esta es la lista completa de lo que comprueba:

@@AUDITORIA@@

## Copias de seguridad

[Copias de seguridad](pantalla:copias) copia la base de datos de la empresa y sus documentos, y **la verifica al hacerla** (huellas, integridad de la base y recuento de registros).

### Copia ligera y copia completa

Los PDF de las **facturas** son casi todo el espacio (centenares de MB) y **no cambian nunca**; además, ya están en sus carpetas de trimestre. Por eso la copia normal es **ligera** y pesa unos pocos MB:

- **Lleva** la base de datos y todo lo que no se puede conseguir de otro sitio: las declaraciones y los acuses de la sede, los libros, el depósito de cuentas, los ficheros de los modelos y los justificantes de bancos y asientos.
- **De los PDF de facturas solo lleva su huella** (una lista con el código de cada uno), no los ficheros.
- La **copia completa** (casilla «Copia completa» al hacerla) los lleva también. Úsela de vez en cuando para un disco externo; pesa cientos de MB.

### Qué se puede hacer

- **Hacer una copia ahora**: crea el `.zip` en la carpeta de copias (ligera, salvo que marque la casilla).
- **Verificar una copia**: la vuelve a comprobar y dice si es ligera o completa.
- **Restaurar una copia…**: sustituye la base actual por la de la copia. **Pide que escriba `RESTAURAR`** como confirmación y, antes de tocar nada, **hace una copia de lo que hay** (aparece como «Antes de restaurar»), por si se equivoca. **Restaurar nunca borra un PDF de factura**: solo añade o repone.
- **Recuperar justificantes…**: si faltan PDF de facturas en el almacén (por ejemplo, tras restaurar en otro equipo), indique las carpetas donde están (una por línea; por ejemplo, la de su OneDrive con las facturas). El programa los busca **por su contenido**, así que no importa cómo se llamen ni en qué subcarpeta estén, y los copia donde los espera. No toca nada de esas carpetas.
- Doble clic en una copia: su contenido, su tipo y **Descargar la copia**.

Al terminar el trimestre, el botón **Copia de seguridad en OneDrive** (en [Trimestre](pantalla:trimestre)) hace la copia, la verifica, la lleva a la carpeta de la ficha de la empresa y allí **vuelve a verificarla**. Como es ligera, en OneDrive ocupa pocos MB y se sube en segundos.

> **Cuándo:** al terminar cada trimestre, antes de cerrar un ejercicio y antes de restaurar nada. Una copia en el mismo disco no protege de un fallo del disco: lleve los `.zip` a otro sitio.

> **Los PDF de las facturas** no van en la copia normal: manténgalos donde ya los guarda (sus carpetas de trimestre). Si los perdiera, «Recuperar justificantes» los repone desde allí.

## Registro de cambios

El programa guarda **todo lo que se da de alta, se cambia o se borra** en los datos contables, con su fecha y el usuario, y lo que valía antes y después. Es el [Registro de cambios](pantalla:registro-cambios), de solo lectura.

Está pensado para que **nada se pueda alterar sin que quede rastro**, como exige la ley antifraude (artículo 29.2.j de la Ley General Tributaria):

- Cada anotación lleva una **huella** que depende de la anterior (una cadena): si alguien retoca el registro, la cadena se rompe y la auditoría lo avisa con un **error**.
- Las huellas se guardan **también fuera de la base de datos** (un fichero en la carpeta de justificantes y la copia de OneDrive), así que no basta con reescribir la base.
- Al hacer una copia, restaurar, registrar una presentación o cerrar y reabrir un ejercicio se añade una línea a ese fichero.

**Límites que conviene saber:** no se anota lo que se escribe con herramientas ajenas al programa (SQL directo), y copiar el fichero de la base a mano (sin usar la pantalla de copias) rompe la comprobación: la auditoría lo marca como error, y es lo esperado. No hay usuarios ni contraseñas propias: el usuario es el del sistema.

## Normativa y diseños

[Normativa y diseños](pantalla:normativa), que se abre desde la **pantalla de empresas** (no es de una empresa: vale para todas), controla de qué normas depende el programa para que no se quede desactualizado. Cada una (los **diseños de registro** de los modelos 200, 202, 303, 390, 190, 347 y 111; el **calendario de plazos**; el **depósito de cuentas (D2)**; la **legalización (Legalia2)**; y el **plan contable**) tiene la versión con la que está implementada y la **época del año en que suele salir lo nuevo**.

- Cuando llega esa época y nadie la ha marcado como revisada, la fila sale **«Por revisar»** y aparece un aviso en la [Auditoría](pantalla:auditoria).
- **Consultar la sede** pregunta a la AEAT, sin descargar nada y sin enviar datos, si el diseño de un modelo **ha cambiado** o si **ya existe el del ejercicio siguiente**. Funciona con los modelos 200, 202, 303 y 390; para los demás solo hay el aviso por calendario.
- Para el **depósito de cuentas (D2)**, «Consultar la sede» mira también el **BOE** (abril a julio): si se publica la resolución con los modelos de cuentas anuales del año, sale como novedad con su enlace y un aviso en la auditoría, hasta que se marque como revisada. La primera consulta tarda unos segundos.
- Doble clic en una fila: qué hacer si hay cambios y **Marcar como revisada hoy**, que apaga el aviso hasta la época del año siguiente.

Cuando un diseño cambia, el procedimiento es: bajarlo, comparar con el anterior (hay una herramienta que lista las casillas que cambian), adaptar el generador, comprobarlo en la sede y marcar la fuente como revisada. Para que el cambio llegue a los demás equipos, se actualiza el programa desde [Programa](pantalla:programa).

## Programa y actualizaciones

[Programa](pantalla:programa), en la **pantalla de empresas** (vale para toda la instalación), enseña qué versión de Conta hay instalada en este equipo y permite ponerla al día.

- **Buscar actualizaciones** pregunta a GitHub si hay cambios nuevos y los lista. No cambia nada.
- **Actualizar ahora…** muestra los cambios y pide confirmación. Antes de descargar hace una **copia de seguridad ligera de cada empresa** (si falla alguna, no se actualiza). Después hay que **cerrar el programa y volver a abrirlo**; las bases añaden solas lo que necesiten. **Los datos no se tocan.**
- Es así como llegan a este equipo las novedades, por ejemplo un diseño nuevo de un modelo de la AEAT que ya se haya adaptado (véase [Normativa y diseños](pantalla:normativa)).
- **Hace falta** que el programa esté instalado con `git clone` (no copiando la carpeta), que git esté instalado y que el equipo tenga acceso al repositorio de GitHub. Si no, la pantalla dice qué falta.
- Se niega a actualizar si hay ficheros del programa modificados a mano en ese equipo: avise a quien lo mantiene.

## Copia de ensayo

Una **copia de ensayo** es una copia de la contabilidad marcada de forma **irreversible** para poder practicar sin riesgo: sale un aviso naranja en todas las pantallas y **no permite generar ficheros para la sede ni registrar presentaciones**. Sirve para probar el flujo del trimestre antes de hacerlo de verdad. La contabilidad oficial de cada empresa es única: no hay una segunda.

Una copia se marca como ensayo con la herramienta `tools/marcar_ensayo.py` y se abre con la variable `CONTA_DATOS` apuntando a su carpeta (y otro puerto, para no confundirla con la real).
