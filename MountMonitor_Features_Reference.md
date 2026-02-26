# MountMonitor - Comprehensive Feature Reference Document

**Source:** https://dehilster.info/docs/MountMonitor-Help/
**Version:** 3.37 (03/01/2021)
**Author:** Nicolas de Hilster, Starmountain Survey & Consultancy BV
**Copyright:** 2018-2021

---

## 1. GENERAL OVERVIEW

### 1.1 Purpose
MountMonitor is a Java application that reads Right Ascension (RA), Declination (DEC) and time data from LX200 or ASCOM protocol supported telescope mounts and displays it as real-time graphs. It is designed to run in the background during astrophotography sessions.

### 1.2 Main Goal
- Monitor the behavior of mounts with absolute encoders (e.g., 10Micron), but also works with relative encoders
- Read mount time, RA and DEC from the mount
- Display data graphically in real-time
- Store data in log files for post-session analysis
- If images show unexpected results, MountMonitor logs can be consulted to identify noise on DEC/RA axis or jumps in mount clock
- Especially useful for **unguided imaging** to verify mount performance, but also works during guiding to show guiding system quality
- Since v3.00: time difference monitoring between PC and mount
- Since v3.03: NIST time server integration
- Optionally connect a seismometer (MountMonitor Plus) to correlate RA/DEC anomalies with ambient vibrations

### 1.3 Limitations
- Up to v3.30: did not show deviations caused by flaws in internal mount models (built via ModelCreator, ModelMaker, MountWizzard)
- A poor quality mount-model may cause tracking to appear more accurate than it is in the graphs
- DOES show movements caused by: external forces (wind, human handling, animals, ground vibrations, localized friction in drive-trains), guiding effects
- From v3.30: `:GaXa#`/`:GaXb#` commands read raw axial orientations for RA and DEC (without model correction - to be confirmed by 10Micron)

### 1.4 Supported Hardware
- **Primary:** 10Micron GM3000 HPS and Celestron CGEM equatorial mounts
- **Should work with:** All 10Micron mounts
- **May work with:** Most LX200 protocol supported mounts (untested, some commands are 10Micron extensions)
- **Since v3.10:** ASCOM interface for wider mount range
- **Seismometer:** USB Seismometer Interface (SEP-064) from Mindsets (UK), tested with Slinky Seismometer System (SEP-067)

### 1.5 User Data Collection
When internet is available, MountMonitor collects: email address, observatory name, mount type, mount ID. Data is for administrative/research/development purposes only, not shared with third parties.

---

## 2. HOW IT WORKS

### 2.1 Methodology / Startup Sequence
1. Communicates over Ethernet
2. Retrieves mount model, firmware version, and ID
3. Checks which side of pier the telescope is on
4. **Sets output resolution to HIGH** (more decimals) - only in LX200 mode, automatically goes to low-res upon mount reboot
5. Retrieves current azimuth and altitude
6. This startup information is used only for log/data file headers

**IMPORTANT:** MountMonitor does NOT alter any data in the mount (except high-res output mode). It does NOT change PC or mount clocks.

### 2.2 Running Loop
Once running, it records:
- Status
- Time
- RA
- DEC
- Axial orientations

Data is drawn in DEC, RA and time graphs, and checked against user-set tolerances. Reference can be the median of data or mount's target coordinates.

### 2.3 LX200 Commands Used
| Command | Description |
|---------|-------------|
| `:GVN#` | Get firmware number |
| `:GVP#` | Get product name |
| `:GETID#` | Returns 20-digit (64-bit) unique mount number |
| `:pS#` | Returns side of pier |
| `:GZ#` | Get telescope azimuth (start of log only) |
| `:GA#` | Get telescope altitude (start of log only) |
| `:GaXa#` | Get RA axial orientation (v3.20+) |
| `:GaXb#` | Get DEC axial orientation (v3.20+) |

### 2.4 Polling
- Polling frequency controls the whole four-command sequence (status, time, RA, DEC)
- Commands are sent at 4x the polling frequency
- Software dynamically adjusts loop timing even when network load changes
- Actual frequencies depend on network speed, computer, and mount capabilities
- When set too high, runs at maximum speed; actual frequency calculated from avg of 100 sequences
- Actual frequencies shown in FFT window upper-right corner

