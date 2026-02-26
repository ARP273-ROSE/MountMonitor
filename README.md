![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue)

**Real-time telescope mount monitoring for astrophotography. Tracks RA/DEC deviations, timing accuracy, seismic vibrations, and provides FFT analysis — all with a modern dark astronomy-friendly interface.**

---

### Overview

MountMonitor is a modernized rewrite of the original Java MountMonitor v3.37 by [Nicolas de Hilster](https://dehilster.info/astronomy/mountmonitor.php) (2018-2021). It monitors telescope mount tracking performance in real-time, helping astrophotographers verify their mount behavior during imaging sessions.

The application reads RA, DEC, and timing data from the mount, displays real-time graphs, computes running statistics, and logs everything to files for post-session analysis.

### Features

#### Real-time Monitoring
- Live RA and DEC deviation graphs with configurable tolerances
- Running standard deviation (STDEV) with 60/120/300/900s windows
- Min/Max tracking with value annotations
- PC-Mount time difference monitoring
- NTP time server integration for absolute time accuracy
- Automatic mount settings verification at startup and after each slew

#### Communication Protocols
- **LX200 TCP/IP** — Native protocol for 10Micron and compatible mounts
- **ASCOM** — Windows ASCOM drivers via COM interface
- **Alpaca** — Platform-independent ASCOM Alpaca (planned)
- **Simulation** — Built-in mount and seismometer simulation for testing

#### Advanced Analysis
- **FFT Analysis** — Frequency and period domain for RA, DEC, and seismic data
- **Axial Velocity/Displacement** — Raw axis position monitoring (10Micron specific)
- **Seismometer Support** — USB seismometer integration for vibration correlation
- **Tolerance Alerts** — Real-time warnings when tracking exceeds limits

#### Data Logging
- Four log file types: `.log` (events), `.dat` (mount data), `.dti` (timing), `.sei` (seismic)
- Tab-separated ASCII format, easily imported into spreadsheets
- Automatic file management with configurable close/dump triggers

#### Modern Interface
- Dark astronomy-friendly theme (preserves night vision)
- High-performance real-time graphs (pyqtgraph with OpenGL)
- Bilingual interface (English / French)
- Keyboard shortcuts for all operations
- Resizable panels with persistent layout

---

### Installation

#### Using the Launcher (Recommended)

**Windows:**
```
launch.bat
```

**Linux / macOS:**
```bash
chmod +x launch.sh
./launch.sh
```

The launcher automatically creates a virtual environment, installs dependencies, and starts the application.

#### Manual Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### Usage

```bash
# Normal mode (connect to real mount)
python main.py

# Simulation mode (demo with simulated data)
python main.py --sim-all

# Simulate mount only (requires real seismometer)
python main.py --sim-mount

# Simulate seismometer only (requires real mount)
python main.py --sim-seismometer

# Debug logging
python main.py --sim-all --log-level DEBUG
```

### Requirements

- Python 3.11+
- PyQt6
- pyqtgraph
- numpy
- pyserial (for seismometer)
- ntplib (for NTP time sync)
- comtypes (Windows only, for ASCOM)

### Credits

Based on [MountMonitor v3.37](https://dehilster.info/astronomy/mountmonitor.php) by Nicolàs de Hilster, PhD — Starmountain Survey & Consultancy BV (2018-2021).

### License

MIT License
