# 03 · Bienes de inversión y amortización (pseudocódigo)

Origen (Visual Objects): `vELbiCuadro.Generar` (`E_Edicion.prg:26126`), `LbiAmortiza` (27020), `vLbi.AmortizaUno` (27129),
`LbiListaCuadro` (27179), `LbiFijaExtras` (27202), `vCierre.AmortTodos/AmortUno` (`F_Contabilidad.prg:20864`).
Tabla `Lbi` (22 bienes en 2021). Verificado con `BBDD 2021` (tests `tests/test_amortizacion.py`).

| Regla | Resultado |
|---|---|
| Regenerar el cuadro de cada bien con el algoritmo de MGD | **22/22 idénticos al céntimo** |
| Σ amortizado hasta 2020 = amortización acumulada de la apertura 2021 (por cuenta) | 7/8 cuentas; el tractor difiere en 110,00 € |

## 1. Ficha (`Lbi`)

`NOMBRE`, cuentas (`CUENBIEN` inmovilizado, `CUENDOTA` **gasto** de dotación 68x, `CUENAMORT` **amortización
acumulada** 281x), `COSTE`, `RESIDUAL`, `FECHA` (puesta en funcionamiento), `FBAJA`/`CBAJA`, `COEFI` (% por periodo; si 0 se
deduce de `PERIODO`), `PERIODO` (vida útil en periodos, p. ej. 25 años), `MESES` (meses por periodo; 12 = anual), `IVA` (IVA
soportado del bien, para la regularización de bienes de inversión), `RECIBIDA`/`PROVEEDOR`/`REGISTRO` (factura de compra),
`CUADRO` (memo con el cuadro) y `NOTAS`.

## 2. Generar el cuadro (`Generar`)

```
neto = coste − residual                                   (error si ≤ 0)
porc = Integer(coefi·100)   (centésimas de punto)         si porc ≤ 0: porc = 10000 / periodos
periodos = 10000 / porc     si periodos ≤ 0
baja_teórica = suma_meses(inicio, meses·periodos) − 1 día
baja = baja_teórica, salvo que haya fecha de baja anterior
# fechas
primer periodo: desde = inicio; hasta = último día del "bloque" de `meses` meses que contiene a inicio (cap. a baja)
resto: hasta = suma_meses(desde, meses) − 1 día (cap. a baja); hasta que hasta == baja
# importes
por_periodo = neto · porc / 10000
para cada periodo [desde, hasta]:
    inicio_teórico = primer día del mes de (hasta − meses + 1)
    si desde == inicio_teórico: previsto = por_periodo
    si no (periodo recortado): previsto = (hasta − desde + 1 días) · por_periodo / (hasta − inicio_teórico + 1 días)
    previsto = round_half_up(previsto, decimales)
si baja == baja_teórica: el último periodo suma (neto − Σ previstos)       # absorbe el redondeo
```
Los días del divisor son los **reales** del periodo (365 o 366). Cada línea del cuadro guarda
`ejercicio · desde · hasta · previsto · ref · valor`.

## 3. Amortizar (`LbiAmortiza`)

Una línea se amortiza si: (1) aún no tiene importe realizado, (2) su periodo cae dentro de `[desde, hasta]` pedidos y
(3) `previsto > 0`. Crea un **asiento extra de tipo `Q`** (texto `AMORTIZACION DE <bien>`), con dos apuntes:

```
D  CUENDOTA  (gasto de amortización)          previsto
H  CUENAMORT (amortización acumulada)         previsto
```
y lo contabiliza (doc 01 §6.4). La fecha del asiento es el 31/12 del año (o la que pida el usuario si el periodo no
acaba el 31/12). La línea queda `ref = "X"` con el nº del extra. Se puede amortizar todo el inmovilizado de una vez
(cierre del ejercicio → "Amortizar los bienes de inversión") o bien por bien.

- **Tipos de extra confirmados:** `Q` = amortización, `M` = asiento normal/de plantilla (`PlContabiliza`), `A` apertura,
  `P` regularización de IVA, `R` regularización de ingresos y gastos, `Z` cierre.
- Al **cerrar con apertura** las líneas `X` pasan a `M` (importe fijado a mano; `LbiFijaExtras`): el ejercicio nuevo ya no
  depende de los extras del ejercicio anterior. Por eso en `BBDD 2021` todas las líneas (259) son `M`.
- `M` con importe 0,00 = periodo **pendiente de amortizar** (así se ve el 2021 de la copia de septiembre).

## 4. Hallazgos y comprobaciones útiles para la auditoría

- Tractor (MGD 2813001 → 28130001): amortización acumulada del cuadro hasta 2020 = 529,26 €; en la contabilidad (apertura) = 639,26 €.
  Falta 110,00 € (un año) en el cuadro de ese bien: lo deja la auditoría como "amortización acumulada contable ≠ cuadro".
