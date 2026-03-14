"""Crash reporting system for MountMonitor.

Captures unhandled exceptions, saves crash reports to JSON files,
and offers to send bug reports via GitHub Issues on next startup.
All paths are anonymized to protect user privacy.
"""

import sys
import json
import platform
import traceback
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

_CRASH_FILE = "crash_report.json"

# GitHub repository for bug reports
GITHUB_REPO = "ARP273-ROSE/MountMonitor"


def _read_version() -> str:
    """Read version from VERSION file."""
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "unknown"


def anonymize_path(text: str) -> str:
    """Anonymize file paths in text to protect user privacy.

    Replaces home directory references with ~ and removes
    any username-revealing path components.
    """
    if not text:
        return text

    home = str(Path.home())

    # Replace forward-slash variant first (common in tracebacks)
    text = text.replace(home.replace("\\", "/"), "~")
    # Replace native path
    text = text.replace(home, "~")

    # On Windows, also handle case-insensitive match
    if sys.platform == "win32":
        text = text.replace(home.lower(), "~")
        text = text.replace(home.upper(), "~")
        # Also catch C:\Users\<username> patterns that might differ
        # from home dir (e.g. different drive letters)
        username = Path.home().name
        pattern = re.compile(
            r'[A-Za-z]:[/\\]+[Uu]sers[/\\]+' + re.escape(username),
            re.IGNORECASE
        )
        text = pattern.sub("~", text)

    return text


def _anonymize_list(lines: List[str]) -> List[str]:
    """Anonymize a list of strings (e.g. traceback lines)."""
    return [anonymize_path(line) for line in lines]


def _get_recent_log_errors(max_lines: int = 20) -> List[str]:
    """Read the last N error/critical lines from the app log."""
    try:
        log_path = Path(__file__).resolve().parent.parent.parent / "Logs" / "mountmonitor_app.log"
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        errors = [
            ln for ln in lines
            if "[ERROR]" in ln or "[CRITICAL]" in ln or "[WARNING]" in ln
        ]
        # Return last max_lines, anonymized
        return _anonymize_list(errors[-max_lines:])
    except Exception:
        return []


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
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
            report = {
                "timestamp": datetime.now().isoformat(),
                "version": _read_version(),
                "python_version": platform.python_version(),
                "os": platform.system(),
                # Only OS name, no detailed version (privacy)
                "architecture": platform.machine(),
                "exception_type": exc_type.__name__,
                "exception_message": anonymize_path(str(exc_value)),
                "traceback": _anonymize_list(tb_lines),
            }

            with open(self._crash_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.critical("Crash report saved: %s", self._crash_file)
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
        """Format a crash report as a GitHub Issue body (anonymized)."""
        tb_raw = report.get('traceback', ['No traceback available'])
        # Ensure traceback is anonymized even if loaded from old report
        tb = anonymize_path(''.join(tb_raw))
        msg = anonymize_path(report.get('exception_message', 'unknown'))

        return (
            f"## Crash Report\n\n"
            f"**Version:** {report.get('version', 'unknown')}\n"
            f"**Date:** {report.get('timestamp', 'unknown')}\n"
            f"**OS:** {report.get('os', 'unknown')}\n"
            f"**Python:** {report.get('python_version', 'unknown')}\n"
            f"**Architecture:** {report.get('architecture', 'unknown')}\n\n"
            f"## Exception\n\n"
            f"**Type:** `{report.get('exception_type', 'unknown')}`\n"
            f"**Message:** {msg}\n\n"
            f"## Traceback\n\n```\n{tb}```\n\n"
            f"## Steps to Reproduce\n\n"
            f"_Please describe what you were doing when the crash occurred._\n"
        )

    def format_bug_report(self, description: str = "") -> str:
        """Format a manual bug report with anonymized system info.

        Args:
            description: Optional user description of the issue.

        Returns:
            GitHub Issue body text, ready for URL encoding.
        """
        recent_errors = _get_recent_log_errors(15)
        errors_text = "\n".join(recent_errors) if recent_errors else "None"

        body = (
            f"## Bug Report\n\n"
            f"**Version:** {_read_version()}\n"
            f"**OS:** {platform.system()}\n"
            f"**Python:** {platform.python_version()}\n"
            f"**Architecture:** {platform.machine()}\n\n"
            f"## Description\n\n"
            f"{description or '_Please describe the issue._'}\n\n"
            f"## Steps to Reproduce\n\n"
            f"1. \n2. \n3. \n\n"
            f"## Expected Behavior\n\n"
            f"_What did you expect to happen?_\n\n"
            f"## Actual Behavior\n\n"
            f"_What actually happened?_\n\n"
            f"## Recent Errors\n\n```\n{errors_text}\n```\n"
        )
        return body
