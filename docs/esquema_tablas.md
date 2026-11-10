# Esquema de tablas (DBF 2021)


| Tabla | Registros | Campos |
|---|---:|---:|
| Actividad | 0 | 4 |
| Ajustes | 1 | 8 |
| Analitica | 0 | 5 |
| Bancos | 4 | 9 |
| Clientes | 3 | 28 |
| Cuentas | 759 | 8 |
| Diario | 391 | 12 |
| Diatxt | 0 | 11 |
| Directos | 1 | 2 |
| Emi | 1 | 18 |
| Empresas | 0 | 4 |
| Eriva | 57 | 12 |
| Eticod | 0 | 4 |
| Etidat | 57 | 4 |
| Exapun | 37 | 7 |
| Explant | 28 | 2 |
| Extra | 3 | 12 |
| F_albemi | 0 | 15 |
| F_albinv | 1 | 9 |
| F_albped | 0 | 11 |
| F_albpede | 0 | 11 |
| F_albpre | 0 | 11 |
| F_albrec | 0 | 18 |
| F_albrep | 0 | 8 |
| F_apu | 0 | 21 |
| F_apupre | 0 | 21 |
| F_art | 0 | 31 |
| F_artc | 0 | 3 |
| F_fam | 0 | 5 |
| F_famc | 0 | 4 |
| Formdoc | 0 | 6 |
| Formhoja | 0 | 4 |
| Fotos | 0 | 8 |
| Infapun | 0 | 22 |
| Informes | 0 | 12 |
| Lbi | 22 | 20 |
| Movbanco | 43 | 14 |
| Pagos | 43 | 8 |
| Param | 67 | 3 |
| Pargen | 0 | 3 |
| Playuda | 0 | 2 |
| Proveed | 102 | 23 |
| Rec | 56 | 20 |
| Recibos | 0 | 10 |
| Tipoiva | 21 | 10 |
| Tipoop | 34 | 6 |
| Tiporef | 0 | 3 |
| Tiporefa | 0 | 3 |
| Tipovtos | 2 | 5 |
| Vtos | 59 | 10 |
| XBORRARX | 121 | 14 |

## Actividad

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 5 | 0 |
| NOMBRE | C | 64 | 0 |
| ETIQUETA | C | 20 | 0 |
| ACTIVA | C | 1 | 0 |

## Ajustes

Registros: 1

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 8 | 0 |
| CUENTA | C | 12 | 0 |
| IMPORTE | N | 14 | 2 |
| CONTRA | C | 1 | 0 |
| CAMBIOAS | C | 1 | 0 |
| AFECTAIVA | C | 1 | 0 |
| DECLTERC | C | 1 | 0 |

## Analitica

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 10 | 0 |
| CUENTA | C | 12 | 0 |
| ACTIVIDAD | N | 5 | 0 |
| IMPORTE | N | 14 | 2 |

## Bancos

Registros: 4

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 3 | 0 |
| NOMBRE | C | 64 | 0 |
| SUCURSAL | C | 64 | 0 |
| NUMCTA | C | 24 | 0 |
| BIC | C | 11 | 0 |
| CUENTA | C | 12 | 0 |
| SALDOINI | N | 14 | 2 |
| SALDOACT | N | 14 | 2 |
| NOTAS | M | 10 | 0 |

## Clientes

Registros: 3

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 5 | 0 |
| NOMBRE | C | 128 | 0 |
| COMERCIAL | C | 64 | 0 |
| DOMICILIO | C | 64 | 0 |
| LOCALIDAD | C | 64 | 0 |
| PROVINCIA | C | 20 | 0 |
| COD_POSTAL | C | 5 | 0 |
| AP_CORREOS | C | 5 | 0 |
| NIF | C | 20 | 0 |
| CUENTA | C | 12 | 0 |
| OPERACION | N | 3 | 0 |
| BRUTO | N | 14 | 2 |
| NETO | N | 14 | 2 |
| PENDIENTE | N | 14 | 2 |
| BANCO_NOM | C | 64 | 0 |
| BANCO_SUC | C | 64 | 0 |
| BANCO_DIG | C | 24 | 0 |
| MANDATO | C | 35 | 0 |
| F_MANDATO | D | 8 | 0 |
| BIC | C | 11 | 0 |
| IVA | N | 3 | 0 |
| BANCO_TIT | C | 64 | 0 |
| ANTICIPO | C | 12 | 0 |
| TIPO | C | 1 | 0 |
| DECLTERC | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| CONTACTOS | M | 10 | 0 |
| NOTAS | M | 10 | 0 |

