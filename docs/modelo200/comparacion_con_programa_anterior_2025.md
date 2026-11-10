# Modelo 200 de 2025: Conta frente a lo que presentó el programa anterior

Comparación hecha con `tools/comparar_200.py` (campo a campo, página a página) entre el fichero que genera Conta y los `.200` presentados en julio de 2026:

```
python tools/comparar_200.py --bd datos_locales/bd/empresa_b.sqlite --real AEAT/C0001_200_2025.200 --en-la-base-real --como-programa-anterior --forzar-25
python tools/comparar_200.py --bd datos_locales/bd/empresa_a.sqlite    --real AEAT/C0002_200_2025.200 --en-la-base-real --como-programa-anterior --forzar-25
```

`--como-programa-anterior` no suma las multas ni el gasto por el impuesto (el programa anterior no lo hacía). `--forzar-25` aplica el tipo general: el programa anterior presentó las dos al 25 % y en la base real de Empresa B
todavía no está marcada la casilla 00066 (entidad patrimonial), que es lo que hace que la regla proponga el 25 %.

## Resultado

Las 20 (Empresa B) y 21 (Empresa A) páginas se generan en el mismo orden que el programa anterior y son **idénticas campo a campo**, salvo estas diferencias, todas explicadas:

| Empresa | Página | Campo | el programa anterior | Conta | Por qué |
|---|---|---|---|---|---|
| Empresa A | 01000 | 00027 «Base imponible negativa o cero» | 0 | 1 | Decisión de Javier: se marca cuando la base es negativa o cero (en 2022 y 2023 el programa anterior sí la marcaba; en 2024 y 2025 no) |
| Empresa A | 01000 | Nombre de la persona de contacto | `…GARCIA XE SOTO` | `…GARCIA DE SOTO` | Errata del programa anterior |
| Empresa A | 02000 y 02B00 | Nombre de Elena Lopez | `LOPEZ GARCIA DE SOTO , ELENA` | `LOPEZ GARCIA DE SOTO, ELENA` | el programa anterior escribió un espacio antes de la coma en Empresa A (en Empresa B no) |
| Empresa B | 02000 | Nominal de tres socios (12 % cada uno) | 360,73 € | 360,61 € | Conta calcula el 12 % del capital del balance (3.005,06 €); la cifra del programa anterior hacía que los socios sumaran 3.005,43 € |
| Las dos | 01000 | Código CNAE-2025 | `0000` (en blanco) | el de la ficha (`7112`, `0125`) | La sede avisa (196) si falta |
| Empresa A | 21000 | Página de actividades agrícolas | no la llevaba | cifra de negocios agrícola | La sede avisa (22587) si se marca «agrícola» y falta |
| Empresa B | 13000 y 12000 | Total de correcciones 00417 y multas 01815 | 0 | 250 € (las multas de 2025) | Decisión acordada: las multas se suman a la base. La sede calcula el total (error E25400417 si no coincide) |

Además, en Empresa A 2025 el programa anterior presentó «actividades agrícolas» = 0 por error (Empresa A sí cultiva); Conta lo escribe con lo que se marque en la pantalla del IS (`agricola`).

## Cómo se obtuvo cada página

- **Balance y PyG (03000–08000):** cada línea PYMES va a su casilla «padre» y, a veces, a una «hija»; la PyG se reparte por cuentas donde el 200 lo pide (compras de mercaderías, servicios profesionales
  independientes, arrendamientos…). Verificado con los importes reales de las dos empresas; las casillas que valen cero en las dos, elegidas por nombre (ver `impuesto_sociedades_200_estados.py`).
- **Estado de cambios del patrimonio neto (09000–11000):** de `cuentas_anuales.estado_cambios_pn`, casando filas y columnas por las descripciones del diseño. El programa anterior solo rellena el resultado
  en la fila «Resultado cuenta de pérdidas y ganancias» y las otras variaciones en el total y en la subfila «Otras variaciones».
- **Titulares reales (02B00):** los socios con más del 25 %, uno por página en orden alfabético; la primera página lleva también al secretario y a los representantes legales (fecha del poder y notaría).
- **Páginas que aparecen según el caso:** 15000 solo con bases negativas pendientes o generadas; 20D00 solo con beneficio; 13000 siempre (en blanco).

## Qué NO está probado con ficheros reales

Ni Empresa A ni Empresa B lo necesitaban en 2025, así que solo hay pruebas con datos inventados: un resultado a **ingresar** (la página bancaria de domiciliación), las **correcciones manuales** al resultado
(solo las multas y el gasto por el impuesto tienen casilla), las **deducciones y bonificaciones**, la **reserva de nivelación**, y las **operaciones con socios** del estado de cambios del patrimonio neto.
La prueba definitiva es la importación en la sede de la AEAT (la hace Javier; el 2025 ya está presentado y NO debe presentarse de nuevo).
