# Inventario del diseño de registro del modelo 200 (`DR200e25.xls`)

Cruzado con 10 ficheros `.200` presentados (Empresa A y Empresa B, 2021–2025). Detalle campo a campo en `inventario_DR200_campos.csv` (filtrar por `clase`).

- Hojas (páginas) del diseño: **77**; campos: **6808**.
- Páginas que aparecen en algún fichero real: **23** (2142 campos).
- Páginas que no aparecen en ninguno: **54** (4666 campos).

## Páginas que aparecen en los ficheros reales

| Hoja | Página | Título | Campos | Ficheros | Con valor | Notas | Decisión |
|---|---|---|---:|---:|---:|---:|---|
| DP200001 | 01000 | Identificación | 113 | 10/10 | 35 | 5 | SE USA: rellenar todos sus campos |
| DP200001B | 01B00 | Grupo mercantil | 23 | 4/10 | 3 | 7 | SE USA: rellenar todos sus campos |
| DP200002 | 02000 | B. Participaciones directas | 145 | 10/10 | 44 | 1 | SE USA: rellenar todos sus campos |
| DP200002B | 02B00 | D. Información de detalle de establecimiento permanente que opere en el extranjero | 167 | 8/10 | 20 | 7 | SE USA: rellenar todos sus campos |
| DP200003 | 03000 | Balance: Activo (I) | 57 | 10/10 | 7 | 1 | SE USA: rellenar todos sus campos |
| DP200004 | 04000 | Balance: Activo (II) | 39 | 10/10 | 6 | 1 | SE USA: rellenar todos sus campos |
| DP200005 | 05000 | Balance: Patrimonio neto y pasivo (I) | 65 | 10/10 | 15 | 1 | SE USA: rellenar todos sus campos |
| DP200006 | 06000 | Balance: Patrimonio neto y pasivo (II) | 39 | 10/10 | 11 | 1 | SE USA: rellenar todos sus campos |
| DP200007 | 07000 | Cuenta de pérdidas y ganancias (I) | 68 | 10/10 | 29 | 1 | SE USA: rellenar todos sus campos |
| DP200008 | 08000 | Cuenta de pérdidas y ganancias (II) | 46 | 10/10 | 9 | 1 | SE USA: rellenar todos sus campos |
| DP200009 | 09000 | Estado de cambios patrimonio neto (I) | 28 | 2/10 | 2 | 1 | SE USA: rellenar todos sus campos |
| DP200010 | 10000 | Estado de cambios patrimonio neto (II) | 154 | 6/10 | 18 | 1 | SE USA: rellenar todos sus campos |
| DP200011 | 11000 | Estado de cambios patrimonio neto (III) | 141 | 6/10 | 12 | 1 | SE USA: rellenar todos sus campos |
| DP200012 | 12000 | Liquidación I | 102 | 10/10 | 6 | 1 | SE USA: rellenar todos sus campos |
| DP200013 | 13000 | Liquidación II | 105 | 10/10 | 5 | 1 | SE USA: rellenar todos sus campos |
| DP200014 | 14000 | Liquidación III | 64 | 10/10 | 11 | 6 | SE USA: rellenar todos sus campos |
| DP200014B | 14B00 | Liquidación IV | 92 | 10/10 | 19 | 5 | SE USA: rellenar todos sus campos |
| DP200015 | 15000 | Detalle compensación bases imponibles negativas | 160 | 8/10 | 48 | 1 | SE USA: rellenar todos sus campos |
| DP200020 | 20000 | Limitación deducibilidad gastos financieros. gastos financieros pendientes deducir | 125 | 10/10 | 5 | 1 | SE USA: rellenar todos sus campos |
| DP200020D | 20D00 | Dotaciones deterioro créditos u otros activos | 111 | 7/10 | 6 | 1 | SE USA: rellenar todos sus campos |
| DP200021 | 21000 | Comunicación importe neto cifra negocios | 61 | 6/10 | 5 | 1 | SE USA: rellenar todos sus campos |
| DP200024B | 24B00 | Partícipes de agrupaciones de interés económico y UTES | 194 | 2/10 | 0 | 1 | SE USA: rellenar todos sus campos |
| DP200DID | DID00 | Cuenta bancaria | 43 | 10/10 | 29 | 7 | SE USA: rellenar todos sus campos |

