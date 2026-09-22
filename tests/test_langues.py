# -*- coding: utf-8 -*-
"""Trois langues, et aucune etiquette vide.

Le neerlandais est la parce que MountMonitor est un programme neerlandais a
l'origine : la version 3.37 est de Nicolàs de Hilster (Starmountain Survey &
Consultancy BV).
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


def test_les_trois_langues_sont_declarees():
    assert set(i18n.LANGUES) == {"en", "fr", "nl"}


def test_aucune_cle_n_est_traduite_a_moitie():
    """Une chaine non traduite est un defaut cosmetique ; un bouton vide, une panne."""
    trous = {
        cle: [lg for lg in i18n.LANGUES if not (entree.get(lg) or "").strip()]
        for cle, entree in i18n.TX.items()
    }
    trous = {k: v for k, v in trous.items() if v}
    assert not trous, f"traductions manquantes : {trous}"


def test_toutes_les_cles_utilisees_existent():
    """Un T() sans entree affiche la cle brute a l'ecran."""
    import re
    racine = Path(__file__).resolve().parents[1]
    utilisees = set()
    for f in list((racine / "src").rglob("*.py")) + [racine / "main.py"]:
        if f.exists():
            utilisees |= set(re.findall(r'\bT\("([a-z_0-9]+)"', f.read_text(encoding="utf-8")))
    assert not (utilisees - set(i18n.TX)), f"cles absentes : {sorted(utilisees - set(i18n.TX))}"


@pytest.mark.parametrize("variable,attendu", [
    ("fr_FR.UTF-8", "fr"),
    ("fr_BE", "fr"),
    ("nl_NL.UTF-8", "nl"),
    ("nl_BE", "nl"),
    ("en_GB", "en"),
    ("de_DE.UTF-8", "en"),     # non traduit -> anglais, pas une etiquette vide
    ("C", "en"),
    ("", "en"),
])
def test_detection_automatique(variable, attendu, monkeypatch):
    for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(v, raising=False)
    if variable:
        monkeypatch.setenv("LANG", variable)
    assert i18n.detect_language() == attendu


def test_un_code_inconnu_ne_casse_pas_l_interface():
    i18n.set_language("kl")          # groenlandais : non traduit
    assert i18n.get_language() == i18n.LANGUE_DEFAUT
    assert i18n.T("btn_connect") == "Connect"


def test_repli_sur_l_anglais_si_une_traduction_manque():
    i18n.TX["_essai"] = {"en": "Fallback", "fr": "", "nl": None}
    try:
        for lg in ("fr", "nl"):
            i18n.set_language(lg)
            assert i18n.T("_essai") == "Fallback"
    finally:
        del i18n.TX["_essai"]
        i18n.set_language("en")


def test_les_trois_langues_disent_des_choses_differentes():
    """Garde-fou contre une traduction recopiee d'une langue a l'autre."""
    identiques = []
    for cle, e in i18n.TX.items():
        valeurs = {e["en"], e["fr"], e["nl"]}
        # les sigles et les noms propres sont legitimement identiques
        if len(valeurs) == 1 and len(e["en"]) > 12:
            identiques.append(cle)
    assert not identiques, f"probablement non traduites : {identiques}"
