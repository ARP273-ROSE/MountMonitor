# Changelog

All notable changes to MountMonitor are recorded here. Versions follow
[semantic versioning](https://semver.org/): the minor number rises when
behaviour changes, the patch number when only a defect is fixed.

Figures quoted below were measured on real sessions, not estimated.

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
  convention: a site 2.76 deg east became 2.76 deg west. It does not announce
  itself -- it moves the observatory, and shifted every twilight by 22
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
