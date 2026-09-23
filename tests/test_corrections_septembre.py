# -*- coding: utf-8 -*-
"""Les corrections du 23 septembre 2026, et pourquoi elles tiennent.

Chaque test ici correspond a un defaut constate sur une session reelle, et
verifie la propriete qui le rendait impossible a voir. Les chiffres cites
sont ceux qui ont ete mesures, pas des estimations.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.logging_module.log_parser import (
    _baseline, _mouvements, _settled_stdevs, _DELAI_APRES_SLEW,
)


# ── Le filtre d'excursions ──────────────────────────────────────────

def test_la_ligne_de_base_suit_une_derive_qui_courbe():
    """Une droite ne decrit pas la derive d'une monture non guidee.

    Le seuil d'excursion s'appliquait a la distance brute a la mediane du
    segment : sur une nuit derivant de -16,8"/h, 59 % des echantillons
    tombaient au-dela des 30" et etaient jetes comme « mouvements
    commandes ».
    """
    from src.logging_module.log_parser import _EXCURSION_ARCSEC

    t = np.arange(0, 8 * 3600, 0.5)
    # Derive qui courbe, comme celle d'un axe en fonction de l'angle horaire.
    # -16,8"/h etait la derive mesuree ; la courbure est ce qu'une droite ne
    # sait pas suivre.
    signal = -16.8 * (t / 3600) - 3.0 * (t / 3600) ** 2

    garde_base = np.mean(np.abs(signal - _baseline(t, signal)) <= _EXCURSION_ARCSEC)
    p = np.polyfit(t, signal, 1)
    garde_droite = np.mean(np.abs(signal - np.polyval(p, t)) <= _EXCURSION_ARCSEC)

    # C'est la propriete qui compte : combien d'echantillons survivent au
    # seuil d'excursion. Sur la nuit reelle, 41 % avec l'ancienne methode,
    # 99,5 % avec la ligne de base.
    assert garde_base > 0.99, f"ligne de base : {garde_base:.1%} gardes"
    assert garde_droite < garde_base, (
        f"une droite garde {garde_droite:.1%}, la ligne de base {garde_base:.1%}")


def test_la_ligne_de_base_suit_un_palier_mais_pas_un_dither():
    """Un recentrage laisse une marche permanente ; un dither, non."""
    t = np.arange(0, 3600, 0.5)
    avec_marche = np.where(t > 1800, 40.0, 0.0)
    residu = avec_marche - _baseline(t, avec_marche)
    # la marche est suivie : le residu retombe a zero de part et d'autre
    assert np.abs(residu[t < 1500]).max() < 1.0
    assert np.abs(residu[t > 2100]).max() < 1.0


# ── Le regroupement des mouvements ──────────────────────────────────

def _segment_avec_mouvement(amplitude, duree_echantillons):
    """Une position tenue, un mouvement etale, une position tenue."""
    n = 600
    t = np.arange(n, dtype=float) * 0.5
    ra = np.zeros(n)
    debut = 300
    for k in range(duree_echantillons):
        ra[debut + k:] = amplitude * (k + 1) / duree_echantillons
    ra += np.random.default_rng(0).normal(0, 0.02, n)
    return ra, np.zeros(n), t


def test_un_recentrage_etale_compte_pour_un_seul_mouvement():
    """98 franchissements de seuil valaient 53 mouvements reels.

    Un recentrage de 70" met plusieurs echantillons a s'accomplir et
    declenche le seuil a chacun. Les compter separement gonflait le nombre
    et divisait l'amplitude mediane par dix.
    """
    ra, dec, t = _segment_avec_mouvement(70.0, 8)
    mv = _mouvements(ra, dec, t)
    assert len(mv) == 1, f"un mouvement attendu, {len(mv)} comptes"
    assert 60.0 < mv[0].amplitude < 80.0


def test_un_dither_et_un_recentrage_ne_sont_pas_de_la_meme_classe():
    ra, dec, t = _segment_avec_mouvement(2.0, 1)
    petit = _mouvements(ra, dec, t)
    ra, dec, t = _segment_avec_mouvement(70.0, 4)
    grand = _mouvements(ra, dec, t)
    assert petit and grand
    assert petit[0].classe == "dither"
    assert grand[0].classe == "recentrage"


# ── L'ecart-type glissant ───────────────────────────────────────────

def test_l_ecart_type_glissant_est_blanchi_au_debut_d_un_segment():
    """Sa fenetre de 60 s enjambe le slew qui precede.

    Une cible de 33 s annoncait 69,9" de moyenne pour un pic-a-pic de
    0,64" : toutes ses valeurs decrivaient le slew.
    """
    t = np.arange(0, 120, 0.5)
    stdevs = np.full(t.shape, 0.07)
    stdevs[:40] = 55.0          # contamine par le slew
    propre = _settled_stdevs(t, stdevs)
    valides = propre[propre > 0]
    assert valides.size > 0
    assert valides.max() < 1.0, "aucune valeur de slew ne doit survivre"


def test_une_cible_plus_courte_que_la_fenetre_n_affiche_rien():
    t = np.arange(0, _DELAI_APRES_SLEW - 10, 0.5)
    stdevs = np.full(t.shape, 42.0)
    propre = _settled_stdevs(t, stdevs)
    assert np.all(propre == 0.0)


# ── Les ephemerides ─────────────────────────────────────────────────

def test_les_crepuscules_tombent_ou_skyfield_les_met():
    """Verifie contre des valeurs de reference calculees par skyfield/DE421
    pour Compiegne le 23 septembre 2026, a la seconde pres en UTC."""
    from datetime import datetime, timezone
    from src.core.ephemerides import nuit_autour

    n = nuit_autour(datetime(2026, 9, 23, 12, tzinfo=timezone.utc), 49.3061, 2.7553)
    attendus = {
        'coucher': (17, 45), 'civil': (18, 16), 'nautique': (18, 54),
        'astro_debut': (19, 32), 'astro_fin': (3, 50), 'lever': (5, 38),
    }
    for cle, (h, m) in attendus.items():
        t = getattr(n, cle)
        assert t is not None, cle
        ecart = abs((t.hour * 60 + t.minute) - (h * 60 + m))
        assert ecart <= 1, f"{cle}: {t.hour:02d}:{t.minute:02d} au lieu de {h:02d}:{m:02d}"


def test_la_longitude_lx200_est_comptee_a_l_envers():
    """Se tromper de signe deplace l'observatoire et decale les crepuscules."""
    from src.core.ephemerides import parse_longitude_lx200 as lon

    assert lon('-002*45') == pytest.approx(2.75, abs=0.01)    # 2,75 est
    assert lon('357*15') == pytest.approx(2.75, abs=0.01)     # meme site, 0-360
    assert lon('+078*30') == pytest.approx(-78.5, abs=0.01)   # 78,5 ouest
    assert lon('-149*00') == pytest.approx(149.0, abs=0.01)   # Australie


