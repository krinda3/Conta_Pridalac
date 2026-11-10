# Instalación en otro equipo (Windows)

Probado el 29/10/2026 en un equipo «limpio» simulado: un clon nuevo del repositorio (sólo lo que está en git), un entorno de Python nuevo, los tests, el arranque con una carpeta de datos vacía, el lanzador y el icono.

## Qué hace falta

- **Windows 10 u 11.**
- **Python 3.11 o superior** de <https://www.python.org/downloads/>, marcando **«Add python.exe to PATH»** al instalarlo. Incluye `tkinter` (el cuadro de «Abrir fichero»), que el programa necesita.
- Un navegador (Edge, Chrome, Firefox…). Internet sólo hace falta durante la instalación.

No hace falta instalar nada más: las bibliotecas (FastAPI, SQLAlchemy, ReportLab…) las instala el propio `instalar.bat` en la carpeta del programa.

## Instalar

1. Traer el programa al equipo con `git clone https://github.com/krinda3/Conta_Pridalac.git C:\ContaPridalac` (mejor una ruta sin espacios ni acentos; el repositorio es privado: el equipo necesita las credenciales de GitHub). **Conviene clonarlo y no copiar la carpeta**: sólo un clon se puede actualizar desde el programa (pantalla *Programa*, en la pantalla de empresas).
2. Doble clic en **`instalar.bat`**. Crea el entorno (`.venv`), instala las dependencias, comprueba que todo importa y deja el icono **Conta Pridalac** en el escritorio y en el menú de inicio.
3. Abrir el programa con el icono. Se arranca solo y abre el navegador en <http://127.0.0.1:8000>; al cerrar la última pestaña, se apaga solo.

`instalar.bat` se puede repetir sin problema: hay que hacerlo si se mueve la carpeta (el icono apunta a la ruta de esa carpeta) o se borra `.venv`. Con `instalar.bat sin-iconos` no crea los iconos.

Si la instalación falla, la ventana no se cierra: hay que copiar los mensajes que muestra. El registro del servidor queda en `datos_locales\web.log`.

## Dónde quedan los datos

