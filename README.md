# MountMonitor

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

**Real-time telescope mount monitoring for astrophotography. Tracks RA/DEC deviations, timing accuracy, seismic vibrations, and provides FFT analysis — all with a modern dark astronomy-friendly interface. Includes automatic GitHub updates, crash detection, and anonymized bug reporting.**

---

## Supported systems

The published packages bundle their own Python and Qt: nothing else has to be
installed. What they do require is a recent enough system, because the Qt
binaries inside them do.

| System | Minimum | Architecture |
|---|---|---|
| **Windows** | Windows 10 (1809) or later | x64 |
| **macOS** | macOS 11 Big Sur or later | Apple Silicon **and** Intel — one package each |
| **Linux** | glibc 2.28 — Debian 11, Ubuntu 20.04, RHEL 8 or later | x86\_64 |
| **Linux ARM64** | glibc 2.39 — Ubuntu 24.04 or later | arm64 |

The Linux ARM64 floor is higher than the x86\_64 one, and it is not our doing:
PyQt6 publishes its aarch64 wheels against a much newer glibc than its x86\_64
ones. On an older ARM system, install from source instead.

Pick the macOS package that matches your Mac: `-macos-arm64.dmg` for Apple
Silicon (M1 and later), `-macos-x86_64.dmg` for Intel. The bundled Python is
architecture-specific even though Qt itself is universal, so the wrong one will
not start at all.

Running from source needs Python 3.10 or later and the packages in
`requirements.txt`.

---

## Features

### Real-time Monitoring
- Live RA and DEC deviation graphs with configurable tolerances
- Running standard deviation (STDEV) with 60/120/300/900s windows
- Min/Max tracking with value annotations
- PC-Mount time difference monitoring
- NTP time server integration for absolute time accuracy
- Automatic mount settings verification at startup and after each slew

### Session Control
- **Armed logging**: the logger waits for the mount to start tracking instead
  of recording the hours between connection and nightfall
- **A night is one unit**: a park mid-night suspends recording and resumes in
  the same file; only sunrise closes the session and writes the report
- **Night ephemeris** from the site the mount reports — sunset, twilights,
  sunrise, and how much of the astronomical night the session covered

### Communication Protocols
- **LX200 TCP/IP** — Native protocol for 10Micron and compatible mounts
- **LX200 Serial** — Serial connection (RS-232, 9600 8N1)
- **ASCOM** — Windows ASCOM drivers via COM interface with native Chooser dialog
- **Simulation** — Built-in mount and seismometer simulation for testing

### Tracking Analysis
- **Jitter measured between repositionings**, not around a straight line: a
  deviation record is a staircase, not a noisy line, and removing a drift does
  not remove a staircase
- **Commanded moves grouped and classified** — dither, re-centering, or
  unsettled — and reported apart from the tracking figures
- Slow drift, commanded moves and tracking jitter each reported on their own
  terms, so none of them contaminates the others

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
- **Crash, freeze and native-crash reporting**: a crash that leaves no Python
  traceback — a segmentation fault inside Qt, say — is picked up from the fault
  log on the next start; a frozen window is detected by a watchdog that samples
  the GUI thread's stack, which is the only thing that says *what* froze it
- **Asked once, and never assumed**: nothing leaves the machine until you have
  answered the question, and a refusal is final
- **Bug report dialog**: Help → Report a Bug
- All file paths in reports are **completely anonymized** (home dir → ~), and
  no mount data, file name or user name is ever sent

### Modern Interface
- Dark astronomy-friendly theme (preserves night vision)
- High-performance real-time graphs (pyqtgraph with OpenGL)
- **Trilingual interface (English / French / Dutch)**, detected from the system
  and switchable from the Language menu — every dialog, report and message
- Keyboard shortcuts for all operations
- Resizable panels with persistent layout
- Custom logo and icon

---

## What's New in v1.19.0

The full history, with the measured figures behind each change, is in
[CHANGELOG.md](CHANGELOG.md). The last few versions, in short:

### The tracking figures now describe tracking
The excursion filter used to discard **59% of a night**: it thresholded the raw
distance from the session median, and an unguided mount left eight hours on one
target drifts far past any fixed threshold without anything being commanded.
99.5% of samples are now kept instead of 41.1% — and the jitter barely moved,
which is what confirmed the figure had been right and the sample selection had
not.

Commanded moves are grouped and classified — dither, re-centering, or
unsettled — and reported apart from the tracking. A sequence that dithers every
frame does not score worse than one that never does.

### A night is one unit
The logger can be **armed** rather than started: it waits for the mount to
begin tracking, so a mount connected at noon no longer writes seven hours of
nothing. If the mount parks at two in the morning and resumes at three,
recording suspends and resumes **in the same file**. Only sunrise ends the
night and triggers the report.

### Night ephemeris
Sunset, twilights and sunrise are computed from the site the mount itself
reports, and the report states how much of the astronomical night the session
actually covered. Checked against skyfield/DE421 over five sites and 36 dates:
worst case 23.8 seconds.

### Three languages, everywhere
English, French and Dutch — in the interface, in the report, in the consent
question and in the crash dialog. A **Language menu** now sits in the menu bar,
each entry written in its own language. All 373 translation keys are complete.

### Six packages
Windows, macOS on Apple Silicon **and** Intel, Linux on x86_64 **and** ARM,
each with an installer and automatic updates.


## Overview

MountMonitor is a modernized rewrite of the original Java MountMonitor v3.37 by [Nicolàs de Hilster](https://dehilster.info/astronomy/mountmonitor.php) (2018-2021). It monitors telescope mount tracking performance in real-time, helping astrophotographers verify their mount behavior during imaging sessions.

The application reads RA, DEC, and timing data from the mount, displays real-time graphs, computes running statistics, and logs everything to files for post-session analysis.

---

## Installation

### Installers (recommended)

Everything is on the
[Releases page](https://github.com/ARP273-ROSE/MountMonitor/releases/latest).
There is **no Python to install and no administrator password to type** on any
of the three systems: each package carries its own interpreter and installs
into your user profile.

| System | File | What to do |
|---|---|---|
| **Windows** | `MountMonitor-Setup-*.exe` | Run it. |
| **macOS** | `MountMonitor-*-macos.dmg` | Open the disk image, drag the app into Applications. First launch: **right-click → Open**, then confirm — the app is not signed. |
| **Linux** | `MountMonitor-*-linux.tar.gz` | Extract, run `installer.sh`. It installs into `~/.local/share` and adds the menu entry. |

Once installed, MountMonitor keeps itself up to date **on all three systems**:
it checks the Releases page at startup and offers the new version, which it
downloads and applies by itself. The update archive holds the code only — the
interpreter and the compiled dependencies are never touched.

Your settings and your session files live outside the installation folder
(`%LOCALAPPDATA%\MountMonitor` on Windows, `~/.local/share` elsewhere), so an
update never touches them.

### Languages

The interface speaks **English, French and Dutch**, and picks your system
language on its own. Dutch is there because MountMonitor began as a Dutch
program: the original v3.37 is by Nicolàs de Hilster. You can force a language
in *Preferences → Language*.

### From source, with the launcher

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

Based on [MountMonitor v3.37](https://dehilster.info/astronomy/mountmonitor.php) by Nicolàs de Hilster, PhD — Starmountain Survey & Consultancy BV (2018-2021).

## License

MIT License
