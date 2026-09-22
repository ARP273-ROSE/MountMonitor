# -*- coding: utf-8 -*-
"""Chaque systeme doit recevoir SON archive.

Une archive Windows posee sur un macOS remplace l'application par des binaires
inutilisables : l'utilisateur perd une installation qui marchait, et la seule
issue est une reinstallation manuelle.
"""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import updater  # noqa: E402


@pytest.fixture(autouse=True)
def _depot_declare(monkeypatch):
    """check() refuse de travailler sans depot : kit.json n'est pas toujours la."""
    monkeypatch.setattr(updater, "REPO", "ARP273-ROSE/MountMonitor", raising=False)
    # PREFIXE_ARCHIVE vient de kit.json : hors du depot il tombe sur une valeur
    # degradee et plus aucun asset ne correspond.
    monkeypatch.setattr(updater, "PREFIXE_ARCHIVE", "mountmonitor-app-", raising=False)


def _publication(*noms):
    return {
        "tag_name": "v9.9.9",
        "body": "notes",
        "assets": [{"name": n, "browser_download_url": "http://x/" + n, "size": 1}
                   for n in noms],
    }


@pytest.mark.parametrize("plate,attendu", [
    ("windows", "mountmonitor-app-9.9.9-windows.zip"),
    ("macos", "mountmonitor-app-9.9.9-macos.zip"),
    ("linux", "mountmonitor-app-9.9.9-linux.zip"),
])
def test_chaque_systeme_prend_son_archive(plate, attendu, monkeypatch):
    monkeypatch.setattr(updater, "plateforme", lambda: plate)
    monkeypatch.setattr(updater, "_open", lambda url: _Faux(_publication(
        "mountmonitor-app-9.9.9-windows.zip",
        "mountmonitor-app-9.9.9-macos.zip",
        "mountmonitor-app-9.9.9-linux.zip",
        "MountMonitor-Setup-9.9.9.exe",
    )))
    maj = updater.check("1.0.0")
    assert maj is not None and maj["url"].endswith(attendu)


def test_l_installeur_n_est_jamais_choisi(monkeypatch):
    """Il s'installe, il ne se deploie pas par-dessus l'application."""
    monkeypatch.setattr(updater, "plateforme", lambda: "windows")
    monkeypatch.setattr(updater, "_open", lambda url: _Faux(_publication(
        "MountMonitor-Setup-9.9.9.exe", "MountMonitor-9.9.9.dmg")))
    assert updater.check("1.0.0") is None


def test_une_archive_d_un_autre_systeme_n_est_jamais_posee(monkeypatch):
    """Mieux vaut pas de mise a jour qu'une mise a jour qui casse l'installation."""
    monkeypatch.setattr(updater, "plateforme", lambda: "macos")
    monkeypatch.setattr(updater, "_open", lambda url: _Faux(_publication(
        "mountmonitor-app-9.9.9-windows.zip", "mountmonitor-app-9.9.9-linux.zip")))
    assert updater.check("1.0.0") is None


@pytest.mark.parametrize("plate", ["windows", "macos", "linux"])
def test_une_archive_sans_suffixe_convient_a_tout_le_monde(plate, monkeypatch):
    """Elle ne contient que `app/`, c'est-a-dire du Python pur.

    Les dependances compilees vivent dans `python/`, que la mise a jour ne
    touche pas. C'est aussi le format des versions anterieures.
    """
    monkeypatch.setattr(updater, "_open", lambda url: _Faux(_publication(
        "mountmonitor-app-9.9.9.zip")))
    monkeypatch.setattr(updater, "plateforme", lambda: plate)
    assert updater.check("1.0.0") is not None


def test_le_suffixe_de_ma_plateforme_passe_avant_l_archive_commune(monkeypatch):
    monkeypatch.setattr(updater, "plateforme", lambda: "macos")
    monkeypatch.setattr(updater, "_open", lambda url: _Faux(_publication(
        "mountmonitor-app-9.9.9.zip",
        "mountmonitor-app-9.9.9-macos.zip")))
    maj = updater.check("1.0.0")
    assert maj is not None and maj["url"].endswith("-macos.zip")


def test_le_bit_d_execution_survit_a_l_extraction(tmp_path):
    """zipfile ne le restitue pas : sans cela l'app ne redemarre plus apres maj."""
    if sys.platform.startswith("win"):
        pytest.skip("les permissions POSIX n'ont pas cours sous Windows")
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


class _Faux:
    """Reponse HTTP minimale : json.load(r) doit fonctionner."""

    def __init__(self, charge):
        import json
        self._t = json.dumps(charge)

    def read(self, *a):
        t, self._t = self._t, ""
        return t.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
