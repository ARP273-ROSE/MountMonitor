# -*- coding: utf-8 -*-
"""Each system must receive ITS archive.

A Windows archive laid over a macOS install replaces the application with
unusable binaries: the user loses an installation that worked, and the only
way out is a manual reinstall.
"""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import updater  # noqa: E402


@pytest.fixture(autouse=True)
def _declared_repo(monkeypatch):
    """check() refuses to work without a repository: kit.json is not always there."""
    monkeypatch.setattr(updater, "REPO", "ARP273-ROSE/MountMonitor", raising=False)
    # PREFIXE_ARCHIVE comes from kit.json: outside the repository it falls back
    # to a degraded value and no asset matches any more.
    monkeypatch.setattr(updater, "PREFIXE_ARCHIVE", "mountmonitor-app-", raising=False)


def _release(*names):
    return {
        "tag_name": "v9.9.9",
        "body": "notes",
        "assets": [{"name": n, "browser_download_url": "http://x/" + n, "size": 1}
                   for n in names],
    }


@pytest.mark.parametrize("plate,expected_value", [
    ("windows", "mountmonitor-app-9.9.9-windows.zip"),
    ("macos", "mountmonitor-app-9.9.9-macos.zip"),
    ("linux", "mountmonitor-app-9.9.9-linux.zip"),
])
def test_each_system_takes_its_archive(plate, expected_value, monkeypatch):
    monkeypatch.setattr(updater, "plateforme", lambda: plate)
    monkeypatch.setattr(updater, "_open", lambda url: _Fake(_release(
        "mountmonitor-app-9.9.9-windows.zip",
        "mountmonitor-app-9.9.9-macos.zip",
        "mountmonitor-app-9.9.9-linux.zip",
        "MountMonitor-Setup-9.9.9.exe",
    )))
    update = updater.check("1.0.0")
    assert update is not None and update["url"].endswith(expected_value)


def test_installer_is_never_chosen(monkeypatch):
    """It gets installed, it is not deployed over the application."""
    monkeypatch.setattr(updater, "plateforme", lambda: "windows")
    monkeypatch.setattr(updater, "_open", lambda url: _Fake(_release(
        "MountMonitor-Setup-9.9.9.exe", "MountMonitor-9.9.9.dmg")))
    assert updater.check("1.0.0") is None


def test_other_system_archive_never_installed(monkeypatch):
    """Better no update than an update that breaks the installation."""
    monkeypatch.setattr(updater, "plateforme", lambda: "macos")
    monkeypatch.setattr(updater, "_open", lambda url: _Fake(_release(
        "mountmonitor-app-9.9.9-windows.zip", "mountmonitor-app-9.9.9-linux.zip")))
    assert updater.check("1.0.0") is None


@pytest.mark.parametrize("plate", ["windows", "macos", "linux"])
def test_unsuffixed_archive_suits_everyone(plate, monkeypatch):
    """It only contains `app/`, that is, pure Python.

    Compiled dependencies live in `python/`, which the update does not
    touch. It is also the format of earlier versions.
    """
    monkeypatch.setattr(updater, "_open", lambda url: _Fake(_release(
        "mountmonitor-app-9.9.9.zip")))
    monkeypatch.setattr(updater, "plateforme", lambda: plate)
    assert updater.check("1.0.0") is not None


def test_my_platform_suffix_beats_common_archive(monkeypatch):
    monkeypatch.setattr(updater, "plateforme", lambda: "macos")
    monkeypatch.setattr(updater, "_open", lambda url: _Fake(_release(
        "mountmonitor-app-9.9.9.zip",
        "mountmonitor-app-9.9.9-macos.zip")))
    update = updater.check("1.0.0")
    assert update is not None and update["url"].endswith("-macos.zip")


def test_exec_bit_survives_extraction(tmp_path):
    """zipfile does not restore it: without this the app no longer restarts after an update."""
    if sys.platform.startswith("win"):
        pytest.skip("POSIX permissions do not apply on Windows")
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as z:
        info = zipfile.ZipInfo("lanceur")
        info.external_attr = 0o755 << 16
        z.writestr(info, "#!/bin/sh\necho ok\n")
    dest = tmp_path / "out"
    with zipfile.ZipFile(archive) as z:
        z.extractall(dest)
        import os
        for i in z.infolist():
            mode = i.external_attr >> 16
            if mode & 0o111:
                p = dest / i.filename
                p.chmod(p.stat().st_mode | 0o111)
    assert (dest / "lanceur").stat().st_mode & 0o111


class _Fake:
    """Minimal HTTP response: json.load(r) must work."""

    def __init__(self, payload):
        import json
        self._t = json.dumps(payload)

    def read(self, *a):
        t, self._t = self._t, ""
        return t.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("interpreter", ["python/python.exe", "python/bin/python3"])
def test_package_recognised_on_three_systems(interpreter, tmp_path, monkeypatch):
    """Up to 1.31, only python.exe was looked for: on macOS and Linux the
    package believed it was run from source and never looked for updates."""
    (tmp_path / "app").mkdir()
    exe = tmp_path / interpreter
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(updater, "app_dir", lambda: tmp_path / "app")
    assert updater.is_packaged()


def test_migration_of_data_written_in_app(tmp_path, monkeypatch):
    """Versions <= 1.31 outside Windows: settings and logs were in app/.
    They are copied once, without overwriting what already exists."""
    from src.config import paths
    app = tmp_path / "app"
    (app / "Logs").mkdir(parents=True)
    (app / "Logs" / "nuit.dat").write_text("ancien")
    (app / "mountmonitor_settings.json").write_text('{"ancien": 1}')
    data = tmp_path / "donnees"
    data.mkdir()
    (data / "reglages_rapports.json").write_text("deja la")
    monkeypatch.setattr(paths, "_PROJECT_ROOT", app)
    monkeypatch.setattr(paths, "_MIGRATION_DONE", False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    paths._migrate_old_data(data)
    assert (data / "Logs" / "nuit.dat").read_text() == "ancien"
    assert (data / "mountmonitor_settings.json").exists()
    assert (data / "reglages_rapports.json").read_text() == "deja la"
