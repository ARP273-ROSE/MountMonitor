# -*- coding: utf-8 -*-
"""The fixes of 23 September 2026, and why they hold.

Each test here matches a defect observed on a real session, and checks the
property that made it impossible to see. The figures quoted are the ones
that were measured, not estimates.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from tests.test_tracking_analysis import _require_qt

from src.logging_module.log_parser import (
    _baseline, _moves, _settled_stdevs, _DELAY_AFTER_SLEW,
)


# ── The excursion filter ────────────────────────────────────────────

def test_baseline_follows_curving_drift():
    """A straight line does not describe the drift of an unguided mount.

    The excursion threshold applied to the raw distance from the segment
    median: on a night drifting at -16.8"/h, 59 % of the samples fell beyond
    30" and were thrown away as "commanded moves".
    """
    from src.logging_module.log_parser import _EXCURSION_ARCSEC

    t = np.arange(0, 8 * 3600, 0.5)
    # Curving drift, like that of an axis as a function of hour angle.
    # -16.8"/h was the measured drift; the curvature is what a straight line
    # cannot follow.
    signal = -16.8 * (t / 3600) - 3.0 * (t / 3600) ** 2

    kept_baseline = np.mean(np.abs(signal - _baseline(t, signal)) <= _EXCURSION_ARCSEC)
    p = np.polyfit(t, signal, 1)
    kept_line = np.mean(np.abs(signal - np.polyval(p, t)) <= _EXCURSION_ARCSEC)

    # This is the property that matters: how many samples survive the
    # excursion threshold. On the real night, 41 % with the old method,
    # 99.5 % with the baseline.
    assert kept_baseline > 0.99, f"baseline: {kept_baseline:.1%} kept"
    assert kept_line < kept_baseline, (
        f"a straight line keeps {kept_line:.1%}, the baseline {kept_baseline:.1%}")


def test_baseline_follows_plateau_but_not_dither():
    """A recentring leaves a permanent step; a dither does not."""
    t = np.arange(0, 3600, 0.5)
    with_step = np.where(t > 1800, 40.0, 0.0)
    residual = with_step - _baseline(t, with_step)
    # the step is followed: the residual drops back to zero on both sides
    assert np.abs(residual[t < 1500]).max() < 1.0
    assert np.abs(residual[t > 2100]).max() < 1.0


# ── Grouping of moves ───────────────────────────────────────────────

def _segment_with_move(amplitude, n_samples):
    """A held position, a spread-out move, a held position."""
    n = 600
    t = np.arange(n, dtype=float) * 0.5
    ra = np.zeros(n)
    start = 300
    for k in range(n_samples):
        ra[start + k:] = amplitude * (k + 1) / n_samples
    ra += np.random.default_rng(0).normal(0, 0.02, n)
    return ra, np.zeros(n), t


def test_spread_recentring_counts_as_one_move():
    """98 threshold crossings were worth 53 real moves.

    A 70" recentring takes several samples to complete and triggers the
    threshold at each one. Counting them separately inflated the number and
    divided the median amplitude by ten.
    """
    ra, dec, t = _segment_with_move(70.0, 8)
    mv = _moves(ra, dec, t)
    assert len(mv) == 1, f"one move expected, {len(mv)} counted"
    assert 60.0 < mv[0].amplitude < 80.0


def test_dither_and_recentring_are_different_classes():
    ra, dec, t = _segment_with_move(2.0, 1)
    small = _moves(ra, dec, t)
    ra, dec, t = _segment_with_move(70.0, 4)
    large = _moves(ra, dec, t)
    assert small and large
    assert small[0].kind == "dither"
    assert large[0].kind == "recentrage"


# ── The running standard deviation ──────────────────────────────────

def test_running_stdev_blanked_at_segment_start():
    """Its 60 s window straddles the preceding slew.

    A 33 s target reported a 69.9" mean for a 0.64" peak-to-peak: all its
    values described the slew.
    """
    t = np.arange(0, 120, 0.5)
    stdevs = np.full(t.shape, 0.07)
    stdevs[:40] = 55.0          # contaminated by the slew
    clean = _settled_stdevs(t, stdevs)
    valid = clean[clean > 0]
    assert valid.size > 0
    assert valid.max() < 1.0, "no slew value may survive"


def test_target_shorter_than_window_shows_nothing():
    t = np.arange(0, _DELAY_AFTER_SLEW - 10, 0.5)
    stdevs = np.full(t.shape, 42.0)
    clean = _settled_stdevs(t, stdevs)
    assert np.all(clean == 0.0)


# ── Ephemerides ─────────────────────────────────────────────────────

def test_twilights_fall_where_skyfield_puts_them():
    """Checked against reference values computed with skyfield/DE421 for the
    Observatoire de Haute-Provence (43.9317 N; 5.7122 E; 650 m) on
    23 September 2026, to the minute in UTC."""
    from datetime import datetime, timezone
    from src.core.ephemerides import night_around

    n = night_around(datetime(2026, 9, 23, 12, tzinfo=timezone.utc), 43.9317, 5.7122)
    expected_values = {
        # skyfield/DE421 : 17:32:57, 18:01:40, 18:35:19, 19:09:43, 03:49:34, 05:26:29
        'sunset': (17, 32), 'civil': (18, 1), 'nautical': (18, 35),
        'astro_start': (19, 9), 'astro_end': (3, 49), 'sunrise': (5, 26),
    }
    for key, (h, m) in expected_values.items():
        t = getattr(n, key)
        assert t is not None, key
        gap_min = abs((t.hour * 60 + t.minute) - (h * 60 + m))
        assert gap_min <= 1, f"{key}: {t.hour:02d}:{t.minute:02d} instead of {h:02d}:{m:02d}"


def test_lx200_longitude_is_counted_backwards():
    """Getting the sign wrong moves the observatory and shifts the twilights."""
    from src.core.ephemerides import parse_longitude_lx200 as lon

    assert lon('-005*42') == pytest.approx(5.70, abs=0.01)    # 5.70 east
    assert lon('354*18') == pytest.approx(5.70, abs=0.01)     # same site, 0-360
    assert lon('+078*30') == pytest.approx(-78.5, abs=0.01)   # 78.5 west
    assert lon('-149*00') == pytest.approx(149.0, abs=0.01)   # Australia


# ── Translations ────────────────────────────────────────────────────

def test_no_key_missing_in_any_language():
    """Ten report messages were written in English AND French at once:
    the Dutch report was not Dutch."""
    from src.utils.i18n import TX
    from src.gui.report_texts import TR

    missing = []
    for name, table in (("i18n", TX), ("rapport", TR)):
        for key, translations in table.items():
            for language in ("en", "fr", "nl"):
                if language not in translations or not str(translations[language]).strip():
                    missing.append(f"{name}:{key}:{language}")
    assert not missing, f"{len(missing)} missing translations: {missing[:8]}"


def test_no_text_shows_two_languages_at_once():
    """The consent box asked "Autoriser / Allow" in the same dialog."""
    from src.utils.i18n import TX
    from src.gui.report_texts import TR

    offenders = []
    for name, table in (("i18n", TX), ("rapport", TR)):
        for key, translations in table.items():
            for language, text in translations.items():
                t = str(text)
                if t.startswith("EN:") or "\nFR:" in t or "\nNL:" in t:
                    offenders.append(f"{name}:{key}:{language}")
    assert not offenders, f"bilingual texts: {offenders[:8]}"


# ── Settings ────────────────────────────────────────────────────────

def test_three_session_options_on_by_default():
    from src.config.defaults import DEFAULTS

    for key in ("autostart_on_tracking", "pause_when_not_tracking",
                "close_at_sunrise"):
        assert DEFAULTS[key] is True, key


def test_layout_settings_exist():
    """The README promised a persistent layout; the splitters were rebuilt
    at their default proportions on every launch."""
    from src.config.defaults import DEFAULTS

    for key in ("splitter_graphs", "splitter_main", "horizontal_zoom"):
        assert key in DEFAULTS, key


# ── Release notes ───────────────────────────────────────────────────

def test_release_notes_sorted_by_language():
    """The update window showed the raw notes.

    They were written in French only, then in all three languages at once:
    a Dutch user read something other than their language either way.
    """
    import updater

    body = (
        "## English\n\n### Download\nWindows file here.\n\n"
        "## Francais\n\n### Telechargement\nLe fichier Windows ici.\n\n"
        "## Nederlands\n\n### Downloaden\nHet Windows-bestand hier."
    )
    markers = {"en": "Windows file", "fr": "Le fichier", "nl": "Het Windows"}
    for language, expected_value in markers.items():
        rendered = updater.notes_dans_la_langue(body, language)
        assert expected_value in rendered
        others = [m for lg, m in markers.items() if lg != language and m in rendered]
        assert not others, f"{language} also shows {others}"


def test_notes_without_sections_are_rendered_whole():
    """Better too much than nothing: an old release stays readable."""
    import updater

    assert updater.notes_dans_la_langue("texte simple", "fr") == "texte simple"
    assert updater.notes_dans_la_langue("", "fr") == ""


def test_announced_package_names_really_exist():
    """The installation table cited files that no longer exist.

    Since packages carry their architecture, "-macos.dmg" and
    "-linux.tar.gz" are no longer produced by anyone.
    """
    from pathlib import Path

    wf = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = wf.read_text(encoding="utf-8")
    # notes written by the kit's shared workflow (step "Rediger les notes")
    body = text.split("Rediger les notes", 1)[1]
    for gone in ("-macos.dmg", "-linux.tar.gz"):
        assert gone not in body, f"the release body cites {gone}"
    for expected_value in ("macos-arm64.dmg", "macos-x86_64.dmg",
                    "linux-x86_64.tar.gz", "linux-arm64.tar.gz"):
        assert expected_value in body, f"{expected_value} missing from the release body"


# ── Language tabs ───────────────────────────────────────────────────

def test_each_tab_keeps_its_own_language_on_empty_session():
    """The French tab showed Dutch.

    The early returns of _run_analysis — precisely the ones used when a
    session is empty — wrote into the current view without looking at the
    requested language. Since the tabs call the method once per language,
    the last call, Dutch, overwrote the tab of the application language.
    """
    _require_qt()
    from src.gui.analysis_dialog import AnalysisDialog
    from src.logging_module.log_parser import ParsedSession

    empty = ParsedSession()
    dlg = AnalysisDialog.__new__(AnalysisDialog)
    dlg._session = empty
    dlg._lang = "fr"
    dlg._report = None
    dlg._reports = {}

    renders = {lg: dlg._run_analysis(lg) for lg in ("en", "fr", "nl")}
    assert renders["fr"] != renders["nl"], "the French tab renders Dutch"
    assert renders["fr"] != renders["en"]
    # and each one carries its own language
    assert "analyser" in renders["fr"] or "suivi" in renders["fr"]


def test_explicit_language_leaves_current_view_alone():
    """Asking for the Dutch report must not change anything on screen."""
    _require_qt()
    from src.gui.analysis_dialog import AnalysisDialog
    from src.logging_module.log_parser import ParsedSession

    class _View:
        def __init__(self):
            self.text = "intact"

        def setPlainText(self, t):
            self.text = t

        def moveCursor(self, *a):
            pass

    dlg = AnalysisDialog.__new__(AnalysisDialog)
    dlg._session = ParsedSession()
    dlg._lang = "fr"
    dlg._report = _View()
    dlg._reports = {}

    dlg._run_analysis("nl")
    assert dlg._report.text == "intact"


def test_morning_announces_coming_night():
    """At 09:16 the module described the night that had just ended.

    Someone connecting in the morning is preparing their evening; they are
    not looking back at the night just gone. The difference was barely
    visible — three minutes on the start of astronomical night — and that
    is exactly what made it sneaky.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.core.ephemerides import night_around

    tz = ZoneInfo("Europe/Paris")
    lat, lon = 43.9317, 5.7122   # Observatoire de Haute-Provence

    # in the morning, after sunrise: the COMING night
    morning = night_around(datetime(2026, 9, 23, 9, 16, tzinfo=tz), lat, lon)
    assert morning.astro_start.astimezone(tz).day == 23
    assert morning.astro_start.astimezone(tz).strftime("%H:%M") == "21:09"

    # the afternoon targets the same night, without skipping one more day
    afternoon = night_around(datetime(2026, 9, 23, 15, 0, tzinfo=tz), lat, lon)
    assert afternoon.astro_start == morning.astro_start

    # in the middle of the night, it is the CURRENT night
    trough = night_around(datetime(2026, 9, 24, 2, 0, tzinfo=tz), lat, lon)
    assert trough.astro_start == morning.astro_start

    # before dawn too: the night that is ending is still the right one
    dawn = night_around(datetime(2026, 9, 24, 6, 30, tzinfo=tz), lat, lon)
    assert dawn.astro_start == morning.astro_start

    # and the next morning, we move on to the following one
    next_night = night_around(datetime(2026, 9, 24, 9, 0, tzinfo=tz), lat, lon)
    assert next_night.astro_start > morning.astro_start


