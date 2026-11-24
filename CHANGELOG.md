# Changelog

All notable changes to MountMonitor are recorded here. Versions follow
[semantic versioning](https://semver.org/): the minor number rises when
behaviour changes, the patch number when only a defect is fixed.

Figures quoted below were measured on real sessions, not estimated.

## 4.5.7 — 2026-11-24

Remarks of the MM3 author on 4.5.6, and menus tidied.

- FFT window: *Analysed* duration (5 min to 4 h, or the whole buffer; 30 min by
  default), the same for RA, DEC and the seismometer. Over the whole buffer the
  mount spectrum covered about 7 h (50,000 samples at 2 Hz) and the
  seismometer's 41 min (at 20 Hz): their lines could not be compared. The top
  line gives the duration each spectrum really covers. Also applies to the
  spectra written in the log.
- Automatic graph dumps as in MountMonitor 3: every automatic choice dumps the
  graphs each time they have filled, and an image at parking, or at each slew
  and parking, can be added. Choices: Manual, When the graph fills, + at
  parking, + at each slew and parking. A dump made for a slew or a park restarts
  the count to the next full graph (no near-duplicate).

- File gathers the session and the application: connect, disconnect, new
  files, export graphs, open a log, analyse mount logs, Settings (Ctrl+,),
  desktop shortcut, quit. The Edit menu, which held Preferences alone, is gone.
- The resets (min/max, graph buffers, both) are a submenu of View; New files and
  Export graphs, which are not resets, moved to File.
- "Preferences" is now called "Settings" everywhere, and opens from the File
  menu only (no toolbar button any more).
- The File menu entries said "Connecting" and "Disconnected" (a state):
  they now read "Connect" and "Disconnect".

## 4.5.6 — 2026-11-24

Unattended start (observatory logon task, `--connect`).

- The "update available" dialog no longer blocks the main window: it is
  modeless, has its own taskbar button and comes to the front. Modal and owned
  by the window, it could stay hidden at logon and leave the window unusable,
  with the taskbar button opening nothing.
- A second copy started with `--connect` while MountMonitor is already running
  ends quietly instead of leaving an "already running" box behind.

## 4.5.5 — 2026-11-24

Remarks of the MountMonitor 3 author on 4.5.4.

- Axial graph titled after the mode chosen ("AXIAL VELOCITY" or "AXIAL
  DISPLACEMENT"); the figures of each axis in the strip are in its curve's colour.
- Axial mode greyed out in pure ASCOM (the axis angles are 10Micron commands),
  and ignored there if it was chosen before switching protocol: no polling, no
  empty graph. The graph is also shown or hidden at once when the mode changes.
- Preferences reopen on the last tab visited.
- The time graph waits for the slew and its settling delay, as RA and DEC do.
- Mouse wheel and drag no longer zoom the graphs (a touchpad scroll zoomed them
  until the next refresh).
- Graphs dumped automatically at the start of a slew or at parking keep their
  colours (the curve had just been greyed).
- Windows installer in English, French or Dutch after the language of Windows
  (English otherwise); it was French only.
- MountMonitor 3 is credited as v3.40, its last version.

Audit for small observatory PCs (24/11/2026). Timings on a desktop Ryzen 5
8500G, buffers full (50,000 samples), seismometer and axial graph on; a
Celeron/N100 NUC is 1.5 to 3 times slower.

- Graph painting: curves clipped to the view and reduced to two points per
  pixel, antialiasing only on sparse curves, rounding limited to what the
  width can show. 1 h span: 102 % of a core and the window 0.4-0.6 s late,
  now 29 % and on time; 10 min: 78 % -> 24 %. The refresh cadence now also
  counts the painting (lateness of its timer).
- FFT window: 245 -> 46 ms every 2 s (two bins per pixel, no antialiasing).
- Log files that cannot be created (disk full, folder missing) are said, and
  logging does not pretend to run; write errors are reported again each night.
- Dumped graphs go next to the log files, each export guarded: they went to
  the current folder (wiped by updates; System32 from the Task Scheduler,
  where the error stopped the parking handler before the night was closed).
- Update and language restart: the window closes first, the new instance
  waits for the old one (up to a minute) and keeps the command line
  (--connect).
- PC clock set back: the graph series restarts instead of drawing an hour as
  two minutes; the settling delay after a slew uses a monotonic clock.
- Seismometer unplugged in the night: the port is reopened in the background
  and its loss and return are shown (10 errors a second were logged forever).
- Disk fsync of the log files moved off the GUI thread.
- Buffer resets run in the poller thread (a reset between two steps of a
  sample gave a 10^5" spike).
- The same exception is reported once per run (it rewrote the crash file at
  every refresh); settings that cannot be saved no longer stop the closing.
- Text from .log10m files escaped in the overview; desktop shortcut script in
  single-quoted PowerShell strings; infinite values from an ASCOM driver
  handled.
- FFT spectra computed in a background thread (25 ms of frozen window every
  2 s on a desktop CPU, 60-80 ms on a NUC).
- Disconnecting no longer freezes the window while a driver is busy (up to
  5.5 s for the poller, 5 s for the NTP client); a new connection waits for
  the old thread to end.
- Packaged Python 3.14.10 (Windows, macOS, Linux). Python 3.12 is
  security-only and python.org stopped building its Windows embeddable zip at
  3.12.10, so its later security fixes never reached the Windows package. The
  downloaded interpreters are checked against pinned SHA-256 (python.org SBOM,
  python-build-standalone SHA256SUMS). No known vulnerability (OSV, 24/11) in
  the libraries shipped: PyQt6 6.9.1, Qt 6.9.2, numpy 2.5.5, requests 2.34.2,
  urllib3 2.8.0, pyserial 3.5, ntplib 0.4.0, comtypes 1.5.0.

## 4.5.4 — 2026-11-23

### Changed
- Axial graph drawn as MountMonitor 3 after a side-by-side test by its
  author: the figures matched (RA 15.16"/s, DEC 0.006"/s) but the raw and
  6-sample speeds, a hundred times noisier (0.36" steps of the angle),
  hid the regression speed. Only the latter is drawn now, thick, relative
  to its median; the strip reads "speed = median +deviation".
- Axial displacement mode implemented: integral of (regression speed -
  median) over the time shown, in arc seconds, around its mean; strip with
  the current value, the mean and the peak-to-peak range, also on the sky
  (x cos dec for RA, MM3's "SPH").
- Checked against MM3's drawing code (sent by its author): displacement
  integrated with the rectangle rule (speed now x time since the previous
  sample), smoothed raw speed as (4 previous + new) / 5, axial scale
  symmetric about the reference (1.2 x the farthest point), nothing drawn
  below 30 points.
- "Align graphs on the running window" now also moves the axial speed back
  by half a range and the displacement by a whole one, as MM3.

## 4.5.3 — 2026-11-23

### Fixed
- Axial graph: speeds now computed as MountMonitor 3 does. The "regression"
  was a straight line fitted to the averaged speed over the visible graph,
  annotated in "/s per minute, which said nothing about the axis speed. It
  is now, for each sample, the slope of a line fitted to the axis angle
  (`:GaXa#`/`:GaXb#`) over the running range, in "/s. Each axis is drawn
  relative to the median of that speed, so RA (about 15.04"/s) and DEC
  (about 0) no longer squash each other on one scale; the latest speed and
  the reference are written above the graph. Same computation when a .dat
  is replayed (`src/core/axial.py`).
- Simulated mount: axis angles read with 4 decimals like a 10Micron, with
  the periodic error, instead of a 3.6" random noise.

## 4.5.2 — 2026-11-23

### Fixed
- Slew: samples were recorded during the final approach. The "delay after
  slew" was counted from the START of the slew (a 10 s slew with a 10 s
  delay resumed recording the moment the slew ended), and a delay changed
  in the preferences while connected was ignored until the next
  connection. Now, as MountMonitor 3: nothing is recorded while the mount
  slews, the graphs are cleared when the slew ends (reset mode "slewing"),
  recording resumes `delay after slew` seconds after the END of the slew,
  and the mount settings and target are read at that moment.

## 4.5.1 — 2026-11-23

### Fixed
- Reference "Mount target coordinates" drew the same graph as the median:
  the target (`:Gr#`/`:Gd#`, ASCOM `TargetRightAscension`/`TargetDeclination`)
  was only read when a slew ended, so connecting to a mount already tracking,
  or choosing the mode during a session, silently kept the median. It is now
  read whenever the mount tracks without one, after every slew and every 30 s;
  the history shows the target in use, and says once when the mount gives
  none.

### Changed
- `:Gmte#` is shown as "tracking ends in" rather than "flip": the protocol
  defines it as the mount's estimate of the time until tracking stops at the
  meridian limit for the current pier side, or at the horizon limit.
- Pure ASCOM: the air line says "not available in pure ASCOM" instead of
  "not read yet".

## 4.5.0 — 2026-11-22

### Changed
- ASCOM is now pure ASCOM by default, as in MM3: only standard ASCOM
  properties are read and no LX200 command is ever sent to the driver, so any
  ASCOM mount (iOptron, Sky-Watcher, Celestron...) can be used safely. The
  refraction setting comes from `DoesRefraction`. A new preference,
  "10Micron commands through the ASCOM driver" (off by default, honoured only
  for the 10Micron driver), brings back temperature, pressure, axis angles,
  alignment model and the mount preference list in ASCOM.
- `:GTMP1#` is labelled as the right ascension motor driver temperature
  ("RA driver"), as the 10Micron command protocol 3.2.5 defines it.

### Fixed
- The alignment model (`:getain#`) was never shown: the reply was read as
  "stars,RMS,polar error" while the mount sends nine fields (RA axis azimuth
  and altitude, polar error, position angle, orthogonality, knob turns,
  number of model TERMS, RMS). It is now read as the protocol describes it,
  "E" fields included; the report says "Model terms".

## 4.4.15 — 2026-11-22

### Fixed
- Manual (EN/FR/NL): no heading left alone at the foot of a page. The room
  reserved before a box or a screenshot was itself a page break when it came
  right after a heading; it is now skipped there, and the preference
  screenshots are smaller so that heading and screenshot fit together.

## 4.4.14 — 2026-11-22

### Changed
- Drop-down lists get the same arrow as the spin boxes (a clear white
  arrow on a button of its own; greyed when the list is disabled), instead of
  the faint grey mark left over from the system style.

## 4.4.13 — 2026-11-22

Checked again on the observatory PC (4K screen at 200 %), and the manual
rewritten.

### Changed
- **Thicker curves on high-density screens**: line widths are now in
  logical pixels (Qt draws them in physical pixels: at 200 % the curves came
  out half as thick as intended); RA/DEC curves 2.5 px.
- The sigma curves are greyed too while the mount is parked; the faint
  titles behind the curves are gone (the coloured title above says it).
- Spin boxes have real arrows (tiny dots at 200 %).
- **Manual** (EN/FR/NL): what MountMonitor is for, an annotated screenshot
  of the main window, every setting, graph, curve and colour, the mount
  checks and what to do when one fails, a normal and a bad night, the night
  report section by section; the rating thresholds corrected (0.4/1.0/2.0"
  guided, 0.5/1.0/2.0" unguided precision). Screenshots made by
  `docs/manuel/captures.py` in simulation, in the three languages.

### Fixed
- The DEC strip did not show its tolerance (only shown after a change).
- "σ max" had one decimal more than the other figures.
- Firmware shown as "3.4 (ASCOM 1.7)", no English left in the French line.

## 4.4.12 — 2026-11-22

Night report reviewed in its three languages; window checked on a 4K
screen at 200 % on the observatory PC.

### Fixed
- **The night report had no spectrum at all**: the .dat keeps whole
  seconds (MountMonitor 3's format), so at 2 Hz most samples shared their
  time stamp, every repeat counted as a gap and the longest stretch was 7
  samples. Repeated stamps are now spread over their second; the FFT
  section is back (live window unaffected, it has real time stamps).
- **Tolerance table on the jitter basis**: it counted the dither steps
  and announced 21 % of samples over 0.5" on a night rated EXCELLENT on a
  0.165" jitter. It now counts the very samples the jitter uses.
- Report: French titles with their accents, RA/DEC as AD/DÉC (RK/DEC),
  tracking states, FFT table, clock section and counts in the report's
  language (54 047, not 54,047).
- Window: the history's air line, pier side, time-graph legend and figures
  translated; standard buttons (Cancel...) translated through Qt's own
  catalogues; ticked boxes show a tick; the ASCOM driver's description is
  no longer shown as the mount's identifier; "correction ... activée".

### Changed
- **Rounded curves** (option, on by default): RA/DEC drawn with a
  monotone cubic (PCHIP) that never goes beyond the samples, so no
  invented peak; dots mark the real samples on short spans; thicker
  anti-aliased lines on every PC. Curves greyed while the mount is parked.
- **Figures above the graphs**: value, sigma, tolerance, min/max and
  sigma max (RA, DEC), and the clock figures, moved from the corner of the
  graph, where the curves ran over them, to a strip above it. In the time
  graph each figure takes its curve's colour and replaces the legend that
  covered the curves.
- Report: dropped the figures that said nothing about the tracking
  (mean, median, min, max, peak-to-peak and percentiles of the raw
  deviations; mean and maximum of the running sigma, which took in the
  slews).

## 4.4.11 — 2026-11-22

### Fixed
- **No "RA tolerance exceeded" on a parked mount**: parked, idle or
  slewing, the mount does not follow the sky and its RA drifts by 15" a
  second, so every connection to a parked mount logged a tolerance alarm.
  Tolerances are now judged only while tracking; meanwhile the deviations
  are shown greyed, with a tooltip saying why.

## 4.4.10 — 2026-11-22

### Changed
- The third value of the air gauge was labelled "inside", as if it were the
  air: it is the mount's internal sensor 1 (:GTMP1#), in its electronics,
  hence some 20 °C above the air. Now labelled "mount elec." and explained
  in the tooltip, in the three languages.

## 4.4.9 — 2026-11-22

### Added
- **Air gauge** under the coordinates: outside temperature and pressure
  read from the mount every 30 s (those the refraction correction uses,
  whether a weather station or a script pushes them), inside temperature
  and time to the meridian flip, with an arrow for the last change.

### Changed
- The history gets an air line only when the temperature changes by
  0.5 °C or the pressure by 1 hPa, instead of every 30 s.

## 4.4.8 — 2026-11-22

### Fixed
- **Check results in the user's language**: the refraction mode, GPS and
  dual-tracking values appeared as raw English keys inside translated
  sentences ("La réfraction est « not updating »", "Le GPS est not
  synchronising"). They now use the same words as the preferences, quoted
  the same way in every check.

## 4.4.7 — 2026-11-22

4.4.6 run on the observatory PC through the 10Micron ASCOM driver, with
NINA connected to the same driver.

### Fixed
- **Positions repeated by the ASCOM driver's cache**: the 10Micron driver
  serves RA/DEC from a cache refreshed about every 2 s, so at 2 Hz three
  samples out of four repeated the previous position with a later time
  stamp, a staircase that was not the mount's. Repeats are now skipped (a
  sample is still kept at least every 5 s), and the history says so once.
- **Mount named after its driver in ASCOM mode**: product and firmware
  showed "10Micron Mount Driver" and "1.7" (the driver's version). They now
  come from the mount (:GVP#, :GVN#), e.g. "10micron GM1000HPS", "3.4 (ASCOM
  driver 1.7)", with the driver's properties as a fallback.

## 4.4.6 — 2026-11-22

Tested on a GM1000HPS (firmware 3.4) through the 10Micron ASCOM driver
1.7.2, shared with NINA over the RS-232 link.

### Fixed
- **No 10Micron check worked in ASCOM mode**: commands were sent with
  raw=False, so the driver wrapped them a second time ("::GREF##"), they
  failed its validation and refraction, refraction mode, dual tracking, GPS
  and the environment readings all came back empty. They are now sent raw;
  the one-character replies (:GREF#, :Gdat#) go through CommandBool as the
  driver requires.
- **GPS check in ASCOM mode** used ":gps#", which is not a 10Micron command;
  it now uses :gtgpps# (firmware 3.2.5 and later) or :gtg#, as in LX200 mode.

### Added
- **Preference list in ASCOM mode** (Follow object, tracking correction,
  speed) when the driver lets :PRlist# through. The 10Micron driver refuses
  it unless "unchecked raw commands" is allowed in its setup; the history
  then says why these three checks are skipped, without raising an alarm.

## 4.4.5 — 2026-11-21

Nicolàs de Hilster's remarks on the preferences and the FFT window, and the
:PRlist# lists he read on his GM3000HPS in sixteen situations.

### Fixed
- **Fields that do not apply now look disabled**: the connection fields of
  the other protocols were already disabled, but the style sheet painted them
  like active ones, so they looked editable until clicked. Disabled fields,
  their labels and greyed boxes are now drawn greyed throughout.
- **Follow object no longer raises a false alarm**: the lists show that
  Follow object switches the tracking speed to "Custom" and writes the
  object's rates there. With a non-sidereal rate expected, "Custom" is now
  reported as the object's rate (r.a. and dec. given), not as a wrong speed.
- **Empty DEC spectrum**: on a quantised axis most samples do not move, so
  the median step was zero and the dither filter took every move for a jump,
  flattening the whole signal. Jumps are now judged against the median of
  the steps that do move. Test: a 0.3" sine read in 0.1" units, with a
  dither, gives its 480 s peak at 0.31".
- **FFT window**: the seismometer has its own scale (right axis, ADC counts)
  instead of going off the arcsecond scale; the vertical scale follows the
  zoom; periods longer than the data (an artefact of zero padding, a flat
  plateau) are no longer drawn; a new button brings back the full
  horizontal range.

### Changed
- **Observing site in its own group**: read from the mount at each connection
  (:Gt#, :Gg#, :Gev#) and now kept in the preferences, where it shows greyed
  out while the mount is connected. Typing it is only needed when the mount or
  its driver does not report a site.

## 4.4.4 — 2026-11-21

Nicolàs de Hilster's test of 4.4.3 (the alert now pops up on the desktop the
user is looking at).

### Changed
- **First departure from MountMonitor 3 -- Follow object allowed when the
  expected rate is not sidereal**: following the Sun or a planet is precisely
  what Follow object is for; with "solar" or "lunar" expected it is reported
  as allowed, and remains an error only when sidereal is expected.
- **Mount checked as soon as the preferences are accepted**, as MM3 does,
  with the new expectations.
- **History marker**: every check writes "### MOUNT SETTINGS CHECK ###" at
  the head of its results, so the block is easy to find. Checks at
  connection, after a slew and after the preferences always print their
  results; the periodic one only when something changed.
- **"King" removed from the expected tracking rates**: the King rate
  (sidereal corrected for refraction) comes from the ASCOM standard and is
  not offered by a 10Micron. The list now follows the mount: sidereal, solar,
  lunar. Settings file version 2 turns a saved "king" into sidereal.

## 4.4.3 — 2026-11-21

Nicolàs de Hilster's test of 4.4.2: the alert works; three follow-ups.

### Added
- **Mount preference list checked again** (`:PRlist#`, as MountMonitor 3):
  follow object off, tracking correction 0.000 %, tracking speed as expected.
  Sequence confirmed on a GM3000HPS: `:PRclr#` (one character, no '#') then
  `:PRlist#` chunk after chunk until the "c" end mark ("x" = more to come).
  Any wrong value joins the single alert window.
- **The alert comes to the user's virtual desktop** (Windows 10/11): it is
  moved to the desktop the user is working on (documented
  IVirtualDesktopManager interface); if that is not possible, it is forced to
  the foreground and Windows switches to MountMonitor's desktop.

### Fixed
- **"Mount parked: tracking checks skipped" one second after "Mount is
  tracking"**: right after connecting, the window's copy of the status was
  still unknown. The status is now read together with the checks, and the
  message says "not tracking" rather than "parked".
- The post-slew check in the polling thread duplicated the window's own
  check; removed.

## 4.4.2 — 2026-11-20

Nicolàs de Hilster's test of 4.4.1 on his 10Micron GM3000HPS (firmware 3.2.5):
the solar tracking alert never came, and the link timed out every minute.

### Fixed
- **Mount checks made the link time out**: `:GREF#` (refraction on/off) and
  `:Gdat#` (dual tracking) answer one character, '0' or '1', WITHOUT the
  closing '#' (MountWizzard4 lists them as COMMAND_B). MM4 waited for the '#':
  5 s timeout and reconnection at every check -- every minute with a 1 min
  check interval. They are now read as one character.
- **Shifted replies**: the late '1' of such an answer was read as the start of
  the next reply, shifting the ones after it -- the status read PARKED while
  the mount tracked, so the tracking-rate check was skipped and the solar
  rate never raised the alert. Leftover bytes are now dropped before each
  command.
- **GPS check used a command that does not exist** (`:gps#`): now `:gtgpps#`
  from firmware 3.2.5, `:gtg#` before.
- **The `:PRlist#` check after each slew** (follow object, tracking
  correction, tracking speed) followed up with `:PRnext#`, a command we could
  not confirm; it is switched off until the exact sequence is confirmed. The
  tracking rate is checked through `:GT#`.
- **Settings file versioned** (suggestion of Nicolàs de Hilster): it now
  carries `settings_version`. A file from an older MountMonitor is converted
  step by step at load (files without a number count as version 0); one from
  a newer version is left untouched. An unreadable file is kept aside as
  `settings.json.corrupt` instead of being overwritten by the defaults at the
  next save. The obsolete `tolerance_as_ha_seconds` key is dropped.
- **launch.bat** printed "The system cannot find the drive specified": `::`
  comments inside parenthesised blocks are read as drive labels by cmd.exe;
  they are `rem` now.

## 4.4.1 — 2026-11-20

### Changed
- **Time graph as in MountMonitor 3** (definitions from its author): the two
  loop times are drawn centred on their average and read on a right-hand axis
  showing average ± range, while the PC-mount and PC-NTP differences keep the
  left axis. Drawn at their raw ~1000 ms, the loop times stretched the scale
  over 1300 ms and flattened everything. The PC-NTP curve now counts in the
  vertical range too.

### Fixed
- **PC loop time** is the PC time at the mount's `:GL#` answer minus the
  previous one (MM3: pcNew - pcOld). It used the start of the polling cycle,
  set by the timer: a flat line that hid the latency jitter.

## 4.4.0 — 2026-11-20

Nicolàs de Hilster's test of 4.3.0 on his 10Micron, and the code in English.

### Code in English
- **Identifiers, comments, docstrings and developer messages are now in
  English** throughout the program, its tests and its tools (608 names, about
  1,600 comment lines), so that the project can be worked on together. File
  renames: `src/core/spectre.py` → `spectrum.py`, `src/utils/ajustement.py` →
  `fitting.py`, `src/gui/aide_textes.py` → `help_texts.py`,
  `src/gui/rapport_textes.py` → `report_texts.py`, the `verifier_*.py` checks
  → `check_*.py`, and the French test file names. Behaviour is unchanged; the
  interface stays trilingual (EN/FR/NL). The files shared with the other
  applications of the kit (updater, reporting, packaging) keep their names.
- The 10Micron log analysis showed a "State (FR)" column whatever the
  language, and no Dutch state names: one state column now, in the interface
  language. The "Open log file" dialog had no Dutch either.

### Fixed
- **A mount left in solar mode raised no alarm**: the tracking-rate check
  accepted any `:GT#` answer starting with "60" -- solar (60.3) passed for
  sidereal (60.2). The answer is now classified (60.2 sidereal, 60.3 solar,
  62.4 lunar, as MountWizzard4 reads them; ASCOM names as before).
- **Seismometer offset sign**: MountMonitor 3 centres the data as reading +
  offset; MM4 subtracted it, so a sensor resting near -300 with an offset of
  300 sat at -600. The .sei columns keep the MM3 order (raw, centred).
- **RA tolerance label** said "arcsec" while the value was in seconds of
  time; it now names the unit in use.

### Changed
- **Mount settings checked every 5 minutes** (adjustable, 0 = off), not only
  at connection and after a slew. One alert window, on top of the other
  programs and flashing in the taskbar, updated rather than stacked, closed by
  itself once the mount is put right, and switchable off in Preferences. The
  history records a check only when its outcome changes.
- **Graphs aligned**: same left and right axis widths on every graph, so a
  spike in RA sits right above the same instant in the time graph.
- **Time graph**: the mount-loop curve is drawn half-transparent under the
  green PC-loop curve.

## 4.3.0 — 2026-11-20

Second comparison with MountMonitor 3 by Nicolàs de Hilster, side by side on a
10Micron in solar and sidereal tracking.

### Changed
- **Standard deviation on its own scale**, right axis, from zero at the
  bottom, top = the power of ten just above 3.3 × the largest sigma (the
  MountMonitor 3 rule). On the deviation scale it was a flat line, and under
  non-sidereal tracking the drift pushed the scale so far it disappeared.
- **Graphs centred on the median of the visible data**, recomputed at every
  refresh, from the raw coordinates. Each stored deviation had been taken
  from the median of its own moment, so a target drifting at a
  non-sidereal rate drew a line leaving zero instead of a centred drift.
- **RA in hours or degrees, applied everywhere and at once**: hours (default)
  shows RA deviations, sigma and tolerance in seconds of time; degrees in
  arcseconds of RA (× 15), as in MountMonitor 3. The choice used to change
  only the RA readout, and only after a restart. The RA tolerance is entered
  in the chosen unit; tolerance alarms compare in that unit. The night report
  keeps true arcseconds on the sky. The separate "tolerance in seconds of
  hour angle" box is gone (it is the hours mode).
- **Mount checks in MountMonitor 3's order, refraction split in two**:
  refraction correction enabled/disabled (`:GREF#`), refraction update mode
  (`:WSG#`), GPS, dual tracking, tracking rate. The mode check is skipped
  when the correction is off.
- **Time graph**: the green PC-loop curve is drawn on top, as in MM3.

### Fixed
- **Refraction update mode read with the wrong command**: `:GREF#` only says
  whether the correction is on (0/1); read as the mode, an enabled
  correction reported "not updating while tracking". The mode is `:WSG#`
  (checked against MountWizzard4, which reads and sets it with
  `:WSG#`/`:WSS<n>#`).
- **Seismometer showed nothing**: the graph layout saved by a session with
  three graphs squeezed a fourth one to zero height; enabling the
  seismometer took effect only after reconnecting, and its graph only after a
  restart; a port that would not open (often held by JamaSeis) was reported
  in the log file alone; only CR+LF line ends were read. Now: applied at once
  from the preferences, a hidden graph gets its share back, the history says
  when the port cannot be opened or when nothing has arrived after 15 s,
  lines may end in CR, LF or both, the baud rate can be set, and values are
  delivered every second even from a device slower than the setting.

## 4.2.1 — 2026-11-20

### Changed
- **Unattended operation in one place**: the four boxes that decide when
  MountMonitor connects, records and closes the night moved from the
  Processing tab (under "Log mode") to their own group on the General tab,
  with a line saying how to start it at boot (`--connect`). They are also on
  a right click of the record button.
- **"Night only" says what it does**: the box formerly called "End the night
  and write the report at sunrise" also kept recording from starting in
  daylight. It is now "Night only: record after sunset, end the night and
  write the report at sunrise"; unticked, day-time sessions (solar observing)
  are recorded. Unticking it while armed in daylight with the mount tracking
  starts recording at once. The daylight message and the button tooltip say
  where to change it.

### Fixed
- **Power cut**: the files were flushed every 20 lines but never forced to
  the disk; whatever the operating system still held was lost. They are now
  flushed and synced (fsync) at least every 5 s.
- Removed an unused label that described the pause on park as "stop and
  write the night report".

## 4.2.0 — 2026-11-19

First feedback from Nicolàs de Hilster on 4.1.0.

### Changed
- **Time span from 30 s to one hour** (View > Time span, or right click on any
  graph), kept between launches. The horizontal zoom could only shrink the
  two-minute window; half an hour of tracking could not be seen. Time marks
  space themselves out (every 5 min on one hour) and each pixel keeps the peak
  of what it summarises, so an hour costs no more to draw than two minutes.
- **Right click on a graph opens MountMonitor's menu**, not pyqtgraph's: its
  "X axis / Y axis" ranges were overwritten by the next refresh, a quarter of a
  second later, so the span looked settable and never stayed.
- **Vertical scale applied**: the menu choice was saved, then overridden four
  times a second by a range that always included the tolerance lines. *Data
  only* now fits the curve and lets the tolerance lines leave the frame when
  tracking is much better than them; the choice is restored at launch.
- **Right-hand pane**: status, RA, DEC and rate boxes have a fixed height and
  the history takes all the remaining height, following the window. The
  values are no longer each boxed (a stylesheet meant for the frame also hit
  every label inside it).
- **Armed button says what it waits for**: "Armed: starts when the mount
  tracks", or "Armed: starts at nightfall" when the mount already tracks in
  daylight — the old "ARMED — waiting for tracking" contradicted a status line
  saying the mount was tracking. A message says it once in the history, the
  tooltip explains that nothing is recorded yet and that a click disarms.

### Fixed
- **Clock drift jumped with every sample**: it was the last point minus the
  first of the visible window, each carrying tens of milliseconds of noise. It
  is now a least-squares slope over the last half hour with spikes rejected
  (slow loops), in ms/h, shown only once two minutes of data exist. On a
  12 ms/h synthetic drift with 15 ms noise and 600 ms spikes it stays within
  5 ms/h and moves by less than 1 ms/h between samples.

## 4.1.0 — 2026-11-18

Full audit: every figure checked against a synthetic signal whose truth is
known, and the program measured on a full buffer. Aimed also at small
observatory PCs (2-4 cores, 4 GB, old Intel graphics).

### Fixed — figures
- **FFT amplitude halved**: the Hann window was not compensated (2/n instead
  of 2/Σw). A 1.5″ peak periodic error read 0.67″. Amplitudes are now
  labelled ″ peak; the seismic axis says ADC counts.
- **Live FFT, replay FFT and the .fft file worked on raw data**: a 20″/h drift
  produced a 5000 s "peak" and hid a 480 s worm period. One spectrum module
  for all of them now removes the drift and the dither steps (which made
  phantom 10-20 min peaks in the report), uses the longest stretch without a
  gap (a 40 min pause made periods 20 % too long), measures the sampling rate
  on the data and refines the peak by zero-padding. The peak list gives
  distinct lines, not the main peak and its neighbouring bins.
- **Jitter without dithers included the drift**: an unguided target is a
  single plateau; 0.2″ of jitter with a 5″/h drift read 5.9″, rated BAD.
  A straight line is now removed from each plateau.
- **PC-mount clock offset in ASCOM was fictitious**: the mount time was cut
  to the second (0-1000 ms sawtooth, loop time 0 or 1000 ms). Hundredths kept,
  and the PC reference is taken in the middle of the exchange.
- **ASCOM coordinates quantised** to 0.15″ (RA) and 0.1″ (DEC) by their
  conversion to text: four and three decimals now.
- **Axial speed 3600 times too small**: :GaXa#/:GaXb# give degrees; sidereal
  tracking showed 0.0042 ″/s. Steps across 0/360° are unwrapped; in replay,
  equal time stamps are dropped instead of dividing by 1e-6.
- **Replay across the end of daylight saving time** (LX200 local time): two
  hours were read as one, halving every FFT period.
- **Seismometer**: each reading of a batch gets its own time (they all had
  the delivery time); tolerance lines follow the preferences (they stayed at
  ±100).
- **Axis labels**: no automatic SI prefixes ("kms", "m″" read as minutes).

### Fixed — reliability
- **Reconnection gave up for good after 5 attempts** (about 30 s): a mount
  that rebooted was never found again. Attempts now continue, spaced 2, 4, 8…
  up to 60 s.
- **LX200 precision command**: `:U#` has no reply and TOGGLES the precision;
  waiting for a reply cost 5 s and marked the new link as lost, and a mount
  already in high precision went back to short formats (then every sample was
  dropped). `:U2#` is sent without reading, and the short formats are read.
  Nothing is sent through ASCOM (it would toggle the mount for NINA too).
- **The connection, the mount checks and the target query no longer run on
  the window thread**: an unreachable mount froze the window 5 s, every 30 s
  with --connect. One thread owns the mount (ASCOM objects stay in the COM
  apartment that created them); the window sends it requests.
- **Running STDEV vectorised** (1.3 ms instead of 50 ms per buffer): the
  poller lost 22 % of its samples at 10 Hz, more on a small PC.
- **Dawn and park froze the window** about 7 s (25 s and more on a small PC):
  the session is now read once, in a background thread, which also writes the
  three reports. Opening a log file is done the same way.
- **Memory leak**: each night's analysis window was hidden, not freed
  (+100 MB per night).
- **Seismometer data crossed threads unprotected** into the session files:
  they now go through a queued signal. Its read buffer is bounded.
- **One modal box per end of slew** when a setting diverged, piling up all
  night: one non-modal box, updated, in the three languages.
- **Armed in daylight while the mount already tracked**: nothing started at
  sunset. The state is checked again every minute.
- **Disk full**: the files are always closed, and the first write error is
  shown once instead of being swallowed.
- A stray byte from the mount no longer raises an exception (false crash
  report).

### Changed — lighter
- Buffers are numpy rings: the graphs copy only the visible two minutes
  (rebuilt seven 50,000-point arrays four times a second before).
- Graph cadence adapts: 4/s, 2/s from the start on 2-4 cores, down to 1/s
  when drawing takes too long; nothing is drawn while the window is minimised.
  Antialiasing only from 8 threads up; OpenGL stays off.
- The FFT window draws only what fits on screen.

### Security
- **Signed updates**: each release publishes a manifest (version and SHA-256
  of the update archives) signed with an Ed25519 key that is not in the
  repository. From 4.1.0 on, the application installs an update only if its
  archive is listed in a manifest signed by that key (public key in kit.json,
  verified in pure Python, `signature_maj.py`). A stolen GitHub token can no
  longer push code to installed copies.
- Update: SHA-256 of the archive checked against the one GitHub publishes,
  size bounded, address checked again after redirects, download in a thread,
  stricter extraction path check.
- Reports: the machine name is no longer sent (random installation id
  instead), host and user names are masked in traces; the report queue is
  pruned even without consent.
- .log10m files: decompression bounded.

## 4.0.0 — 2026-11-18

### Changed
- **MountMonitor 4.0**: with the agreement of Nicolàs de Hilster, author of the
  original Java MountMonitor (v3.37, 2018-2021), this program becomes its
  successor and is now developed jointly. The numbering follows on from
  v3.37: 4.0.0 comes after 1.33.0, and installed copies are offered the
  update as usual. No change in behaviour from 1.33.0.

## 1.33.0 — 2026-11-10

### Added
- **Connection at launch** for an observatory PC that starts on its own: the
  `--connect` option, or *Connect to the mount when MountMonitor opens* in the
  Preferences. While the mount does not answer (control box still booting), a
  new attempt every 30 s (`connect_retry_s`, 5 s minimum) until the first
  success; a click on Connect/Disconnect stops the attempts. No dialog during
  these attempts (ASCOM Chooser not opened, previous-crash offer kept for the
  next launch). Recording then follows the arming setting.

## 1.32.0 — 2026-10-14

### Changed
- **Fixed look on every system**: Fusion style, a complete palette (active,
  inactive and disabled groups) and embedded fonts (Source Sans 3, Source Code
  Pro for figures), whatever the system theme, accent colour or fonts. The
  monospaced texts used Consolas, which only exists on Windows.
- **Real file chooser on Linux** (full Qt dialog with sidebar and folder tree)
  where the portal's dialog is reduced.
- **Help menu**: *Report a problem…* sends a written report to the collection
  point, and *Send crash reports automatically* withdraws or restores consent;
  the GitHub entry is now *Report a Bug on GitHub*. The About box shows the logo
  and speaks Dutch too.
- **Logo**: one SVG source (`logo.svg`) for the icon, the About box and the
  manuals (ICO, ICNS, PNG 16–512); `icon.png` and `about.png` are gone.
- **Manuals** (EN/FR/NL) in the house PDF format, with a real screenshot of the
  window in each language, version taken from `VERSION`.
- **Translations**: the 10micron log dialog now follows the chosen language
  (it read the system locale) and speaks Dutch; the last texts written in one
  language (preference lists, baud rate, error prefixes, "already running")
  are translated; a test catches hard-coded displayed texts.
- **Packaging**: common kit workflow and `build_unix.py` (Linux `installer.sh`,
  stripped `libpython`, version check, `--check` start test on every system).

### Fixed
- **Native crash traces were lost**: the trace file was reopened (emptied)
  before the previous session's trace was read.
- The simulated mount reported a real observing site; it now reports the
  example site used everywhere else (Observatoire de Haute-Provence).

## 1.31.1 — 2026-10-13

### Fixed
- **macOS and Linux: automatic updates never worked.** Two defects in the
  shared update kit: the installed package was only recognised by
  `python/python.exe` (Windows), so the macOS and Linux packages believed they
  ran from source and never looked for a new version; and `build_unix.py` did
  not ship `kit.json`, so the distribution repository was empty. Both fixed;
  the Unix build now fails if the update check would not work. An update was
  tested end to end on the real Linux package. **macOS and Linux installations
  up to 1.31.0 must be reinstalled once by hand.**
- macOS and Linux: settings, report consent and session logs were written
  inside the program folder (a consequence of the same defect). They now live
  in the data folder (`~/.local/share/MountMonitor`) and are copied there once
  from the old location, without overwriting anything.

### Changed
- Removal of personal mentions; installer publisher and the header of
  `reporting.py` now read ARP273-ROSE. The example observing site (preferences
  placeholder, tests, night simulator) is now the Observatoire de Haute-Provence
  (43.9317 N, 5.7122 E, 650 m); the twilight reference values of the tests were
  recomputed with skyfield/DE421. Teaching documents use example configurations.
  Settings location (`QSettings` organisation `ARP273`) is unchanged.
- Privacy guard `tests/test_confidentialite.py` (files, PDF text and metadata,
  PNG, binaries), run by CI.

## 1.31.0 — 2026-09-25

### Fixed
- **The graphs still did not scroll, and the axis still read in ks.** The 1.28
  fix applied the "one point per pixel" rule to the wrong data: each graph was
  handed the whole buffer -- up to 50 000 samples, several nights chained --
  decimated to 5 000 points, so each displayed point stood for about ten
  samples and the window spanned hours. The axis started at the beginning of
  the buffer, hence the kiloseconds.
- The automatic graph dump ("each time the window width is filled") counted
  buffer samples. The buffer is circular and caps at 50 000: once full its
  size never changes, and the dumps silently stopped mid-night.

### Changed
- The graphs now show **the last two minutes, at full resolution, scrolling at
  the present**: the time axis runs from -120 s to 0. The horizontal zoom
  divides that width (5x = the last 24 s). The 30 s markers sit on real clock
  times and scroll with the curve, labelled HH:MM:SS. The vertical scale and
  the sigma overlay follow the visible window only; night-long min/max stay
  computed on the whole buffer. Replaying a session still shows it whole.
- Graph dumps now fire each time the window has been fully renewed, so every
  image shows a different slice of the night.

## 1.28.0 — 2026-09-24

### Fixed
- **The graphs stopped scrolling.** A regression of my own: when the horizontal
  zoom was added, the window start returned 0.0 for any zoom of 1 or less --
  the beginning of the buffer. Zoom 1 being the default, the axis started at
  zero and stretched as the night went on, crushing the data into the middle.
  After seven hours it reached 26 ks and displayed a 1960" standard deviation
  while the side panel gave the true figures: 0.06" in RA, 0.14" in DEC.
- Two poller messages were hard-coded in English, and one of them was wrong.
  "Logging started." does not announce a recording: it reports that the mount
  checks passed after a slew. Returning at every dither, it made the session
  look as though it restarted every twenty seconds.

## 1.27.0 — 2026-09-24

### Added
- **The program now chains nights unattended.** At sunrise it closed the night
  and stayed connected but idle: someone had to click every evening. It
  re-arms itself after the morning close.
- A daylight guard breaks a loop the first version created: the mount is often
  still tracking at sunrise, so re-arming restarted within the second --
  closing the night and immediately reopening a file in broad daylight.
- The morning analysis window no longer blocks: it was modal, and would have
  frozen the event loop on the first unattended morning.

## 1.26.0 — 2026-09-24

### Fixed
- **In the morning, the ephemeris described the night that had just ended.** A
  09:16 connection announced 21:35 -> 05:48 where tonight's values are
  21:32 -> 05:50. Starting from the local noon before the reference is right
  for a session opened at 02:00; at nine in the morning one is looking ahead.
  The Sun settles it.

## 1.25.0 — 2026-09-23

### Fixed
- **An analysis window opened on connection.** The automatic analysis fired on
  any PARKED status and analysed the newest .dat on disk, so connecting to an
  already-parked mount opened a report on an unrelated night.
- **The French tab showed Dutch.** On an empty session, two early returns in
  `_run_analysis` wrote into the current view without checking the requested
  language. The tabs call it once per language, so the last call -- Dutch --
  overwrote the tab of the application's own language.
- Release notes are written in all three languages, each under its own
  heading, and the update window shows only the user's. Their download table
  also listed `-macos.dmg` and `-linux.tar.gz`, which no longer exist.

## 1.24.0 — 2026-09-23

### Fixed
- **Recording started even on a parked mount.** Arming covered the button
  only; connection called `_start_logging` directly.
- **Longitude flipped west.** ASCOM counts `SiteLongitude` positive EAST, the
  LX200 protocol west, and the driver's string was read with the LX200
  convention: a site 5.71 deg east became 5.71 deg west. It does not announce
  itself -- it moves the observatory, and shifted every twilight by 46
  minutes.
- **"Tracking rate: Sidereal OK" on a parked mount.** The check read the
  configured rate, not the actual state.
- The status log mixed two languages: sixteen more labels translated.

## 1.23.0 — 2026-09-23

### Fixed
- **A test was protecting the defect it should have reported.** It asked for a
  French report, then checked it contained "Rating" and "Combined jitter".
- Twelve tests added for the day's corrections. The suite has 65.

### Removed
- `docs/GUIDE_UTILISATEUR.md`, 1075 lines, superseded by the manual.

## 1.22.0 — 2026-09-23

### Changed
- **The manual was rewritten and translated.** Its statistics chapter still
  taught the reading that has since been refuted: a raw standard deviation as
  a measure of tracking. Every paragraph was also doubled by its English
  translation in italics, so the document was a real manual in neither
  language. Three separate documents now, one per language, 19 to 20 pages.
- The Help menu gained a "Manual (PDF)" entry.

## 1.21.0 — 2026-09-23

### Fixed
- **72 tooltips showed two languages at once** and none in Dutch.
- **Settings did not survive a restart**: horizontal zoom and vertical zoom
  mode were never saved, and panel positions were neither saved nor restored
  although the read-me promised a "persistent layout".

### Changed
- The three session settings are on by default.

## 1.20.0 — 2026-09-23

### Changed
- **The built-in help described version 1.6.** Two hard-coded strings, English
  and French; a Dutch user got English. It now lives in `aide_textes.py`,
  eleven sections in three languages.
- This CHANGELOG created; the read-me had not mentioned anything since 1.7.0.

## 1.19.0 — 2026-09-23

### Fixed
- **The consent question was asked in two languages at once.** French and
  English were stacked in the same box, buttons included (`Autoriser / Allow`).
  A Dutch user read neither, and everyone else read it twice — immediately
  before deciding whether to allow anything to be sent. The crash dialog shown
  at the next start had the same defect. Both now use the user's language only.
- The chosen language is now applied **before** those dialogs: the crash box
  appears well before the main window, so it used to speak the auto-detected
  system language instead of the one the user had set.
- **Installed RAM read as 0 GB on every Mac.** `/proc/meminfo` does not exist on
  macOS; the exception was swallowed and the incident report carried a wrong
  number in the one place someone looks when diagnosing a freeze. macOS now
  goes through `sysctl hw.memsize`.

## 1.18.0 — 2026-09-23

### Added
- **macOS Intel packages.** `macos-latest` has been Apple Silicon since 2024
  and the bundled Python is architecture-specific, so the published `.dmg` was
  arm64-only: an Intel Mac could not open it at all. Releases now carry one
  package per architecture, each named accordingly.
- **Linux ARM64 packages**, built on `ubuntu-24.04-arm`.

### Changed
- **PyQt6 capped below 6.10.** Version 6.10 moved its Linux wheels from
  `manylinux_2_28` to `manylinux_2_34`, which required glibc 2.34 and shut out
  Debian 11, Ubuntu 20.04 and RHEL 8 — four years of still-current
  distributions — for Qt features the application does not use. Measured on the
  shipped binaries: `libQt6Gui` demanded `GLIBC_2.34` where the bundled Python
  needed only `GLIBC_2.17`.
- Supported systems are now stated in the read-me, verified against the
  published packages and the PyPI wheel metadata.

## 1.17.0 — 2026-09-23

### Fixed
- **Samples following a slew counted as tracking.** The mount reports TRACKING
  as soon as the slew command ends, while the axes are still settling. Five
  seconds are now discarded at every resumption, on the analysis side: 94
  samples on one night, and the declination of the shortest target fell from
  0.227″ to 0.137″.
- **Threshold crossings were counted as movements.** A 70″ re-centering trips
  the threshold at every sample it takes to complete. One night read as 98
  crossings where there were 53 actual moves, and the report announced
  "47 movements of median amplitude 0.79″" where it should have read
  53 movements of 6.47″.
- Ten report messages were hard-coded in English **and** French together, so
  the Dutch report was not Dutch and the French one said everything twice. All
  373 keys across both dictionaries are now complete in en/fr/nl.
- The session start time is timezone-aware, taken from the PC's own setting via
  `astimezone()` — the one portable way to get the local offset on Windows,
  macOS and Linux that also follows DST.

### Added
- **Commanded moves are classified** as dither, re-centering, or unsettled, in
  their own report section. A move whose aftermath stays several times the
  usual spread is the one worth looking at.
- The jitter is measured between moves with a two-sample margin after each, so
  that a sequence dithering every frame does not score worse than one that
  never does. On the reference night: 0.0755″ in RA, 0.1324″ in DEC.

## 1.16.0 — 2026-09-23

### Added
- **Night ephemeris**, computed from the site the mount reports (`:Gt#` /
  `:Gg#`), with a preference fallback — needed, since a mount that was never
  given its site answers nothing. Pure Python, checked against skyfield/DE421
  over five sites, 36 dates and eight boundaries: worst case 23.8 s.
- The report says **how much of the astronomical night a session covered**.
  On the reference night, 8 h 07 of 8 h 13, plus 49 min recorded after dawn.
- The site and the UTC offset are written into the `.dat` header, in decimal
  degrees with longitude positive **east**. LX200 counts longitude positive
  west and the preferences hold plain decimals; both are normalised on writing,
  because guessing wrong flips the hemisphere.

### Changed
- **Automatic stop became a suspension.** A mount that parks at 02:00 and
  resumes at 03:00 is still the same night: closing the session would have
  split it across two files and two reports. Recording now stops writing but
  keeps the session open, and resumes in the same file. Only sunrise ends the
  night — and only once the Sun has actually been below the horizon during the
  session, so a daytime trial does not close itself.

## 1.15.0 — 2026-09-23

### Added
- **A Language menu**, in the menu bar. The setting existed, buried in the
  "Layout" group of the preferences, and changed nothing visible — menus and
  labels are built once at startup. Each entry is written in its own language,
  because someone who landed in the wrong one cannot read the current one to
  find their way out. Changing it offers a restart, unless a recording is
  running.
- **The logger can be armed.** A mount connected at noon for a night starting
  at 19:00 wrote seven hours of nothing. Armed, it waits for the first TRACKING
  sample — or starts at once if the mount is already tracking. Optional, and
  off by default.

## 1.14.0 — 2026-09-23

### Fixed
- **The excursion filter discarded 59% of the night.** The 30″ threshold was
  applied to the raw distance from the segment median. An unguided mount left
  8 h on one target drifts far past that without anything being commanded: on
  the reference session the declination drifted −16.8″/h, some 134″ end to end,
  so 36,336 of that target's 54,388 samples were thrown out and labelled
  "commanded excursions". The threshold now applies to the residual after a
  block-median baseline, which follows both the curve of the drift and the step
  left by a re-centering. **99.5% of samples kept instead of 41.1%**, and the
  jitter barely moved (0.083″ → 0.076″ in RA) — which is what confirmed it had
  been right all along.
- **Running STDEV straddled the moves.** Computed live over a 60 s window, it
  described the movement rather than the tracking at the start of a segment,
  after an acquisition gap and after each repositioning. One 33 s target
  reported a mean of 69.9″ for a peak-to-peak of 0.64″.
- **The tolerance analysis contradicted the verdict.** It ran on raw
  deviations while announcing itself as tracking status, so a session rated
  EXCELLENT on a 0.171″ jitter then declared 70% of samples beyond 2″. It now
  uses the same basis as the jitter: 4.5% beyond 2″ in RA.
- "Slew samples excluded" actually counted samples outside any segment —
  36,342 of them, in a file holding 231 SLEWING samples. Renamed, and down to
  283 by the fix above.

## 1.13.0 — 2026-09-22

### Added
- The night report is written in **three languages**, one tab per language,
  and saved automatically next to the `.dat` at the end of a session.
- Automatic language detection, and packages for macOS and Linux built the same
  way as the Windows one.

## 1.12.0 and earlier

- Replay mode fixed: black screens, and the night report that never arrived.
- **The jitter is measured between repositionings, not around a straight
  line.** A deviation record is a staircase, not a noisy line: the sequencer
  dithers between exposures and the mount stays on its new step. Removing a
  linear drift does not remove a staircase. On one session the raw combined RMS
  read 86.269″ — a damning verdict — while the mount was holding each position
  to 0.179″.
- MIT licence file added; the badge had pointed at a file that did not exist.
- Graph tick marks now follow the data.
