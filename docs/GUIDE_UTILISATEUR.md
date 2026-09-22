# MountMonitor — Guide Utilisateur Complet

---

## Table des matières

1. [Qu'est-ce que MountMonitor ?](#1-quest-ce-que-mountmonitor)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Connexion de la monture](#3-connexion-de-la-monture)
4. [Les graphiques en détail](#4-les-graphiques-en-détail)
5. [Le panneau d'état](#5-le-panneau-détat)
6. [Interpréter les données](#6-interpréter-les-données)
7. [Analyse FFT — Comprendre les transformées de Fourier](#7-analyse-fft--comprendre-les-transformées-de-fourier)
8. [Le sismomètre](#8-le-sismomètre)
9. [Journalisation et export](#9-journalisation-et-export)
10. [Relecture et analyse des logs du matin](#10-relecture-et-analyse-des-logs-du-matin)
11. [Préférences détaillées](#11-préférences-détaillées)
12. [Diagnostics et résolution de problèmes](#12-diagnostics-et-résolution-de-problèmes)
13. [Annexes techniques](#13-annexes-techniques)

---

## 1. Qu'est-ce que MountMonitor ?

### Vue d'ensemble

MountMonitor est un logiciel de **surveillance en temps réel des performances de suivi** d'une monture de télescope pour l'astrophotographie. Développé à l'origine par Nicolás de Hilster (Pays-Bas) pour les montures 10Micron, il fonctionne avec toute monture compatible ASCOM ou LX200.

Le programme est **non-invasif** : il interroge la monture mais ne modifie jamais aucun réglage. Il observe, enregistre et visualise — c'est un outil de diagnostic pur.

### Pourquoi c'est essentiel

En astrophotographie à longue pose, la monture doit compenser **exactement** la rotation de la Terre. La moindre erreur de suivi se traduit par des étoiles allongées (trailing). MountMonitor permet de :

- **Voir en temps réel** la précision de suivi en ascension droite (RA) et déclinaison (DEC)
- **Quantifier** les erreurs en secondes d'arc (arcsec, noté `"`)
- **Identifier la source** des problèmes : erreur périodique, alignement polaire, vibrations, vent
- **Vérifier les réglages** de la monture (réfraction, vitesse de suivi, GPS, suivi dual)
- **Documenter** les performances avec des fichiers log et des captures de graphiques
- **Corréler** les perturbations de suivi avec les vibrations environnementales (sismomètre)
- **Analyser les fréquences** des erreurs par transformée de Fourier (FFT)

### Précision requise selon la focale

La règle d'or : l'erreur de suivi doit être **inférieure à l'échelle pixel** de votre imageur.

| Focale | Échelle pixel typique | Précision nécessaire | Difficulté |
|--------|----------------------|---------------------|------------|
| 50-200 mm  | 4-15"/pixel | 5-15" | Facile, la plupart des montures |
| 300-500 mm | 1.5-3"/pixel | 1.5-3" | Monture de qualité ou autoguidage |
| 500-1000 mm | 0.8-1.5"/pixel | 0.8-1.5" | Excellent guidage ou monture haut de gamme |
| 1000-2000 mm | 0.3-0.8"/pixel | 0.3-0.8" | Monture 10Micron ou guidage précis |
| 2000 mm+ | <0.4"/pixel | <0.4" | Monture d'observatoire professionnel |

**Formule :** `Échelle pixel (") = 206.265 × taille_pixel_µm / focale_mm`

---

## 2. Installation et lancement

### Lancement rapide (recommandé)

**Le plus simple : utilisez le lanceur automatique.** Il détecte Python, crée l'environnement virtuel, installe les dépendances et lance l'application.

```bash
# Windows — double-cliquer sur :
launch.bat

# Linux / macOS :
chmod +x launch.sh
./launch.sh
```

Le lanceur effectue automatiquement les étapes suivantes :

| Étape | Ce qu'il fait |
|-------|---------------|
| **Step 1/4** | Recherche Python 3.10+ (emplacements courants, py launcher, PATH) |
| **Step 2/4** | Crée ou vérifie l'environnement virtuel (`venv/`) |
| **Step 3/4** | Installe les dépendances (seulement si nécessaire) |
| **Step 4/4** | Lance MountMonitor |

**Si Python n'est pas trouvé :**
- **Windows** : le lanceur propose de télécharger et installer Python 3.12 automatiquement (avec barre de progression)
- **Linux** : propose la commande apt/dnf/pacman adaptée
- **macOS** : propose l'installation via Homebrew

**Options du lanceur :**

```bash
# Mode simulation
launch.bat --sim-all

# Réparer une installation corrompue (supprime le venv et réinstalle tout)
launch.bat --repair

# Combiner les deux
launch.bat --repair --sim-all
```

### Vérification d'intégrité automatique

À chaque lancement, le lanceur vérifie :
- Que l'environnement virtuel est fonctionnel (pas de Python supprimé, pas de corruption)
- Que toutes les dépendances clés sont importables (PyQt6, pyqtgraph, numpy, serial, ntplib)
- Que le `requirements.txt` n'a pas changé depuis la dernière installation

Si un problème est détecté, les dépendances sont automatiquement réinstallées. En cas d'échec, utilisez `--repair` pour repartir de zéro.

### Prérequis

- **Python 3.10+** (recommandé : 3.12) — installé automatiquement par le lanceur si absent
- **ASCOM Platform** installé (pour la connexion ASCOM sur Windows)
- **Driver ASCOM** de votre monture installé

### Dépendances Python

```
PyQt6>=6.6.0        # Interface graphique
pyqtgraph>=0.13.3   # Graphiques temps réel
numpy>=1.24.0       # Calculs numériques
pyserial>=3.5       # Port série (LX200 Serial + sismomètre)
ntplib>=0.4.0       # Synchronisation NTP
comtypes>=1.2.0     # ASCOM (Windows uniquement)
requests>=2.31.0    # Mises à jour et communication réseau
```

Installation manuelle (si vous n'utilisez pas le lanceur) : `pip install -r requirements.txt`

### Modes de lancement

```bash
# Via le lanceur automatique (recommandé)
launch.bat                         # Windows — mode normal
launch.bat --sim-all               # Windows — simulation
./launch.sh                        # Linux/macOS — mode normal
./launch.sh --sim-all              # Linux/macOS — simulation

# Lancement direct (si dépendances déjà installées)
python main.py                     # Mode normal (connexion réelle)
python main.py --sim-all           # Simulation complète
python main.py --sim-mount         # Simulation monture seule
python main.py --sim-seismometer   # Simulation sismomètre seul
python main.py --log-level DEBUG   # Mode debug (logs détaillés)
```

### Multiplateforme

MountMonitor fonctionne sur **Windows**, **Linux** et **macOS**. Les fonctionnalités ASCOM sont spécifiques à Windows. Sur Linux/macOS, utilisez LX200 TCP/IP ou LX200 Serial.

---

## 3. Connexion de la monture

### Protocoles disponibles

| Protocole | Usage | Configuration requise |
|-----------|-------|----------------------|
| **ASCOM** | Recommandé sur Windows | Bouton "Select..." ouvre le sélecteur ASCOM natif |
| **LX200 (TCP/IP)** | Connexion réseau directe | Adresse IP + port (défaut : 192.168.1.1:3492) |
| **LX200 (Serial)** | Connexion série directe | Port COM (auto-détecté) |
| **Simulation** | Test et démonstration | Aucune configuration nécessaire |

### Connexion ASCOM (recommandée)

1. Ouvrir les **Préférences** (Ctrl+,)
2. Dans l'onglet **General**, sélectionner **ASCOM** dans le protocole
3. Cliquer **Select... / Sélectionner...** pour ouvrir le sélecteur ASCOM
4. Choisir votre driver de monture dans la liste
5. Cliquer OK, puis fermer les préférences et cliquer **Connect**

> **Astuce :** Si vous cliquez "Connect" sans avoir sélectionné de driver, le sélecteur ASCOM s'ouvre automatiquement.

### Connexion LX200 TCP/IP

Pour les montures 10Micron connectées en réseau :
1. Sélectionner **LX200 (TCP/IP)** dans les préférences
2. Entrer l'adresse IP de la monture (ex : `10.0.1.151`)
3. Entrer le port TCP (défaut : `3492` pour les 10Micron)
4. Connecter

### Connexion LX200 Serial

Pour les montures avec connexion série :
1. Sélectionner **LX200 (Serial)** dans les préférences
2. Choisir le port COM dans le menu déroulant (ports auto-détectés)
3. Connecter (baudrate : 9600, 8N1)

### Vérifications automatiques à la connexion

À chaque connexion (et après chaque slew), MountMonitor vérifie :

| Vérification | Ce qu'il vérifie | Valeur attendue |
|--------------|-----------------|-----------------|
| **Correction de réfraction** | Mode de correction atmosphérique | "Continuously updating" |
| **Vitesse de suivi** | Mode de tracking | "Sidereal" (pour le ciel profond) |
| **Synchronisation GPS** | Horloge GPS verrouillée | "Synchronising" |
| **Suivi dual** | Suivi sur les 2 axes | Selon votre config |

Si un réglage ne correspond pas, une alerte jaune s'affiche avec les détails.

---

## 4. Les graphiques en détail

### 4.1 Graphique RA (Ascension Droite) — LE PLUS IMPORTANT

Le graphe RA montre la **déviation de suivi** par rapport à une référence (médiane ou coordonnées cible) en secondes d'arc.

```
┌─────────────────────────────────────────────────────────┐
│  ···· ←Ligne Max STDEV (bleu pointillé)                 │  +0.85"  σmax
│ ────── ←Ligne tolérance haute (vert)                    │  +1.50"
│          ╱╲    ╱╲                                        │
│    ╱╲  ╱    ╲╱    ╲╱╲     ←Courbe données (magenta)     │
│ ──╱──╲╱─────────────────── ←Ligne médiane (gris tiret)  │   0.00"
│ ╱      ····                ←Courbe STDEV (bleu)          │
│ ────── ←Ligne tolérance basse (vert)                    │  -1.50"
│ ╌╌╌╌╌╌ ←Ligne min (magenta pointillé)                   │  -0.87"
│    │         │         │   ←Marqueurs 30s (gris)         │
│   0:30      1:00      1:30                               │  temps
└─────────────────────────────────────────────────────────┘
                                          +0.45"  σ=0.32"  ←Stats
```

#### Légende des éléments

| Élément | Style | Couleur | Rôle |
|---------|-------|---------|------|
| **Courbe de données** | Trait continu 1.5px | Magenta | Déviation instantanée en arcsec |
| **Courbe STDEV** | Trait continu 1.5px | Bleu | Écart-type glissant (dispersion) |
| **Lignes de tolérance** | Trait continu 1px | Vert | Seuils ± configurables (défaut ±1.5") |
| **Lignes Min/Max** | Pointillé 1px | Magenta | Extrema depuis le dernier reset |
| **Ligne médiane** | Tiret-point 1px | Gris | Référence à 0 |
| **Ligne Max STDEV** | Pointillé 1px | Bleu | Écart-type maximum atteint |
| **Marqueurs temporels** | Pointillé vertical | Gris | Repères toutes les 30 secondes |
| **Filigrane** | Texte 24pt 15% opacité | Gris | Titre "RA" en arrière-plan |
| **Stats** | Texte coin supérieur droit | Blanc | Valeur actuelle + RMS courant |
| **Labels tolérance** | Texte petit | Vert | Valeur en arcsec à droite de chaque ligne |
| **Labels min/max** | Texte petit | Magenta | Valeur en arcsec à droite |

### 4.2 Graphique DEC (Déclinaison)

Structure identique au graphe RA mais en **rouge**. Montre la déviation en déclinaison.

**Différence clé avec le RA :** En suivi normal, la DEC devrait rester **quasi plate** car il n'y a théoriquement pas de mouvement DEC en suivi sidéral. Toute dérive systématique en DEC indique une erreur d'alignement polaire.

### 4.3 Graphique TIME (Comparaison temporelle)

```
┌─────────────────────────────────────────────────────────┐
│ PC-Mount: +5.2ms  PC loop: 501ms  Mt loop: 432ms       │
│                                                          │
│ ═══════════════════════════════════ ←PC-Mount (blanc)    │
│ ─────────────────────────────────── ←PC-NTP (bleu)      │
│ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ ←Zéro (gris)        │
│ ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ ←PC loop (vert)      │
│ ▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪▪ ←Mount loop (rouge)  │
│                               Drift: +0.05 ms/min       │
└─────────────────────────────────────────────────────────┘
```

| Courbe | Couleur | Ce qu'elle mesure |
|--------|---------|-------------------|
| **PC-Mount** | Blanc brillant | Écart de temps entre le PC et la monture (ms) |
| **PC loop** | Vert | Durée d'un cycle de polling côté PC (ms) |
| **Mount loop** | Rouge | Temps de réponse de la monture (ms) |
| **PC-NTP** | Bleu | Décalage PC vs serveur NTP (ms) |
| **Ligne zéro** | Gris pointillé | Référence à 0 ms |

**Informations supplémentaires affichées :**
- **Drift** : taux de dérive en ms/min — indique si les horloges divergent
- **Valeurs courantes** de chaque trace en haut du graphe

### 4.4 Graphique AXIAL (Vitesse/Déplacement)

Activable dans Préférences → Processing → Axial mode.

```
┌─────────────────────────────────────────────────────────┐
│ RA: +0.0012"/s/min  DEC: -0.0003"/s/min                │
│                                                          │
│ ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ ←RA regression (blanc)  │
│ ≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈ ←RA avg (magenta épais) │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ ←RA raw (gris fin)      │
│ ─────────────────────────────── ←Zéro                    │
│ ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ ←DEC raw (gris sombre)  │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ←DEC avg (rouge épais)  │
└─────────────────────────────────────────────────────────┘
```

| Courbe | Couleur | Épaisseur | Description |
|--------|---------|-----------|-------------|
| **RA raw** | Gris (120,120,130) | 1px | Vitesse brute axe RA ("/s) |
| **DEC raw** | Gris sombre (140,140,150) | 1px | Vitesse brute axe DEC ("/s) |
| **RA avg** | Magenta | 2.5px | Moyenne glissante 6 points RA |
| **DEC avg** | Rouge | 2.5px | Moyenne glissante 6 points DEC |
| **RA regression** | Blanc pointillé | 3px | Régression linéaire RA |
| **DEC regression** | Rose pointillé | 3px | Régression linéaire DEC |
| **Ligne zéro** | Gris pointillé | 1px | Référence vitesse nulle |

**Ce que montre la pente de régression :** la valeur en "/s/min indique si la vitesse axiale change dans le temps. Une pente nulle = vitesse constante = normal. Une pente significative = dérive thermique ou mécanique.

### 4.5 Graphique SEISMIC (Sismomètre)

Visible quand un sismomètre est connecté (ou en simulation).

| Élément | Couleur | Description |
|---------|---------|-------------|
| **Données** | Gris clair | Amplitude brute centrée sur zéro |
| **STDEV** | Bleu | Écart-type glissant |
| **Tolérance ±** | Vert | Seuils basés sur un % de la plage |

---

## 5. Le panneau d'état

Le panneau à droite des graphiques affiche les informations en temps réel.

### Indicateur de connexion

| Couleur | Signification |
|---------|---------------|
| 🟢 Vert | Connecté, en suivi (tracking) |
| 🟡 Jaune | En rotation (slewing) |
| 🔴 Rouge | Erreur de connexion |
| ⚪ Gris | Déconnecté / au parc / au repos |

### Valeurs en temps réel

```
● Tracking
RA:  12:34:56.78   Δ +0.23"   σ 0.45"
DEC: +56:34:12.3   Δ -0.15"   σ 0.32"
2.0 Hz | 1234 samples
```

- **Δ (delta)** : déviation instantanée — **s'affiche en ROUGE** si la tolérance est dépassée
- **σ (sigma)** : écart-type glissant — affiché en bleu

### Messages horodatés

Le panneau affiche un journal défilant avec les événements :
- **Blanc** : Information générale
- **Vert** : Vérification OK (✓)
- **Jaune** : Avertissement (⚠)
- **Rouge** : Erreur ou tolérance dépassée

---

## 6. Interpréter les données

### 6.1 Qualité du suivi — Barème STDEV

| STDEV RA | Qualité | Adapté pour |
|----------|---------|-------------|
| < 0.3" | **Excellent** | Longues poses à longue focale (>1000mm), non guidé sur 10Micron |
| 0.3" - 0.5" | **Très bon** | Imagerie haute résolution (<1"/pixel) |
| 0.5" - 1.0" | **Bon** | Ciel profond standard (1-2"/pixel) |
| 1.0" - 2.0" | **Acceptable** | Grand champ (>2"/pixel) ou poses courtes |
| > 2.0" | **Insuffisant** | Étoiles probablement allongées |

**Règle pratique :** Votre STDEV doit être inférieur à votre échelle pixel. En conditions de seeing moyen (2-3" FWHM), viser mieux que la moitié du seeing n'apporte plus rien.

### 6.2 Identifier l'erreur périodique (PE)

L'erreur périodique est une oscillation **régulière sinusoïdale** causée par les imperfections des engrenages (vis sans fin).

**Comment la reconnaître :**
- Oscillation lisse et régulière sur le graphe RA
- Période constante (typiquement 4-10 minutes)
- Se répète cycle après cycle

**Périodes typiques :**

| Monture | Période PE |
|---------|------------|
| 10Micron GM1000/2000/3000/4000 | ~480 s (8 min) |
| EQ6 / HEQ5 | ~478 s |
| Losmandy G11 | ~480 s |
| Takahashi EM-200 | ~600 s |
| Paramount MX/MX+ | ~150 s |

**Amplitudes typiques :**

| Type de monture | PE sans PEC | PE avec PEC |
|-----------------|-------------|-------------|
| Entrée de gamme | 30-120" | 10-30" |
| Milieu de gamme | 10-30" | 3-10" |
| Haut de gamme | 3-10" | <1" |
| 10Micron HPS (encodeurs) | ±4" méca | <1" (0.6" RMS) |

### 6.3 Identifier une erreur d'alignement polaire

**Le symptôme clé : dérive constante en DEC.**

Si le graphe DEC montre une pente régulière qui ne s'aplatit jamais, c'est un défaut d'alignement polaire.

**Quantifier l'erreur :**
- Dérive de 1"/min en DEC ≈ erreur polaire de ~4' (minutes d'arc)
- Formule approx : `erreur polaire (') ≈ dérive DEC ("/min) × 3.82`

**Ce que le RA montre en parallèle :**
- Une erreur polaire crée aussi un drift en RA, mais il est souvent masqué par l'erreur périodique

### 6.4 Table de diagnostic — Symptômes et causes

| Symptôme sur les graphiques | RA | DEC | Sismique | Cause probable |
|----------------------------|-----|------|----------|----------------|
| Oscillation sinusoïdale régulière | ✓ | - | - | **Erreur périodique** (PE) |
| Dérive constante | - | ✓ | - | **Alignement polaire** |
| Sursauts brusques | ✓ | - | - | **Backlash** (jeu dans les engrenages) |
| Pics aléatoires violents | ✓ | ✓ | ✓ | **Vibrations externes** (vent, pas) |
| Pics sans signal sismique | ✓ | ✓ | - | **Problème mécanique interne** |
| STDEV qui monte progressivement | ✓ | ✓ | - | **Flexion du tube** ou déséquilibre |
| Oscillation haute fréquence | ✓ | ✓ | - | **Mauvais engrènement** ou usure |
| Vitesse axiale qui dérive | - | - | - | **Déformation thermique** (graphe axial) |
| PC-Mount qui diverge | - | - | - | **Problème horloge** (graphe temps) |
| Mount loop avec des pics | - | - | - | **Monture occupée** ou congestion |

### 6.5 Impact du vent et des conditions

- **Vent** : oscillations erratiques en RA et DEC, corrélées avec le sismomètre
- **Seeing** : n'affecte PAS le suivi (MountMonitor lit les encodeurs, pas les étoiles)
- **Température** : dérive lente par dilatation thermique (visible sur le graphe axial)
- **Humidité** : peut affecter l'électronique si condensation

---

## 7. Analyse FFT — Comprendre les transformées de Fourier

### C'est quoi la FFT ? (explication simple)

Imagine que tu écoutes un orchestre. Ton oreille entend un mélange de sons, mais ton cerveau arrive à distinguer les instruments individuels (violon, trompette, tambour). **La FFT (Fast Fourier Transform) fait exactement la même chose, mais avec des données numériques** : elle prend un signal complexe (le mélange de tous les mouvements de ta monture) et le décompose en ses composantes individuelles.

**En entrée :** une courbe qui varie dans le temps (l'erreur de suivi RA ou DEC qui oscille)
**En sortie :** un graphique qui montre **quelles oscillations** sont présentes et **à quelle intensité**

C'est comme passer d'un enregistrement audio brut à un spectre montrant chaque note de musique avec son volume.

### Pourquoi c'est utile pour ta monture ?

Ta monture a des engrenages. Chaque engrenage a des imperfections qui créent des oscillations **régulières**. La FFT permet de :
- **Identifier l'erreur périodique** (PE) : l'oscillation principale de la vis sans fin
- **Voir les harmoniques** : des oscillations à des multiples de la fréquence PE
- **Détecter des vibrations** : moteurs, vent, sol
- **Distinguer** un problème mécanique d'une perturbation externe

### Accéder à l'FFT

Menu **View → Show FFT Window** ou **Ctrl+F**

> **Nouveau :** La FFT est maintenant enregistrée automatiquement dans le fichier `.fft` pendant toute la session, même si la fenêtre FFT n'est pas ouverte. Les 3 pics dominants de chaque axe (RA, DEC, sismique) sont sauvegardés toutes les 2 secondes.

### Organisation de la fenêtre

La fenêtre FFT contient **deux graphiques** :

1. **Graphe supérieur — Domaine fréquentiel**
   - Axe X : Fréquence en Hertz (Hz = oscillations par seconde)
   - Axe Y : Amplitude (force de l'oscillation en arcsec)
   - Plus intuitif pour les vibrations rapides

2. **Graphe inférieur — Domaine périodique**
   - Axe X : Période en secondes (temps pour un cycle complet) = 1/fréquence
   - Axe Y : Amplitude
   - **C'est ce graphe qu'il faut regarder en priorité** pour l'erreur périodique, car on cherche des périodes en minutes

### Trois courbes FFT

| Courbe | Couleur | Ce qu'elle analyse |
|--------|---------|-------------------|
| **RA FFT** | Magenta | Erreurs de suivi en ascension droite |
| **DEC FFT** | Rouge | Erreurs de suivi en déclinaison |
| **Seismic FFT** | Gris clair | Vibrations environnementales |

### Comment lire les pics — Guide pratique

Un **pic** sur la FFT signifie qu'il y a une oscillation régulière à cette fréquence/période. Plus le pic est haut, plus l'oscillation est forte.

**Ce qu'il faut chercher :**

```
  Amplitude
  │
  │     ╱╲                          ← Pic 1 : Erreur périodique (PE)
  │    ╱  ╲                            C'est LE pic le plus important
  │   ╱    ╲     ╱╲                 ← Pic 2 : Harmonique 2 (PE/2)
  │  ╱      ╲   ╱  ╲                  Normal, moitié de la période PE
  │ ╱        ╲ ╱    ╲  ╱╲          ← Pic 3 : Harmonique 3
  │╱──────────╲──────╲╱──╲─────    ← Bruit de fond (plat = OK)
  └──────────────────────────────
  480s   240s   160s   120s  Période
  (8min) (4min) (2.7m) (2min)
```

#### Tableau de diagnostic des pics

| Pic à cette période | Ce que ça signifie | Action |
|---------------------|-------------------|--------|
| **240-600 s** (4-10 min) | **Erreur périodique fondamentale** de la vis sans fin | Normal. Amplitude < 1" = excellent |
| **120-240 s** (2-4 min) | **Harmonique 2** de la PE | Normal. Indique PE non-sinusoïdale |
| **60-120 s** (1-2 min) | Harmoniques supérieures ou engrenage secondaire | Normal si faible |
| **10-30 s** | Oscillation mécanique (flexion, balance, ressort) | Vérifier mécanique si fort |
| **1-5 s** | Vibrations mécaniques (moteur, courroie) | Vérifier fixations |
| **< 1 s** | Bruit électronique ou vibrations sol | Comparer avec sismomètre |

### Qu'est-ce qu'un "bon" résultat FFT ?

- **Excellent :** Un seul pic fin à la fréquence PE, le reste plat et très bas. Ta monture guide parfaitement.
- **Bon :** Pic PE + quelques harmoniques faibles. Tout à fait normal.
- **Moyen :** Pic PE élevé (> 2") + harmoniques multiples. PEC à calibrer.
- **Problème :** Nombreux pics dispersés à des fréquences inattendues. Problème mécanique ou vibrations à investiguer.

### Pour ta 10Micron en particulier

Ta 10Micron avec ses encodeurs absolus HPS devrait montrer un graphique FFT **très propre** :
- PE mécanique de ±4" corrigée à < 1" par les encodeurs
- Pic PE dominant vers **480 secondes** (8 minutes)
- Amplitude résiduelle **< 0.5"** = excellent
- Le bruit de fond devrait être très bas

Si tu vois des pics importants ailleurs que sur le PE et ses harmoniques, ça peut indiquer du vent, une vibration du sol, ou un câble qui tire.

### Commandes de navigation

| Bouton | Action |
|--------|--------|
| **+** | Zoomer l'axe X |
| **-** | Dézoomer l'axe X |
| **<** | Déplacer la vue à gauche |
| **>** | Déplacer la vue à droite |

---

## 8. Le sismomètre

### Pourquoi un sismomètre ?

Le sismomètre détecte les **vibrations du sol** : pas de personnes, vent, trafic routier, trains, séismes. En corrélant les données sismiques avec les perturbations de tracking, on distingue les **causes environnementales** des **problèmes mécaniques**.

> Selon la documentation originale, les microséismes environnementaux produisent typiquement **moins de 0.1"** d'effet sur la monture.

### Configuration

Dans Préférences → Auxiliary → Seismometer :

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| Enable | Activer la collecte | Non |
| Serial port | Port COM du sismomètre | Auto-détecté |
| Frequency | Fréquence d'échantillonnage | 20 Hz |
| Offset | Valeur soustraite pour centrer sur zéro | 300 |
| Range | Plage verticale d'affichage | 2000 |

### Hardware supporté

- Sismomètre à bobine (slinky) avec convertisseur USB MindSets
- Tout capteur fournissant des valeurs numériques sur port série (CR+LF)

### Lecture combinée

| Si RA/DEC perturbé | Et sismomètre... | Alors la cause est... |
|--------------------|-------------------|----------------------|
| ✓ Pic | ✓ Pic simultané | **Environnementale** (vibration) |
| ✓ Pic | Plat | **Mécanique interne** |
| Plat | ✓ Pic | **Vibration trop faible** pour affecter le suivi |

---

## 9. Journalisation et export

### Enregistrement automatique

**Le logging démarre automatiquement** dès que la monture se connecte. Vous n'avez rien à faire — toutes les données sont enregistrées automatiquement pendant toute la nuit. Le bouton "Start/Stop Log" dans la barre d'outils permet de contrôler manuellement si besoin.

### Fichiers créés pendant une session

Tous les fichiers sont dans le dossier `Logs/`, nommés `MountMonitor_YYYYMMDD-HHMMSS.ext`

| Extension | Contenu | Format | Usage |
|-----------|---------|--------|-------|
| `.log` | Journal d'événements | Texte horodaté | Diagnostic après session |
| `.dat` | Données de suivi | TSV 27 colonnes | Analyse dans Excel/Python |
| `.dti` | Données temporelles | TSV | Analyse horloge |
| `.sei` | Données sismiques | TSV | Corrélation vibrations |
| `.fft` | Snapshots FFT | TSV (top 3 pics/axe) | Évolution spectrale |
| `.env` | Environnement & diagnostics | TSV | Température, pression, alignement |

### Format du fichier .dat (27 colonnes)

```
Col 1-2:   Temps monture (brut + traité)
Col 3-4:   RA (brut + traité)
Col 5:     RA StDev
Col 6-7:   DEC (brut + traité)
Col 8:     DEC StDev
Col 9-14:  Axes (positions et StDev RA/DEC)
Col 15-20: Min/Max glissants RA/DEC
Col 21-26: Min/Max glissants axes
Col 27:    Statut (TRACKING/SLEWING/PARKED/IDLE)
```

### Export de graphiques

**Menu → Reset → Dump Graphs** exporte tous les graphiques en PNG :

| Dossier | Contenu |
|---------|---------|
| `RA_graphs/` | Captures du graphe RA |
| `DEC_graphs/` | Captures du graphe DEC |
| `Time_graphs/` | Captures du graphe temporel |
| `Seismic_graphs/` | Captures du graphe sismique |
| `Axial_graphs/` | Captures du graphe axial |
| `FFT_graphs/` | Captures FFT (fréquentiel + périodique) |

Résolution : 1600 pixels de large.

### Format du fichier .fft (nouveau)

Le fichier `.fft` enregistre les **3 pics FFT dominants** toutes les 2 secondes pour chaque axe :

```
Timestamp  Axis  SampleRate  NumBins  Peak1Freq  Peak1Period  Peak1Amp  Peak2...  Peak3...
01:23:45   RA    2.00        4134     0.00208    480.00       0.3421    0.00417   240.00  0.1205  ...
01:23:45   DEC   2.00        4134     0.00104    960.00       0.0892    ...
```

Ceci permet de suivre l'**évolution spectrale** au cours de la nuit : la PE a-t-elle changé ? Des vibrations sont-elles apparues à certaines heures ?

### Format du fichier .env (diagnostics avancés)

Le fichier `.env` enregistre les **données environnementales et diagnostics** de la monture toutes les 30 secondes :

```
Timestamp  Temp Ext [°C]  Pressure [mbar]  Temp Int [°C]  Status Code  Tracking Rate  Meridian Flip [min]  Pier Side  Align Stars  Align RMS ["]  Polar Error [°]
01:00:00   -0.5           1004.5           15.2           0            60.1            180.0                East       22           12.9           0.1848
01:00:30   -0.6           1004.5           15.1           0            60.1            179.5                East       22           12.9           0.1848
```

Les données proviennent des commandes LX200 étendues (10Micron) :

| Donnée | Commande | Description |
|--------|----------|-------------|
| Température ext. | `:GRTMP#` | Sonde externe de la monture |
| Pression | `:GRPRS#` | Baromètre interne |
| Température int. | `:GTMP1#` | Capteur interne (moteurs) |
| Code statut | `:Gstat#` | Statut étendu (0=suivi, 5=parqué, 11=erreur moteur) |
| Taux de suivi | `:GT#` | Multiplicateur (60.1 = sidéral) |
| Flip méridien | `:Gmte#` | Minutes restantes avant le flip |
| Modèle d'alignement | `:getain#` | Nb étoiles, RMS, erreur polaire |

**Utilité dans l'analyse du matin :**
- **Chute de température** → affecte la mise au point et le comportement mécanique
- **Pression barométrique** → changement météo pendant la nuit
- **Température interne** → surchauffe des moteurs ?
- **Erreur polaire** → qualité de votre alignement
- **RMS du modèle** → qualité du modèle de pointage

### Modes automatiques

| Déclencheur | Réinitialiser buffers | Exporter graphes | Fermer fichiers |
|------------|----------------------|-----------------|-----------------|
| **Manuel** | ✓ | ✓ | ✓ |
| **Au slew** | ✓ (option) | ✓ (option) | ✓ (option) |
| **Au parcage** | - | ✓ (option) | ✓ (option) |

Configurable dans Préférences → Processing.

---

## 10. Relecture et analyse des logs du matin

### Analyse automatique au parcage

Quand la monture se parque en fin de nuit, MountMonitor lance **automatiquement** une analyse complète de la session. Vous retrouvez le rapport d'analyse prêt sans rien faire !

Le rapport s'affiche dans une fenêtre dédiée et couvre **tous les paramètres enregistrés**.

### Ouvrir un log manuellement

Pour relire un log d'une nuit précédente :

1. **Fichier → Ouvrir un log...** (Ctrl+O)
2. Naviguer dans le dossier `Logs/`
3. Sélectionner un fichier `.dat`
4. Les graphiques se remplissent avec les données enregistrées
5. La fenêtre FFT s'ouvre avec l'analyse spectrale
6. Le **rapport d'analyse complet** s'affiche automatiquement

### Contenu du rapport d'analyse

Le rapport couvre **12 sections** d'analyse exhaustive :

| Section | Ce qu'elle analyse |
|---------|-------------------|
| **1. Aperçu session** | Date, durée, échantillons, observatoire, monture |
| **2. Qualité globale** | Note EXCELLENT/BON/MOYEN/MAUVAIS + RMS combiné |
| **3. Ascension droite** | Mean, median, RMS, P2P, percentiles 95/99, STDEV, dérive RA |
| **4. Déclinaison** | Idem pour DEC + diagnostic d'alignement polaire |
| **5. FFT / Erreur périodique** | Top 5 pics RA + Top 3 pics DEC, détection PE automatique |
| **6. Données axiales** | Excursion axes, vitesses moyennes et max |
| **7. Synchronisation** | PC-Mount diff, drift horloge, boucle PC, boucle monture, NTP |
| **8. Statut de suivi** | % du temps en tracking vs slewing vs parqué |
| **9. Tolérance** | % d'échantillons hors tolérance à 0.5", 1", 1.5", 2", 3", 5" |
| **10. Continuité** | Détection des coupures (gaps) dans l'acquisition |
| **10b. Environnement** | Température (ext/int), pression, alignement, codes statut, flip méridien |
| **11. Journal événements** | Résumé des alertes, warnings, changements de statut |
| **12. Recommandations** | Conseils personnalisés basés sur les données et l'environnement |

### Barème de qualité

La note porte sur le **jitter** — les déviations une fois la dérive lente retirée.
C'est lui, et lui seul, qui étale les étoiles pendant une pose.

| Note | Jitter combiné | Signification |
|------|----------------|---------------|
| **EXCELLENT** | < 0.4" (0.5" non-guidé) | Étoiles parfaitement ponctuelles |
| **BON** | jusqu'à 1.0" | Résultats satisfaisants pour la plupart des focales |
| **MOYEN** | jusqu'à 2.0" | Visible sur longues poses à focales élevées |
| **MAUVAIS** | au-delà | Étoiles probablement allongées |

#### Pourquoi le jitter, et pas le RMS brut

Le RMS brut additionne trois choses qui n'ont pas les mêmes conséquences :

| | Échelle | Effet sur une pose de 180 s |
|---|---|---|
| **Jitter** | secondes | **étale directement l'étoile** |
| **Repositionnement** (dither, recentrage) | entre les poses | aucun : la pose est finie |
| **Dérive lente** | heures | quelques dixièmes de seconde d'arc, annulés par le dither suivant |

Le rapport les sépare, et la note porte sur le premier.

#### Le jitter se mesure entre les repositionnements

Un enregistrement de déviation n'est pas une ligne bruitée, c'est un **escalier** :
entre deux poses le séquenceur dithère, et la monture *reste* sur sa nouvelle marche.

```
-14.10"  -14.10"  -14.10"   <- une marche : écart-type local 0,07"
-14.40"  -14.40"  -14.40"   <- la suivante
-10.20"  -10.10"  -10.10"   <- et ainsi de suite
```

Retirer une droite ne retire pas un escalier. Sur la session du 21/09/2026, il
restait **9,1″** de prétendu jitter, alors que la monture tenait chaque marche à
**0,12″**. Le jitter est donc mesuré **à l'intérieur de chaque palier**, et les
marches sont comptées à part.

Une dérive de 5"/h ne déplace une étoile que de **0.28"** pendant une pose de 180 s.
Mais étalée sur sept heures, elle produit à elle seule un RMS de **12"** — une rampe
d'amplitude A ayant un écart-type de A/√12. Noter une monture là-dessus revient à
juger son suivi sur la durée de la nuit.

Le rapport affiche donc les deux, et note sur le premier :

```
--- 1. Tracking jitter ---
Combined jitter    : 0.179"   <-- la note est fondée là-dessus
--- 2. Commanded repositioning ---
Moves detected     : 170        Median size : 1.05"
--- 3. Slow drift ---
RA drift           : +0.73"/h   DEC drift : -2.42"/h
Star motion over a 180 s exposure : 0.13"
--- For reference ---
Raw RMS (everything mixed)   : 11.243"
After removing the drift only:  9.107"   (contient encore les paliers)
```

*(chiffres réels de la session du 21 septembre 2026 : le rapport d'origine
annonçait 86,269″ et la note MAUVAIS)*

### Le rapport de nuit, en trois langues, enregistré tout seul

À l'arrêt de l'enregistrement, le rapport complet est écrit **à côté du `.dat`**,
une fois par langue :

```
MountMonitor_20260921-220015.dat
MountMonitor_20260921-220015-rapport-fr.txt   <- écrits
MountMonitor_20260921-220015-rapport-en.txt      automatiquement
MountMonitor_20260921-220015-rapport-nl.txt
```

La fenêtre d'analyse présente les trois dans des **onglets** — English, Français,
Nederlands — et s'ouvre sur celui de la langue de l'interface. Le bouton
**Exporter TXT** enregistre l'onglet que vous avez sous les yeux, pas un autre.

Chaque rapport est écrit dans **une seule** langue. Auparavant chaque phrase était
suivie de sa traduction française, ce qui le rendait deux fois plus long à lire
sans rien apporter.

⚠️ Si l'écriture échoue (disque plein, dossier en lecture seule), la fermeture des
fichiers de session se poursuit normalement : perdre le rapport ne doit jamais
coûter les données.

#### Ce qui est exclu des statistiques

- les échantillons pris **pendant un slew** entre deux cibles ;
- les **excursions commandées** au-delà de 30" : dither, recentrage, autofocus.
  Ce sont de vrais mouvements de la monture, mais ils sont *demandés* — les
  compter reviendrait à mesurer le séquenceur, pas la monture.

Les deux sont comptés et affichés dans la section « For reference ».

### Détection automatique de l'erreur périodique

L'analyse FFT du rapport cherche automatiquement :
- Le **pic dominant** dans la plage 2-15 minutes (période typique des vis sans fin)
- Les **harmoniques** (multiples de la fréquence fondamentale)
- L'**amplitude** de la PE et sa qualification (très faible / acceptable / élevée)

### Diagnostic de dérive (alignement polaire)

Le rapport calcule la dérive en "/min et "/h pour RA et DEC :
- **RA drift** : erreur d'azimut de l'alignement polaire
- **DEC drift** : erreur d'altitude de l'alignement polaire
- Seuils : > 1"/h = légère, > 5"/h = significative → recommandation de correction

### Section environnement et diagnostics

Si le fichier `.env` existe pour la session, le rapport inclut une section dédiée :

- **Température extérieure** : tendance début → fin, plage, variation totale
  - Variation > 5°C → alerte (effet sur la mise au point)
  - Variation > 2°C → surveillance recommandée
- **Température interne** : surchauffe des moteurs ?
  - Hausse > 10°C → alerte ventilation
- **Pression barométrique** : stabilité météo
  - Variation > 5 mbar → conditions changeantes
- **Modèle d'alignement** : nombre d'étoiles, RMS, erreur polaire
  - Erreur polaire > 5' → refaire l'alignement
  - Erreur polaire > 1' → acceptable mais améliorable
- **Codes statut 10Micron** : historique des états internes
  - 0=suivi, 1=arrêté, 5=parqué, 11=erreur moteur
- **Taux de suivi** : stabilité du multiplicateur de tracking

### Export du rapport

Le bouton **"Exporter TXT"** sauvegarde le rapport complet dans un fichier texte que vous pouvez archiver ou partager.

---

## 11. Préférences détaillées

> **Note :** Chaque onglet des préférences est défilant. Si la fenêtre est trop petite pour afficher toutes les options, une barre de défilement apparaît automatiquement — les options ne se chevauchent plus.

### Onglet General

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| Observatory name | Nom apparaissant dans les logs | "My Observatory" |
| Mount name | Nom de la monture (logs) | "" |
| Protocol | Protocole de connexion | LX200 (TCP/IP) |
| Mount IP | Adresse IP (LX200 TCP) | 192.168.1.1 |
| Mount port | Port TCP | 3492 |
| Serial port | Port COM (LX200 Serial) | Auto |
| ASCOM driver | Driver ASCOM | Via sélecteur |
| Graph:Text ratio | Ratio hauteur graphes/panneau texte | 4 |
| Language | Langue (Auto/EN/FR) | Auto |

### Onglet Processing

| Paramètre | Description | Défaut | Conseils |
|-----------|-------------|--------|----------|
| Polling frequency | Interrogations par seconde | 2.0 Hz | 2 Hz = bon compromis |
| Running range | Fenêtre de calcul STDEV | 60 s | 60s pour monitoring, 300s pour trends |
| Correct for range | Décaler STDEV pour compenser le délai | Oui | Laisser activé |
| Reference mode | Point de référence des déviations | Median | "Target" si vous faites du goto |
| RA tolerance | Seuil tolérance RA | 1.5" | Ajuster à votre échelle pixel |
| DEC tolerance | Seuil tolérance DEC | 1.5" | Idem |
| Show as HA | Afficher RA en secondes de temps | Non | Utile pour les monteurs expérimentés |
| Seismic tolerance | Tolérance sismique (% de plage) | 5.0% | - |
| Log mode | Quoi journaliser | Tout | "Tracking only" = ignore slew/park |
| Delay after slew | Pause après rotation | 0 s | 5-10s recommandé pour laisser stabiliser |
| Axial mode | Mode vitesse/déplacement axial | Off | Activer pour montures 10Micron |
| Reset mode | Quand réinitialiser les buffers | Manuel | "Au slew" = auto-reset par cible |
| Dump mode | Quand exporter les graphes | Manuel | "Au slew" = sauvegarde auto |
| Close files mode | Quand fermer les fichiers log | Manuel | "Au slew" = un fichier par cible |
| History lines | Lignes dans le panneau messages | 50 | - |

### Onglet Auxiliary

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| NTP enabled | Activer comparaison NTP | Non |
| NTP server | Serveur de temps | time.nist.gov |
| NTP interval | Intervalle de polling | 30 s |
| Seismometer enabled | Activer le sismomètre | Non |
| Seismometer port | Port série | Auto-détecté |
| Seismometer freq | Fréquence | 20 Hz |
| Seismometer offset | Offset de centrage | 300 |
| Seismometer range | Plage d'affichage | 2000 |

### Onglet Miscellaneous (Vérifications monture)

| Vérification | Valeurs possibles | Défaut |
|--------------|-------------------|--------|
| Réfraction | Not updating / Not while tracking / **Continuously updating** | Activé |
| Vitesse suivi | **Sidereal** / Lunar / Solar / King | Activé |
| GPS | **Synchronising** / Not synchronising | Désactivé |
| Dual tracking | Enabled / **Disabled** | Désactivé |

---

## 11bis. Rapport de crash et détection hardware

### Rapport de crash automatique

Si MountMonitor plante, un fichier `crash_report.json` est sauvegardé automatiquement avec :
- Le traceback complet de l'erreur
- Le système d'exploitation et la version de Python
- La version de MountMonitor
- L'architecture du processeur

Au prochain lancement, une boîte de dialogue informe du crash précédent et permet de consulter les détails.

### Détection hardware

Au démarrage, MountMonitor détecte automatiquement :
- **CPU** : nom, nombre de cœurs physiques/logiques
- **RAM** : mémoire totale disponible
- **GPU** : carte graphique (Windows uniquement)
- **Type de stockage** : SSD ou HDD

Ces informations sont utilisées pour adapter les performances :
- Taille des buffers circulaires (10k à 100k échantillons selon la RAM)
- Nombre de workers recommandé (basé sur les cœurs physiques)

---

## 12. Diagnostics et résolution de problèmes

### "La connexion ASCOM échoue"

1. Vérifier que la monture est allumée et connectée au PC
2. Vérifier que l'ASCOM Platform est installé
3. Vérifier que le driver ASCOM de votre monture est installé
4. Tester la connexion avec un autre logiciel ASCOM (N.I.N.A., POTH, Stellarium)
5. Le sélecteur ASCOM peut apparaître en arrière-plan — utilisez Alt+Tab

### "Les valeurs RA/DEC sont aberrantes"

- Vérifier que la monture est en mode haute précision
- Vérifier que le mode de suivi est correct (sidéral pour les étoiles)
- Réinitialiser les buffers (menu Reset → Reset Buffers)

### "Le STDEV augmente continuellement"

- **Normal en début de session** : la fenêtre glissante (60s) doit se remplir
- Si ça continue après 2-3 minutes : vérifier alignement polaire, balance, conditions météo

### "L'erreur périodique est très grande"

- Montures avec PEC : vérifier que le PEC est activé et qu'un training a été fait
- PE > 5-10" sans PEC = normal pour la plupart des montures
- PE < 1" = excellent (monture haut de gamme avec PEC ou encodeurs)

### "La DEC dérive constamment"

- C'est un défaut d'alignement polaire — la correction est mécanique, pas logicielle
- Utiliser le taux de dérive pour quantifier et corriger

### "MountMonitor freeze / ne répond plus"

- Le problème a été corrigé (cascades de signaux pyqtgraph)
- Si ça arrive encore : relancer le programme

### "L'application ne se lance pas" ou "Erreur d'import"

1. **Utilisez le lanceur** (`launch.bat` ou `launch.sh`) — il gère tout automatiquement
2. Si le problème persiste, utilisez le mode réparation :
   ```bash
   launch.bat --repair     # Windows
   ./launch.sh --repair    # Linux/macOS
   ```
3. Ceci supprime l'environnement virtuel et réinstalle toutes les dépendances de zéro

### "Le lanceur dit que Python n'est pas trouvé"

- **Windows** : acceptez l'installation automatique de Python proposée par le lanceur
- **Linux** : `sudo apt install python3 python3-venv python3-pip`
- **macOS** : `brew install python@3.12`
- Après installation, relancez le lanceur

---

## 13. Annexes techniques

### Formules de calcul

**Déviation RA en arcsec :**
```
déviation = (RA_actuelle - RA_référence) × 15 × 3600
```
*(avec gestion du wrap-around à 24h)*

**Déviation DEC en arcsec :**
```
déviation = (DEC_actuelle - DEC_référence) × 3600
```

**Échelle pixel :**
```
échelle (") = 206.265 × taille_pixel_µm / focale_mm
```

**STDEV glissant :**
Algorithme O(n) à deux pointeurs avec correction de Bessel :
```
variance = (Σx²/n - (Σx/n)²) × n/(n-1)
STDEV = √variance
```

**Vitesse axiale :**
```
vitesse = (position_t2 - position_t1) / (t2 - t1)  [arcsec/s]
```

### Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| Ctrl+K | Connecter |
| Ctrl+D | Déconnecter |
| Ctrl+O | Ouvrir un log (relecture + analyse) |
| Ctrl+, | Préférences |
| Ctrl+F | Fenêtre FFT |
| Ctrl+Q | Quitter |

### Compatibilité des montures

| Monture | Protocole recommandé | Fonctions spécifiques |
|---------|---------------------|----------------------|
| 10Micron GM1000/2000/3000/4000 | ASCOM ou LX200 TCP | Toutes (axes, GPS, réfraction, dual) |
| Meade LX200/LX600 | LX200 TCP ou Serial | Commandes LX200 de base |
| Celestron (ASCOM) | ASCOM | Propriétés standard |
| iOptron (ASCOM) | ASCOM | Propriétés standard |
| Sky-Watcher EQ6/EQ8 (EQMOD) | ASCOM | Propriétés standard |
| Losmandy Gemini | LX200 Serial ou ASCOM | Commandes LX200 |
| Takahashi Temma | ASCOM | Propriétés standard |
| ZWO AM3/AM5 | ASCOM | Propriétés standard |

### Ports réseau par défaut

| Monture | Port TCP |
|---------|----------|
| 10Micron | 3492 |
| Meade LX200GPS | 4030 |
| Celestron WiFi | 2000 |

### Benchmarks 10Micron (non guidé)

- Spécification : < 0.6" RMS tracking
- Poses non guidées de 20-30 minutes possibles avec bon modèle de ciel
- PE mécanique ±4", réduit à ±0.25" par les encodeurs absolus HPS
- Avec autoguidage actif : 0.05" RMS (limité par le seeing)

---

### Sources

- [MountMonitor - Nicolas de Hilster](https://dehilster.info/astronomy/mountmonitor.php)
- [Documentation MountMonitor v3.37](https://dehilster.info/docs/MountMonitor-Help/about.htm)
- [10Micron HPS Key Features](https://alpineastro.com/blogs/blog/10micron-hps-mounts-key-features-and-benefits)
- [Equatorial Mount Tracking Errors](https://www.pk3.org/Astro/astrophoto_mount_errors.htm)
- [Mount Periodic Error - Astrojolo](https://astrojolo.com/gears/mount-periodic-error/)
- [How Much Guiding Error Is Too Much?](https://www.innovationsforesight.com/education/how-much-guiding-error-is-too-much/)

---

*MountMonitor — Version Python basée sur le logiciel original de Nicolás de Hilster*
*Guide rédigé pour la version 1.3.0 — Dernière mise à jour : mars 2026*
*Nouveautés v1.3.0 : logging FFT automatique, relecture de logs, analyse automatique de nuit, analyse au parcage*
