"""Crash reporting system for MountMonitor.

Captures unhandled exceptions, saves crash reports to JSON files,
and offers to send bug reports via GitHub Issues on next startup.
"""

import sys
import json
import platform
import traceback
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CRASH_FILE = "crash_report.json"


def _read_version() -> str:
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "unknown"


class CrashReporter:
    """Handles crash detection, reporting, and recovery."""

    def __init__(self, app_dir: Optional[Path] = None):
        if app_dir is None:
            app_dir = Path(__file__).resolve().parent.parent.parent
        self._app_dir = app_dir
        self._crash_file = app_dir / _CRASH_FILE
        self._original_excepthook = sys.excepthook

    def install(self):
        """Install the crash handler as sys.excepthook."""
        sys.excepthook = self._handle_exception
        logger.info("Crash reporter installed")

    def uninstall(self):
        """Restore the original excepthook."""
        sys.excepthook = self._original_excepthook

    def _handle_exception(self, exc_type, exc_value, exc_tb):
        """Custom exception handler that saves crash report."""
        # Save crash report
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "version": _read_version(),
                "python_version": platform.python_version(),
                "os": platform.system(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_value),
                "traceback": traceback.format_exception(exc_type, exc_value, exc_tb),
            }

            with open(self._crash_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.critical(f"Crash report saved: {self._crash_file}")
        except Exception:
            pass

        # Call original handler
        self._original_excepthook(exc_type, exc_value, exc_tb)

    def has_crash_report(self) -> bool:
        """Check if a crash report exists from a previous session."""
        return self._crash_file.exists()

    def get_crash_report(self) -> Optional[dict]:
        """Read the crash report if it exists."""
        if not self._crash_file.exists():
            return None
        try:
            with open(self._crash_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def clear_crash_report(self):
        """Delete the crash report file."""
        try:
            self._crash_file.unlink(missing_ok=True)
        except OSError:
            pass

    def format_github_issue(self, report: dict) -> str:
        """Format a crash report as a GitHub Issue body."""
        tb = ''.join(report.get('traceback', ['No traceback available']))
        return (
            f"## Crash Report\n\n"
            f"**Version:** {report.get('version', 'unknown')}\n"
            f"**Date:** {report.get('timestamp', 'unknown')}\n"
            f"**OS:** {report.get('os', 'unknown')} {report.get('os_version', '')}\n"
            f"**Python:** {report.get('python_version', 'unknown')}\n"
            f"**Architecture:** {report.get('architecture', 'unknown')}\n\n"
            f"## Exception\n\n"
            f"**Type:** `{report.get('exception_type', 'unknown')}`\n"
            f"**Message:** {report.get('exception_message', 'unknown')}\n\n"
            f"## Traceback\n\n```\n{tb}```\n\n"
            f"## Steps to Reproduce\n\n"
            f"_Please describe what you were doing when the crash occurred._\n"
        )
