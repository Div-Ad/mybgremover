# Détourage d'aquarelles

Retire le papier (Canson, crème, teinté) d'aquarelles à l'encre scannées ou photographiées,
en local, sans envoyer d'image où que ce soit. Sortie PNG, WebP sans perte ou AVIF, profil
couleur et DPI conservés (DPI : PNG et AVIF).

Par défaut, l'image est réduite *avant* le détourage à 300 dpi, petit côté de 21 cm (largeur
d'un portrait, hauteur d'un paysage) : un scan A4 à 1200 dpi se traite deux fois plus vite.
Réglable en cm ou en px ; case décochée = résolution d'origine. Jamais d'agrandissement.

On dépose les images (chaque carte annonce sa taille finale), puis « Lancer ». Sous Chrome ou
Edge, « Enregistrer dans » écrit chaque résultat dans un dossier dès qu'il est prêt.

## Lancer

Double-clic sur `lancer.bat` : il installe l'environnement au premier lancement, puis ouvre
http://127.0.0.1:8765. Au tout premier démarrage, le modèle BiRefNet (≈ 1 Go) est téléchargé
dans `modeles/`. Ensuite, tout fonctionne hors ligne.

Compter environ 15 à 20 s par image sur le processeur (i7-7700), quelle que soit sa taille.

## Comment ça marche

Hybride, parce qu'aucune des deux approches ne suffit seule (cf. `bench/`) :

1. **Papier** (`moteur/papier.py`) : on estime la couleur du papier en chaque point (teinte +
   éclairage inégal), on la neutralise, puis « couleur vers alpha » contre le blanc. Contours
   d'encre parfaitement lissés, lavis dégradés, aucun halo de papier. Hors de la feuille (bord
   de scanner, table) et poussières isolées : supprimés.
2. **IA** (`moteur/ia.py`, BiRefNet ONNX, licence MIT) : dit *où* est le sujet, pour que les
   blancs du sujet (pétales, reflets, réserves) restent opaques au lieu de devenir transparents.

Le résultat posé sur du blanc redonne exactement l'aquarelle d'origine, papier blanchi.

## Développement

```
.venv\Scripts\python -m pytest -q                     # tests
.venv\Scripts\python bench\comparer.py papier hybride  # banc d'essai (bench/images/reel)
```

Pour le banc, mettre `bench` dans `PYTHONPATH` quand on teste `birefnet` ou `hybride`.
