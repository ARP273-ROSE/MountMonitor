"""Settings manager for MountMonitor. JSON-based, atomic saves."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS

logger = logging.getLogger(__name__)

# Version of the settings file layout. Raise it whenever a setting is renamed,
# split or changes meaning, and add the step in _MIGRATIONS: a file written by
# an older MountMonitor is then converted once at load, instead of silently
# keeping a value whose meaning changed. Files written before 4.4.3 carry no
# number and count as version 0.
SETTINGS_VERSION = 2
VERSION_KEY = "settings_version"


def _v0_to_v1(data: dict) -> None:
    """4.4.3: the version number itself. The separate "tolerance in seconds
    of hour angle" box was folded into the RA unit choice in 4.3.0; its key
    is dropped."""
    data.pop("tolerance_as_ha_seconds", None)


def _v1_to_v2(data: dict) -> None:
    """4.4.4: "king" left the expected tracking rates (a 10Micron offers
    sidereal, solar and lunar only)."""
    if str(data.get("check_tracking_rate_value", "")).lower() == "king":
        data["check_tracking_rate_value"] = "sidereal"


# _MIGRATIONS[n] turns a version-n file into a version n+1 one, in place.
_MIGRATIONS = {0: _v0_to_v1, 1: _v1_to_v2}


def migrate(data: dict) -> dict:
    """Bring a loaded settings dict up to SETTINGS_VERSION, step by step."""
    try:
        version = int(data.get(VERSION_KEY, 0))
    except (TypeError, ValueError):
        version = 0
    if version > SETTINGS_VERSION:
        # Written by a newer MountMonitor (downgrade): keep everything as it
        # is -- unknown keys are ignored and kept, nothing is converted back.
        logger.warning("Settings file version %s is newer than this program (%s)",
                       version, SETTINGS_VERSION)
        return data
    while version < SETTINGS_VERSION:
        _MIGRATIONS[version](data)
        version += 1
        logger.info("Settings converted to version %s", version)
    data[VERSION_KEY] = version
    return data


class Settings:
    """Thread-safe settings manager with atomic saves."""

    _instance = None
    _initialized = False

    def __new__(cls, path: Path | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, path: Path | None = None):
        if self._initialized:
            return
        self._initialized = True
        if path is None:
            # From source: next to the code. Installed: in the data folder,
            # which updates do not wipe. See config/paths.py.
            from .paths import settings_file
            self._path = settings_file()
        else:
            self._path = Path(path)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load settings from disk, merging with defaults."""
        self._data = dict(DEFAULTS)
        self._data[VERSION_KEY] = SETTINGS_VERSION
        if self._path.exists():
            try:
                with open(self._path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                if not isinstance(saved, dict):
                    raise ValueError("settings file is not a JSON object")
                self._data.update(migrate(saved))
            except (json.JSONDecodeError, ValueError, OSError) as e:
                # Defaults, but keep the unreadable file aside: the next save
                # would otherwise overwrite every setting without a trace.
                logger.warning("Settings file unreadable (%s), defaults used", e)
                try:
                    self._path.replace(self._path.with_suffix(self._path.suffix + '.corrupt'))
                except OSError:
                    pass

    def save(self):
        """Atomic save: write to temp file, fsync, then replace."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent),
            suffix='.tmp',
            prefix='settings_'
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._path))
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._data.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        """Set a setting value."""
        self._data[key] = value

    def get_all(self) -> dict[str, Any]:
        """Get all settings as a dict."""
        return dict(self._data)

    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        self._data = dict(DEFAULTS)
        self._data[VERSION_KEY] = SETTINGS_VERSION

    @classmethod
    def reset_singleton(cls):
        """Reset singleton for testing."""
        cls._instance = None
        cls._initialized = False
