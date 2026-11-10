# 06 · Asientos manuales («extras») y plantillas

Origen (Visual Objects): `vNuevoExtra` / `vPlConcreta` (`E_Edicion.prg:15790…16260`), `VtoAutomatico2Fecha` (2579),
`EvaluaCadenaFecha` (`A_Util.prg:5805`), `CadenaNumerosCad2Array` (3784). Tablas `Extra`, `Exapun` y `Explant`.
Verificado con MGD 2021: 14 extras reales (Empresa A 3, Empresa B 11) y 45 plantillas (28 + 17). Tests en `tests/test_plantillas.py` y
`tests/test_servicio_extras.py`.

## 1. Extras

Un **extra** es todo asiento que no nace de una factura ni de tesorería. Tipos (campo `TIPO`, y `TPASIENTO` en el Diario):
`M` normal o de plantilla · `A` apertura · `R` regularización de ingresos y gastos · `Z` cierre · `P` regularización de IVA · `Q` amortización.
En el sistema nuevo es un `Asiento` de tipo 4 (general) o 9 (automático); sus líneas son los `Apunte`.

- **Se agrupan por cuenta como el resto**: los 14 extras reales coinciden con el Diario tras agrupar (2 tenían cuentas repetidas).
- **Vencimientos por línea**: cada apunte puede tener vencimientos (la cuota de un préstamo, la retención de una nómina, las
  partidas pendientes del asiento de apertura…). En MGD cuelgan del apunte (`Vtos.TIPO = 'X'`, `TPNUMERO` = nº de apunte `Exapun`);
  aquí cuelgan de `apunte_id`. 19 vencimientos reales (1 Empresa A, 18 Empresa B), todos enlazados.
- El **signo** del vencimiento no sale del apunte: en el asiento de apertura una cuenta puede tener líneas al debe y al haber que
  se agrupan en un único apunte, y sus vencimientos llevan signos distintos (positivo a cobrar, negativo a pagar).
- Los apuntes **se reutilizan** al regrabar (como los registros en MGD): conservan su identidad —de la que cuelgan los
  vencimientos— y sus textos.

## 2. Plantillas

`Explant.CONTENIDO` guarda una línea por apunte con campos separados por `|`:

| Campo | Significado |
|---|---|
| cuenta | código de cuenta (7 dígitos en MGD, 8 aquí) |
| ayuda | texto de la línea |
| D / H / C | debe, haber o **cuadre** |
| importe | de muestra |
| vencimientos | reglas de fecha separadas por comas; cada una crea un vencimiento |

Reglas de uso (`vNuevoExtra`, `vPlConcreta._GrabaDatos`):
- **Cuadre**: una sola línea (más de una es error). Su importe es `Σ debe − Σ haber` del resto: si es ≥ 0 sale por el **haber**; si es
  < 0, por el **debe**. Con álgebra con signo.
- Una línea con importe 0 se omite; un importe negativo cambia de lado.
- Todas las cuentas deben existir al usarla (si no: «esta plantilla no se puede utilizar»).
- **Título**: admite `{año}`, `{mes}`, `{cmes}` (nombre del mes), `{dia}`, `{cdia}`, `{trimestre}`, `{cuatrimestre}` y operaciones
  (`{mes-1}`, `{año+1}`). `{cmes}` en minúsculas da minúsculas, `{CMES}` mayúsculas, `{Cmes}` capitalizado.
  No se usa `eval`: solo aritmética sencilla.

## 3. Reglas de fecha de vencimiento

`D<op><n> M<op><n> A<op><n> [PT | PM | PL] [DP<lista>]` (`fecha_de_vencimiento`):
- `=n` fija el valor; `+n` suma; sin número no cambia. `D=25 M= A=` → el día 25 del mes de la fecha del asiento.
- Si el día fijado ya ha pasado respecto al día de la fecha base, salta al **mes siguiente**. Particularidad de MGD: la
  comparación se hace con el día original y el mes ya cambiado, así que `D=1 M+1` desde el día 10 da el día 1 del mes
  *siguiente al siguiente*.
- `PT` primer día del trimestre siguiente (antes de aplicar D/M/A); `PM` próximo miércoles; `PL` próximo lunes;
  `DP5,20` / `DP12-` / `DP-3` primer día de pago de la lista a partir de esa fecha.
- Supuestos no verificables con los datos: un día inexistente se recorta al fin de mes y `D-n` resta (MGD lee el número sin signo).

## 4. Servicios (`servicios/extras.py`)

`grabar_extra` (crea o regraba; debe cuadrar; vencimientos por línea), `crear_desde_plantilla` (título evaluado, cuadre,
vencimientos automáticos), `eliminar_extra` (no si un vencimiento tiene pagos), `lineas_de_plantilla`.
Advertencia (no bloquea) si los vencimientos de una cuenta no suman el apunte, como el `??` de MGD.

## 5. Hallazgos

- Empresa B registra la cuota de su préstamo con una plantilla (`PRESTAMO BANKINTER`: cuota al haber de 5200001, principal e
  intereses al debe; regla `D+ M+ A+` = vencimiento el mismo día del asiento). Tres de esas cuotas están fechadas en 2020 dentro de
  la empresa de 2021 (las 3 que marca la auditoría).
- Los vencimientos de la regularización de IVA (extras `P`) los crea otro proceso (liquidación del IVA), no una plantilla: a
  día 25 del mes siguiente al trimestre.