---

## 3. PREFERENCES (All Settings)

The preferences window has **four tabs**: General, Processing, Auxiliary, Miscellaneous.

### 3.1 General Tab

#### 3.1.1 Licence
- Basic edition: monitors RA and DEC only
- Registered version: adds seismometer support
- Email address required for registration (used for communication + license check)
- Supplying email = automatic update notifications
- Basic mode: no email or internet needed
- Seismometer license: email + internet at startup mandatory
- No internet at startup = automatic revert to basic mode

#### 3.1.2 Mount Settings
| Setting | Description |
|---------|-------------|
| **Observatory** | Recorded in log/data files |
| **Mount name** | Recorded in log/data files, auto-retrieved from mount |
| **Mount IP Address** | IP for LX200 connection |
| **Mount Port** | Default: 3492 (10Micron HPS default) |
| **Mount Protocol** | LX200 or ASCOM |
| **Select ASCOM Mount** | Enabled when ASCOM protocol selected; opens ASCOM Chooser (may appear in background, use ALT+TAB) |

When ASCOM mode: Mount IP Address and Mount Port are disabled.

#### 3.1.3 Layout
| Setting | Description |
|---------|-------------|
| **Graph:Textbox Ratio** | Height ratio of graphs to text boxes. E.g., 4:1 means each graph is 4x the text box height |

### 3.2 Processing Tab

| Setting | Description | Default/Values |
|---------|-------------|----------------|
| **Polling Frequency** | Interval for full interrogation sequence | Configurable (Hz) |
| **Running Range Length** | Period for running STDEV calculation | 60, 120, 300, 900 seconds |
| **Correct graphs for running range length** | Shift graphs to compensate for delay | On/Off (see details below) |
| **RA/DEC Reference** | Reference point for calculations | Median / Mount target coordinates |
| **Tolerance (RA axis)** | Max deviation from median for RA | Arc seconds or seconds of time |
| **Tolerance (DEC axis)** | Max deviation from median for DEC | Arc seconds |
| **Use tolerance as HA [s]** | Show RA tolerance in seconds of time | On/Off |
| **Tolerance (Seismic data)** | Max deviation as percentage of seismic range | Percentage |
| **Axial velocity** | Enable `:GaXa#`/`:GaXb#` axis monitoring | Off / Axial velocity / Axial displacement |
| **Log** | What to log | All / Only when tracking |
| **Delay after slewing** | Wait time after slew before logging | Seconds |
| **History** | Lines kept in scrolling text blocks | Default: 50 lines |
| **Reset buffers and min/max** | When to reset | Manual / When slewing |
| **Dump graphs** | When to save graphs to disk | Manual / When slewing / When parking |
| **Close files** | When to close/reopen data and log files | Manual / When slewing / When parking |

#### Graph Correction Details (Correct graphs for running range length)
When enabled, shifts graphs in time to compensate:
- **STDEVs:** shifted by half the running average length (peak STDEV aligns with peak deviation)
- **Raw axial velocity:** shifted by 3 observations (half of the 6 used)
- **Axial velocity:** shifted by half the running average length
- **Axial displacement:** shifted by full running average length (integrated displacement aligns with measured displacement, correlates with PHD2 measurements)

#### RA/DEC Reference Details
- **Median mode:** reference = median of currently visible data
- **Mount target coordinates mode:** requests target at startup and after each slew (after delay period)
- ASCOM limitation: target coordinates may not be available until next slew after MountMonitor start

### 3.3 Auxiliary Tab

#### 3.3.1 NIST Time Server Panel
| Setting | Description | Default |
|---------|-------------|---------|
| **Use server** | Enable/disable NIST connection | Off |
| **Server address** | NIST Time Server address | e.g., time.nist.gov |
| **Polling interval** | How often to contact NIST server | 30 seconds |

When enabled: blue line added to time graph showing PC-NIST difference. If internet drops, blue line disappears.

#### 3.3.2 Seismometer Panel
Only active with seismometer license + valid email + internet at startup.