## Cuentas

Registros: 759

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| CUENTA | C | 12 | 0 |
| TEXTO | C | 128 | 0 |
| DEBE | N | 14 | 2 |
| HABER | N | 14 | 2 |
| PENTIDAD | N | 3 | 0 |
| PDIRECTO | L | 1 | 0 |
| PTIPO | N | 3 | 0 |
| MARCA | C | 1 | 0 |

## Diario

Registros: 391

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ASIENTO | N | 10 | 0 |
| FECHA | D | 8 | 0 |
| TPASIENTO | C | 1 | 0 |
| CLAVE | C | 3 | 0 |
| CLAVE_ORI | C | 4 | 0 |
| TIPO | C | 1 | 0 |
| NUMERO | N | 10 | 0 |
| IMPORTE | N | 14 | 2 |
| CUENTA | C | 12 | 0 |
| SALDO | N | 14 | 2 |
| MULTI | C | 1 | 0 |
| MARCA | C | 1 | 0 |

## Diatxt

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 10 | 0 |
| CUENTA | C | 12 | 0 |
| TEXTO | C | 128 | 0 |
| DOCU | C | 15 | 0 |
| MULTI | C | 1 | 0 |
| NEGATIVO | C | 1 | 0 |
| ACUMULAR | C | 1 | 0 |
| ASIENTO | N | 10 | 0 |
| FECHA | D | 8 | 0 |
| NOTAS | M | 10 | 0 |

## Directos

Registros: 1

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| CUENTA | C | 12 | 0 |
| TEXTO | C | 64 | 0 |

## Emi

Registros: 1

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| FREGISTRO | D | 8 | 0 |
| CLIENTE | N | 5 | 0 |
| CLCUENTA | C | 12 | 0 |
| TIPOOP | N | 3 | 0 |
| TOCUENTA | C | 12 | 0 |
| TOTAL | N | 14 | 2 |
| TOTALDECL | N | 14 | 2 |
| DECLTERC | C | 1 | 0 |
| CCAJA | C | 1 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| REGISTRO | N | 8 | 0 |
| NOTAS | M | 10 | 0 |

## Empresas

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 3 | 0 |
| NOMBRE | C | 64 | 0 |
| MONEDA | C | 1 | 0 |
| HISTORICO | L | 1 | 0 |

## Eriva

Registros: 57

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| FACTURA | N | 8 | 0 |
| NUMERO | N | 3 | 0 |
| IVA | N | 5 | 2 |
| IVA_CTA | C | 12 | 0 |
| IVA_TOTAL | N | 14 | 2 |
| RE | N | 5 | 2 |
| RE_CTA | C | 12 | 0 |
| RE_TOTAL | N | 14 | 2 |
| BASE | N | 14 | 2 |
| NODEDU | C | 1 | 0 |
| BINVERSION | C | 1 | 0 |

## Eticod

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| CLAVE | C | 1 | 0 |
| FORMA | C | 1 | 0 |
| CODIGO | C | 30 | 0 |

## Etidat

Registros: 57

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 10 | 0 |
| CLAVE | C | 1 | 0 |
| TEXTO | C | 64 | 0 |

## Exapun

Registros: 37

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| EXTRA | N | 8 | 0 |
| CUENTA | C | 12 | 0 |
| AYUDA | C | 64 | 0 |
| DH | C | 1 | 0 |
| IMPORTE | N | 14 | 2 |
| DECLTERC | C | 1 | 0 |

## Explant

Registros: 28

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TEXTO | C | 64 | 0 |
| CONTENIDO | M | 10 | 0 |

## Extra

Registros: 3

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| TIPO | C | 1 | 0 |
| CLAVE | C | 3 | 0 |
| TEXTO | C | 64 | 0 |
| GRUPO | C | 1 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albemi

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| CLIENTE | N | 5 | 0 |
| FACTURA | N | 6 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| CPI | C | 3 | 0 |
| ORDEN | N | 4 | 0 |
| ESTADOREP | C | 1 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albinv

Registros: 1

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| TIPO | C | 1 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| APUNTES | N | 8 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albped

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| PROVEEDOR | N | 5 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albpede

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| CLIENTE | N | 5 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albpre

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| CLIENTE | N | 5 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albrec

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| PROVEEDOR | N | 5 | 0 |
| FACTURA | N | 6 | 0 |
| PRALBARAN | C | 20 | 0 |
| PRFECHA | D | 8 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| CPI | C | 3 | 0 |
| ORDEN | N | 4 | 0 |
| ESTADOREP | C | 1 | 0 |
| PEDIDO | N | 8 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## F_albrep

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| ALBARAN | N | 8 | 0 |
| FACTURA | N | 8 | 0 |
| IMPORTE | N | 14 | 2 |
| APUNTES | N | 8 | 0 |
| CPI | C | 3 | 0 |
| ORDEN | N | 4 | 0 |
| REPARTO | C | 1 | 0 |