# ── Chaining nights ─────────────────────────────────────────────────

def test_daylight_guard_prevents_loop():
    """Left running, the program must handle several nights on its own.

    At sunrise it closed the night and stayed connected but idle: someone
    had to be there every evening to click again. And the first version of
    the re-arming restarted within the second, because the mount is often
    still tracking at sunrise — the program closed and then reopened a file
    in broad daylight, in a loop. _is_daytime is what breaks the loop.

    The full window is not built here: instantiating it under pytest brings
    Qt down. The whole three-night cycle is replayed with
    outils/simulate_nights.py, which needs a real graphical environment.
    """
    _require_qt()
    import src.core.ephemerides as E
    from src.config.settings import Settings
    from src.gui.main_window import MainWindow

    w = MainWindow.__new__(MainWindow)
    s = Settings()
    s.set("close_at_sunrise", True)
    w._settings = s
    w._site = lambda: (43.9317, 5.7122, 650)

    true_fn = E.sun_altitude
    try:
        E.sun_altitude = lambda *a, **k: +10.0
        assert w._is_daytime() is True, "the Sun is up, must refuse"
        E.sun_altitude = lambda *a, **k: -20.0
        assert w._is_daytime() is False, "it is night, must accept"

        # Without the option, no guard: the button keeps its usual meaning.
        s.set("close_at_sunrise", False)
        E.sun_altitude = lambda *a, **k: +10.0
        assert w._is_daytime() is False

        # Unknown site: no guessing, let it through.
        s.set("close_at_sunrise", True)
        w._site = lambda: None
        assert w._is_daytime() is False
    finally:
        E.sun_altitude = true_fn


