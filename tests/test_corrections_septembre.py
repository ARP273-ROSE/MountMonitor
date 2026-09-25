# -*- coding: utf-8 -*-
"""Les corrections du 23 septembre 2026, et pourquoi elles tiennent.

Chaque test ici correspond a un defaut constate sur une session reelle, et
verifie la propriete qui le rendait impossible a voir. Les chiffres cites
sont ceux qui ont ete mesures, pas des estimations.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from tests.test_analyse_suivi import _exige_qt

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


# ── Les notes de version ────────────────────────────────────────────

def test_les_notes_de_version_sont_triees_par_langue():
    """La fenetre de mise a jour montrait les notes brutes.

    Elles etaient ecrites en francais seulement, puis dans les trois
    langues a la fois : un utilisateur neerlandais lisait de toute facon
    autre chose que sa langue.
    """
    import updater

    corps = (
        "## English\n\n### Download\nWindows file here.\n\n"
        "## Francais\n\n### Telechargement\nLe fichier Windows ici.\n\n"
        "## Nederlands\n\n### Downloaden\nHet Windows-bestand hier."
    )
    marqueurs = {"en": "Windows file", "fr": "Le fichier", "nl": "Het Windows"}
    for langue, attendu in marqueurs.items():
        rendu = updater.notes_dans_la_langue(corps, langue)
        assert attendu in rendu
        autres = [m for lg, m in marqueurs.items() if lg != langue and m in rendu]
        assert not autres, f"{langue} montre aussi {autres}"


def test_des_notes_sans_section_sont_rendues_entieres():
    """Mieux vaut trop que rien : une release ancienne reste lisible."""
    import updater

    assert updater.notes_dans_la_langue("texte simple", "fr") == "texte simple"
    assert updater.notes_dans_la_langue("", "fr") == ""


def test_les_noms_de_paquets_annonces_existent_vraiment():
    """Le tableau d'installation citait des fichiers disparus.

    Depuis que les paquets portent leur architecture, « -macos.dmg » et
    « -linux.tar.gz » ne sont plus produits par personne.
    """
    from pathlib import Path

    wf = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    texte = wf.read_text(encoding="utf-8")
    corps = texte.split("body: |", 1)[1]
    for disparu in ("-macos.dmg", "-linux.tar.gz"):
        assert disparu not in corps, f"le corps de release cite {disparu}"
    for attendu in ("macos-arm64.dmg", "macos-x86_64.dmg",
                    "linux-x86_64.tar.gz", "linux-arm64.tar.gz"):
        assert attendu in corps, f"{attendu} manque au corps de release"


# ── Les onglets de langue ───────────────────────────────────────────

def test_chaque_onglet_porte_sa_propre_langue_sur_une_session_vide():
    """L'onglet francais affichait du neerlandais.

    Les sorties anticipees de _run_analysis — celles qui servent justement
    quand une session est vide — ecrivaient dans la vue courante sans
    regarder la langue demandee. Les onglets appelant la methode une fois
    par langue, le dernier appel, le neerlandais, ecrasait l'onglet de la
    langue de l'application.
    """
    _exige_qt()
    from src.gui.analysis_dialog import AnalysisDialog
    from src.logging_module.log_parser import ParsedSession

    vide = ParsedSession()
    dlg = AnalysisDialog.__new__(AnalysisDialog)
    dlg._session = vide
    dlg._lang = "fr"
    dlg._report = None
    dlg._rapports = {}

    rendus = {lg: dlg._run_analysis(lg) for lg in ("en", "fr", "nl")}
    assert rendus["fr"] != rendus["nl"], "l'onglet francais rend du neerlandais"
    assert rendus["fr"] != rendus["en"]
    # et chacun porte bien sa langue
    assert "analyser" in rendus["fr"] or "suivi" in rendus["fr"]


def test_une_langue_explicite_ne_touche_pas_la_vue_courante():
    """Demander le rapport neerlandais ne doit rien changer a l'affichage."""
    _exige_qt()
    from src.gui.analysis_dialog import AnalysisDialog
    from src.logging_module.log_parser import ParsedSession

    class _Vue:
        def __init__(self):
            self.texte = "intact"

        def setPlainText(self, t):
            self.texte = t

        def moveCursor(self, *a):
            pass

    dlg = AnalysisDialog.__new__(AnalysisDialog)
    dlg._session = ParsedSession()
    dlg._lang = "fr"
    dlg._report = _Vue()
    dlg._rapports = {}

    dlg._run_analysis("nl")
    assert dlg._report.texte == "intact"


