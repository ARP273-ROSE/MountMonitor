"""Internationalization system for MountMonitor. Bilingual FR/EN."""

import locale

_current_lang = "en"

# Translation dictionary: key -> {en: ..., fr: ...}
TX = {
    # Main window
    "app_title": {"en": "MountMonitor", "fr": "MountMonitor", "nl": "MountMonitor"},
    "menu_file": {"en": "File", "fr": "Fichier", "nl": "Bestand"},
    "menu_edit": {"en": "Edit", "fr": "Édition", "nl": "Bewerken"},
    "menu_view": {"en": "View", "fr": "Affichage", "nl": "Beeld"},
    "menu_reset": {"en": "Reset", "fr": "Réinitialiser", "nl": "Resetten"},
    "menu_help": {"en": "Help", "fr": "Aide", "nl": "Help"},
    "menu_language": {"en": "Language", "fr": "Langue", "nl": "Taal"},

    # Panneau d'etat : ces lignes etaient ecrites en anglais en dur, si bien
    # que le journal melangeait la langue de l'utilisateur et l'anglais.
    "pan_mount": {"en": "Mount", "fr": "Monture", "nl": "Montering"},
    "pan_firmware": {"en": "Firmware", "fr": "Micrologiciel", "nl": "Firmware"},
    "pan_id": {"en": "ID", "fr": "Identifiant", "nl": "Identificatie"},
    "pan_pier": {"en": "Pier side", "fr": "Côté du pied", "nl": "Zijde van de zuil"},
    "pan_site": {"en": "Site", "fr": "Site", "nl": "Locatie"},
    "pan_elev": {"en": "elev.", "fr": "alt.", "nl": "hoogte"},
    "chk_refraction_ok": {"en": "Refraction: {v}", "fr": "Réfraction : {v}",
                          "nl": "Refractie: {v}"},
    "chk_refraction_ko": {
        "en": "Refraction is '{a}', expected '{e}'",
        "fr": "La réfraction est « {a} », attendu « {e} »",
        "nl": "De refractie is '{a}', verwacht '{e}'"},
    "chk_refraction_simple": {
        "en": "Refraction: {v} (simple check)",
        "fr": "Réfraction : {v} (contrôle simple)",
        "nl": "Refractie: {v} (eenvoudige controle)"},
    "chk_rate_ok": {"en": "Tracking rate set to {v}",
                    "fr": "Vitesse de suivi réglée sur {v}",
                    "nl": "Volgsnelheid ingesteld op {v}"},
    "chk_rate_ko": {
        "en": "Tracking rate is {a}, expected {e}",
        "fr": "La vitesse de suivi est {a}, attendu {e}",
        "nl": "De volgsnelheid is {a}, verwacht {e}"},
    "chk_gps_ok": {"en": "GPS: {v}", "fr": "GPS : {v}", "nl": "Gps: {v}"},
    "chk_gps_ko": {"en": "GPS is {a}, expected {e}", "fr": "Le GPS est {a}, attendu {e}",
                   "nl": "De gps is {a}, verwacht {e}"},
    "chk_dual_ok": {"en": "Dual tracking: {v}", "fr": "Suivi dual : {v}",
                    "nl": "Dual tracking: {v}"},
    "chk_dual_ko": {"en": "Dual tracking is {a}, expected {e}",
                    "fr": "Le suivi dual est {a}, attendu {e}",
                    "nl": "Dual tracking is {a}, verwacht {e}"},
    "chk_parked": {
        "en": "Mount parked: tracking checks skipped.",
        "fr": "Monture parquée : contrôles de suivi ignorés.",
        "nl": "Montering geparkeerd: volgcontroles overgeslagen."},
    "menu_manual": {"en": "Manual (PDF)", "fr": "Manuel (PDF)",
                    "nl": "Handleiding (pdf)"},
    "tt_manual": {
        "en": "Open the full manual in your language",
        "fr": "Ouvrir le manuel complet dans votre langue",
        "nl": "De volledige handleiding in uw taal openen"},
    "manual_absent": {
        "en": "The manual was not found next to the application.",
        "fr": "Le manuel est introuvable à côté de l'application.",
        "nl": "De handleiding is niet naast de toepassing gevonden."},

    "tt_zoom_h": {
        "en": "Set horizontal zoom to {zoom}x",
        "fr": "Zoom horizontal {zoom}x",
        "nl": "Horizontale zoom op {zoom}x zetten"},
    "tt_bug_desc": {
        "en": "Describe the issue here...",
        "fr": "Décrivez le problème ici...",
        "nl": "Beschrijf het probleem hier..."},
    "tt_upd_source": {
        "en": "Running from source — update with git.",
        "fr": "Lancé depuis les sources — mettez à jour avec git.",
        "nl": "Vanuit de broncode gestart — werk bij met git."},
    "tt_upd_failed": {
        "en": "The update could not be installed:\n{err}\n\n"
              "Your current version stays in place and works.",
        "fr": "La mise à jour n'a pas pu être installée :\n{err}\n\n"
              "Votre version actuelle reste en place et fonctionne.",
        "nl": "De update kon niet worden geïnstalleerd:\n{err}\n\n"
              "Uw huidige versie blijft staan en werkt."},
    "tt_an_window": {
        "en": "Comprehensive analysis of the recorded session",
        "fr": "Analyse complète de la session enregistrée",
        "nl": "Volledige analyse van de opgenomen sessie"},
    "tt_an_tabs": {
        "en": "The same report, in each language",
        "fr": "Le même rapport, dans chaque langue",
        "nl": "Hetzelfde rapport, in elke taal"},
    "tt_an_export": {
        "en": "Export analysis report as text file",
        "fr": "Exporter le rapport en fichier texte",
        "nl": "Het rapport als tekstbestand exporteren"},
    "tt_an_close": {
        "en": "Close analysis window",
        "fr": "Fermer la fenêtre d'analyse",
        "nl": "Het analysevenster sluiten"},
    # Tooltips. They were hard-coded as "EN: ...\nFR: ..." in the
    # widgets, which showed both languages at once and none in Dutch.
    "tt_connect": {
        "en": "Connect to mount",
        "fr": "Se connecter à la monture",
        "nl": "Verbinding maken met de montering"},
    "tt_disconnect": {
        "en": "Disconnect from mount",
        "fr": "Se déconnecter de la monture",
        "nl": "Verbinding met de montering verbreken"},
    "tt_open_log": {
        "en": "Open and analyze a previous log file",
        "fr": "Ouvrir et analyser un fichier log précédent",
        "nl": "Een eerder logbestand openen en analyseren"},
    "tt_open_log10m": {
        "en": "Analyze 10micron mount internal log files (.log10m)",
        "fr": "Analyser les fichiers log internes de la monture 10micron (.log10m)",
        "nl": "Interne logbestanden van de 10Micron-montering analyseren (.log10m)"},
    "tt_fft_win": {
        "en": "Open FFT analysis window",
        "fr": "Ouvrir la fenêtre d'analyse FFT",
        "nl": "Het FFT-analysevenster openen"},
    "tt_prefs": {
        "en": "Open preferences",
        "fr": "Ouvrir les préférences",
        "nl": "De voorkeuren openen"},
    "tt_doc_online": {
        "en": "Open online documentation",
        "fr": "Ouvrir la documentation en ligne",
        "nl": "De online documentatie openen"},
    "tt_bug_github": {
        "en": "Report a bug via GitHub Issues",
        "fr": "Signaler un bug via GitHub Issues",
        "nl": "Een fout melden via GitHub Issues"},
    "tt_check_upd": {
        "en": "Check for new versions on GitHub",
        "fr": "Vérifier les nouvelles versions sur GitHub",
        "nl": "Op GitHub naar nieuwe versies zoeken"},
    "tt_bug_prefilled": {
        "en": "Open GitHub with pre-filled bug report",
        "fr": "Ouvrir GitHub avec le rapport pré-rempli",
        "nl": "GitHub openen met een vooraf ingevuld foutrapport"},
    "tt_bug_cancel": {
        "en": "Cancel bug report",
        "fr": "Annuler le rapport",
        "nl": "Foutmelding annuleren"},
    "tt_upd_install": {
        "en": "Download and install the update",
        "fr": "Télécharger et installer la mise à jour",
        "nl": "De update downloaden en installeren"},
    "tt_upd_skip": {
        "en": "Skip this update",
        "fr": "Ignorer cette mise à jour",
        "nl": "Deze update overslaan"},
    "tt_obs_name": {
        "en": "Observatory name",
        "fr": "Nom de l'observatoire",
        "nl": "Naam van de sterrenwacht"},
    "tt_mount_name": {
        "en": "Mount name",
        "fr": "Nom de la monture",
        "nl": "Naam van de montering"},
    "tt_protocol": {
        "en": "Communication protocol",
        "fr": "Protocole de communication",
        "nl": "Communicatieprotocol"},
    "tt_mount_ip": {
        "en": "Mount IP address",
        "fr": "Adresse IP de la monture",
        "nl": "IP-adres van de montering"},
    "tt_mount_port": {
        "en": "Mount TCP port",
        "fr": "Port TCP de la monture",
        "nl": "TCP-poort van de montering"},
    "tt_serial_port": {
        "en": "Serial port for mount",
        "fr": "Port série de la monture",
        "nl": "Seriële poort van de montering"},
    "tt_serial_baud": {
        "en": "Serial speed — must match the mount's own setting (9600 by default)",
        "fr": "Vitesse de la liaison — elle doit être celle réglée dans la monture (9600 par défaut)",
        "nl": "Snelheid van de verbinding — moet overeenkomen met de instelling in de montering zelf (standaard 9600)"},
    "tt_ascom_id": {
        "en": "ASCOM driver ID",
        "fr": "Identifiant du driver ASCOM",
        "nl": "Identificatie van het ASCOM-stuurprogramma"},
    "tt_ascom_choose": {
        "en": "Open ASCOM Chooser to select mount driver",
        "fr": "Ouvrir le sélecteur ASCOM pour choisir le driver",
        "nl": "De ASCOM-kiezer openen om het stuurprogramma te selecteren"},
    "tt_ratio": {
        "en": "Graph to text box height ratio",
        "fr": "Ratio hauteur graphe/zone texte",
        "nl": "Hoogteverhouding grafiek/tekstvak"},
    "tt_language": {
        "en": "Interface language",
        "fr": "Langue de l'interface",
        "nl": "Taal van de interface"},
    "tt_polling": {
        "en": "Polling frequency",
        "fr": "Fréquence d'interrogation",
        "nl": "Uitleesfrequentie"},
    "tt_run_range": {
        "en": "Running STDEV window length",
        "fr": "Fenêtre de calcul écart-type glissant",
        "nl": "Vensterlengte voor de lopende standaardafwijking"},
    "tt_shift_graphs": {
        "en": "Shift graphs to compensate for running range delay",
        "fr": "Décaler les graphes pour compenser le délai de la plage glissante",
        "nl": "Grafieken verschuiven om de vertraging van het lopende bereik te compenseren"},
    "tt_reference": {
        "en": "Reference for deviations",
        "fr": "Référence pour les déviations",
        "nl": "Referentie voor de afwijkingen"},
    "tt_tol_ra": {
        "en": "RA tolerance in arcseconds",
        "fr": "Tolérance AD en secondes d'arc",
        "nl": "RK-tolerantie in boogseconden"},
    "tt_tol_dec": {
        "en": "DEC tolerance in arcseconds",
        "fr": "Tolérance DÉC en secondes d'arc",
        "nl": "DEC-tolerantie in boogseconden"},
    "tt_tol_ha": {
        "en": "Display RA tolerance in seconds of time (hour angle)",
        "fr": "Afficher la tolérance AD en secondes de temps (angle horaire)",
        "nl": "De RK-tolerantie in tijdseconden tonen (uurhoek)"},
    "tt_tol_sei": {
        "en": "Seismic tolerance as percentage of range",
        "fr": "Tolérance sismique en pourcentage de la plage",
        "nl": "Seismische tolerantie als percentage van het bereik"},
    "tt_log_mode": {
        "en": "What to log",
        "fr": "Quoi journaliser",
        "nl": "Wat er geregistreerd wordt"},
    "tt_site_auto": {
        "en": "Left empty, the mount is asked (:Gt#)",
        "fr": "Laissé vide, la monture est interrogée (:Gt#)",
        "nl": "Leeg gelaten wordt de montering bevraagd (:Gt#)"},
    "tt_site_lon": {
        "en": "POSITIVE EAST. The LX200 protocol counts the other way; the conversion is done for you when the mount answers.",
        "fr": "POSITIF VERS L'EST. Le protocole LX200 compte à l'envers ; la conversion est faite pour vous quand la monture répond.",
        "nl": "POSITIEF NAAR HET OOSTEN. Het LX200-protocol telt andersom; de omrekening gebeurt voor u zodra de montering antwoordt."},
    "tt_arm": {
        "en": "The log button arms the logger; recording starts at the first TRACKING sample",
        "fr": "Le bouton d'enregistrement arme l'enregistreur ; l'enregistrement démarre au premier échantillon en SUIVI",
        "nl": "De opnameknop zet de logger gereed; de registratie start bij het eerste meetpunt in VOLGEN"},
    "tt_pause": {
        "en": "The session stays open and the file stays the same; samples simply stop. Tracking again resumes in place.",
        "fr": "La session reste ouverte et le fichier reste le même ; les échantillons cessent, c'est tout. Le retour en suivi reprend sur place.",
        "nl": "De sessie blijft open en het bestand blijft hetzelfde; de meetpunten stoppen eenvoudigweg. Zodra er weer gevolgd wordt, hervat de registratie ter plaatse."},
    "tt_pause_delay": {
        "en": "Grace delay -- slews and autofocus finish well inside it",
        "fr": "Délai de grâce — slews et autofocus finissent largement avant",
        "nl": "Respijttijd — zwenkbewegingen en autofocus zijn er ruim binnen klaar"},
    "tt_sunrise": {
        "en": "Needs a known site. Only daylight ends a night: a mount that parks at 02:00 and resumes at 03:00 stays one night, one file, one report.",
        "fr": "Demande un site connu. Seul le jour termine une nuit : une monture qui parque à 02 h et repart à 03 h reste une seule nuit, un seul fichier, un seul rapport.",
        "nl": "Vereist een bekende locatie. Alleen het daglicht beëindigt een nacht: een montering die om 02:00 parkeert en om 03:00 verdergaat, blijft één nacht, één bestand, één rapport."},
    "tt_delay_slew": {
        "en": "Wait time after slew before logging resumes",
        "fr": "Délai après rotation avant reprise",
        "nl": "Wachttijd na een zwenkbeweging voordat de registratie hervat"},
    "tt_axial": {
        "en": "Axial position monitoring mode",
        "fr": "Mode de surveillance position axiale",
        "nl": "Bewakingsmodus voor de aspositie"},
    "tt_reset_mode": {
        "en": "When to automatically reset buffers",
        "fr": "Quand réinitialiser automatiquement les tampons",
        "nl": "Wanneer de buffers automatisch worden gewist"},
    "tt_dump_mode": {
        "en": "When to automatically dump graphs to files",
        "fr": "Quand exporter automatiquement les graphes",
        "nl": "Wanneer de grafieken automatisch worden weggeschreven"},
    "tt_close_mode": {
        "en": "When to automatically close log files",
        "fr": "Quand fermer automatiquement les fichiers log",
        "nl": "Wanneer de logbestanden automatisch worden gesloten"},
    "tt_history": {
        "en": "Number of lines in the history text area",
        "fr": "Nombre de lignes dans la zone d'historique",
        "nl": "Aantal regels in het geschiedenisvak"},
    "tt_ntp_on": {
        "en": "Enable NTP time comparison",
        "fr": "Activer la comparaison temps NTP",
        "nl": "De tijdvergelijking met NTP inschakelen"},
    "tt_ntp_server": {
        "en": "NTP server address",
        "fr": "Adresse du serveur NTP",
        "nl": "Adres van de NTP-server"},
    "tt_ntp_interval": {
        "en": "NTP polling interval",
        "fr": "Intervalle d'interrogation NTP",
        "nl": "Uitleesinterval voor NTP"},
    "tt_sei_on": {
        "en": "Enable seismometer data display",
        "fr": "Activer l'affichage sismomètre",
        "nl": "De weergave van de seismometer inschakelen"},
    "tt_sei_port": {
        "en": "Serial port for seismometer",
        "fr": "Port série du sismomètre",
        "nl": "Seriële poort van de seismometer"},
    "tt_sei_freq": {
        "en": "Seismometer sampling frequency",
        "fr": "Fréquence d'échantillonnage sismomètre",
        "nl": "Bemonsteringsfrequentie van de seismometer"},
    "tt_sei_offset": {
        "en": "Offset to center data around zero",
        "fr": "Décalage pour centrer les données sur zéro",
        "nl": "Verschuiving om de gegevens rond nul te centreren"},
    "tt_sei_range": {
        "en": "Vertical range for seismic graph",
        "fr": "Plage verticale du graphe sismique",
        "nl": "Verticaal bereik van de seismische grafiek"},
    "tt_chk_refr": {
        "en": "Verify refraction correction at startup and after each slew",
        "fr": "Vérifier la correction de réfraction au démarrage et après chaque rotation",
        "nl": "De refractiecorrectie controleren bij het starten en na elke zwenkbeweging"},
    "tt_chk_refr_mode": {
        "en": "Expected refraction correction mode",
        "fr": "Mode attendu de la correction de réfraction",
        "nl": "Verwachte modus van de refractiecorrectie"},
    "tt_chk_rate": {
        "en": "Verify tracking rate matches expected value",
        "fr": "Vérifier que la vitesse de suivi correspond à la valeur attendue",
        "nl": "Controleren of de volgsnelheid overeenkomt met de verwachte waarde"},
    "tt_chk_rate_val": {
        "en": "Expected tracking rate",
        "fr": "Vitesse de suivi attendue",
        "nl": "Verwachte volgsnelheid"},
    "tt_chk_gps": {
        "en": "Verify GPS clock synchronization",
        "fr": "Vérifier la synchronisation GPS",
        "nl": "De gps-kloksynchronisatie controleren"},
    "tt_chk_gps_val": {
        "en": "Expected GPS sync state",
        "fr": "État attendu de la synchro GPS",
        "nl": "Verwachte staat van de gps-synchronisatie"},
    "tt_chk_dual": {
        "en": "Verify dual tracking status",
        "fr": "Vérifier le statut du suivi dual",
        "nl": "De status van dual tracking controleren"},
    "tt_chk_dual_val": {
        "en": "Expected dual tracking state",
        "fr": "État attendu du suivi dual",
        "nl": "Verwachte staat van dual tracking"},
    "tt_ra": {
        "en": "Right Ascension",
        "fr": "Ascension Droite",
        "nl": "Rechte klimming"},
    "tt_dec": {
        "en": "Declination",
        "fr": "Déclinaison",
        "nl": "Declinatie"},
    "tt_freq": {
        "en": "Polling frequency and sample count",
        "fr": "Fréquence d'acquisition et nombre d'échantillons",
        "nl": "Uitleesfrequentie en aantal meetpunten"},
    "consent_question": {
        "en": "Allow MountMonitor to report its own problems?",
        "fr": "Autoriser MountMonitor à signaler ses problèmes ?",
        "nl": "MountMonitor toestaan zijn eigen problemen te melden?"},
    "consent_detail": {
        "en": "If the application crashes, freezes or fails to start, it can "
              "report it by itself to whoever maintains it. You will have "
              "nothing to do, and nothing else is ever sent: not your tracking "
              "data, not your file names, not your user name.",
        "fr": "Si l'application plante, se fige ou refuse de démarrer, elle peut "
              "l'annoncer toute seule à celui qui la maintient. Vous n'aurez rien "
              "à faire, et rien d'autre n'est envoyé : ni vos données de suivi, "
              "ni vos noms de fichiers, ni votre nom d'utilisateur.",
        "nl": "Als de toepassing vastloopt, blokkeert of niet wil starten, kan "
              "zij dat zelf melden aan wie haar onderhoudt. U hoeft niets te "
              "doen, en er wordt niets anders verstuurd: niet uw volggegevens, "
              "niet uw bestandsnamen, niet uw gebruikersnaam."},
    "consent_oui": {"en": "Allow", "fr": "Autoriser", "nl": "Toestaan"},
    "crash_titre": {"en": "Crash report", "fr": "Rapport de plantage",
                    "nl": "Crashrapport"},
    "crash_texte": {
        "en": "MountMonitor crashed during the last session.",
        "fr": "MountMonitor a planté lors de la dernière session.",
        "nl": "MountMonitor is tijdens de vorige sessie vastgelopen."},
    "crash_erreur": {"en": "Error", "fr": "Erreur", "nl": "Fout"},
    "crash_question": {
        "en": "Would you like to report this crash on GitHub?",
        "fr": "Voulez-vous signaler ce plantage sur GitHub ?",
        "nl": "Wilt u deze crash melden op GitHub?"},
    "crash_anonyme": {
        "en": "(all paths are anonymized)",
        "fr": "(tous les chemins sont anonymisés)",
        "nl": "(alle paden worden geanonimiseerd)"},
    "crash_signaler": {"en": "Report on GitHub", "fr": "Signaler sur GitHub",
                       "nl": "Melden op GitHub"},
    "crash_ignorer": {"en": "Dismiss", "fr": "Ignorer", "nl": "Negeren"},
    "consent_non": {"en": "No thanks", "fr": "Non merci", "nl": "Nee, bedankt"},
    "nuit_coucher": {"en": "Sunset", "fr": "Coucher", "nl": "Zonsondergang"},
    "nuit_nautique": {"en": "Naut. twilight", "fr": "Crép. nautique",
                      "nl": "Nautische schemering"},
    "nuit_lever": {"en": "Sunrise", "fr": "Lever", "nl": "Zonsopkomst"},
    "nuit_noire": {"en": "Astronomical night", "fr": "Nuit noire",
                   "nl": "Astronomische nacht"},
    "nuit_pas_de_nuit_noire": {
        "en": "No astronomical night tonight: the Sun stays above -18 deg.",
        "fr": "Pas de nuit noire cette nuit : le Soleil reste au-dessus de -18°.",
        "nl": "Geen astronomische nacht vannacht: de zon blijft boven -18 graden."},
    "nuit_jour_permanent": {
        "en": "The Sun does not set at this site today.",
        "fr": "Le Soleil ne se couche pas sur ce site aujourd'hui.",
        "nl": "De zon gaat vandaag niet onder op deze locatie."},
    "pref_site": {"en": "Observing site", "fr": "Site d'observation",
                  "nl": "Waarnemingslocatie"},
    "pref_site_lat": {"en": "Latitude (deg, + north)", "fr": "Latitude (°, + nord)",
                      "nl": "Breedtegraad (°, + noord)"},
    "pref_site_lon": {"en": "Longitude (deg, + EAST)", "fr": "Longitude (°, + EST)",
                      "nl": "Lengtegraad (°, + OOST)"},
    "pref_site_elev": {"en": "Elevation (m)", "fr": "Altitude (m)", "nl": "Hoogte (m)"},
    "t_nuit": {"en": "NIGHT EPHEMERIS", "fr": "ÉPHÉMÉRIDES DE LA NUIT",
               "nl": "EFEMERIDEN VAN DE NACHT"},
    "nuit_site": {"en": "Site", "fr": "Site", "nl": "Locatie"},
    "nuit_duree_noire": {"en": "Astronomical night lasts", "fr": "Durée de nuit noire",
                         "nl": "Duur astronomische nacht"},
    "nuit_couverture": {"en": "Session covers", "fr": "La session couvre",
                        "nl": "De sessie bedekt"},
    "nuit_avant": {"en": "recorded before nightfall",
                   "fr": "enregistré avant la nuit noire",
                   "nl": "opgenomen voor het donker"},
    "nuit_apres": {"en": "recorded after dawn", "fr": "enregistré après l'aube",
                   "nl": "opgenomen na het ochtendgloren"},
    "nuit_pas_de_site": {
        "en": "No site known: set it in Preferences to get the twilights.",
        "fr": "Site inconnu : renseignez-le dans les préférences pour avoir les crépuscules.",
        "nl": "Locatie onbekend: stel deze in bij Voorkeuren voor de schemeringen."},
    "btn_armed_log": {"en": "ARMED — waiting for tracking",
                      "fr": "ARMÉ — en attente du suivi",
                      "nl": "GEREED — wacht op volgen"},
    "logging_armed": {
        "en": "Logger armed: recording starts when the mount begins tracking.",
        "fr": "Enregistreur armé : l'enregistrement démarrera quand la monture suivra.",
        "nl": "Logger gereed: de registratie start zodra de montering volgt."},
    "logging_disarmed": {"en": "Logger disarmed.", "fr": "Enregistreur désarmé.",
                         "nl": "Logger uitgeschakeld."},
    "logging_autostart": {
        "en": "Mount is tracking: recording started.",
        "fr": "La monture suit : enregistrement démarré.",
        "nl": "De montering volgt: registratie gestart."},
    "logging_autostop": {
        "en": "Sun is up: night over, recording stopped and report written.",
        "fr": "Le Soleil est levé : nuit terminée, enregistrement arrêté et rapport écrit.",
        "nl": "De zon is op: nacht voorbij, registratie gestopt en rapport geschreven."},
    "logging_suspendu": {
        "en": "Mount no longer tracking: recording suspended, same night kept.",
        "fr": "La monture ne suit plus : enregistrement suspendu, la nuit reste ouverte.",
        "nl": "De montering volgt niet meer: registratie onderbroken, de nacht blijft open."},
    "logging_repris": {
        "en": "Tracking again: recording resumed in the same file.",
        "fr": "Suivi retrouvé : enregistrement repris dans le même fichier.",
        "nl": "Weer aan het volgen: registratie hervat in hetzelfde bestand."},
    "pref_pause": {
        "en": "Suspend recording when the mount stops tracking",
        "fr": "Suspendre l'enregistrement quand la monture cesse de suivre",
        "nl": "Registratie onderbreken zodra de montering stopt met volgen"},
    "pref_close_sunrise": {
        "en": "End the night and write the report at sunrise",
        "fr": "Terminer la nuit et écrire le rapport au lever du Soleil",
        "nl": "De nacht beëindigen en het rapport schrijven bij zonsopkomst"},
    "pref_autostart": {
        "en": "Start recording when the mount starts tracking",
        "fr": "Démarrer l'enregistrement quand la monture se met à suivre",
        "nl": "Registratie starten zodra de montering begint te volgen"},
    "pref_autostop": {
        "en": "Stop and write the night report when the mount parks",
        "fr": "Arrêter et écrire le rapport de nuit quand la monture se parque",
        "nl": "Stoppen en het nachtrapport schrijven zodra de montering parkeert"},
    "lang_auto": {"en": "Automatic (system)", "fr": "Automatique (système)",
                  "nl": "Automatisch (systeem)"},
    "lang_restart_titre": {"en": "Language changed", "fr": "Langue changée",
                           "nl": "Taal gewijzigd"},
    "lang_restart_texte": {
        "en": "The interface language will be applied when MountMonitor restarts.",
        "fr": "La langue de l'interface sera appliquée au prochain démarrage de MountMonitor.",
        "nl": "De taal van de interface wordt toegepast bij de volgende start van MountMonitor."},
    "lang_restart_now": {"en": "Restart now", "fr": "Redémarrer maintenant",
                         "nl": "Nu herstarten"},
    "lang_restart_later": {"en": "Later", "fr": "Plus tard", "nl": "Later"},
    "lang_restart_bloque": {
        "en": "Logging is running: the restart is not offered so the night is not cut short.",
        "fr": "L'enregistrement est en cours : le redémarrage n'est pas proposé, pour ne pas couper la nuit.",
        "nl": "De registratie loopt: herstarten wordt niet aangeboden om de nacht niet af te breken."},
    "menu_preferences": {"en": "Preferences", "fr": "Préférences", "nl": "Voorkeuren"},
    "menu_quit": {"en": "Quit", "fr": "Quitter", "nl": "Afsluiten"},
    "menu_about": {"en": "About", "fr": "À propos", "nl": "Over"},
    "menu_help_contents": {"en": "Help Contents", "fr": "Contenu de l'aide", "nl": "Helponderwerpen"},
    "menu_online_help": {"en": "Online Help", "fr": "Aide en ligne", "nl": "Online help"},
    "menu_report_bug": {"en": "Report a Bug", "fr": "Signaler un bug", "nl": "Een fout melden"},
    "menu_create_shortcut": {"en": "Create Desktop Shortcut", "fr": "Créer raccourci bureau", "nl": "Snelkoppeling maken"},

    # Connection
    "connecting": {"en": "Connecting...", "fr": "Connexion...", "nl": "Verbinden..."},
    "connected": {"en": "Connected", "fr": "Connecté", "nl": "Verbonden"},
    "disconnected": {"en": "Disconnected", "fr": "Déconnecté", "nl": "Niet verbonden"},
    "connection_failed": {"en": "Connection failed", "fr": "Échec de connexion", "nl": "Verbinding mislukt"},
    "connection_restored": {"en": "Connection restored", "fr": "Connexion restaurée", "nl": "Verbinding hersteld"},
    "reconnecting": {"en": "Reconnecting...", "fr": "Reconnexion...", "nl": "Opnieuw verbinden..."},

    # Mount status
    "mount_tracking": {"en": "The mount is tracking", "fr": "La monture est en suivi", "nl": "De montering volgt"},
    "mount_slewing": {"en": "The mount is slewing", "fr": "La monture pivote", "nl": "De montering zwenkt"},
    "mount_parked": {"en": "The mount is parked", "fr": "La monture est parquée", "nl": "De montering is geparkeerd"},
    "mount_idle": {"en": "The mount is idle", "fr": "La monture est au repos", "nl": "De montering is inactief"},

    # Graphs
    "right_ascension": {"en": "RIGHT ASCENSION", "fr": "ASCENSION DROITE", "nl": "RECHTE KLIMMING"},
    "declination": {"en": "DECLINATION", "fr": "DÉCLINAISON", "nl": "DECLINATIE"},
    "seismic": {"en": "SEISMIC", "fr": "SISMIQUE", "nl": "SEISMISCH"},
    "time_graph": {"en": "TIME", "fr": "TEMPS", "nl": "TIJD"},
    "ra_short": {"en": "RA", "fr": "AD", "nl": "RK"},
    "dec_short": {"en": "DEC", "fr": "DÉC", "nl": "DEC"},

    # Statistics
    "stdev": {"en": "STDEV", "fr": "ÉCART-TYPE", "nl": "STDEV"},
    "min_value": {"en": "Min", "fr": "Min", "nl": "Min"},
    "max_value": {"en": "Max", "fr": "Max", "nl": "Max"},
    "range_value": {"en": "Range", "fr": "Plage", "nl": "Bereik"},
    "tolerance": {"en": "Tolerance", "fr": "Tolérance", "nl": "Tolerantie"},
    "tolerance_exceeded": {"en": "Tolerance exceeded!", "fr": "Tolérance dépassée !", "nl": "Tolerantie overschreden!"},
    "tolerance_ok": {"en": "Within tolerance", "fr": "Dans la tolérance", "nl": "Binnen de tolerantie"},

    # FFT
    "fft_title": {"en": "FFT Analysis", "fr": "Analyse FFT", "nl": "FFT-analyse"},
    "frequency_domain": {"en": "Frequency Domain", "fr": "Domaine fréquentiel", "nl": "Frequentiedomein"},
    "period_domain": {"en": "Period Domain", "fr": "Domaine temporel", "nl": "Periodedomein"},

    # Preferences
    "pref_general": {"en": "General", "fr": "Général", "nl": "Algemeen"},
    "pref_processing": {"en": "Processing", "fr": "Traitement", "nl": "Verwerking"},
    "pref_auxiliary": {"en": "Auxiliary", "fr": "Auxiliaire", "nl": "Hulpapparatuur"},
    "pref_misc": {"en": "Miscellaneous", "fr": "Divers", "nl": "Overig"},
    "pref_observatory": {"en": "Observatory name", "fr": "Nom de l'observatoire", "nl": "Naam sterrenwacht"},
    "pref_mount_name": {"en": "Mount name", "fr": "Nom de la monture", "nl": "Naam montering"},
    "pref_mount_ip": {"en": "Mount IP address", "fr": "Adresse IP de la monture", "nl": "IP-adres montering"},
    "pref_mount_port": {"en": "Mount port", "fr": "Port de la monture", "nl": "Poort montering"},
    "pref_protocol": {"en": "Protocol", "fr": "Protocole", "nl": "Protocol"},
    "pref_polling": {"en": "Polling frequency (Hz)", "fr": "Fréquence d'interrogation (Hz)", "nl": "Uitleesfrequentie (Hz)"},
    "pref_running_range": {"en": "Running range (s)", "fr": "Plage glissante (s)", "nl": "Lopend bereik (s)"},
    "pref_reference": {"en": "Reference", "fr": "Référence", "nl": "Referentie"},
    "pref_tolerance_ra": {"en": "RA tolerance (arcsec)", "fr": "Tolérance AD (arcsec)", "nl": "RK-tolerantie (boogseconden)"},
    "pref_tolerance_dec": {"en": "DEC tolerance (arcsec)", "fr": "Tolérance DÉC (arcsec)", "nl": "DEC-tolerantie (boogseconden)"},
    "pref_log_mode": {"en": "Logging", "fr": "Journalisation", "nl": "Loggen"},
    "pref_ntp_enabled": {"en": "Use NTP server", "fr": "Utiliser un serveur NTP", "nl": "NTP-server gebruiken"},
    "pref_ntp_server": {"en": "NTP server address", "fr": "Adresse du serveur NTP", "nl": "Adres NTP-server"},
    "pref_seismometer": {"en": "Seismometer", "fr": "Sismomètre", "nl": "Seismometer"},
    "pref_mount_checks": {"en": "Mount checks", "fr": "Vérifications monture", "nl": "Controles montering"},
    "pref_connection": {"en": "Connection", "fr": "Connexion", "nl": "Verbinding"},
    "pref_layout": {"en": "Layout", "fr": "Mise en page", "nl": "Indeling"},
    "pref_graph_ratio": {"en": "Graph:Textbox ratio", "fr": "Ratio graphe:texte", "nl": "Verhouding grafiek:tekst"},
    "pref_polling_group": {"en": "Polling", "fr": "Acquisition", "nl": "Uitlezen"},
    "pref_correct_graphs": {"en": "Correct graphs for range", "fr": "Corriger graphes pour la plage", "nl": "Grafieken corrigeren voor bereik"},
    "pref_log_mode_label": {"en": "Mode", "fr": "Mode", "nl": "Modus"},
    "pref_delay_slew": {"en": "Delay after slew (s)", "fr": "Délai après pointage (s)", "nl": "Wachttijd na zwenken (s)"},
    "pref_axial_mode": {"en": "Axial mode", "fr": "Mode axial", "nl": "Axiale modus"},
    "pref_ntp_group": {"en": "NTP Time Server", "fr": "Serveur NTP", "nl": "NTP-tijdserver"},
    "pref_ntp_interval": {"en": "Interval (s)", "fr": "Intervalle (s)", "nl": "Interval (s)"},
    "pref_sei_offset": {"en": "Offset", "fr": "Décalage", "nl": "Offset"},
    "pref_show_ra_ha": {"en": "Show RA as HA [s]", "fr": "AD en HA [s]", "nl": "RK tonen als UH [s]"},
    "pref_ascom_driver": {"en": "ASCOM Driver", "fr": "Pilote ASCOM", "nl": "ASCOM-driver"},
    "pref_reset_mode": {"en": "Reset mode", "fr": "Mode réinitialisation", "nl": "Resetmodus"},
    "pref_dump_graphs": {"en": "Dump graphs", "fr": "Export graphes", "nl": "Grafieken exporteren"},
    "pref_close_files": {"en": "Close files", "fr": "Fermer fichiers", "nl": "Bestanden sluiten"},
    "pref_tolerance_seismic": {"en": "Seismic tolerance (%)", "fr": "Tolérance sismique (%)", "nl": "Seismische tolerantie (%)"},
    "pref_history_lines": {"en": "History lines", "fr": "Lignes d'historique", "nl": "Regels historie"},
    "pref_expected_value": {"en": "Expected value", "fr": "Valeur attendue", "nl": "Verwachte waarde"},
    "pref_serial_port": {"en": "Serial port", "fr": "Port série", "nl": "Seriële poort"},
    "pref_select_ascom": {"en": "Select...", "fr": "Sélectionner...", "nl": "Selecteren..."},
    "pref_language": {"en": "Language", "fr": "Langue", "nl": "Taal"},
    "pref_enable": {"en": "Enable", "fr": "Activer", "nl": "Inschakelen"},
    "pref_frequency": {"en": "Frequency (Hz)", "fr": "Fréquence (Hz)", "nl": "Frequentie (Hz)"},
    "pref_range": {"en": "Range", "fr": "Plage", "nl": "Bereik"},

    # Logging
    "logging_started": {"en": "Logging started", "fr": "Journalisation démarrée", "nl": "Loggen gestart"},
    "logging_stopped": {"en": "Logging stopped", "fr": "Journalisation arrêtée", "nl": "Loggen gestopt"},
    "new_log_files": {"en": "New log files created", "fr": "Nouveaux fichiers log créés", "nl": "Nieuwe logbestanden aangemaakt"},

    # Log replay & analysis
    "menu_open_log": {"en": "Open Log...", "fr": "Ouvrir un log...", "nl": "Log openen..."},
    "menu_open_log10m": {"en": "Analyze Mount Logs (.log10m)...", "fr": "Analyser logs monture (.log10m)...", "nl": "Monteringlogs analyseren (.log10m)..."},
    "open_log_title": {"en": "Open Log File", "fr": "Ouvrir un fichier log", "nl": "Logbestand openen"},
    "replay_loaded": {
        "en": "Log loaded: {samples} samples, duration {duration}",
        "fr": "Log chargé : {samples} échantillons, durée {duration}",
    "nl": "Log geladen: {samples} meetpunten, duur {duration}",
},
    "replay_no_data": {
        "en": "No data found in this log file",
        "fr": "Aucune donnée trouvée dans ce fichier log",
    "nl": "Geen gegevens gevonden in dit logbestand",
},
    "replay_mode": {"en": "REPLAY MODE", "fr": "MODE RELECTURE", "nl": "HERHAALMODUS"},
    "report_saved": {
        "en": "Night report saved",
        "fr": "Rapport de nuit enregistré",
    "nl": "Nachtrapport opgeslagen",
},
    "replay_graphs_failed": {
        "en": "Graphs could not be drawn (the report opens anyway)",
        "fr": "Les graphes n'ont pas pu être tracés (le rapport s'ouvre quand même)",
    "nl": "Grafieken konden niet worden getekend (het rapport opent toch)",
},
    "replay_fft_failed": {
        "en": "FFT could not be computed (the report opens anyway)",
        "fr": "La FFT n'a pas pu être calculée (le rapport s'ouvre quand même)",
    "nl": "FFT kon niet worden berekend (het rapport opent toch)",
},
    "replay_report_failed": {
        "en": "The night report could not be built",
        "fr": "Le rapport de nuit n'a pas pu être construit",
    "nl": "Het nachtrapport kon niet worden opgebouwd",
},
    "analysis_complete": {
        "en": "Analysis complete",
        "fr": "Analyse terminée",
    "nl": "Analyse voltooid",
},

    # Zoom
    "horizontal_zoom": {"en": "Horizontal Zoom", "fr": "Zoom horizontal", "nl": "Horizontale zoom"},
    "vertical_zoom": {"en": "Vertical Zoom", "fr": "Zoom vertical", "nl": "Verticale zoom"},
    "zoom_data": {"en": "Data (median centred)", "fr": "Données (centré médiane)", "nl": "Gegevens (gecentreerd op mediaan)"},
    "zoom_tolerance": {"en": "Tolerance", "fr": "Tolérance", "nl": "Tolerantie"},
    "zoom_maximum": {"en": "Maximum (data/tolerance)", "fr": "Maximum (données/tolérance)", "nl": "Maximum (gegevens/tolerantie)"},
    "zoom_minmax": {"en": "Min/Max value lines", "fr": "Lignes Min/Max", "nl": "Min/Max-lijnen"},

    # Reset
    "reset_minmax": {"en": "Reset Min/Max", "fr": "Réinitialiser Min/Max", "nl": "Min/Max resetten"},
    "reset_buffers": {"en": "Reset Buffers", "fr": "Réinitialiser les tampons", "nl": "Buffers resetten"},
    "reset_both": {"en": "Reset Buffers and Min/Max", "fr": "Réinitialiser tampons et Min/Max", "nl": "Buffers en Min/Max resetten"},
    "reset_new_files": {"en": "New Files", "fr": "Nouveaux fichiers", "nl": "Nieuwe bestanden"},

    # Simulation
    "sim_mount": {"en": "Mount simulation active", "fr": "Simulation monture active", "nl": "Simulatie montering actief"},
    "sim_seismometer": {"en": "Seismometer simulation active", "fr": "Simulation sismomètre active", "nl": "Simulatie seismometer actief"},
    "sim_all": {"en": "Full simulation mode", "fr": "Mode simulation complète", "nl": "Volledige simulatiemodus"},

    # Auto-update
    "update_available": {"en": "Update Available", "fr": "Mise à jour disponible", "nl": "Update beschikbaar"},
    "update_current": {"en": "Current version", "fr": "Version actuelle", "nl": "Huidige versie"},
    "update_new": {"en": "New version", "fr": "Nouvelle version", "nl": "Nieuwe versie"},
    "update_download": {"en": "Download && Install", "fr": "Télécharger && installer", "nl": "Downloaden && installeren"},
    "update_skip": {"en": "Skip", "fr": "Ignorer", "nl": "Overslaan"},
    "update_checking": {"en": "Checking for updates...", "fr": "Vérification des mises à jour...", "nl": "Controleren op updates..."},
    "update_up_to_date": {
        "en": "You are running the latest version ({version}).",
        "fr": "Vous utilisez la dernière version ({version}).",
    "nl": "U gebruikt de nieuwste versie ({version}).",
},
    "update_changelog": {"en": "Changelog", "fr": "Notes de version", "nl": "Wijzigingen"},
    "update_failed": {
        "en": "Update failed. Please try again or download manually.",
        "fr": "La mise à jour a échoué. Réessayez ou téléchargez manuellement.",
    "nl": "Update mislukt. Probeer opnieuw of download handmatig.",
},
    "update_success": {
        "en": "Update installed successfully. MountMonitor will restart.",
        "fr": "Mise à jour installée. MountMonitor va redémarrer.",
    "nl": "Update geïnstalleerd. MountMonitor wordt opnieuw gestart.",
},
    "update_downloading": {"en": "Downloading update...", "fr": "Téléchargement en cours...", "nl": "Update downloaden..."},
    "update_applying": {"en": "Applying update...", "fr": "Application de la mise à jour...", "nl": "Update toepassen..."},
    "update_error": {
        "en": "Could not check for updates.\nPlease check your internet connection.",
        "fr": "Impossible de vérifier les mises à jour.\nVérifiez votre connexion internet.",
    "nl": "Kan niet controleren op updates.\nControleer uw internetverbinding.",
},
    "menu_check_updates": {"en": "Check for Updates...", "fr": "Vérifier les mises à jour...", "nl": "Controleren op updates..."},

    # Bug report (enhanced)
    "bug_report_title": {"en": "Report a Bug", "fr": "Signaler un bug", "nl": "Een fout melden"},
    "bug_report_send": {"en": "Open on GitHub", "fr": "Ouvrir sur GitHub", "nl": "Openen op GitHub"},
    "bug_report_cancel": {"en": "Cancel", "fr": "Annuler", "nl": "Annuleren"},
    "bug_report_description": {
        "en": "Describe the problem:",
        "fr": "Décrivez le problème :",
    "nl": "Beschrijf het probleem:",
},
    "bug_report_info": {
        "en": "System information will be included automatically (anonymized).",
        "fr": "Les informations système seront incluses automatiquement (anonymisées).",
    "nl": "Systeeminformatie wordt automatisch meegestuurd",
},

    # Crash report dialog (improved)
    "crash_title": {
        "en": "Crash Report",
        "fr": "Rapport de crash",
    "nl": "Crashrapport",
},
    "crash_detected": {
        "en": "MountMonitor crashed during the last session.",
        "fr": "MountMonitor a planté lors de la dernière session.",
    "nl": "MountMonitor is tijdens de vorige sessie vastgelopen.",
},
    "crash_send": {"en": "Report on GitHub", "fr": "Signaler sur GitHub", "nl": "Melden op GitHub"},
    "crash_dismiss": {"en": "Dismiss", "fr": "Ignorer", "nl": "Negeren"},

    # Status panel labels
    "label_ra": {"en": "RA:", "fr": "AD :", "nl": "RK:"},
    "label_dec": {"en": "DEC:", "fr": "DÉC :", "nl": "DEC:"},
    "samples": {"en": "samples", "fr": "échantillons", "nl": "meetpunten"},
    "error_status": {"en": "Error", "fr": "Erreur", "nl": "Fout"},

    # Buttons
    "btn_connect": {"en": "Connect", "fr": "Connecter", "nl": "Verbinden"},
    "btn_disconnect": {"en": "Disconnect", "fr": "Déconnecter", "nl": "Verbinding verbreken"},
    "btn_start_log": {"en": "Start Log", "fr": "Démarrer log", "nl": "Log starten"},
    "btn_stop_log": {"en": "Stop Log", "fr": "Arrêter log", "nl": "Log stoppen"},

    # Messages
    "graphs_exported": {"en": "Graphs exported", "fr": "Graphes exportés", "nl": "Grafieken geëxporteerd"},
    "loading_file": {"en": "Loading", "fr": "Chargement", "nl": "Laden"},
    "no_serial_port": {
        "en": "No serial port configured",
        "fr": "Aucun port série configuré",
    "nl": "Geen seriële poort ingesteld",
},
    "no_ascom_driver": {
        "en": "No ASCOM driver selected",
        "fr": "Aucun driver ASCOM sélectionné",
    "nl": "Geen ASCOM-driver geselecteerd",
},
    "protocol_not_impl": {
        "en": "Protocol not yet implemented",
        "fr": "Protocole non implémenté",
    "nl": "Protocol nog niet geïmplementeerd",
},
    "parked_auto_analysis": {
        "en": "Mount parked — automatic night analysis...",
        "fr": "Monture parquée — analyse automatique de la nuit...",
    "nl": "Montering geparkeerd — automatische nachtanalyse...",
},
    "dump_graphs_action": {"en": "Dump Graphs", "fr": "Exporter graphes", "nl": "Grafieken exporteren"},

    # Graph labels
    "deviation": {"en": "Deviation", "fr": "Déviation", "nl": "Afwijking"},
    "time_label": {"en": "Time", "fr": "Temps", "nl": "Tijd"},
    "time_graph_title": {
        "en": "TIME — PC vs Mount Clock",
        "fr": "TEMPS — PC vs Horloge monture",
    "nl": "TIJD — Pc vs. klok montering",
},
    "time_diff": {"en": "Time diff", "fr": "Diff. temps", "nl": "Tijdverschil"},
    "seismic_title": {
        "en": "SEISMIC — Vibrations",
        "fr": "SISMIQUE — Vibrations",
    "nl": "SEISMISCH — Trillingen",
},
    "amplitude": {"en": "Amplitude", "fr": "Amplitude", "nl": "Amplitude"},
    "axial_title": {
        "en": "AXIAL — Speed / Displacement",
        "fr": "AXIAL — Vitesse / Déplacement",
    "nl": "AXIAAL — Snelheid / Verplaatsing",
},
    "speed_label": {"en": "Speed", "fr": "Vitesse", "nl": "Snelheid"},
    "frequency_label": {"en": "Frequency", "fr": "Fréquence", "nl": "Frequentie"},
    "period_label": {"en": "Period", "fr": "Période", "nl": "Periode"},

    # Preferences combobox items
    "ref_median": {"en": "Median", "fr": "Médiane", "nl": "Mediaan"},
    "ref_target": {
        "en": "Mount target coordinates",
        "fr": "Coordonnées cible monture",
    "nl": "Doelcoördinaten montering",
},
    "log_all": {"en": "All", "fr": "Tout", "nl": "Alles"},
    "log_tracking_only": {
        "en": "Only when tracking",
        "fr": "Suivi uniquement",
    "nl": "Alleen tijdens volgen",
},
    "axial_off": {"en": "Off", "fr": "Désactivé", "nl": "Uit"},
    "axial_velocity": {"en": "Axial velocity", "fr": "Vitesse axiale", "nl": "Axiale snelheid"},
    "axial_displacement": {
        "en": "Axial displacement",
        "fr": "Déplacement axial",
    "nl": "Axiale verplaatsing",
},
    "mode_manual": {"en": "Manual", "fr": "Manuel", "nl": "Handmatig"},
    "mode_slewing": {"en": "When slewing", "fr": "En pointage", "nl": "Bij het zwenken"},
    "mode_parking": {"en": "When parking", "fr": "Au parcage", "nl": "Bij het parkeren"},
    "mode_full": {"en": "When the graph fills", "fr": "Quand le graphe est plein", "nl": "Wanneer de grafiek vol is"},

    # Mount checks labels
    "check_refraction_label": {
        "en": "Check refraction correction",
        "fr": "Vérifier correction réfraction",
    "nl": "Refractiecorrectie controleren",
},
    "check_tracking_label": {
        "en": "Check tracking rate",
        "fr": "Vérifier vitesse de suivi",
    "nl": "Volgsnelheid controleren",
},
    "check_gps_label": {
        "en": "Check GPS sync",
        "fr": "Vérifier synchro GPS",
    "nl": "GPS-synchronisatie controleren",
},
    "check_dual_label": {
        "en": "Check dual tracking",
        "fr": "Vérifier suivi dual",
    "nl": "Dubbele tracking controleren",
},
    "refraction_not_updating": {
        "en": "Not updating",
        "fr": "Pas de mise à jour",
    "nl": "Wordt niet bijgewerkt",
},
    "refraction_not_tracking": {
        "en": "Not updating while tracking",
        "fr": "Pas de maj en suivi",
    "nl": "Wordt niet bijgewerkt tijdens volgen",
},
    "refraction_continuous": {
        "en": "Continuously updating",
        "fr": "Mise à jour continue",
    "nl": "Wordt continu bijgewerkt",
},

    # Tooltips
    "tt_connect": {
        "en": "Connect to the telescope mount",
        "fr": "Se connecter à la monture du télescope",
    "nl": "Verbinding maken met de montering",
},
    "tt_disconnect": {
        "en": "Disconnect from the mount",
        "fr": "Se déconnecter de la monture",
    "nl": "Verbinding met de montering verbreken",
},
    "tt_start_logging": {
        "en": "Start recording data to log files",
        "fr": "Démarrer l'enregistrement des données",
    "nl": "Beginnen met het opnemen van gegevens",
},
    "tt_stop_logging": {
        "en": "Stop recording data",
        "fr": "Arrêter l'enregistrement",
    "nl": "Stoppen met opnemen",
},
    "tt_fft": {
        "en": "Open FFT analysis window",
        "fr": "Ouvrir la fenêtre d'analyse FFT",
    "nl": "Het FFT-analysevenster openen",
},
    "tt_preferences": {
        "en": "Open preferences dialog",
        "fr": "Ouvrir les préférences",
    "nl": "Het voorkeurenvenster openen",
},
}


