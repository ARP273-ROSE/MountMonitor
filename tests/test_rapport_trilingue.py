# -*- coding: utf-8 -*-
"""Le rapport de nuit existe dans les trois langues, et dans UNE a la fois.

Il etait ecrit en dur, chaque phrase suivie de sa traduction francaise : deux
fois plus long a lire, impossible a etendre, et sourd a la langue choisie.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "rapport_textes_test", RACINE / "src" / "gui" / "rapport_textes.py")


def _charger():
    """Le module de textes seul, sans entrainer tout le paquet GUI."""
    import types
    if "src.utils.i18n" not in sys.modules:
        sp = importlib.util.spec_from_file_location(
            "src.utils.i18n", RACINE / "src" / "utils" / "i18n.py")
        m = importlib.util.module_from_spec(sp)
        paquet = types.ModuleType("src.utils")
        paquet.__path__ = [str(RACINE / "src" / "utils")]
        sys.modules.setdefault("src", types.ModuleType("src"))
        sys.modules["src"].__path__ = [str(RACINE / "src")]
        sys.modules["src.utils"] = paquet
        sys.modules["src.utils.i18n"] = m
        sp.loader.exec_module(m)
    sp = importlib.util.spec_from_file_location(
        "src.gui.rapport_textes", RACINE / "src" / "gui" / "rapport_textes.py")
    mod = importlib.util.module_from_spec(sp)
    import types as _t
    g = _t.ModuleType("src.gui"); g.__path__ = [str(RACINE / "src" / "gui")]
    sys.modules.setdefault("src.gui", g)
    sys.modules["src.gui.rapport_textes"] = mod
    sp.loader.exec_module(mod)
    return mod


TEXTES = _charger()


def test_les_trois_langues_sont_completes():
    trous = {c: [lg for lg in ("en", "fr", "nl") if not (e.get(lg) or "").strip()]
             for c, e in TEXTES.TR.items()}
    trous = {k: v for k, v in trous.items() if v}
    assert not trous, f"textes manquants : {trous}"


def test_les_champs_de_format_concordent():
    """Un {champ} present dans une langue et pas dans une autre leve a l'execution."""
    for cle, e in TEXTES.TR.items():
        champs = {lg: set(re.findall(r"\{(\w+)[^}]*\}", e[lg])) for lg in ("en", "fr", "nl")}
        assert champs["en"] == champs["fr"] == champs["nl"], \
            f"{cle} : champs differents {champs}"


def test_une_cle_absente_ne_plante_pas():
    assert TEXTES.R("cle_qui_n_existe_pas") == "cle_qui_n_existe_pas"


def test_repli_sur_l_anglais():
    TEXTES.TR["_essai"] = {"en": "Fallback", "fr": "", "nl": None}
    try:
        assert TEXTES.R("_essai", "fr") == "Fallback"
        assert TEXTES.R("_essai", "nl") == "Fallback"
    finally:
        del TEXTES.TR["_essai"]


def test_le_rapport_n_est_plus_ecrit_en_dur_bilingue():
    """Garde-fou : aucune ligne du generateur ne doit rejouer « EN / FR »."""
    code = (RACINE / "src" / "gui" / "analysis_dialog.py").read_text(encoding="utf-8")
    fautives = [l.strip() for l in code.split("\n")
                if ("lines.append" in l or "recommendations.append" in l)
                and " / " in l and "R(" not in l and "_(" not in l]
    assert not fautives, f"lignes encore bilingues : {fautives[:3]}"


@pytest.mark.parametrize("langue,attendu", [
    ("en", "SESSION OVERVIEW"),
    ("fr", "APERCU DE LA SESSION"),
    ("nl", "OVERZICHT VAN DE SESSIE"),
])
def test_chaque_langue_a_son_titre(langue, attendu):
    assert TEXTES.R("t_apercu", langue) == attendu


def test_les_trois_disent_des_choses_differentes():
    identiques = [c for c, e in TEXTES.TR.items()
                  if len({e["en"], e["fr"], e["nl"]}) == 1 and len(e["en"]) > 14]
    assert not identiques, f"probablement non traduites : {identiques}"
