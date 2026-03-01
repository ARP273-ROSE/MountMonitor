#!/usr/bin/env bash
# ============================================================
#  MountMonitor Launcher - Linux / macOS
#  Auto-detects Python, creates venv, installs dependencies
#  Usage: ./launch.sh [--repair] [--sim-all] [--sim-mount] ...
# ============================================================

set -e

MIN_MAJOR=3
MIN_MINOR=10
VENV_DIR="venv"
REQ_FILE="requirements.txt"
MAIN_SCRIPT="main.py"
REPAIR_MODE=0

# Parse --repair flag, pass rest to app
APP_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--repair" ]; then
        REPAIR_MODE=1
    else
        APP_ARGS+=("$arg")
    fi
done

echo ""
echo " ==================================================="
echo "  MountMonitor - Telescope Mount Monitor"
echo "  Launcher / Lanceur automatique"
echo " ==================================================="
echo ""

# Change to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ----------------------------------------------------------
#  Repair mode: delete venv and stamp to force full reinstall
# ----------------------------------------------------------
if [ "$REPAIR_MODE" -eq 1 ]; then
    echo " [REPAIR] Repair mode enabled / Mode reparation active"
    echo ""
    if [ -d "$VENV_DIR" ]; then
        echo " [REPAIR] Removing virtual environment..."
        echo "          Suppression de l'environnement virtuel..."
        rm -rf "$VENV_DIR"
        echo " [OK] Virtual environment removed / Environnement virtuel supprime"
    fi
    echo ""
fi

# ----------------------------------------------------------
#  Step 1/4: Find Python >= MIN_MAJOR.MIN_MINOR
# ----------------------------------------------------------
echo " [Step 1/4] Searching for Python... / Recherche de Python..."

check_version() {
    local cmd="$1"
    local version
    version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || return 1
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -gt "$MIN_MAJOR" ] 2>/dev/null; then
        return 0
    elif [ "$major" -eq "$MIN_MAJOR" ] && [ "$minor" -ge "$MIN_MINOR" ] 2>/dev/null; then
        return 0
    fi
    return 1
}

PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if check_version "$cmd"; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo " [!] Python ${MIN_MAJOR}.${MIN_MINOR}+ not found!"
    echo "     Python ${MIN_MAJOR}.${MIN_MINOR}+ introuvable !"
    echo ""

    # Detect OS and suggest/offer installation
    OS_TYPE="$(uname -s)"
    case "$OS_TYPE" in
        Linux*)
            if command -v apt &>/dev/null; then
                echo " Install with / Installer avec :"
                echo "   sudo apt update && sudo apt install python3 python3-venv python3-pip"
                echo ""
                read -rp " Install now? / Installer maintenant ? (Y/N): " INSTALL_CHOICE
                if [[ "$INSTALL_CHOICE" =~ ^[YyOo]$ ]]; then
                    echo ""
                    echo " [INFO] Installing Python..."
                    echo "        Installation de Python..."
                    sudo apt update && sudo apt install -y python3 python3-venv python3-pip
                    PYTHON_CMD="python3"
                fi
            elif command -v dnf &>/dev/null; then
                echo " Install with / Installer avec :"
                echo "   sudo dnf install python3 python3-pip"
                echo ""
                read -rp " Install now? / Installer maintenant ? (Y/N): " INSTALL_CHOICE
                if [[ "$INSTALL_CHOICE" =~ ^[YyOo]$ ]]; then
                    echo ""
                    echo " [INFO] Installing Python..."
                    sudo dnf install -y python3 python3-pip
                    PYTHON_CMD="python3"
                fi
            elif command -v pacman &>/dev/null; then
                echo " Install with / Installer avec :"
                echo "   sudo pacman -S python python-pip"
                echo ""
                read -rp " Install now? / Installer maintenant ? (Y/N): " INSTALL_CHOICE
                if [[ "$INSTALL_CHOICE" =~ ^[YyOo]$ ]]; then
                    echo ""
                    echo " [INFO] Installing Python..."
                    sudo pacman -S --noconfirm python python-pip
                    PYTHON_CMD="python3"
                fi
            else
                echo " Install Python ${MIN_MAJOR}.${MIN_MINOR}+ from / Installez depuis :"
                echo "   https://www.python.org/downloads/"
            fi
            ;;
        Darwin*)
            if command -v brew &>/dev/null; then
                echo " Install with Homebrew / Installer avec Homebrew :"
                echo "   brew install python@3.12"
                echo ""
                read -rp " Install now? / Installer maintenant ? (Y/N): " INSTALL_CHOICE
                if [[ "$INSTALL_CHOICE" =~ ^[YyOo]$ ]]; then
                    echo ""
                    echo " [INFO] Installing Python via Homebrew..."
                    echo "        Installation de Python via Homebrew..."
                    brew install python@3.12
                    PYTHON_CMD="python3.12"
                    if ! command -v "$PYTHON_CMD" &>/dev/null; then
                        PYTHON_CMD="python3"
                    fi
                fi
            else
                echo " Install Homebrew first / Installez d'abord Homebrew :"
                echo '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
                echo " Then / Puis : brew install python@3.12"
                echo ""
                echo " Or download from / Ou telecharger depuis :"
                echo "   https://www.python.org/downloads/"
            fi
            ;;
    esac

    if [ -z "$PYTHON_CMD" ]; then
        echo ""
        echo " Please install Python ${MIN_MAJOR}.${MIN_MINOR}+ and run this script again."
        echo " Installez Python ${MIN_MAJOR}.${MIN_MINOR}+ et relancez ce script."
        exit 1
    fi