# Supported languages, in the order they appear in Preferences.
# Dutch is there because MountMonitor started as a Dutch program: the original
# v3.37 is by Nicolàs de Hilster (Starmountain Survey & Consultancy BV).
LANGUES = {
    'en': "English",
    'fr': "Français",
    'nl': "Nederlands",
}
LANGUE_DEFAUT = 'en'


def detect_language() -> str:
    """System language, restricted to what we actually translate.

    ``locale.getdefaultlocale`` is deprecated since Python 3.11 and removed in
    3.13, and on Windows it returns the *format* locale rather than the display
    language. We therefore try, in order: the usual environment variables (which
    Linux and macOS honour), then the Windows display language, then the format
    locale as a last resort.
    """
    codes = []
    try:
        import os
        for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            val = os.environ.get(var)
            if val:
                codes.extend(val.replace(':', ',').split(','))
    except Exception:
        pass
    try:  # Windows display language, which is what the user actually reads
        import ctypes
        nom = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        codes.append(locale.windows_locale.get(nom, ''))
    except Exception:
        pass
    try:
        codes.append(locale.setlocale(locale.LC_CTYPE) or '')
    except Exception:
        pass
    try:  # removed in Python 3.13, kept for older interpreters
        codes.append((locale.getdefaultlocale() or ('',))[0] or '')
    except Exception:
        pass

    for code in codes:
        code = (code or '').strip().lower().replace('-', '_')
        if not code or code in ('c', 'posix'):
            continue
        racine = code.split('_')[0].split('.')[0]
        if racine in LANGUES:
            return racine
    return LANGUE_DEFAUT


def set_language(lang: str):
    """Set the current language: a code from LANGUES, or 'auto'."""
    global _current_lang
    if lang == 'auto':
        _current_lang = detect_language()
    elif lang in LANGUES:
        _current_lang = lang
    else:
        # An unknown code must not leave the interface half-translated.
        _current_lang = LANGUE_DEFAUT


def get_language() -> str:
    """Get the current language code."""
    return _current_lang


def T(key: str, lang: str | None = None) -> str:
    """Translate a key, falling back to English then to the key itself.

    A missing translation shows the English text, never an empty label: an
    untranslated string is a cosmetic flaw, a blank button is a broken program.
    """
    l = lang or _current_lang
    entry = TX.get(key)
    if entry is None:
        return key
    valeur = entry.get(l)
    if valeur:
        return valeur
    return entry.get(LANGUE_DEFAUT) or key


def langues_disponibles() -> dict:
    """Code -> native name, for the Preferences dialog."""
    return dict(LANGUES)


# Auto-detect on import
set_language('auto')