## F_apu

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ALBARAN | N | 8 | 0 |
| TALBARAN | C | 1 | 0 |
| FECHA | D | 8 | 0 |
| TIPO | C | 1 | 0 |
| ARTICULO | N | 8 | 0 |
| TEXTO | C | 128 | 0 |
| TEXTO2 | C | 20 | 0 |
| TEXTO3 | C | 64 | 0 |
| DCTO1 | N | 5 | 2 |
| DCTO2 | N | 5 | 2 |
| DCTO3 | N | 5 | 2 |
| CANTIDAD | N | 17 | 5 |
| PRECIO | N | 17 | 5 |
| IMPORTE | N | 14 | 2 |
| PVENTAIVA | N | 14 | 2 |
| TIVA | N | 3 | 0 |
| TIPOOP | N | 3 | 0 |
| CUENTA | C | 12 | 0 |
| REPARTO | C | 1 | 0 |
| GRUPO | C | 3 | 0 |
| ALMACEN | C | 1 | 0 |

## F_apupre

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ALBARAN | N | 8 | 0 |
| TALBARAN | C | 1 | 0 |
| FECHA | D | 8 | 0 |
| TIPO | C | 1 | 0 |
| ARTICULO | N | 8 | 0 |
| TEXTO | C | 128 | 0 |
| TEXTO2 | C | 20 | 0 |
| TEXTO3 | C | 64 | 0 |
| DCTO1 | N | 5 | 2 |
| DCTO2 | N | 5 | 2 |
| DCTO3 | N | 5 | 2 |
| CANTIDAD | N | 17 | 5 |
| PRECIO | N | 17 | 5 |
| IMPORTE | N | 14 | 2 |
| PVENTAIVA | N | 14 | 2 |
| TIVA | N | 3 | 0 |
| TIPOOP | N | 3 | 0 |
| CUENTA | C | 12 | 0 |
| REPARTO | C | 1 | 0 |
| GRUPO | C | 3 | 0 |
| ALMACEN | C | 1 | 0 |

## F_art

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CODIGO | C | 20 | 0 |
| EAN13 | C | 20 | 0 |
| UBICACION | C | 15 | 0 |
| PROVEEDOR | N | 5 | 0 |
| FAMILIA | N | 3 | 0 |
| NOMBRE | C | 128 | 0 |
| PVENTA | N | 17 | 5 |
| PVENTAIVA | N | 14 | 2 |
| DCTO | N | 5 | 2 |
| TDCTO | C | 1 | 0 |
| DCTO2 | N | 5 | 2 |
| DCTO3 | N | 5 | 2 |
| PCOMPRA | N | 17 | 5 |
| PCDCTO | N | 5 | 2 |
| PCDCTO2 | N | 5 | 2 |
| PCDCTO3 | N | 5 | 2 |
| TIPOIVAC | N | 3 | 0 |
| TIPOIVAV | N | 3 | 0 |
| OPERACIONC | N | 3 | 0 |
| OPERACIONV | N | 3 | 0 |
| ALBINVENT | N | 8 | 0 |
| FINVENT | D | 8 | 0 |
| QINVENT | N | 17 | 5 |
| QCOMPRAS | N | 17 | 5 |
| QVENTAS | N | 17 | 5 |
| MINIMO | N | 17 | 5 |
| TIPO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| ASOCIADO | N | 8 | 0 |
| NOTAS | M | 10 | 0 |

## F_artc

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ARTICULO | N | 8 | 0 |
| CARNUM | N | 2 | 0 |
| DATO | C | 20 | 0 |

## F_fam

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 3 | 0 |
| PADRE | N | 3 | 0 |
| TEXTO | C | 40 | 0 |
| DCTO | N | 5 | 2 |
| TDCTO | C | 1 | 0 |

## F_famc

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| FAMILIA | N | 3 | 0 |
| CARNUM | N | 2 | 0 |
| TIPO | C | 1 | 0 |
| TEXTO | C | 40 | 0 |