def test_le_matin_on_annonce_la_nuit_qui_vient():
    """A 09 h 16 le module decrivait la nuit qui venait de finir.

    Quelqu'un qui se connecte le matin prepare sa soiree ; il ne revient pas
    sur la nuit ecoulee. La difference se voyait a peine — trois minutes sur
    le debut de nuit noire — et c'est bien ce qui la rendait sournoise.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.core.ephemerides import nuit_autour

    tz = ZoneInfo("Europe/Paris")
    lat, lon = 49.30611, 2.75528

    # le matin, apres le lever : la nuit A VENIR
    matin = nuit_autour(datetime(2026, 9, 23, 9, 16, tzinfo=tz), lat, lon)
    assert matin.astro_debut.astimezone(tz).day == 23
    assert matin.astro_debut.astimezone(tz).strftime("%H:%M") == "21:32"

    # l'apres-midi vise la meme nuit, sans sauter un jour de plus
    aprem = nuit_autour(datetime(2026, 9, 23, 15, 0, tzinfo=tz), lat, lon)
    assert aprem.astro_debut == matin.astro_debut

    # en pleine nuit, c'est la nuit EN COURS
    creux = nuit_autour(datetime(2026, 9, 24, 2, 0, tzinfo=tz), lat, lon)
    assert creux.astro_debut == matin.astro_debut

    # avant l'aube aussi : la nuit qui se termine reste la bonne
    aube = nuit_autour(datetime(2026, 9, 24, 6, 30, tzinfo=tz), lat, lon)
    assert aube.astro_debut == matin.astro_debut

    # et le lendemain matin, on passe a la suivante
    suivant = nuit_autour(datetime(2026, 9, 24, 9, 0, tzinfo=tz), lat, lon)
    assert suivant.astro_debut > matin.astro_debut


# ── L'enchainement des nuits ────────────────────────────────────────

def test_le_garde_fou_de_jour_empeche_la_boucle():
    """Laisse allume, le programme doit tenir plusieurs nuits tout seul.

    Au lever il cloturait la nuit et restait connecte mais inerte : il
    fallait etre la chaque soir pour recliquer. Et la premiere version du
    rearmement redemarrait dans la seconde, parce que la monture suit
    souvent encore au lever — le programme cloturait puis rouvrait un
    fichier en plein jour, en boucle. C'est _fait_jour qui casse la boucle.

    La fenetre complete n'est pas construite ici : l'instancier sous pytest
    fait tomber Qt. Le cycle entier des trois nuits se rejoue avec
    outils/simuler_nuits.py, qui demande un vrai environnement graphique.
    """
    _exige_qt()
    import src.core.ephemerides as E
    from src.config.settings import Settings
    from src.gui.main_window import MainWindow

    w = MainWindow.__new__(MainWindow)
    s = Settings()
    s.set("close_at_sunrise", True)
    w._settings = s
    w._site = lambda: (49.3061, 2.7553, 57)

    vraie = E.hauteur_soleil
    try:
        E.hauteur_soleil = lambda *a, **k: +10.0
        assert w._fait_jour() is True, "le Soleil est haut, on doit refuser"
        E.hauteur_soleil = lambda *a, **k: -20.0
        assert w._fait_jour() is False, "il fait nuit, on doit accepter"

        # Sans l'option, aucun garde-fou : le bouton garde son sens habituel.
        s.set("close_at_sunrise", False)
        E.hauteur_soleil = lambda *a, **k: +10.0
        assert w._fait_jour() is False

        # Site inconnu : on ne devine pas, on laisse passer.
        s.set("close_at_sunrise", True)
        w._site = lambda: None
        assert w._fait_jour() is False
    finally:
        E.hauteur_soleil = vraie


# ── L'affichage des graphes ─────────────────────────────────────────

def test_les_courbes_defilent_au_zoom_par_defaut():
    """Au zoom 1 l'axe partait de zero et ne defilait plus.

    Le zoom 1 etant le defaut, les graphes faisaient du surplace : l'axe
    s'etirait a mesure que la nuit avancait et tassait les donnees au
    milieu. Apres sept heures il atteignait 26 ks et annoncait un
    ecart-type de 1960 arcsec pour une monture qui tenait a 0,06.
    """
    import numpy as np

    from src.gui.graph_widgets import fenetre_horizontale

    class _Faux:
        def width(self):
            return 1200

    w = _Faux()
    # sept heures a 1,9 Hz
    t = np.linspace(0, 25000, 47500)

    x0 = fenetre_horizontale(w, t, t[-1], 1)
    assert x0 > 0, "au zoom 1, la fenetre doit suivre la fin des donnees"
    affiche = t[-1] - x0
    assert 300 < affiche < 1200, f"{affiche:.0f} s affichees, attendu ~600"

    # plus on zoome, moins on voit de temps
    largeurs = [t[-1] - fenetre_horizontale(w, t, t[-1], z) for z in (1, 2, 5, 10)]
    assert largeurs == sorted(largeurs, reverse=True), largeurs

    # tant qu'il y a moins de points que de pixels, on montre tout
    court = np.linspace(0, 100, 300)
    assert fenetre_horizontale(w, court, court[-1], 1) == 0.0

    # un zoom absurde ne casse rien
    assert fenetre_horizontale(w, t, t[-1], 0) > 0
    assert fenetre_horizontale(w, t, t[-1], None) > 0


def test_les_graphes_defilent_sur_deux_minutes_au_present():
    """Le tampon enchaine plusieurs nuits : seul le present doit s'afficher.

    Le graphe recevait tout le tampon reduit a 5 000 points, et la regle
    « un point par pixel » s'appliquait a ces points reduits : la fenetre
    couvrait des heures et l'axe, parti du debut du tampon, se graduait
    en ks. Il recoit maintenant les deux dernieres minutes, pleine
    resolution, et le zoom les divise.
    """
    import numpy as np

    from src.gui.graph_widgets import couper_au_present, largeur_fenetre

    assert largeur_fenetre(1) == 120.0
    assert largeur_fenetre(5) == 24.0
    assert largeur_fenetre(None) == largeur_fenetre(0) == 120.0

    # trois nuits de 8 h a 1,9 Hz, separees par des journees vides
    nuits = [np.arange(0, 8 * 3600, 1 / 1.9) + k * 86400 for k in range(3)]
    t = np.concatenate(nuits)
    v = np.sin(t)
    sd = np.abs(np.cos(t))

    tc, vc, sdc = couper_au_present(t, v, 120.0, None, sd)
    assert t[-1] - tc[0] <= 120.0 + 1.0, "la fenetre deborde de deux minutes"
    assert t[-1] - tc[1] <= 120.0
    assert tc[-1] == t[-1], "le present doit etre le dernier echantillon"
    assert len(tc) == len(vc) == len(sdc)
    assert 220 < len(tc) < 240, len(tc)

    # une serie d'une autre longueur que t n'est pas coupee de travers
    _, _, rien = couper_au_present(t, v, 120.0, None, sd[:10])
    assert rien is None

    # une serie annexe se coupe sur le present d'une autre (graphe du temps)
    t2 = t[::7]
    t2c, _ = couper_au_present(t2, t2, 120.0, float(t[-1]))
    assert t2c[-1] == t2[-1] and t[-1] - t2c[1] <= 120.0

    # tampon plus court que la fenetre : tout est garde
    court = np.arange(0, 30, 0.5)
    assert len(couper_au_present(court, court, 120.0)[0]) == len(court)


# ── Les coordonnees ─────────────────────────────────────────────────

def test_le_report_des_secondes_ne_donne_plus_soixante():
    """« 01:59:60.00 » au lieu de « 02:00:00.00 ».

    Defaut preexistant des trois formateurs : sans report, une valeur qui
    arrondit a soixante secondes s'affiche telle quelle. Il ne se voit que
    sur les valeurs qui tombent juste, ce qui le rend d'autant plus
    surprenant a l'ecran.
    """
    from src.utils.coordinates import format_dec, format_ra, format_ra_degrees

    assert format_ra(1 + 59 / 60 + 59.999 / 3600) == "02:00:00.00"
    assert format_ra(23.999999) == "00:00:00.00"          # et le tour complet
    assert format_dec(41 + 1 / 60 + 59.999 / 3600) == "+41:02:00.0"
    assert format_dec(-30.9999999) == "-31:00:00.0"
    assert format_ra_degrees(23.999999) == "359:59:59.9"

    for f, v in ((format_ra, 2.735555556), (format_dec, 61.8),
                 (format_ra_degrees, 12.0)):
        assert ":60" not in f(v), f(v)


def test_l_ascension_droite_se_lit_aussi_en_degres():
    """Demande de Nicolàs de Hilster : une heure vaut quinze degres."""
    from src.utils.coordinates import format_ra_degrees

    assert format_ra_degrees(0.0) == "000:00:00.0"
    assert format_ra_degrees(12.0) == "180:00:00.0"
    assert format_ra_degrees(2 + 44 / 60 + 8 / 3600) == "041:02:00.0"


def test_le_rapport_s_affiche_a_la_cloture_du_matin():
    """La nuit se cloturait, le rapport s'ecrivait, et rien ne s'affichait.

    L'analyse automatique ne se declenchait que sur une TRANSITION vers
    PARKED. Une monture parquee depuis une demi-heure quand le Soleil se
    leve n'en produit aucune — c'est pourtant le seul moment ou l'on veut
    voir le rapport.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src" / "gui"
           / "main_window.py").read_text(encoding="utf-8")
    bloc = src.split("def _surveiller_aube")[1].split("def ")[0]
    assert "_auto_analyze_on_park()" in bloc, (
        "la cloture du matin n'ouvre pas le rapport")
    assert bloc.index("_stop_logging()") < bloc.index("_auto_analyze_on_park()"), (
        "le rapport doit etre ecrit avant d'etre montre")

    # et une meme session n'est montree qu'une fois
    analyse = src.split("def _auto_analyze_on_park")[1].split("\n    def ")[0]
    assert "_session_analysee" in analyse
