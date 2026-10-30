"""Méthodes à base d'IA pour le banc d'essai."""

from __future__ import annotations

import numpy as np
from PIL import Image

from moteur.ia import masque_sujet
from moteur.papier import detourer


def birefnet(im: Image.Image) -> Image.Image:
    """Découpe « à la remove.bg » : couleurs d'origine, alpha = masque du modèle."""
    m = masque_sujet(im)
    alpha = Image.fromarray((m * 255).astype(np.uint8)).resize(im.size, Image.BILINEAR)
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out


def hybride(im: Image.Image) -> Image.Image:
    """Le modèle dit où est le sujet, le traitement du papier fait les bords et les couleurs."""
    return detourer(im, sujet=masque_sujet(im))
