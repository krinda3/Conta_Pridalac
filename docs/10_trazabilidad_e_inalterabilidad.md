# 10 · Trazabilidad e inalterabilidad de los registros contables

*Hoja para enseñar si alguien pregunta cómo evita Conta-Pridalac la contabilidad paralela. Redactada el 31/10/2026; no es asesoramiento jurídico.*

## Qué se exige
El art. 29.2.j de la Ley General Tributaria (según la Ley 11/2021, antifraude) obliga a que los programas que soportan la contabilidad garanticen la **integridad, conservación, accesibilidad, legibilidad, trazabilidad e inalterabilidad** de los registros: nada se altera, omite o interpola sin que quede la debida anotación en el propio sistema. Se sanciona tener o usar programas que permitan llevar contabilidades distintas o manipular datos sin dejar rastro. Para la contabilidad no hay un reglamento técnico ni una certificación como la de la facturación (Verifactu, que no aplica aquí: Conta no emite facturas, sólo carga las que emite la aplicación de la AEAT).

## Qué hace el programa
1. **Anota todo cambio.** Cada alta, modificación y borrado de asientos, apuntes, facturas, cuentas, terceros, bancos, vencimientos, bienes, declaraciones, extractos y datos de la empresa queda anotado con fecha, usuario del sistema, tabla y fila, el antes y el después y, en los borrados, la fila entera. Va en la misma transacción que el cambio: si el cambio se deshace, la anotación también. Es independiente de la pantalla o función que lo haga (se engancha a la capa de base de datos). Pantalla: *Ejercicio → Registro de cambios*.
2. **No se puede modificar el registro.** La base rechaza `UPDATE` y `DELETE` sobre la tabla `registro_cambios`, y el programa sólo la añade. Cada anotación lleva el SHA-256 de su contenido y de la anterior (cadena de huellas): cualquier retoque posterior rompe la cadena desde ese punto.
3. **La huella también se guarda fuera de la base.** En cada copia de seguridad, restauración, presentación registrada y cierre o reapertura de ejercicio se añade una línea (fecha, motivo, nº de anotación y huella) a `huellas_registro_NNN.txt`, en el almacén de justificantes, fuera de la base y de las copias, con su propia cadena de huellas. Una copia se lleva también a la carpeta de la empresa en OneDrive.
4. **Se comprueba solo.** La *Auditoría de integridad* verifica la cadena y contrasta cada huella externa con la base; si no cuadra, es un **error**. Si no cuadra, se conserva la base tal cual y se compara con una copia anterior.
5. **Sin contabilidad paralela.** Hay una sola base real por empresa. Las copias para ensayar se marcan como **COPIA DE ENSAYO** (marca irreversible, aviso en todas las pantallas): no pueden generar ficheros para la sede ni registrar presentaciones, y sólo en ellas se puede usar la herramienta que borra facturas para ensayar. Lo presentado a la AEAT queda además con su justificante, su CSV y la huella del fichero.
6. **Cierre de ejercicio.** Un ejercicio cerrado no admite cambios; reabrirlo es un cambio más del registro, con su línea de huella externa.

## Límites (a decir con franqueza)
- Quien tenga el archivo de la base y sepa lo que hace podría reescribir toda la cadena; lo cubren las huellas externas y las copias de OneDrive, que habría que alterar también.
- No se anota lo que se escribe con SQL directo fuera del programa (migraciones) ni los borrados en cascada que hace la base. No se anotan las lecturas.
- Una restauración a mano (copiando el archivo sin usar la pantalla de copias) no deja línea y la auditoría dará error: es lo esperado.
- El usuario es el del sistema operativo; no hay usuarios ni contraseñas propias.
- No hay certificación oficial para software de contabilidad: esto es un diseño razonado que se puede explicar y verificar, no un sello.

## Dónde está en el código
`db/registro.py` (anotaciones, cadena, verificación) · `servicios/huellas.py` (huellas externas) · `servicios/entorno.py` (copias de ensayo) · `auditoria.py` (comprobaciones `registro_de_cambios_roto` y `huellas_externas_no_coinciden`) · `web/registro_cambios.py` (pantalla). Tests: `tests/test_registro_cambios.py`, `test_huellas_externas.py`, `test_entorno_ensayo.py`.
