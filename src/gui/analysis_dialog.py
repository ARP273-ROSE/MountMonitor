"""Night session analysis dialog for MountMonitor.

Provides comprehensive analysis of a recorded session:
- Overall quality rating
- RA/DEC tracking statistics
- Periodic error detection via FFT
- Drift analysis
- Time synchronization analysis
- Event summary
- Detailed recommendations
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

from ..logging_module.log_parser import ParsedSession
from ..utils.i18n import T, get_language

logger = logging.getLogger(__name__)


def _rating_emoji(rating: str) -> str:
    """Return text indicator for quality rating (no emoji per CLAUDE.md)."""
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


class AnalysisDialog(QDialog):
    """Comprehensive session analysis dialog."""

    def __init__(self, session: ParsedSession, parent=None):
        super().__init__(parent)
        self._session = session
        self._lang = get_language()
        self._setup_ui()
        self._run_analysis()

    def _setup_ui(self):
        if self._lang == 'fr':
            title = "Analyse de session — MountMonitor"
        else:
            title = "Session Analysis — MountMonitor"
        self.setWindowTitle(title)
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel()
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #88ccff; margin: 8px;")
        if self._lang == 'fr':
            header.setText("Rapport d'analyse de la nuit")
        else:
            header.setText("Night Session Analysis Report")
        layout.addWidget(header)

        # Report text area
        self._report = QTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("Consolas", 10))
        self._report.setStyleSheet(
            "QTextEdit { background: #1a1a2e; color: #e0e0e0; "
            "border: 1px solid #333; padding: 8px; }"
        )
        layout.addWidget(self._report)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_export = QPushButton(
            "Export TXT" if self._lang == 'en'
            else "Exporter TXT"
        )
        btn_export.setToolTip(
            "EN: Export analysis report as text file\n"
            "FR: Exporter le rapport d'analyse en fichier texte"
        )
        btn_export.clicked.connect(self._export_report)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_close = QPushButton(
            "Close" if self._lang == 'en' else "Fermer"
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
        lines.append(f"  Duration       : {s.duration_str}")
        lines.append(f"  Samples        : {s.sample_count:,}")
        if s.effective_frequency > 0:
            lines.append(f"  Sample rate    : {s.effective_frequency:.2f} Hz")
        lines.append(f"  File           : {s.file_path}")
        lines.append("")

        if s.sample_count == 0:
            lines.append("  [!] No data to analyze / Aucune donnée à analyser")
            self._report.setPlainText("\n".join(lines))
            return

        # ═══════════════════════════════════════════════════════════
        # 2. OVERALL QUALITY RATING
        # ═══════════════════════════════════════════════════════════
        ra_rms = float(np.std(s.ra_deviations)) if len(s.ra_deviations) > 0 else 999
        dec_rms = float(np.std(s.dec_deviations)) if len(s.dec_deviations) > 0 else 999
        combined_rms = np.sqrt(ra_rms**2 + dec_rms**2)

        if combined_rms < 0.5:
            rating = 'excellent'
        elif combined_rms < 1.5:
            rating = 'good'
        elif combined_rms < 3.0:
            rating = 'fair'
        else:
            rating = 'poor'

        rating_color = _rating_color(rating)
        rating_text = _rating_emoji(rating)

        lines.append("=" * 70)
        lines.append("  OVERALL QUALITY / QUALITE GLOBALE")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"  Rating         : {rating_text}")
        lines.append(f"  Combined RMS   : {combined_rms:.3f}\"")
        lines.append(f"  RA RMS         : {ra_rms:.3f}\"")
        lines.append(f"  DEC RMS        : {dec_rms:.3f}\"")
        lines.append("")

        if fr:
            if rating == 'excellent':
                lines.append("  Votre suivi est excellent ! Les étoiles seront")
                lines.append("  parfaitement ponctuelles sur vos images.")
            elif rating == 'good':
                lines.append("  Bon suivi. Résultats satisfaisants pour la plupart")
                lines.append("  des focales. Quelques améliorations possibles.")
            elif rating == 'fair':
                lines.append("  Suivi moyen. Visible sur les longues poses avec")
                lines.append("  des focales élevées. Vérifiez l'alignement polaire.")
            else:
                lines.append("  Suivi insuffisant. Étoiles probablement allongées.")
                lines.append("  Vérifiez : alignement polaire, serrage, équilibrage.")
        else:
            if rating == 'excellent':
                lines.append("  Your tracking is excellent! Stars will be")
                lines.append("  perfectly round in your images.")
            elif rating == 'good':
                lines.append("  Good tracking. Satisfactory for most focal lengths.")
                lines.append("  Some improvements possible.")
            elif rating == 'fair':
                lines.append("  Fair tracking. Visible on long exposures at high")
                lines.append("  focal lengths. Check polar alignment.")
            else:
                lines.append("  Poor tracking. Stars likely elongated.")
                lines.append("  Check: polar alignment, tightness, balance.")
        lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 3. RIGHT ASCENSION ANALYSIS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  RIGHT ASCENSION (RA) / ASCENSION DROITE (AD)")
        lines.append("=" * 70)
        lines.append("")

        if len(s.ra_deviations) > 0:
            ra = s.ra_deviations
            lines.append(f"  Mean deviation     : {np.mean(ra):+.4f}\"")
            lines.append(f"  Median deviation   : {np.median(ra):+.4f}\"")
            lines.append(f"  RMS (std dev)      : {ra_rms:.4f}\"")
            lines.append(f"  Peak-to-peak       : {np.ptp(ra):.4f}\"")
            lines.append(f"  Min deviation      : {np.min(ra):+.4f}\"")
            lines.append(f"  Max deviation      : {np.max(ra):+.4f}\"")
            lines.append(f"  95th percentile    : {np.percentile(np.abs(ra), 95):.4f}\"")
            lines.append(f"  99th percentile    : {np.percentile(np.abs(ra), 99):.4f}\"")
            lines.append("")

            # RA STDEV statistics
            if len(s.ra_stdevs) > 0 and np.any(s.ra_stdevs > 0):
                valid_stdevs = s.ra_stdevs[s.ra_stdevs > 0]
                lines.append(f"  Running STDEV avg  : {np.mean(valid_stdevs):.4f}\"")
                lines.append(f"  Running STDEV max  : {np.max(valid_stdevs):.4f}\"")
                lines.append(f"  Running STDEV med  : {np.median(valid_stdevs):.4f}\"")
                lines.append("")

            # Drift analysis
            if len(ra) > 100:
                t_rel = s.timestamps - s.timestamps[0]
                coeffs = np.polyfit(t_rel, ra, 1)
                drift_per_min = coeffs[0] * 60.0
                drift_per_hour = coeffs[0] * 3600.0
                lines.append(f"  Drift rate         : {drift_per_min:+.4f}\"/min ({drift_per_hour:+.2f}\"/h)")

                if abs(drift_per_hour) > 5.0:
                    if fr:
                        lines.append("  [!] Dérive RA significative — vérifiez l'alignement polaire (azimut)")
                    else:
                        lines.append("  [!] Significant RA drift — check polar alignment (azimuth)")
                elif abs(drift_per_hour) > 1.0:
                    if fr:
                        lines.append("  [i] Légère dérive RA détectée")
                    else:
                        lines.append("  [i] Slight RA drift detected")
                else:
                    if fr:
                        lines.append("  [OK] Pas de dérive RA significative")
                    else:
                        lines.append("  [OK] No significant RA drift")
                lines.append("")
        lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 4. DECLINATION ANALYSIS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  DECLINATION (DEC) / DECLINAISON (DEC)")
        lines.append("=" * 70)
        lines.append("")

        if len(s.dec_deviations) > 0:
            dec = s.dec_deviations
            lines.append(f"  Mean deviation     : {np.mean(dec):+.4f}\"")
            lines.append(f"  Median deviation   : {np.median(dec):+.4f}\"")
            lines.append(f"  RMS (std dev)      : {dec_rms:.4f}\"")
            lines.append(f"  Peak-to-peak       : {np.ptp(dec):.4f}\"")
            lines.append(f"  Min deviation      : {np.min(dec):+.4f}\"")
            lines.append(f"  Max deviation      : {np.max(dec):+.4f}\"")
            lines.append(f"  95th percentile    : {np.percentile(np.abs(dec), 95):.4f}\"")
            lines.append(f"  99th percentile    : {np.percentile(np.abs(dec), 99):.4f}\"")
            lines.append("")

            # DEC STDEV statistics
            if len(s.dec_stdevs) > 0 and np.any(s.dec_stdevs > 0):
                valid_stdevs = s.dec_stdevs[s.dec_stdevs > 0]
                lines.append(f"  Running STDEV avg  : {np.mean(valid_stdevs):.4f}\"")
                lines.append(f"  Running STDEV max  : {np.max(valid_stdevs):.4f}\"")
                lines.append(f"  Running STDEV med  : {np.median(valid_stdevs):.4f}\"")
                lines.append("")

            # DEC Drift
            if len(dec) > 100:
                t_rel = s.timestamps - s.timestamps[0]
                coeffs = np.polyfit(t_rel, dec, 1)
                drift_per_min = coeffs[0] * 60.0
                drift_per_hour = coeffs[0] * 3600.0
                lines.append(f"  Drift rate         : {drift_per_min:+.4f}\"/min ({drift_per_hour:+.2f}\"/h)")

                if abs(drift_per_hour) > 5.0:
                    if fr:
                        lines.append("  [!] Dérive DEC significative — vérifiez l'alignement polaire (altitude)")
                    else:
                        lines.append("  [!] Significant DEC drift — check polar alignment (altitude)")
                elif abs(drift_per_hour) > 1.0:
                    if fr:
                        lines.append("  [i] Légère dérive DEC détectée")
                    else:
                        lines.append("  [i] Slight DEC drift detected")
                else:
                    if fr:
                        lines.append("  [OK] Pas de dérive DEC significative")
                    else:
                        lines.append("  [OK] No significant DEC drift")
                lines.append("")
        lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 5. FFT / PERIODIC ERROR ANALYSIS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        lines.append("  FFT / PERIODIC ERROR / ERREUR PERIODIQUE")
        lines.append("=" * 70)
        lines.append("")

        if len(s.ra_deviations) > 64 and s.effective_frequency > 0:
            ra_data = s.ra_deviations - np.mean(s.ra_deviations)
            window = np.hanning(len(ra_data))
            windowed = ra_data * window
            n = len(windowed)
            fft_result = np.fft.rfft(windowed)
            magnitudes = 2.0 / n * np.abs(fft_result)
            frequencies = np.fft.rfftfreq(n, d=1.0 / s.effective_frequency)

            # Skip DC component
            freqs = frequencies[1:]
            mags = magnitudes[1:]

            if len(mags) > 0:
                # Find top 5 peaks
                peak_indices = np.argsort(mags)[::-1][:5]

                lines.append("  RA FFT — Top 5 peaks / 5 pics dominants :")
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

                # Identify PE
                dominant_idx = peak_indices[0]
                dominant_freq = freqs[dominant_idx]
                dominant_period = 1.0 / dominant_freq if dominant_freq > 0 else 0
                dominant_amp = mags[dominant_idx]

                if 120 < dominant_period < 900:
                    if fr:
                        lines.append(f"  [PE] Erreur périodique détectée !")
                        lines.append(f"        Période : {dominant_period:.1f} s ({dominant_period/60:.1f} min)")
                        lines.append(f"        Amplitude : {dominant_amp:.4f}\"")
                        if dominant_amp < 0.5:
                            lines.append("        => PE très faible, excellent !")
                        elif dominant_amp < 1.5:
                            lines.append("        => PE acceptable")
                        else:
                            lines.append("        => PE élevée — considérez la calibration PEC")
                    else:
                        lines.append(f"  [PE] Periodic Error detected!")
                        lines.append(f"        Period: {dominant_period:.1f} s ({dominant_period/60:.1f} min)")
                        lines.append(f"        Amplitude: {dominant_amp:.4f}\"")
                        if dominant_amp < 0.5:
                            lines.append("        => Very low PE, excellent!")
                        elif dominant_amp < 1.5:
                            lines.append("        => Acceptable PE")
                        else:
                            lines.append("        => High PE — consider PEC calibration")
                else:
                    if fr:
                        lines.append("  [i] Pas d'erreur périodique typique détectée dans la plage 2-15 min")
                    else:
                        lines.append("  [i] No typical periodic error detected in 2-15 min range")
                lines.append("")

            # DEC FFT
            if len(s.dec_deviations) > 64:
                dec_data = s.dec_deviations - np.mean(s.dec_deviations)
                window = np.hanning(len(dec_data))
                windowed = dec_data * window
                n = len(windowed)
                fft_result = np.fft.rfft(windowed)
                mags = 2.0 / n * np.abs(fft_result)
                freqs = np.fft.rfftfreq(n, d=1.0 / s.effective_frequency)
                freqs = freqs[1:]
                mags = mags[1:]

                if len(mags) > 0:
                    peak_indices = np.argsort(mags)[::-1][:3]
                    lines.append("  DEC FFT — Top 3 peaks / 3 pics dominants :")
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

        else:
            if fr:
                lines.append("  Pas assez de données pour l'analyse FFT (minimum 64 échantillons)")
            else:
                lines.append("  Not enough data for FFT analysis (minimum 64 samples)")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 6. AXIAL DATA ANALYSIS
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_axis) > 10 and np.any(s.ra_axis != 0):
            lines.append("=" * 70)
            lines.append("  AXIAL DATA / DONNEES AXIALES")
            lines.append("=" * 70)
            lines.append("")

            # RA axis
            ra_axis = s.ra_axis[s.ra_axis != 0] if np.any(s.ra_axis != 0) else s.ra_axis
            if len(ra_axis) > 1:
                lines.append(f"  RA Axis range      : {np.min(ra_axis):.4f} — {np.max(ra_axis):.4f}")
                lines.append(f"  RA Axis excursion  : {np.ptp(ra_axis):.4f} deg")

            # DEC axis
            dec_axis = s.dec_axis[s.dec_axis != 0] if np.any(s.dec_axis != 0) else s.dec_axis
            if len(dec_axis) > 1:
                lines.append(f"  DEC Axis range     : {np.min(dec_axis):.4f} — {np.max(dec_axis):.4f}")
                lines.append(f"  DEC Axis excursion : {np.ptp(dec_axis):.4f} deg")

            # Compute speeds
            if len(ra_axis) > 2 and len(s.timestamps) > 2:
                t_rel = s.timestamps[:len(ra_axis)] - s.timestamps[0]
                dt = np.diff(t_rel)
                dt[dt == 0] = 1e-6
                ra_speed = np.diff(ra_axis) / dt
                lines.append(f"  RA mean speed      : {np.mean(ra_speed):+.6f} deg/s")
                lines.append(f"  RA max speed       : {np.max(np.abs(ra_speed)):.6f} deg/s")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 7. TIME SYNCHRONIZATION ANALYSIS
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

            # Drift
            if len(td) > 100:
                t_rel = s.time_timestamps - s.time_timestamps[0]
                coeffs = np.polyfit(t_rel, td, 1)
                drift_per_min = coeffs[0] * 60.0
                lines.append(f"  Clock drift rate   : {drift_per_min:+.3f} ms/min")

                if abs(drift_per_min) > 1.0:
                    if fr:
                        lines.append("  [!] Dérive d'horloge significative détectée")
                    else:
                        lines.append("  [!] Significant clock drift detected")
                else:
                    if fr:
                        lines.append("  [OK] Horloge stable")
                    else:
                        lines.append("  [OK] Stable clock")
            lines.append("")

            # PC loop time
            if len(s.time_pc_loop) > 0:
                pl = s.time_pc_loop
                lines.append(f"  PC loop avg        : {np.mean(pl):.1f} ms")
                lines.append(f"  PC loop max        : {np.max(pl):.1f} ms")
                lines.append(f"  PC loop std        : {np.std(pl):.1f} ms")

                if np.mean(pl) > 1000:
                    if fr:
                        lines.append("  [!] Boucle PC lente — le PC a du mal à maintenir la cadence")
                    else:
                        lines.append("  [!] Slow PC loop — PC struggling to maintain polling rate")
            lines.append("")

            # Mount loop time
            if len(s.time_mount_loop) > 0:
                ml = s.time_mount_loop
                lines.append(f"  Mount loop avg     : {np.mean(ml):.1f} ms")
                lines.append(f"  Mount loop max     : {np.max(ml):.1f} ms")
            lines.append("")

            # NTP
            if len(s.time_ntp_diff) > 0 and np.any(s.time_ntp_diff != 0):
                ntp = s.time_ntp_diff[s.time_ntp_diff != 0]
                if len(ntp) > 0:
                    lines.append(f"  PC-NTP offset avg  : {np.mean(ntp):+.1f} ms")
                    lines.append(f"  PC-NTP offset max  : {np.max(np.abs(ntp)):.1f} ms")
                    if np.max(np.abs(ntp)) > 1000:
                        if fr:
                            lines.append("  [!] Décalage NTP important — synchronisez l'horloge PC")
                        else:
                            lines.append("  [!] Large NTP offset — synchronize PC clock")
                    lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 8. TRACKING STATUS ANALYSIS
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
                if fr:
                    lines.append(f"  [!] Seulement {tracking_pct:.0f}% du temps en suivi")
                    lines.append("      La monture a passé beaucoup de temps hors suivi")
                else:
                    lines.append(f"  [!] Only {tracking_pct:.0f}% of time tracking")
                    lines.append("      Mount spent significant time not tracking")
            else:
                if fr:
                    lines.append(f"  [OK] {tracking_pct:.0f}% du temps en suivi — normal")
                else:
                    lines.append(f"  [OK] {tracking_pct:.0f}% of time tracking — normal")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 9. TOLERANCE EVENTS
        # ═══════════════════════════════════════════════════════════
        if len(s.ra_deviations) > 0:
            lines.append("=" * 70)
            lines.append("  TOLERANCE ANALYSIS / ANALYSE DES TOLERANCES")
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
        # 10. DATA CONTINUITY / GAPS
        # ═══════════════════════════════════════════════════════════
        if len(s.timestamps) > 10:
            lines.append("=" * 70)
            lines.append("  DATA CONTINUITY / CONTINUITE DES DONNEES")
            lines.append("=" * 70)
            lines.append("")

            dt = np.diff(s.timestamps)
            expected_dt = 1.0 / s.effective_frequency if s.effective_frequency > 0 else 0.5

            gaps = dt[dt > expected_dt * 5]  # Gaps > 5x expected interval
            if len(gaps) > 0:
                lines.append(f"  Gaps detected      : {len(gaps)}")
                lines.append(f"  Largest gap        : {np.max(gaps):.1f} s")
                lines.append(f"  Total gap time     : {np.sum(gaps):.1f} s")

                if fr:
                    lines.append("  [i] Des interruptions d'acquisition ont été détectées")
                    lines.append("      (slewing, reconnexion, problème réseau...)")
                else:
                    lines.append("  [i] Data acquisition interruptions detected")
                    lines.append("      (slewing, reconnection, network issue...)")
            else:
                if fr:
                    lines.append("  [OK] Acquisition continue, pas de coupure détectée")
                else:
                    lines.append("  [OK] Continuous acquisition, no gaps detected")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 10b. ENVIRONMENT / DIAGNOSTICS
        # ═══════════════════════════════════════════════════════════
        has_env = len(s.env_timestamps) > 0
        if has_env:
            lines.append("=" * 70)
            lines.append("  ENVIRONMENT & DIAGNOSTICS / ENVIRONNEMENT & DIAGNOSTICS")
            lines.append("=" * 70)
            lines.append("")

            # Temperature
            temp = s.env_temperature_ext
            valid_temp = temp[~np.isnan(temp)] if len(temp) > 0 else np.array([])
            if len(valid_temp) > 0:
                lines.append(f"  Temperature (ext)  : {valid_temp[0]:.1f}°C → {valid_temp[-1]:.1f}°C")
                lines.append(f"  Temp range         : {np.min(valid_temp):.1f}°C — {np.max(valid_temp):.1f}°C")
                temp_delta = valid_temp[-1] - valid_temp[0]
                lines.append(f"  Temp change        : {temp_delta:+.1f}°C over session")
                if abs(temp_delta) > 5.0:
                    if fr:
                        lines.append("  [!] Variation thermique importante — peut affecter la mise au point et le suivi")
                    else:
                        lines.append("  [!] Large temperature change — may affect focus and tracking")
                elif abs(temp_delta) > 2.0:
                    if fr:
                        lines.append("  [i] Variation thermique modérée — surveillez la mise au point")
                    else:
                        lines.append("  [i] Moderate temperature change — monitor focus")
                else:
                    if fr:
                        lines.append("  [OK] Température stable")
                    else:
                        lines.append("  [OK] Stable temperature")
                lines.append("")

            # Internal temperature
            temp_int = s.env_temperature_int
            valid_int = temp_int[~np.isnan(temp_int)] if len(temp_int) > 0 else np.array([])
            if len(valid_int) > 0:
                lines.append(f"  Internal temp      : {valid_int[0]:.1f}°C → {valid_int[-1]:.1f}°C")
                lines.append(f"  Internal range     : {np.min(valid_int):.1f}°C — {np.max(valid_int):.1f}°C")
                int_delta = valid_int[-1] - valid_int[0]
                if int_delta > 10.0:
                    if fr:
                        lines.append("  [!] La monture chauffe significativement — vérifiez la ventilation")
                    else:
                        lines.append("  [!] Mount heating significantly — check ventilation")
                lines.append("")

            # Pressure
            pres = s.env_pressure
            valid_pres = pres[~np.isnan(pres)] if len(pres) > 0 else np.array([])
            if len(valid_pres) > 0:
                lines.append(f"  Pressure           : {valid_pres[0]:.1f} → {valid_pres[-1]:.1f} mbar")
                lines.append(f"  Pressure range     : {np.min(valid_pres):.1f} — {np.max(valid_pres):.1f} mbar")
                pres_delta = valid_pres[-1] - valid_pres[0]
                lines.append(f"  Pressure change    : {pres_delta:+.1f} mbar")
                if abs(pres_delta) > 5.0:
                    if fr:
                        lines.append("  [i] Changement barométrique notable — conditions météo changeantes")
                    else:
                        lines.append("  [i] Notable barometric change — weather conditions changing")
                lines.append("")

            # Alignment model
            valid_rms = s.env_alignment_rms[~np.isnan(s.env_alignment_rms)] if len(s.env_alignment_rms) > 0 else np.array([])
            if len(valid_rms) > 0:
                stars = s.env_alignment_stars
                valid_stars = [st for st in stars if st > 0]
                if valid_stars:
                    lines.append(f"  Alignment stars    : {valid_stars[0]}")
                lines.append(f"  Alignment RMS      : {valid_rms[0]:.1f}\"")

                valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
                if len(valid_polar) > 0:
                    polar_arcmin = valid_polar[0] * 60.0
                    lines.append(f"  Polar error        : {valid_polar[0]:.4f}° ({polar_arcmin:.1f}')")
                    if polar_arcmin > 5.0:
                        if fr:
                            lines.append("  [!] Erreur polaire élevée — refaites l'alignement polaire")
                        else:
                            lines.append("  [!] High polar error — redo polar alignment")
                    elif polar_arcmin > 1.0:
                        if fr:
                            lines.append("  [i] Erreur polaire modérée — acceptable pour la plupart des usages")
                        else:
                            lines.append("  [i] Moderate polar error — acceptable for most use cases")
                    else:
                        if fr:
                            lines.append("  [OK] Alignement polaire excellent")
                        else:
                            lines.append("  [OK] Excellent polar alignment")
                lines.append("")

            # Tracking rate stability
            rates = s.env_tracking_rates
            valid_rates = rates[~np.isnan(rates)] if len(rates) > 0 else np.array([])
            if len(valid_rates) > 1:
                rate_std = np.std(valid_rates)
                lines.append(f"  Tracking rate avg  : {np.mean(valid_rates):.2f}")
                lines.append(f"  Tracking rate std  : {rate_std:.4f}")
                if rate_std > 0.1:
                    if fr:
                        lines.append("  [i] Variation du taux de suivi détectée")
                    else:
                        lines.append("  [i] Tracking rate variation detected")
                lines.append("")

            # Mount status codes history
            valid_codes = [c for c in s.env_status_codes if c >= 0]
            if valid_codes:
                from collections import Counter
                code_counts = Counter(valid_codes)
                # 10Micron status codes
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
                lines.append("  Mount status codes (10Micron :Gstat#) :")
                for code, count in code_counts.most_common():
                    name = status_names.get(code, f"Code {code}")
                    lines.append(f"    {code} = {name:<30} : {count}x")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 11. EVENTS SUMMARY
        # ═══════════════════════════════════════════════════════════
        if s.events:
            lines.append("=" * 70)
            lines.append("  EVENT LOG / JOURNAL DES EVENEMENTS")
            lines.append("=" * 70)
            lines.append("")

            tolerance_events = [e for e in s.events if 'TOLERANCE' in e[1]]
            warning_events = [e for e in s.events if 'WARNING' in e[1] or 'Check WARNING' in e[1]]
            status_events = [e for e in s.events if 'Mount status' in e[1]]

            lines.append(f"  Total events       : {len(s.events)}")
            lines.append(f"  Tolerance alerts   : {len(tolerance_events)}")
            lines.append(f"  Warnings           : {len(warning_events)}")
            lines.append(f"  Status changes     : {len(status_events)}")
            lines.append("")

            if tolerance_events:
                lines.append("  Tolerance events (first 10):")
                for ts, msg in tolerance_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                if len(tolerance_events) > 10:
                    lines.append(f"    ... and {len(tolerance_events) - 10} more")
                lines.append("")

            if warning_events:
                lines.append("  Warnings:")
                for ts, msg in warning_events[:10]:
                    lines.append(f"    {ts}  {msg}")
                lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 12. RECOMMENDATIONS / RECOMMANDATIONS
        # ═══════════════════════════════════════════════════════════
        lines.append("=" * 70)
        if fr:
            lines.append("  RECOMMANDATIONS")
        else:
            lines.append("  RECOMMENDATIONS")
        lines.append("=" * 70)
        lines.append("")

        recommendations = []

        if ra_rms > 2.0:
            if fr:
                recommendations.append(
                    "- RA instable (RMS > 2\") : vérifiez l'équilibrage RA, "
                    "le serrage des fixations, les câbles qui tirent"
                )
            else:
                recommendations.append(
                    "- RA unstable (RMS > 2\"): check RA balance, "
                    "clamp tightness, cable drag"
                )

        if dec_rms > 2.0:
            if fr:
                recommendations.append(
                    "- DEC instable (RMS > 2\") : vérifiez l'équilibrage DEC, "
                    "le jeu dans l'axe DEC"
                )
            else:
                recommendations.append(
                    "- DEC unstable (RMS > 2\"): check DEC balance, "
                    "DEC axis backlash"
                )

        # Check for drift
        if len(s.ra_deviations) > 100:
            t_rel = s.timestamps - s.timestamps[0]
            ra_coeffs = np.polyfit(t_rel, s.ra_deviations, 1)
            ra_drift_h = ra_coeffs[0] * 3600.0
            if abs(ra_drift_h) > 5.0:
                if fr:
                    recommendations.append(
                        f"- Dérive RA de {ra_drift_h:+.1f}\"/h : ajustez l'azimut "
                        "de l'alignement polaire"
                    )
                else:
                    recommendations.append(
                        f"- RA drift of {ra_drift_h:+.1f}\"/h: adjust azimuth "
                        "of polar alignment"
                    )

        if len(s.dec_deviations) > 100:
            t_rel = s.timestamps - s.timestamps[0]
            dec_coeffs = np.polyfit(t_rel, s.dec_deviations, 1)
            dec_drift_h = dec_coeffs[0] * 3600.0
            if abs(dec_drift_h) > 5.0:
                if fr:
                    recommendations.append(
                        f"- Dérive DEC de {dec_drift_h:+.1f}\"/h : ajustez l'altitude "
                        "de l'alignement polaire"
                    )
                else:
                    recommendations.append(
                        f"- DEC drift of {dec_drift_h:+.1f}\"/h: adjust altitude "
                        "of polar alignment"
                    )

        # Environment-based recommendations
        if has_env:
            valid_temp = s.env_temperature_ext[~np.isnan(s.env_temperature_ext)] if len(s.env_temperature_ext) > 0 else np.array([])
            if len(valid_temp) > 1 and abs(valid_temp[-1] - valid_temp[0]) > 5.0:
                if fr:
                    recommendations.append(
                        f"- Chute de température de {abs(valid_temp[-1] - valid_temp[0]):.1f}°C : "
                        "utilisez un focuser motorisé avec compensation thermique"
                    )
                else:
                    recommendations.append(
                        f"- Temperature drop of {abs(valid_temp[-1] - valid_temp[0]):.1f}°C: "
                        "use a motorized focuser with temperature compensation"
                    )

            valid_polar = s.env_polar_error[~np.isnan(s.env_polar_error)] if len(s.env_polar_error) > 0 else np.array([])
            if len(valid_polar) > 0 and valid_polar[0] * 60.0 > 5.0:
                if fr:
                    recommendations.append(
                        f"- Erreur polaire de {valid_polar[0]*60:.1f}' : "
                        "refaites l'alignement polaire avec PoleMaster ou SharpCap"
                    )
                else:
                    recommendations.append(
                        f"- Polar error of {valid_polar[0]*60:.1f}': "
                        "redo polar alignment with PoleMaster or SharpCap"
                    )

        if not recommendations:
            if fr:
                recommendations.append(
                    "- Aucun problème majeur détecté. Continuez avec ces réglages !"
                )
            else:
                recommendations.append(
                    "- No major issues detected. Continue with these settings!"
                )

        for r in recommendations:
            lines.append(f"  {r}")
        lines.append("")

        # Final separator
        lines.append("=" * 70)
        if fr:
            lines.append(f"  Rapport généré le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}")
        else:
            lines.append(f"  Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}")
        lines.append("=" * 70)

        self._report_text = "\n".join(lines)
        self._report.setPlainText(self._report_text)
        self._report.moveCursor(QTextCursor.MoveOperation.Start)

    def _export_report(self):
        """Export analysis report to a text file."""
        if self._lang == 'fr':
            title = "Exporter le rapport"
        else:
            title = "Export Report"

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