## Páginas que no aparecen en ninguno

| Hoja | Página | Título | Campos | Notas | Decisión |
|---|---|---|---:|---:|---|
| DP200000 | - | (DP200000) | 8 | 9 | CABECERA del fichero (no es una página): se escribe siempre |
| DP200015B | 15B00 | Deducciones doble imposición interna (DT 23.1 LIS) | 168 | 1 | OPCIONAL, entrada manual (doble imposición interna (DT 23.ª)): solo si hay datos |
| DP200016 | 16000 | Deducciones doble imposición internacional LIS | 152 | 1 | OPCIONAL, entrada manual (doble imposición internacional): solo si hay datos |
| DP200016B | 16B00 | Deducciones inversión Canarias | 173 | 1 | NO APLICA (Canarias): se omite |
| DP200016C | 16C00 | Información adicional para el cálculo de límites de deducciones | 13 | 1 | OPCIONAL, entrada manual (límites de deducciones (si hay deducciones)): solo si hay datos |
| DP200017 | 17000 | Deducc. para incentivar determ.actividades | 177 | 1 | OPCIONAL, entrada manual (deducciones por incentivos (I+D+i, innovación…)): solo si hay datos |
| DP200018 | 18000 | Deducc. para incentivar determ.actividades | 166 | 1 | OPCIONAL, entrada manual (deducciones por incentivos): solo si hay datos |
| DP200018B | 18B00 | Deducciones por producciones cinematográficas extranjeras (art. 36.2 LIS) | 153 | 1 | OPCIONAL, entrada manual (producciones cinematográficas extranjeras): solo si hay datos |
| DP200018C | 18C00 | Deducción donativos entidades sin fines lucro | 169 | 1 | OPCIONAL, entrada manual (donativos a entidades sin fines de lucro): solo si hay datos |
| DP200019 | 19000 | Deducciones I+D+i excluidas de límite | 245 | 3 | OPCIONAL, entrada manual (I+D+i excluidas de límite): solo si hay datos |
| DP200019B | 19B00 | Deducciones I+D+i excluidas de límite | 10 | 1 | OPCIONAL, entrada manual (I+D+i excluidas de límite): solo si hay datos |
| DP200020B | 20B00 | Reserva de nivelación | 97 | 3 | OPCIONAL, entrada manual (reserva de nivelación): solo si hay datos |
| DP200020C | 20C00 | Conversión activos impuesto diferido crédito exigible frente Admón.tributaria | 168 | 1 | OPCIONAL, entrada manual (conversión de activos por impuesto diferido en crédito exigible): solo si hay datos |
| DP200022 | 22000 | Rég. cooperativas | 150 | 1 | NO APLICA (cooperativas): se omite |
| DP200022B | 22B00 | Rég. especial reserva inversiones Illes Balears | 27 | 1 | NO APLICA (Illes Balears): se omite |
| DP200023 | 23000 | Operaciones fusión, escisión, canje valores | 57 | 1 | OPCIONAL, entrada manual (fusión, escisión, canje de valores): solo si hay datos |
| DP200024 | 24000 | Agrup. Interés económico y UTES | 66 | 1 | NO APLICA (AIE y UTE): se omite |
| DP200025 | 25000 | Rég.transparencia fiscal internacional | 62 | 1 | OPCIONAL, entrada manual (transparencia fiscal internacional): solo si hay datos |
| DP200026 | 26000 | Tributación conjunta Estado y Adm.Forales | 159 | 1 | NO APLICA (tributación conjunta con Diputaciones Forales): se omite |
| DP200026B | 26B00 | Cambio de criterios contables (art. 11.3.2º LIS) | 171 | 1 | OPCIONAL, entrada manual (cambio de criterios contables): solo si hay datos |
| DP200026C | 26C00 | Pérdidas por deterioro del art. 13.1 LIS no afectada por el art. 11.12 ni por DT 33ª.1 LIS | 125 | 1 | OPCIONAL, entrada manual (pérdidas por deterioro (art. 13.1 LIS)): solo si hay datos |
| DP200026D | 26D00 | Asimetrías híbridas (art. 15 bis LIS, excepto art. 15 bis.12 LIS) | 135 | 1 | OPCIONAL, entrada manual (asimetrías híbridas): solo si hay datos |
| DP200026E | 26E00 | Exención sobre la renta obtenida en la transmisión de valores entidades no residentes (art. 21.3, 21.10 y DT 40ª LIS) | 188 | 1 | NO APLICA (exención de valores de entidades no residentes): se omite |
| DP200026F | 26F00 | Transparencia fiscal internacional (art. 100 LIS) | 150 | 1 | OPCIONAL, entrada manual (transparencia fiscal internacional (art. 100)): solo si hay datos |
| DP200026G | 26G00 | Operaciones a plazos (DT 1ª LIS) | 88 | 1 | OPCIONAL, entrada manual (operaciones a plazos (DT 1.ª)): solo si hay datos |
| DP200027 | 27000 | Contabilidad Banco de España | 64 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200027B | 27B00 | Contabilidad Banco de España | 16 | 1 | NO APLICA (entidades de crédito): se omite |
| DP200028 | 28000 | Contabilidad Banco de España | 48 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200029 | 29000 | Contabilidad Banco de España | 48 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200030 | 30000 | Contabilidad Banco de España | 45 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200031 | 31000 | Contabilidad Banco de España | 46 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200032 | 32000 | Contabilidad Banco de España | 105 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200033 | 33000 | Contabilidad Banco de España | 93 | 1 | NO APLICA (entidades de crédito (contabilidad Banco de España)): se omite |
| DP200034 | 34000 | Entidades aseguradoras | 59 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200035 | 35000 | Entidades aseguradoras | 17 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200036 | 36000 | Entidades aseguradoras | 52 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200037 | 37000 | Entidades aseguradoras | 36 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200038 | 38000 | Entidades aseguradoras | 62 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200039 | 39000 | Entidades aseguradoras | 52 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200040 | 40000 | Entidades aseguradoras | 56 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200041 | 41000 | Entidades aseguradoras | 38 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200042 | 42000 | Entidades aseguradoras | 133 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200043 | 43000 | Entidades aseguradoras | 115 | 1 | NO APLICA (entidades aseguradoras): se omite |
| DP200044 | 44000 | Inst. inversión colectiva | 58 | 1 | NO APLICA (instituciones de inversión colectiva): se omite |
| DP200045 | 45000 | Inst. inversión colectiva | 64 | 1 | NO APLICA (instituciones de inversión colectiva): se omite |
| DP200046 | 46000 | Inst. inversión colectiva | 46 | 1 | NO APLICA (instituciones de inversión colectiva): se omite |
| DP200047 | 47000 | Inst. inversión colectiva | 57 | 1 | NO APLICA (instituciones de inversión colectiva): se omite |
| DP200048 | 48000 | Inst. inversión colectiva | 17 | 1 | NO APLICA (instituciones de inversión colectiva): se omite |
| DP200049 | 49000 | Sociedades de garantía recíproca | 57 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
| DP200050 | 50000 | Sociedades de garantía recíproca | 26 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
| DP200051 | 51000 | Sociedades de garantía recíproca | 36 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
| DP200052 | 52000 | Sociedades de garantía recíproca | 21 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
| DP200053 | 53000 | Sociedades de garantia recíproca | 67 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
| DP200054 | 54000 | Sociedades de garantia recíproca | 55 | 1 | NO APLICA (sociedades de garantía recíproca): se omite |
