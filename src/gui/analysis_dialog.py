"""Night session analysis dialog for MountMonitor.

Provides comprehensive analysis of a recorded session:
- Overall quality rating (TRACKING data only)
- Per-target RA/DEC tracking statistics
- Periodic error detection via FFT
- Drift analysis
- Time synchronization analysis
- Event summary
- Detailed recommendations

All text is bilingual FR/EN.
"""

import logging
from datetime import datetime

import numpy as np

from ..utils.ajustement import pente
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QProgressBar, QFileDialog, QApplication, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

from ..logging_module.log_parser import ParsedSession, TargetSegment
from ..utils.i18n import T, get_language, LANGUES
from .rapport_textes import R
from ..utils.coordinates import format_ra, format_dec

logger = logging.getLogger(__name__)


def _rating_emoji(rating: str, lg: str = 'en') -> str:
    """The quality rating, in one language."""
    cles = {'excellent': 'note_excellent', 'good': 'note_bon',
            'fair': 'note_moyen', 'poor': 'note_mauvais'}
    cle = cles.get(rating)
    return f"[{R(cle, lg)}]" if cle else rating


def _rating_color(rating: str) -> str:
    """Return HTML color for rating."""
    return {
        'excellent': '#00ff88',
        'good': '#88ff00',
        'fair': '#ffaa00',
        'poor': '#ff4444',
    }.get(rating, '#ffffff')


def _is_precision_unguided_mount(session) -> bool:
    """Detect whether the mount is a high-precision unguided type (e.g. 10Micron).

    These mounts use internal pointing models instead of external guiding,
    so their coordinate-reported deviations are naturally larger than guided mounts.
    The quality thresholds must be adapted accordingly.

    Checks mount_name, firmware, and mount_driver fields from the session.
    """
    # Collect all identifying strings
    fields = []
    for attr in ('mount_name', 'firmware', 'mount_driver'):
        val = getattr(session, attr, '') or ''
        if val:
            fields.append(val.lower())
    combined = ' '.join(fields)

    if not combined:
        return False

    # 10Micron mounts (GM1000, GM2000, GM3000, GM4000)
    if '10micron' in combined or '10 micron' in combined or 'tenmicron' in combined:
        return True
    if any(m in combined for m in ('gm1000', 'gm2000', 'gm3000', 'gm4000')):
        return True
    # Planewave mounts
    if 'planewave' in combined:
        return True
    # ASA DDM mounts (direct drive, often unguided)
    if 'asa' in combined and 'ddm' in combined:
        return True
    return False


def construire_rapport(session, lang: str = 'fr') -> str:
    """Le texte du rapport de nuit, sans ouvrir de fenetre.

    Sert a la sauvegarde automatique en fin de session : le rapport le plus
    utile est celui qu'on n'a pas eu besoin de demander.
    """
    dlg = AnalysisDialog.__new__(AnalysisDialog)
    dlg._session = session
    dlg._lang = lang

    class _Tampon:
        def __init__(self):
            self.texte = ""

        def setPlainText(self, t):
            self.texte = t

        def __getattr__(self, _):
            return lambda *a, **k: None

    dlg._report = _Tampon()
    dlg._vues = {}
    dlg._rapports = {}
    return dlg._run_analysis(lang)


def sauver_rapport(chemin_dat, lang: str = 'fr', toutes_langues: bool = True):
    """Ecrit le rapport de nuit a cote du .dat, dans les trois langues.

        MountMonitor_20260921-220015-rapport-fr.txt
        MountMonitor_20260921-220015-rapport-en.txt
        MountMonitor_20260921-220015-rapport-nl.txt

    Renvoie le chemin de celui de `lang`, ou None. Ne leve jamais : perdre le
    rapport ne doit pas empecher la fermeture propre des fichiers de session.
    """
    from pathlib import Path as _P
    from ..logging_module.log_parser import parse_dat_file
    try:
        chemin_dat = _P(chemin_dat)
        if not chemin_dat.exists():
            return None
        session = parse_dat_file(chemin_dat)
        if session.sample_count == 0:
            return None
        codes = list(LANGUES) if toutes_langues else [lang]
        principal = None
        for code in codes:
            sortie = chemin_dat.with_name(f"{chemin_dat.stem}-rapport-{code}.txt")
            sortie.write_text(construire_rapport(session, code), encoding="utf-8")
            if code == lang:
                principal = sortie
        logger.info("Rapport de nuit ecrit en %s : %s",
                    ", ".join(codes), chemin_dat.stem)
        return principal or chemin_dat.with_name(
            f"{chemin_dat.stem}-rapport-{codes[0]}.txt")
    except Exception:
        logger.exception("Le rapport de nuit n'a pas pu etre ecrit")
        return None