| Setting | Description | Default |
|---------|-------------|---------|
| **Show seismic data** | Show/hide seismic graph | On |
| **Serial port** | COM port for USB AD-converter | Auto-populated dropdown |
| **Sampling frequency** | AD-converter sampling rate | 20 Hz |
| **Offset** | Fixed value to center data around zero | 300 |
| **Range** | Max +/- value shown in seismic graph | Configurable |

Serial port list refreshes each time preferences dialog opens (USB device can be connected while MountMonitor runs, as long as prefs dialog is closed).

### 3.4 Miscellaneous Tab - Mount Settings Checks

All checks are performed at startup and after every slew. Alerts via popup + logged to file.

| Check | Options |
|-------|---------|
| **Check if refraction setting is** | Enabled / Disabled |
| **Check if refraction is** | Not updating / Not updating while tracking / Continuously updating |
| **Check if GPS clock synch is** | Not synchronising / Synchronising |
| **Check if Dual Tracking status is** | Enabled / Disabled |
| **Check if Tracking Rate is** | Sidereal (checks: Follow object OFF, Tracking correction 0.000%, Speed = Sidereal) |

Note: Custom tracking with 0.000 rate for both axes still triggers warning despite being sidereal speed.

---

## 4. LAYOUT AND MENUS

### 4.1 Title Bar
Displays: version, date, polling frequency, connection info.
- Example: `MountMonitor (v.3.00 200321) 5Hz on TCP/IP address 10.0.0.10:3492`
- Test mode: `5Hz in test mode`

### 4.2 Menu Items

#### Horizontal Zoom Menu
- Changes data density along horizontal axis
- Default: 1x (1 pixel = 1 data point)
- 5x = 5 pixels per data point
- Recommended: leave at 1x
- Note: if combined settings result in < 60 seconds of data, running STDEV won't work properly for 60s

#### Vertical Zoom Menu
| Option | Behavior |
|--------|----------|
| **Data (median centred)** | Zooms to data, tolerance lines may be off screen, median vertically centered |
| **Tolerance** | Zooms to tolerance levels, data may run off screen, median centered |
| **Maximum (data/tolerance)** | Keeps both data and tolerance visible (spikes may compress detail) |
| **Min/Max value lines** | Zooms to min/max lines to see their values |

#### Reset Menu
| Option | Action |
|--------|--------|
| **Min/Max** | Resets min/max value lines |
| **Buffers** | Resets graph buffers (graphs go blank, restart empty) |
| **Buffers and Min/Max** | Resets both |
| **New files** | Closes current .log/.dat files, opens new ones |

#### Preferences Menu
- **Edit** - Opens preferences dialog (remembers last opened pane)

#### Help Menu
- Help file
- On-line help (v3.37+)
- About box

---

## 5. THE GRAPHS

### 5.1 Storage
Graphs stored in automatically created directories:
- `RA_graphs/`
- `DEC_graphs/`
- `Seismic_graphs/`
- `Time_graphs/`
- `FFT_graphs/` (once FFT window opened)

Auto-saved each time window width fills with new data. On close/slew/park (per preferences), last graphs saved with grey overlay indicating overlap with previous graphs.

### 5.2 RA and DEC Graphs

**Data colors:**
- RA: **magenta**
- DEC: **red**

**Background:** "RIGHT ASCENSION" / "DECLINATION" in light grey

**Graph elements:**
| Element | Color/Style | Description |
|---------|-------------|-------------|
| Data line | Magenta (RA) / Red (DEC) | Raw tracking data |
| Dashed horizontal lines | Same color as data | Min/max values, annotated with deviation from median in arc seconds |
| Running STDEV | Blue solid undulating line | Length configurable (60/120/300/900s) |
| Max STDEV | Blue dashed horizontal | Max since recording started, with short dashed segments; annotated with range length + extreme value |
| Tolerance lines | Green solid horizontal | Around median, value set in preferences |
| Time fixes | Grey vertical lines | Every 30 seconds, annotated with mount time |
| Scale (left) | Grey | RA/DEC values |
| Scale (right) | Blue | STDEV values |

### 5.3 Axial Speed and Displacement Graphs (v3.30+)

Uses `:GaXa#`/`:GaXb#` commands for raw axis orientation.

**Expected values without polar alignment error/refraction:**
- RA axial speed: 15.02"/s
- DEC axial speed: 0"/s

