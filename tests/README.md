# Tests

```
pip install pytest
python -m pytest tests/ -q
```

`test_analyse_suivi.py` rejoue une session synthétique dont **la vérité terrain est
connue** — deux cibles séparées de 14,7°, un jitter de 0,26″ RMS, une dérive de
−5,65″/h, une erreur périodique de 1,5″ à 8 minutes — et vérifie que le rapport
les retrouve.

Un dernier test rejoue la **session réelle** qui a déclenché tout ceci. Le fichier
`Logs/MountMonitor_20260921-220015.dat` n'est pas versionné (`Logs/` est dans
`.gitignore`, et il pèse 9,5 Mo) : le test est *skippé* s'il est absent. Pour le
jouer, poser le fichier à cet endroit.

Ces tests existent parce qu'une session réelle de 8 h 30 était notée **MAUVAIS**
avec un RMS combiné de 86″, alors que le jitter valait **0,179″**. Cinq causes :

1. la segmentation cherchait un **saut** entre échantillons consécutifs ; un slew
   étant un mouvement continu, aucun saut n'était jamais assez grand, et deux
   cibles tombaient dans un seul segment dont la médiane se plaçait entre elles ;
2. les échantillons pris **pendant** un slew entraient dans les statistiques ;
3. le RMS mélangeait la **dérive lente** et le **jitter**, alors qu'une dérive de
   5″/h ne déplace une étoile que de 0,28″ pendant une pose de 180 s et que chaque
   dither l'annule ;
4. la **FFT** travaillait sur les déviations brutes : la dérive y produisait un
   faux « pic dominant » qui masquait la véritable erreur périodique ;
5. 🔴 **le jitter était mesuré en retirant une droite, alors que le signal est un
   escalier.** Entre deux poses le séquenceur dithère et la monture *reste* sur sa
   nouvelle marche. Retirer une droite ne retire pas un escalier : il restait 9,1″
   de « jitter » sur la session réelle, alors que la monture tenait chaque marche à
   **0,12″**. Le jitter se mesure désormais **entre les repositionnements**.
