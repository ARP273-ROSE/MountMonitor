"""Internationalization system for MountMonitor. Bilingual FR/EN."""

import locale

_current_lang = "en"

# Translation dictionary: key -> {en: ..., fr: ...}
TX = {
    # Main window
    "app_title": {"en": "MountMonitor", "fr": "MountMonitor"},
    "menu_file": {"en": "File", "fr": "Fichier"},
    "menu_edit": {"en": "Edit", "fr": "Édition"},
    "menu_view": {"en": "View", "fr": "Affichage"},
    "menu_reset": {"en": "Reset", "fr": "Réinitialiser"},
    "menu_help": {"en": "Help", "fr": "Aide"},
    "menu_preferences": {"en": "Preferences", "fr": "Préférences"},
    "menu_quit": {"en": "Quit", "fr": "Quitter"},
    "menu_about": {"en": "About", "fr": "À propos"},
    "menu_help_contents": {"en": "Help Contents", "fr": "Contenu de l'aide"},
    "menu_online_help": {"en": "Online Help", "fr": "Aide en ligne"},
    "menu_report_bug": {"en": "Report a Bug", "fr": "Signaler un bug"},

    # Connection
    "connecting": {"en": "Connecting...", "fr": "Connexion..."},
    "connected": {"en": "Connected", "fr": "Connecté"},
    "disconnected": {"en": "Disconnected", "fr": "Déconnecté"},
    "connection_failed": {"en": "Connection failed", "fr": "Échec de connexion"},
    "connection_restored": {"en": "Connection restored", "fr": "Connexion restaurée"},
    "reconnecting": {"en": "Reconnecting...", "fr": "Reconnexion..."},

    # Mount status
    "mount_tracking": {"en": "The mount is tracking", "fr": "La monture est en suivi"},
    "mount_slewing": {"en": "The mount is slewing", "fr": "La monture pivote"},
    "mount_parked": {"en": "The mount is parked", "fr": "La monture est parquée"},
    "mount_idle": {"en": "The mount is idle", "fr": "La monture est au repos"},

    # Graphs
    "right_ascension": {"en": "RIGHT ASCENSION", "fr": "ASCENSION DROITE"},
    "declination": {"en": "DECLINATION", "fr": "DÉCLINAISON"},
    "seismic": {"en": "SEISMIC", "fr": "SISMIQUE"},
    "time_graph": {"en": "TIME", "fr": "TEMPS"},
    "ra_short": {"en": "RA", "fr": "AD"},
    "dec_short": {"en": "DEC", "fr": "DÉC"},

    # Statistics
    "stdev": {"en": "STDEV", "fr": "ÉCART-TYPE"},
    "min_value": {"en": "Min", "fr": "Min"},
    "max_value": {"en": "Max", "fr": "Max"},
    "range_value": {"en": "Range", "fr": "Plage"},
    "tolerance": {"en": "Tolerance", "fr": "Tolérance"},
    "tolerance_exceeded": {"en": "Tolerance exceeded!", "fr": "Tolérance dépassée !"},
    "tolerance_ok": {"en": "Within tolerance", "fr": "Dans la tolérance"},

    # FFT
    "fft_title": {"en": "FFT Analysis", "fr": "Analyse FFT"},
    "frequency_domain": {"en": "Frequency Domain", "fr": "Domaine fréquentiel"},
    "period_domain": {"en": "Period Domain", "fr": "Domaine temporel"},

    # Preferences
    "pref_general": {"en": "General", "fr": "Général"},
    "pref_processing": {"en": "Processing", "fr": "Traitement"},
    "pref_auxiliary": {"en": "Auxiliary", "fr": "Auxiliaire"},
    "pref_misc": {"en": "Miscellaneous", "fr": "Divers"},
    "pref_observatory": {"en": "Observatory name", "fr": "Nom de l'observatoire"},
    "pref_mount_name": {"en": "Mount name", "fr": "Nom de la monture"},
    "pref_mount_ip": {"en": "Mount IP address", "fr": "Adresse IP de la monture"},
    "pref_mount_port": {"en": "Mount port", "fr": "Port de la monture"},
    "pref_protocol": {"en": "Protocol", "fr": "Protocole"},
    "pref_polling": {"en": "Polling frequency (Hz)", "fr": "Fréquence d'interrogation (Hz)"},
    "pref_running_range": {"en": "Running range (s)", "fr": "Plage glissante (s)"},
    "pref_reference": {"en": "Reference", "fr": "Référence"},
    "pref_tolerance_ra": {"en": "RA tolerance (arcsec)", "fr": "Tolérance AD (arcsec)"},
    "pref_tolerance_dec": {"en": "DEC tolerance (arcsec)", "fr": "Tolérance DÉC (arcsec)"},
    "pref_log_mode": {"en": "Logging", "fr": "Journalisation"},
    "pref_ntp_enabled": {"en": "Use NTP server", "fr": "Utiliser un serveur NTP"},
    "pref_ntp_server": {"en": "NTP server address", "fr": "Adresse du serveur NTP"},
    "pref_seismometer": {"en": "Seismometer", "fr": "Sismomètre"},
    "pref_mount_checks": {"en": "Mount checks", "fr": "Vérifications monture"},
    "pref_connection": {"en": "Connection", "fr": "Connexion"},
    "pref_layout": {"en": "Layout", "fr": "Mise en page"},
    "pref_graph_ratio": {"en": "Graph:Textbox ratio", "fr": "Ratio graphe:texte"},
    "pref_polling_group": {"en": "Polling", "fr": "Acquisition"},
    "pref_correct_graphs": {"en": "Correct graphs for range", "fr": "Corriger graphes pour la plage"},
    "pref_log_mode_label": {"en": "Mode", "fr": "Mode"},
    "pref_delay_slew": {"en": "Delay after slew (s)", "fr": "Délai après pointage (s)"},
    "pref_axial_mode": {"en": "Axial mode", "fr": "Mode axial"},
    "pref_ntp_group": {"en": "NTP Time Server", "fr": "Serveur NTP"},
    "pref_ntp_interval": {"en": "Interval (s)", "fr": "Intervalle (s)"},
    "pref_sei_offset": {"en": "Offset", "fr": "Décalage"},
    "pref_show_ra_ha": {"en": "Show RA as HA [s]", "fr": "AD en HA [s]"},
    "pref_ascom_driver": {"en": "ASCOM Driver", "fr": "Pilote ASCOM"},
    "pref_reset_mode": {"en": "Reset mode", "fr": "Mode réinitialisation"},
    "pref_dump_graphs": {"en": "Dump graphs", "fr": "Export graphes"},
    "pref_close_files": {"en": "Close files", "fr": "Fermer fichiers"},
    "pref_tolerance_seismic": {"en": "Seismic tolerance (%)", "fr": "Tolérance sismique (%)"},
    "pref_history_lines": {"en": "History lines", "fr": "Lignes d'historique"},
    "pref_expected_value": {"en": "Expected value", "fr": "Valeur attendue"},
    "pref_serial_port": {"en": "Serial port", "fr": "Port série"},
    "pref_select_ascom": {"en": "Select...", "fr": "Sélectionner..."},
    "pref_language": {"en": "Language", "fr": "Langue"},
    "pref_enable": {"en": "Enable", "fr": "Activer"},
    "pref_frequency": {"en": "Frequency (Hz)", "fr": "Fréquence (Hz)"},
    "pref_range": {"en": "Range", "fr": "Plage"},

    # Logging
    "logging_started": {"en": "Logging started", "fr": "Journalisation démarrée"},
    "logging_stopped": {"en": "Logging stopped", "fr": "Journalisation arrêtée"},
    "new_log_files": {"en": "New log files created", "fr": "Nouveaux fichiers log créés"},

    # Log replay & analysis
    "menu_open_log": {"en": "Open Log...", "fr": "Ouvrir un log..."},
    "menu_open_log10m": {"en": "Analyze Mount Logs (.log10m)...", "fr": "Analyser logs monture (.log10m)..."},
    "open_log_title": {"en": "Open Log File", "fr": "Ouvrir un fichier log"},
    "replay_loaded": {
        "en": "Log loaded: {samples} samples, duration {duration}",
        "fr": "Log chargé : {samples} échantillons, durée {duration}",
    },
    "replay_no_data": {
        "en": "No data found in this log file",
        "fr": "Aucune donnée trouvée dans ce fichier log",
    },
    "replay_mode": {"en": "REPLAY MODE", "fr": "MODE RELECTURE"},
    "analysis_complete": {
        "en": "Analysis complete",
        "fr": "Analyse terminée",
    },

    # Zoom
    "horizontal_zoom": {"en": "Horizontal Zoom", "fr": "Zoom horizontal"},
    "vertical_zoom": {"en": "Vertical Zoom", "fr": "Zoom vertical"},
    "zoom_data": {"en": "Data (median centred)", "fr": "Données (centré médiane)"},
    "zoom_tolerance": {"en": "Tolerance", "fr": "Tolérance"},
    "zoom_maximum": {"en": "Maximum (data/tolerance)", "fr": "Maximum (données/tolérance)"},
    "zoom_minmax": {"en": "Min/Max value lines", "fr": "Lignes Min/Max"},

    # Reset
    "reset_minmax": {"en": "Reset Min/Max", "fr": "Réinitialiser Min/Max"},
    "reset_buffers": {"en": "Reset Buffers", "fr": "Réinitialiser les tampons"},
    "reset_both": {"en": "Reset Buffers and Min/Max", "fr": "Réinitialiser tampons et Min/Max"},
    "reset_new_files": {"en": "New Files", "fr": "Nouveaux fichiers"},

    # Simulation
    "sim_mount": {"en": "Mount simulation active", "fr": "Simulation monture active"},
    "sim_seismometer": {"en": "Seismometer simulation active", "fr": "Simulation sismomètre active"},
    "sim_all": {"en": "Full simulation mode", "fr": "Mode simulation complète"},

    # Auto-update
    "update_available": {"en": "Update available", "fr": "Mise à jour disponible"},
    "update_current": {"en": "Current version", "fr": "Version actuelle"},
    "update_new": {"en": "New version", "fr": "Nouvelle version"},
    "update_download": {"en": "Download", "fr": "Télécharger"},
    "update_skip": {"en": "Skip", "fr": "Ignorer"},
    "update_checking": {"en": "Checking for updates...", "fr": "Vérification des mises à jour..."},
    "update_up_to_date": {"en": "You are up to date", "fr": "Vous êtes à jour"},

    # Status panel labels
    "label_ra": {"en": "RA:", "fr": "AD :"},
    "label_dec": {"en": "DEC:", "fr": "DÉC :"},
    "samples": {"en": "samples", "fr": "échantillons"},
    "error_status": {"en": "Error", "fr": "Erreur"},

    # Buttons
    "btn_connect": {"en": "Connect", "fr": "Connecter"},
    "btn_disconnect": {"en": "Disconnect", "fr": "Déconnecter"},
    "btn_start_log": {"en": "Start Log", "fr": "Démarrer log"},
    "btn_stop_log": {"en": "Stop Log", "fr": "Arrêter log"},

    # Messages
    "graphs_exported": {"en": "Graphs exported", "fr": "Graphes exportés"},
    "loading_file": {"en": "Loading", "fr": "Chargement"},
    "no_serial_port": {
        "en": "No serial port configured",
        "fr": "Aucun port série configuré",
    },
    "no_ascom_driver": {
        "en": "No ASCOM driver selected",
        "fr": "Aucun driver ASCOM sélectionné",
    },
    "protocol_not_impl": {
        "en": "Protocol not yet implemented",
        "fr": "Protocole non implémenté",
    },
    "parked_auto_analysis": {
        "en": "Mount parked — automatic night analysis...",
        "fr": "Monture parquée — analyse automatique de la nuit...",
    },
    "dump_graphs_action": {"en": "Dump Graphs", "fr": "Exporter graphes"},

    # Graph labels
    "deviation": {"en": "Deviation", "fr": "Déviation"},
    "time_label": {"en": "Time", "fr": "Temps"},
    "time_graph_title": {
        "en": "TIME — PC vs Mount Clock",
        "fr": "TEMPS — PC vs Horloge monture",
    },
    "time_diff": {"en": "Time diff", "fr": "Diff. temps"},
    "seismic_title": {
        "en": "SEISMIC — Vibrations",
        "fr": "SISMIQUE — Vibrations",
    },
    "amplitude": {"en": "Amplitude", "fr": "Amplitude"},
    "axial_title": {
        "en": "AXIAL — Speed / Displacement",
        "fr": "AXIAL — Vitesse / Déplacement",
    },
    "speed_label": {"en": "Speed", "fr": "Vitesse"},
    "frequency_label": {"en": "Frequency", "fr": "Fréquence"},
    "period_label": {"en": "Period", "fr": "Période"},

    # Preferences combobox items
    "ref_median": {"en": "Median", "fr": "Médiane"},
    "ref_target": {
        "en": "Mount target coordinates",
        "fr": "Coordonnées cible monture",
    },
    "log_all": {"en": "All", "fr": "Tout"},
    "log_tracking_only": {
        "en": "Only when tracking",
        "fr": "Suivi uniquement",
    },
    "axial_off": {"en": "Off", "fr": "Désactivé"},
    "axial_velocity": {"en": "Axial velocity", "fr": "Vitesse axiale"},
    "axial_displacement": {
        "en": "Axial displacement",
        "fr": "Déplacement axial",
    },
    "mode_manual": {"en": "Manual", "fr": "Manuel"},
    "mode_slewing": {"en": "When slewing", "fr": "En pointage"},
    "mode_parking": {"en": "When parking", "fr": "Au parcage"},

    # Mount checks labels
    "check_refraction_label": {
        "en": "Check refraction correction",
        "fr": "Vérifier correction réfraction",
    },
    "check_tracking_label": {
        "en": "Check tracking rate",
        "fr": "Vérifier vitesse de suivi",
    },
    "check_gps_label": {
        "en": "Check GPS sync",
        "fr": "Vérifier synchro GPS",
    },
    "check_dual_label": {
        "en": "Check dual tracking",
        "fr": "Vérifier suivi dual",
    },
    "refraction_not_updating": {
        "en": "Not updating",
        "fr": "Pas de mise à jour",
    },
    "refraction_not_tracking": {
        "en": "Not updating while tracking",
        "fr": "Pas de maj en suivi",
    },
    "refraction_continuous": {
        "en": "Continuously updating",
        "fr": "Mise à jour continue",
    },

    # Tooltips
    "tt_connect": {
        "en": "Connect to the telescope mount",
        "fr": "Se connecter à la monture du télescope"
    },
    "tt_disconnect": {
        "en": "Disconnect from the mount",
        "fr": "Se déconnecter de la monture"
    },
    "tt_start_logging": {
        "en": "Start recording data to log files",
        "fr": "Démarrer l'enregistrement des données"
    },
    "tt_stop_logging": {
        "en": "Stop recording data",
        "fr": "Arrêter l'enregistrement"
    },
    "tt_fft": {
        "en": "Open FFT analysis window",
        "fr": "Ouvrir la fenêtre d'analyse FFT"
    },
    "tt_preferences": {
        "en": "Open preferences dialog",
        "fr": "Ouvrir les préférences"
    },
}


def detect_language() -> str:
    """Detect system language. Returns 'fr' or 'en'."""
    try:
        lang = locale.getdefaultlocale()[0]
        if lang and lang.startswith('fr'):
            return 'fr'
    except Exception:
        pass
    return 'en'


def set_language(lang: str):
    """Set the current language ('fr', 'en', or 'auto')."""
    global _current_lang
    if lang == 'auto':
        _current_lang = detect_language()
    else:
        _current_lang = lang


def get_language() -> str:
    """Get the current language code."""
    return _current_lang


def T(key: str, lang: str | None = None) -> str:
    """Translate a key to the current (or specified) language."""
    l = lang or _current_lang
    entry = TX.get(key)
    if entry is None:
        return key
    return entry.get(l, entry.get('en', key))


# Auto-detect on import
set_language('auto')
