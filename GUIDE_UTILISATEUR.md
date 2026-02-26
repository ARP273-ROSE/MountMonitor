# MountMonitor — Guide Utilisateur Complet

## C'est quoi MountMonitor ?

MountMonitor est un programme qui **surveille en temps réel la précision de suivi de ta monture télescope** pendant tes sessions d'astrophotographie.

### En termes simples :

Imagine que tu fais une pose longue de 180 secondes sur une nébuleuse. Pendant ces 3 minutes, ta monture doit suivre le ciel avec une précision extrême. MountMonitor te montre **en direct** si ta monture suit correctement ou si elle dévie.

### À quoi ça sert concrètement ?

1. **Vérifier la qualité de suivi** — Tu poses tes images, et MountMonitor tourne en arrière-plan. Si tes images sont floues ou ont des étoiles allongées, tu peux consulter les logs pour voir ce qui s'est passé.

2. **Diagnostiquer les problèmes** — Si les graphes montrent des pics de déviation, ça peut indiquer :
   - Du vent qui secoue la monture
   - Des vibrations (passage de voiture, train, etc.)
   - Un problème mécanique de la monture (erreur périodique)
   - Un guidage qui corrige trop ou pas assez

3. **Comparer avant/après** — Après avoir fait un réglage (alignement polaire, modèle de pointage, etc.), tu peux comparer les graphes pour voir si ça s'est amélioré.

4. **Surveiller le temps** — Vérifier que les horloges PC et monture restent synchronisées (important pour le goto et le suivi).

---

## Les Graphiques — Comprendre ce qu'on voit

### Graphe AD (Ascension Droite) — En magenta/violet

C'est le graphe le plus important. Il montre **combien ta monture dévie en AD** par rapport à sa position idéale.

- **Ligne magenta** = la déviation réelle en secondes d'arc ("")
- **Ligne verte** = la limite de tolérance que tu as fixée
- **Ligne bleue** = l'écart-type glissant (une mesure de la "nervosité" du suivi)
- **Lignes pointillées** = les valeurs min/max atteintes

**Comment lire :** Si la ligne magenta reste dans les lignes vertes, tout va bien. Si elle sort, ta monture dévie trop.

**Valeurs typiques pour ta config** (Takahashi FC-76DCU + ASI2600MC) :
- Ton échantillonnage est de 1.60"/pixel
- Une tolérance de 1.5" (environ 1 pixel) est raisonnable
- Si la déviation reste sous 1", c'est excellent

### Graphe DÉC (Déclinaison) — En rouge

Même chose que l'AD, mais pour l'axe Nord-Sud. En théorie, si l'alignement polaire est parfait, la DEC ne bouge pas du tout.

- Si tu vois de la dérive en DEC → alignement polaire à corriger
- Si tu vois des oscillations → problème de guidage ou flexion

### Graphe Temps — En gris/vert/rouge

Compare les horloges :
- **Ligne grise** = différence entre l'heure du PC et l'heure de la monture
- **Ligne verte** = durée d'un cycle de mesure (vue du PC)
- **Ligne rouge** = durée d'un cycle de mesure (vue de la monture)
- **Ligne bleue** (si NTP activé) = différence entre le PC et un serveur NTP

Si le vert et le rouge se superposent → les deux horloges sont d'accord. C'est normal.

### Graphe Sismique — En gris (optionnel)

Si tu as un sismomètre connecté, il montre les vibrations ambiantes. Utile pour corréler des pics de déviation avec des événements (passage de train, vent, etc.).

---

## L'Analyse FFT — Comprendre les fréquences

La FFT (Transformée de Fourier Rapide) transforme les données de suivi en **spectre de fréquences**. En gros, elle répond à la question : "Quelles sont les vibrations récurrentes ?"

### Graphe supérieur : Domaine fréquentiel
- Axe horizontal = fréquence (Hz)
- Axe vertical = amplitude
- Un pic à une certaine fréquence signifie qu'il y a une vibration régulière à cette fréquence

### Graphe inférieur : Domaine temporel (période)
- Axe horizontal = période (secondes)
- Même info mais vue différemment (période = 1/fréquence)
- Un pic à 480 secondes = l'erreur périodique de ta vis sans fin (worm gear)

### Exemples de ce que tu peux trouver :
- Pic à **8 minutes** (480s) → erreur périodique de la monture
- Pic à **0.5 Hz** → vibration mécanique (moteur, ventilateur)
- Pic à **1-5 Hz** → vibrations du sol (trafic)

---

## Les Fichiers Log

MountMonitor crée 4 fichiers à chaque session dans le dossier `Logs/` :

| Fichier | Contenu | Quand le consulter |
|---------|---------|-------------------|
| `.log` | Événements (changements de réglages, alertes) | Après une session problématique |
| `.dat` | Données RA/DEC complètes | Pour analyse détaillée dans Excel |
| `.dti` | Données de temps | Si tu suspectes un problème d'horloge |
| `.sei` | Données sismomètre | Si tu as un sismomètre |

Tous les fichiers sont en texte simple avec des tabulations. Tu peux les ouvrir dans Excel pour faire des graphes personnalisés.

---

## Configuration — Les Préférences