#### Axial Speed Display (3 simultaneous methods):
| Method | Color/Style | Description |
|--------|-------------|-------------|
| Raw speeds | Gray | Speed from 2 consecutive samples; noisy; automatic unannoted scale |
| 6-sample running average | Fat black line | Averaged over 5 samples; same scale as raw, not annotated |
| Linear regression | Extra fat black line | Uses Running Average Length; smoother but may miss small deviations; delayed by RAL; annotated in "/s |

**NOTE:** First period of Running Range Length can produce incorrect data. Reliable data expected after at least 2x this time.

#### Axial Displacement Display
Replaces linear regression speed graph (raw + 5-sample average remain). Integration of speed data:
- Annotated in arc seconds `[x.xx"]`
- Annotated in spherical arc seconds `[x.xx"SPH]` (= displacement * cos(declination))
- Spherical value directly comparable to pixel angular resolution of imaging setup

### 5.4 Seismic Graph
- Data: **black**
- Background: "SEISMIC" in light grey
- Vertical scale: manual (set in preferences)
- Left scale: grey, shows max/min values
- Contains: running STDEV (blue), tolerance lines (green), time fixes (grey vertical, every 30s)

### 5.5 Time Graph
**Data colors and meaning:**
| Color | Represents |
|-------|------------|
| **Black** | Difference between PC-time and mount-time |
| **Green** | Length of full MountMonitor loop (PC clock) |
| **Red** | Length of full MountMonitor loop (mount clock) |
| **Blue** | PC-NIST time difference (only when NIST connected) |

**Behavior:**
- When all OK: red line almost completely covered by green line (only red dots at peaks)
- Red and green lines have running-average offset (equal to RA/DEC running STDEV length) for better vertical scale
- Black line: no offset; grey horizontal center line = 0ms PC-Mount difference
- Legend shows three graph colors, current values, and drift rate of black graph

**Time jump analysis:**
- Jumps in black graph: red/green graphs indicate whether PC or mount clock jumped
- Leading edge color indicates source of jump
- PC sync jump has no effect on guiding
- Mount clock jump causes RA-axis jump (e.g., 1.18 arcseconds star trail, then auto-correction)

**Protocol quality:**
- 10Micron GM3000HPS shows measurable difference in timing accuracy between LX200 and ASCOM protocols

---

## 6. FAST FOURIER TRANSFORMATION (FFT)

### 6.1 Overview
Converts RA, DEC, and seismic data from time domain to:
- **Frequency domain** (upper graph)
- **Wave period domain** (lower graph)

Purpose: identify vibration sources by frequency/period, detect correlation between vibrations and mount data.

### 6.2 Frequency Limits (Nyquist-Shannon)
- Seismic data (20Hz): max detectable frequency = **10 Hz**
- RA/DEC data (~4Hz): max detectable frequency = **~2 Hz** (depends on computer/network)

### 6.3 Display
- Actual data frequencies displayed in upper-right corner in graph colors
- Auto-scaled to most significant data when FFT window opens

### 6.4 Controls
| Button | Action |
|--------|--------|
| **+** | Zoom in (horizontal scale) |
| **-** | Zoom out (horizontal scale) |
| **<** | Shift graph left |
| **>** | Shift graph right |

### 6.5 Graph Storage
Once FFT window is opened, FFT graphs are stored to `FFT_graphs/` at the same pace as RA/DEC/seismic graphs.

---

## 7. SEISMOMETER

### 7.1 Purpose
Correlate RA/DEC deviations with environmental vibrations: earthquakes, traffic, railroads, heavy industry, coastal surf. Most sources generate microseisms with limited mount effect (< 0.1 arc second), depending on magnitude and distance.

### 7.2 Supported Hardware
- **USB Seismometer AD-converter** (SEP-064) from Mindsets (UK)
- **Slinky Seismometer System** (SEP-067) from Mindsets
- Any coil-type seismometer can be used with the MindSets AD-converter
- Other seismometer types can be interfaced on request

### 7.3 Data Format
- Expected at **20 Hz**
- Simple format: values separated by CR+LF
- Example: `-216[CrLf]-376[CrLf]-351[CrLf]`
- AD-converter stores values, supplies as single string each new sequence
- Default 20Hz used for array creation; actual frequency calculated from data amount per time period
- MountMonitor uses **interpolation** to fit seismic data into RA/DEC sequence elapsed time

