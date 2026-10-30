"""Dessine lanceur/icone.ico et les icônes de la PWA : une goutte d'aquarelle cernée d'encre, à moitié sur le papier,
à moitié sur le damier de la transparence."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

T = 1024
ICI = Path(__file__).resolve().parent


def goutte(t: int) -> Image.Image:
    """Masque d'une goutte (pointe en haut)."""
    m = Image.new("L", (t, t), 0)
    d = ImageDraw.Draw(m)
    cx, cy, r = t * 0.5, t * 0.6, t * 0.25
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    d.polygon([(cx, t * 0.17), (cx - r * 0.93, cy - r * 0.38), (cx + r * 0.93, cy - r * 0.38)], fill=255)
    return m.filter(ImageFilter.GaussianBlur(t * 0.004))


def dessiner() -> Image.Image:
    tuile = Image.new("L", (T, T), 0)
    ImageDraw.Draw(tuile).rounded_rectangle((T * 0.04, T * 0.04, T * 0.96, T * 0.96), T * 0.2, fill=255)

    # fond : papier crème en haut à gauche, damier en bas à droite (coupe en diagonale)
    y, x = np.mgrid[0:T, 0:T]
    case = T // 8
    damier = np.where(((x // case) + (y // case)) % 2, 232, 255)
    papier = np.array([244, 236, 214])
    fond = np.where((x + y < T)[..., None], papier, damier[..., None].repeat(3, 2))
    img = Image.fromarray(fond.astype(np.uint8))

    # lavis outremer dégradé, plus dense en bas
    m = goutte(T)
    lavis = np.zeros((T, T, 3))
    k = np.clip((y - T * 0.17) / (T * 0.7), 0, 1)[..., None]
    lavis[:] = np.array([96, 160, 236]) * (1 - k) + np.array([30, 66, 168]) * k
    img.paste(Image.fromarray(lavis.astype(np.uint8)), mask=m)

    # reflet blanc (la réserve), puis contour à l'encre de Chine
    reflet = Image.new("L", (T, T), 0)
    ImageDraw.Draw(reflet).ellipse((T * 0.36, T * 0.5, T * 0.46, T * 0.66), fill=200)
    img.paste((255, 255, 255), mask=ImageChops.multiply(reflet.filter(ImageFilter.GaussianBlur(T * 0.012)), m))
    contour = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(41)), m.filter(ImageFilter.MinFilter(9)))
    img.paste((22, 20, 24), mask=contour)

    img.putalpha(tuile)
    return img


if __name__ == "__main__":
    grand = dessiner()
    tailles = [256, 128, 64, 48, 32, 24, 16]
    grand.resize((256, 256), Image.Resampling.LANCZOS).save(
        ICI / "icone.ico", sizes=[(s, s) for s in tailles]
    )
    grand.resize((256, 256), Image.Resampling.LANCZOS).save(ICI / "icone.png")
    for s in (192, 512):  # icônes de l'app installée (PWA)
        grand.resize((s, s), Image.Resampling.LANCZOS).save(ICI.parent / "app" / "statique" / f"icone-{s}.png")
    print("icone.ico :", tailles, "+ app/statique/icone-192.png, icone-512.png")
