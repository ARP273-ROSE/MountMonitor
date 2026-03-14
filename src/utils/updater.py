"""Auto-update system for MountMonitor.

Checks GitHub Releases for newer versions and offers to download/apply updates.
Features:
  - Threaded check (non-blocking)
  - Silent startup check with delay
  - Manual check from Help menu
  - Secure download with size limits and zip validation
  - File whitelist (never overwrites user data)
  - Automatic restart after update
"""

import io
import json
import logging
import os
import re
import shutil
import struct
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

# GitHub repository
GITHUB_REPO = "ARP273-ROSE/MountMonitor"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Security limits
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024  # 100 MB max download
MAX_ZIP_ENTRIES = 500  # Max files in zip
MAX_SINGLE_FILE = 50 * 1024 * 1024  # 50 MB max single file

# Files/dirs that should NEVER be overwritten (user data, config, secrets)
_PROTECTED = {
    "mountmonitor_settings.json",
    "crash_report.json",
    "_progress.json",
    "CLAUDE.md",
    ".claude",
    ".git",
    ".gitignore",
    "venv",
    ".venv",
    "__pycache__",
    "Logs",
    "mountlog",
    "RA_graphs",
    "DEC_graphs",
    "Seismic_graphs",
    "Time_graphs",
    "FFT_graphs",
}

# Only update these file extensions
_ALLOWED_EXTENSIONS = {
    ".py", ".txt", ".md", ".bat", ".sh", ".png", ".ico",
    ".pdf", ".json", ".yaml", ".yml", ".cfg", ".ini",
    ".tex",  # LaTeX sources
}