- El coste de las cuentas de inmovilizado **no** coincide con Σ coste de `Lbi` (terrenos, instalaciones… tienen saldo que no está
  como bien individual): `Lbi` solo recoge lo que se amortiza y se quiso registrar, salvo `2300000` que cuadra.
- El programa anterior usa **otro** redondeo del primer periodo (ver plan §8): MGD prorratea por días reales del periodo con redondeo
  "mitad hacia arriba"; el programa anterior da 26,34 € en un caso y 317,22 € en otro, que ninguna de las dos variantes explica a la vez.
  Para años ya contabilizados manda el Diario; el cuadro de los bienes nuevos usará la regla elegida para el sistema nuevo.

## 5. Implicaciones para el sistema nuevo

- Tabla `bien_inversion` + `amortizacion_periodo` (hecho). El cuadro se **regenera** a demanda y las líneas realizadas guardan
  su importe y su asiento (`asiento_id`), no un texto.
- Cada amortización genera un asiento tipo 9 (automático, como en el programa anterior `2025.9.5`) o 4 según se decida, con la pareja
  gasto/amortización acumulada, y no se puede duplicar para el mismo periodo (restricción `UNIQUE(bien, desde)` y comprobación).
- Bajas: prorratear el último año hasta la fecha de baja (`fecha_baja`, "no amortizar en el ejercicio de baja") y retirar
  coste y amortización acumulada contra la cuenta de resultados. **No leído todavía**: asiento de baja y regularización de IVA de
  bienes de inversión.
- Falta la amortización **fiscal** (columna aparte en el programa anterior): necesaria para el modelo 200 (Hito 5).

## 6. Servicio implementado (`servicios/bienes.py`)

`alta_bien` (ficha validada + cuadro), `cuadro_del_bien` / `regenerar_cuadro` (rehace sólo las líneas sin amortizar; protege las
ya contabilizadas), `amortizar_periodo` / `amortizar_ejercicio` (asiento automático tipo 9, subtipo `Q`: dotación al debe y
amortización acumulada al haber, fechado al fin del periodo), `deshacer_amortizacion`, `periodos_pendientes` y `dar_de_baja`
(fija la fecha, acorta y prorratea el cuadro; respeta «no amortizar en el ejercicio de baja»).

**Validación con el programa anterior:** amortizar con el motor los periodos pendientes de 2021 y sumar la amortización acumulada de la
apertura de 2021 da exactamente la de la apertura de 2022 del programa anterior en **Empresa B** (168.624,51 €; el edificio, 9.217,41 €).
En **Empresa A** la diferencia es 343,56 €: la amortización de las naves, que el programa anterior añadió y que en MGD no era un bien de `Lbi`.
Es decir, la regla de MGD reproduce lo que se contabilizó en 2021 para los 22 bienes. (La diferencia de redondeo con el programa anterior
del §4 afecta a bienes nuevos del programa anterior, no a los años de MGD.)

### Baja y asiento de baja (no existe en MGD)

El código de MGD sólo **acorta el cuadro** con la fecha de baja (`vELbiCuadro.CambioFBaja`, `E_Edicion.prg:26900`: borra los periodos
posteriores y prorratea el último por días); no genera ningún asiento. El asiento de baja es nuevo y sigue el PGC
(`asiento_de_baja`, tipo 9, subtipo `B`):

```
D amortización acumulada   Σ amortizado hasta la baja
D cuenta de cobro          precio de venta (si lo hay)
D pérdidas del inmovilizado (671)   si precio < valor neto
H beneficios del inmovilizado (771) si precio > valor neto
H inmovilizado             coste
```
Exige fecha de baja y todos los periodos anteriores amortizados (salvo el de la baja si «no amortizar en el ejercicio de baja»), no
se repite (`BienInversion.asiento_baja_id`) y se puede deshacer. El IVA de una venta va en la factura emitida, no aquí.

### IVA de bienes de inversión (`servicios/bienes_iva.py`)

En MGD el IVA de un bien es un dato informativo de la ficha (`Lbi.IVA`) y la marca `BINVERSION` de las líneas de IVA; no hay asiento ni
regularización automática. En el 2021 de Empresa A ese dato es poco fiable (el Mazda trae 361.217 € de IVA). El servicio da el **libro de
bienes de inversión** (art. 40 RIVA) y la **regularización anual de deducciones** (arts. 107-110 LIVA): bien de inversión = más de
3.005,06 €; periodo de 5 años naturales (10 para terrenos y edificaciones); cada año tras el primero
`IVA / plazo × (% deducible del año − % deducible del primer año)`. Con deducción del 100 % es cero, que es el caso de los bienes de 2014-2016
de Empresa A (periodo ya agotado en 2021). La regularización por transmisión anticipada (art. 110) no se calcula: se avisa. Los porcentajes
por año se pasan al servicio; cuando exista la declaración de IVA de fin de año (Hito 4) saldrán de la prorrata definitiva.
