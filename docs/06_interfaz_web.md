# 06 · Interfaz web local

Aplicación **FastAPI + HTMX** que se abre en el navegador, sólo en este equipo (`127.0.0.1`). No necesita internet: HTMX 2.0.4 va
incluido en `src/conta_pridalac/web/static/`.

## Arrancar

```bash
python tools/crear_bd_mgd.py        # una vez: crea datos_locales/bd/empresa_a.sqlite y empresa_b.sqlite desde las copias de MGD
python -m conta_pridalac.web        # http://127.0.0.1:8000   (--puerto 8765, --datos <carpeta>, --almacen <carpeta>)
```

- **Datos:** una base `<empresa>.sqlite` por empresa en `datos_locales/bd` (o la carpeta de `CONTA_DATOS` / `--datos`). El nombre del
  fichero es el de la empresa en las direcciones: `/e/empresa_a/2021/cuentas`. `datos_locales/` no se versiona.
- **Justificantes:** `datos_locales/justificantes` (o `CONTA_ALMACEN` / `--almacen`).
- Una empresa nueva es copiar o crear otro `.sqlite`; la pantalla de inicio las lista todas.

## Tema claro, oscuro y automático

El botón de la barra superior recorre **Auto → Claro → Oscuro** y recuerda la elección en el navegador. «Auto» sigue el tema del
sistema (`prefers-color-scheme`). La paleta es la de `empresa_b_theme.py` (aplicaciones de escritorio de Empresa B), con los mismos
nombres y valores (`bg_base`, `pistacho`, `danger`…): `web/tema.py` los publica como variables CSS en `/tema.css` y todo el estilo
(`static/app.css`) usa sólo esas variables, de modo que cambiar un color en un sitio cambia toda la aplicación.

## El listado reutilizable (`web/listados.py`)

Aplica las reglas de `03_principios_de_diseno.md` a todos los listados. Cada listado sólo declara **columnas**, **campos** de
edición y tres operaciones (`filas`, `guardar`, `eliminar`), siempre a través de los servicios contables (nunca escribe tablas por
su cuenta, así que las reglas —ejercicio cerrado, cuentas en uso, asientos cuadrados— se aplican igual que desde otro sitio).

| Regla | Cómo |
|---|---|
| Todos los campos | una columna por dato; los importes alineados a la derecha, en negativo en rojo |
| Doble clic edita | abre el formulario en un diálogo (o el detalle de sólo lectura, p. ej. el asiento completo del Diario); Intro también |
| Columnas ordenables | clic en la cabecera (ascendente/descendente); los vacíos van siempre al final |
| Columnas ajustables | arrastrar el borde de la cabecera; doble clic en el borde = ancho automático; se recuerda por listado |
| Buscar | un cuadro que filtra en todas las columnas, sin distinguir mayúsculas ni acentos (tecla `/` para ir a él) |
| Añadir / Borrar | botones de la barra; el borrado pide confirmación, admite varias filas y muestra el motivo si no se puede |
| PDF y Excel | exportan **lo que se ve**: filtro, orden y parámetros actuales, con totales |
| Menú | el menú lateral se queda fijo al desplazar la página y, si no cabe, tiene su propio scroll |
| Parámetros | filtros propios del listado (nivel del balance, cuenta del mayor, fechas `DDMMAA`…) |

Errores contables (`ErrorContable`) y de base de datos vuelven al formulario como aviso sin perder lo escrito.

## Listados actuales

| Grupo | Listado | Edita |
|---|---|---|
| Facturas | Facturas recibidas · Facturas emitidas | alta, edición y borrado con asiento, vencimientos y justificantes (ver abajo) |
| Ejercicio | Auditoría de integridad | sólo lectura, con la explicación de cada hallazgo (ver abajo) |
| Ejercicio | Cierre del ejercicio | cerrar, reabrir y crear ejercicios (ver abajo) |
| IVA | Liquidación del IVA | liquidar, rehacer y deshacer cada periodo; parámetros (ver abajo) |
| Inmovilizado | Bienes de inversión · Libro de bienes de inversión (IVA) | alta, ficha, cuadro, amortización y baja (ver abajo) |
| Tesorería | Movimientos de banco · Vencimientos pendientes · Bancos | altas, ediciones, cobros, pagos y transferencias (ver abajo) |
| Asientos | Asientos manuales · Plantillas de asientos | alta, edición y borrado (ver abajo) |
| Datos | Plan de cuentas (con sumas del ejercicio) | alta, cambio y baja; el código sólo cambia si nada usa la cuenta |
| Datos | Clientes y proveedores | alta, cambio y baja; no se borra un tercero con documentos |
| Contabilidad | Libro Diario (doble clic = asiento completo) · Libro Mayor (todas las cuentas, cada una con su saldo y su total; se acota a una cuenta o a un grupo) · Balance de sumas y saldos (1, 2, 3 u 8 dígitos) | sólo lectura |
| IVA | Libro de IVA de facturas recibidas y emitidas | sólo lectura |

