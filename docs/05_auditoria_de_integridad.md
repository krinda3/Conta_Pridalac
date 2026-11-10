# 05 · Auditoría de integridad contable

Código: [`src/conta_pridalac/auditoria.py`](../src/conta_pridalac/auditoria.py). Herramienta de línea de comandos:
`python tools/auditar_mgd.py <carpeta_dbf> <empresa> <nombre> <año> [informe.txt]`.

Es de **solo lectura**, se puede lanzar a demanda y será obligatoria **sin errores** antes de cerrar un ejercicio.
Los servicios (`servicios/asientos.py`, `servicios/facturas.py`) impiden crear los errores; la auditoría los caza si llegan por
otra vía (importación de datos antiguos, edición directa, regla nueva que cambió).

## Comprobaciones

| Código | Gravedad | Qué comprueba |
|---|---|---|
| `asiento_descuadrado` | ERROR | Σ debe ≠ Σ haber en un asiento |
| `apunte_en_cuenta_de_grupo` | ERROR | Apunte en una cuenta de menos de 8 dígitos |
| `asiento_fuera_del_ejercicio` | ERROR | Fecha del asiento fuera del ejercicio |
| `factura_fuera_del_ejercicio` | ERROR | Fecha contable de la factura fuera del ejercicio |
| `factura_sin_asiento` | ERROR | Factura sin el asiento que le corresponde |
| `factura_no_contabilizable` | ERROR | Factura a la que le falta una cuenta (p. ej. cuenta de IVA) |
| `asiento_distinto_del_regenerado` | ERROR | El asiento guardado ≠ el que se regenera desde la factura o el movimiento de banco |
| `movimiento_sin_asiento` / `asiento_de_movimiento_sobrante` | ERROR | Movimiento de banco con líneas sin asiento, o asiento de un movimiento que no genera líneas |
| `saldo_de_banco` | ERROR | Saldo contable de la cuenta del banco ≠ saldo inicial + Σ movimientos |
| `transferencia_sin_espejo` / `transferencia_importes` | ERROR | Transferencia entre bancos sin movimiento espejo o con importes que no se anulan |
| `hueco_en_el_diario` | AVISO | Números del libro diario sin asiento (asientos borrados) |
| `asiento_sin_documento` | AVISO | Asiento de factura o de banco cuyo documento no existe |
| `total_incoherente` | AVISO | Total ≠ Σ (base + IVA + recargo) + ajustes (retención de IRPF) |
| `vencimiento_pagado_de_mas` | AVISO | Pendiente con signo contrario al importe |
| `justificante_ausente` | AVISO | PDF/JPG referenciado que no está en disco (con almacén: o que ya no está en él) |
| `justificante_alterado` | AVISO | Con almacén: el fichero ya no tiene la huella SHA-256 guardada al adjuntarlo |
| `fichero_huerfano` | AVISO | Con almacén: fichero del ejercicio que ningún documento referencia |
| `gasto_sin_justificante` | AVISO | Con almacén: factura recibida sin ningún justificante presente |
| `liquidacion_iva_desactualizada` | AVISO | La liquidación de IVA grabada ≠ la que saldría hoy del saldo de las cuentas 472/477 del periodo (facturas contabilizadas después de liquidar) |
| `amortizacion_acumulada` | AVISO | Σ amortizado en el cuadro hasta el año anterior ≠ amortización acumulada de la apertura |
| `saldo_con_signo_raro` | AVISO | Cliente con saldo acreedor o proveedor con saldo deudor |

Pendiente de añadir: saldo de un tercero ≠ Σ de sus vencimientos pendientes, IVA de facturas ≠ saldo de las cuentas 472/477,
apertura ≠ cierre del ejercicio anterior, regularización de IVA.

## Qué encuentra en los datos reales (MGD 2021)

Con los datos de las dos empresas la auditoría **no inventa** nada: los asientos de facturas y de bancos se regeneran
idénticos (hallazgo 0 en esos controles) y lo que sale son cosas reales para revisar. Los informes completos con nombres e
importes están en `datos_locales/auditoria_*_2021.txt` (no se versionan).

| | Empresa A | Empresa B |
|---|---|---|
| Errores | 0 | **6** `asiento_fuera_del_ejercicio` |
| Cuadro de amortización ≠ apertura | 1 cuenta (110,00 €, el tractor) | 1 cuenta (9.217,41 € = un año de amortización del edificio) |
| Huecos en el libro diario | 3 números | 15 números |
| Liquidación de IVA desactualizada | 1 (2T, 18,87 €) | 1 (1T, 337,90 €) |
| Justificantes ausentes | 7 | 18 |
| Saldo con signo raro | 1 proveedor con saldo deudor de 58,85 € | 1 acreedor con saldo deudor de 542,80 € (viene de la apertura) |

**Lo que hay que revisar de verdad (Empresa B, errores):**
- 6 asientos fechados entre octubre y diciembre de **2020** dentro de la empresa de 2021 (movimientos de banco 81, 82 y 103
  y extras 6, 7 y 8). Es la cuota de un préstamo. El movimiento 103 dice en su texto "19/10/21" pero lleva fecha 19/10/**2020**:
  casi seguro un error de año al teclear, que es justo lo que evita la validación de fechas del sistema nuevo.
  Hay que decidir si son de 2020 (y pertenecen al ejercicio 2020) o están mal fechados.

**A revisar con tu asesor (avisos):**
- En las dos empresas el cuadro de amortización y la contabilidad difieren **un año** para un bien (en Empresa A, la contabilidad tiene
  110 € más que el cuadro; en Empresa B, el cuadro tiene 9.217,41 € más que la contabilidad). Son años de amortización que están
  en un sitio y no en el otro.
- Los huecos del diario son asientos que se borraron; no es un error, pero el libro diario legalizado debe ser correlativo.

## Cómo se prueba

`tests/test_auditoria.py`: casos sintéticos (descuadre, fecha fuera, factura sin asiento, asiento que ya no coincide con su
factura, huérfano, total incoherente, saldos con signo raro con el importe correcto) y las cifras de los hallazgos conocidos
de cada empresa real, para que un cambio en una regla que altere el resultado se vea al momento.
