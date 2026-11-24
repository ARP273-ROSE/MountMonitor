# -*- coding: utf-8 -*-
"""Three languages, and no empty label.

Dutch is there because MountMonitor is originally a Dutch program: version
3.40 is by Nicolàs de Hilster (Starmountain Survey & Consultancy BV).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "i18n_test", Path(__file__).resolve().parents[1] / "src" / "utils" / "i18n.py")
i18n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(i18n)


def test_three_languages_are_declared():
    assert set(i18n.LANGUAGES) == {"en", "fr", "nl"}


def test_no_key_is_half_translated():
    """An untranslated string is a cosmetic defect; an empty button, a failure."""
    gaps = {
        key: [lg for lg in i18n.LANGUAGES if not (entry.get(lg) or "").strip()]
        for key, entry in i18n.TX.items()
    }
    gaps = {k: v for k, v in gaps.items() if v}
    assert not gaps, f"missing translations: {gaps}"


def test_all_used_keys_exist():
    """A T() without an entry shows the raw key on screen."""
    import re
    root = Path(__file__).resolve().parents[1]
    used = set()
    for f in list((root / "src").rglob("*.py")) + [root / "main.py"]:
        if f.exists():
            used |= set(re.findall(r'\bT\("([a-z_0-9]+)"', f.read_text(encoding="utf-8")))
    assert not (used - set(i18n.TX)), f"missing keys: {sorted(used - set(i18n.TX))}"


@pytest.mark.parametrize("variable,expected_value", [
    ("fr_FR.UTF-8", "fr"),
    ("fr_BE", "fr"),
    ("nl_NL.UTF-8", "nl"),
    ("nl_BE", "nl"),
    ("en_GB", "en"),
    ("de_DE.UTF-8", "en"),     # not translated -> English, not an empty label
    ("C", "en"),
    ("", "en"),
])
def test_automatic_detection(variable, expected_value, monkeypatch):
    for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(v, raising=False)
    if variable:
        monkeypatch.setenv("LANG", variable)
    assert i18n.detect_language() == expected_value


def test_unknown_code_does_not_break_ui():
    i18n.set_language("kl")          # Greenlandic: not translated
    assert i18n.get_language() == i18n.DEFAULT_LANGUAGE
    assert i18n.T("btn_connect") == "Connect"


def test_fallback_to_english_if_translation_missing():
    i18n.TX["_essai"] = {"en": "Fallback", "fr": "", "nl": None}
    try:
        for lg in ("fr", "nl"):
            i18n.set_language(lg)
            assert i18n.T("_essai") == "Fallback"
    finally:
        del i18n.TX["_essai"]
        i18n.set_language("en")


def test_three_languages_say_different_things():
    """Guard against a translation copied from one language to another."""
    identical = []
    for key, e in i18n.TX.items():
        values = {e["en"], e["fr"], e["nl"]}
        # acronyms and proper names are legitimately identical
        if len(values) == 1 and len(e["en"]) > 12:
            identical.append(key)
    assert not identical, f"probably untranslated: {identical}"
