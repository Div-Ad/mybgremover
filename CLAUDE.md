# Détourage d'aquarelles — notes pour Claude Code

App locale (Windows, processeur seul : la GTX 750 Ti n'est pas utilisable) qui retire le papier
d'aquarelles à l'encre de Chine. Interface et code en français. « 0 froufrou » : glisser-déposer,
choix du format (PNG / WebP sans perte / AVIF), aperçu, téléchargement. Pas de fonctionnalité
non demandée.

- `moteur/papier.py` : traitement du papier (le cœur) ; `moteur/ia.py` : masque BiRefNet ONNX.
- `app/serveur.py` (FastAPI) + `app/statique/index.html` (JS natif, sans build).
- `bench/comparer.py` : planches de contrôle sur `bench/images/reel` (images non versionnées).
- Tests : `.venv\Scripts\python -m pytest -q`. Lancer : `lancer.bat` (port 8765).

Toute modification du moteur se vérifie sur le banc (fonds sombre et bleu) : les défauts typiques
sont le papier resté opaque, les blancs du sujet devenus transparents et les liserés clairs.
Étape suivante prévue : hébergement (moteur sur Modal, page sur Vercel).
