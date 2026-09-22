#!/usr/bin/env python3
"""MountMonitor - Modern telescope mount monitoring for astrophotography.

Modernized rewrite of MountMonitor v3.37 (Java) by Nicolàs de Hilster.
Now in Python/PyQt6/pyqtgraph with dark astronomy theme.

Usage:
    python main.py                    # Normal mode (requires mount)
    python main.py --sim-mount        # Simulate mount
    python main.py --sim-seismometer  # Simulate seismometer
    python main.py --sim-all          # Simulate everything (demo mode)
"""

import sys
import os
import logging
import argparse
from pathlib import Path

# Ensure the project root is in the path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))


def setup_logging(log_level: str = "INFO"):
    """Configure application logging."""
    from src.config.paths import dossier_journaux
    log_dir = dossier_journaux()
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.handlers.RotatingFileHandler(
                log_dir / "mountmonitor_app.log",
                maxBytes=500 * 1024,  # 500KB
                backupCount=3,
                encoding='utf-8',
            ),
        ],
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MountMonitor - Real-time telescope mount monitoring"
    )
    parser.add_argument(
        '--sim-mount', action='store_true',
        help='Simulate mount connection (for testing)'
    )
    parser.add_argument(
        '--sim-seismometer', action='store_true',
        help='Simulate seismometer data (for testing)'
    )
    parser.add_argument(
        '--sim-all', action='store_true',
        help='Simulate everything (demo mode)'
    )
    parser.add_argument(
        '--log-level', default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    return parser.parse_args()


_FICHIER_CRASH_NATIF = "_crash_natif.log"
_vigie = None


def _initialiser_les_rapports():
    """Prepare la remontee des incidents, et ramasse ceux du dernier depart.

    Trois choses se jouent ici :

      - `relever_crash_natif` lit la trace laissee par un plantage qui n'a pas
        produit d'exception Python — une faute de segmentation dans Qt, par
        exemple. Sans elle, ce genre de mort ne laisse rien du tout ;
      - la file d'attente est reprise : un rapport ecrit alors que la maison
        n'avait pas de reseau part au prochain lancement ;
      - le gestionnaire d'exceptions envoie ce qui n'a pas ete rattrape.

    Tout est suspendu au consentement, demande une fois, apres l'ouverture de
    la fenetre : tant qu'il n'a pas ete donne, rien ne sort de la machine.
    """
    global _vigie
    try:
        import reporting
        from src.config.paths import dossier_donnees
    except Exception:
        logging.getLogger(__name__).debug("Rapports indisponibles", exc_info=True)
        return

    donnees = dossier_donnees()
    reporting.init(donnees)

    # Trace des plantages sans exception : elle s'ecrit au fil de l'eau dans
    # un fichier, releve au demarrage suivant.
    chemin_natif = donnees / _FICHIER_CRASH_NATIF
    try:
        import faulthandler
        _initialiser_les_rapports._fichier = open(chemin_natif, 'w', encoding='utf-8')
        faulthandler.enable(file=_initialiser_les_rapports._fichier, all_threads=True)
    except Exception:
        logging.getLogger(__name__).debug("faulthandler indisponible", exc_info=True)

    try:
        reporting.relever_crash_natif(chemin_natif)
        reporting.reprendre_file_en_fond()
    except Exception:
        logging.getLogger(__name__).debug("File des rapports non reprise", exc_info=True)

    # Vigie anti-gel : un minuteur bat sur le fil graphique, un fil de fond
    # regarde l'heure. Si le battement s'arrete, la fenetre est figee, et la
    # pile du fil graphique dit alors quelle operation n'a pas ete deportee.
    # Sans cela un gel ne laisse aucune trace : on tue l'application et on ne
    # peut rien en dire.
    try:
        _vigie = reporting.Vigie(seuil=10.0, periode=2.0)
        _vigie.demarrer()
    except Exception:
        logging.getLogger(__name__).debug("Vigie non demarree", exc_info=True)


def _demander_accord_rapports(fenetre):
    """Pose la question une seule fois, puis signale le demarrage."""
    try:
        import reporting
    except Exception:
        return
    try:
        if reporting.consentement() is None:
            from PyQt6.QtWidgets import QMessageBox
            boite = QMessageBox(fenetre)
            boite.setWindowTitle("MountMonitor")
            boite.setIcon(QMessageBox.Icon.Question)
            boite.setText("Autoriser MountMonitor a signaler ses problemes ?\n"
                          "Allow MountMonitor to report its own problems?")
            boite.setInformativeText(
                "Si l'application plante, se fige ou refuse de demarrer, elle "
                "peut l'annoncer toute seule a celui qui la maintient. Vous "
                "n'aurez rien a faire, et rien d'autre n'est envoye : ni vos "
                "donnees de suivi, ni vos noms de fichiers, ni votre nom "
                "d'utilisateur.\n\n"
                "If the application crashes, freezes or fails to start, it can "
                "report it by itself. Nothing else is ever sent.")
            oui = boite.addButton("Autoriser / Allow",
                                  QMessageBox.ButtonRole.AcceptRole)
            boite.addButton("Non merci / No thanks",
                            QMessageBox.ButtonRole.RejectRole)
            boite.exec()
            reporting.definir_consentement(boite.clickedButton() is oui)
        reporting.signaler_demarrage()
    except Exception:
        logging.getLogger(__name__).debug("Accord non demande", exc_info=True)


def main():
    """Application entry point."""
    # Need to import logging.handlers before setup
    import logging.handlers

    args = parse_args()
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("MountMonitor starting...")

    # Determine simulation mode
    if args.sim_all:
        sim_mode = "all"
    elif args.sim_mount:
        sim_mode = "mount"
    elif args.sim_seismometer:
        sim_mode = "seismometer"
    else:
        sim_mode = "none"

    if sim_mode != "none":
        logger.info(f"Simulation mode: {sim_mode}")

    # Create Qt application
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("MountMonitor")
    app.setOrganizationName("ARP273")

    # Une seule instance a la fois. Deux copies qui interrogent la meme monture
    # sur le meme port LX200, c'est deux flots de commandes entrelaces : la
    # monture repond a l'une ce que l'autre attendait.
    from PyQt6.QtCore import QLockFile, QDir
    _verrou = QLockFile(str(Path(QDir.tempPath()) / 'mountmonitor.lock'))
    _verrou.setStaleLockTime(30000)
    if not _verrou.tryLock(200):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "MountMonitor",
            "MountMonitor est deja ouvert.\n"
            "MountMonitor is already running.\n\n"
            "Regardez dans la barre des taches : la fenetre est sans doute "
            "derriere une autre.")
        return 0
    app._verrou_instance = _verrou

    # Verrou nomme, lisible par l'installeur (AppMutex dans installer.iss).
    # QLockFile ne se voit que depuis Qt : sans celui-ci, installer une
    # nouvelle version par-dessus l'application ouverte ne remplace pas les
    # fichiers en cours d'utilisation, et se termine pourtant en annoncant
    # « termine ».
    if sys.platform == 'win32':
        try:
            import ctypes
            app._mutex_installeur = ctypes.windll.kernel32.CreateMutexW(
                None, False, 'MountMonitorEnCours')
        except Exception:
            logger.debug("Verrou nomme non pose", exc_info=True)

    # Remontee des incidents. Initialisee avant tout le reste : ce qui nous
    # interesse le plus, ce sont justement les demarrages qui n'aboutissent pas.
    _initialiser_les_rapports()

    # Apply dark theme
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)

    # Install crash reporter
    from src.logging_module.crash_reporter import CrashReporter
    from src.config.paths import dossier_donnees
    crash_reporter = CrashReporter(dossier_donnees())
    crash_reporter.install()

    # Check for previous crash — offer to report on GitHub
    if crash_reporter.has_crash_report():
        report = crash_reporter.get_crash_report()
        if report:
            from PyQt6.QtWidgets import QMessageBox
            from src.logging_module.crash_reporter import anonymize_path, GITHUB_REPO

            exc_type = report.get('exception_type', 'Unknown')
            exc_msg = anonymize_path(report.get('exception_message', ''))

            msg = QMessageBox()
            msg.setWindowTitle("Crash Report / Rapport de crash")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(
                "MountMonitor crashed during the last session.\n"
                "MountMonitor a planté lors de la dernière session.\n\n"
                f"Error: {exc_type}\n{exc_msg}"
            )
            msg.setInformativeText(
                "Would you like to report this crash on GitHub?\n"
                "Voulez-vous signaler ce crash sur GitHub ?\n\n"
                "(All paths are anonymized / Tous les chemins sont anonymisés)"
            )

            send_btn = msg.addButton(
                "Report on GitHub / Signaler",
                QMessageBox.ButtonRole.AcceptRole,
            )
            dismiss_btn = msg.addButton(
                "Dismiss / Ignorer",
                QMessageBox.ButtonRole.RejectRole,
            )
            msg.exec()

            if msg.clickedButton() == send_btn:
                import webbrowser
                from urllib.parse import quote
                body = crash_reporter.format_github_issue(report)
                title = quote(f"Crash: {exc_type}", safe='')
                encoded_body = quote(body, safe='')
                url = (
                    f"https://github.com/{GITHUB_REPO}/issues/new"
                    f"?title={title}&body={encoded_body}"
                )
                webbrowser.open(url)

        crash_reporter.clear_crash_report()

    # Inventaire de la machine : en fil de fond, apres l'affichage.
    #
    # Sous Windows il repose sur quatre appels a `wmic`, chacun avec cinq
    # secondes d'attente maximum. Lances ici, avant la creation de la
    # fenetre, ils retardaient l'ouverture d'autant — ecran noir, sans un
    # mot. Et `wmic` a ete retire des versions recentes de Windows : sur ces
    # machines les quatre appels echouent, apres avoir coute le lancement de
    # quatre processus.
    #
    # Le resultat ne sert qu'a une ligne de journal. Il n'a aucune raison de
    # retenir l'affichage.
    def _inventorier():
        try:
            from src.utils.hardware_detect import detect_hardware
            hw = detect_hardware()
            logger.info(f"Hardware: {hw.cpu_name}, {hw.cpu_cores_physical} cores, "
                        f"{hw.ram_total_mb}MB RAM, GPU: {hw.gpu_name}")
        except Exception:
            logger.debug("Inventaire de la machine indisponible", exc_info=True)

    import threading
    threading.Thread(target=_inventorier, daemon=True,
                     name='inventaire-machine').start()

    # Create and show main window
    from src.gui.main_window import MainWindow
    window = MainWindow(sim_mode=sim_mode)
    window.show()

    # Offer desktop shortcut on first launch
    from src.config.settings import Settings
    _settings = Settings()
    from shortcut_helper import offer_shortcut
    offer_shortcut("MountMonitor", "main.py", "logo.ico",
                   get_config=lambda k: _settings.get(k),
                   set_config=lambda k, v: (_settings.set(k, v), _settings.save()))

    _demander_accord_rapports(window)

    logger.info("MountMonitor ready")
    code = app.exec()

    # Sortie immediate, sans demontage de l'interpreteur.
    #
    # Une fois la boucle terminee, Python detruit ses objets dans un ordre que
    # Qt ne supporte pas : la bibliotheque graphique est liberee pendant que
    # des objets s'y referent encore, et le processus meurt d'une faute de
    # segmentation. Sous Windows cela donne « le logiciel a cesse de
    # fonctionner » au moment ou l'on ferme la fenetre — signale comme un
    # plantage, alors que tout le travail est fait. Les fichiers de session
    # sont fermes par la fenetre elle-meme avant d'en arriver la.
    try:
        if _vigie is not None:
            _vigie.arreter()
    except Exception:
        pass
    try:
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