def _read_local_version() -> str:
    """Read the local VERSION file."""
    try:
        version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_path.read_text(encoding='utf-8').strip()
    except Exception:
        return "0.0.0"


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse a version string like '1.6.1' into a tuple of ints."""
    # Strip leading 'v' if present
    v = version_str.strip().lstrip('vV')
    parts = re.split(r'[.\-]', v)
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    return tuple(result) if result else (0, 0, 0)


def is_newer(remote: str, local: str) -> bool:
    """Check if remote version is newer than local."""
    return parse_version(remote) > parse_version(local)


def check_for_update() -> Optional[Dict[str, Any]]:
    """Check GitHub API for latest release.

    Returns:
        Dict with keys: tag_name, name, body, zipball_url, html_url
        or None if up-to-date or on error.
    """
    local_version = _read_local_version()
    logger.info("Checking for updates... (local: %s)", local_version)

    try:
        req = Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"MountMonitor/{local_version}",
            },
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        tag = data.get("tag_name", "")
        if not tag:
            logger.info("No release tag found")
            return None

        if is_newer(tag, local_version):
            logger.info("Update available: %s -> %s", local_version, tag)
            return {
                "tag_name": tag,
                "name": data.get("name", tag),
                "body": data.get("body", ""),
                "zipball_url": data.get("zipball_url", ""),
                "html_url": data.get("html_url", ""),
            }
        else:
            logger.info("Already up to date (%s)", local_version)
            return None

    except (URLError, HTTPError, json.JSONDecodeError, OSError) as e:
        logger.warning("Update check failed: %s", e)
        return None


def _is_safe_zip_entry(entry: zipfile.ZipInfo) -> bool:
    """Validate a zip entry for security (anti path traversal, symlinks)."""
    name = entry.filename

    # Reject absolute paths
    if name.startswith('/') or name.startswith('\\'):
        return False

    # Reject path traversal
    if '..' in name or '\x00' in name:
        return False

    # Reject backslash paths (Windows traversal)
    if '\\' in name:
        return False

    # Reject symlinks
    if entry.external_attr >> 28 == 0xA:
        return False

    # Reject oversized files
    if entry.file_size > MAX_SINGLE_FILE:
        return False

    return True


def _strip_top_dir(name: str) -> str:
    """Strip the top-level directory from a zip entry path.

    GitHub zipballs have a top-level dir like 'repo-name-hash/'.
    """
    parts = name.split('/')
    if len(parts) > 1:
        return '/'.join(parts[1:])
    return name


def _should_update_file(rel_path: str) -> bool:
    """Check if a file should be updated (whitelist approach)."""
    p = Path(rel_path)

    # Never overwrite protected files/dirs
    for part in p.parts:
        if part in _PROTECTED:
            return False

    # Only update allowed extensions
    if p.suffix.lower() not in _ALLOWED_EXTENSIONS:
        return False

    return True


def download_and_apply(zipball_url: str, app_dir: Optional[Path] = None) -> bool:
    """Download and apply an update from GitHub zipball.

    Args:
        zipball_url: URL to the GitHub zipball
        app_dir: Application root directory

    Returns:
        True if update was applied successfully
    """
    if app_dir is None:
        app_dir = Path(__file__).resolve().parent.parent.parent

    logger.info("Downloading update from %s", zipball_url)

    try:
        req = Request(
            zipball_url,
            headers={
                "User-Agent": f"MountMonitor/{_read_local_version()}",
            },
        )

        with urlopen(req, timeout=60) as resp:
            # Check content length
            content_length = resp.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                logger.error("Download too large: %s bytes", content_length)
                return False

            # Read with size limit
            data = resp.read(MAX_DOWNLOAD_SIZE + 1)
            if len(data) > MAX_DOWNLOAD_SIZE:
                logger.error("Download exceeded size limit")
                return False

        # Validate zip
        zip_buffer = io.BytesIO(data)
        if not zipfile.is_zipfile(zip_buffer):
            logger.error("Downloaded file is not a valid zip")
            return False

        zip_buffer.seek(0)
        updated_count = 0

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            entries = zf.infolist()

            # Anti zip-bomb: check entry count
            if len(entries) > MAX_ZIP_ENTRIES:
                logger.error("Too many entries in zip: %d", len(entries))
                return False

            for entry in entries:
                # Skip directories
                if entry.is_dir():
                    continue

                # Security validation
                if not _is_safe_zip_entry(entry):
                    logger.warning("Skipping unsafe zip entry: %s", entry.filename)
                    continue

                # Strip top-level dir (GitHub zipball format)
                rel_path = _strip_top_dir(entry.filename)
                if not rel_path:
                    continue

                # Check whitelist
                if not _should_update_file(rel_path):
                    logger.debug("Skipping protected/non-whitelisted: %s", rel_path)
                    continue

                # Extract to target
                target = app_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)

                # Atomic write: extract to temp, then replace
                try:
                    file_data = zf.read(entry.filename)
                    fd, tmp_path = tempfile.mkstemp(
                        dir=str(target.parent),
                        suffix='.tmp'
                    )
                    try:
                        os.write(fd, file_data)
                        os.fsync(fd)
                    finally:
                        os.close(fd)

                    # Replace target file
                    shutil.move(tmp_path, str(target))
                    updated_count += 1
                    logger.debug("Updated: %s", rel_path)
                except Exception as e:
                    logger.warning("Failed to update %s: %s", rel_path, e)
                    # Clean up temp file
                    try:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception:
                        pass

        logger.info("Update applied: %d files updated", updated_count)
        return updated_count > 0

    except (URLError, HTTPError, OSError, zipfile.BadZipFile) as e:
        logger.error("Download/apply failed: %s", e)
        return False


def restart_application():
    """Restart the application after update."""
    logger.info("Restarting application...")
    python = sys.executable
    script = str(Path(__file__).resolve().parent.parent.parent / "main.py")
    args = [python, script] + sys.argv[1:]
    try:
        os.execv(python, args)
    except Exception as e:
        logger.error("Restart failed: %s", e)


class UpdateChecker:
    """Threaded update checker with callback support."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[Dict[str, Any]] = None
        self._callback = None
        self._checking = False

    @property
    def is_checking(self) -> bool:
        return self._checking

    @property
    def result(self) -> Optional[Dict[str, Any]]:
        return self._result

    def check_async(self, callback=None):
        """Start a threaded update check.

        Args:
            callback: Function called with the result (Dict or None).
                      Called from the background thread — use signals
                      to update GUI.
        """
        if self._checking:
            return

        self._checking = True
        self._result = None
        self._callback = callback

        self._thread = threading.Thread(
            target=self._run_check,
            daemon=True,
            name="UpdateChecker",
        )
        self._thread.start()

    def _run_check(self):
        """Background thread: check for updates."""
        try:
            self._result = check_for_update()
        except Exception as e:
            logger.warning("Update check thread error: %s", e)
            self._result = None
        finally:
            self._checking = False
            if self._callback:
                try:
                    self._callback(self._result)
                except Exception as e:
                    logger.warning("Update callback error: %s", e)