Todo lo del usuario vive en `datos_locales\` dentro de la carpeta del programa, que **no está en git**:

| Carpeta o fichero | Contenido |
|---|---|
| `bd\<empresa>.sqlite` | La contabilidad de cada empresa (una base por empresa) |
| `justificantes\` | Facturas y demás documentos adjuntos |
| `copias\` | Copias de seguridad (pantalla *Ejercicio → Copias de seguridad*): ligeras (unos pocos MB; sin los PDF de las facturas, que se recuperan por su contenido desde las carpetas de trimestre) o completas |
| `bd\_preferencias.json` | Tema, disposición del menú y última caja abierta |

**La carpeta de datos se puede cambiar.** La ubicación se guarda **fuera** de la carpeta de datos, en `%APPDATA%\ContaPridalac\ubicacion.json` (Windows) o `~/.config/conta-pridalac/ubicacion.json` (Linux); la variable de entorno `CONTA_DATOS` (la carpeta `bd`) tiene prioridad sobre ella. Desde la pantalla de empresas, **Carpeta de datos** permite usar otra carpeta con datos o **mover** los datos (copiar, verificar y cambiar; la antigua no se borra). Si no encuentra los datos al arrancar, pregunta dónde están en vez de ofrecer crear una empresa.

**Candado.** Para no abrir los mismos datos desde dos equipos a la vez (lo que corrompería las bases si la carpeta se sincroniza), Conta deja `conta.lock` en la carpeta de datos y renueva su señal cada 20 s; si otro equipo lo tiene, no se abre y ofrece reintentar o forzar (escribiendo FORZAR). Con `--sin-candado` no se pone (sólo pruebas). No es perfecto: la sincronización tarda en llegar a otros equipos, así que hay que cerrar Conta y esperar a que termine antes de abrirlo en otro ordenador.

Para llevar los datos a otro equipo basta una copia de seguridad desde esa pantalla y restaurarla allí. Una copia en el mismo disco no protege de un fallo del disco: conviene copiar los `.zip` a otro sitio.

## Crear la primera empresa

En la pantalla de inicio, **Añadir empresa**. Hay dos caminos:

- **Empresa nueva**: nace vacía con el plan de cuentas del PGC de PYMES o con el de entidades sin fines lucrativos (ONG, fundaciones, asociaciones: se elige en «Plan de cuentas»), los tipos de IVA habituales y las cuentas que necesita el programa. Se elige el nombre, el NIF, el año del primer ejercicio y los **dígitos de las subcuentas** (6 a 10; se eligen ahora y no se pueden cambiar).
- **Desde una copia de Gestión MGD**: se sube el `.zip` de la copia de seguridad, el programa enseña lo que contiene (asientos, justificantes, año, dígitos de las cuentas, que se conservan) y, al confirmar, crea la empresa.

Al crear la empresa se elige su **protección de acceso**: *sin protección* (se abre directamente) o *con certificado digital*; con certificado, se abre su ficha para indicar el `.pfx` y su contraseña, que será la de entrada. Se puede cambiar después, en la ficha. Es una barrera de pantalla, no un cifrado de los datos. Para probar sin ninguna exigencia, se arranca el programa a mano con `.\.venv\Scripts\python -m conta_pridalac.web --sin-certificado` y se abre http://127.0.0.1:8000.

### Con la herramienta de línea de órdenes

Lo mismo que el segundo camino, sin pantalla. Hace falta la copia de seguridad de MGD (el `.zip` o su carpeta) en el equipo. Desde la carpeta del programa, en PowerShell:

```powershell
.\.venv\Scripts\python tools\importar_mgd.py "C:\ruta\copia de MGD.zip" --nombre "Nombre de la Empresa S.L." --nif B12345678
```

Hay que dar la **ruta completa** del `.zip`: en el Explorador, se selecciona el fichero y se pulsa Ctrl+Mayús+C, y se pega en la orden (o se arrastra el fichero a la ventana de PowerShell). Esa orden **sólo mira la copia** y dice qué haría: cuántos asientos y justificantes tiene, el año, y los dígitos de las subcuentas, que son los de su plan de cuentas (no se convierten ni se inventan cuentas). Si todo es correcto, se repite añadiendo `--aplicar`:

```powershell
.\.venv\Scripts\python tools\importar_mgd.py "C:\ruta\copia de MGD.zip" --nombre "Nombre de la Empresa S.L." --nif B12345678 --aplicar
```

La empresa aparece al refrescar la pantalla de inicio del programa. Opciones: `--plan esfl` (entidad sin fines lucrativos; por defecto `pymes`), `--anio` (por defecto el de los apuntes), `--slug` (el nombre interno, por defecto sale del nombre), `--codigo` (el número de empresa de MGD) y `--digitos` (para forzar otros dígitos). Nunca sustituye una empresa que ya exista; si falla a medias, no deja la empresa creada.

Para quitar una empresa de prueba: cerrar el programa y borrar su `datos_locales\bd\<slug>.sqlite` y su carpeta en `datos_locales\justificantes`.

## Actualizar el programa

Con el programa instalado como clon de git, la pantalla **Programa** (en la pantalla de empresas, la primera que se ve al abrir Conta) busca cambios nuevos en GitHub y los descarga:

1. **Buscar actualizaciones** lista lo nuevo sin cambiar nada.
2. **Actualizar ahora…** pide confirmación, hace una copia de seguridad ligera de cada empresa y descarga los cambios (`git pull --ff-only`; si cambió `pyproject.toml`, reinstala las dependencias).
3. Cerrar el programa y volver a abrirlo. Los datos (`datos_locales\`) no se tocan; las bases añaden solas las columnas nuevas.

Se niega a actualizar si hay ficheros del programa modificados a mano o si la copia de seguridad falla. Si algo sale mal, el servicio está en `servicios/actualizar_programa.py` y se puede hacer a mano con `git pull` en la carpeta del programa.

Si el programa no es un clon (se copió la carpeta), se sustituyen los ficheros a mano y se ejecuta otra vez `instalar.bat`; `datos_locales\` no se toca.

## Instalar en Linux

Probado en **Ubuntu 24.04** (Python 3.12): instalación con `instalar.sh`, arranque con el lanzador, cierre, y la suite de tests entera. Debería valer igual en Debian, Linux Mint, Fedora, openSUSE y Arch: si falta algo del sistema, el instalador dice qué paquete y con qué orden se instala.

1. **Traer el programa** con git, igual que en Windows (el repositorio es privado: el equipo necesita las credenciales de GitHub):

   ```bash
   git clone https://github.com/krinda3/Conta_Pridalac.git ~/ContaPridalac
   ```

2. **Instalar.** En la carpeta del programa:

   ```bash
   cd ~/ContaPridalac
   bash instalar.sh
   ```

   Comprueba que hay Python 3.11 o superior, crea el entorno (`.venv`), instala las dependencias, comprueba que todo importa y deja el icono **Conta Pridalac** en el escritorio y en el menú de aplicaciones.
   - Si faltan `python3-venv` o `python3-tk` (el cuadro de «Abrir fichero» del certificado lo necesita), lo dice y ofrece ejecutar la orden de instalación de su sistema (pide la contraseña). En Ubuntu y Debian: `sudo apt install python3-venv python3-tk`.
   - Se puede repetir sin problema: hay que hacerlo si se mueve la carpeta (el icono apunta a la ruta de esa carpeta) o se borra `.venv`. Con `bash instalar.sh sin-iconos` no crea los iconos.

3. **Abrir** con el icono. Se arranca solo y abre el navegador en <http://127.0.0.1:8000>; al cerrar la última pestaña, se apaga solo. En GNOME, si el icono del escritorio sale con un aviso, botón derecho → «Permitir ejecutar». Sin icono: `.venv/bin/python -m conta_pridalac.lanzador` (y `--parar` para cerrarlo).

Lo demás es igual que en Windows: los datos viven en `datos_locales/` dentro de la carpeta del programa, el registro del servidor está en `datos_locales/web.log`, las copias se hacen desde *Ejercicio → Copias de seguridad* (y se pueden restaurar entre Windows y Linux: son ficheros `.zip` con la base de SQLite), y **se actualiza desde *Programa*** (pantalla de empresas).

**Particularidades de Linux:**
- Los ficheros para presentar se copian a la carpeta de descargas del usuario (`xdg-user-dir DOWNLOAD`, normalmente `~/Descargas` o `~/Downloads`), en la subcarpeta *Conta Pridalac*.
- «Abrir la carpeta» usa `xdg-open`.
- El certificado digital (`.pfx`) se elige con el cuadro de ficheros de tkinter; la ruta puede escribirse también a mano.
- El arranque automático al iniciar sesión (opcional): `.venv/bin/python tools/crear_acceso_directo.py --arranque`.

## Lo que todavía no se puede hacer en un equipo nuevo

- **Entidades sin fines lucrativos**: tienen su plan de cuentas, su balance y su cuenta de resultados (según el BOE), todavía por validar con los estados reales de una ONG. No tienen memoria ni modelo 200. Tampoco está hecho el plan de un autónomo.
- **macOS**: no probado (Linux sí: véase arriba).
- **Instalador de doble clic sin Python** (PyInstaller e Inno Setup): sólo si instalar Python resulta un obstáculo.
