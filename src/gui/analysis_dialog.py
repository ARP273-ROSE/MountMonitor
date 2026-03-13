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
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QProgressBar, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor

from ..logging_module.log_parser import ParsedSession, TargetSegment
from ..utils.i18n import T, get_language
from ..utils.coordinates import format_ra, format_dec

logger = logging.getLogger(__name__)


def _rating_emoji(rating: str) -> str:
    """Return bilingual text indicator for quality rating."""
    mapping = {
        'excellent': '[EXCELLENT]',
        'good': '[GOOD / BON]',
        'fair': '[FAIR / MOYEN]',
        'poor': '[POOR / MAUVAIS]',
    }
    return mapping.get(rating, rating)


def _rating_color(rating: str) -> str:
    """Return HTML color for rating."""
    return {
        'excellent': '#00ff88',
        'good': '#88ff00',
        'fair': '#ffaa00',
        'poor': '#ff4444',
    }.get(rating, '#ffffff')


def _bi(en: str, fr: str, lang: str) -> str:
    """Return bilingual string: both EN and FR always shown."""
    if lang == 'fr':
        return f"{fr} / {en}"
    return f"{en} / {fr}"


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


class AnalysisDialog(QDialog):
    """Comprehensive session analysis dialog."""

    def __init__(self, session: ParsedSession, parent=None):
        super().__init__(parent)
        self._session = session
        self._lang = get_language()
        self._setup_ui()
        self._run_analysis()

    def _setup_ui(self):
        title = _bi("Session Analysis — MountMonitor",
                     "Analyse de session — MountMonitor", self._lang)
        self.setWindowTitle(title)
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel()
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #88ccff; margin: 8px;")
        header.setText(_bi("Night Session Analysis Report",
                           "Rapport d'analyse de la nuit", self._lang))
        header.setToolTip(
            "EN: Comprehensive analysis of the recorded session\n"
            "FR: Analyse complète de la session enregistrée"
        )
        layout.addWidget(header)

        # Report text area
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("Consolas", 10))
        self._report.setStyleSheet(
            "QTextEdit { background: #1a1a2e; color: #e0e0e0; "
            "border: 1px solid #333; padding: 8px; }"
        )
        self._report.setToolTip(
            "EN: Full analysis report text\n"
            "FR: Texte complet du rapport d'analyse"
        )
        layout.addWidget(self._report)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_export = QPushButton(
            _bi("Export TXT", "Exporter TXT", self._lang)
        )
        btn_export.setToolTip(
            "EN: Export analysis report as text file\n"
            "FR: Exporter le rapport d'analyse en fichier texte"
        )
        btn_export.clicked.connect(self._export_report)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_close = QPushButton(
            _bi("Close", "Fermer", self._lang)
        )
        btn_close.setToolTip(
            "EN: Close analysis window\n"
            "FR: Fermer la fenêtre d'analyse"
        )
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _run_analysis(self):
        """Run the complete analysis and populate the report."""
        s = self._session
        fr = self._lang == 'fr'
        lines = []

        # ═══════════════════════════════════════════════════════════
        # 1. SESSION OVERVIEW
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  SESSION OVERVIEW / APERCU DE LA SESSION")
        lines.append("=" * 70)
        lines.append("")

        if s.start_time:
            lines.append(f"  Date           : {s.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
        lines.append(f"  Observatory    : {s.observatory or 'N/A'}")
        lines.append(f"  Mount          : {s.mount_name or 'N/A'}")
        if s.firmware:
            lines.append(f"  Firmware       : {s.firmware}")
        lines.append(f"  Duration / Durée : {s.duration_str}")
        lines.append(f"  Total samples / Échantillons totaux : {s.sample_count:,}")
        lines.append(f"  Tracking samples / Échantillons suivi : {s.tracking_sample_count:,}")
        if s.effective_frequency > 0:
            lines.append(f"  Sample rate / Fréquence : {s.effective_frequency:.2f} Hz")
        lines.append(f"  Targets / Cibles : {len(s.target_segments)}")
        lines.append(f"  File / Fichier : {s.file_path}")
        lines.append("")

        if s.sample_count == 0:
            lines.append("  [!] No data to analyze / Aucune donnée à analyser")
            self._report.setPlainText("\n".join(lines))
            return

        if s.tracking_sample_count == 0:
            lines.append("  [!] No TRACKING data found / Aucune donnée de suivi trouvée")
            lines.append("      Only SLEWING/PARKED/IDLE samples in file.")
            lines.append("      Seuls des échantillons SLEWING/PARKED/IDLE dans le fichier.")
            self._report.setPlainText("\n".join(lines))
            return

        # ═══════════════════════════════════════════════════════════
        # 2. OVERALL QUALITY RATING (combined from all segments)
        # ═══════════════════════════════════════════════════════════
        ra_rms = float(np.std(s.ra_deviations)) if len(s.ra_deviations) > 0 else 999
        dec_rms = float(np.std(s.dec_deviations)) if len(s.dec_deviations) > 0 else 999
        combined_rms = np.sqrt(ra_rms**2 + dec_rms**2)

        # Detect mount type and adapt scoring thresholds
        # Unguided precision mounts (10Micron, Planewave) report coordinate-level
        # deviations that are naturally larger than guided mounts. Their tracking
        # quality is excellent even at 2-4" RMS as measured by MountMonitor.
        precision_unguided = _is_precision_unguided_mount(s)
        if precision_unguided:
            # Adapted thresholds for unguided precision mounts
            if combined_rms < 2.0:
                rating = 'excellent'
            elif combined_rms < 4.0:
                rating = 'good'
            elif combined_rms < 8.0:
                rating = 'fair'
            else:
                rating = 'poor'
        else:
            # Standard thresholds for guided mounts
            if combined_rms < 0.5:
                rating = 'excellent'
            elif combined_rms < 1.5:
                rating = 'good'
            elif combined_rms < 3.0:
                rating = 'fair'
            else:
                rating = 'poor'

        rating_text = _rating_emoji(rating)

        lines.append("=" * 70)
        lines.append("  OVERALL QUALITY / QUALITE GLOBALE")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"  Rating / Note      : {rating_text}")
        lines.append(f"  Combined RMS       : {combined_rms:.3f}\"")
        lines.append(f"  RA RMS             : {ra_rms:.3f}\"")
        lines.append(f"  DEC RMS            : {dec_rms:.3f}\"")
        if precision_unguided:
            lines.append(f"  Mount type         : Precision unguided / Précision non-guidée")
            lines.append(f"  Thresholds adapted / Seuils adaptés : Exc <2.0\" | Good <4.0\" | Fair <8.0\"")
        else:
            lines.append(f"  Thresholds / Seuils : Exc <0.5\" | Good <1.5\" | Fair <3.0\"")
        lines.append("")

        if rating == 'excellent':
            if precision_unguided:
                lines.append("  Excellent tracking for unguided mount! Model-corrected pointing is precise.")
                lines.append("  Suivi excellent pour monture non-guidée ! Le pointage corrigé par modèle est précis.")
            else:
                lines.append("  Your tracking is excellent! Stars will be perfectly round.")
                lines.append("  Votre suivi est excellent ! Étoiles parfaitement ponctuelles.")
        elif rating == 'good':
            if precision_unguided:
                lines.append("  Good tracking. Normal performance for unguided precision mount.")
                lines.append("  Bon suivi. Performance normale pour monture de précision non-guidée.")
            else:
                lines.append("  Good tracking. Satisfactory for most focal lengths.")
                lines.append("  Bon suivi. Résultats satisfaisants pour la plupart des focales.")
        elif rating == 'fair':
            if precision_unguided:
                lines.append("  Fair tracking. Consider re-running alignment model or checking balance.")
                lines.append("  Suivi moyen. Refaites le modèle d'alignement ou vérifiez l'équilibrage.")
            else:
                lines.append("  Fair tracking. Visible on long exposures at high focal lengths.")
                lines.append("  Suivi moyen. Visible sur les longues poses à haute focale.")
                lines.append("  Check polar alignment. / Vérifiez l'alignement polaire.")
        else:
            if precision_unguided:
                lines.append("  Poor tracking for precision mount. Rebuild alignment model.")
                lines.append("  Suivi insuffisant pour monture de précision. Refaites le modèle d'alignement.")
                lines.append("  Check: model quality, balance, axis play, temperature changes.")
                lines.append("  Vérifiez : qualité du modèle, équilibrage, jeu d'axes, variations thermiques.")
            else:
                lines.append("  Poor tracking. Stars likely elongated.")
                lines.append("  Suivi insuffisant. Étoiles probablement allongées.")
                lines.append("  Check: polar alignment, tightness, balance.")
                lines.append("  Vérifiez : alignement polaire, serrage, équilibrage.")
        lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 3. PER-TARGET ANALYSIS
        # ═══════════════════════════════════════════════════════════
        for seg_idx, seg in enumerate(s.target_segments):
            lines.append("=" * 70)
            ra_str = format_ra(seg.ra_median_hours)
            dec_str = format_dec(seg.dec_median_degrees)
            lines.append(f"  TARGET / CIBLE #{seg_idx + 1}  —  RA {ra_str}  DEC {dec_str}  "
                         f"({seg.sample_count:,} samples / échantillons)")
            lines.append("=" * 70)
            lines.append("")

            self._write_axis_stats(lines, "RA", seg.ra_deviations,
                                   seg.timestamps, seg.ra_stdevs, fr)
            self._write_axis_stats(lines, "DEC", seg.dec_deviations,
                                   seg.timestamps, seg.dec_stdevs, fr)

            # FFT for this segment
            if len(seg.ra_deviations) > 64:
                freq = len(seg.ra_deviations) / max(1.0, seg.timestamps[-1] - seg.timestamps[0])
                self._write_fft(lines, "RA", seg.ra_deviations, freq, fr, top_n=5)
            if len(seg.dec_deviations) > 64:
                freq = len(seg.dec_deviations) / max(1.0, seg.timestamps[-1] - seg.timestamps[0])
                self._write_fft(lines, "DEC", seg.dec_deviations, freq, fr, top_n=3)

            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # If no segments but we have combined data, show combined stats
        # ═══════════════════════════════════════════════════════════
        if not s.target_segments and len(s.ra_deviations) > 0:
            lines.append("=" * 70)
            lines.append("  RIGHT ASCENSION (RA) / ASCENSION DROITE (AD)")
            lines.append("=" * 70)
            lines.append("")
            self._write_axis_stats(lines, "RA", s.ra_deviations,
                                   s.tracking_timestamps, s.tracking_ra_stdevs, fr)
            lines.append("=" * 70)
            lines.append("  DECLINATION (DEC) / DECLINAISON (DEC)")
            lines.append("=" * 70)
            lines.append("")
            self._write_axis_stats(lines, "DEC", s.dec_deviations,
                                   s.tracking_timestamps, s.tracking_dec_stdevs, fr)

        # ═══════════════════════════════════════════════════════════
        # 4. AXIAL DATA
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_axis) > 10 and np.any(s.ra_axis != 0):
            lines.append("=" * 70)
            lines.append("  AXIAL DATA / DONNEES AXIALES")
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
            lines.append("  TIME SYNCHRONIZATION / SYNCHRONISATION TEMPORELLE")
            lines.append("=" * 70)
            lines.append("")

            td = s.time_pc_mount_diff
            lines.append(f"  PC-Mount diff avg  : {np.mean(td):+.1f} ms")
            lines.append(f"  PC-Mount diff med  : {np.median(td):+.1f} ms")
            lines.append(f"  PC-Mount diff max  : {np.max(np.abs(td)):.1f} ms")
            lines.append(f"  PC-Mount diff std  : {np.std(td):.1f} ms")

            if len(td) > 100:
                t_rel = s.time_timestamps - s.time_timestamps[0]
                coeffs = np.polyfit(t_rel, td, 1)
                drift_per_min = coeffs[0] * 60.0
                lines.append(f"  Clock drift rate / Dérive horloge : {drift_per_min:+.3f} ms/min")
                if abs(drift_per_min) > 1.0:
                    lines.append("  [!] Significant clock drift detected / Dérive d'horloge significative détectée")
                else:
                    lines.append("  [OK] Stable clock / Horloge stable")
            lines.append("")

            if len(s.time_pc_loop) > 0:
                pl = s.time_pc_loop
                lines.append(f"  PC loop avg        : {np.mean(pl):.1f} ms")
                lines.append(f"  PC loop max        : {np.max(pl):.1f} ms")
                lines.append(f"  PC loop std        : {np.std(pl):.1f} ms")
                if np.mean(pl) > 1000:
                    lines.append("  [!] Slow PC loop / Boucle PC lente — PC struggling / Le PC a du mal")
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
                        lines.append("  [!] Large NTP offset / Décalage NTP important — synchronize PC clock / synchronisez l'horloge PC")
                    lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 6. TRACKING STATUS
        # ═══════════════════════════════════════════════════════════
        if s.statuses:
            lines.append("=" * 70)
            lines.append("  TRACKING STATUS / STATUT DE SUIVI")
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
                lines.append(f"  [!] Only {tracking_pct:.0f}% tracking / Seulement {tracking_pct:.0f}% en suivi")
                lines.append("      Mount spent significant time not tracking.")
                lines.append("      La monture a passé beaucoup de temps hors suivi.")
            else:
                lines.append(f"  [OK] {tracking_pct:.0f}% tracking / en suivi — normal")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 7. TOLERANCE ANALYSIS (TRACKING data only)
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_deviations) > 0:
            lines.append("=" * 70)
            lines.append("  TOLERANCE ANALYSIS / ANALYSE DES TOLERANCES")
            lines.append("  (TRACKING data only / Données de suivi uniquement)")
            lines.append("=" * 70)
            lines.append("")

            for tol in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
                ra_exceed = np.sum(np.abs(s.ra_deviations) > tol)
                dec_exceed = np.sum(np.abs(s.dec_deviations) > tol)
                ra_pct = ra_exceed / len(s.ra_deviations) * 100
                dec_pct = dec_exceed / len(s.dec_deviations) * 100
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
            lines.append("  DATA CONTINUITY / CONTINUITE DES DONNEES")
            lines.append("=" * 70)
            lines.append("")

            dt = np.diff(s.timestamps)
            expected_dt = 1.0 / s.effective_frequency if s.effective_frequency > 0 else 0.5

            gaps = dt[dt > expected_dt * 5]
            if len(gaps) > 0:
                lines.append(f"  Gaps detected / Coupures détectées : {len(gaps)}")
                lines.append(f"  Largest gap / Plus grande coupure  : {np.max(gaps):.1f} s")
                lines.append(f"  Total gap time / Temps total perdu : {np.sum(gaps):.1f} s")
                lines.append("  [i] Data acquisition interruptions detected")
                lines.append("      Des interruptions d'acquisition ont été détectées")
                lines.append("      (slewing, reconnection, network issue / réseau...)")
            else:
                lines.append("  [OK] Continuous acquisition, no gaps detected")
                lines.append("       Acquisition continue, pas de coupure détectée")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 9. ENVIRONMENT & DIAGNOSTICS
        # ═══════════════════════════════════════════════════════════
        has_env = len(s.env_timestamps) > 0
        if has_env:
            lines.append("=" * 70)
            lines.append("  ENVIRONMENT & DIAGNOSTICS / ENVIRONNEMENT & DIAGNOSTICS")
            lines.append("=" * 70)
            lines.append("")

            temp = s.env_temperature_ext
            valid_temp = temp[~np.isnan(temp)] if len(temp) > 0 else np.array([])
            if len(valid_temp) > 0:
                lines.append(f"  Temperature (ext)  : {valid_temp[0]:.1f}°C -> {valid_temp[-1]:.1f}°C")
                lines.append(f"  Temp range         : {np.min(valid_temp):.1f}°C — {np.max(valid_temp):.1f}°C")
                temp_delta = valid_temp[-1] - valid_temp[0]
                lines.append(f"  Temp change        : {temp_delta:+.1f}°C over session / pendant la session")
                if abs(temp_delta) > 5.0:
                    lines.append("  [!] Large temperature change — may affect focus and tracking")
                    lines.append("      Variation thermique importante — peut affecter la mise au point et le suivi")
                elif abs(temp_delta) > 2.0:
                    lines.append("  [i] Moderate temperature change — monitor focus")
                    lines.append("      Variation thermique modérée — surveillez la mise au point")
                else:
                    lines.append("  [OK] Stable temperature / Température stable")
                lines.append("")

            temp_int = s.env_temperature_int
            valid_int = temp_int[~np.isnan(temp_int)] if len(temp_int) > 0 else np.array([])
            if len(valid_int) > 0:
                lines.append(f"  Internal temp      : {valid_int[0]:.1f}°C -> {valid_int[-1]:.1f}°C")
                lines.append(f"  Internal range     : {np.min(valid_int):.1f}°C — {np.max(valid_int):.1f}°C")
                int_delta = valid_int[-1] - valid_int[0]
                if int_delta > 10.0:
                    lines.append("  [!] Mount heating significantly — check ventilation")
                    lines.append("      La monture chauffe significativement — vérifiez la ventilation")
                lines.append("")

            pres = s.env_pressure
            valid_pres = pres[~np.isnan(pres)] if len(pres) > 0 else np.array([])
            if len(valid_pres) > 0:
                lines.append(f"  Pressure / Pression : {valid_pres[0]:.1f} -> {valid_pres[-1]:.1f} mbar")
                lines.append(f"  Pressure range      : {np.min(valid_pres):.1f} — {np.max(valid_pres):.1f} mbar")
                pres_delta = valid_pres[-1] - valid_pres[0]
                lines.append(f"  Pressure change     : {pres_delta:+.1f} mbar")
                if abs(pres_delta) > 5.0:
                    lines.append("  [i] Notable barometric change — weather conditions changing")
                    lines.append("      Changement barométrique notable — conditions météo changeantes")
                lines.append("")

            valid_rms = s.env_alignment_rms[~np.isnan(s.env_alignment_rms)] if len(s.env_alignment_rms) > 0 else np.array([])
            if len(valid_rms) > 0:
                stars = s.env_alignment_stars
                valid_stars = [st for st in stars if st > 0]
                if valid_stars:
                    lines.append(f"  Alignment stars / Étoiles d'alignement : {valid_stars[0]}")
                lines.append(f"  Alignment RMS      : {valid_rms[0]:.1f}\"")

                valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
                if len(valid_polar) > 0:
                    polar_arcmin = valid_polar[0] * 60.0
                    lines.append(f"  Polar error / Erreur polaire : {valid_polar[0]:.4f}° ({polar_arcmin:.1f}')")
                    if polar_arcmin > 5.0:
                        lines.append("  [!] High polar error — redo polar alignment")
                        lines.append("      Erreur polaire élevée — refaites l'alignement polaire")
                    elif polar_arcmin > 1.0:
                        lines.append("  [i] Moderate polar error — acceptable for most use cases")
                        lines.append("      Erreur polaire modérée — acceptable pour la plupart des usages")
                    else:
                        lines.append("  [OK] Excellent polar alignment / Alignement polaire excellent")
                lines.append("")

            rates = s.env_tracking_rates
            valid_rates = rates[~np.isnan(rates)] if len(rates) > 0 else np.array([])
            if len(valid_rates) > 1:
                rate_std = np.std(valid_rates)
                lines.append(f"  Tracking rate avg  : {np.mean(valid_rates):.2f}")
                lines.append(f"  Tracking rate std  : {rate_std:.4f}")
                if rate_std > 0.1:
                    lines.append("  [i] Tracking rate variation detected / Variation du taux de suivi détectée")
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
                lines.append("  Mount status codes / Codes statut monture (10Micron :Gstat#) :")
                for code, count in code_counts.most_common():
                    name = status_names.get(code, f"Code {code}")
                    lines.append(f"    {code} = {name:<30} : {count}x")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 10. EVENTS
        # ═══════════════════════════════════════════════════════════
        if s.events:
            lines.append("=" * 70)
            lines.append("  EVENT LOG / JOURNAL DES EVENEMENTS")
            lines.append("=" * 70)
            lines.append("")

            tolerance_events = [e for e in s.events if 'TOLERANCE' in e[1]]
            warning_events = [e for e in s.events if 'WARNING' in e[1] or 'Check WARNING' in e[1]]
            status_events = [e for e in s.events if 'Mount status' in e[1]]

            lines.append(f"  Total events / Événements totaux : {len(s.events)}")
            lines.append(f"  Tolerance alerts / Alertes tolérance : {len(tolerance_events)}")
            lines.append(f"  Warnings / Avertissements : {len(warning_events)}")
            lines.append(f"  Status changes / Changements de statut : {len(status_events)}")
            lines.append("")

            if tolerance_events:
                lines.append("  Tolerance events (first 10) / Événements de tolérance (10 premiers) :")
                for ts, msg in tolerance_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                if len(tolerance_events) > 10:
                    lines.append(f"    ... and {len(tolerance_events) - 10} more / et {len(tolerance_events) - 10} de plus")
                lines.append("")

            if warning_events:
                lines.append("  Warnings / Avertissements :")
                for ts, msg in warning_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 11. RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  RECOMMENDATIONS / RECOMMANDATIONS")
        lines.append("=" * 70)
        lines.append("")

        recommendations = []

        # Adapt recommendation thresholds for mount type
        ra_threshold = 5.0 if precision_unguided else 2.0
        dec_threshold = 5.0 if precision_unguided else 2.0

        if ra_rms > ra_threshold:
            if precision_unguided:
                recommendations.append(
                    f"- RA unstable (RMS > {ra_threshold}\"): rebuild alignment model, check RA balance\n"
                    f"  RA instable (RMS > {ra_threshold}\") : refaites le modèle d'alignement, vérifiez l'équilibrage RA"
                )
            else:
                recommendations.append(
                    "- RA unstable (RMS > 2\"): check RA balance, clamp tightness, cable drag\n"
                    "  RA instable (RMS > 2\") : vérifiez l'équilibrage RA, le serrage, les câbles"
                )

        if dec_rms > dec_threshold:
            if precision_unguided:
                recommendations.append(
                    f"- DEC unstable (RMS > {dec_threshold}\"): rebuild alignment model, check DEC balance\n"
                    f"  DEC instable (RMS > {dec_threshold}\") : refaites le modèle d'alignement, vérifiez l'équilibrage DEC"
                )
            else:
                recommendations.append(
                    "- DEC unstable (RMS > 2\"): check DEC balance, DEC axis backlash\n"
                    "  DEC instable (RMS > 2\") : vérifiez l'équilibrage DEC, le jeu dans l'axe DEC"
                )

        # Check drift per segment
        for seg_idx, seg in enumerate(s.target_segments):
            if len(seg.ra_deviations) > 100:
                t_rel = seg.timestamps - seg.timestamps[0]
                ra_coeffs = np.polyfit(t_rel, seg.ra_deviations, 1)
                ra_drift_h = ra_coeffs[0] * 3600.0
                if abs(ra_drift_h) > 5.0:
                    recommendations.append(
                        f"- Target #{seg_idx + 1}: RA drift {ra_drift_h:+.1f}\"/h — adjust azimuth of polar alignment\n"
                        f"  Cible #{seg_idx + 1} : dérive RA {ra_drift_h:+.1f}\"/h — ajustez l'azimut de l'alignement polaire"
                    )

            if len(seg.dec_deviations) > 100:
                t_rel = seg.timestamps - seg.timestamps[0]
                dec_coeffs = np.polyfit(t_rel, seg.dec_deviations, 1)
                dec_drift_h = dec_coeffs[0] * 3600.0
                if abs(dec_drift_h) > 5.0:
                    recommendations.append(
                        f"- Target #{seg_idx + 1}: DEC drift {dec_drift_h:+.1f}\"/h — adjust altitude of polar alignment\n"
                        f"  Cible #{seg_idx + 1} : dérive DEC {dec_drift_h:+.1f}\"/h — ajustez l'altitude de l'alignement polaire"
                    )

        # Environment-based recommendations
        if has_env:
            valid_temp = s.env_temperature_ext[~np.isnan(s.env_temperature_ext)] if len(s.env_temperature_ext) > 0 else np.array([])
            if len(valid_temp) > 1 and abs(valid_temp[-1] - valid_temp[0]) > 5.0:
                recommendations.append(
                    f"- Temperature drop of {abs(valid_temp[-1] - valid_temp[0]):.1f}°C: use motorized focuser with temp compensation\n"
                    f"  Chute de température de {abs(valid_temp[-1] - valid_temp[0]):.1f}°C : utilisez un focuser avec compensation thermique"
                )

            valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
            if len(valid_polar) > 0 and valid_polar[0] * 60.0 > 5.0:
                recommendations.append(
                    f"- Polar error of {valid_polar[0]*60:.1f}': redo polar alignment with PoleMaster or SharpCap\n"
                    f"  Erreur polaire de {valid_polar[0]*60:.1f}' : refaites l'alignement polaire"
                )

        if not recommendations:
            recommendations.append(
                "- No major issues detected. Continue with these settings!\n"
                "  Aucun problème majeur détecté. Continuez avec ces réglages !"
            )

        for r in recommendations:
            lines.append(f"  {r}")
        lines.append("")

        # Final separator
        lines.append("=" * 70)
        lines.append(f"  Report generated on / Rapport généré le {datetime.now().strftime('%d/%m/%Y')} "
                     f"at / à {datetime.now().strftime('%H:%M:%S')}")
        lines.append("=" * 70)

        self._report_text = "\n".join(lines)
        self._report.setPlainText(self._report_text)
        self._report.moveCursor(QTextCursor.MoveOperation.Start)

    def _write_axis_stats(self, lines: list, axis_name: str,
                          deviations: np.ndarray, timestamps: np.ndarray,
                          stdevs: np.ndarray, fr: bool):
        """Write statistics for one axis (RA or DEC)."""
        if len(deviations) == 0:
            return

        rms = float(np.std(deviations))
        lines.append(f"  --- {axis_name} ---")
        lines.append(f"  Mean deviation / Déviation moyenne   : {np.mean(deviations):+.4f}\"")
        lines.append(f"  Median deviation / Déviation médiane : {np.median(deviations):+.4f}\"")
        lines.append(f"  RMS (std dev)                        : {rms:.4f}\"")
        lines.append(f"  Peak-to-peak / Pic-à-pic             : {np.ptp(deviations):.4f}\"")
        lines.append(f"  Min deviation                        : {np.min(deviations):+.4f}\"")
        lines.append(f"  Max deviation                        : {np.max(deviations):+.4f}\"")
        lines.append(f"  95th percentile                      : {np.percentile(np.abs(deviations), 95):.4f}\"")
        lines.append(f"  99th percentile                      : {np.percentile(np.abs(deviations), 99):.4f}\"")
        lines.append("")

        # Running STDEV statistics
        if len(stdevs) > 0 and np.any(stdevs > 0):
            valid_stdevs = stdevs[stdevs > 0]
            lines.append(f"  Running STDEV avg  : {np.mean(valid_stdevs):.4f}\"")
            lines.append(f"  Running STDEV max  : {np.max(valid_stdevs):.4f}\"")
            lines.append(f"  Running STDEV med  : {np.median(valid_stdevs):.4f}\"")
            lines.append("")

        # Drift analysis
        if len(deviations) > 100 and len(timestamps) == len(deviations):
            t_rel = timestamps - timestamps[0]
            coeffs = np.polyfit(t_rel, deviations, 1)
            drift_per_min = coeffs[0] * 60.0
            drift_per_hour = coeffs[0] * 3600.0
            lines.append(f"  Drift rate / Taux de dérive : {drift_per_min:+.4f}\"/min ({drift_per_hour:+.2f}\"/h)")

            if abs(drift_per_hour) > 5.0:
                if axis_name == "RA":
                    lines.append("  [!] Significant RA drift — check polar alignment (azimuth)")
                    lines.append("      Dérive RA significative — vérifiez l'alignement polaire (azimut)")
                else:
                    lines.append("  [!] Significant DEC drift — check polar alignment (altitude)")
                    lines.append("      Dérive DEC significative — vérifiez l'alignement polaire (altitude)")
            elif abs(drift_per_hour) > 1.0:
                lines.append(f"  [i] Slight {axis_name} drift detected / Légère dérive {axis_name} détectée")
            else:
                lines.append(f"  [OK] No significant {axis_name} drift / Pas de dérive {axis_name} significative")
            lines.append("")
        lines.append("")

    def _write_fft(self, lines: list, axis_name: str,
                   deviations: np.ndarray, sample_rate: float,
                   fr: bool, top_n: int = 5):
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

        lines.append(f"  {axis_name} FFT — Top {top_n} peaks / pics dominants :")
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
            lines.append(f"  [PE] Periodic Error detected! / Erreur périodique détectée !")
            lines.append(f"        Period / Période : {dominant_period:.1f} s ({dominant_period/60:.1f} min)")
            lines.append(f"        Amplitude : {dominant_amp:.4f}\"")
            if dominant_amp < 0.5:
                lines.append("        => Very low PE, excellent! / PE très faible, excellent !")
            elif dominant_amp < 1.5:
                lines.append("        => Acceptable PE / PE acceptable")
            else:
                lines.append("        => High PE — consider PEC calibration / PE élevée — considérez la calibration PEC")
        else:
            lines.append("  [i] No typical periodic error in 2-15 min range")
            lines.append("      Pas d'erreur périodique typique dans la plage 2-15 min")
        lines.append("")

    def _export_report(self):
        """Export analysis report to a text file."""
        title = _bi("Export Report", "Exporter le rapport", self._lang)

        default_name = "MountMonitor_Analysis"
        if self._session.start_time:
            default_name += f"_{self._session.start_time.strftime('%Y%m%d')}"
        default_name += ".txt"

        path, _ = QFileDialog.getSaveFileName(
            self, title, default_name,
            "Text Files (*.txt);;All Files (*)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self._report_text)
                logger.info(f"Analysis report exported to {path}")
            except OSError as e:
                logger.error(f"Failed to export report: {e}")
