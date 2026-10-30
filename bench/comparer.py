"""Banc d'essai : détoure les images de bench/images/reel et fabrique une planche de contrôle.

Chaque ligne : original | sur fond sombre | sur fond bleu | alpha.
Usage : python bench/comparer.py [methode ...]   (methodes : papier, birefnet, toonout, hybride)
"""

from __future__ import annotations

import glob
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE.parent))

VIGNETTE = 520


def composer(rgba: Image.Image, fond: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", rgba.size, fond)
    base.paste(rgba, mask=rgba.getchannel("A"))
    return base


def vignette(im: Image.Image) -> Image.Image:
    im = im.copy()
    im.thumbnail((VIGNETTE, VIGNETTE))
    cadre = Image.new("RGB", (VIGNETTE, VIGNETTE), (128, 128, 128))
    cadre.paste(im, ((VIGNETTE - im.width) // 2, (VIGNETTE - im.height) // 2))
    return cadre


def methode(nom: str):
    if nom == "papier":
        from moteur.papier import detourer

        return detourer
    import modeles_ia

    return getattr(modeles_ia, nom)


def main(noms: list[str]) -> None:
    fichiers = sorted(glob.glob(str(RACINE / "images" / "reel" / "*.jpg")))
    for nom in noms:
        f_detour = methode(nom)
        dossier = RACINE / "sorties" / nom
        dossier.mkdir(parents=True, exist_ok=True)
        lignes = []
        for f in fichiers:
            src = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
            t = time.perf_counter()
            out = f_detour(src.copy())
            duree = time.perf_counter() - t
            print(f"{nom:9s} {Path(f).name} {src.size} {duree:6.1f} s", flush=True)
            out.save(dossier / (Path(f).stem + ".png"))
            lignes.append(
                [
                    vignette(src),
                    vignette(composer(out, (34, 34, 38))),
                    vignette(composer(out, (40, 90, 200))),
                    vignette(out.getchannel("A").convert("RGB")),
                ]
            )
        planche = Image.new("RGB", (VIGNETTE * 4, VIGNETTE * len(lignes)))
        for i, ligne in enumerate(lignes):
            for j, v in enumerate(ligne):
                planche.paste(v, (j * VIGNETTE, i * VIGNETTE))
        planche.save(RACINE / "sorties" / f"planche_{nom}.jpg", quality=88)


if __name__ == "__main__":
    main(sys.argv[1:] or ["papier"])