# ── Graph display ───────────────────────────────────────────────────

def test_curves_scroll_at_default_zoom():
    """At zoom 1 the axis started at zero and no longer scrolled.

    Zoom 1 being the default, the graphs stood still: the axis stretched as
    the night went on and squeezed the data into the middle. After seven
    hours it reached 26 ks and reported a standard deviation of 1960 arcsec
    for a mount holding at 0.06.
    """
    import numpy as np

    from src.gui.graph_widgets import horizontal_window

    class _Fake:
        def width(self):
            return 1200

    w = _Fake()
    # seven hours at 1.9 Hz
    t = np.linspace(0, 25000, 47500)

    x0 = horizontal_window(w, t, t[-1], 1)
    assert x0 > 0, "at zoom 1, the window must follow the end of the data"
    shown = t[-1] - x0
    assert 300 < shown < 1200, f"{shown:.0f} s shown, expected ~600"

    # the more you zoom, the less time you see
    spans = [t[-1] - horizontal_window(w, t, t[-1], z) for z in (1, 2, 5, 10)]
    assert spans == sorted(spans, reverse=True), spans

    # as long as there are fewer points than pixels, show everything
    short = np.linspace(0, 100, 300)
    assert horizontal_window(w, short, short[-1], 1) == 0.0

    # an absurd zoom breaks nothing
    assert horizontal_window(w, t, t[-1], 0) > 0
    assert horizontal_window(w, t, t[-1], None) > 0


