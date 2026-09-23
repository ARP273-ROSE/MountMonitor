"""Help text, in the three languages.

Kept out of main_window because it is prose, not behaviour, and because
adding a language should not mean pasting a hundred lines into a file that
already holds two thousand. The English/French pair used to live there and
still described version 1.6; every section below has been rewritten against
what the application actually does now.

Each entry is a list of (heading, body) pairs. The body is Qt rich text.
"""

AIDE = {
    'en': [
        ("Quick start", """
<ol>
<li>Set the mount connection in <b>Preferences</b>: IP and port, or serial port.</li>
<li>While you are there, set your <b>site</b> — latitude, longitude (positive
east) and elevation. Most mounts never report one, and without it the night
ephemeris cannot be computed.</li>
<li>Click <b>Connect</b>, then the record button.</li>
</ol>"""),

        ("Arming the logger", """
<p><i>Start recording when the mount starts tracking</i> is on by default, so the
record button <b>arms</b> the logger instead of starting it: nothing is written
until the mount actually tracks. A mount connected at noon for a night starting
at seven no longer records seven hours of nothing. A second click disarms.</p>
<p>A night is treated as one unit. If the mount parks at two in the morning and
resumes at three, recording suspends and resumes <b>in the same file</b>; only
sunrise closes the session and writes the report. Events are still logged while
suspended — that is what documents the gap.</p>"""),

        ("What the numbers mean", """
<p>This is the part worth reading.</p>
<p><b>Jitter</b> is the spread the mount shows while it holds a position. It is
the only figure that blurs an exposure, and the rating is based on it.</p>
<p><b>Commanded moves</b> — dither, re-centering — are movements between
exposures. The mount is moved and stays there. They do not blur a frame, and
they are reported separately, grouped and classified. A move whose aftermath
stays several times the usual spread is flagged as <i>unsettled</i>: that is
the one worth looking at.</p>
<p><b>Slow drift</b> is quoted per hour and per exposure. On an unguided mount
it is cancelled by each dither.</p>
<p>A raw RMS over a whole night describes none of these. A deviation record is
a <b>staircase</b>, not a noisy line, and removing a linear drift does not
remove a staircase — one real session read 86.3&Prime; that way while the mount
was holding each position to 0.18&Prime;.</p>"""),

        ("Night ephemeris", """
<p>Computed from the site the mount reports, or from Preferences. The report
gives sunset, nautical twilight, astronomical night, sunrise — and how much of
the dark night the session actually covered. A session started an hour late
loses an hour that cannot be recovered, and that reads better next to the
tracking figures than after the fact.</p>"""),

        ("Graphs", """
<p>Right ascension and declination deviations in real time, with the running
standard deviation and the tolerance limits. Zoom with the View menu or the
mouse wheel; the running window is set in Preferences (60 to 900 s).</p>"""),

        ("FFT analysis", """
<p>Looks for periodic error in the 2&ndash;15 minute range, the band where a
worm period shows. The transform runs on the detrended deviations: a linear
drift is not periodic, but over a finite window it produces a large
low-frequency component that would hide what is being looked for.</p>"""),

        ("Replay", """
<p><b>File &rarr; Open log</b> reads a finished session and rebuilds the whole
analysis. The site and time offset travel in the file header, so twilights are
still available long after the mount is disconnected.</p>
<p>The night report is written automatically at the end of a session, next to
the <code>.dat</code>, one file per language.</p>"""),

        ("Language", """
<p>The <b>Language</b> menu holds English, French and Dutch, plus automatic
detection from the system. Each entry is written in its own language. A change
takes effect at the next start — the application offers to restart, unless a
recording is running.</p>"""),

        ("Keyboard", """
<table cellpadding="3">
<tr><td><b>F1</b></td><td>this help</td></tr>
<tr><td><b>Ctrl+,</b></td><td>preferences</td></tr>
<tr><td><b>Ctrl+O</b></td><td>open a log</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>quit</td></tr>
</table>"""),

        ("Protocols and files", """
<p>LX200 over TCP/IP or serial (9600 8N1), and ASCOM on Windows. The raw axis
positions exposed by 10Micron firmware are read when available.</p>
<p>A session writes <code>.dat</code> (samples), <code>.dti</code> (timing),
<code>.fft</code>, <code>.env</code> (environment) and <code>.log</code>
(events), plus the night report.</p>"""),

        ("Updates and problem reports", """
<p>Updates are checked silently at startup. If the application crashes, freezes
or fails to start, it can report it by itself — you are asked once whether you
allow this, and nothing else is ever sent: not your tracking data, not your
file names, not your user name. All paths are anonymised.</p>"""),
    ],

    'fr': [
        ("Démarrage rapide", """
<ol>
<li>Réglez la connexion à la monture dans les <b>Préférences</b> : IP et port,
ou port série.</li>
<li>Profitez-en pour renseigner votre <b>site</b> — latitude, longitude
(positive vers l'est) et altitude. La plupart des montures n'en transmettent
aucun, et sans lui les éphémérides ne peuvent pas être calculées.</li>
<li>Cliquez sur <b>Connecter</b>, puis sur le bouton d'enregistrement.</li>
</ol>"""),

        ("Armer l'enregistreur", """
<p>L'option <i>Démarrer l'enregistrement quand la monture se met à suivre</i>
est active par défaut : le bouton <b>arme</b> l'enregistreur au lieu de le démarrer : rien
n'est écrit tant que la monture ne suit pas réellement. Une monture connectée à
midi pour une nuit qui commence à 19 h n'enregistre plus sept heures de rien.
Un second clic désarme.</p>
<p>Une nuit est traitée comme un tout. Si la monture se parque à 2 h et repart
à 3 h, l'enregistrement se suspend puis reprend <b>dans le même fichier</b> ;
seul le lever du Soleil termine la session et écrit le rapport. Les événements
continuent d'être journalisés pendant la suspension : c'est ce qui documente le
trou.</p>"""),

        ("Ce que les chiffres veulent dire", """
<p>C'est la partie qui mérite d'être lue.</p>
<p>Le <b>jitter</b> est la dispersion que montre la monture pendant qu'elle
tient sa position. C'est le seul chiffre qui étale une pose, et la note est
fondée sur lui.</p>
<p>Les <b>mouvements commandés</b> — dither, recentrage — sont des déplacements
entre les poses. La monture est déplacée et y reste. Ils n'étalent aucune pose
et sont rapportés à part, regroupés et classés. Un mouvement dont la suite
reste plusieurs fois la dispersion habituelle est signalé comme <i>non
stabilisé</i> : c'est celui-là qui mérite un coup d'œil.</p>
<p>La <b>dérive lente</b> est donnée par heure et par pose. Sur une monture non
guidée, chaque dither l'annule.</p>
<p>Un RMS brut sur toute une nuit ne décrit rien de tout cela. Un enregistrement
de déviation est un <b>escalier</b>, pas une ligne bruitée, et retirer une
dérive linéaire ne retire pas un escalier — une session réelle affichait ainsi
86,3&Prime; alors que la monture tenait chaque position à 0,18&Prime;.</p>"""),

        ("Éphémérides de la nuit", """
<p>Calculées depuis le site que transmet la monture, ou depuis les Préférences.
Le rapport donne le coucher, le crépuscule nautique, la nuit noire, le lever —
et la part de nuit noire que la session a réellement couverte. Une nuit
commencée une heure trop tard perd une heure qui ne se rattrape pas, et cela se
lit mieux à côté des chiffres de suivi qu'après coup.</p>"""),

        ("Graphiques", """
<p>Déviations en ascension droite et en déclinaison en temps réel, avec
l'écart-type glissant et les limites de tolérance. Zoom par le menu Affichage
ou la molette ; la fenêtre glissante se règle dans les Préférences (60 à
900 s).</p>"""),

        ("Analyse FFT", """
<p>Cherche une erreur périodique entre 2 et 15 minutes, la plage où se voit une
période de vis sans fin. La transformée porte sur les déviations détrendées :
une dérive linéaire n'est pas périodique, mais sur une fenêtre finie elle
produit une composante basse fréquence qui masquerait ce que l'on cherche.</p>"""),

        ("Relecture", """
<p><b>Fichier &rarr; Ouvrir un log</b> relit une session terminée et reconstruit
toute l'analyse. Le site et le décalage horaire voyagent dans l'en-tête du
fichier : les crépuscules restent disponibles longtemps après que la monture a
été débranchée.</p>
<p>Le rapport de nuit est écrit automatiquement en fin de session, à côté du
<code>.dat</code>, un fichier par langue.</p>"""),

        ("Langue", """
<p>Le menu <b>Langue</b> propose le français, l'anglais et le néerlandais, plus
la détection automatique depuis le système. Chaque entrée est écrite dans sa
propre langue. Un changement prend effet au prochain démarrage — l'application
propose de redémarrer, sauf si un enregistrement est en cours.</p>"""),

        ("Clavier", """
<table cellpadding="3">
<tr><td><b>F1</b></td><td>cette aide</td></tr>
<tr><td><b>Ctrl+,</b></td><td>préférences</td></tr>
<tr><td><b>Ctrl+O</b></td><td>ouvrir un log</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>quitter</td></tr>
</table>"""),

        ("Protocoles et fichiers", """
<p>LX200 en TCP/IP ou série (9600 8N1), et ASCOM sous Windows. Les positions
brutes des axes exposées par le firmware 10Micron sont lues quand elles sont
disponibles.</p>
<p>Une session écrit <code>.dat</code> (échantillons), <code>.dti</code>
(temps), <code>.fft</code>, <code>.env</code> (environnement) et
<code>.log</code> (événements), plus le rapport de nuit.</p>"""),

        ("Mises à jour et signalement", """
<p>Les mises à jour sont vérifiées discrètement au démarrage. Si l'application
plante, se fige ou refuse de démarrer, elle peut le signaler toute seule — la
question vous est posée une fois, et rien d'autre n'est envoyé : ni vos données
de suivi, ni vos noms de fichiers, ni votre nom d'utilisateur. Tous les chemins
sont anonymisés.</p>"""),
    ],

    'nl': [
        ("Snel aan de slag", """
<ol>
<li>Stel de verbinding met de montering in bij <b>Voorkeuren</b>: IP en poort,
of seriële poort.</li>
<li>Vul meteen uw <b>locatie</b> in — breedtegraad, lengtegraad (positief naar
het oosten) en hoogte. De meeste monteringen geven er geen door, en zonder
locatie kunnen de efemeriden niet worden berekend.</li>
<li>Klik op <b>Verbinden</b> en daarna op de opnameknop.</li>
</ol>"""),

        ("De logger gereedzetten", """
<p>De optie <i>Registratie starten zodra de montering begint te volgen</i> staat
standaard aan: de opnameknop zet de logger <b>gereed</b> in plaats van hem te starten: er
wordt niets geschreven zolang de montering niet werkelijk volgt. Een montering
die om twaalf uur 's middags wordt aangesloten voor een nacht die om zeven uur
begint, registreert niet langer zeven uur niets. Een tweede klik schakelt
uit.</p>
<p>Een nacht geldt als één geheel. Parkeert de montering om twee uur en gaat ze
om drie uur verder, dan wordt de registratie onderbroken en hervat <b>in
hetzelfde bestand</b>; alleen zonsopkomst sluit de sessie af en schrijft het
rapport. Gebeurtenissen worden tijdens de onderbreking nog steeds
vastgelegd — dat is wat het gat documenteert.</p>"""),

        ("Wat de cijfers betekenen", """
<p>Dit is het deel dat de moeite van het lezen waard is.</p>
<p><b>Jitter</b> is de spreiding die de montering vertoont terwijl zij haar
positie vasthoudt. Het is het enige cijfer dat een opname doet uitlopen, en het
oordeel berust erop.</p>
<p><b>Aangestuurde bewegingen</b> — dither, hercentrering — zijn verplaatsingen
tussen opnames. De montering wordt verplaatst en blijft daar. Zij doen geen
enkele opname uitlopen en worden apart gerapporteerd, gegroepeerd en
ingedeeld. Een beweging waarvan de nasleep meerdere malen de gebruikelijke
spreiding blijft, wordt gemeld als <i>niet gestabiliseerd</i>: juist die
verdient aandacht.</p>
<p>De <b>langzame drift</b> wordt per uur en per opname gegeven. Bij een
ongegidste montering heft elke dither haar op.</p>
<p>Een ruwe RMS over een hele nacht beschrijft niets daarvan. Een
afwijkingsregistratie is een <b>trap</b>, geen ruizige lijn, en het verwijderen
van een lineaire drift verwijdert geen trap — één werkelijke sessie las zo
86,3&Prime; terwijl de montering elke positie op 0,18&Prime; hield.</p>"""),

        ("Efemeriden van de nacht", """
<p>Berekend op basis van de locatie die de montering doorgeeft, of uit de
Voorkeuren. Het rapport geeft zonsondergang, nautische schemering,
astronomische nacht en zonsopkomst — en hoeveel van de donkere nacht de sessie
werkelijk heeft bestreken. Een nacht die een uur te laat begint, verliest een
uur dat niet meer in te halen is, en dat leest beter naast de volgcijfers dan
achteraf.</p>"""),

        ("Grafieken", """
<p>Afwijkingen in rechte klimming en declinatie in real time, met de lopende
standaardafwijking en de tolerantiegrenzen. Zoomen via het menu Beeld of met
het muiswiel; het lopende venster stelt u in bij Voorkeuren (60 tot 900 s).</p>"""),

        ("FFT-analyse", """
<p>Zoekt naar periodieke fouten tussen 2 en 15 minuten, het bereik waarin een
wormperiode zichtbaar wordt. De transformatie werkt op de ontdrifte
afwijkingen: een lineaire drift is niet periodiek, maar over een eindig venster
levert zij een grote laagfrequente component op die zou verbergen waarnaar
gezocht wordt.</p>"""),

        ("Terugkijken", """
<p><b>Bestand &rarr; Logbestand openen</b> leest een afgeronde sessie en bouwt
de volledige analyse opnieuw op. De locatie en de tijdzone reizen mee in de
bestandskop, zodat de schemeringen nog lang beschikbaar blijven nadat de
montering is losgekoppeld.</p>
<p>Het nachtrapport wordt aan het einde van een sessie automatisch geschreven,
naast het <code>.dat</code>-bestand, één bestand per taal.</p>"""),

        ("Taal", """
<p>Het menu <b>Taal</b> biedt Nederlands, Engels en Frans, plus automatische
herkenning vanuit het systeem. Elke regel staat in haar eigen taal geschreven.
Een wijziging gaat in bij de volgende start — de toepassing biedt aan opnieuw
te starten, tenzij er een registratie loopt.</p>"""),

        ("Toetsenbord", """
<table cellpadding="3">
<tr><td><b>F1</b></td><td>deze hulp</td></tr>
<tr><td><b>Ctrl+,</b></td><td>voorkeuren</td></tr>
<tr><td><b>Ctrl+O</b></td><td>logbestand openen</td></tr>
<tr><td><b>Ctrl+Q</b></td><td>afsluiten</td></tr>
</table>"""),

        ("Protocollen en bestanden", """
<p>LX200 via TCP/IP of serieel (9600 8N1), en ASCOM onder Windows. De ruwe
asposities die de 10Micron-firmware beschikbaar stelt, worden gelezen waar ze
voorhanden zijn.</p>
<p>Een sessie schrijft <code>.dat</code> (meetpunten), <code>.dti</code>
(tijd), <code>.fft</code>, <code>.env</code> (omgeving) en <code>.log</code>
(gebeurtenissen), plus het nachtrapport.</p>"""),

        ("Updates en probleemmeldingen", """
<p>Updates worden bij het opstarten stil gecontroleerd. Als de toepassing
vastloopt, blokkeert of niet wil starten, kan zij dat zelf melden — de vraag
wordt u eenmaal gesteld, en er wordt niets anders verstuurd: niet uw
volggegevens, niet uw bestandsnamen, niet uw gebruikersnaam. Alle paden worden
geanonimiseerd.</p>"""),
    ],
}

TITRE = {'en': "Help", 'fr': "Aide", 'nl': "Hulp"}


def aide_html(langue: str, version: str) -> str:
    """Full help document for one language, as Qt rich text."""
    sections = AIDE.get(langue) or AIDE['en']
    morceaux = [f"<h2>MountMonitor v{version}</h2>"]
    for titre, corps in sections:
        morceaux.append(f"<h3>{titre}</h3>{corps}")
    return "\n".join(morceaux)
