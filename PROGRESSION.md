# MountMonitor 4: progress and resume note

## Resume note (2026-11-22)

**State:** master = tag **v4.4.11**, published through the release
workflow (signed updates, release_unique keeps only the latest Release).
Code, comments and commits are in English; the i18n keys and the user
texts are trilingual (EN/FR/NL) in `src/utils/i18n.py`.

**Tested on real hardware (GM1000HPS, firmware 3.4, 2026-11-22), read-only:**
- LX200 TCP/IP: product, firmware, :GT#, :GREF#/:Gdat# (one character, no
  '#'), :WSG#, :gtgpps#, :PRclr#+:PRlist# (7 chunks), 20 polls: all OK,
  70–140 ms per command.
- ASCOM through the 10Micron driver 1.7.2, shared with NINA over RS-232:
  4.4.6–4.4.8 validated with the app's own classes and with the GUI running.
  The driver needs raw=True, CommandBool for one-character replies, rejects
  :PRclr#/:PRlist# unless "unchecked raw commands" is ticked, and caches
  RA/DEC (~2 s refresh: repeats skipped since 4.4.7).
- Air gauge (4.4.9/4.4.10) and "no tolerance alarm while parked" (4.4.11)
  are covered by unit tests only, not yet seen on the real GUI.

**Not verified:**
- What the :GTMP1# sensor measures (labelled "mount electronics"; asked
  the MM3 author).
- A full night of real tracking through ASCOM since 4.4.7: check the
  effective rate (~0.5 Hz), the curves, the night report and the 6 s
  preference read every 5 min.
- The virtual-desktop alert path on Windows was confirmed by the MM3
  author in 4.4.4; nothing re-tested since.

**Next steps:**
1. After a real night in ASCOM mode: open the night report, check the
   spectrum (gaps from the 6 s check must stay under the 5x-step gap
   threshold) and the air gauge.
2. Answer of the MM3 author about :GTMP1# → adjust the label `env_inside`
   in `src/utils/i18n.py` and the manuals (`docs/manuel/corps_*.tex`).
3. Pre-existing: `check_subprocesses.py` flags `reporting.py:218`
   (sysctl without CREATE_NO_WINDOW, macOS only), a kit file.

**How to work:**
- Tests: `QT_QPA_PLATFORM=offscreen python -m pytest -q tests` (172 pass).
- Code must compile on Python 3.10 (the MM3 author runs from source).
- Manuals: `cd docs/manuel && python compiler.py` (pdflatex), commit the
  three PDFs with the .tex.
- Release: bump `VERSION`, entry in `CHANGELOG.md`, commit, push master,
  annotated tag `vX.Y.Z`, push the tag; the workflow builds, signs and
  publishes.
- The privacy test (`tests/test_confidentialite.py`) rejects real site
  coordinates: use made-up ones in tests.

**Pitfalls met:**
- On a quantised axis the median step is 0: jump detection must use the
  median of the NON-zero steps (empty DEC spectrum, 4.4.5).
- The style sheet overrode the palette for disabled widgets: disabled
  rules must be in `STYLESHEET` (4.4.5).
- Follow object switches the tracking speed to "Custom" (4.4.5).
- Never use LX200 serial on a port an ASCOM driver already holds; choose
  ASCOM with the same driver.
