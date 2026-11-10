# 03 · Principios de diseño

Reglas transversales que se aplican a todas las pantallas. Se amplía a medida que aparezcan más.

## 1. Listados (norma para todos los listados)

Aplica a facturas recibidas, facturas emitidas, movimientos de tesorería, asientos, cuentas, terceros, bienes de
inversión, adjuntos y cualquier otro listado.

- **Se muestran todos los campos** del registro (columnas), sin ocultar datos por defecto.
- **Doble clic en una fila abre la edición** de ese registro. No hay botón "Editar" aparte.
- **Columnas redimensionables (expandibles)** y **ordenables** pulsando la cabecera (ascendente/descendente).
- **Acciones estándar** de la barra del listado: **Añadir**, **Borrar**, **Exportar a PDF** y **Exportar a Excel**.
  La exportación respeta lo que se ve: filtros, orden y columnas.
- Borrar pide confirmación y respeta las reglas contables (no se borra lo contabilizado en un ejercicio cerrado; si
  el registro tiene asiento, se avisa y se borra también su asiento o se bloquea, según el tipo).

Implementado (`web/listados.py`, ver `06_interfaz_web.md`): un componente de tabla reutilizable (FastAPI + HTMX) al que cada
listado solo aporta sus columnas y sus consultas; así el comportamiento es idéntico en todas las pantallas.

## 1 bis. Tema

Todas las pantallas ofrecen tema **claro**, **oscuro** y **automático** (el del sistema), con la paleta EMPRESA B de las
aplicaciones de escritorio; el color sólo se define como variable (`web/tema.py`).

## 2. Fechas

Entrada en `DDMMAA`/`DDMMAAAA`/`D/M`…, validación al introducir, coherencia con el ejercicio y el periodo contable
(ver Hito 1 del plan, punto 12).

## 3. Integridad

Nada puede grabar un asiento descuadrado; la auditoría de integridad se puede ejecutar a demanda y es obligatoria
antes de cerrar un ejercicio (ver Hito 1, punto 11).

## 4. Adjuntos

Las facturas recibidas y emitidas admiten PDF y JPG; se ven junto a los datos (ver Hito 1, punto 13).
