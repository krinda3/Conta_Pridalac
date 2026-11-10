# Conta-Pridalac

Conta Pridalac es un programa Contabilidad local en Python, que parte de el programa Gestión MGD y se complementa con la presentación de modelos de Hacienda, legalizacion de cuentas en el Registro Mercantil y un pequeño flujo de trabajo trimestral de conciliacion de extractos bancarios:

Es un programa **web local**: se ejecuta en el propio equipo, se abre en el navegador (http://127.0.0.1:8000) y los datos no salen de él.
Cada empresa es un fichero SQLite propio y se abre con la contraseña de su certificado digital.

Plan de trabajo y decisiones: [docs/00_plan_de_trabajo.md](docs/00_plan_de_trabajo.md) · Reglas para quien trabaje en el código: [AGENTS.md](AGENTS.md)

## Qué hace hoy

- **Contabilidad**: plan de cuentas con los dígitos que se elijan por empresa (8 por defecto), asientos y plantillas, diario, mayor, balance de sumas y saldos,
  cierre y apertura del ejercicio, auditoría de integridad.
- **Facturas recibidas y emitidas** con IVA multitipo, recargo de equivalencia, retenciones, vencimientos con su banco o tarjeta, justificantes en PDF o JPG y aviso de duplicadas.
- **Tesorería**: bancos, vencimientos, cobros y pagos, transferencias, partidas pendientes de aplicar.
- **Bienes de inversión** y cuadros de amortización, con su libro y la regularización del IVA.
- **Estados contables**: saldos acumulados, balance de situación, pérdidas y ganancias, y los modelos oficiales de **PYMES** (balance, PyG y estado de cambios en el patrimonio neto)
  y de **entidades sin fines lucrativos** (balance y cuenta de resultados, aún por validar con datos reales de una ONG).
- **Ayuda integrada** (botón **?**): temas, buscador y partes generadas del propio programa; **control de cambios normativos** (pantalla *Normativa y diseños*, con sondeo de la sede).
- **Registro Mercantil**: libros de socios y de actas, legalización de libros (Legalia2) y depósito de cuentas (D2).
- **Modelos de la AEAT**: **303, 111, 115, 190, 180, 347, 390, 202 y 200** (el 200, del ejercicio 2025). Cada uno con su cálculo desde los libros, controles, fichero para la sede, registro de lo presentado con su justificante,
  importación de lo ya presentado y vigilancia de plazos. El fichero se importa en la sede con el certificado: el programa no envía nada por su cuenta.
- **Empresas**: alta desde la pantalla (con el plan del PGC de PYMES o el de entidades sin fines lucrativos) o desde una copia de Gestión MGD; ficha con certificado digital;
  copias de seguridad con verificación; tema claro, oscuro o automático y menú en cajas.

## Qué falta

Registro de la presentación del modelo **200** con el PDF de la sede (cuando haya diseño de 2026); los casos del 200 sin probar en la sede (resultado a ingresar, correcciones manuales, deducciones); autónomos.
El orden y el estado de cada punto están en el plan de trabajo.

## Instalación (Windows)

Hace falta Python 3.11 o superior (marcando «Add python.exe to PATH» al instalarlo). Descomprima el programa en una carpeta, haga doble clic en `instalar.bat` y abra
**Conta Pridalac** con el icono que deja en el escritorio. Detalles, copias de seguridad y cómo crear la primera empresa: [docs/08_instalacion.md](docs/08_instalacion.md).

## Uso

```powershell
.\.venv\Scripts\python -m conta_pridalac.web                    # http://127.0.0.1:8000
.\.venv\Scripts\python -m conta_pridalac.web --sin-certificado  # sólo para pruebas: no exige el certificado de la empresa
.\.venv\Scripts\python -m conta_pridalac.lanzador --parar       # cierra el programa si está en marcha
```

Opciones de arranque: `--datos` (carpeta de las bases), `--almacen` (justificantes), `--puerto` y `--autoapagar` (se cierra al cerrar la última pestaña; lo usa el icono).
Variables de entorno: `CONTA_DATOS`, `CONTA_ALMACEN`, `CONTA_COPIAS`, `CONTA_DESCARGAS` y `CONTA_PUERTO`.

Los datos del usuario viven en `datos_locales/` (fuera de git): `bd/<empresa>.sqlite`, `justificantes/` y `copias/`.

## Desarrollo

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
```

Los tests que necesitan datos reales (`@pytest.mark.datos_reales`) leen dos copias de MGD 2021 y se omiten si no están: la de Empresa A en `D:\Proyectos\GestionMGD Access\BBDD 2021`
(o `CONTA_MGD_2021`) y la de Empresa B en `datos_locales/mgd_empresa_b_2021` (o `CONTA_MGD_EMPRESA_B_2021`).

### Estructura

```
src/conta_pridalac/
├── db/             modelos SQLAlchemy 2, sesión y comprobaciones de integridad
├── domain/         reglas puras: asientos de factura, tesorería, amortización, fechas, PGC
├── servicios/      casos de uso: facturas, tesorería, cierre, modelos 303/111/190/347, estados contables, alta de empresa…
├── ficheros_aeat/  generadores de los ficheros de registro de la AEAT y sus diseños
├── migracion/      cargadores de Gestión MGD y el programa anterior y de las declaraciones ya presentadas
├── exportacion/    PDF y Excel de los listados
├── web/            FastAPI + HTMX: pantallas, listados, plantillas y estáticos
├── lanzador.py     arranque y parada del programa (el icono del escritorio)
tools/              herramientas de línea de órdenes: importaciones, comparaciones con el programa anterior, correcciones
tests/              pytest
docs/               plan de trabajo, diseño y documentación
```

## Documentación

| Documento | Contenido |
|---|---|
| [00_plan_de_trabajo.md](docs/00_plan_de_trabajo.md) | Hitos, decisiones, resultados de cada fase y backlog |
| [03_principios_de_diseno.md](docs/03_principios_de_diseno.md) | Normas comunes a todas las pantallas |
| [05_auditoria_de_integridad.md](docs/05_auditoria_de_integridad.md) | Comprobaciones de la auditoría |
| [06_interfaz_web.md](docs/06_interfaz_web.md) | Cómo está hecha la interfaz y lo que se validó |
| [07_rediseno_del_menu.md](docs/07_rediseno_del_menu.md) | El menú en cajas y la estructura del programa anterior como referencia |
| [08_instalacion.md](docs/08_instalacion.md) | Instalar en otro equipo, crear empresas y actualizar |
| `pseudocodigo/`, `esquema_tablas.md`, `mapa_codigo.md` | Análisis del programa original (Gestión MGD) |

## Datos y privacidad

El repositorio **no** contiene datos fiscales: `.gitignore` excluye `datos_locales/`, `AEAT/` (ficheros presentados y diseños), las exportaciones del programa anterior y el manual.
Ojo: los documentos de `docs/` citan algunos ejemplos puntuales (nombres de terceros, importes de facturas), así que **hay que revisarlos antes de publicar el repositorio en ningún sitio**.
Los certificados digitales y las credenciales no deben entrar nunca en el repositorio.
