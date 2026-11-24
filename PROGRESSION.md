# MountMonitor 4: progress and resume note

## Resume note (2026-11-24)

**On master, not released (24/11):** remarks of the MM3 author on 4.5.4: axial title per
mode, RA/DEC figures coloured, `MainWindow._axial_mode()` = "off" in pure ASCOM (combo
greyed in Preferences), preferences reopen on the last tab (`preferences_tab`), time
sample held by the poller loop and dropped during slew + settle, no mouse zoom on the
graphs, automatic dumps drawn in colour, installer EN/FR/NL after the Windows language
(installer.iss now differs from the kit template; UTF-8 BOM added), MM3 credited as v3.40.
Then the audit of 24/11 (see CHANGELOG "Unreleased"): `pixel_downsampling` and
`density_antialias` in graph_widgets, timer lateness in `_adapt_rate`, `start_session` returns
False, dumps under the log folder, KIT_RELANCE relaunch, DataBuffer CLOCK_JUMP_S, seismometer
reopen + `_watch_seismometer`, background fsync, resets via `poller.submit`, crash dedupe.
Benchmarks: scratch scripts loop_run.py / per_graph.py (not kept). Not done: FFT computed in a
worker (46 ms every 2 s), asynchronous stop of poller/NTP on disconnect. Not checked: dependency
CVEs (pip-audit refused here). 200 tests. Next release: 4.5.5.

**Released as v4.5.4 (23/11 evening):** after the MM3 author's side-by-side screenshots
(figures agreed, look did not): axial graph draws only the regression speed vs its median;
displacement = integral of (reg - median) over the shown span, around its mean, + "sky"
(x cos dec, MM3 "SPH"); shift by range/2 (speed) or range (displacement) when
correct_graphs_for_range. Then aligned on MM3's drawing code (received 23/11 evening): rectangle-rule integral from
the first valid point, smoothing (4 prev + new)/5, symmetric scale x1.2, nothing below 30 points.

**Released as v4.5.3 (23/11):** axial speeds as MM3 (code sent by its author,
23/11): `src/core/axial.py` (raw, 6-sample mean, regression of the angle over the running
range, median reference); graph drawn relative to each axis' median; manuals updated.
Displacement mode NOT done: MM3 integrates the speed ("[x.xx"]" and "x cos(dec) [SPH]",
shifted by one running range) but its code was not sent -> asked for it.

**Released as v4.5.2 (23/11):** slew fix from the MM3
author's video (4.4.15 recorded during the final approach): `MountPoller._skip_for_slew` drops
samples while slewing and for delay_after_slew after the slew END, emits `slew_settled` ->
`MainWindow._on_slew_settled` (mount checks + target); reset "slewing" at slew end; delay
re-applied on preference change. tests/test_slew_settle.py.
:Gmte# note: his 128 min to the flip on the Sun at 09:50 UTC does not prove the horizon is
ignored (the Sun was rising, the flip limit comes first); label "tracking ends in" kept.

**State:** master = tag **v4.5.1** (23/11: target reference read while tracking, :Gmte# =
"tracking ends in", pure-ASCOM air text). Before: tag **v4.5.0** (22/11 afternoon: pure ASCOM by default + option
"10Micron commands through the ASCOM driver", :GTMP1# = RA driver, :getain# fixed).
Before that: tag v4.4.15 (release workflow: signed updates,
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
3. (released in 4.5.0) `env_inside` = "RA driver" in EN/FR/NL, help text
   and the three manuals; screenshots still show the old label -> rerun captures before the release.
3a. (released in 4.5.0) :getain# read as protocol 3.2.5 p. 9 describes it
   (`parse_getain`, tests/test_getain.py): polar error = field 3, model TERMS = field 8,
   RMS = field 9, "E" = not computed. The old code took the azimuth as a star count, so the
   int() failed and the alignment model was never shown. Label "Model terms".
   Protocol PDF kept privately (10Micron document, not for the public repo):
   in the private docs folder, 10Micron/ (pdf + pdftotext .txt). :PRclr#/:PRlist# are not in it.
   :Gmte# = time to tracking END (horizon or flip limit), not strictly the flip.
3b. (released in 4.5.0) MM3 author's point on ASCOM: never send LX200 commands to an ASCOM
   driver. Now pure ASCOM by default (send_raw_* return None, DoesRefraction for :GREF#);
   setting `ascom_10micron_commands` (off) re-enables them, only for a 10Micron driver id.
   Pure mode tried by the MM3 author on an iOptron CEM120 (22/11, works). Not yet tried on a 10Micron in pure mode (expected: no temperature/pressure/axis/
   alignment/preferences, history line "chk_prefs_pure_ascom").
4. Screenshots (redone for 4.5.0): `QT_QPA_PLATFORM=offscreen MM_CAPTURE_RUN_S=150 python -B
   docs/manuel/captures.py`, then `python docs/manuel/compiler.py`.
5. Pre-existing: `check_subprocesses.py` flags `reporting.py:218` (kit file).

**How to work:**
- Tests: `QT_QPA_PLATFORM=offscreen python -m pytest -q tests` (196 pass).
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
