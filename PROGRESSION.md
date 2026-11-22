# MountMonitor 4: progress and resume note

## Resume note (2026-11-22, evening)

**State:** master = tag **v4.4.15** (release workflow: signed updates,
release_unique keeps only the latest Release). Code, comments and commits in
English; user texts trilingual (EN/FR/NL) in `src/utils/i18n.py` and
`src/gui/report_texts.py`.

**Done today (4.4.5 -> 4.4.13):** ASCOM path fixed (raw commands,
CommandBool, GPS command, preference list, cache repeats skipped, mount
product/firmware), air gauge, no tolerance alarm while parked, night report
reviewed (spectrum restored for whole-second .dat stamps, tolerance table on
the jitter basis, translations, useless raw figures removed), window
translated, rounded monotone curves (PCHIP, never beyond the samples),
figures moved to a strip above each graph, line widths in logical pixels,
spin-box arrows, manual rewritten (35-36 pages) with annotated screenshots.

**Tested on real hardware (GM1000HPS fw 3.4, read-only):** LX200 TCP/IP and
ASCOM through the 10Micron driver 1.7.2 shared with NINA; GUI of 4.4.11 and
4.4.12 checked on a 4K screen at 200 %.

**Not verified yet:**
- (done) 4.4.13-4.4.15 checked on the real PC at 4K/200 %: line thickness, spin-box and drop-down arrows, Help > Manual opens; the installed manual_fr.pdf is byte-identical (1 231 245 bytes) to the one checked here for orphan headings.
- A full night of real tracking in ASCOM since 4.4.7 (curves, night report,
  6 s preference read every 5 min).

**Next steps:**
1. (done) Recap mail sent to the MM3 author; answer received 22/11: :GTMP1# = RA motor driver
   (protocol 3.2.5 p. 21; 9 = electronics box, special mounts only).
2. After a real night: night report (FFT section now present), air gauge.
3. (done in the working tree, not released) `env_inside` = "RA driver" in EN/FR/NL, help text
   and the three manuals; screenshots still show the old label -> rerun captures before the release.
3b. MM3 author's point on ASCOM: never send non-ASCOM (LX200) commands to an ASCOM driver;
   MM3 keeps an LX200 -> ASCOM table and skips rows without an ASCOM equivalent. Today
   ascom_connection sends raw :GRTMP#, :GaXa#, :PRlist#... to ANY driver. Decision pending.
4. Screenshots: `QT_QPA_PLATFORM=offscreen MM_CAPTURE_RUN_S=150 python -B
   docs/manuel/captures.py`, then `python docs/manuel/compiler.py`.
5. Pre-existing: `check_subprocesses.py` flags `reporting.py:218` (kit file).

**How to work:**
- Tests: `QT_QPA_PLATFORM=offscreen python -m pytest -q tests` (176 pass).
- Code must compile on Python 3.10 (the MM3 author runs from source).
- Manuals: `cd docs/manuel && python compiler.py` (pdflatex), commit the
  three PDFs with the .tex.
- Release: bump `VERSION`, entry in `CHANGELOG.md`, commit, push master,
  annotated tag `vX.Y.Z`, push the tag; the workflow builds, signs and
  publishes.
- The privacy test (`tests/test_confidentialite.py`) rejects real site
  coordinates: use made-up ones in tests.

**Pitfalls met:**
- The .dat keeps whole seconds: repeated stamps must be spread before any
  spectrum (`spread_whole_seconds`), or no contiguous stretch is long enough.
- Cosmetic pen widths are physical pixels: multiply by devicePixelRatio
  (`_w()` in graph_widgets).
- Never draw figures inside a graph: they go in the `_Header` strip.
- On a quantised axis the median step is 0: jump detection must use the
  median of the NON-zero steps (empty DEC spectrum, 4.4.5).
- The style sheet overrode the palette for disabled widgets: disabled
  rules must be in `STYLESHEET` (4.4.5).
- Follow object switches the tracking speed to "Custom" (4.4.5).
- Never use LX200 serial on a port an ASCOM driver already holds; choose
  ASCOM with the same driver.