## Formdoc

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 2 | 0 |
| NUMERO | N | 3 | 0 |
| TEXTO | C | 40 | 0 |
| ENBLANCO | L | 1 | 0 |
| COPIAS | N | 3 | 0 |
| DATOS | M | 10 | 0 |

## Formhoja

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 2 | 0 |
| NUMERO | N | 3 | 0 |
| TEXTO | C | 40 | 0 |
| DATOS | M | 10 | 0 |

## Fotos

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 8 | 0 |
| NOMBRE | C | 64 | 0 |
| MOSTRAR | L | 1 | 0 |
| IZQ | N | 4 | 0 |
| ARR | N | 4 | 0 |
| ANCHO | N | 4 | 0 |
| ALTO | N | 4 | 0 |

## Infapun

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| INFORME | N | 5 | 0 |
| NUMERO | N | 5 | 0 |
| PADRE | N | 5 | 0 |
| TEXTO | C | 125 | 0 |
| TIPO | N | 1 | 0 |
| MODO_IMP | N | 1 | 0 |
| LINEA_SEP | N | 1 | 0 |
| LINEA_DEB | N | 1 | 0 |
| LINEA_ENC | N | 1 | 0 |
| CONDICION | N | 1 | 0 |
| MARGEN_TXT | N | 2 | 0 |
| MARGEN_IMP | N | 2 | 0 |
| ALIN_TXT | N | 1 | 0 |
| ALIN_IMP | N | 1 | 0 |
| CLAVE | C | 14 | 0 |
| DECIMALES | N | 1 | 0 |
| SUMAR | L | 1 | 0 |
| NEGRITA | L | 1 | 0 |
| HABER | L | 1 | 0 |
| PORC | C | 1 | 0 |
| TIPOSAS | C | 4 | 0 |
| DATOS | M | 10 | 0 |

## Informes

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 5 | 0 |
| NOMBRE | C | 128 | 0 |
| TITULO | C | 128 | 0 |
| PGC | C | 30 | 0 |
| ANCHO_TXT | N | 3 | 0 |
| SI_MULTI | L | 1 | 0 |
| CABECERA | C | 40 | 0 |
| TIPOS | C | 4 | 0 |
| CLAVE | C | 3 | 0 |
| COMPROBAR | M | 10 | 0 |
| COLUMNAS | M | 10 | 0 |
| PROGRAMA | M | 10 | 0 |

## Lbi

Registros: 22

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NOMBRE | C | 64 | 0 |
| CUENBIEN | C | 12 | 0 |
| CUENDOTA | C | 12 | 0 |
| CUENAMORT | C | 12 | 0 |
| COSTE | N | 14 | 2 |
| RESIDUAL | N | 14 | 2 |
| FECHA | D | 8 | 0 |
| FBAJA | D | 8 | 0 |
| CBAJA | C | 15 | 0 |
| COEFI | N | 6 | 2 |
| PERIODO | N | 4 | 0 |
| MESES | N | 3 | 0 |
| IVA | N | 14 | 2 |
| MARCA | C | 1 | 0 |
| RECIBIDA | N | 8 | 0 |
| PROVEEDOR | N | 5 | 0 |
| REGFECHA | D | 8 | 0 |
| REGISTRO | N | 8 | 0 |
| CUADRO | M | 10 | 0 |
| NOTAS | M | 10 | 0 |

## Movbanco

Registros: 43

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| BANCO | N | 3 | 0 |
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| TEXTO | C | 64 | 0 |
| AUTOTEXT | N | 2 | 0 |
| CLAVE | C | 3 | 0 |
| FECHA | D | 8 | 0 |
| TOTAL | N | 14 | 2 |
| SALDONUE | N | 14 | 2 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |

## Pagos

Registros: 43

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| BANCO | N | 3 | 0 |
| NUMERO | N | 8 | 0 |
| IMPORTE | N | 14 | 2 |
| VTO | N | 10 | 0 |
| DIRSUBCTA | C | 12 | 0 |
| NUMEROT | N | 7 | 0 |
| BANCOT | N | 3 | 0 |
| DECLTERC | C | 1 | 0 |

## Param

Registros: 67

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ETIQUETA | C | 20 | 0 |
| TEXTO | C | 64 | 0 |
| MAS | L | 1 | 0 |

## Pargen

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| ETIQUETA | C | 20 | 0 |
| TEXTO | C | 64 | 0 |
| MAS | L | 1 | 0 |

## Playuda

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| IMPORTE | C | 14 | 0 |
| AYUDA | C | 64 | 0 |

## Proveed

