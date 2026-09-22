# -*- coding: utf-8 -*-
"""Les textes du rapport de nuit, en trois langues.

Le rapport etait ecrit en dur, chaque phrase suivie de sa traduction
francaise. Cela le rendait deux fois plus long a lire, impossible a etendre a
une troisieme langue, et sourd a la langue choisie dans les preferences.

Ici, chaque texte porte une cle et existe en anglais, en francais et en
neerlandais. `R(cle)` rend celui de la langue demandee, et retombe sur
l'anglais si une traduction manque — jamais sur une ligne vide.

Les cles sont groupees dans l'ordre ou elles apparaissent dans le rapport.
"""

from ..utils.i18n import LANGUE_DEFAUT

TR = {

    # ── titres de section ──────────────────────────────────────────────
    "t_apercu": {
        "en": "SESSION OVERVIEW", "fr": "APERCU DE LA SESSION",
        "nl": "OVERZICHT VAN DE SESSIE"},
    "t_qualite": {
        "en": "OVERALL QUALITY", "fr": "QUALITE GLOBALE",
        "nl": "ALGEMENE KWALITEIT"},
    "t_cible": {"en": "TARGET", "fr": "CIBLE", "nl": "DOEL"},
    "t_ad": {
        "en": "RIGHT ASCENSION (RA)", "fr": "ASCENSION DROITE (AD)",
        "nl": "RECHTE KLIMMING (RK)"},
    "t_dec": {
        "en": "DECLINATION (DEC)", "fr": "DECLINAISON (DEC)",
        "nl": "DECLINATIE (DEC)"},
    "t_temps": {
        "en": "TIME SYNCHRONIZATION", "fr": "SYNCHRONISATION TEMPORELLE",
        "nl": "TIJDSYNCHRONISATIE"},
    "t_axial": {
        "en": "AXIAL DATA", "fr": "DONNEES AXIALES", "nl": "AXIALE GEGEVENS"},
    "t_suivi": {
        "en": "TRACKING STATUS", "fr": "STATUT DE SUIVI", "nl": "VOLGSTATUS"},
    "t_tolerance": {
        "en": "TOLERANCE ANALYSIS", "fr": "ANALYSE DE TOLERANCE",
        "nl": "TOLERANTIEANALYSE"},
    "t_continuite": {
        "en": "DATA CONTINUITY", "fr": "CONTINUITE DES DONNEES",
        "nl": "CONTINUITEIT VAN DE GEGEVENS"},
    "t_environnement": {
        "en": "ENVIRONMENT & DIAGNOSTICS", "fr": "ENVIRONNEMENT & DIAGNOSTICS",
        "nl": "OMGEVING & DIAGNOSE"},
    "t_journal": {
        "en": "EVENT LOG", "fr": "JOURNAL DES EVENEMENTS", "nl": "GEBEURTENISSENLOG"},
    "t_recommandations": {
        "en": "RECOMMENDATIONS", "fr": "RECOMMANDATIONS", "nl": "AANBEVELINGEN"},

    # ── apercu ─────────────────────────────────────────────────────────
    "date": {"en": "Date", "fr": "Date", "nl": "Datum"},
    "observatoire": {"en": "Observatory", "fr": "Observatoire", "nl": "Sterrenwacht"},
    "monture": {"en": "Mount", "fr": "Monture", "nl": "Montering"},
    "firmware": {"en": "Firmware", "fr": "Micrologiciel", "nl": "Firmware"},
    "duree": {"en": "Duration", "fr": "Durée", "nl": "Duur"},
    "ech_total": {
        "en": "Total samples", "fr": "Échantillons totaux", "nl": "Meetpunten totaal"},
    "ech_suivi": {
        "en": "Tracking samples", "fr": "Échantillons en suivi",
        "nl": "Meetpunten tijdens volgen"},
    "cadence": {"en": "Sample rate", "fr": "Fréquence", "nl": "Meetfrequentie"},
    "cibles": {"en": "Targets", "fr": "Cibles", "nl": "Doelen"},
    "fichier": {"en": "File", "fr": "Fichier", "nl": "Bestand"},
    "echantillons": {"en": "samples", "fr": "échantillons", "nl": "meetpunten"},
    "rien_a_analyser": {
        "en": "No data to analyze",
        "fr": "Aucune donnée à analyser",
        "nl": "Geen gegevens om te analyseren"},
    "pas_de_suivi": {
        "en": "No TRACKING data found",
        "fr": "Aucune donnée de suivi trouvée",
        "nl": "Geen volggegevens gevonden"},
    "pas_de_suivi_detail": {
        "en": "Only SLEWING/PARKED/IDLE samples in file.",
        "fr": "Seuls des échantillons SLEWING/PARKED/IDLE dans le fichier.",
        "nl": "Alleen SLEWING/PARKED/IDLE-meetpunten in het bestand."},

    # ── qualite ────────────────────────────────────────────────────────
    "note": {"en": "Rating", "fr": "Note", "nl": "Beoordeling"},
    "s_jitter": {
        "en": "1. Tracking jitter", "fr": "1. Jitter de suivi",
        "nl": "1. Volgjitter"},
    "jitter_explique": {
        "en": "(spread while the mount holds a position — this is what blurs a frame)",
        "fr": "(dispersion quand la monture tient sa position — c'est ce qui étale l'étoile)",
        "nl": "(spreiding terwijl de montering haar positie houdt — dit maakt de ster onscherp)"},
    "jitter_combine": {
        "en": "Combined jitter", "fr": "Jitter combiné", "nl": "Gecombineerde jitter"},
    "note_fondee_ici": {
        "en": "<-- rating is based on this",
        "fr": "<-- la note est fondée là-dessus",
        "nl": "<-- hierop is de beoordeling gebaseerd"},
    "s_repositionnement": {
        "en": "2. Commanded repositioning", "fr": "2. Repositionnements commandés",
        "nl": "2. Opgedragen herpositioneringen"},
    "mouvements_detectes": {
        "en": "Moves detected", "fr": "Mouvements détectés", "nl": "Bewegingen gedetecteerd"},
    "amplitude_mediane": {
        "en": "Median size", "fr": "Amplitude médiane", "nl": "Mediane grootte"},
    "repositionnement_explique": {
        "en": "(dither and re-centering: the mount is MOVED between frames and stays\n"
              "       there — no effect inside an exposure)",
        "fr": "(dither et recentrage : la monture est DÉPLACÉE entre les poses et y\n"
              "       reste — sans effet pendant une pose)",
        "nl": "(dither en hercentrering: de montering wordt tussen de opnames VERPLAATST\n"
              "       en blijft daar — geen effect tijdens een opname)"},
    "aucun_detecte": {
        "en": "None detected", "fr": "Aucun détecté", "nl": "Geen gedetecteerd"},
    "s_derive": {
        "en": "3. Slow drift", "fr": "3. Dérive lente", "nl": "3. Langzame drift"},
    "derive_ad": {"en": "RA drift", "fr": "Dérive AD", "nl": "RK-drift"},
    "derive_dec": {"en": "DEC drift", "fr": "Dérive DEC", "nl": "DEC-drift"},
    "deplacement_pose": {
        "en": "Star motion over a {n:.0f} s exposure",
        "fr": "Déplacement de l'étoile sur une pose de {n:.0f} s",
        "nl": "Sterverplaatsing tijdens een opname van {n:.0f} s"},
    "annule_par_dither": {
        "en": "(cancelled by every dither)",
        "fr": "(annulée par chaque dither)",
        "nl": "(door elke dither opgeheven)"},
    "s_memoire": {
        "en": "For reference", "fr": "Pour mémoire", "nl": "Ter informatie"},
    "rms_brut": {
        "en": "Raw RMS (everything mixed)", "fr": "RMS brut (tout mélangé)",
        "nl": "Ruwe RMS (alles door elkaar)"},
    "rms_sans_derive": {
        "en": "After removing the drift only", "fr": "Dérive retirée seule",
        "nl": "Alleen de drift verwijderd"},
    "contient_paliers": {
        "en": "(still contains the repositioning steps)",
        "fr": "(contient encore les paliers de repositionnement)",
        "nl": "(bevat nog de herpositioneringsstappen)"},
    "excursions_ecartees": {
        "en": "Commanded excursions excluded",
        "fr": "Excursions commandées écartées",
        "nl": "Opgedragen uitwijkingen uitgesloten"},
    "excursions_explique": {
        "en": "(dither, re-centering, autofocus — mount motion, not tracking error)",
        "fr": "(dither, recentrage, autofocus — mouvement commandé, pas erreur de suivi)",
        "nl": "(dither, hercentrering, autofocus — opgedragen beweging, geen volgfout)"},
    "slews_ecartes": {
        "en": "Slew samples excluded", "fr": "Échantillons de slew écartés",
        "nl": "Zwenk-meetpunten uitgesloten"},
    "type_monture": {"en": "Mount type", "fr": "Type de monture", "nl": "Type montering"},
    "non_guidee_precision": {
        "en": "Precision unguided", "fr": "Précision non guidée",
        "nl": "Precisie, ongegidst"},
    "seuils_adaptes": {
        "en": "Thresholds adapted", "fr": "Seuils adaptés", "nl": "Aangepaste drempels"},
    "seuils": {"en": "Thresholds", "fr": "Seuils", "nl": "Drempels"},

    # ── verdicts ───────────────────────────────────────────────────────
    "v_exc_ng": {
        "en": "Excellent tracking for an unguided mount. Model-corrected pointing is precise.",
        "fr": "Suivi excellent pour une monture non guidée. Le pointage corrigé par modèle est précis.",
        "nl": "Uitstekend volgen voor een ongegidste montering. Het door het model gecorrigeerde richten is nauwkeurig."},
    "v_exc": {
        "en": "Your tracking is excellent. Stars will be perfectly round.",
        "fr": "Votre suivi est excellent. Les étoiles seront parfaitement rondes.",
        "nl": "Uw volgen is uitstekend. De sterren worden perfect rond."},
    "v_bon_ng": {
        "en": "Good tracking. Normal performance for an unguided precision mount.",
        "fr": "Bon suivi. Performance normale pour une monture de précision non guidée.",
        "nl": "Goed volgen. Normale prestatie voor een ongegidste precisiemontering."},
    "v_bon": {
        "en": "Good tracking. Satisfactory for most focal lengths.",
        "fr": "Bon suivi. Satisfaisant pour la plupart des focales.",
        "nl": "Goed volgen. Voldoende voor de meeste brandpuntsafstanden."},
    "v_moyen_ng": {
        "en": "Fair tracking. Check balance and axis play first.",
        "fr": "Suivi moyen. Vérifiez d'abord l'équilibrage et le jeu des axes.",
        "nl": "Matig volgen. Controleer eerst de uitbalancering en de speling van de assen."},
    "v_moyen_ng_note": {
        "en": "Note: on a model-driven mount the polar error is IN the model and is\n"
              "  compensated by corrected tracking rates — do not touch the azimuth screw.",
        "fr": "Note : sur une monture à modèle, l'erreur polaire est DANS le modèle et\n"
              "  est compensée par les taux de suivi — ne touchez pas la vis d'azimut.",
        "nl": "Let op: bij een montering met model zit de poolfout IN het model en wordt\n"
              "  zij door de volgsnelheden gecompenseerd — raak de azimutschroef niet aan."},
    "v_moyen": {
        "en": "Fair tracking. Visible on long exposures at high focal lengths.",
        "fr": "Suivi moyen. Visible sur les longues poses à haute focale.",
        "nl": "Matig volgen. Zichtbaar bij lange opnames en grote brandpuntsafstanden."},
    "v_moyen_note": {
        "en": "Check polar alignment.",
        "fr": "Vérifiez l'alignement polaire.",
        "nl": "Controleer de poolopstelling."},
    "v_mauvais_ng": {
        "en": "Poor jitter for a precision mount.",
        "fr": "Jitter insuffisant pour une monture de précision.",
        "nl": "Onvoldoende jitter voor een precisiemontering."},
    "v_mauvais_ng_ordre": {
        "en": "Check, in this order: balance, axis play, cable snag, wind, seeing.",
        "fr": "Vérifiez, dans cet ordre : équilibrage, jeu d'axes, câble qui tire, vent, seeing.",
        "nl": "Controleer in deze volgorde: uitbalancering, speling van de assen, trekkende kabel, wind, seeing."},
    "v_mauvais_ng_modele": {
        "en": "A pointing model corrects POINTING and slow drift, not short-term jitter:\n"
              "  rebuilding it will not help here.",
        "fr": "Un modèle de pointage corrige le POINTAGE et la dérive lente, pas le jitter :\n"
              "  le refaire n'y changera rien.",
        "nl": "Een richtmodel corrigeert het RICHTEN en de langzame drift, niet de jitter:\n"
              "  het opnieuw opbouwen helpt hier niet."},
    "v_mauvais": {
        "en": "Poor tracking. Stars likely elongated.",
        "fr": "Suivi insuffisant. Étoiles probablement allongées.",
        "nl": "Onvoldoende volgen. De sterren zijn waarschijnlijk langgerekt."},
    "v_mauvais_verif": {
        "en": "Check: polar alignment, tightness, balance.",
        "fr": "Vérifiez : alignement polaire, serrage, équilibrage.",
        "nl": "Controleer: poolopstelling, aandraaien, uitbalancering."},

    # ── statistiques par axe ───────────────────────────────────────────
    "dev_moyenne": {
        "en": "Mean deviation", "fr": "Déviation moyenne", "nl": "Gemiddelde afwijking"},
    "dev_mediane": {
        "en": "Median deviation", "fr": "Déviation médiane", "nl": "Mediane afwijking"},
    "jitter_entre": {
        "en": "JITTER (between repositionings)",
        "fr": "JITTER (entre repositionnements)",
        "nl": "JITTER (tussen herpositioneringen)"},
    "etale_la_pose": {
        "en": "<-- blurs the exposure", "fr": "<-- étale l'étoile",
        "nl": "<-- maakt de opname onscherp"},
    "rms_brut_court": {
        "en": "RMS raw (everything mixed)", "fr": "RMS brut (tout mélangé)",
        "nl": "Ruwe RMS (alles door elkaar)"},
    "pic_a_pic": {"en": "Peak-to-peak", "fr": "Pic-à-pic", "nl": "Piek-tot-piek"},
    "dev_min": {"en": "Min deviation", "fr": "Déviation min", "nl": "Minimale afwijking"},
    "dev_max": {"en": "Max deviation", "fr": "Déviation max", "nl": "Maximale afwijking"},
    "percentile": {"en": "percentile", "fr": "percentile", "nl": "percentiel"},
    "resolution_lecture": {
        "en": "Reading resolution", "fr": "Résolution de lecture",
        "nl": "Uitleesresolutie"},
    "limite_resolution": {
        "en": "[!] jitter is at the resolution limit — the true value may be smaller",
        "fr": "[!] le jitter est à la limite de résolution — la vraie valeur peut être plus faible",
        "nl": "[!] de jitter ligt op de resolutiegrens — de werkelijke waarde kan kleiner zijn"},
    "stdev_moy": {
        "en": "Running STDEV avg", "fr": "ÉCART-TYPE glissant moyen",
        "nl": "Lopende STDEV gemiddeld"},
    "stdev_max": {
        "en": "Running STDEV max", "fr": "ÉCART-TYPE glissant max",
        "nl": "Lopende STDEV max"},
    "stdev_med": {
        "en": "Running STDEV med", "fr": "ÉCART-TYPE glissant médian",
        "nl": "Lopende STDEV mediaan"},
    "taux_derive": {
        "en": "Drift rate", "fr": "Taux de dérive", "nl": "Driftsnelheid"},
    "derive_non_calculable": {
        "en": "Drift rate: not computable (zero duration or incomplete data)",
        "fr": "Taux de dérive : non calculable (durée nulle ou données incomplètes)",
        "nl": "Driftsnelheid: niet te berekenen (nulduur of onvolledige gegevens)"},
    "sur_pose_180": {
        "en": "over a 180 s exposure", "fr": "sur une pose de 180 s",
        "nl": "over een opname van 180 s"},
    "derive_forte_modele": {
        "en": "[!] Significant {axe} drift — add model points near this target",
        "fr": "[!] Dérive {axe} significative — ajoutez des points de modèle près de cette cible",
        "nl": "[!] Aanzienlijke {axe}-drift — voeg modelpunten toe in de buurt van dit doel"},
    "derive_forte_modele_note": {
        "en": "(the polar error is IN the model: the azimuth screw is not the answer)",
        "fr": "(l'erreur polaire est DANS le modèle : la vis d'azimut n'est pas la réponse)",
        "nl": "(de poolfout zit IN het model: de azimutschroef is niet het antwoord)"},
    "derive_forte_ad": {
        "en": "[!] Significant RA drift — check polar alignment (azimuth)",
        "fr": "[!] Dérive AD significative — vérifiez l'alignement polaire (azimut)",
        "nl": "[!] Aanzienlijke RK-drift — controleer de poolopstelling (azimut)"},
    "derive_forte_dec": {
        "en": "[!] Significant DEC drift — check polar alignment (altitude)",
        "fr": "[!] Dérive DEC significative — vérifiez l'alignement polaire (altitude)",
        "nl": "[!] Aanzienlijke DEC-drift — controleer de poolopstelling (hoogte)"},
    "derive_sans_effet": {
        "en": "[i] {axe} drift present but harmless over one exposure",
        "fr": "[i] Dérive {axe} présente mais sans effet sur une pose",
        "nl": "[i] {axe}-drift aanwezig maar zonder gevolg voor een opname"},
    "derive_legere": {
        "en": "[i] Slight {axe} drift detected",
        "fr": "[i] Légère dérive {axe} détectée",
        "nl": "[i] Lichte {axe}-drift gedetecteerd"},
    "derive_nulle": {
        "en": "[OK] No significant {axe} drift",
        "fr": "[OK] Pas de dérive {axe} significative",
        "nl": "[OK] Geen noemenswaardige {axe}-drift"},

    # ── FFT ────────────────────────────────────────────────────────────
    "fft_pics": {
        "en": "{axe} FFT — Top {n} peaks", "fr": "FFT {axe} — {n} pics dominants",
        "nl": "{axe} FFT — top {n} pieken"},
    "rang": {"en": "Rank", "fr": "Rang", "nl": "Rang"},
    "frequence": {"en": "Frequency", "fr": "Fréquence", "nl": "Frequentie"},
    "periode": {"en": "Period", "fr": "Période", "nl": "Periode"},
    "amplitude": {"en": "Amplitude", "fr": "Amplitude", "nl": "Amplitude"},
    "pe_detectee": {
        "en": "Periodic Error detected!", "fr": "Erreur périodique détectée !",
        "nl": "Periodieke fout gedetecteerd!"},
    "pe_tres_faible": {
        "en": "=> Very low PE, excellent!", "fr": "=> EP très faible, excellent !",
        "nl": "=> Zeer lage PF, uitstekend!"},
    "pe_acceptable": {
        "en": "=> Acceptable PE", "fr": "=> EP acceptable", "nl": "=> Aanvaardbare PF"},
    "pe_elevee": {
        "en": "=> High PE — consider PEC calibration",
        "fr": "=> EP élevée — envisagez une calibration PEC",
        "nl": "=> Hoge PF — overweeg PEC-kalibratie"},

    # ── temps, continuite, environnement ───────────────────────────────
    "derive_horloge": {
        "en": "Clock drift rate", "fr": "Dérive de l'horloge", "nl": "Klokdrift"},
    "derive_horloge_forte": {
        "en": "[!] Significant clock drift detected",
        "fr": "[!] Dérive d'horloge significative détectée",
        "nl": "[!] Aanzienlijke klokdrift gedetecteerd"},
    "horloge_stable": {
        "en": "[OK] Stable clock", "fr": "[OK] Horloge stable", "nl": "[OK] Stabiele klok"},
    "boucle_pc_lente": {
        "en": "[!] Slow PC loop", "fr": "[!] Boucle PC lente", "nl": "[!] Trage pc-lus"},
    "decalage_ntp": {
        "en": "[!] Large NTP offset", "fr": "[!] Décalage NTP important",
        "nl": "[!] Grote NTP-afwijking"},
    "coupures": {
        "en": "Gaps detected", "fr": "Coupures détectées", "nl": "Onderbrekingen gevonden"},
    "plus_longue_coupure": {
        "en": "Largest gap", "fr": "Plus longue coupure", "nl": "Langste onderbreking"},
    "coupure_cause": {
        "en": "(slewing, reconnection, network issue)",
        "fr": "(pointage, reconnexion, problème réseau)",
        "nl": "(zwenken, opnieuw verbinden, netwerkprobleem)"},
    "etoiles_modele": {
        "en": "Alignment stars", "fr": "Étoiles d'alignement", "nl": "Uitlijnsterren"},
    "erreur_polaire": {
        "en": "Polar error", "fr": "Erreur polaire", "nl": "Poolfout"},
    "alignement_excellent": {
        "en": "[OK] Excellent polar alignment",
        "fr": "[OK] Alignement polaire excellent",
        "nl": "[OK] Uitstekende poolopstelling"},
    "pression": {"en": "Pressure", "fr": "Pression", "nl": "Luchtdruk"},
    "temperature_stable": {
        "en": "[OK] Stable temperature", "fr": "[OK] Température stable",
        "nl": "[OK] Stabiele temperatuur"},
    "codes_statut": {
        "en": "Mount status codes", "fr": "Codes de statut monture",
        "nl": "Statuscodes montering"},
    "changements_statut": {
        "en": "Status changes", "fr": "Changements de statut", "nl": "Statuswijzigingen"},
    "aucun_probleme": {
        "en": "- No major issues detected. Continue with these settings.",
        "fr": "- Aucun problème majeur détecté. Continuez avec ces réglages.",
        "nl": "- Geen grote problemen gevonden. Ga zo door met deze instellingen."},

    # ── pied ───────────────────────────────────────────────────────────
    "genere_le": {
        "en": "Report generated on", "fr": "Rapport généré le",
        "nl": "Rapport gegenereerd op"},
    "a_heure": {"en": "at", "fr": "à", "nl": "om"},
    # ── complement ─────────────────────────────────────────────────────
    "temps_total_perdu": {
        "en": "Total gap time", "fr": "Temps total perdu", "nl": "Totaal verloren tijd"},
    "pc_a_du_mal": {
        "en": "— the PC is struggling", "fr": "— le PC a du mal",
        "nl": "— de pc kan het niet bijhouden"},
    "synchroniser_horloge": {
        "en": "— synchronize the PC clock", "fr": "— synchronisez l'horloge du PC",
        "nl": "— synchroniseer de pc-klok"},
    "suivi_faible": {
        "en": "[!] Only {pct:.0f}% tracking",
        "fr": "[!] Seulement {pct:.0f}% en suivi",
        "nl": "[!] Slechts {pct:.0f}% volgend"},
    "suivi_normal": {
        "en": "[OK] {pct:.0f}% tracking — normal",
        "fr": "[OK] {pct:.0f}% en suivi — normal",
        "nl": "[OK] {pct:.0f}% volgend — normaal"},
    "changement_temp": {
        "en": "Temp change", "fr": "Variation de température",
        "nl": "Temperatuurverandering"},
    "pendant_session": {
        "en": "over the session", "fr": "pendant la session",
        "nl": "gedurende de sessie"},
    "variation_taux_suivi": {
        "en": "[i] Tracking rate variation detected",
        "fr": "[i] Variation du taux de suivi détectée",
        "nl": "[i] Variatie in de volgsnelheid gedetecteerd"},
    "evenements_totaux": {
        "en": "Total events", "fr": "Événements totaux", "nl": "Gebeurtenissen totaal"},
    "alertes_tolerance": {
        "en": "Tolerance alerts", "fr": "Alertes de tolérance",
        "nl": "Tolerantiewaarschuwingen"},
    "avertissements": {
        "en": "Warnings", "fr": "Avertissements", "nl": "Waarschuwingen"},
    "evenements_tolerance_10": {
        "en": "Tolerance events (first 10)",
        "fr": "Événements de tolérance (10 premiers)",
        "nl": "Tolerantiegebeurtenissen (eerste 10)"},
    "et_n_de_plus": {
        "en": "... and {n} more", "fr": "... et {n} de plus", "nl": "... en nog {n}"},
    "titre_fenetre": {
        "en": "Session Analysis — MountMonitor",
        "fr": "Analyse de session — MountMonitor",
        "nl": "Sessieanalyse — MountMonitor"},
    "titre_rapport": {
        "en": "Night Session Analysis Report",
        "fr": "Rapport d'analyse de la session",
        "nl": "Analyserapport van de nachtsessie"},
    "exporter_txt": {
        "en": "Export TXT", "fr": "Exporter TXT", "nl": "TXT exporteren"},
    "fermer": {"en": "Close", "fr": "Fermer", "nl": "Sluiten"},
    "exporter_rapport": {
        "en": "Export Report", "fr": "Exporter le rapport", "nl": "Rapport exporteren"},
    "note_excellent": {"en": "EXCELLENT", "fr": "EXCELLENT", "nl": "UITSTEKEND"},
    "note_bon": {"en": "GOOD", "fr": "BON", "nl": "GOED"},
    "note_moyen": {"en": "FAIR", "fr": "MOYEN", "nl": "MATIG"},
    "note_mauvais": {"en": "POOR", "fr": "MAUVAIS", "nl": "ONVOLDOENDE"},
    # recommandations
    "r_ad_instable": {
        "en": "- RA jitter > {seuil}\": check RA balance, clamp tightness, cable drag",
        "fr": "- Jitter AD > {seuil}\" : vérifiez l'équilibrage AD, le serrage, les câbles",
        "nl": "- RK-jitter > {seuil}\": controleer de RK-uitbalancering, het aandraaien, de kabels"},
    "r_dec_instable": {
        "en": "- DEC jitter > {seuil}\": check DEC balance and DEC axis backlash",
        "fr": "- Jitter DEC > {seuil}\" : vérifiez l'équilibrage DEC et le jeu de l'axe DEC",
        "nl": "- DEC-jitter > {seuil}\": controleer de DEC-uitbalancering en de speling van de DEC-as"},
    "r_derive_modele": {
        "en": "- Target #{n}: {axe} drift {v:+.1f}\"/h — add model points near this target\n"
              "  (on a model-driven mount the azimuth screw is NOT the answer: the polar\n"
              "   error is in the model and is compensated by corrected tracking rates)",
        "fr": "- Cible #{n} : dérive {axe} {v:+.1f}\"/h — ajoutez des points de modèle près de cette cible\n"
              "  (sur une monture à modèle, la vis d'azimut n'est PAS la réponse : l'erreur\n"
              "   polaire est dans le modèle et compensée par les taux de suivi)",
        "nl": "- Doel #{n}: {axe}-drift {v:+.1f}\"/u — voeg modelpunten toe in de buurt van dit doel\n"
              "  (bij een montering met model is de azimutschroef NIET het antwoord: de\n"
              "   poolfout zit in het model en wordt door de volgsnelheden gecompenseerd)"},
    "r_derive_ad_polaire": {
        "en": "- Target #{n}: RA drift {v:+.1f}\"/h — adjust azimuth of polar alignment",
        "fr": "- Cible #{n} : dérive AD {v:+.1f}\"/h — ajustez l'azimut de l'alignement polaire",
        "nl": "- Doel #{n}: RK-drift {v:+.1f}\"/u — stel de azimut van de poolopstelling bij"},
    "r_derive_dec_polaire": {
        "en": "- Target #{n}: DEC drift {v:+.1f}\"/h — adjust altitude of polar alignment",
        "fr": "- Cible #{n} : dérive DEC {v:+.1f}\"/h — ajustez l'altitude de l'alignement polaire",
        "nl": "- Doel #{n}: DEC-drift {v:+.1f}\"/u — stel de hoogte van de poolopstelling bij"},
    "r_temperature": {
        "en": "- Temperature drop of {v:.1f}°C: use a motorized focuser with temperature compensation",
        "fr": "- Chute de température de {v:.1f}°C : utilisez un focuser motorisé avec compensation thermique",
        "nl": "- Temperatuurdaling van {v:.1f}°C: gebruik een gemotoriseerde focuser met temperatuurcompensatie"},
    "r_polaire": {
        "en": "- Polar error of {v:.1f}': redo the polar alignment",
        "fr": "- Erreur polaire de {v:.1f}' : refaites l'alignement polaire",
        "nl": "- Poolfout van {v:.1f}': voer de poolopstelling opnieuw uit"},
}


def R(cle: str, langue: str = LANGUE_DEFAUT, **kw) -> str:
    """Le texte de `cle` dans `langue`, anglais a defaut, la cle en dernier recours."""
    entree = TR.get(cle)
    if entree is None:
        return cle
    texte = entree.get(langue) or entree.get(LANGUE_DEFAUT) or cle
    return texte.format(**kw) if kw else texte
