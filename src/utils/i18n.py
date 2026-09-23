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
        "en": "Mount parked: recording stopped and night report written.",
        "fr": "Monture parquée : enregistrement arrêté et rapport de nuit écrit.",
        "nl": "Montering geparkeerd: registratie gestopt en nachtrapport geschreven."},
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