Registros: 102

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 5 | 0 |
| NOMBRE | C | 128 | 0 |
| COMERCIAL | C | 64 | 0 |
| DOMICILIO | C | 64 | 0 |
| LOCALIDAD | C | 64 | 0 |
| PROVINCIA | C | 20 | 0 |
| COD_POSTAL | C | 5 | 0 |
| AP_CORREOS | C | 4 | 0 |
| NIF | C | 20 | 0 |
| CUENTA | C | 12 | 0 |
| OPERACION | N | 3 | 0 |
| BRUTO | N | 14 | 2 |
| PENDIENTE | N | 14 | 2 |
| NETO | N | 14 | 2 |
| IVA | N | 3 | 0 |
| CTAIRPF | C | 12 | 0 |
| ANTICIPO | C | 12 | 0 |
| TIPO | C | 1 | 0 |
| CCAJA | C | 1 | 0 |
| DECLTERC | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| CONTACTOS | M | 10 | 0 |
| NOTAS | M | 10 | 0 |

## Rec

Registros: 56

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| FECHA | D | 8 | 0 |
| REGFECHA | D | 8 | 0 |
| PROVEEDOR | N | 5 | 0 |
| PRCUENTA | C | 12 | 0 |
| PRFACTURA | C | 20 | 0 |
| PRFECHA | D | 8 | 0 |
| TIPOOP | N | 3 | 0 |
| TOCUENTA | C | 12 | 0 |
| TOTAL | N | 14 | 2 |
| TOTALDECL | N | 14 | 2 |
| DECLTERC | C | 1 | 0 |
| CCAJA | C | 1 | 0 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| REGISTRO | N | 8 | 0 |
| NOTAS | M | 10 | 0 |

## Recibos

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| AGENTE | N | 5 | 0 |
| TIPOAP | C | 1 | 0 |
| DIA | N | 2 | 0 |
| MES | N | 2 | 0 |
| EJERCICIO | N | 4 | 0 |
| IMPORTE | C | 30 | 0 |
| CONCEPTO | C | 64 | 0 |
| RSEPARADO | L | 1 | 0 |
| VTO | C | 20 | 0 |

## Tipoiva

Registros: 21

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 3 | 0 |
| TEXTO | C | 30 | 0 |
| IVA | N | 5 | 2 |
| CTA_IVA | C | 12 | 0 |
| IVA_RE | N | 5 | 2 |
| CTA_IVA_RE | C | 12 | 0 |
| PORDEFECTO | L | 1 | 0 |
| INACTIVO | L | 1 | 0 |
| ABREVIA | C | 3 | 0 |

## Tipoop

Registros: 34

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 3 | 0 |
| TEXTO | C | 30 | 0 |
| CUENTA | C | 12 | 0 |
| PORDEFECTO | L | 1 | 0 |
| IVA | N | 3 | 0 |

## Tiporef

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 3 | 0 |
| TEXTO | C | 30 | 0 |

## Tiporefa

Registros: 0

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| TIPO | C | 1 | 0 |
| NUMERO | N | 3 | 0 |
| TPNUMERO | N | 8 | 0 |

## Tipovtos

Registros: 2

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 3 | 0 |
| TEXTO | C | 30 | 0 |
| CLIDEF | C | 1 | 0 |
| PROVDEF | C | 1 | 0 |
| ESTADO | C | 40 | 0 |

## Vtos

Registros: 59

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| NUMERO | N | 10 | 0 |
| TIPO | C | 1 | 0 |
| TPNUMERO | N | 8 | 0 |
| FECHA | D | 8 | 0 |
| IMPORTE | N | 14 | 2 |
| PENDIENTE | N | 14 | 2 |
| CUENTA | C | 12 | 0 |
| CUENTADEF | C | 12 | 0 |
| PENTIDAD | N | 3 | 0 |
| PTIPO | N | 3 | 0 |

## XBORRARX

Registros: 121

| Campo | Tipo | Long | Dec |
|---|---|---:|---:|
| BANCO | N | 3 | 0 |
| NUMERO | N | 8 | 0 |
| CNUMERO | N | 9 | 0 |
| TIPONUM | C | 1 | 0 |
| CNUMALT | C | 20 | 0 |
| TEXTO | C | 64 | 0 |
| AUTOTEXT | N | 2 | 0 |
| CLAVE | C | 3 | 0 |
| FECHA | D | 8 | 0 |
| TOTAL | N | 14 | 2 |
| SALDONUE | N | 14 | 2 |
| ESTADO | C | 1 | 0 |
| MARCA | C | 1 | 0 |
| NOTAS | M | 10 | 0 |
