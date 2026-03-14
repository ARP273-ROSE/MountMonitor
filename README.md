# MountMonitor

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

**Real-time telescope mount monitoring for astrophotography. Tracks RA/DEC deviations, timing accuracy, seismic vibrations, and provides FFT analysis — all with a modern dark astronomy-friendly interface. Includes automatic GitHub updates, crash detection, and anonymized bug reporting.**

---

## Features

### Real-time Monitoring
- Live RA and DEC deviation graphs with configurable tolerances
- Running standard deviation (STDEV) with 60/120/300/900s windows
- Min/Max tracking with value annotations
- PC-Mount time difference monitoring
- NTP time server integration for absolute time accuracy
- Automatic mount settings verification at startup and after each slew

### Communication Protocols
- **LX200 TCP/IP** — Native protocol for 10Micron and compatible mounts
- **LX200 Serial** — Serial connection (RS-232, 9600 8N1)
- **ASCOM** — Windows ASCOM drivers via COM interface with native Chooser dialog
- **Simulation** — Built-in mount and seismometer simulation for testing

### Advanced Analysis
- **FFT Analysis** — Frequency and period domain for RA, DEC, and seismic data
- **Axial Velocity/Displacement** — Raw axis position monitoring (10Micron specific)
- **Seismometer Support** — USB seismometer integration for vibration correlation
- **Tolerance Alerts** — Real-time warnings when tracking exceeds limits

### Data Logging & Analysis
- Six log file types: `.log` (events), `.dat` (mount data), `.dti` (timing), `.sei` (seismic), `.fft` (FFT), `.env` (environment/diagnostics)
- Tab-separated ASCII format, easily imported into spreadsheets
- Automatic logging on connect — records all parameters throughout the night
- **Log replay**: Open previous `.dat` files to visualize past sessions
- **Automatic morning analysis**: Comprehensive report auto-generated when the mount parks
- 13-section analysis report: quality rating, RA/DEC stats, FFT/PE detection, drift, environment, recommendations

### Environment Monitoring (10Micron)
- External/internal temperature logging every 30 seconds
- Barometric pressure tracking
- Alignment model quality (stars, RMS, polar error)
- Extended mount status codes (`:Gstat#`)
- Meridian flip countdown
- All data included in the morning analysis report

### Auto-Update & Bug Reports
- **Automatic update check** at startup (silent, background, threaded)
- Manual check via **Help → Check for Updates**
- Compares local version with latest GitHub Release
- Shows changelog, offers to download & install with one click
- Secure download with size limits, zip validation, anti-path-traversal
- File whitelist: never overwrites user data (settings, logs, graphs)
- Automatic restart after successful update
- **Crash detection**: if MountMonitor crashes, the next startup offers to report it on GitHub
- **Bug report dialog**: Help → Report a Bug, pre-fills a GitHub Issue with anonymized system info and recent errors
- All file paths in reports are **completely anonymized** (home dir → ~)

### Modern Interface
- Dark astronomy-friendly theme (preserves night vision)
- High-performance real-time graphs (pyqtgraph with OpenGL)
- Bilingual interface (English / French)
- Keyboard shortcuts for all operations
- Resizable panels with persistent layout
- Custom logo and icon

---

## What's New in v1.7.0

### Auto-Update from GitHub
MountMonitor now checks for updates **automatically at startup** (silent, background, non-blocking):
- Compares local `VERSION` with latest GitHub Release tag
- Shows changelog and offers to **download & install** with one click
- Manual check via **Help → Check for Updates**
- Secure download: size limits (100 MB), zip validation, anti-path-traversal, anti-symlink, anti-zip-bomb
- **File whitelist**: only updates `.py`, `.md`, `.bat`, `.sh`, `.png`, `.ico`, `.pdf` etc. — never overwrites user data (settings, logs, graphs, venv, .git)
- Atomic writes (temp file + fsync + replace) for safe file replacement
- Automatic restart after successful update

### Crash Detection & Reporting
- **Automatic crash capture**: `sys.excepthook` saves a JSON crash report with anonymized traceback
- On next startup, MountMonitor detects the crash report and offers to **report it on GitHub** (pre-filled Issue with system info)
- All file paths are **completely anonymized** — home directory replaced with `~`, username patterns removed

