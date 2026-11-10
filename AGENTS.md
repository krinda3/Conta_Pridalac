# AGENTS.md — Conta-Pridalac

## Objetivo del proyecto
Contabilidad local escrito en Python a pertir de Gestión MGD con mejoras segun mi necesidad:
presentación de modelos a la AEAT con trazabilidad, libros y cuentas al Registro Mercantil y un flujo de trabajo trimestral centrado en la conciliación de extractos bancario. 
Lo usa **Javier**; otras personas lo instalarán en su equipo con sus propias empresas.

## Estado y plan
El estado, las decisiones (D1…D19…) y el backlog están en `docs/00_plan_de_trabajo.md`: **léelo antes de cambiar nada importante** y actualízalo al terminar un paso.
Hecho: motor contable, facturas, tesorería, bienes de inversión, cierre, estados contables (PYMES y ONG), modelos 303, 111, 190 y 347, alta de empresa, importación de MGD, copias, menú.
Pendiente (en este orden aproximado): Verifactu, modelos 390, 202 y 200, Registro Mercantil, control de cambios de normativa, autónomos, Linux y, **al final**, la ayuda del programa.

## Entorno
- **Python ≥ 3.11** (se usa 3.13). Venv en `.venv`. Instalar: `.\.venv\Scripts\python -m pip install -e ".[dev]"`. Tests: `.\.venv\Scripts\python -m pytest -q -p no:warnings`.
- Windows (desarrollo y uso). La herramienta Bash del agente es Git Bash: usa `.venv/Scripts/python.exe`. Linux sin probar.
- Arrancar: `python -m conta_pridalac.web` (http://127.0.0.1:8000; `--sin-certificado` sólo para pruebas). Variables: `CONTA_DATOS`, `CONTA_ALMACEN`, `CONTA_COPIAS`, `CONTA_DESCARGAS`, `CONTA_PUERTO`.
- **Dependencias**: sqlalchemy, dbfread, openpyxl, reportlab, pypdf, fastapi, uvicorn, jinja2, python-multipart, cryptography. No añadir más sin justificarlo.

## Arquitectura
FastAPI + HTMX (el servidor pinta el HTML; sin SPA) sobre SQLite, una base por empresa (`datos_locales/bd/<slug>.sqlite`).

```
src/conta_pridalac/
├── db/             modelos.py (SQLAlchemy 2), sesion.py (crear_esquema, actualizar_esquema), integridad.py, tipos.py (Dinero)
├── domain/         reglas puras sin base de datos: facturas, tesorería, amortización, fechas, pgc.py y pgc_esfl.py (generado)
├── servicios/      casos de uso (reciben una Session): facturas, tesorería, cierre, modeloNNN, presentacionNNN, estados, alta_empresa…
├── ficheros_aeat/  ficheroNNN.py: generadores byte a byte de los ficheros de la AEAT + diseños (json)
├── migracion/      mgd.py, programa_anterior.py, declaracionesNNN.py, comprobantes.py
├── exportacion/    a_pdf, a_excel
└── web/            app.py (rutas), listados.py (componente de tabla), definiciones.py (listados y menú CAJAS), un módulo por pantalla, plantillas/, static/
tools/              scripts de línea de órdenes (importar, comparar con el programa anterior, corregir): por defecto SOLO simulan; cambian datos con --aplicar
tests/              pytest (un fichero por tema; los de datos reales llevan @pytest.mark.datos_reales y se omiten si faltan)
```

### Modelo de datos (lo esencial)
- `Empresa` (`digitos_cuenta`, `tipo_plan` «pymes» o «esfl», certificado `.pfx` sólo como ruta), `Ejercicio`, `Cuenta`, `Parametro` (PYG, IVA_DEBE, IVA_HABER, PTE_APLIC), `Tercero` (cliente, proveedor…).
- `Asiento`/`Apunte` (tipos 1 emitidas, 2 recibidas, 3 tesorería, 4 general, 9 automático; subtipos A apertura, R regularización, Z cierre), `Factura`/`FacturaIva`/`FacturaAjuste`, `Vencimiento`/`Pago`, `Banco`/`MovimientoBanco`, `BienInversion`.
- `PresentacionAeat` (+ eventos) y `DeclaracionPresentada`: el ciclo borrador → fichero → presentado de cada modelo, y lo ya presentado (también importado).
- Importes con el tipo `Dinero` (céntimos enteros): nunca `float`. Columnas nuevas: con valor por defecto, y `actualizar_esquema` las añade a las bases existentes (no hay migraciones).

## Reglas del dominio que no se negocian
1. **Los dígitos de las subcuentas son de cada empresa** (`Empresa.digitos_cuenta`, 8 por defecto, se fijan al crearla). No escribas `8` ni códigos de 8 dígitos en el código: usa `servicios/cuentas.digitos_de`, `cuenta_estandar` o `NIVEL_SUBCUENTA`.
2. **El plan de cuentas depende de `tipo_plan`**: nombres con `nombre_pgc(codigo, tipo_plan)`; los estados oficiales con el modelo de su plan (`cuentas_anuales` para PYMES, `cuentas_anuales_esfl` para ONG).
3. **Los estados contables excluyen siempre los asientos R y Z** (regularización y cierre) y las cuentas sin línea salen en `sin_asignar`, nunca se pierden en silencio.
4. **Nada puede grabar un asiento descuadrado**; la auditoría de integridad es obligatoria antes de cerrar.
5. **Lo presentado no se toca** (D19): una factura de un trimestre con 303 presentado no se edita, borra ni se le añaden otras (`servicios/bloqueo.py`).
6. **El programa no presenta nada por su cuenta** (D18, «plan B»): genera y verifica el fichero; el usuario lo importa en la sede con su certificado y registra aquí la presentación subiendo el PDF de la sede (se comprueba que su justificante coincide con el del fichero).
7. **Cada empresa exige su certificado digital** (`.pfx` fuera del repositorio; su contraseña se comprueba abriéndolo, nunca se guarda).
8. **Un fichero de la AEAT se valida contra los reales** de `AEAT/` (fuera de git): generar el mismo fichero byte a byte (190 y 347 lo cumplen con 8 ficheros cada uno) antes de dar un modelo por bueno.
9. **Fechas**: se teclean `DDMMAA`/`DDMMAAAA`/`D/M…`; en el 347 el trimestre sale de la **fecha contable**, no de la de la factura. Plazos y vigilancia en `servicios/plazos.py` y `vigilancia.py`.
10. **Los datos reales no entran en git** (`datos_locales/`, `AEAT/`, `docs/Exportaciones del programa anterior/`, `*.sqlite`, `*.txt`). Si escribes un documento, que sea `.md`.

## Interfaz
- **Todos los listados** siguen `docs/03_principios_de_diseno.md`: todos los campos, doble clic para editar, columnas ordenables y redimensionables, Añadir, Borrar, PDF y Excel. Se hacen con una subclase de `Listado` (`web/listados.py`) registrada en `web/definiciones.py`.
- **El menú** son cajas (`CAJAS` en `definiciones.py`); **cada opción lleva su explicación visible debajo** y no se pierde en ningún rediseño. Lo que aún no existe sale como «próximamente».
- UI y textos en español, con lenguaje claro para un contable. Colores sólo como variables (`web/tema.py`). Preferencias de pantalla (tema, disposición del menú, última caja) las guarda el servidor, no el navegador.
- Un error de formulario se muestra y no deja nada grabado; los avisos que se pueden confirmar usan una casilla «Grabar de todos modos».
- **La ayuda** son los temas Markdown de `web/ayuda/NN_tema.md` (`web/ayuda.py`; botón «?» de la barra, buscador). El menú y los avisos de la auditoría **se generan solos** en ella (`@@MENU@@`, `@@AUDITORIA@@`); lo demás se escribe a mano. **Quien cambie una pantalla, un modelo o un flujo actualiza su tema de ayuda en el mismo cambio**; `tests/test_ayuda.py` comprueba que los enlaces entre temas y a pantallas no se rompen, y que cada aviso de la auditoría tiene explicación (hay que añadirlo a `CATALOGO` en `web/auditoria.py`).

## Cómo se añade un modelo de la AEAT
Sigue el molde de 303, 111, 190 y 347 y valida contra los ficheros reales:
1. `ficheros_aeat/ficheroNNN.py` (+ diseño de registro) y `tools/comparar_NNN.py`.
2. `servicios/modeloNNN.py` (cálculo desde los libros) y `servicios/presentacionNNN.py` (controles, borrador, fichero, presentado, justificante).
3. `web/modeloNNN.py` + `plantillas/_modeloNNN.html`, la entrada en `CAJAS` y las rutas de fichero, carpeta y justificante en `app.py`.
4. `migracion/declaracionesNNN.py` + `tools/importar_NNN_presentados.py` para lo ya presentado, y el plazo en `servicios/plazos.py`.
5. Tests: `test_ficheroNNN`, `test_modeloNNN`, `test_presentacionNNN`, `test_web_modeloNNN`, `test_importar_NNN`; y un párrafo en el plan con lo validado y lo asumido.
6. Su apartado en la ayuda (`web/ayuda/07_modelos.md` o `08_sociedades.md`) y su fila en el catálogo de normativa (`CATALOGO` en `servicios/normativa.py`: versión del diseño, ventana del año y dirección en la sede si se puede sondear).
Antes de implementar, comprueba el diseño de registro vigente en la sede y anota su versión y fecha de consulta en el plan.

## Convenciones de código
- Servicios reciben la `Session`; no hacen `commit` salvo que lo digan (lo hace la pantalla o la herramienta). Escrituras múltiples, en una transacción.
- Los ficheros de código usan CRLF: al editarlos con scripts, conserva los saltos de línea de cada fichero (lee y escribe con `newline=""`).
- En consola de Windows (cp1252) no imprimas caracteres fuera de esa página (flechas, etc.) desde las herramientas.
- Un fallo se arregla en su causa; si encuentras uno de otra funcionalidad, dilo y arréglalo con su test.
- Tests con datos sintéticos siempre que se pueda; cada pantalla nueva, con su test web (`TestClient`) y, si es visual, comprobada en el navegador.

## Forma de trabajo con Javier
- **Javier hace los commits y el push.** No hagas `git commit` ni `git push`. Al terminar un paso, da los comandos exactos en dos bloques: `git add <ficheros concretos>` y `git commit -m "…" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`. **Nunca incluyas `.gitignore`** (tiene ediciones suyas).
- **Paso a paso**: un cambio cada vez, con tests; presenta los cambios de datos antes de aplicarlos (las herramientas simulan por defecto y se aplican con `--aplicar`).
- Lo irreversible (presentaciones reales, borrados de datos) se confirma siempre. Avisa antes de buscar fuera de la carpeta del proyecto.
- Responde en español. Si algo falla por tu causa, dilo.
- La ayuda del programa y los modelos 390, 202 y 200 van **al final**; antes, lo que desbloquee a otras personas o evite errores de datos.

## Git y repositorio
- Rama `main`; remoto en GitHub (`krinda3/Conta_Pridalac`).
- `.gitignore`: `datos_locales/`, `AEAT/`, `docs/_muestras/`, `docs/_manual/`, `docs/Exportaciones del programa anterior/`, `*.sqlite`, `*.db`, `*.txt`, `.venv/`, cachés.
- Revisar los documentos de `docs/` antes de publicar el repositorio: citan ejemplos reales puntuales.
