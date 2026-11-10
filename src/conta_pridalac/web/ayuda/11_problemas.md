# Si algo no funciona

Los mensajes rojos del programa dicen **por qué** no se pudo hacer algo. Estas son las situaciones más habituales.

## Al abrir el programa

- **«No hace nada al pulsar el icono».** Probablemente ya está abierto: busque la pestaña del navegador (`http://127.0.0.1:8000`). Si no, repita la instalación con `instalar.bat` (Windows) o `bash instalar.sh` (Linux) (hay que hacerlo si se movió la carpeta del programa).
- **Pide una contraseña al entrar en una empresa.** Es la **contraseña de su certificado digital** (`.pfx`), la que se indica en la ficha de la empresa, porque esa empresa está protegida con certificado. Si no quiere esa protección, abra su ficha y elija **Sin protección**. Si la empresa tiene la protección sin configurar, el programa le lleva a la ficha para que indique el certificado o elija «Sin protección».
- **No sale una empresa en el inicio.** Cada empresa es un fichero `.sqlite` en la carpeta de datos (`datos_locales\bd`); si no está ahí, no aparece. Si el programa se arrancó con otra carpeta (`CONTA_DATOS`), mostrará las de esa.
- **La ventana de instalación se cierra con un error.** Copie sus mensajes; el registro del servidor está en `datos_locales\web.log`.

## Al trabajar

- **«El ejercicio está cerrado».** Un ejercicio cerrado no admite cambios. Si de verdad hay que tocarlo, reábralo en [Cierre del ejercicio](pantalla:ejercicios) (queda anotado) y vuelva a cerrarlo después.
- **«Esta base es una copia de ensayo…».** Está en una copia de ensayo, que no puede generar ficheros para la sede ni registrar presentaciones. Hágalo en la base real.
- **No puedo cerrar el ejercicio.** La auditoría tiene errores: ábrala y corrija cada uno ([Cierre y control](tema:cierre#auditoria-de-integridad)).
- **No me deja grabar un asiento.** Debe cuadrar (debe = haber) y sus cuentas deben ser subcuentas del plan.
- **Una factura aparece «posible duplicada».** Ya hay otra del mismo tercero, número e importe. Si es otra distinta, confirme «grabar de todos modos».
- **No puedo aplicar las propuestas en Recibidas del trimestre.** Quedan proveedores nuevos sin decidir ([paso 4 del trimestre](tema:trimestre#4-elegir-los-proveedores-nuevos)).
- **Un banco no cuadra.** Mire qué hay solo en uno de los lados ([Cuadre de bancos](tema:tesoreria#cuadre-de-bancos)); casi siempre falta una línea del extracto por contabilizar, o el extracto no está completo.
- **No encuentro un fichero que generé.** Se guarda en el almacén del programa y, con **Copiar para presentar**, se copia a su carpeta de descargas con un nombre claro (por ejemplo `EMPRESA_A_AEAT_303_2026_1T.303`). «Abrir la carpeta de copias» la abre.
- **Un modelo ya está «Presentado» y quiero cambiarlo.** Lo presentado no se toca: se presenta una rectificativa, complementaria o sustitutiva ([Los modelos de la AEAT](tema:modelos#rectificar-una-declaracion)).

## Con la sede de la AEAT

- **La sede rechaza el fichero.** Copie el **código y el texto** del mensaje. Suelen indicar la casilla o el dato que falla. Si es un error del programa, avíselo con ese mensaje.
- **Dice que ya constan declaraciones previas (40340).** Es el caso de un ejercicio ya presentado: el fichero está bien pero no se puede presentar otra vez como «normal». Para el modelo 200 de un ejercicio ya presentado, el fichero sirve solo para comprobar.
- **Dice que falta el CNAE, la persona de contacto, una página…** Complete el dato en la ficha de la empresa o en los datos de cierre y genere de nuevo.
- **No me deja presentar el 390 de 2026.** La sede todavía no admitía ese ejercicio en las pruebas de octubre de 2026; repita la prueba en enero.

## Datos y copias

- **He borrado algo sin querer.** Restaure la última copia de seguridad ([Copias de seguridad](tema:cierre#copias-de-seguridad)); antes de restaurar el programa hace una copia de lo que hay. Y mire el [Registro de cambios](pantalla:registro-cambios): dice qué se borró y cuándo.
- **Tras restaurar, faltan PDF de facturas.** La copia ligera no los lleva. Use «Recuperar justificantes» en [Copias de seguridad](pantalla:copias) e indique las carpetas donde los guarda (por ejemplo, las de su OneDrive): los busca por su contenido.
- **Copié el fichero de la base a mano y ahora la auditoría da un error.** Es lo esperado: el registro de cambios no ve una restauración hecha fuera del programa. Use siempre la pantalla de copias.
- **El plazo de un modelo sale «no confirmado».** La fecha de **domiciliación** de ese periodo es una estimación porque la AEAT todavía no ha publicado el calendario. El plazo de presentación es fiable.
- **Una cifra no coincide con el programa anterior o con lo presentado.** Mire las [declaraciones presentadas](pantalla:declaraciones) del modelo y compare casilla a casilla; las diferencias suelen venir de una factura que cayó en otro trimestre.

## Si no encuentra la respuesta

Use el **buscador** de la ayuda (arriba a la izquierda) con una palabra clave, y consulte el [Glosario](tema:glosario). Si hay un fallo del programa, copie el mensaje exacto y la pantalla en que ocurre.
