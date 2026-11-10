# Categorías de gasto (análisis) — diseño

## Para qué
Poder analizar los gastos de cada empresa por conceptos con sentido (gas, electricidad, combustible, abonos, labores subcontratadas…) **desde 2021**, sin alterar la contabilidad de los ejercicios cerrados ni ningún modelo presentado.

## Decisiones (04/11/2026)
- **Vía híbrida.** Ejercicios 2021-2025 (cerrados, presentados, diarios legalizados): **no se toca ningún asiento**; se añade una *categoría de análisis* por factura. Desde 2026 se reclasifica de verdad en cuentas nuevas, de modo que categoría y cuenta coincidan y en unos años todo quede limpio.
- La cuenta **623** (servicios profesionales independientes) no se toca nunca: toda factura con contrapartida 623 es la categoría «Servicios profesionales».
- Labores subcontratadas: en una cuenta del 629 (no en la 607), para que no entren en aprovisionamientos.
- Maquinaria agrícola: desde 2026 la compra va a Maquinaria (21300000), se amortice o no. En los años anteriores el análisis la marca «compra de maquinaria (inversión)».
- **Empresa A, gasóleo en existencias (321.10):** en los años cerrados se queda como está y el análisis lo cuenta como gasóleo. En 2026 (abierto) un asiento llevará el saldo a la cuenta de gasto de gasóleo, y la 321.10 queda a cero (a gasto de 2026, no a reservas).
- **Paneles solares de Empresa B (2024):** se quedan como gasto en la contabilidad. En el informe, categoría aparte «Instalación / inversión» (no entra en la serie de electricidad) y una columna *informativa* de amortización teórica a 5 años. No se contabiliza.
- Una factura = una categoría; opcionalmente un **reparto** (categoría principal + importe para otra), p. ej. gasolinera con tienda → parte a comidas. Endesa: gas y electricidad separados factura a factura.

## Modelo (implementado)
- Tabla `categoria_gasto` (por empresa): código, nombre, tipo (`gasto`, `inversion`, `amortizacion`, `impuesto`, `excepcional`, `financiero`), cuenta destino desde 2026.
- `factura.categoria_gasto_id` (nulo = se deduce por reglas) y `factura_reparto` (factura, categoría, importe).
- Cambiar la categoría **no es un cambio contable**: se permite en ejercicio cerrado sin reabrir, y queda anotado en el registro de cambios.
- Asignación inicial por reglas `proveedor → categoría` (con la cuenta actual como respaldo) y excepciones por factura. Las reglas viven en `datos_locales/categorias_gasto_<empresa>.json` (datos reales: fuera de git).
- Informe «Gastos por categoría y año» por empresa (categoría × año, detalle por proveedor, exportación a Excel).

## Orden de prioridad de las reglas
1. Cuenta de la factura que manda (623 → servicios profesionales; 321 → gasóleo; 211/212/213 → inversión; 68 → amortización; 630 → impuesto…).
2. Excepción por factura.
3. Regla por proveedor (puede depender de la cuenta actual).
4. Cuenta actual por defecto.
5. «Sin clasificar».

## Simulación
`datos_locales/salida/simulacion_categorias.md` y `simulacion_categorias_<empresa>.csv` (solo lectura sobre copias). Las categorías de gasto cuadran con el grupo 6 de los libros; las diferencias son las partidas de inversión, el gasóleo en existencias (321) y las aplicaciones informáticas (206).

## Categorías añadidas durante la revisión (Empresa A)
- **Reforma de la casilla y nave nueva (2021-2025):** categoría propia para saber lo que costó la remodelación (ampliación de la casilla con la nave existente y construcción de una nave nueva). Reúne facturas que en los libros están en cuentas distintas (inmovilizado 211, reparaciones 622, servicios profesionales 623 y compras 600); el análisis las junta sin tocar ningún asiento.
- Las anotaciones del propietario sobre facturas concretas se guardan como `excepciones_factura` (ejercicio + asiento) y mandan sobre cualquier regla.

## Implementación (04/11/2026)
- `db/modelos.py`: `CategoriaGasto` (código, nombre, tipo, prefijos de cuenta, años de amortización teórica), `FacturaReparto` y `Factura.categoria_gasto_id`. Las tres tablas están en el registro de cambios.
- `servicios/categorias_gasto.py`: catálogo, clasificación por reglas, asignación a mano (permitida en ejercicio cerrado), reparto e informe por categoría y año. Si la factura no tiene categoría, se deduce de su cuenta de gasto por prefijo (el más largo gana).
- `tools/cargar_categorias_gasto.py`: carga el catálogo y clasifica las facturas desde el fichero de reglas. Simula por defecto, comprueba que los saldos de **todas** las cuentas quedan idénticos y exige `--en-la-base-real --copia-hecha` para aplicar.
- Pantalla **Gastos por categoría** (caja «Listados»), con detalle por proveedor y exportación a PDF y Excel como el resto de listados.
- Tests: `tests/test_categorias_gasto.py`.

## Pendiente
- Cuentas nuevas de 2026 y reclasificación real de las facturas de 2026 a ellas (propuesta de cuentas a aprobar).
- Asiento de 2026 de la 321.10 de Empresa A a gasto de gasóleo; atomizador (Zeppelin 4.034 €) de la 622 a la 21300000.
- Campo «Categoría» en la ficha de la factura, para ajustarla desde la pantalla.
