# 02 · Inventario funcional según el manual de Gestión MGD

Fuente: manual del Módulo 1, unidades 1–3 (J. Feás Muñoz, 2012; licencia CC BY-NC-SA 3.0), sobre la
versión **3.5 r45**. El código que tenemos es la última versión (**4.0.3**) y es el punto de partida;
el manual solo describe una versión anterior. Cruzado con el código (fichero:línea) y con las tablas.

Importante: el manual es del autor del programa (Jesús Martínez, Universidad de Zaragoza). El programa
es gratuito y "abierto en el sentido de que el desarrollo se alimenta de aportaciones de usuarios",
pero **no es software libre con licencia declarada**. Antes de redistribuir nada derivado del código
conviene confirmar con el autor; para uso propio no hay problema práctico.

## 1. Conceptos que el manual aclara

| Concepto | Qué es | Efecto en el diseño |
|---|---|---|
| Empresa | Unidad de datos, nº 1–950, carpeta `mgdNNN` | El prefijo `011_` de los PDF de 2021 es la empresa 11 |
| Ejercicio | Se recomienda **una empresa por ejercicio** (el cierre crea la nueva con el asiento de apertura) | Modelo: `empresa` + `ejercicio` explícitos; el cierre debe poder abrir ejercicio nuevo |
| Empresa Base | Plantilla de la que se copian los parámetros al crear empresas | Necesitamos parámetros por defecto |
| Plan de cuentas | PGC 2008 Pymes precargado, 7 dígitos configurables, cambio de PGC posible | `gnCuenta` = longitud de cuenta; `CambioPGC` en el cierre |
| Asiento "Extra" | Cualquier asiento que no nazca de factura ni de tesorería | Confirmado: tipo `X` del Diario |
| Tipos de extra | Normal, Apertura, Regularización, Cierre, Regularización IVA, Amortización | `M`(?)/`A`/`R`/`Z`/`P`/amortización; falta cerrar `M` y `Q` |
| Vencimientos | Toda factura genera vencimientos; los cobros/pagos se casan contra ellos | `Vtos` + `Pagos` son el motor de tesorería |
| "Pendiente de aplicación" | Cobro/pago de origen desconocido, va a una cuenta puente | Es `param.pteAplic` en `ListaPagos.Asiento` |
| Plantillas | De asientos extra (D/H/Cuadre) y de cobros/pagos | Tabla `Playuda`/plantillas; patrón "D, H o Cuadre" |

## 2. Funciones del programa y su rol en el proyecto

Leyenda: **N** núcleo contable · **F** fiscal/presentación · **P** periférico · **X** fuera de alcance.

| Función (menú original) | Rol | Datos 2021 | Notas |
|---|---|---|---|
| Empresas, parámetros, multiusuario | P | Empresas, Param, Pargen | Multiusuario y red de ficheros: no aplican con BD cliente-servidor |
| Copias de seguridad (rápidas, internas, externas) | P | – | Sustituible por backup de BD |
| Plan de cuentas + consulta PGC | **N** | Cuentas (759) | Cobros/pagos por cuenta (Cuentas.PENTIDAD/PDIRECTO/PTIPO) |
| Tesorería: bancos, cajas, saldo inicial | **N** | Bancos (4), Movbanco (43) | Saldo inicial automático tras el cierre |
| Plantillas de cobros/pagos | P | – | Comodidad |
| Proveedores/acreedores/clientes/deudores | **N** | Proveed (102), Clientes (3) | Cuentas 400/410/430/440 + tipos para 173/164/165/523 |
| Facturas recibidas | **N** | Rec (56) | **Verificado 56/56** (doc 01) |
| Facturas emitidas | **N** | Emi (1) | Lógica leída, sin datos de prueba suficientes |
| IVA multi-tipo, RE, no deducible, bien de inversión | **N** | Eriva (57), Tipoiva (21) | |
| Cobros y pagos, remesas, compensaciones | **N** | Vtos (59), Pagos (43) | Algoritmo en doc 01 §6.3 |
| Previsión de tesorería | P | – | Informe sobre Vtos |
| Asientos extra y plantillas, múltiples extras | **N** | Extra (3), Exapun (37) | |
| Bienes de inversión + cuadro de amortización | **N** | Lbi (22) | Asiento de amortización aún sin leer |
| Resumen de IVA (modelo 303 en papel) + asiento de regularización | **F** | ficheros `IVA_*.dat` | Base de la presentación a AEAT |
| Libros registro (emitidas, recibidas, ventas, compras, resúmenes) | **F** | – | Hoy salen en Excel/DBF/PDF; falta formato oficial |
| Declaraciones de terceros (347, umbral 3.005,06 €) | **F** | – | Hoy lista de clientes/proveedores |
| Cierre: existencias, amortización, regularización, cierre/apertura | **N** | Extra tipos R/Z/A | Sin leer `CierreContable` |
| Balance, PyG, ECPN, memoria, análisis (informes y "fusionar" con Word) | **F** | Informes, Infapun | Motor de informes propio (`impInformes`, `vInformes`) |
| Facturación: artículos, familias, pedidos, albaranes, stock | X (de momento) | tablas `F_*` **vacías** | No se usaba |
| Importación desde ContaPlus | X | – | `_Trasvase Contaplus.prg` |
| Aviso, calculadora, casos prácticos, actualización | X | – | |

## 3. Lo que el manual NO cubre (y el proyecto necesita)

- **Presentación a la AEAT** (303, 390, 111, 115, 347…): el programa solo imprime o exporta. Hay que
  construirlo completo. Los `IVA_*.dat` de 2014–2021 son un banco de pruebas útil (ver §4).
- **Cuentas anuales y depósito en el Registro Mercantil**: el programa genera Balance, PyG, memoria
  y análisis para pegar en Word; no hay formato oficial de depósito.
- **Libros oficiales legalizables** (Diario y Mayor en el formato de legalización telemática).
- Módulos 2 y siguientes del manual (si existen) no los tenemos: el programa tiene más funciones de las
  que cubre este material (informes configurables, importar, analítica…).

## 4. Para usar los ficheros `IVA_*.dat`

Son liquidaciones guardadas con cabeceras `[EMITIDA]`, `NUMFACTURA=…`. Un `IVA_AAAAMMDD_AAAAMMDD.dat`
por periodo (2014–2021, algunos con periodos solapados que parecen recálculos). Servirán para validar el
cálculo del 303 igual que el Diario sirve para validar los asientos. Pendiente de analizar el formato.

## 5. Dudas abiertas que resuelve (o no) el manual

- `TPASIENTO`: `P` = regularización IVA. `M` y `Q` siguen sin confirmar.
- `noReduceApuntes`: el manual no lo menciona; es una opción interna. Pendiente de valor real.
- Versión: el manual es 3.5; el código es 4.0.3. Cualquier diferencia de comportamiento la gana el código.
