# Modelo 200: prueba de ida y vuelta y páginas de cada fichero

Hecha el 02/11/2026 con `DR200e25.xls` (diseño del ejercicio 2025) y los 10 `.200` presentados de Empresa A y Empresa B (2021–2025). Herramienta de partida: `tools/inventario_dr200.py`.

## 1. El diseño 2025 reproduce los ficheros 2025 byte a byte

- Los campos de cada página cubren su longitud sin huecos ni solapes. La última fila de cada hoja es la etiqueta de cierre (`</T20001000>`, 12 caracteres).
- Los tipos se escriben así (y no hay una sola excepción en los dos ficheros de 2025):
  - `N` (importe, 17): `NDDDDDDDDDDDDDDDD` si es negativo (la `N` ocupa la primera posición) o 17 dígitos si es positivo; siempre en céntimos, sin coma.
  - `Num`: dígitos con ceros a la izquierda hasta la longitud.
  - `A` y `An`: texto alineado a la izquierda y relleno de blancos a la derecha.
- El fichero es **una sola cadena** (sin saltos de línea): `<T200020250A0000><AUX>…</AUX>` + páginas + `</T200020250A0000>`.
- Leer cada página en valores tipados y volver a escribirla con esas reglas da el **mismo fichero**: 41 páginas de 41 y los dos ficheros completos idénticos.
- Los ficheros de 2021 a 2024 **no** cuadran con este diseño (las páginas miden menos): cada año tiene su diseño. De ahí que el generador y el control de cambios vayan **versionados por ejercicio**.

## 2. Qué páginas lleva cada fichero (`c` = página complementaria)

El Excel **no explica cuándo** se incluye cada página (solo da su formato y que deben ir en orden). Lo observado en los ficheros del programa anterior:

| Fichero | Páginas |
|---|---|
| Empresa B 2021 | 01 02 03 04 05 06 07 08 12 13 14 14B 15 20 20D 21 DID |
| Empresa B 2022 | 01 02 02B 03 04 05 06 07 08 10 11 12 13 14 14B 15 20 20D 21 DID |
| Empresa B 2023 | 01 02 02B 03–08 10 11 12 13 14 14B 15 20 20D 21 24B DID |
| Empresa B 2024 | 01 01B 02 02B 03–08 10 11 12 13 14 14B 20 DID |
| Empresa B 2025 | 01 01B 02 02B 03–08 09 10 11 12 13 14 14B 20 20D DID |
| Empresa A 2021 | 01 02 03 04 05 06 07 08 12 13 14 14B 15 20 20D 21 DID |
| Empresa A 2022 | 01 02 02B 03–08 12 13 14 14B 15 20 20D 21 DID |
| Empresa A 2023 | 01 02 02B 02Bc 03–08 12 13 14 14B 15 20 20D 21 24B DID |
| Empresa A 2024 | 01 01B 02 02B 02Bc 03–08 10 11 12 13 14 14B 15 20 DID |
| Empresa A 2025 | 01 01B 02 02B 02Bc 03–08 09 10 11 12 13 14 14B 15 20 DID |

Conclusiones y dudas:

- **Núcleo fijo** (en todos los años y empresas): 01, 02, 03–08, 12, 13, 14, 14B, 20 y DID.
- **Cambian con el diseño del año**: 01B desde 2024; 09 desde 2025; 10 y 11 desde 2022 (Empresa B) y 2024 (Empresa A); 21 solo hasta 2023.
- **15 (compensación de bases negativas)**: en Empresa A todos los años (tiene bases negativas pendientes) y en Empresa B solo hasta 2023.
- **02B**: a partir de 2022. Se repite como complementaria (`c`) en Empresa A desde 2023, cuando la lista no cabe en una página.
- **20D (deterioro de créditos)**: aparece también con **todos los campos a cero** (Empresa B y Empresa A 2021–2022) y 24B (AIE/UTE) aparece vacía en 2023: el programa anterior incluye alguna página aunque no tenga datos. La regla «una página va si tiene datos» **no es cierta**.
- Por tanto las reglas de inclusión **no se pueden deducir solo de los ficheros**: hay que contrastarlas con la validación de la AEAT.

## 3. Pendiente

1. Regla provisional del generador para 2025: núcleo fijo + 01B + 02B (y su complementaria) + 09, 10 y 11 + 15 si hay bases negativas pendientes + 20D si hay deterioro de créditos. Las opcionales, solo si el usuario introduce datos.
2. Comprobar el fichero generado con el validador de la AEAT (la prueba definitiva de qué páginas son obligatorias) antes de dar el generador por bueno.
3. Reglas de validación del Excel (columna «Validación») como controles previos a generar.