## Facturas (`web/facturas.py`)

El formulario es del servidor: cada cambio (tipo de IVA, base, tercero, línea nueva, repartir el pago) vuelve a calcular y devuelve el
cuerpo del formulario con las mismas reglas que el resto del programa. Mientras se teclea no se pierde nada: si llegan dos cambios
seguidos gana el último y el texto que se está escribiendo se conserva.

- **Cabecera:** fecha contable (obligatoria, validada contra el ejercicio y su estado), fecha y nº de la factura, tercero, cuenta del
  tercero y de gasto o ingreso, concepto y notas. Al elegir tercero se proponen su cuenta y el gasto de su última factura.
- **Líneas de IVA:** tipo del catálogo (propone el marcado por defecto o el más usado), base, %, cuota, cuenta de IVA, recargo,
  deducible y bien de inversión. La cuota se calcula mientras no se teclee; una cuota fuera de lo habitual de una factura ya grabada
  se respeta.
- **Ajustes y retenciones:** cuenta, importe, contrapartida y marcas; una retención crea su propio vencimiento a favor de Hacienda.
- **Vencimientos:** siguen al total mientras no se toquen; se pueden añadir, quitar y repartir en N plazos cada M meses. Los que ya
  tienen cobros o pagos no se quitan. La suma ha de ser total + retenciones: si no, no se graba y se dice la diferencia.
- **Justificantes:** se suben junto con la factura (PDF o JPG), se ven en un panel al lado y se quitan marcándolos. Si un fichero no
  es válido no se graba nada.
- **Todo o nada:** la factura, sus asientos, sus vencimientos y sus justificantes se graban en una sola transacción.
- Borrar una factura borra también sus asientos, vencimientos y los ficheros de sus justificantes (no si ya tiene pagos).

Comprobado con los datos reales: cada factura de MGD (las que cuadran con sus líneas) se reconstruye en el formulario, se graba y el
Diario y los vencimientos quedan idénticos.

## Asientos manuales y plantillas (`web/asientos.py`)

- **Asientos manuales** (tipo 4): fecha, concepto y líneas (cuenta, Debe/Haber, importe, concepto de la línea). Muestra Debe, Haber y el
  descuadre al momento; un asiento descuadrado no se graba. «Línea de cuadre» añade una línea cuyo importe y lado se calculan solos.
- **Vencimientos por línea** (cuotas de un préstamo, retenciones de una nómina…), con signo: positivo si se va a cobrar, negativo si se va
  a pagar. Los que ya tienen cobros o pagos no se quitan.
- **Justificantes** en PDF o JPG, con el mismo panel de vista que las facturas.
- **Desde plantilla:** se elige plantilla y fecha y se abre el asiento con sus líneas, el título resuelto (`NOMINA 3/2026`), la línea de
  cuadre y los vencimientos que mandan las reglas (`D=20 M+1 A=` → el día 20 del mes siguiente). Sólo hay que teclear los importes.
- **Plantillas:** título con `{año}`, `{mes}`, `{cmes}`, `{trimestre}`… y operaciones, líneas Debe/Haber/Cuadre (una sola de cuadre),
  importe de muestra y reglas de vencimiento separadas por comas (se validan al guardar).
- Con los datos reales (Empresa B 2021): los 4 asientos manuales que caen dentro del ejercicio se reconstruyen en el formulario, se graban y el
  Diario y los vencimientos quedan idénticos. Los 3 restantes llevan fecha de 2020 dentro del ejercicio 2021 (dato de MGD) y el formulario
  se niega a grabarlos hasta que se corrija la fecha. Empresa A no tiene asientos manuales en 2021.

## Tesorería (`web/tesoreria.py`)