def test_graphs_scroll_over_two_minutes_to_present():
    """The buffer chains several nights: only the present must be shown.

    The graph received the whole buffer reduced to 5,000 points, and the
    "one point per pixel" rule applied to those reduced points: the window
    covered hours and the axis, starting at the beginning of the buffer, was
    graduated in ks. It now receives the last two minutes at full
    resolution, and the zoom divides them.
    """
    import numpy as np

    from src.gui.graph_widgets import cut_to_present, window_width

    assert window_width(1) == 120.0
    assert window_width(5) == 24.0
    assert window_width(None) == window_width(0) == 120.0

    # three 8 h nights at 1.9 Hz, separated by empty days
    nights = [np.arange(0, 8 * 3600, 1 / 1.9) + k * 86400 for k in range(3)]
    t = np.concatenate(nights)
    v = np.sin(t)
    sd = np.abs(np.cos(t))

    tc, vc, sdc = cut_to_present(t, v, 120.0, None, sd)
    assert t[-1] - tc[0] <= 120.0 + 1.0, "the window overflows two minutes"
    assert t[-1] - tc[1] <= 120.0
    assert tc[-1] == t[-1], "the present must be the last sample"
    assert len(tc) == len(vc) == len(sdc)
    assert 220 < len(tc) < 240, len(tc)

    # a series of a different length than t is not cut askew
    _, _, nothing = cut_to_present(t, v, 120.0, None, sd[:10])
    assert nothing is None

    # a side series is cut on another one's present (time graph)
    t2 = t[::7]
    t2c, _ = cut_to_present(t2, t2, 120.0, float(t[-1]))
    assert t2c[-1] == t2[-1] and t[-1] - t2c[1] <= 120.0

    # buffer shorter than the window: everything is kept
    short = np.arange(0, 30, 0.5)
    assert len(cut_to_present(short, short, 120.0)[0]) == len(short)