---

## 8. NIST TIME SERVER

### 8.1 Purpose
Contact NIST Time Server over internet to determine PC-NIST time difference. **Does NOT adjust the PC or mount time.**

### 8.2 Available Servers
List at: https://tf.nist.gov/tf-cgi/servers.cgi

### 8.3 PC Time Synchronization (Manual Setup)

#### Registry Tweak
- Path: `HKEY_LOCAL_MACHINE\SYSTEM\ControlSet001\Services\w32time\TimeProviders\NtpClient`
- Default: 604800 (7 days in seconds = 0x93A80 hex)
- For daily sync: change to 86400 (24*60*60 = 0x15180 hex)
- Tip: sync around noon via systray clock > "Adjust date/time" > "Synchronise now"

#### Software Solution
- NISTIME32 from NIST: https://www.nist.gov/pml/time-and-frequency-division/services/internet-time-service-its
- Requires admin rights to adjust clock
- Minimum sync interval: 1 hour

---

## 9. LOG FILES

### 9.1 Storage Location
All files stored in automatically created `Logs/` directory.

### 9.2 File Types

| File Pattern | Extension | Content |
|-------------|-----------|---------|
| `MountMonitor_YYYYMMDD-HHMMSS.log` | .log | Setting changes, tolerance exceedance times, return-to-tolerance events, summary at close |
| `MountMonitor_YYYYMMDD-HHMMSS.dat` | .dat | All RA/DEC data with header. Contains raw ASCII + derived values (should match except + sign) |
| `MountMonitor_YYYYMMDD-HHMMSS.sei` | .sei | Seismometer data: time, raw data, processed data, standard deviation |
| `MountMonitor_YYYYMMDD-HHMMSS.tdi` | .tdi | Time data: time, PC-mount difference, PC loop time, mount loop time |

### 9.3 File Format
- Plain ASCII
- TAB-separated fields
- Can be opened with any text editor
- Easily imported into spreadsheet software (Excel, etc.)

### 9.4 Log Options
- **All**: log everything
- **Only when tracking**: skip slewing data (e.g., meridian flips); status window shows ignored data; logging resumes after delay-after-slewing period

---

## 10. MOUNT SETTINGS CHECKS

Performed at startup and after every slew. Results logged (both warnings and successful verifications).

| Check | Options | LX200 Commands |
|-------|---------|----------------|
| Refraction setting | Enabled / Disabled | Checks mount refraction correction state |
| Refraction mode | Not updating / Not updating while tracking / Continuously updating | Corresponds to mount keypad settings |
| GPS clock synch | Not synchronising / Synchronising | Checks GPS sync state |
| Dual Tracking | Enabled / Disabled | Checks dual tracking status |
| Tracking Rate | Sidereal | Verifies: Follow object OFF, Tracking correction 0.000%, Speed = Sidereal |

Alert popup warns user to correct any mismatch. Both warnings and successful verifications logged.

---

## 11. INSTALLATION

### 11.1 Requirements
- **Java** must be installed (runs on all Java-supporting platforms)
- Must NOT be on a network drive
- Tested on 32-bit and 64-bit machines
- Compatible with Virtual KeyPad and TimeSynch running simultaneously on same TCP/IP and port

### 11.2 Installation Steps
1. Create a directory (e.g., on desktop)
2. Extract zip file contents to that directory
3. Start via `MountMonitor.bat`
4. First run: serial port detection (up to 10 seconds)
5. Set IP address and port in Preferences > Edit

### 11.3 Zip File Contents

| File | Description |
|------|-------------|
| `MountMonitor_[version]-help.CHM` | Help file |
| `MountMonitor.jar` | Main Java application |
| `MountMonitor.pref` | Preferences file |
| `MountMonitor.bat` | Normal start (requires mount) |
| `MountMonitor_simAll.bat` | Test mode: simulates mount + seismometer |
| `MountMonitor_simMount.bat` | Test mode: simulates mount only (needs seismometer) |
| `MountMonitor_simSeismometer.bat` | Test mode: simulates seismometer only (needs mount) |
| `commons-net-3.6.jar` | NIST server communication library |
| `jacob.jar` | Java-to-ASCOM communication (general) |
| `jacob-1.19-x64.dll` | Java-to-ASCOM (64-bit) |
| `jacob-1.19-x86.dll` | Java-to-ASCOM (32-bit) |
| `jSerialComm-2.4.0.jar` | Serial communication library |