- **Bancos:** nombre, sucursal, IBAN, BIC, cuenta contable y saldo inicial. El listado compara el *saldo por movimientos* (saldo inicial +
  Σ pagos) con el *saldo de la cuenta contable* y resalta en ámbar el banco en que no coinciden (es la misma comprobación que hace la
  auditoría). Un banco con movimientos no se borra ni cambia de cuenta.
- **Movimientos de banco:** cada línea salda **un vencimiento**, va a **una cuenta directa** o queda **pendiente de aplicar**. Al elegir un
  vencimiento se propone su pendiente (con el signo del banco: positivo entra, negativo sale). El formulario enseña el asiento que se
  generará antes de grabar; el texto en blanco se genera solo. El listado da el saldo del banco tras cada movimiento y admite
  justificantes (extracto, recibo).
- **Vencimientos pendientes (cartera):** lo que queda por cobrar y pagar, con lo ya cobrado/pagado, la cuenta, el banco previsto y el estado
  (los vencidos se resaltan). Doble clic en uno: **cobrar o pagar** (total o una parte), **compensar** contra otra cuenta, o cambiar su fecha,
  forma de pago y banco previsto.
- **Transferencias:** botón «⇄ Transferencia» en los movimientos; crea las dos mitades y un solo asiento entre los dos bancos. Sus mitades no
  se editan: al borrar una se borran las dos. Los movimientos de los bancos del sistema (compensación, remesas) sólo se ven.
- Los textos de movimientos heredados de MGD (con otro formato) y su orden dentro del día se respetan al editarlos.
- Con los datos reales: cada movimiento de banco de Empresa A y Empresa B se reconstruye en el formulario y se regraba con asientos, pagos y
  textos idénticos; todos los bancos cuadran con su cuenta contable.
- Pendiente: remesas de vencimientos (banco −3), que MGD usaba para recibos, y la conciliación bancaria con el extracto.

## Bienes de inversión (`web/bienes.py`)

- **Listado:** código, descripción, cuenta, puesta en funcionamiento, precio, residual, vida, lo amortizado, lo pendiente, baja y estado
  (sin amortizar · en amortización · totalmente amortizado · dado de baja); se puede filtrar por estado.
- **Ficha del bien:** descripción, tipo, factura de compra, fechas, precio, residual, vida útil en periodos (o % por periodo), meses por
  periodo, IVA soportado y las tres cuentas (inmovilizado, amortización acumulada, dotación). Al crearlo se genera el cuadro y el
  formulario sigue abierto para verlo.
- **Cuadro de amortización:** un renglón por periodo con lo previsto y lo contabilizado. «Amortizar» crea el asiento de dotación de ese periodo
  y «Deshacer» lo borra. Sólo se contabilizan los periodos que acaban en el ejercicio abierto; los demás indican «otro ejercicio».
- **Cambios de ficha:** con periodos amortizados sólo se cambian los datos descriptivos; si cambian precio, fechas, vida o cuentas hay que
  deshacer antes las amortizaciones. Un cambio sólo descriptivo **no rehace el cuadro**, así se respetan los cuadros con ajustes a mano
  heredados de MGD (el edificio de Empresa B tiene el primer periodo y los importes fijados a mano y 50 periodos).
- **Baja:** fecha, causa y «no amortizar en el ejercicio de baja» acortan el cuadro; después se contabiliza el asiento de baja (precio de venta,
  cuenta de cobro, pérdidas y beneficios) o se anula la baja. Todo con los avisos del servicio (periodos sin amortizar, cuentas inexistentes…).
- **«Amortizar el ejercicio»:** vista previa de todos los periodos pendientes que acaban en el ejercicio y, al confirmar, un asiento por cada uno.
- **Libro de bienes de inversión (IVA):** bienes de más de 3.005,06 € con IVA soportado, su periodo de regularización y la regularización del año
  (cero con deducción del 100 %); resalta los datos dudosos (IVA mayor que el precio).
- Con los datos reales: los 22 bienes de Empresa A y el edificio de Empresa B se abren y se guardan tal cual sin alterar su cuadro.
- Pendiente: editar a mano un periodo del cuadro y la amortización fiscal.

## Liquidación del IVA (`web/iva.py`)

- **Listado:** un renglón por periodo (trimestral por defecto; bimestral o mensual configurables) con el IVA soportado y repercutido, lo
  compensado de periodos anteriores, el resultado (a pagar o a compensar), la fecha de pago, el asiento y el **estado**: *sin liquidar*,
  *liquidado*, *desactualizado* (la liquidación grabada ya no coincide con el IVA del periodo: se contabilizaron facturas del periodo
  después de liquidar; se resalta en ámbar) o *sin IVA*.