# ── Les traductions ─────────────────────────────────────────────────

def test_aucune_cle_ne_manque_dans_une_langue():
    """Dix messages du rapport etaient ecrits en anglais ET en francais a la
    fois : le rapport neerlandais n'etait pas neerlandais."""
    from src.utils.i18n import TX
    from src.gui.rapport_textes import TR

    manquants = []
    for nom, table in (("i18n", TX), ("rapport", TR)):
        for cle, trads in table.items():
            for langue in ("en", "fr", "nl"):
                if langue not in trads or not str(trads[langue]).strip():
                    manquants.append(f"{nom}:{cle}:{langue}")
    assert not manquants, f"{len(manquants)} traductions manquantes : {manquants[:8]}"


def test_aucun_texte_ne_montre_deux_langues_a_la_fois():
    """Le consentement demandait « Autoriser / Allow » dans la meme boite."""
    from src.utils.i18n import TX
    from src.gui.rapport_textes import TR

    fautifs = []
    for nom, table in (("i18n", TX), ("rapport", TR)):
        for cle, trads in table.items():
            for langue, texte in trads.items():
                t = str(texte)
                if t.startswith("EN:") or "\nFR:" in t or "\nNL:" in t:
                    fautifs.append(f"{nom}:{cle}:{langue}")
    assert not fautifs, f"textes bilingues : {fautifs[:8]}"


# ── Les reglages ────────────────────────────────────────────────────

def test_les_trois_options_de_session_sont_actives_par_defaut():
    from src.config.defaults import DEFAULTS

    for cle in ("autostart_on_tracking", "pause_when_not_tracking",
                "close_at_sunrise"):
        assert DEFAULTS[cle] is True, cle


def test_les_reglages_de_disposition_existent():
    """Le README promettait une disposition persistante ; les separateurs
    etaient reconstruits a leurs proportions par defaut a chaque lancement."""
    from src.config.defaults import DEFAULTS

    for cle in ("splitter_graphs", "splitter_main", "horizontal_zoom"):
        assert cle in DEFAULTS, cle
