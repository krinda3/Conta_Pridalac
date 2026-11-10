# 04 · Justificantes (adjuntos PDF/JPG) en Gestión MGD

Origen: `clJustificantes` (`D_Comun.prg:13927…14219`: `LeeDatos`, `Graba`, `Nuevo`, `MenuEjecuta`). Tabla `Etidat`.
Verificado con las copias de Empresa A (empresa 011) y Empresa B (empresa 012) de 2021 (`tests/test_adjuntos_2021.py`).

## 1. Cómo guarda MGD los justificantes

- Los ficheros viven en una carpeta `<base>\Justificantes\` con nombre `EEE_T_NNNNN_<nombre original>` donde `EEE` es la empresa
  (011, 012), `T` el tipo de documento (`R` recibida, `E` emitida, `B` movimiento de banco, `X` extra) y `NNNNN` un **contador
  propio** por empresa y tipo (fichero `EEE_T_Control.num`), **no** el número de la factura.
- El enlace con el documento está en la tabla **`Etidat`** (`TIPO`, `NUMERO` = nº interno del documento, `CLAVE` = `"?"`, `TEXTO` 64):
  la lista de ficheros del documento se une con `;` y se **trocea en bloques de 64 caracteres**, una fila por bloque.
- Al leer: se concatenan los bloques del documento recortando los espacios finales de cada bloque (`Trim`), se separa por `;` y
  **se descartan los ficheros que no existen** en la carpeta.
- Por eso el número del nombre del PDF no sirve para localizar la factura (no coincide con `Rec.NUMERO` ni con `Rec.CNUMERO`:
  se probó en las dos empresas); hay que pasar por `Etidat`.

## 2. Cifras de 2021

| | Empresa A | Empresa B |
|---|---:|---:|
| Documentos con justificantes | 53 | 154 |
| Referencias a ficheros (tras recomponer) | 56 | 162 |
| Ficheros presentes en la copia | 49 | 144 |
| Referencias a ficheros que **ya no están** | 7 | 18 |
| Ficheros sin referencia (huérfanos) | 0 | 0 |
| Tipos | R 56 · E 1 | R · E (20) · B (1) · X (1) |

Los ficheros que faltan (p. ej. los 4 PDF de Renfe del documento nº 18 de Empresa A) están en `Etidat` pero no en la copia de
seguridad: MGD simplemente los ignora al mostrarlos. En el sistema nuevo se importan **marcados como no presentes** y la
auditoría de integridad los lista. Varios nombres traen el prefijo repetido (`012_R_00118_012_R_00005_…`): son copias de
justificantes ya adjuntados que se volvieron a adjuntar.

## 3. Modelo nuevo

`Adjunto` cuelga de **exactamente uno** de: factura, movimiento de banco, asiento (restricción `CHECK` en base de datos).
Guarda nombre, ruta relativa, tipo (PDF o JPG), huella SHA-256 y tamaño; `sha256`/`tamano` nulos = fichero ausente.
El almacenamiento en disco por empresa y ejercicio (con copia al subir) es trabajo del Hito 1.

## 4. Trampas encontradas

- Los ZIP creados en Windows guardan los nombres en codificación MS-DOS (cp437) sin la marca UTF-8: un `ó` aparece como `≤`.
  Para extraerlos hay que reinterpretar el nombre (`cp437` → `cp1252`).
- Hay nombres legítimos terminados en `..pdf` (`aparcto..pdf`). Un filtro de seguridad contra `..` mal planteado los descarta.
  La protección correcta contra el recorrido de rutas es rechazar los separadores `/` y `\` o un nombre igual a `..`.
- El `Trim` por bloque puede perder un espacio que caiga justo en el límite de 64 caracteres; MGD lo sufre igual.

## 5. Para el sistema nuevo (Hito 1)

- Subir PDF/JPG a una factura (recibida o emitida), un movimiento de banco o un asiento; verlos junto a los datos; sustituir y quitar.
- Guardar con huella y no permitir duplicados idénticos en el mismo documento (aviso, no error).
- Auditoría: adjuntos cuyo fichero no está; ficheros del almacén sin documento; documentos de gasto sin justificante.

## 6. Servicio implementado (`servicios/adjuntos.py`)

- **Almacén** (`AlmacenAdjuntos(raíz)`): `<raíz>/<empresa 3 dígitos>/<año>/<R|E|B|X>/<id>_<nombre saneado>`; la ruta guardada es relativa y nunca
  puede salir del almacén. El nombre original se conserva para mostrarlo.
- `adjuntar` (PDF/JPG, comprobando extensión **y** cabecera real, 25 MB máximo, huella SHA-256; un duplicado idéntico en el mismo documento no se
  guarda y se avisa), `sustituir` (mantiene la posición; si el nuevo no es válido no se toca el antiguo), `quitar`, `listar`.
- Con el ejercicio cerrado no se añaden ni quitan justificantes.
- `verificar_almacen`: ausentes, **alterados** (huella distinta) y huérfanos (ficheros sin adjunto). `facturas_sin_justificante`.
- `trasladar_a_almacen`: copia al almacén los justificantes importados de MGD y fija su ruta definitiva (idempotente). Con los datos
  de 2021 traslada los 49 de Empresa A y los 144 de Empresa B que existen, y deja los 7 y 18 ausentes marcados.
- **Auditoría:** `auditar(sesion, ejercicio, almacen=...)` añade tres avisos: `justificante_ausente` (el fichero no está en el almacén),
  `justificante_alterado` (la huella ya no coincide), `fichero_huerfano` y `gasto_sin_justificante` (factura recibida sin ningún justificante
  presente). Sin `almacen` la auditoría sólo avisa de los justificantes importados que faltaban.
- **Pendiente:** la interfaz web (subir, ver junto a los datos, quitar).

