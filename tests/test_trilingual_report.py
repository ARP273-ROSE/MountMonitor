# -*- coding: utf-8 -*-
"""The night report exists in all three languages, and in ONE at a time.

It used to be hard-coded, each sentence followed by its French translation:
twice as long to read, impossible to extend, and deaf to the chosen language.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "report_texts_test", ROOT / "src" / "gui" / "report_texts.py")


def _load_module():
    """The texts module alone, without dragging in the whole GUI package."""
    import types
    if "src.utils.i18n" not in sys.modules:
        sp = importlib.util.spec_from_file_location(
            "src.utils.i18n", ROOT / "src" / "utils" / "i18n.py")
        m = importlib.util.module_from_spec(sp)
        package = types.ModuleType("src.utils")
        package.__path__ = [str(ROOT / "src" / "utils")]
        sys.modules.setdefault("src", types.ModuleType("src"))
        sys.modules["src"].__path__ = [str(ROOT / "src")]
        sys.modules["src.utils"] = package
        sys.modules["src.utils.i18n"] = m
        sp.loader.exec_module(m)
    sp = importlib.util.spec_from_file_location(
        "src.gui.report_texts", ROOT / "src" / "gui" / "report_texts.py")
    mod = importlib.util.module_from_spec(sp)
    import types as _t
    g = _t.ModuleType("src.gui"); g.__path__ = [str(ROOT / "src" / "gui")]
    sys.modules.setdefault("src.gui", g)
    sys.modules["src.gui.report_texts"] = mod
    sp.loader.exec_module(mod)
    return mod


TEXTS = _load_module()


def test_three_languages_are_complete():
    gaps = {c: [lg for lg in ("en", "fr", "nl") if not (e.get(lg) or "").strip()]
             for c, e in TEXTS.TR.items()}
    gaps = {k: v for k, v in gaps.items() if v}
    assert not gaps, f"missing texts: {gaps}"


def test_format_fields_match():
    """A {field} present in one language and not another raises at run time."""
    for key, e in TEXTS.TR.items():
        fields = {lg: set(re.findall(r"\{(\w+)[^}]*\}", e[lg])) for lg in ("en", "fr", "nl")}
        assert fields["en"] == fields["fr"] == fields["nl"], \
            f"{key}: different fields {fields}"


def test_missing_key_does_not_crash():
    assert TEXTS.R("cle_qui_n_existe_pas") == "cle_qui_n_existe_pas"


def test_fallback_to_english():
    TEXTS.TR["_essai"] = {"en": "Fallback", "fr": "", "nl": None}
    try:
        assert TEXTS.R("_essai", "fr") == "Fallback"
        assert TEXTS.R("_essai", "nl") == "Fallback"
    finally:
        del TEXTS.TR["_essai"]


def test_report_no_longer_hardcoded_bilingual():
    """Guard: no line of the generator may replay "EN / FR"."""
    code = (ROOT / "src" / "gui" / "analysis_dialog.py").read_text(encoding="utf-8")
    offending = [l.strip() for l in code.split("\n")
                if ("lines.append" in l or "recommendations.append" in l)
                and " / " in l and "R(" not in l and "_(" not in l]
    assert not offending, f"lines still bilingual: {offending[:3]}"


@pytest.mark.parametrize("language,expected_value", [
    ("en", "SESSION OVERVIEW"),
    ("fr", "APERÇU DE LA SESSION"),
    ("nl", "OVERZICHT VAN DE SESSIE"),
])
def test_each_language_has_its_title(language, expected_value):
    assert TEXTS.R("t_apercu", language) == expected_value


def test_the_three_say_different_things():
    identical = [c for c, e in TEXTS.TR.items()
                  if len({e["en"], e["fr"], e["nl"]}) == 1 and len(e["en"]) > 14]
    assert not identical, f"probably untranslated: {identical}"
