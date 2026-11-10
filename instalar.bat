@echo off
rem Instala Conta Pridalac en este equipo: crea su entorno de Python, instala lo que necesita y deja el icono para abrirlo.
rem Uso: doble clic. Se puede repetir sin problema (por ejemplo tras mover la carpeta).
rem Con el argumento "sin-iconos" no crea los iconos (para probar la instalacion).
setlocal
cd /d "%~dp0"
echo.
echo === Instalacion de Conta Pridalac ===
echo.

set PY=
for %%C in (py python) do (
  if not defined PY (
    %%C -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set PY=%%C
  )
)
if not defined PY goto sinpython

echo Python encontrado: %PY%
if not exist ".venv\Scripts\python.exe" (
  echo Creando el entorno...
  %PY% -m venv .venv || goto error
)

echo Instalando las dependencias ^(puede tardar un par de minutos^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -e . --quiet || goto error

echo Comprobando la instalacion...
".venv\Scripts\python.exe" -c "import tkinter, conta_pridalac.web.app" || goto error

if /i "%~1"=="sin-iconos" goto fin
echo Creando los iconos ^(escritorio y menu de inicio^)...
".venv\Scripts\python.exe" tools\crear_acceso_directo.py --menu || goto error

:fin
echo.
echo Listo. Abra Conta Pridalac con su icono del escritorio.
if /i not "%~1"=="sin-iconos" pause
exit /b 0

:sinpython
echo No se encuentra Python 3.11 o superior.
echo Instalelo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH" y vuelva a ejecutar este fichero.
if /i not "%~1"=="sin-iconos" pause
exit /b 1

:error
echo.
echo La instalacion ha fallado. Copie los mensajes de arriba y enviaselos a quien le ha pasado el programa.
if /i not "%~1"=="sin-iconos" pause
exit /b 1
