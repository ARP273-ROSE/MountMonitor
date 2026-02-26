#!/usr/bin/env python3
"""MountMonitor - Modern telescope mount monitoring for astrophotography.

Modernized rewrite of MountMonitor v3.37 (Java) by Nicolas de Hilster.
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
    log_dir = project_root / "Logs"
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

    # Apply dark theme
    from src.gui.theme import apply_dark_theme
    apply_dark_theme(app)

    # Install crash reporter
    from src.logging_module.crash_reporter import CrashReporter
    crash_reporter = CrashReporter(project_root)
    crash_reporter.install()

    # Check for previous crash
    if crash_reporter.has_crash_report():
        report = crash_reporter.get_crash_report()
        if report:
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setWindowTitle("Crash Report / Rapport de crash")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(
                "MountMonitor crashed during the last session.\n"
                "MountMonitor a planté lors de la dernière session.\n\n"
                f"Error: {report.get('exception_type', 'Unknown')}\n"
                f"{report.get('exception_message', '')}"
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore
            )
            msg.exec()
        crash_reporter.clear_crash_report()

    # Detect hardware for optimization
    from src.utils.hardware_detect import detect_hardware
    hw = detect_hardware()
    logger.info(f"Hardware: {hw.cpu_name}, {hw.cpu_cores_physical} cores, "
                f"{hw.ram_total_mb}MB RAM, GPU: {hw.gpu_name}")

    # Create and show main window
    from src.gui.main_window import MainWindow
    window = MainWindow(sim_mode=sim_mode)
    window.show()

    logger.info("MountMonitor ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
