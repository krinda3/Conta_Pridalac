# Primeros pasos

Conta Pridalac es el programa de contabilidad de la empresa. Lleva los asientos, las facturas y los bancos; prepara los modelos para la Agencia Tributaria (AEAT: 303, 111, 190, 347, 390, 202 y 200) y los libros y las cuentas anuales para el Registro Mercantil.

> **Lo más importante:** el programa **no envía nada por su cuenta** a la AEAT ni al Registro Mercantil. Prepara el fichero, usted lo sube con su certificado digital en la sede (o en D2 y Legalia2, para el Registro) y después registra aquí lo que presentó.

## Cómo se abre y se cierra

1. Abra **Conta Pridalac** con el icono del escritorio. Se arranca solo y abre el navegador en `http://127.0.0.1:8000`.
2. Para **cerrar**, pulse el botón de apagado (arriba a la derecha) o simplemente cierre la última pestaña del navegador: el programa se apaga solo.
3. Si el icono no hace nada, es que ya está abierto (busque la pestaña) o que hay que repetir la instalación: [Instalación en otro equipo](tema:empezar#instalacion-en-otro-equipo).

Los datos **no salen del equipo**: la dirección `127.0.0.1` es la del propio ordenador. Solo hay tres casos en que el programa se conecta a internet, y en ninguno envía datos: «Consultar la sede» en [Normativa y diseños](tema:cierre#normativa-y-disenos) (pregunta a la AEAT y al BOE si han cambiado sus diseños), «Buscar actualizaciones» y «Actualizar» en [Programa](tema:cierre#programa-y-actualizaciones) (hablan con GitHub) y la instalación.

## Empresas, certificado y ejercicio

- En la pantalla de inicio salen las **empresas**. Cada una tiene su propia base de datos. Al crearla (y después, en su ficha) se elige su **protección de acceso**: **sin protección** (se abre directamente) o **con certificado digital**, y entonces se abre con la **contraseña de su certificado** (el `.pfx` que se indica en la ficha). Es una barrera de pantalla para que no entre cualquiera desde ese navegador, no un cifrado de los datos: para protegerlos de verdad, cifre el disco.
- Dentro de una empresa, el selector **Ejercicio** (arriba) cambia de año. Un ejercicio **cerrado** no se puede modificar; para tocarlo hay que reabrirlo desde [Cierre del ejercicio](tema:cierre#cierre-y-reapertura-del-ejercicio).
- El nombre de la empresa (arriba) abre su **ficha**: datos fiscales, Registro Mercantil, presentador, actividades, representantes con poder, carpetas de copias, **modelos que presenta** y protección de acceso con certificado. Muchos modelos leen datos de aquí: conviene tenerla completa.

## Moverse por el programa

- El **menú** está en cajas (Trimestre, Facturas, Tesorería, Asientos…). Al pulsar una caja salen sus pantallas. El botón de la barra cambia la disposición (debajo de las pestañas o en columna a la izquierda), y el de al lado el tema (claro, oscuro o automático).
- La **pantalla de inicio de cada empresa** muestra los plazos de los modelos que corren y lo que queda por hacer.
- En casi todas las listas: la **lupa** filtra, pulsar el título de una columna **ordena**, **doble clic** en una fila la abre, y los botones **PDF** y **Excel** exportan lo que se ve.
- El botón **?** (arriba, junto al de apagar) abre esta ayuda en el tema de la pantalla en que está.
- Los mensajes verdes y rojos que aparecen abajo a la derecha son el resultado de la última acción; los rojos dicen por qué no se pudo hacer.

## Por dónde empezar cada trimestre

Si es su primer día con el programa, vaya al tema [El cierre del trimestre](tema:trimestre): es el orden de trabajo normal, paso a paso, y la caja **Trimestre** lo va marcando sola («Hecho», «Pendiente», «Revisar»).

## Dónde están los datos y cómo no perderlos

Todo lo del usuario está en la carpeta `datos_locales` dentro de la carpeta del programa:

| Qué | Dónde |
|---|---|
| La contabilidad de cada empresa | `datos_locales\bd\<empresa>.sqlite` |
| Facturas y otros documentos adjuntos | `datos_locales\justificantes\` |
| Copias de seguridad | `datos_locales\copias\` |
| Tema, menú y revisiones de normativa | `datos_locales\bd\_preferencias.json` y `_normativa.json` |

> **Importante:** una copia de seguridad en el mismo disco no protege de un fallo del disco. Haga la copia desde **Ejercicio → Copias de seguridad** y lleve los `.zip` a otro sitio (la ficha de la empresa permite indicar una carpeta de OneDrive y el programa la copia allí al terminar el trimestre). La copia normal es **ligera** (unos pocos MB: no lleva los PDF de las facturas, que ya están en sus carpetas de trimestre). Cómo: [Copias de seguridad](tema:cierre#copias-de-seguridad).

### Cambiar la carpeta de datos y usarla desde varios equipos

La carpeta de datos no está fija: en la pantalla de empresas, la tarjeta **[Carpeta de datos](pantalla:datos)** dice cuál es y permite:

- **Usar otra carpeta que ya tiene datos** (por ejemplo, la de otro equipo en un disco externo o en una carpeta sincronizada, o una que se movió de sitio). No copia ni borra nada: sólo cambia cuál se usa.
- **Mover los datos a otra carpeta vacía o nueva.** Copia todo, **comprueba que la copia es idéntica** (integridad de cada base y huella de cada fichero) y sólo entonces pasa a usarla. La carpeta antigua **no se borra**: queda con una nota (`MOVIDO_A.txt`). Mientras copia, el programa se bloquea para que nadie escriba en lo que se copia.

Si al abrir Conta no encuentra los datos en la carpeta que tiene configurada (una unidad externa o de red desconectada, una carpeta movida), **no ofrece crear una empresa**: pregunta *«¿dónde están sus datos?»* y deja elegir la carpeta, reintentar o empezar con datos nuevos.

Si la carpeta de datos se **sincroniza** (Drive, OneDrive, Dropbox) o está en **red**, hay que saber dos cosas:

- **Un solo equipo a la vez.** Conta pone un **candado** en la carpeta (`conta.lock`) y renueva su señal mientras está abierto. Si otro equipo lo tiene, no se abre: sale una pantalla que dice quién lo tiene y desde cuándo, con **Reintentar** y **Forzar**.
- **Forzar** sólo si de verdad quedó pillado (se apagó el otro equipo, se fue la luz): hay que escribir FORZAR. Si el otro equipo seguía abierto, se bloquea solo al darse cuenta, pero lo que escribiera mientras tanto se puede perder.
- **Cierre Conta antes de cambiar de equipo y espere a que termine la sincronización**: el candado y las bases tardan en llegar al otro ordenador, y por eso el candado **no es perfecto**. En Drive, use «Mantener los archivos sin conexión» (no «Transmitir»). Si aparecen ficheros «copia en conflicto» junto a las bases, no los borre.

## Instalación en otro equipo

1. Hace falta **Windows 10 u 11** y **Python 3.11 o superior** (de python.org, marcando «Add python.exe to PATH»). Un navegador cualquiera.
2. Copie la carpeta del programa al equipo (mejor una ruta sin espacios ni acentos, por ejemplo `C:\ContaPridalac`).
3. Doble clic en **`instalar.bat`**: crea el entorno, instala lo necesario y deja el icono en el escritorio. Se puede repetir sin problema (hay que hacerlo si se cambia la carpeta de sitio).
4. Para llevar los datos de un equipo a otro, haga una copia de seguridad en el primero y restáurela en el segundo.

Si algo falla, la ventana no se cierra: copie sus mensajes. El registro del programa queda en `datos_locales\web.log`.

## Crear una empresa nueva

En la pantalla de inicio, **Añadir empresa**. Hay dos caminos: una **empresa nueva** (vacía, con el plan de cuentas de PYMES o el de entidades sin fines lucrativos, los tipos de IVA habituales y las cuentas que el programa necesita) o **desde una copia de Gestión MGD** (sube el `.zip` y el programa enseña lo que contiene antes de crear nada). Después hay que completar su ficha y el certificado.