### Bug Report Dialog
- **Help → Report a Bug**: opens a dialog to describe the issue
- Submits a **pre-filled GitHub Issue** with anonymized system info, Python version, architecture, and recent error log entries
- No telemetry — everything is offline, only sent voluntarily via GitHub Issues

### Privacy & Anonymization
- New `anonymize_path()` function strips home directory, username, and drive-letter patterns from all reports
- Works cross-platform (Windows case-insensitive path matching, Unix home detection)
- OS version details removed from crash reports (only OS name kept)
- Recent error log entries included in bug reports are also anonymized

---

## What's New in v1.6.1

### NAS / Multi-PC Portability
MountMonitor can now be stored on a **NAS or synced folder** and used from multiple PCs without conflict:
- **Local venv**: The virtual environment is stored locally (`%LOCALAPPDATA%\MountMonitor\venv` on Windows, `~/.local/share/MountMonitor/venv` on Linux) instead of inside the project folder
- **Portable shortcut**: Desktop shortcut targets `launch.bat`/`launch.sh` instead of a specific Python path — works on any PC regardless of Python install location
- **Auto-detect stale paths**: If the project folder moves, the shortcut detects the old path and offers to update itself
- **Local icon copy**: The icon is copied to local storage so it displays correctly even from network/UNC paths

---

## What's New in v1.6.0

### Performance — UI Freeze Fix
Seven compounding causes of progressive UI freeze identified and fixed:
- **Numpy array caching** with dirty flags — no redundant copies of 50K+ element buffers
- **Graph downsampling** — max 5,000 points displayed, preserving extremes
- **250ms refresh timer** (was 100ms) — 4 fps, halving CPU load with no visible difference
- **QPlainTextEdit** status panel — 10x faster than QTextEdit HTML rendering
- **Stylesheet caching** — CSS only recalculated when state actually changes
- **STDEV outside lock** — heavy computation no longer blocks the main thread
- **Cached pen/font** — QPen and QFont objects reused across refreshes

Stable for 8h+ sessions without any degradation.

### Adaptive Night Report Scoring
Automatic detection of **unguided precision mounts** (10Micron, Planewave, ASA DDM) with adapted thresholds:

| Rating | Guided (standard) | Unguided precision |
|---|---|---|
| Excellent | < 0.5" | < 2.0" |
| Good | < 1.5" | < 4.0" |
| Fair | < 3.0" | < 8.0" |

Detection combines mount name, ASCOM driver, and firmware fields. Recommendations are also adapted (pointing model vs. polar alignment).

### Security Hardening
- LX200 response buffer limited to 4,096 bytes (anti-DoS)
- Log header sanitization (anti-newline/tab injection)
- Periodic flush every 20 writes (NAS performance: 95% fewer flush calls)
- Mount driver parsed from .dat files for enriched detection

### Environment Logging
New `.env` log file type — temperature, pressure, alignment model quality, extended mount status, meridian flip countdown. Six log file types total.

---

## Overview

MountMonitor is a modernized rewrite of the original Java MountMonitor v3.37 by [Nicolas de Hilster](https://dehilster.info/astronomy/mountmonitor.php) (2018-2021). It monitors telescope mount tracking performance in real-time, helping astrophotographers verify their mount behavior during imaging sessions.

The application reads RA, DEC, and timing data from the mount, displays real-time graphs, computes running statistics, and logs everything to files for post-session analysis.

---

## Installation

### Using the Launcher (Recommended)

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

### Manual Installation

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

## Usage

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

## Requirements

- Python 3.10+
- PyQt6
- pyqtgraph
- numpy
- pyserial (for seismometer)
- ntplib (for NTP time sync)
- comtypes (Windows only, for ASCOM)

## Credits

Based on [MountMonitor v3.37](https://dehilster.info/astronomy/mountmonitor.php) by Nicolas de Hilster, PhD — Starmountain Survey & Consultancy BV (2018-2021).

## License

MIT License
