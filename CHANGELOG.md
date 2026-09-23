# Changelog

All notable changes to MountMonitor are recorded here. Versions follow
[semantic versioning](https://semver.org/): the minor number rises when
behaviour changes, the patch number when only a defect is fixed.

Figures quoted below were measured on real sessions, not estimated.

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