### Onglet Général
- **Nom de l'observatoire** — Juste un label pour les fichiers log
- **Protocole** — LX200 (TCP/IP pour 10Micron), ASCOM (drivers Windows), ou Simulation
- **IP / Port** — L'adresse de ta monture (en LX200). Pour toi avec l'AM3N, vérifie l'IP dans ton routeur

### Onglet Traitement
- **Fréquence de polling** — Combien de fois par seconde on interroge la monture. 2 Hz est un bon début
- **Plage glissante** — Fenêtre de calcul de l'écart-type : 60s pour une vue rapide, 300s pour plus de stabilité
- **Tolérance AD/DÉC** — Les lignes vertes sur les graphes. 1.5" est bien pour ton setup
- **Référence** — "Médiane" utilise la médiane des données comme référence. "Coordonnées cible" utilise le goto

### Onglet Auxiliaire
- **Serveur NTP** — Active-le pour avoir une ligne bleue sur le graphe temps. Utilise time.nist.gov
- **Sismomètre** — Si tu en as un, configure le port série ici

### Onglet Divers
- **Vérifications monture** — MountMonitor vérifie au démarrage que la réfraction est activée, que le suivi est sidéral, etc. Active celles qui correspondent à ta monture

---

## Mode Simulation

Si tu veux tester le programme sans monture, lance-le en mode simulation :

```
python main.py --sim-all
```

Ça simule :
- Une monture avec erreur périodique réaliste
- Du bruit aléatoire (vibrations, seeing)
- De la dérive (simule une erreur d'alignement polaire)
- Un sismomètre avec des micro-séismes

Parfait pour comprendre l'interface avant d'aller sur le terrain.

---

## Raccourcis Clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl+K` | Connecter à la monture |
| `Ctrl+D` | Déconnecter |
| `Ctrl+F` | Ouvrir la fenêtre FFT |
| `Ctrl+,` | Ouvrir les préférences |
| `Ctrl+Q` | Quitter |
| `F1` | Aide |

---

## FAQ

### "J'ai une ZWO AM3N, quel protocole utiliser ?"
L'AM3N est compatible ASCOM et LX200. Si tu la contrôles via ASIAIR, MountMonitor peut se connecter en TCP/IP (LX200) à l'adresse IP de l'AM3N. Vérifie le port dans les réglages de la monture.

### "C'est quoi l'erreur périodique (PE) ?"
C'est une erreur mécanique causée par les engrenages de la monture. Elle se répète à chaque tour de vis sans fin. Sur les montures harmoniques comme l'AM3N, cette erreur est très faible.

### "Quand est-ce que je dois m'inquiéter ?"
- Déviation > 2-3" sur des poses de 3 minutes → vérifie le guidage
- Dérive constante en DEC → refais l'alignement polaire
- Pics réguliers en AD → erreur périodique, active le PEC
- Pics aléatoires dans tous les axes → vibrations, vérifie la stabilité du trépied

### "MountMonitor peut-il corriger les erreurs ?"
Non ! MountMonitor **observe seulement**, il ne modifie rien dans la monture. Il ne touche ni les réglages, ni l'horloge. C'est juste un diagnostic.

---

## Architecture Technique (pour référence)

```
MountMonitor/
├── main.py                        # Point d'entrée
├── VERSION                        # Version actuelle
├── requirements.txt               # Dépendances Python
├── launch.bat / launch.sh         # Lanceurs
├── src/
│   ├── config/                    # Configuration JSON
│   │   ├── settings.py            # Gestionnaire de réglages
│   │   └── defaults.py            # Valeurs par défaut
│   ├── core/                      # Moteur de l'application
│   │   ├── mount_connection.py    # Interface abstraite monture
│   │   ├── lx200_protocol.py      # Protocole LX200 TCP/IP
│   │   ├── poller.py              # Boucle de polling
│   │   ├── data_processor.py      # Stats, STDEV, tolerances
│   │   ├── ntp_client.py          # Synchronisation NTP
│   │   └── seismometer.py         # Interface sismomètre
│   ├── gui/                       # Interface graphique
│   │   ├── main_window.py         # Fenêtre principale
│   │   ├── graph_widgets.py       # Graphes temps réel
│   │   ├── fft_window.py          # Fenêtre FFT
│   │   ├── status_panel.py        # Panneau de statut
│   │   ├── preferences_dialog.py  # Dialogue préférences
│   │   └── theme.py               # Thème sombre
│   ├── models/                    # Modèles de données
│   │   ├── mount_data.py          # Structures de données
│   │   └── data_buffer.py         # Buffer circulaire
│   ├── simulation/                # Mode simulation
│   │   ├── sim_mount.py           # Monture simulée
│   │   └── sim_seismometer.py     # Sismomètre simulé
│   ├── logging_module/            # Journalisation
│   │   ├── file_logger.py         # Fichiers .log/.dat/.dti/.sei
│   │   └── crash_reporter.py      # Rapport de crash
│   └── utils/                     # Utilitaires
│       ├── i18n.py                # Bilingue FR/EN
│       ├── coordinates.py         # Parsing RA/DEC
│       └── hardware_detect.py     # Détection matériel
└── Logs/                          # Fichiers de session
```
