#!/usr/bin/env bash
# Instala Conta Pridalac en este equipo Linux: crea su entorno de Python, instala lo que necesita y deja el icono para abrirlo.
# Uso:    bash instalar.sh               (se puede repetir sin problema, p. ej. tras mover la carpeta)
#         bash instalar.sh sin-iconos    (no crea los iconos: para probar la instalacion)
# Equivale a instalar.bat de Windows. Probado en Ubuntu 24.04; en Debian, Linux Mint, Fedora, openSUSE y Arch propone los paquetes que le falten.
set -u
cd "$(dirname "$0")" || exit 1

echo
echo "=== Instalacion de Conta Pridalac ==="
echo

fallo() {
  echo
  echo "La instalacion ha fallado. Copie los mensajes de arriba y enviaselos a quien le ha pasado el programa."
  exit 1
}

# --- Python 3.11 o superior
PY=""
for c in python3 python; do
  if [ -z "$PY" ] && command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$c"
  fi
done
if [ -z "$PY" ]; then
  echo "No se encuentra Python 3.11 o superior."
  echo "Instalelo con el gestor de paquetes de su sistema (por ejemplo: sudo apt install python3 python3-venv python3-tk) y vuelva a ejecutar este fichero."
  exit 1
fi
echo "Python encontrado: $PY ($("$PY" --version 2>&1))"

# --- lo que Python necesita del sistema: venv (el entorno) y tkinter (el cuadro de «Abrir fichero»)
faltan=""
"$PY" -c 'import venv, ensurepip' >/dev/null 2>&1 || faltan="venv"
"$PY" -c 'import tkinter' >/dev/null 2>&1 || faltan="$faltan tkinter"

if [ -n "$faltan" ]; then
  echo
  echo "Faltan componentes de Python en el sistema:$faltan"
  orden=""
  if command -v apt-get >/dev/null 2>&1; then orden="sudo apt-get install -y python3-venv python3-tk"
  elif command -v dnf >/dev/null 2>&1; then orden="sudo dnf install -y python3 python3-tkinter"
  elif command -v zypper >/dev/null 2>&1; then orden="sudo zypper install -y python3 python3-tk"
  elif command -v pacman >/dev/null 2>&1; then orden="sudo pacman -S --needed --noconfirm python tk"
  fi
  if [ -z "$orden" ]; then
    echo "Instale python3-venv y tkinter con el gestor de paquetes de su sistema y vuelva a ejecutar este fichero."
    exit 1
  fi
  echo "Se instalan con:  $orden"
  if [ -t 0 ]; then
    read -r -p "Quiere que lo ejecute ahora (le pedira su contrasena)? [s/N] " respuesta
    case "$respuesta" in
      s|S|si|SI|Si|sí|Sí) $orden || fallo ;;
      *) echo "De acuerdo. Ejecute esa orden usted y vuelva a lanzar este fichero."; exit 1 ;;
    esac
  else
    echo "Ejecute esa orden y vuelva a lanzar este fichero."
    exit 1
  fi
  "$PY" -c 'import venv, ensurepip, tkinter' >/dev/null 2>&1 || { echo "Siguen faltando componentes de Python."; fallo; }
fi

# --- entorno
if [ ! -x ".venv/bin/python" ]; then
  echo "Creando el entorno..."
  "$PY" -m venv .venv || fallo
fi

echo "Instalando las dependencias (puede tardar un par de minutos)..."
.venv/bin/python -m pip install --upgrade pip --quiet || fallo
.venv/bin/python -m pip install -e . --quiet || fallo

echo "Comprobando la instalacion..."
.venv/bin/python -c "import tkinter, conta_pridalac.web.app" || fallo

# --- iconos
if [ "${1:-}" != "sin-iconos" ]; then
  echo "Creando los iconos (escritorio y menu de aplicaciones)..."
  .venv/bin/python tools/crear_acceso_directo.py --menu || fallo
fi

echo
echo "Listo. Abra Conta Pridalac con su icono (escritorio o menu de aplicaciones)."
echo "Si el icono del escritorio sale con un aviso, pulse con el boton derecho y elija «Permitir ejecutar»."
echo "Sin icono: .venv/bin/python -m conta_pridalac.lanzador"
if [ ! -d ".git" ]; then
  echo
  echo "Nota: esta carpeta no es un clon de git, asi que el programa no podra actualizarse solo (pantalla Programa)."
  echo "Para poder actualizarlo, instale con:  git clone https://github.com/krinda3/Conta_Pridalac.git"
fi
exit 0