### 11.4 Autostart on Windows
1. Create desktop shortcut to MountMonitor location
2. Press Win+R, type `shell:common startup`, hit Enter
3. Drag shortcut to startup folder
4. Number shortcuts for launch order: `1-[program1]`, `2-[program2]`, etc.

---

## 12. COMMUNICATION PROTOCOLS

### 12.1 LX200 Protocol
- Native protocol for 10Micron and Meade mounts
- Connection via TCP/IP (Ethernet)
- Default port: 3492 (10Micron HPS)
- Sets output to high-resolution mode (more decimals)
- Auto-reverts to low-res on mount reboot

### 12.2 ASCOM Protocol (v3.10+)
- Uses ASCOM Chooser for mount selection
- Requires jacob.jar + DLL (32 or 64-bit)
- IP/Port fields disabled in ASCOM mode
- Target coordinates may not be available until next slew after MountMonitor start
- Lower timing accuracy than LX200 on 10Micron GM3000HPS

---

## 13. TOLERANCE SYSTEM

### 13.1 RA Tolerance
- Can be expressed in **arc seconds ["]** or **seconds of time [s]**
- When in arc seconds: tolerance lines annotated with both values (arc-seconds / 15 / cos(declination))
- Arc-second mode useful for comparing to pixel physical dimensions

### 13.2 DEC Tolerance
- Expressed in arc seconds

### 13.3 Seismic Tolerance
- Expressed as percentage of seismic range
- Only available when seismometer is connected

### 13.4 Tolerance Alerts
- Warning in status window when data or running STDEV exceeds tolerance
- Logged in .log file (both exceedance and return-to-tolerance events)

---

## 14. AUTOMATIC TIMEZONE HANDLING (v3.15+)
- Automatic timezone offsets for both PC and mount
- Allows time comparison when in different timezones (e.g., mount in UTC, PC in UTC+2)

---

## 15. VERSION HISTORY (KEY MILESTONES)

| Version | Date | Key Features |
|---------|------|-------------|
| 1.20 | 06/01/2019 | Graph dump, buffer reset, log file range, status text box, mount info commands |
| 1.21 | 08/01/2019 | Auto reconnect after TCP/IP loss |
| 1.30 | 10/01/2019 | Running STDEV (60/120/300/900s), preferences popup, automation options |
| 2.00 | 14/02/2019 | FFT implementation, seismometer interface, polling frequency controls full sequence |
| 2.10 | 01/12/2019 | Improved layout for high-res monitors |
| 3.00 | 21/03/2020 | Time graph added |
| 3.03 | 02/04/2020 | NIST server, mount target reference option |
| 3.10 | 16/04/2020 | ASCOM interface added |
| 3.11 | 21/05/2020 | License timeout, refraction check, non-halting alerts |
| 3.12 | 23/05/2020 | Improved LX200 interfacing, extended checklist |
| 3.13 | 23/05/2020 | Improved tracking rate verification |
| 3.14 | 24/05/2020 | More mount checks, RA tolerance in arc seconds or time seconds |
| 3.15 | 25/05/2020 | Sidereal tracking check fix, automatic timezone offsets |
| 3.20 | 27/05/2020 | `:GaXa#`/`:GaXb#` axial velocity graphs |
| 3.30 | 31/05/2020 | Axial data fixes, preference file validation, improved resize |
| 3.34 | 18/07/2020 | UI improvements, NIST server fix |
| 3.35 | 20/07/2020 | Shift option for axial velocity/displacement and STDEV graphs |
| 3.37 | 03/01/2021 | Horizontal zoom fix for >2000px screens, online help |

---

## 16. KNOWN ISSUES (as of v3.30)
- Window resize to smaller than graph length causes integrated axial speed data corruption
- Workaround: Reset buffers clears the issue

---

## 17. CONTACT
- Web: www.DeHilster.info
- Web: www.Starmountain.nl
- Email: info@DeHilster.info
