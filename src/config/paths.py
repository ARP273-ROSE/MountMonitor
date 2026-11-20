# -*- coding: utf-8 -*-
"""Where the application writes its data.

Run from source — as its author does — MountMonitor writes next to its code:
logs in `Logs/`, settings at the root. It is convenient, and nothing calls
that into question.

Installed, that is untenable. The installation folder belongs to the
installer: it wipes its contents before laying down a new version, precisely
so that no file from a past version survives there. An acquisition night's
logs and the mount settings would vanish at the first update.

Installed, the application therefore writes to `%LOCALAPPDATA%\\MountMonitor`,
which does not depend on any version.

Nothing is moved: the two cases never meet on the same machine, and an
automatic move of acquisition data is exactly the kind of operation one does
not do behind someone's back.
"""

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def is_packaged() -> bool:
    """True when running from the standalone package (Python bundled alongside).

    The package puts the code in `app/` and the interpreter in `python/`, side
    by side. It is the most reliable signature: it depends neither on an
    environment variable nor on a flag one might forget to set.
    """
    python = _PROJECT_ROOT.parent / 'python'
    # Windows: python/python.exe; macOS and Linux: python/bin/python3.
    return (python / 'python.exe').exists() or (python / 'bin' / 'python3').exists()


def data_folder() -> Path:
    """Folder where logs, settings and reports are written."""
    if not is_packaged():
        return _PROJECT_ROOT

    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA')
                    or Path.home() / 'AppData' / 'Local')
    else:
        base = Path(os.environ.get('XDG_DATA_HOME')
                    or Path.home() / '.local' / 'share')
    folder = base / 'MountMonitor'
    folder.mkdir(parents=True, exist_ok=True)
    _migrate_old_data(folder)
    return folder


_MIGRATION_DONE = False


def _migrate_old_data(folder: Path) -> None:
    """Versions <= 1.31 on macOS and Linux: the package did not recognise itself,
    and settings, reports and session logs were written into `app/`.
    They are copied once into the data folder, without deleting anything and
    without ever overwriting what is already there."""
    global _MIGRATION_DONE
    if _MIGRATION_DONE or sys.platform == 'win32':
        return
    _MIGRATION_DONE = True
    import shutil
    for name in ('mountmonitor_settings.json', 'reglages_rapports.json', 'Logs'):
        old_path, new_path = _PROJECT_ROOT / name, folder / name
        if not old_path.exists():
            continue
        try:
            if old_path.is_dir():
                for f in old_path.rglob('*'):
                    target = new_path / f.relative_to(old_path)
                    if f.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, target)
            elif not new_path.exists():
                shutil.copy2(old_path, new_path)
        except OSError:
            pass


def logs_folder() -> Path:
    """Folder for session files (.log, .dat, .dti, .sei, .fft, .env)."""
    logs = data_folder() / 'Logs'
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def settings_file() -> Path:
    return data_folder() / 'mountmonitor_settings.json'
