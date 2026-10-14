# -*- coding: utf-8 -*-
"""Menu Aide branché sur le kit commun : manuel PDF, mises à jour, rapports.

Ce module relie la fenêtre principale aux fichiers du kit (`updater.py`,
`reporting.py`, `interface_kit.py`), qui ne connaissent pas l'interface :

* **Manuel (PDF)** dans la langue de l'interface (`docs/manuel-fr.pdf`,
  `docs/manuel-en.pdf`), ouvert avec la visionneuse du système ;
* **Rechercher des mises à jour** : silencieusement 3 s après l'ouverture
  pour une application installée, et sur demande ; l'archive est posée par
  `updater.download_and_apply` puis l'application redémarre. Depuis les
  sources, on n'ouvre que la page de téléchargement ;
* **Signaler un problème…** et la case **Envoyer automatiquement les
  rapports** ; l'accord est demandé au premier lancement.

Les fils de fond ne touchent jamais Qt : le résultat revient par un signal,
la progression par un dictionnaire relu à 10 Hz.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel,
                             QMessageBox, QPlainTextEdit, QProgressDialog,
                             QVBoxLayout)

log = logging.getLogger(__name__)

#: textes du module, par langue (fr, en, et nl pour les applications qui le parlent)
TEXTES = {
    'manuel': {'fr': "&Manuel (PDF)", 'en': "&Manual (PDF)", 'nl': "&Handleiding (PDF)"},
    'manuel_absent': {
        'fr': "Le manuel PDF est introuvable dans le dossier de l'application.",
        'en': "The PDF manual could not be found in the application folder.",
        'nl': "De PDF-handleiding is niet gevonden in de programmamap."},
    'maj': {'fr': "Rechercher des &mises à jour...", 'en': "Check for &updates...",
            'nl': "Naar &updates zoeken..."},
    'signaler': {'fr': "&Signaler un problème...", 'en': "&Report a problem...",
                 'nl': "&Probleem melden..."},
    'auto': {'fr': "Envoyer automatiquement les rapports d'incident",
             'en': "Send crash reports automatically",
             'nl': "Foutrapporten automatisch versturen"},
    'maj_titre': {'fr': "Mise à jour", 'en': "Update", 'nl': "Update"},
    'maj_recherche': {'fr': "Recherche de mises à jour...", 'en': "Checking for updates...",
                      'nl': "Zoeken naar updates..."},
    'maj_a_jour': {'fr': "Vous avez la dernière version ({v}).",
                   'en': "You have the latest version ({v}).",
                   'nl': "U hebt de nieuwste versie ({v})."},
    'maj_dispo': {'fr': "La version {v} est disponible (vous avez la {c}).",
                  'en': "Version {v} is available (you have {c}).",
                  'nl': "Versie {v} is beschikbaar (u hebt {c})."},
    'maj_installer': {'fr': "Installer et redémarrer", 'en': "Install and restart",
                      'nl': "Installeren en herstarten"},
    'maj_page': {'fr': "Ouvrir la page de téléchargement", 'en': "Open the download page",
                 'nl': "Downloadpagina openen"},
    'maj_sources': {
        'fr': "Cette copie tourne depuis les sources : la mise à jour automatique "
              "ne concerne que l'application installée.",
        'en': "This copy runs from source: automatic updates only apply to the "
              "installed application.",
        'nl': "Deze kopie draait vanaf de broncode: automatische updates gelden "
              "alleen voor de geïnstalleerde toepassing."},
    'maj_plus_tard': {'fr': "Plus tard", 'en': "Later", 'nl': "Later"},
    'maj_telechargement': {'fr': "Téléchargement de la mise à jour...",
                           'en': "Downloading the update...", 'nl': "Update downloaden..."},
    'maj_verrou': {
        'fr': "Un fichier de l'application est utilisé par un autre programme. "
              "Fermez les autres fenêtres de l'application et réessayez.",
        'en': "An application file is in use by another program. Close the "
              "application's other windows and try again.",
        'nl': "Een bestand van de toepassing is in gebruik door een ander programma. "
              "Sluit de andere vensters van de toepassing en probeer opnieuw."},
    'maj_echec': {'fr': "La mise à jour a échoué : {e}", 'en': "The update failed: {e}",
                  'nl': "De update is mislukt: {e}"},
    'maj_redemarrer': {'fr': "Mise à jour installée. L'application va redémarrer.",
                       'en': "Update installed. The application will now restart.",
                       'nl': "Update geïnstalleerd. De toepassing wordt herstart."},
    'accord_titre': {'fr': "Aider à corriger les problèmes ?", 'en': "Help fix problems?",
                     'nl': "Helpen problemen op te lossen?"},
    'accord_texte': {
        'fr': "En cas de plantage ou de gel, l'application peut envoyer un court rapport "
              "technique (version, système, trace de l'erreur). Aucun fichier, aucun nom, "
              "aucun chemin personnel. Ce choix se modifie à tout moment dans le menu Aide.",
        'en': "If the application crashes or freezes, it can send a short technical "
              "report (version, system, error trace). No files, no names, no personal "
              "paths. You can change this at any time in the Help menu.",
        'nl': "Bij een crash of bevriezing kan de toepassing een kort technisch rapport "
              "versturen (versie, systeem, foutspoor). Geen bestanden, geen namen, geen "
              "persoonlijke paden. U kunt dit altijd wijzigen in het menu Help."},
    'accord_oui': {'fr': "Envoyer les rapports", 'en': "Send reports", 'nl': "Rapporten versturen"},
    'accord_non': {'fr': "Ne rien envoyer", 'en': "Send nothing", 'nl': "Niets versturen"},
    'rapport_titre': {'fr': "Signaler un problème", 'en': "Report a problem",
                      'nl': "Probleem melden"},
    'rapport_invite': {'fr': "Décrivez ce qui ne va pas :", 'en': "Describe what went wrong:",
                       'nl': "Beschrijf wat er misgaat:"},
    'rapport_exemple': {'fr': "Ce que vous faisiez, ce qui s'est passé, ce que vous attendiez...",
                        'en': "What you were doing, what happened, what you expected...",
                        'nl': "Wat u deed, wat er gebeurde, wat u verwachtte..."},
    'rapport_note': {
        'fr': "Le message part avec la version, le système et les dernières lignes du "
              "journal, sans nom ni chemin personnel.",
        'en': "The message is sent with the version, the system and the last log lines, "
              "without names or personal paths.",
        'nl': "Het bericht wordt verstuurd met de versie, het systeem en de laatste "
              "logregels, zonder namen of persoonlijke paden."},
    'rapport_envoyer': {'fr': "Envoyer", 'en': "Send", 'nl': "Versturen"},
    'rapport_annuler': {'fr': "Annuler", 'en': "Cancel", 'nl': "Annuleren"},
    'rapport_vide': {'fr': "Le message est vide : rien n'a été envoyé.",
                     'en': "The message is empty: nothing was sent.",
                     'nl': "Het bericht is leeg: er is niets verstuurd."},
    'rapport_envoye': {
        'fr': "Merci ! Le signalement est transmis (sans réseau, il repartira au "
              "prochain démarrage).",
        'en': "Thank you! The report is being sent (without a network, it will be sent "
              "at the next start).",
        'nl': "Bedankt! De melding wordt verstuurd (zonder netwerk gebeurt dat bij de "
              "volgende start)."},
}


def texte(cle: str, langue: str, **valeurs) -> str:
    jeu = TEXTES[cle]
    t = jeu.get(langue) or jeu['en']
    return t.format(**valeurs) if valeurs else t


class AideKit(QObject):
    """À créer par la fenêtre principale ; `remplir_menu(menu)` ajoute les
    entrées du kit au menu Aide existant."""

    _resultat_maj = pyqtSignal(object, bool)

    def __init__(self, fenetre, version: str, langue, dossiers_manuel,
                 nom_fil: str = 'kit', etat=None, journal=None):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.version = version
        self._langue = langue                  # fonction -> 'fr' / 'en' / 'nl'
        self.dossiers_manuel = [Path(d) for d in dossiers_manuel]
        self.nom_fil = nom_fil
        self.etat = etat                       # fonction -> dict joint au signalement
        self.journal = journal                 # fichier journal (extraits joints)
        self._resultat_maj.connect(self._sur_resultat_maj)
        self.act_manuel = self.act_maj = self.act_signaler = self.act_auto = None

    # -- textes ---------------------------------------------------------------
    def t(self, cle, **valeurs):
        try:
            lg = self._langue()
        except Exception:
            lg = 'en'
        return texte(cle, lg, **valeurs)

    # -- menu -----------------------------------------------------------------
    def remplir_menu(self, menu, avec_manuel: bool = True, avec_maj: bool = True) -> None:
        """`avec_manuel` / `avec_maj` à False pour une application qui a déjà
        ses propres entrées (manuel en trois langues, mises à jour)."""
        if avec_manuel:
            self.act_manuel = QAction(self.t('manuel'), self.fenetre)
            self.act_manuel.triggered.connect(self.ouvrir_manuel)
            menu.addAction(self.act_manuel)
        if avec_maj:
            self.act_maj = QAction(self.t('maj'), self.fenetre)
            self.act_maj.triggered.connect(lambda: self.verifier_maj(manuel=True))
            menu.addAction(self.act_maj)
        self.act_signaler = QAction(self.t('signaler'), self.fenetre)
        self.act_signaler.triggered.connect(self.signaler)
        menu.addAction(self.act_signaler)
        self.act_auto = QAction(self.t('auto'), self.fenetre)
        self.act_auto.setCheckable(True)
        try:
            import reporting
            self.act_auto.setChecked(reporting.consentement() is True)
        except Exception:
            pass
        self.act_auto.toggled.connect(self._definir_auto)
        menu.addAction(self.act_auto)

    def retraduire(self) -> None:
        for act, cle in ((self.act_manuel, 'manuel'), (self.act_maj, 'maj'),
                         (self.act_signaler, 'signaler'), (self.act_auto, 'auto')):
            if act is not None:
                act.setText(self.t(cle))

    def demarrer(self, accord_ms: int = 1200, maj_ms: int = 3000) -> None:
        """Accord (premier lancement) puis preuve de vie ; recherche
        silencieuse des mises à jour pour une application installée
        (maj_ms à 0 : l'application s'en charge elle-même)."""
        QTimer.singleShot(accord_ms, self.demander_accord)
        if not maj_ms:
            return
        try:
            import updater
            if updater.is_packaged():
                QTimer.singleShot(maj_ms, lambda: self.verifier_maj(manuel=False))
        except Exception:
            pass

    # -- manuel ---------------------------------------------------------------
    def ouvrir_manuel(self) -> None:
        try:
            import interface_kit
            if interface_kit.ouvrir_manuel(self.dossiers_manuel, self._langue()):
                return
        except Exception:
            log.exception("manuel")
        QMessageBox.information(self.fenetre, self.t('manuel').replace('&', ''),
                                self.t('manuel_absent'))

    # -- rapports -------------------------------------------------------------
    def demander_accord(self) -> None:
        try:
            import reporting
            premier = reporting.consentement() is None
            if premier:
                box = QMessageBox(self.fenetre)
                box.setWindowTitle(QApplication.applicationDisplayName()
                                   or QApplication.applicationName())
                box.setIcon(QMessageBox.Icon.Question)
                box.setText(self.t('accord_titre'))
                box.setInformativeText(self.t('accord_texte'))
                oui = box.addButton(self.t('accord_oui'), QMessageBox.ButtonRole.AcceptRole)
                box.addButton(self.t('accord_non'), QMessageBox.ButtonRole.RejectRole)
                box.exec()
                reporting.definir_consentement(box.clickedButton() is oui)
                if self.act_auto is not None:
                    self.act_auto.setChecked(reporting.consentement() is True)
            reporting.signaler_demarrage(premier=premier)
        except Exception:
            log.debug("accord des rapports", exc_info=True)

    def _definir_auto(self, actif: bool) -> None:
        try:
            import reporting
            reporting.definir_consentement(bool(actif))
        except Exception:
            pass

    def signaler(self) -> None:
        import reporting
        dlg = QDialog(self.fenetre)
        dlg.setWindowTitle(self.t('rapport_titre'))
        dlg.resize(540, 360)
        form = QVBoxLayout(dlg)
        form.addWidget(QLabel(self.t('rapport_invite')))
        zone = QPlainTextEdit()
        zone.setPlaceholderText(self.t('rapport_exemple'))
        form.addWidget(zone)
        note = QLabel(self.t('rapport_note'))
        note.setWordWrap(True)
        form.addWidget(note)
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        boutons.button(QDialogButtonBox.StandardButton.Ok).setText(self.t('rapport_envoyer'))
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.t('rapport_annuler'))
        boutons.accepted.connect(dlg.accept)
        boutons.rejected.connect(dlg.reject)
        form.addWidget(boutons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        description = zone.toPlainText().strip()
        if not description:
            QMessageBox.information(self.fenetre, self.t('rapport_titre'), self.t('rapport_vide'))
            return
        # Un signalement écrit à la main est toujours transmis : l'accord ne
        # gouverne que l'envoi automatique.
        accord = reporting.consentement()
        if accord is not True:
            reporting.definir_consentement(True)
        champs = {}
        try:
            champs = dict(self.etat() or {}) if self.etat else {}
        except Exception:
            pass
        if self.journal:
            try:
                champs['journal'] = reporting.extraits_journal(self.journal)
            except Exception:
                pass
        rapport = reporting.envoyer('manuel', description=description,
                                    version=self.version, **champs)
        if accord is not True:
            reporting.definir_consentement(bool(accord))
        # envoi en fond ; sans réseau, le rapport attend dans la file et
        # repart au démarrage suivant (reporting.vider_file)
        QMessageBox.information(self.fenetre, self.t('rapport_titre'), self.t('rapport_envoye'))
        return rapport

    # -- mises à jour ---------------------------------------------------------
    def verifier_maj(self, manuel: bool = False) -> None:
        """Interroge GitHub dans un fil séparé, sans bloquer l'interface."""
        if manuel:
            try:
                self.fenetre.statusBar().showMessage(self.t('maj_recherche'), 5000)
            except Exception:
                pass

        def _fil():
            try:
                import updater
                info = updater.check(self.version)
            except Exception:                 # ne jamais faire tomber l'app
                info = None
            self._resultat_maj.emit(info, manuel)

        self._fil_maj = threading.Thread(target=_fil, daemon=True,
                                         name=f'{self.nom_fil}-maj')
        self._fil_maj.start()

    def _sur_resultat_maj(self, info, manuel: bool) -> None:
        if not info:
            if manuel:
                QMessageBox.information(self.fenetre, self.t('maj_titre'),
                                        self.t('maj_a_jour', v=self.version))
            return
        try:
            import updater
            installe = bool(updater.is_packaged())
            page = f"https://github.com/{updater.REPO}/releases/latest"
        except Exception:
            installe, page = False, ''
        box = QMessageBox(self.fenetre)
        box.setWindowTitle(self.t('maj_titre'))
        box.setText(self.t('maj_dispo', v=info['version'], c=self.version))
        notes = (info.get('notes') or '').strip()
        try:
            import updater as _u
            notes = _u.notes_dans_la_langue(notes, self._langue()).strip()
        except Exception:
            pass
        if notes:
            box.setDetailedText(notes[:4000])
        if installe:
            oui = box.addButton(self.t('maj_installer'), QMessageBox.ButtonRole.AcceptRole)
        else:
            box.setInformativeText(self.t('maj_sources'))
            oui = box.addButton(self.t('maj_page'), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.t('maj_plus_tard'), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not oui:
            return
        if not installe:
            if page:
                QDesktopServices.openUrl(QUrl(page))
            return
        self._telecharger(info)

    def _telecharger(self, info: dict) -> None:
        import updater
        dlg = QProgressDialog(self.t('maj_telechargement'), None, 0, 100, self.fenetre)
        dlg.setWindowTitle(self.t('maj_titre'))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        etat = {'fait': 0, 'total': 0, 'fini': False, 'erreur': None, 'pose': False}

        def _progres(fait, total):
            etat['fait'], etat['total'] = fait, total

        def _fil():
            try:
                etat['pose'] = bool(updater.download_and_apply(info, progress=_progres))
            except Exception as exc:
                etat['erreur'] = exc
            finally:
                etat['fini'] = True

        threading.Thread(target=_fil, daemon=True, name=f'{self.nom_fil}-maj-pose').start()
        minuteur = QTimer(self)
        minuteur.setInterval(100)

        def _tic():
            if not etat['fini']:
                if etat['total'] > 0:
                    dlg.setValue(min(99, etat['fait'] * 100 // etat['total']))
                return
            minuteur.stop()
            dlg.close()
            err = etat['erreur']
            if err is not None or not etat['pose']:
                msg = str(err) if err is not None else 'archive'
                verrou = (isinstance(err, PermissionError) or 'WinError 32' in msg
                          or 'used by another process' in msg)
                QMessageBox.warning(self.fenetre, self.t('maj_titre'),
                                    self.t('maj_verrou') if verrou
                                    else self.t('maj_echec', e=msg))
                return
            QMessageBox.information(self.fenetre, self.t('maj_titre'), self.t('maj_redemarrer'))
            try:
                updater.restart()
            finally:
                QApplication.quit()

        minuteur.timeout.connect(_tic)
        minuteur.start()
        self._minuteur_maj = minuteur


def logo_a_propos(box: QMessageBox, chemin) -> None:
    """Le logo de l'application (même source que l'icône) dans « À propos »."""
    try:
        if Path(chemin).is_file():
            box.setIconPixmap(QPixmap(str(chemin)))
    except Exception:
        pass
