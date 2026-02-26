"""Settings manager for MountMonitor. JSON-based, atomic saves."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS


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
            # Default: next to the executable / main script
            self._path = Path(__file__).resolve().parent.parent.parent / "mountmonitor_settings.json"
        else:
            self._path = Path(path)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load settings from disk, merging with defaults."""
        self._data = dict(DEFAULTS)
        if self._path.exists():
            try:
                with open(self._path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, OSError):
                pass  # Use defaults on corrupted file

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

    @classmethod
    def reset_singleton(cls):
        """Reset singleton for testing."""
        cls._instance = None
        cls._initialized = False