- **Ficha del periodo** (doble clic): las cuentas de IVA con su saldo del periodo, el asiento de regularización —con la comparación
  *grabado / nuevo* si ya estaba liquidado— y el vencimiento que se crea. Botones: **Liquidar el periodo / Volver a liquidar**
  (idempotente: sustituye el asiento y su vencimiento) y **Deshacer la liquidación** (no si el IVA ya está pagado). La casilla *Compensar
  el saldo a favor de periodos anteriores* y «Recalcular la vista» permiten ver el efecto antes de grabar.
- **Parámetros del IVA** (botón del listado): periodicidad, día de pago de cada periodo (por ejemplo `20,20,20,30` para que el cuarto
  trimestre venza el 30 de enero) y las cuentas de Hacienda deudora y acreedora. Sin ellos el listado avisa de qué falta.
- Con los datos reales sale lo que ya señalaba la auditoría: en Empresa A el 1T está liquidado y el 2T desactualizado (18,87 € de IVA soportado
  contabilizado después de liquidar) y el 3T sin liquidar; en Empresa B el 1T está desactualizado (337,90 €) y el 2T y el 3T liquidados.
- Pendiente: la presentación del modelo 303 y el resumen anual 390 (Hito 4).

## Cierre y apertura del ejercicio (`web/ejercicios.py`)

- **Listado de ejercicios:** año, fechas, estado (abierto o cerrado), nº de asientos, resultado, asiento de cierre y apertura del siguiente.
- **Ficha del ejercicio** (doble clic) con la **lista de comprobación** previa al cierre:
  1. *Auditoría de integridad*: los **errores bloquean el cierre** (se listan con su referencia y el botón queda desactivado); los avisos no.
  2. *Liquidaciones del IVA*: cuántos periodos están liquidados, sin liquidar o desactualizados (enlaza con la liquidación).
  3. *Amortización de los bienes*: periodos sin amortizar y su importe (enlaza con los bienes).
  4. *Regularización de ingresos y gastos*: qué cuentas se saldarán contra Pérdidas y Ganancias (o la regularización ya hecha).
  5. *Vencimientos pendientes*: cuántos y por cuánto se **arrastran** a la apertura del siguiente.
- **Cerrar el ejercicio**: regulariza, genera el asiento de cierre, abre el ejercicio siguiente (casilla opcional) con sus vencimientos y
  marca el ejercicio como cerrado; después ya no admite movimientos en ninguna pantalla. Avisa del resultado (beneficio o pérdida) y de los
  vencimientos arrastrados. Todo o nada: si falla algo no queda nada a medias.
- **Reabrir el ejercicio**: deshace todo lo que hizo el cierre —el asiento de cierre, la **regularización de ingresos y gastos** y la apertura del
  siguiente—, sólo si éste no tiene más movimientos que su apertura. Al volver a cerrar se regulariza de nuevo con lo que haya (si se añadió algo
  tras reabrir, el resultado lo recoge).
- **Nuevo ejercicio**: crea un ejercicio vacío (1 de enero a 31 de diciembre) para empezar una contabilidad o un año intermedio.
- Con los datos reales: **Empresa A** se cierra y abre 2022; **Empresa B** no se puede cerrar mientras la auditoría marque los 6 asientos fechados
  en 2020 como error (y no se crea nada a medias).
- Como se señalaba en `pseudocodigo/07_cierre_e_iva.md` §6, el cierre se verificó por invariantes y no contra la salida real de MGD; para
  compararlo al céntimo hace falta una copia de MGD de un año anterior cerrado.

## Auditoría de integridad (`web/auditoria.py`)

- **Listado** de todos los hallazgos del ejercicio (los errores primero) con su gravedad, la comprobación, la referencia (asiento,
  factura, banco…) y qué ocurre; filtros por gravedad y por comprobación; un resumen encima («6 errores y 90 avisos — hay que corregir los
  errores antes de cerrar el ejercicio») y exportación a PDF y Excel.
- **Ficha de cada hallazgo** (doble clic): qué significa, **cómo se corrige** y un enlace a la pantalla donde se arregla (si la referencia es un
  asiento, la pantalla depende de su tipo: facturas, banco o asientos manuales) con el contenido del asiento a la vista.