class AnalysisDialog(QDialog):
    """Comprehensive session analysis dialog."""

    def __init__(self, session: ParsedSession, parent=None):
        super().__init__(parent)
        self._session = session
        self._lang = get_language()
        self._rapports = {}
        self._setup_ui()
        self._remplir_les_langues()

    def _remplir_les_langues(self):
        """Un rapport par langue, chacun dans son onglet.

        Les trois sont construits d'emblee : l'analyse d'une nuit entiere prend
        une fraction de seconde, et changer d'onglet doit etre instantane.
        """
        for code, vue in getattr(self, '_vues', {}).items():
            texte = self._run_analysis(code)
            self._rapports[code] = texte
            vue.setPlainText(texte)
            vue.moveCursor(QTextCursor.MoveOperation.Start)
        self._report_text = self._rapports.get(self._lang, '')
        if not self._rapports:          # pas d'interface : usage en bibliotheque
            self._report_text = self._run_analysis()

    def _setup_ui(self):
        title = R("titre_fenetre", self._lang)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel()
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #88ccff; margin: 8px;")
        header.setText(R("titre_rapport", self._lang))
        header.setToolTip(
            "EN: Comprehensive analysis of the recorded session\n"
            "FR: Analyse complète de la session enregistrée\n"
            "NL: Volledige analyse van de opgenomen sessie"
        )
        layout.addWidget(header)

        # One tab per language. The report is written in ONE language at a
        # time — reading it in two, as before, made it twice as long for no
        # gain. The tab of the interface language is the one shown on opening.
        self._onglets = QTabWidget()
        self._onglets.setToolTip(
            "EN: The same report, in each language\n"
            "FR: Le même rapport, dans chaque langue\n"
            "NL: Hetzelfde rapport, in elke taal"
        )
        self._vues = {}
        for code, nom in LANGUES.items():
            vue = QTextEdit()
            vue.setReadOnly(True)
            vue.setFont(QFont("Consolas", 10))
            vue.setStyleSheet(
                "QTextEdit { background: #1a1a2e; color: #e0e0e0; "
                "border: 1px solid #333; padding: 8px; }"
            )
            self._vues[code] = vue
            self._onglets.addTab(vue, nom)
        # `_report` reste l'onglet de la langue de l'application : tout le code
        # existant (remplissage, export, recherche) continue de fonctionner.
        self._report = self._vues.get(self._lang) or next(iter(self._vues.values()))
        self._onglets.setCurrentWidget(self._report)
        layout.addWidget(self._onglets)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_export = QPushButton(
            R("exporter_txt", self._lang)
        )
        btn_export.setToolTip(
            "EN: Export analysis report as text file\n"
            "FR: Exporter le rapport d'analyse en fichier texte"
        )
        btn_export.clicked.connect(self._export_report)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_close = QPushButton(
            R("fermer", self._lang)
        )
        btn_close.setToolTip(
            "EN: Close analysis window\n"
            "FR: Fermer la fenêtre d'analyse"
        )
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _run_analysis(self, langue=None):
        """Build the report. Returns the text; also fills the widget if there is one."""
        s = self._session
        lg = langue or self._lang
        # `_` traduit dans la langue demandee : le rapport est ecrit dans UNE
        # langue, plus en double comme avant.
        def _(cle, **kw):
            return R(cle, lg, **kw)
        fr = lg == 'fr'
        lines = []

        # ═══════════════════════════════════════════════════════════
        # 1. SESSION OVERVIEW
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  " + _("t_apercu"))
        lines.append("=" * 70)
        lines.append("")

        if s.start_time:
            lines.append(f"  {_('date'):<22} : {s.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
        lines.append(f"  {_('observatoire'):<22} : {s.observatory or 'N/A'}")
        lines.append(f"  {_('monture'):<22} : {s.mount_name or 'N/A'}")
        if s.firmware:
            lines.append(f"  {_('firmware'):<22} : {s.firmware}")
        lines.append(f"  {_('duree'):<22} : {s.duration_str}")
        lines.append(f"  {_('ech_total'):<22} : {s.sample_count:,}")
        lines.append(f"  {_('ech_suivi'):<22} : {s.tracking_sample_count:,}")
        if s.effective_frequency > 0:
            lines.append(f"  {_('cadence'):<22} : {s.effective_frequency:.2f} Hz")
        lines.append(f"  {_('cibles'):<22} : {len(s.target_segments)}")
        lines.append(f"  {_('fichier'):<22} : {s.file_path}")
        lines.append("")

        if s.sample_count == 0:
            lines.append("  [!] " + _("rien_a_analyser"))
            self._report.setPlainText("\n".join(lines))
            return

        if s.tracking_sample_count == 0:
            lines.append("  [!] " + _("pas_de_suivi"))
            lines.append("      " + _("pas_de_suivi_detail"))
            self._report.setPlainText("\n".join(lines))
            return

        # ═══════════════════════════════════════════════════════════
        # 2. OVERALL QUALITY RATING (combined from all segments)
        # ═══════════════════════════════════════════════════════════
        # Raw RMS, kept for reference only. It mixes three different things:
        # the tracking jitter, the slow drift, and any commanded motion. The
        # rating must not depend on it — see the detrended figures below.
        ra_rms = float(np.std(s.ra_deviations)) if len(s.ra_deviations) > 0 else 999
        dec_rms = float(np.std(s.dec_deviations)) if len(s.dec_deviations) > 0 else 999
        combined_rms_raw = float(np.sqrt(ra_rms**2 + dec_rms**2))

        # Jitter: the spread the mount shows WHILE it holds a position. It is
        # measured between repositionings, because a deviation record is a
        # staircase, not a noisy line: the sequencer dithers between exposures
        # and the mount STAYS on its new step. Removing a straight line does not
        # remove a staircase — on the real 21/09/2026 session that left 9.1"
        # while the mount was holding each step to 0.12".
        ra_jit = float(s.ra_jitter) if s.ra_jitter > 0 else float(np.std(s.ra_detrended) or ra_rms)
        dec_jit = float(s.dec_jitter) if s.dec_jitter > 0 else float(np.std(s.dec_detrended) or dec_rms)
        combined_rms = float(np.sqrt(ra_jit**2 + dec_jit**2))
        rms_detrend = float(np.sqrt(
            (np.std(s.ra_detrended) if len(s.ra_detrended) else 0.0) ** 2
            + (np.std(s.dec_detrended) if len(s.dec_detrended) else 0.0) ** 2))

        # Mean drift over the segments, weighted by sample count.
        _segs = [g for g in s.target_segments if g.sample_count > 0]
        if _segs:
            _w = float(sum(g.sample_count for g in _segs))
            ra_drift_mean = sum(g.ra_drift_arcsec_per_hour * g.sample_count for g in _segs) / _w
            dec_drift_mean = sum(g.dec_drift_arcsec_per_hour * g.sample_count for g in _segs) / _w
        else:
            ra_drift_mean = dec_drift_mean = 0.0

        # Detect mount type and adapt scoring thresholds
        # Unguided precision mounts (10Micron, Planewave) report coordinate-level
        # deviations that are naturally larger than guided mounts. Their tracking
        # quality is excellent even at 2-4" RMS as measured by MountMonitor.
        precision_unguided = _is_precision_unguided_mount(s)
        if precision_unguided:
            # Thresholds for unguided precision mounts, applied to the JITTER.
            # They used to be 2/4/8" because the figure they graded included the
            # drift and the commanded motion. On the jitter alone, a 10Micron
            # under a pointing model sits around 0.2-0.5", so the scale must be
            # tighter or every session would come out "excellent".
            if combined_rms < 0.5:
                rating = 'excellent'
            elif combined_rms < 1.0:
                rating = 'good'
            elif combined_rms < 2.0:
                rating = 'fair'
            else:
                rating = 'poor'
        else:
            # Standard thresholds for guided mounts, also applied to the jitter
            if combined_rms < 0.4:
                rating = 'excellent'
            elif combined_rms < 1.0:
                rating = 'good'
            elif combined_rms < 2.0:
                rating = 'fair'
            else:
                rating = 'poor'

        rating_text = _rating_emoji(rating, lg)

        lines.append("=" * 70)
        lines.append("  " + _("t_qualite"))
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"  {_('note'):<22} : {rating_text}")
        lines.append("")
        lines.append("  --- " + _("s_jitter") + " ---")
        lines.append("      " + _("jitter_explique"))
        lines.append(f"  {_('jitter_combine'):<22} : {combined_rms:.3f}\"   {_('note_fondee_ici')}")
        lines.append(f"  {T('ra_short', lg) + ' RMS':<22} : {ra_jit:.3f}\"")
        lines.append(f"  {T('dec_short', lg) + ' RMS':<22} : {dec_jit:.3f}\"")
        lines.append("")
        lines.append("  --- " + _("s_repositionnement") + " ---")
        _mv = getattr(s, 'mouvements', None) or []
        if _mv or s.repositionnements:
            # Count MOVES, not threshold crossings. One re-centering trips the
            # threshold at every sample it takes to complete, so crossings
            # both inflate the count and deflate the median amplitude -- the
            # 2026-09-22 session read 47 moves of 0.79" where there were 55
            # moves of 6.47".
            if _mv:
                _am = float(np.median([m.amplitude for m in _mv]))
                _n = len(_mv)
            else:
                _amp = [g.amplitude_repositionnement for g in s.target_segments
                        if g.amplitude_repositionnement > 0]
                _am = float(np.median(_amp)) if _amp else 0.0
                _n = s.repositionnements
            lines.append(f"  {_('mouvements_detectes'):<22} : {_n}")
            lines.append(f"  {_('amplitude_mediane'):<22} : {_am:.2f}\"")
            lines.append("      " + _("repositionnement_explique"))
        else:
            lines.append("  " + _("aucun_detecte"))
        lines.append("")
        lines.append("  --- " + _("s_derive") + " ---")
        lines.append(f"  {_('derive_ad'):<22} : {ra_drift_mean:+.2f}\"/h")
        lines.append(f"  {_('derive_dec'):<22} : {dec_drift_mean:+.2f}\"/h")
        _expo = 180.0
        _mv = np.hypot(ra_drift_mean, dec_drift_mean) * _expo / 3600.0
        lines.append(f"  {_('deplacement_pose', n=_expo)} : {_mv:.2f}\"")
        lines.append("      " + _("annule_par_dither"))
        lines.append("")
        lines.append("  --- " + _("s_memoire") + " ---")
        lines.append(f"  {_('rms_brut'):<34} : {combined_rms_raw:.3f}\"")
        lines.append(f"  {_('rms_sans_derive'):<34} : {rms_detrend:.3f}\"")
        lines.append("      " + _("contient_paliers"))
        if s.excursions_removed:
            lines.append(f"  {_('excursions_ecartees'):<34} : "
                         f"{s.excursions_removed:,} {_('echantillons')}")
            lines.append("      " + _("excursions_explique"))
        _dropped = s.tracking_sample_count - s.samples_in_segments
        if _dropped > 0:
            lines.append(f"  {_('slews_ecartes'):<34} : {_dropped:,}")
        if precision_unguided:
            lines.append(f"  {_('type_monture'):<22} : {_('non_guidee_precision')}")
            lines.append(f"  {_('seuils_adaptes'):<22} : <0.5\" | <1.0\" | <2.0\"")
        else:
            lines.append(f"  {_('seuils'):<22} : <0.4\" | <1.0\" | <2.0\"")
        lines.append("")

        if rating == 'excellent':
            if precision_unguided:
                lines.append("  " + _("v_exc_ng"))
            else:
                lines.append("  " + _("v_exc"))
        elif rating == 'good':
            if precision_unguided:
                lines.append("  " + _("v_bon_ng"))
            else:
                lines.append("  " + _("v_bon"))
        elif rating == 'fair':
            if precision_unguided:
                lines.append("  " + _("v_moyen_ng"))
                lines.append("  " + _("v_moyen_ng_note"))
            else:
                lines.append("  " + _("v_moyen"))
                lines.append("  " + _("v_moyen_note"))
        else:
            if precision_unguided:
                lines.append("  " + _("v_mauvais_ng"))
                lines.append("  " + _("v_mauvais_ng_ordre"))
                lines.append("  " + _("v_mauvais_ng_modele"))
            else:
                lines.append("  " + _("v_mauvais"))
                lines.append("  " + _("v_mauvais_verif"))
        lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 3. PER-TARGET ANALYSIS
        # ═══════════════════════════════════════════════════════════
        for seg_idx, seg in enumerate(s.target_segments):
            lines.append("=" * 70)
            ra_str = format_ra(seg.ra_median_hours)
            dec_str = format_dec(seg.dec_median_degrees)
            lines.append(f"  {_('t_cible')} #{seg_idx + 1}  —  {T('ra_short', lg)} {ra_str}  "
                         f"{T('dec_short', lg)} {dec_str}  "
                         f"({seg.sample_count:,} {_('echantillons')})")
            lines.append("=" * 70)
            lines.append("")

            self._write_axis_stats(lines, "RA", seg.ra_deviations,
                                   seg.timestamps, seg.ra_stdevs, fr,
                                   precision_unguided, lg)
            self._write_axis_stats(lines, "DEC", seg.dec_deviations,
                                   seg.timestamps, seg.dec_stdevs, fr,
                                   precision_unguided, lg)

            # FFT on the DETRENDED deviations. A linear drift is not periodic,
            # but a finite window turns it into a large low-frequency component
            # that dominates the spectrum and hides the worm period we are
            # actually looking for.
            if len(seg.ra_deviations) > 64:
                freq = len(seg.ra_deviations) / max(1.0, seg.timestamps[-1] - seg.timestamps[0])
                self._write_fft(lines, "RA", seg.ra_detrended, freq, fr, top_n=5, lg=lg)
            if len(seg.dec_deviations) > 64:
                freq = len(seg.dec_deviations) / max(1.0, seg.timestamps[-1] - seg.timestamps[0])
                self._write_fft(lines, "DEC", seg.dec_detrended, freq, fr, top_n=3, lg=lg)

            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # If no segments but we have combined data, show combined stats
        # ═══════════════════════════════════════════════════════════
        if not s.target_segments and len(s.ra_deviations) > 0:
            lines.append("=" * 70)
            lines.append("  " + _("t_ad"))
            lines.append("=" * 70)
            lines.append("")
            self._write_axis_stats(lines, "RA", s.ra_deviations,
                                   s.tracking_timestamps, s.tracking_ra_stdevs, fr)
            lines.append("=" * 70)
            lines.append("  " + _("t_dec"))
            lines.append("=" * 70)
            lines.append("")
            self._write_axis_stats(lines, "DEC", s.dec_deviations,
                                   s.tracking_timestamps, s.tracking_dec_stdevs, fr)

        # ═══════════════════════════════════════════════════════════
        # 4. AXIAL DATA
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_axis) > 10 and np.any(s.ra_axis != 0):
            lines.append("=" * 70)
            lines.append("  " + _("t_axial"))
            lines.append("=" * 70)
            lines.append("")

            ra_axis = s.ra_axis[s.ra_axis != 0] if np.any(s.ra_axis != 0) else s.ra_axis
            if len(ra_axis) > 1:
                lines.append(f"  RA Axis range      : {np.min(ra_axis):.4f} — {np.max(ra_axis):.4f}")
                lines.append(f"  RA Axis excursion  : {np.ptp(ra_axis):.4f} deg")

            dec_axis = s.dec_axis[s.dec_axis != 0] if np.any(s.dec_axis != 0) else s.dec_axis
            if len(dec_axis) > 1:
                lines.append(f"  DEC Axis range     : {np.min(dec_axis):.4f} — {np.max(dec_axis):.4f}")
                lines.append(f"  DEC Axis excursion : {np.ptp(dec_axis):.4f} deg")

            if len(ra_axis) > 2 and len(s.timestamps) > 2:
                t_rel = s.timestamps[:len(ra_axis)] - s.timestamps[0]
                dt = np.diff(t_rel)
                dt[dt == 0] = 1e-6
                ra_speed = np.diff(ra_axis) / dt
                lines.append(f"  RA mean speed      : {np.mean(ra_speed):+.6f} deg/s")
                lines.append(f"  RA max speed       : {np.max(np.abs(ra_speed)):.6f} deg/s")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 5. TIME SYNCHRONIZATION
        # ═══════════════════════════════════════════════════════════
        if len(s.time_pc_mount_diff) > 0:
            lines.append("=" * 70)
            lines.append("  " + _("t_temps"))
            lines.append("=" * 70)
            lines.append("")

            td = s.time_pc_mount_diff
            lines.append(f"  PC-Mount diff avg  : {np.mean(td):+.1f} ms")
            lines.append(f"  PC-Mount diff med  : {np.median(td):+.1f} ms")
            lines.append(f"  PC-Mount diff max  : {np.max(np.abs(td)):.1f} ms")
            lines.append(f"  PC-Mount diff std  : {np.std(td):.1f} ms")

            if len(td) > 100:
                a = pente(s.time_timestamps - s.time_timestamps[0], td)
                if a is None:
                    lines.append("  " + _("derive_non_calculable"))
                else:
                    drift_per_min = a * 60.0
                    lines.append(f"  {_('derive_horloge'):<34} : {drift_per_min:+.3f} ms/min")
                    if abs(drift_per_min) > 1.0:
                        lines.append("  " + _("derive_horloge_forte"))
                    else:
                        lines.append("  " + _("horloge_stable"))
            lines.append("")

            if len(s.time_pc_loop) > 0:
                pl = s.time_pc_loop
                lines.append(f"  PC loop avg        : {np.mean(pl):.1f} ms")
                lines.append(f"  PC loop max        : {np.max(pl):.1f} ms")
                lines.append(f"  PC loop std        : {np.std(pl):.1f} ms")
                if np.mean(pl) > 1000:
                    lines.append("  " + _("boucle_pc_lente") + " " + _("pc_a_du_mal"))
            lines.append("")

            if len(s.time_mount_loop) > 0:
                ml = s.time_mount_loop
                lines.append(f"  Mount loop avg     : {np.mean(ml):.1f} ms")
                lines.append(f"  Mount loop max     : {np.max(ml):.1f} ms")
            lines.append("")

            if len(s.time_ntp_diff) > 0 and np.any(s.time_ntp_diff != 0):
                ntp = s.time_ntp_diff[s.time_ntp_diff != 0]
                if len(ntp) > 0:
                    lines.append(f"  PC-NTP offset avg  : {np.mean(ntp):+.1f} ms")
                    lines.append(f"  PC-NTP offset max  : {np.max(np.abs(ntp)):.1f} ms")
                    if np.max(np.abs(ntp)) > 1000:
                        lines.append("  " + _("decalage_ntp") + " " + _("synchroniser_horloge"))
                    lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 6. TRACKING STATUS
        # ═══════════════════════════════════════════════════════════
        if s.statuses:
            lines.append("=" * 70)
            lines.append("  " + _("t_suivi"))
            lines.append("=" * 70)
            lines.append("")

            from collections import Counter
            status_counts = Counter(s.statuses)
            total = len(s.statuses)
            for status, count in status_counts.most_common():
                pct = count / total * 100
                lines.append(f"  {status:<20} : {count:>6} samples ({pct:.1f}%)")
            lines.append("")

            tracking_pct = status_counts.get('TRACKING', 0) / total * 100
            if tracking_pct < 90:
                lines.append(_("suivi_faible", pct=tracking_pct))
                lines.append("      " + _("suivi_faible_detail"))
            else:
                lines.append(_("suivi_normal", pct=tracking_pct))
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 6a. COMMANDED MOVES
        # ═══════════════════════════════════════════════════════════
        lines.extend(self._section_mouvements(s, lg))

        # ═══════════════════════════════════════════════════════════
        # 6b. NIGHT EPHEMERIS
        # ═══════════════════════════════════════════════════════════
        lines.extend(self._section_nuit(s, lg))

        # ═══════════════════════════════════════════════════════════
        # 7. TOLERANCE ANALYSIS (TRACKING data only)
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_deviations) > 0:
            lines.append("=" * 70)
            lines.append("  " + _("t_tolerance"))
            lines.append("  (" + _("t_suivi").lower() + ")")
            lines.append("=" * 70)
            lines.append("")

            # Detrended deviations, i.e. the same basis as the jitter and the
            # rating. Using the RAW deviations here made the report contradict
            # itself: the 2026-09-22 session was rated EXCELLENT on a 0.171"
            # jitter and then announced that 70% of samples exceeded 2" -- that
            # 70% was the slow drift and the dither steps, neither of which
            # blurs a frame.
            _ra_tol = s.ra_residual if len(s.ra_residual) else s.ra_deviations
            _dec_tol = s.dec_residual if len(s.dec_residual) else s.dec_deviations
            for tol in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
                ra_exceed = np.sum(np.abs(_ra_tol) > tol)
                dec_exceed = np.sum(np.abs(_dec_tol) > tol)
                ra_pct = ra_exceed / len(_ra_tol) * 100
                dec_pct = dec_exceed / len(_dec_tol) * 100
                lines.append(
                    f"  > {tol:.1f}\"  :  RA {ra_exceed:>6} ({ra_pct:>5.1f}%)  "
                    f"|  DEC {dec_exceed:>6} ({dec_pct:>5.1f}%)"
                )
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 8. DATA CONTINUITY / GAPS
        # ═══════════════════════════════════════════════════════════
        if len(s.timestamps) > 10:
            lines.append("=" * 70)
            lines.append("  " + _("t_continuite"))
            lines.append("=" * 70)
            lines.append("")

            dt = np.diff(s.timestamps)
            expected_dt = 1.0 / s.effective_frequency if s.effective_frequency > 0 else 0.5

            gaps = dt[dt > expected_dt * 5]
            if len(gaps) > 0:
                lines.append(f"  {_('coupures'):<34} : {len(gaps)}")
                lines.append(f"  {_('plus_longue_coupure'):<34} : {np.max(gaps):.1f} s")
                lines.append(f"  {_('temps_total_perdu'):<34} : {np.sum(gaps):.1f} s")
                lines.append("  " + _("coupures_detectees"))
                lines.append("      " + _("coupure_cause"))
            else:
                lines.append("  " + _("acquisition_continue"))
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 9. ENVIRONMENT & DIAGNOSTICS
        # ═══════════════════════════════════════════════════════════
        has_env = len(s.env_timestamps) > 0
        if has_env:
            lines.append("=" * 70)
            lines.append("  " + _("t_environnement"))
            lines.append("=" * 70)
            lines.append("")

            temp = s.env_temperature_ext
            valid_temp = temp[~np.isnan(temp)] if len(temp) > 0 else np.array([])
            if len(valid_temp) > 0:
                lines.append(f"  Temperature (ext)  : {valid_temp[0]:.1f}°C -> {valid_temp[-1]:.1f}°C")
                lines.append(f"  Temp range         : {np.min(valid_temp):.1f}°C — {np.max(valid_temp):.1f}°C")
                temp_delta = valid_temp[-1] - valid_temp[0]
                lines.append(f"  {_('changement_temp'):<34} : {temp_delta:+.1f}°C {_('pendant_session')}")
                if abs(temp_delta) > 5.0:
                    lines.append("  " + _("temp_grande_variation"))
                elif abs(temp_delta) > 2.0:
                    lines.append("  " + _("temp_variation_moderee"))
                else:
                    lines.append("  " + _("temperature_stable"))
                lines.append("")

            temp_int = s.env_temperature_int
            valid_int = temp_int[~np.isnan(temp_int)] if len(temp_int) > 0 else np.array([])
            if len(valid_int) > 0:
                lines.append(f"  Internal temp      : {valid_int[0]:.1f}°C -> {valid_int[-1]:.1f}°C")
                lines.append(f"  Internal range     : {np.min(valid_int):.1f}°C — {np.max(valid_int):.1f}°C")
                int_delta = valid_int[-1] - valid_int[0]
                if int_delta > 10.0:
                    lines.append("  " + _("monture_chauffe"))
                lines.append("")

            pres = s.env_pressure
            valid_pres = pres[~np.isnan(pres)] if len(pres) > 0 else np.array([])
            if len(valid_pres) > 0:
                lines.append(f"  {_('pression'):<34} : {valid_pres[0]:.1f} -> {valid_pres[-1]:.1f} mbar")
                lines.append(f"  Pressure range      : {np.min(valid_pres):.1f} — {np.max(valid_pres):.1f} mbar")
                pres_delta = valid_pres[-1] - valid_pres[0]
                lines.append(f"  Pressure change     : {pres_delta:+.1f} mbar")
                if abs(pres_delta) > 5.0:
                    lines.append("  " + _("barometre_change"))
                lines.append("")

            valid_rms = s.env_alignment_rms[~np.isnan(s.env_alignment_rms)] if len(s.env_alignment_rms) > 0 else np.array([])
            if len(valid_rms) > 0:
                stars = s.env_alignment_stars
                valid_stars = [st for st in stars if st > 0]
                if valid_stars:
                    lines.append(f"  {_('etoiles_modele'):<34} : {valid_stars[0]}")
                lines.append(f"  Alignment RMS      : {valid_rms[0]:.1f}\"")

                valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
                if len(valid_polar) > 0:
                    polar_arcmin = valid_polar[0] * 60.0
                    lines.append(f"  {_('erreur_polaire'):<34} : {valid_polar[0]:.4f}° ({polar_arcmin:.1f}')")
                    if polar_arcmin > 5.0:
                        lines.append("  " + _("polaire_elevee"))
                    elif polar_arcmin > 1.0:
                        lines.append("  " + _("polaire_moderee"))
                    else:
                        lines.append("  " + _("alignement_excellent"))
                lines.append("")

            rates = s.env_tracking_rates
            valid_rates = rates[~np.isnan(rates)] if len(rates) > 0 else np.array([])
            if len(valid_rates) > 1:
                rate_std = np.std(valid_rates)
                lines.append(f"  Tracking rate avg  : {np.mean(valid_rates):.2f}")
                lines.append(f"  Tracking rate std  : {rate_std:.4f}")
                if rate_std > 0.1:
                    lines.append("  " + _("variation_taux_suivi"))
                lines.append("")

            valid_codes = [c for c in s.env_status_codes if c >= 0]
            if valid_codes:
                from collections import Counter
                code_counts = Counter(valid_codes)
                status_names = {
                    0: "Tracking",
                    1: "Stopped (no tracking)",
                    2: "Slewing (park)",
                    3: "Unparking",
                    4: "Slewing (home)",
                    5: "Parked",
                    6: "Slewing (goto)",
                    7: "Tracking (guiding)",
                    8: "Outside limits",
                    9: "Following satellite",
                    10: "User OK needed",
                    11: "Motor fault",
                    98: "Unknown",
                    99: "Error",
                }
                lines.append("  " + _("codes_statut") + " (10Micron :Gstat#) :")
                for code, count in code_counts.most_common():
                    name = status_names.get(code, f"Code {code}")
                    lines.append(f"    {code} = {name:<30} : {count}x")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 10. EVENTS
        # ═══════════════════════════════════════════════════════════
        if s.events:
            lines.append("=" * 70)
            lines.append("  " + _("t_journal"))
            lines.append("=" * 70)
            lines.append("")

            tolerance_events = [e for e in s.events if 'TOLERANCE' in e[1]]
            warning_events = [e for e in s.events if 'WARNING' in e[1] or 'Check WARNING' in e[1]]
            status_events = [e for e in s.events if 'Mount status' in e[1]]

            lines.append(f"  {_('evenements_totaux'):<34} : {len(s.events)}")
            lines.append(f"  {_('alertes_tolerance'):<34} : {len(tolerance_events)}")
            lines.append(f"  {_('avertissements'):<34} : {len(warning_events)}")
            lines.append(f"  {_('changements_statut'):<34} : {len(status_events)}")
            lines.append("")

            if tolerance_events:
                lines.append("  " + _("evenements_tolerance_10") + " :")
                for ts, msg in tolerance_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                if len(tolerance_events) > 10:
                    lines.append("    " + _("et_n_de_plus", n=len(tolerance_events) - 10))
                lines.append("")

            if warning_events:
                lines.append("  " + _("avertissements") + " :")
                for ts, msg in warning_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 11. RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  " + _("t_recommandations"))
        lines.append("=" * 70)
        lines.append("")

        recommendations = []

        # Applied to the JITTER (drift removed), so the values are much tighter
        # than the old ones, which graded a figure polluted by drift and slews.
        ra_threshold = 1.0 if precision_unguided else 1.5
        dec_threshold = 1.0 if precision_unguided else 1.5

        if ra_jit > ra_threshold:
            recommendations.append(_("r_ad_instable", seuil=ra_threshold))
        if dec_jit > dec_threshold:
            recommendations.append(_("r_dec_instable", seuil=dec_threshold))

        # Drift, per target. The threshold is what a drift actually costs over
        # one exposure, not its hourly figure: every dither cancels the rest.
        for seg_idx, seg in enumerate(s.target_segments):
            for axe, devs in (("RA", seg.ra_deviations), ("DEC", seg.dec_deviations)):
                if len(devs) <= 100:
                    continue
                a = pente(seg.timestamps - seg.timestamps[0], devs)
                if a is None:
                    continue
                par_heure = a * 3600.0
                if abs(par_heure) <= 15.0:
                    continue
                if precision_unguided:
                    recommendations.append(_("r_derive_modele", n=seg_idx + 1,
                                             axe=axe, v=par_heure))
                elif axe == "RA":
                    recommendations.append(_("r_derive_ad_polaire", n=seg_idx + 1,
                                             v=par_heure))
                else:
                    recommendations.append(_("r_derive_dec_polaire", n=seg_idx + 1,
                                             v=par_heure))

        # Environment-based recommendations
        if has_env:
            valid_temp = s.env_temperature_ext[~np.isnan(s.env_temperature_ext)] if len(s.env_temperature_ext) > 0 else np.array([])
            if len(valid_temp) > 1 and abs(valid_temp[-1] - valid_temp[0]) > 5.0:
                recommendations.append(
                    _("r_temperature", v=abs(valid_temp[-1] - valid_temp[0])))

            valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
            if len(valid_polar) > 0 and valid_polar[0] * 60.0 > 5.0:
                recommendations.append(_("r_polaire", v=valid_polar[0] * 60))

        if not recommendations:
            recommendations.append(_("aucun_probleme"))

        for r in recommendations:
            lines.append(f"  {r}")
        lines.append("")

        # Final separator
        lines.append("=" * 70)
        lines.append(f"  {_('genere_le')} {datetime.now().strftime('%d/%m/%Y')} "
                     f"{_('a_heure')} {datetime.now().strftime('%H:%M:%S')}")
        lines.append("=" * 70)

        texte = "\n".join(lines)
        if langue is None:
            # Appel normal : on remplit la fenetre. Appel pour une autre langue
            # (les onglets, la sauvegarde) : on rend seulement le texte.
            self._report_text = texte
            if getattr(self, '_report', None) is not None:
                self._report.setPlainText(texte)
                self._report.moveCursor(QTextCursor.MoveOperation.Start)
        return texte

    def _section_mouvements(self, s, lg) -> list:
        """Dither, re-centering, and moves the mount did not recover from.

        Kept strictly apart from the tracking figures. A sequencer that
        dithers every frame must not come out worse than one that never
        does, so none of this touches the jitter -- that is measured between
        moves, with a margin after each.
        """
        def _(cle, **kw):
            return R(cle, lg, **kw)

        mv = getattr(s, 'mouvements', None) or []
        lines = ["=" * 70, "  " + _("t_mouvements"), "=" * 70, "",
                 "  " + _("mv_intro"), ""]
        if not mv:
            lines += ["  " + _("mv_aucun"), ""]
            return lines

        import numpy as _np
        amp = _np.array([m.amplitude for m in mv])
        dur = _np.array([m.duree for m in mv])
        classes = [m.classe for m in mv]
        n_d = classes.count("dither")
        n_r = classes.count("recentrage")
        n_a = classes.count("anomalie")

        lines.append(f"  {_('mv_total'):<34} : {len(mv)}")
        if n_d:
            lines.append(f"  {_('mv_dither'):<34} : {n_d}")
        if n_r:
            lines.append(f"  {_('mv_recentrage'):<34} : {n_r}")
        if n_a:
            lines.append(f"  {_('mv_anomalie'):<34} : {n_a}")
        lines.append("")
        lines.append(f"  {_('mv_amplitude'):<34} : {_np.median(amp):.2f}\"")
        lines.append(f"  {_('mv_max'):<34} : {amp.max():.2f}\"")
        lines.append(f"  {_('mv_duree'):<34} : {_np.median(dur):.1f} s")
        if len(mv) > 1:
            ecarts = _np.diff(sorted(m.instant for m in mv))
            ecarts = ecarts[ecarts > 0]
            if len(ecarts):
                lines.append(f"  {_('mv_cadence'):<34} : {_np.median(ecarts):.0f} s")
        lines.append("")
        lines.append("  " + _("mv_hors_jitter"))
        if n_a:
            lines.append("  " + _("mv_anomalie_detail"))
        lines.append("")
        return lines

    def _section_nuit(self, s, lg) -> list:
        """Sunset, twilights and how much of the night the session covers.

        Computed from the site the mount reported, stored in the .dat header
        so that it still works on replay. Without a site there is nothing to
        say, and saying where to set one is more use than an empty section.
        """
        def _(cle, **kw):
            return T(cle, lg) if not kw else T(cle, lg).format(**kw)

        lines = ["=" * 70, "  " + _("t_nuit"), "=" * 70, ""]
        lat = getattr(s, 'site_lat', None)
        lon = getattr(s, 'site_lon', None)
        if lat is None or lon is None:
            lines += ["  " + _("nuit_pas_de_site"), ""]
            return lines

        from ..core.ephemerides import nuit_autour
        from datetime import datetime, timezone, timedelta
        debut = getattr(s, 'start_iso', None)
        if debut is None:
            lines += ["  " + _("nuit_pas_de_site"), ""]
            return lines
        try:
            n = nuit_autour(debut, lat, lon)
        except Exception:
            return lines[:0]

        tz = debut.tzinfo or timezone.utc

        def hl(t):
            return t.astimezone(tz).strftime('%H:%M') if t else '--:--'

        elev = getattr(s, 'site_elev', None)
        elev_s = f"  {elev:.0f} m" if elev else ""
        lines.append(f"  {_('nuit_site'):<34} : {lat:+.4f}  {lon:+.4f}{elev_s}")
        lines.append("")
        lines.append(f"  {_('nuit_coucher'):<34} : {hl(n.coucher)}")
        lines.append(f"  {_('nuit_nautique'):<34} : {hl(n.nautique)}")
        if n.nuit_noire:
            d = n.duree_noire
            lines.append(f"  {_('nuit_noire'):<34} : {hl(n.astro_debut)} "
                         f"-> {hl(n.astro_fin)}")
            lines.append(f"  {_('nuit_duree_noire'):<34} : "
                         f"{int(d.total_seconds() // 3600)} h "
                         f"{int((d.total_seconds() % 3600) // 60):02d}")
        else:
            lines.append("  " + _("nuit_pas_de_nuit_noire"))
        lines.append(f"  {_('nuit_lever'):<34} : {hl(n.lever)}")
        lines.append("")

        # How much of the dark night the session actually holds. A session
        # that starts an hour late loses an hour that cannot be recovered,
        # and that is worth seeing next to the tracking figures.
        if n.nuit_noire and len(s.timestamps) > 1:
            fin = debut + timedelta(seconds=float(s.timestamps[-1] - s.timestamps[0]))
            recouvre = (min(fin, n.astro_fin) - max(debut, n.astro_debut))
            secs = max(0.0, recouvre.total_seconds())
            total = n.duree_noire.total_seconds()
            lines.append(f"  {_('nuit_couverture'):<34} : "
                         f"{int(secs // 3600)} h {int((secs % 3600) // 60):02d} "
                         f"/ {int(total // 3600)} h {int((total % 3600) // 60):02d}"
                         f"  ({100 * secs / total:.0f} %)")
            avant = (min(fin, n.astro_debut) - debut).total_seconds()
            if avant > 300:
                lines.append(f"      {int(avant // 3600)} h "
                             f"{int((avant % 3600) // 60):02d} {_('nuit_avant')}")
            apres = (fin - max(debut, n.astro_fin)).total_seconds()
            if apres > 300:
                lines.append(f"      {int(apres // 3600)} h "
                             f"{int((apres % 3600) // 60):02d} {_('nuit_apres')}")
            lines.append("")
        return lines

    def _write_axis_stats(self, lines: list, axis_name: str,
                          deviations: np.ndarray, timestamps: np.ndarray,
                          stdevs: np.ndarray, fr: bool,
                          precision_unguided: bool = False, lg: str = 'en'):
        def _(cle, **kw):
            return R(cle, lg, **kw)
        """Write statistics for one axis (RA or DEC)."""
        if len(deviations) == 0:
            return

        rms = float(np.std(deviations))
        # Jitter = deviations with the linear drift removed. On a long segment the
        # raw RMS is dominated by the drift (a linear ramp of amplitude A has an
        # RMS of A/sqrt(12)), which says nothing about what a single exposure sees.
        jitter = rms
        if len(deviations) >= 8:
            from ..logging_module.log_parser import TargetSegment
            jitter = TargetSegment().jitter(deviations)
        lines.append(f"  --- {axis_name} ---")
        lines.append(f"  {_('dev_moyenne'):<34} : {np.mean(deviations):+.4f}\"")
        lines.append(f"  {_('dev_mediane'):<34} : {np.median(deviations):+.4f}\"")
        lines.append(f"  {_('jitter_entre'):<34} : {jitter:.4f}\"   {_('etale_la_pose')}")
        lines.append(f"  {_('rms_brut_court'):<34} : {rms:.4f}\"")
        lines.append(f"  {_('pic_a_pic'):<34} : {np.ptp(deviations):.4f}\"")
        lines.append(f"  {_('dev_min'):<34} : {np.min(deviations):+.4f}\"")
        lines.append(f"  {_('dev_max'):<34} : {np.max(deviations):+.4f}\"")
        lines.append(f"  {'95e ' + _('percentile'):<34} : {np.percentile(np.abs(deviations), 95):.4f}\"")
        lines.append(f"  {'99e ' + _('percentile'):<34} : {np.percentile(np.abs(deviations), 99):.4f}\"")
        lines.append("")

        # A median that lands exactly on zero means more than half the samples
        # read identically: the mount reports its position on a finite grid
        # (0.01 s in RA, 0.1" in DEC for a 10Micron). Worth saying, because it
        # bounds how small a deviation this file can possibly show.
        _q = float(np.median(np.abs(np.diff(np.unique(np.sort(deviations)))))) \
            if len(np.unique(deviations)) > 2 else 0.0
        if _q > 0:
            lines.append(f"  {_('resolution_lecture'):<34} : {_q:.3f}\"")
            if jitter < 2 * _q:
                lines.append("      " + _("limite_resolution"))
        lines.append("")

        # Running STDEV statistics
        if len(stdevs) > 0 and np.any(stdevs > 0):
            valid_stdevs = stdevs[stdevs > 0]
            lines.append(f"  {_('stdev_moy'):<34} : {np.mean(valid_stdevs):.4f}\"")
            lines.append(f"  {_('stdev_max'):<34} : {np.max(valid_stdevs):.4f}\"")
            lines.append(f"  {_('stdev_med'):<34} : {np.median(valid_stdevs):.4f}\"")
            lines.append("")

        # Drift analysis
        #
        # La regression n'a de sens que si le temps avance. Sur un fichier
        # tronque, ou sur une session tenant dans la meme seconde, tous les
        # instants sont egaux : l'ajustement devient degenere et numpy leve
        # « SVD did not converge » — au milieu de la construction du rapport,
        # dont l'ouverture d'un fichier .dat n'est pas protegee. Un rapport
        # qui ne peut pas calculer une pente le dit ; il ne fait pas tomber
        # l'application.
        if len(deviations) > 100 and len(timestamps) == len(deviations):
            t_rel = timestamps - timestamps[0]
            a = pente(t_rel, deviations)
            if a is None:
                lines.append("  " + _("derive_non_calculable"))
                lines.append("")
                return
            drift_per_min = a * 60.0
            drift_per_hour = a * 3600.0
            lines.append(f"  {_('taux_derive'):<34} : {drift_per_min:+.4f}\"/min ({drift_per_hour:+.2f}\"/h)")

            # What a drift actually costs is what it moves a star DURING one
            # exposure — not its hourly figure, which every dither cancels.
            mv180 = abs(drift_per_hour) * 180.0 / 3600.0
            lines.append(f"      = {mv180:.2f}\" {_('sur_pose_180')}")

            if abs(drift_per_hour) > 15.0:
                if precision_unguided:
                    lines.append("  " + _("derive_forte_modele", axe=axis_name))
                    lines.append("      " + _("derive_forte_modele_note"))
                elif axis_name == "RA":
                    lines.append("  " + _("derive_forte_ad"))
                else:
                    lines.append("  " + _("derive_forte_dec"))
            elif abs(drift_per_hour) > 5.0:
                lines.append("  " + _("derive_sans_effet", axe=axis_name))
            elif abs(drift_per_hour) > 1.0:
                lines.append("  " + _("derive_legere", axe=axis_name))
            else:
                lines.append("  " + _("derive_nulle", axe=axis_name))
            lines.append("")
        lines.append("")

    def _write_fft(self, lines: list, axis_name: str,
                   deviations: np.ndarray, sample_rate: float,
                   fr: bool, top_n: int = 5, lg: str = 'en'):
        def _(cle, **kw):
            return R(cle, lg, **kw)
        """Write FFT analysis for one axis."""
        if len(deviations) < 64 or sample_rate <= 0:
            return

        data = deviations - np.mean(deviations)
        window = np.hanning(len(data))
        windowed = data * window
        n = len(windowed)
        fft_result = np.fft.rfft(windowed)
        magnitudes = 2.0 / n * np.abs(fft_result)
        frequencies = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        freqs = frequencies[1:]
        mags = magnitudes[1:]

        if len(mags) == 0:
            return

        peak_indices = np.argsort(mags)[::-1][:top_n]

        lines.append(_("fft_pics", axe=axis_name, n=top_n) + " :")
        lines.append(f"  {'Rank':>4}  {'Frequency':>12}  {'Period':>12}  {'Amplitude':>12}")
        lines.append(f"  {'----':>4}  {'----------':>12}  {'------':>12}  {'---------':>12}")

        for rank, idx in enumerate(peak_indices, 1):
            freq = freqs[idx]
            period = 1.0 / freq if freq > 0 else float('inf')
            amp = mags[idx]

            if period > 3600:
                period_str = f"{period/3600:.1f} h"
            elif period > 60:
                period_str = f"{period/60:.1f} min"
            else:
                period_str = f"{period:.1f} s"

            lines.append(f"  #{rank:>3}  {freq:>10.5f} Hz  {period_str:>12}  {amp:>10.4f}\"")

        lines.append("")

        # Identify PE in typical 2-15 min range
        dominant_idx = peak_indices[0]
        dominant_freq = freqs[dominant_idx]
        dominant_period = 1.0 / dominant_freq if dominant_freq > 0 else 0
        dominant_amp = mags[dominant_idx]

        if 120 < dominant_period < 900:
            lines.append(f"  [PE] " + _("pe_detectee"))
            lines.append(f"        {_('periode')} : {dominant_period:.1f} s ({dominant_period/60:.1f} min)")
            lines.append(f"        Amplitude : {dominant_amp:.4f}\"")
            if dominant_amp < 0.5:
                lines.append("        " + _("pe_tres_faible"))
            elif dominant_amp < 1.5:
                lines.append("        " + _("pe_acceptable"))
            else:
                lines.append("        " + _("pe_elevee"))
        else:
            lines.append("  " + _("pas_ep_typique"))
        lines.append("")

    def _export_report(self):
        """Export the report shown in the current tab."""
        title = R("exporter_rapport", self._lang)

        # La langue exportee est celle de l'onglet affiche, pas celle de
        # l'interface : on exporte ce qu'on a sous les yeux.
        code = self._lang
        for c, vue in getattr(self, '_vues', {}).items():
            if vue is self._onglets.currentWidget():
                code = c
                break
        texte = self._rapports.get(code, getattr(self, '_report_text', ''))

        default_name = "MountMonitor_Analysis"
        if self._session.start_time:
            default_name += f"_{self._session.start_time.strftime('%Y%m%d')}"
        default_name += f"_{code}.txt"

        path, _ignore = QFileDialog.getSaveFileName(
            self, title, default_name,
            "Text Files (*.txt);;All Files (*)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(texte)
                logger.info(f"Analysis report exported to {path}")
            except OSError as e:
                logger.error(f"Failed to export report: {e}")