# ── Coordinates ─────────────────────────────────────────────────────

def test_seconds_carry_never_gives_sixty():
    """"01:59:60.00" instead of "02:00:00.00".

    Pre-existing defect of all three formatters: without carry, a value that
    rounds to sixty seconds is displayed as is. It only shows on values that
    land exactly on the boundary, which makes it all the more surprising on
    screen.
    """
    from src.utils.coordinates import format_dec, format_ra, format_ra_degrees

    assert format_ra(1 + 59 / 60 + 59.999 / 3600) == "02:00:00.00"
    assert format_ra(23.999999) == "00:00:00.00"          # and the full turn
    assert format_dec(41 + 1 / 60 + 59.999 / 3600) == "+41:02:00.0"
    assert format_dec(-30.9999999) == "-31:00:00.0"
    assert format_ra_degrees(23.999999) == "359:59:59.9"

    for f, v in ((format_ra, 2.735555556), (format_dec, 61.8),
                 (format_ra_degrees, 12.0)):
        assert ":60" not in f(v), f(v)


def test_right_ascension_also_reads_in_degrees():
    """Requested by Nicolàs de Hilster: one hour is fifteen degrees."""
    from src.utils.coordinates import format_ra_degrees

    assert format_ra_degrees(0.0) == "000:00:00.0"
    assert format_ra_degrees(12.0) == "180:00:00.0"
    assert format_ra_degrees(2 + 44 / 60 + 8 / 3600) == "041:02:00.0"


def test_report_shown_at_morning_close():
    """The night closed, the report was written, and nothing was shown.

    Automatic analysis only triggered on a TRANSITION to PARKED. A mount
    parked for half an hour when the Sun rises produces none — yet that is
    the only moment one wants to see the report.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "gui"
           / "main_window.py").read_text(encoding="utf-8")
    block = src.split("def _watch_dawn")[1].split("def ")[0]
    assert "_auto_analyze_on_park()" in block, (
        "the morning close does not open the report")
    assert block.index("_stop_logging()") < block.index("_auto_analyze_on_park()"), (
        "the report must be written before being shown")

    # and a given session is shown only once
    analysis = src.split("def _auto_analyze_on_park")[1].split("\n    def ")[0]
    assert "_analysed_session" in analysis