- Las 27 comprobaciones tienen su texto en el catálogo (`CATALOGO`); un test comprueba que ninguna comprobación nueva se queda sin explicación.
- El cierre del ejercicio enlaza con esta pantalla. La auditoría se recalcula cada vez (unos segundos con los datos de Empresa B).
- Incluye las comprobaciones de los justificantes (ausentes, modificados, ficheros sueltos y gastos sin justificante).

## Ficha ampliada de clientes y proveedores, y cuadro de amortización editable

- **Proveedores y Clientes** (dos listados separados, menú «Datos»): el formulario va por secciones (*Datos generales*, *Contabilidad*, *Por defecto en las facturas*, *Datos de pago o de cobro*) con los campos del programa anterior:
  identificador, nombre comercial, domicilio, teléfonos, correo, web, divisa, marcas (recargo de equivalencia, no 347, genérico, criterio de caja, REAGP), subcuentas de
  gasto/ingreso, suplidos y pago/cobro, tipos de IVA por defecto, retención, % de IVA deducible, forma de pago, IBAN (con dígitos de control) y BIC. Con la cuenta
  vacía se crea la siguiente cuenta libre del grupo (400/410/430/440). Las columnas nuevas se añaden solas a las bases existentes (`actualizar_esquema`).
- **Facturas**: el proveedor o cliente se busca escribiendo (nombre o NIF; el navegador sugiere y el servidor resuelve el texto, avisando si no hay coincidencia o hay varias). Al elegirlo se propone su subcuenta de gasto o de ingreso (si no la tiene, la de su última factura), su primer tipo de IVA y su forma de pago.
- **Importador de MGD**: carga domicilio, población, provincia, código postal, BIC, notas y criterio de caja.
- **Cuadro de amortización**: cada periodo sin asiento tiene sus importes previsto y contabilizado editables («Guardar los importes del cuadro»); con importe contabilizado
  queda «fijado a mano» y sin importe, pendiente. Un periodo con asiento propio se cambia tras «Deshacer».
- **Buscador de cuentas**: todo campo donde se escribe una cuenta (asientos, plantillas, movimientos, facturas, bienes, ficha de terceros, bancos, parámetros de IVA) sugiere mientras se teclea: cada palabra se busca dentro del número y de la descripción (sin tildes ni mayúsculas), primero las que empiezan por lo escrito; flechas y Enter eligen, Esc cierra (`static/app.js`, listas `dl-cuentas*`).
- **Vencimientos**: ayuda breve en «Compensar» y «Banco previsto».
- Los listados con muchas filas mantienen fijas la cabecera de columnas y la fila de totales; sólo se desplazan los datos.

## Ficha de la empresa y contraseña (certificado digital)

- Pantalla de inicio → «Ficha de la empresa» (`/empresa/<empresa>`): razón social, NIF, fecha de constitución, actividad y CNAE, domicilio y contacto, representante,
  datos del Registro Mercantil y certificado digital. Las columnas nuevas de `empresa` se añaden solas a las bases existentes.
- **Certificado**: la ficha guarda sólo la ruta del `.pfx` (fuera del repositorio). Al asociarlo se comprueba que la contraseña lo abre (`cryptography`, como Verifactu) y se
  muestran titular, NIF y caducidad. Con certificado asociado la empresa pide su contraseña al entrar (🔒 en la tarjeta); sin él se abre libremente.
- **Examinar…** abre el cuadro «Abrir fichero» de Windows (la aplicación corre en este mismo equipo, así que se lanza desde el servidor con `tkinter`) y devuelve la ruta; el navegador no puede dar rutas reales.
- **Datos del certificado**: «Rellenar la ficha con los datos del certificado» lee el `.pfx` y propone razón social, NIF de la empresa y nombre y NIF del representante (pistas: organización, `organizationIdentifier`, `serialNumber`, `(R: …)` o `CIF …` en el nombre común, como Verifactu). Sólo rellena lo que está vacío; al asociar un certificado nuevo el servidor hace lo mismo. Son propuestas: los certificados no son todos iguales.
- Movimientos de banco: la primera línea de un movimiento nuevo es «Una cuenta directa».
- La contraseña **no se guarda**: vive en memoria del servidor, por navegador (cookie de sesión `HttpOnly`) y empresa, hasta «Cerrar la empresa» o parar el programa.
  Con HTMX una sesión no abierta recibe `401` + `HX-Redirect` a la pantalla de entrada. La base de datos no se cifra.

## Pendiente en la interfaz

Nada: el backlog de la interfaz del Hito 1 está terminado.
