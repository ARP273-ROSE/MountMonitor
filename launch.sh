#!/bin/bash
# MountMonitor Launcher for Linux/macOS
# Detects Python, creates venv if needed, installs dependencies, and launches

echo "MountMonitor - Telescope Mount Monitor"
echo "========================================"

# Check for Python 3
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        version=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ not found"
    echo "Please install Python 3.11+ from https://python.org"
    exit 1
fi

echo "Using $PYTHON ($($PYTHON --version))"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install/update dependencies
pip install -q -r requirements.txt 2>/dev/null

# Parse arguments
SIM_ARG=""
case "$1" in
    simAll) SIM_ARG="--sim-all" ;;
    simMount) SIM_ARG="--sim-mount" ;;
    simSeismometer) SIM_ARG="--sim-seismometer" ;;
esac

# Launch
echo "Starting MountMonitor..."
python main.py $SIM_ARG