fi

PY_VERSION=$("$PYTHON_CMD" --version 2>&1)
echo "            Found / Trouve : $PY_VERSION"
echo ""

# ----------------------------------------------------------
#  Step 2/4: Create or verify virtual environment
# ----------------------------------------------------------
echo " [Step 2/4] Checking virtual environment... / Verification environnement virtuel..."

VENV_OK=0
SKIP_VENV=""

if [ -f "$VENV_DIR/bin/python" ]; then
    # Verify venv is functional (not corrupted / not pointing to deleted Python)
    if "$VENV_DIR/bin/python" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
        VENV_OK=1
        echo "            OK"
    else
        echo "            Corrupted / Corrompu - recreating..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ "$VENV_OK" -eq 0 ]; then
    echo "            Creating... / Creation..."
    if ! "$PYTHON_CMD" -m venv "$VENV_DIR" 2>/dev/null; then
        echo " [!] Venv creation failed. Trying to install python3-venv..."
        echo "     Echec. Tentative d'installation de python3-venv..."
        if command -v apt &>/dev/null; then
            sudo apt install -y python3-venv
            "$PYTHON_CMD" -m venv "$VENV_DIR"
        else
            echo " [!] Cannot create venv. Running without it..."
            echo "     Impossible de creer le venv. Lancement sans..."
            SKIP_VENV=1
        fi
    fi
    if [ -z "$SKIP_VENV" ]; then
        echo "            Created / Cree"
    fi
fi

if [ -z "$SKIP_VENV" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
    PIP_CMD="$VENV_DIR/bin/pip"
else
    PIP_CMD="$PYTHON_CMD -m pip"
fi

# ----------------------------------------------------------
#  Step 3/4: Install dependencies
# ----------------------------------------------------------
echo ""
echo " [Step 3/4] Checking dependencies... / Verification des dependances..."

STAMP="$VENV_DIR/.deps_stamp"
NEED_INSTALL=0

if [ ! -f "$STAMP" ]; then
    NEED_INSTALL=1
elif [ "$REQ_FILE" -nt "$STAMP" ]; then
    NEED_INSTALL=1
fi

# Quick import check: verify key packages are importable
if [ "$NEED_INSTALL" -eq 0 ]; then
    if ! "$PYTHON_CMD" -c "import PyQt6, pyqtgraph, numpy, serial, ntplib" 2>/dev/null; then
        echo "            Missing packages detected / Paquets manquants"
        NEED_INSTALL=1
    fi
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    PKG_COUNT=$(grep -cve '^\s*$\|^\s*#' "$REQ_FILE" 2>/dev/null || echo "?")
    echo "            Installing $PKG_COUNT packages... this may take 1-2 minutes on first run"
    echo "            Installation de $PKG_COUNT paquets... 1-2 min au premier lancement"
    echo ""

    $PIP_CMD install --upgrade pip --quiet 2>/dev/null || true

    if ! $PIP_CMD install --progress-bar on -r "$REQ_FILE"; then
        echo ""
        echo " [!] Installation failed! Try: ./launch.sh --repair"
        echo "     Echec ! Essayez : ./launch.sh --repair"
        exit 1
    fi
    touch "$STAMP"
    echo ""
    echo " [OK] All dependencies installed / Toutes les dependances installees"
else
    echo "            Up to date / A jour"
fi

# ----------------------------------------------------------
#  Step 4/4: Launch MountMonitor
# ----------------------------------------------------------
echo ""
echo " ==================================================="
echo "  [Step 4/4] Launching MountMonitor... / Lancement..."
echo " ==================================================="
echo ""

"$PYTHON_CMD" "$MAIN_SCRIPT" "${APP_ARGS[@]}"
