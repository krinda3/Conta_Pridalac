# Registro Mercantil: libros y depósito de cuentas

Una sociedad tiene dos obligaciones anuales con el Registro Mercantil:

1. **Legalizar los libros** del ejercicio (diario, inventario y cuentas anuales, registro de socios y registro de actas), **hasta el 30 de abril** del año siguiente. Se hace con **Legalia2**.
2. **Depositar las cuentas anuales**, **un mes después de que la junta las apruebe** (la junta debe aprobarlas antes del 30 de junio). Se hace con **D2**.

Conta **prepara** lo que esos programas necesitan; **ellos firman y presentan**. Conta no firma nada.

## Antes de empezar: la ficha de la empresa

Los dos trámites leen la **ficha de la empresa** (se abre pulsando su nombre, arriba). Compruebe que tiene:

- NIF, domicilio, código postal, población y provincia.
- **Datos del Registro Mercantil**: provincia del registro, tomo, folio, hoja y el **código IRUS** (13 cifras).
- **Municipio y provincia del INE** (códigos numéricos), que pide Legalia2.
- **Presentador**: nombre, apellidos, NIF, domicilio, teléfono y correo de quien presenta.
- **Representantes con poder** (para el 390 y el modelo 200).

El programa avisa de lo que falta antes de dejarle generar nada.

## Libro de socios y libro de actas

- [Libro de socios](pantalla:libro-socios): los socios y los **movimientos de sus participaciones** (constitución, compras, ventas, ampliaciones…). Doble clic en un socio para ver o corregir sus datos y movimientos. El libro que se legaliza sale de aquí, y también el reparto de capital que usan el depósito y el modelo 200 (los **titulares reales** son los socios con más del 25 %).
- [Libro de actas](pantalla:libro-actas): las actas de las reuniones de la sociedad. **Cada acta entra en el libro del ejercicio al que pertenece su fecha**: la reunión de marzo de 2025 (que aprobó las cuentas de 2024) va en el libro de 2025, que se legaliza en abril de 2026. El botón **Acta de aprobación de cuentas…** prepara una con el texto habitual, que se puede cambiar.

> **El capital de los socios debe coincidir con la cuenta de capital del balance.** Si no, la legalización lo avisa (por ejemplo, 35.000 € de socios frente a 34.580 € de la cuenta 100).

## Legalización de libros

[Legalización de libros](pantalla:legalizacion-libros): una fila por ejercicio. Doble clic abre la ficha con los **controles**, los **números de libro** y los botones numerados.

### Cómo se hace

1. **Generar los libros.** Crea los cuatro PDF: el **diario**, el **inventario y cuentas anuales** (balances de sumas y saldos inicial, de cada trimestre y de inventario, más la memoria), el **registro de socios** y el **registro de actas**, y el ZIP para Legalia2 (con el nombre que ese programa espera, por ejemplo `LL28025B00000010.ZIP`).
2. **Copiar el ZIP** a la carpeta de descargas.
3. En **Legalia2**: importe el ZIP, revíselo y **envíe** la legalización con su certificado.
4. **Registrar el envío**: suba el PDF **«Acuse de recibo»** que devuelve el Registro; de él se leen el identificador, la referencia, el número de entrada y la fecha. El ejercicio queda como **enviado** y deja de avisar el plazo.

### Cosas que conviene saber

- **El número de libro** sube cada año en el diario y en el inventario; el de socios y el de actas se conservan. El programa propone los números a partir de la legalización del año anterior y le pide, en cada libro, «**Legalizado antes hasta**» (la fecha de cierre del último legalizado, que Legalia2 exige cuando el número de libro no es el 1).
- **El IRUS** debe tener 13 cifras.
- **El presentante no se importa**: hay que escribirlo en Legalia2 (con el programa anterior pasaba lo mismo).
- La auditoría bloquea generar los libros si el ejercicio no está cerrado o si hay errores graves.
- Si ya legalizó el ejercicio con otro programa, **no lo envíe de nuevo**: pruebe el ZIP en Legalia2 en una carpeta de prueba, sin enviarlo.

## Depósito de cuentas

[Depósito de cuentas](pantalla:deposito-cuentas): una fila por ejercicio. Doble clic abre la pantalla de **Datos de cierre**, que se parece a la de D2, con lo que Conta ya sabe calculado.

### Antes del ZIP: los datos de cierre

- **Fechas** de formulación y de aprobación de las cuentas (el plazo del depósito corre desde la aprobación; si hay un acta de aprobación del año siguiente, se propone su fecha).
- **Personal** (número medio de empleados) y **órgano de administración** (miembros y mujeres, este año y el anterior).
- **Periodo medio de pago a proveedores**, en días, este año y el anterior.
- **Aplicación del resultado** y base de reparto.
- Lo demás de la memoria y de la certificación.

Los **controles** de arriba dicen qué falta: mientras haya **errores**, no se puede preparar el depósito.

### Cómo se hace

Conta tiene **cinco botones numerados**; entre medias hay pasos que se hacen en D2 o con su firma digital. En este orden:

| Orden | Dónde | Qué se hace |
|---|---|---|
| 1 | Conta | **1.- Preparar el depósito.** Crea el ZIP que importa D2: el formulario, el fichero XBRL de las cuentas y la memoria |
| 2 | Conta | **2.- Copiar el ZIP** a la carpeta `Registro Mercantil` de su carpeta de descargas |
| 3 | **D2** | Importe el ZIP, **corrija lo que D2 pida** y genere la **huella digital**. Conta **no puede calcularla**: D2 la saca de su propio ZIP |
| 4 | Conta | **3.- Guardar la huella y preparar la certificación.** Escriba la huella (o suba el `Huella.pdf` o `Huella.txt` que crea D2 en su carpeta «Presentacion»): Conta prepara el PDF de la **certificación** del acuerdo de la junta, que lleva esa huella |
| 5 | Conta | **4.- Copiar la certificación** a la misma carpeta |
| 6 | **Fuera de Conta** | **Firme** la certificación y, en D2 (sin cerrarlo), **envíe el depósito**: al presentarlo le pide la certificación firmada |
| 7 | Conta | **5.- Registrar el envío:** suba el «Acuse de recibo» que devuelve el Registro |

Los botones de Conta se marcan con ✓ al darlos.

### Qué hace falta saber

- **Si vuelve a preparar el depósito y el ZIP cambia**, la huella de D2 deja de valer: hay que importar de nuevo en D2 y volver a registrar la huella.
- **Los titulares reales** que pide D2 son los socios con **más del 25 %** del capital; los demás no se incluyen.
- Si D2 muestra un error obligatorio, apunte su código y corrija el dato en Conta (casi siempre en los datos de cierre o en la ficha de la empresa) y vuelva a preparar.
- Las cuentas se depositan en el **modelo de PYMES**: balance, cuenta de pérdidas y ganancias, estado de cambios en el patrimonio neto y memoria.
- Un depósito vencido se multa (de 1.200 a 60.000 €) y el Registro puede cerrar la hoja de la sociedad: el programa **vigila el plazo** y avisa una semana antes.
