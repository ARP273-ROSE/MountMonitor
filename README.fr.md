# MountMonitor

**[English](README.md)** · **[Télécharger](https://github.com/ARP273-ROSE/MountMonitor/releases/latest)** · Manuels : [FR](docs/manual_fr.pdf) · [EN](docs/manual_en.pdf) · [NL](docs/manual_nl.pdf)

**Surveillance en temps réel d'une monture de télescope pour l'astrophotographie : écarts en
ascension droite et en déclinaison, exactitude des horloges, vibrations, analyse de Fourier et
rapport de nuit. Réécriture Python/PyQt6 de MountMonitor v3.37 (Java) de Nicolàs de Hilster.
Interface en anglais, français et néerlandais ; Windows, macOS et Linux.**

## Installer

Depuis la [page des versions](https://github.com/ARP273-ROSE/MountMonitor/releases/latest),
Python compris, sans droits d'administrateur :

| Système | Fichier |
|---|---|
| **Windows 10 (1809) ou plus récent** | `MountMonitor-Setup-X.Y.Z.exe` (lien permanent : [MountMonitor-Setup.exe](https://github.com/ARP273-ROSE/MountMonitor/releases/latest/download/MountMonitor-Setup.exe)) |
| **macOS 11 ou plus récent** | `MountMonitor-X.Y.Z-macos-arm64.dmg` (Apple Silicon) / `-macos-x86_64.dmg` (Intel) ; la première fois : clic droit → Ouvrir |
| **Linux x86_64 (glibc 2.28+) / ARM64 (glibc 2.39+)** | `MountMonitor-X.Y.Z-linux-x86_64.tar.gz` / `-linux-arm64.tar.gz`, puis `./installer.sh` (sans sudo) |

**Ce qui dépend du système** : la monture se joint par le réseau (LX200 en TCP/IP, la voie
habituelle d'une 10Micron GM1000/2000) ou par un port série sur les trois systèmes ; **ASCOM
n'existe que sous Windows** (protocole grisé ailleurs). L'apparence est figée (style Fusion,
palette complète, polices embarquées) et identique partout ; sous Linux, les boîtes de fichiers
sont les boîtes complètes de Qt.

Essai sans matériel : `MountMonitor --sim-all`. Depuis les sources : Python 3.10+,
`pip install -r requirements.txt`, puis `python main.py`.

## Mises à jour, rapports, données

- L'application installée cherche une nouvelle version au démarrage et sur demande
  (**Aide → Rechercher des mises à jour**), la pose et redémarre, sur les trois systèmes.
- Avec votre accord (demandé une fois), plantages, crashs natifs et gels envoient un court
  rapport technique anonyme ; **Aide → Signaler un problème…** pour écrire soi-même, et la case
  **Envoyer automatiquement les rapports d'incident** pour retirer l'accord.
- Réglages, journaux de session et rapports de l'application installée vivent hors du dossier
  d'installation (`%LOCALAPPDATA%\MountMonitor`, `~/.local/share/MountMonitor`).
- **Langue** : celle du système au premier lancement, puis le menu **Langue**.

## Licence

MIT — voir [LICENSE](LICENSE). Le détail des versions est dans [CHANGELOG.md](CHANGELOG.md).
