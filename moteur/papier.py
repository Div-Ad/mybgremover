"""Retire le papier d'une aquarelle scannée ou photographiée.

Principe (pas de réseau de neurones) :
1. on estime la couleur du papier en chaque point (teinte du Canson + éclairage inégal) ;
2. on divise l'image par ce champ : le papier devient blanc pur ;
3. « couleur vers alpha » contre le blanc : chaque pixel devient le pigment qui, posé sur du
   blanc, redonne exactement le pixel d'origine (contours d'encre parfaitement lissés, lavis
   dégradés, aucun liseré du papier) ;
4. l'intérieur du sujet (zones délimitées par l'encre ou la peinture) est rendu opaque pour que
   les réserves blanches restent blanches sur un fond foncé ;
5. tout ce qui est hors de la feuille (bord du scanner, table) et les poussières isolées
   disparaissent.

Les analyses se font sur une version réduite (rapide), l'alpha final est calculé à pleine
résolution.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage
from scipy.spatial import ConvexHull, QhullError

TAILLE_ANALYSE = 1024


@dataclass
class Reglages:
    # seuil (alpha « couleur vers alpha ») à partir duquel un pixel est de la peinture franche
    seuil_peinture: float = 0.18
    # seuil bas : tout ce qui est marqué (crayon, lavis pâle) et qu'on garde s'il n'est pas isolé
    seuil_trace: float = 0.05
    # surface maximale d'une réserve blanche entourée de peinture, gardée opaque
    reserve_max: float = 0.01
    # couverture à partir de laquelle un pixel est entièrement opaque (encre, gouache)
    plafond: float = 0.9
    # probabilité (IA) à partir de laquelle un pixel appartient au sujet
    seuil_ia: float = 0.5
    # surface minimale d'une tache conservée, en fraction de l'image (poussières en dessous)
    surface_min: float = 2e-5
    # intérieur du sujet opaque (sinon : transparence aquarelle intégrale)
    interieur_opaque: bool = True


def _reduire(rgb: np.ndarray, cote: int) -> tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    echelle = min(1.0, cote / max(h, w))
    if echelle == 1.0:
        return rgb, 1.0
    im = Image.fromarray((rgb * 255).astype(np.uint8))
    im = im.resize((max(1, round(w * echelle)), max(1, round(h * echelle))), Image.BOX)
    return np.asarray(im, dtype=np.float32) / 255.0, echelle


def _agrandir(canal: np.ndarray, taille: tuple[int, int]) -> np.ndarray:
    """Redimensionne un canal flottant (h, w) vers taille=(w, h), en bilinéaire."""
    return np.asarray(Image.fromarray(canal.astype(np.float32), "F").resize(taille, Image.BILINEAR))


def _flou_normalise(valeurs: np.ndarray, poids: np.ndarray, sigma: float) -> np.ndarray:
    """Moyenne locale pondérée : bouche les zones sans papier avec le papier voisin."""
    p = ndimage.gaussian_filter(poids, sigma, mode="nearest")
    out = np.empty_like(valeurs)
    for c in range(valeurs.shape[2]):
        v = ndimage.gaussian_filter(valeurs[..., c] * poids, sigma, mode="nearest")
        out[..., c] = v / np.maximum(p, 1e-6)
    return out


def estimer_papier(petit: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (champ de couleur du papier, masque des pixels de papier) sur l'image réduite."""
    # le champ varie lentement : on l'estime sur une version encore plus petite
    mini, _ = _reduire(petit, 256)
    lum = mini.mean(axis=2)
    clair = lum >= np.percentile(lum, 85)
    teinte = np.median(mini[clair], axis=0)
    champ = np.broadcast_to(teinte, mini.shape).astype(np.float32)
    sigma = max(mini.shape[:2]) / 12
    for _ in range(3):
        ecart = np.abs(mini / np.maximum(champ, 1e-3) - 1).max(axis=2)
        # le papier est lisse : on écarte les pixels pris dans un trait
        masque = ndimage.binary_erosion(ecart < 0.07, iterations=1)
        if masque.mean() < 0.02:
            break
        champ = _flou_normalise(mini, masque.astype(np.float32), sigma)
    champ = np.clip(champ, 0.05, 1.0)
    taille = (petit.shape[1], petit.shape[0])
    champ = np.stack([_agrandir(champ[..., c], taille) for c in range(3)], axis=2)
    ecart = np.abs(petit / champ - 1).max(axis=2)
    masque = ndimage.binary_erosion(ecart < 0.07, iterations=1)
    return champ, masque


def _feuille(masque_papier: np.ndarray) -> np.ndarray | None:
    """Enveloppe convexe de la feuille, ou None si on ne la distingue pas du cadre."""
    etiq, n = ndimage.label(masque_papier)
    if n == 0:
        return None
    tailles = ndimage.sum(np.ones_like(etiq), etiq, range(1, n + 1))
    # le dessin découpe souvent le papier en plusieurs morceaux : on les garde tous
    gros = np.concatenate([[False], tailles >= 0.005 * masque_papier.size])
    papier = gros[etiq]
    if papier.mean() < 0.15:
        return None
    ys, xs = np.nonzero(papier)
    pts = np.column_stack([xs, ys])
    try:
        hull = ConvexHull(pts)
    except QhullError:
        return None
    h, w = masque_papier.shape
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).polygon([tuple(map(float, pts[i])) for i in hull.vertices], fill=255)
    feuille = np.asarray(im) > 0
    if feuille.mean() > 0.995:
        return None  # la feuille remplit tout le cadre : rien à couper
    return feuille


def _sans_poussieres(masque: np.ndarray, surface_min: float) -> np.ndarray:
    etiq, n = ndimage.label(masque, structure=np.ones((3, 3)))
    if n == 0:
        return masque
    tailles = ndimage.sum(np.ones_like(etiq), etiq, range(1, n + 1))
    garder = np.concatenate([[False], tailles >= max(6, surface_min * masque.size)])
    return garder[etiq]


def detourer(
    image: Image.Image, reglages: Reglages | None = None, sujet: np.ndarray | None = None
) -> Image.Image:
    """`sujet` : masque de probabilité (n'importe quelle taille) qui remplace la détection
    classique de l'intérieur du sujet (cf. ia.masque_sujet)."""
    r = reglages or Reglages()
    image = ImageOps.exif_transpose(image)
    icc = image.info.get("icc_profile")
    dpi = image.info.get("dpi")
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    h, w = rgb.shape[:2]

    petit, echelle = _reduire(rgb, TAILLE_ANALYSE)
    champ_petit, papier_petit = estimer_papier(petit)

    # alpha « couleur vers alpha » sur l'image réduite, pour les masques
    norm_petit = np.clip(petit / champ_petit, 0, 1)
    a_petit = 1 - norm_petit.min(axis=2)
    # niveau de grain du papier : ce qui est en dessous est du papier
    grain = float(np.percentile(a_petit[papier_petit], 99.5)) if papier_petit.any() else 0.03
    plancher_petit = float(np.clip(grain, 0.02, 0.15))

    feuille = _feuille(papier_petit)
    dans_feuille = feuille if feuille is not None else np.ones_like(papier_petit)
    # on rogne un peu la feuille : son bord est souvent ombré
    if feuille is not None:
        dans_feuille = ndimage.binary_erosion(dans_feuille, iterations=2)

    a_net = np.clip((a_petit - plancher_petit) / (1 - plancher_petit), 0, 1)
    trace = _sans_poussieres((a_net > r.seuil_trace) & dans_feuille, r.surface_min)
    garde = ndimage.binary_dilation(trace, iterations=3) & dans_feuille

    if r.interieur_opaque:
        interieur = _interieur(a_net, dans_feuille, r, sujet)
    else:
        interieur = np.zeros_like(papier_petit)

    # ---- pleine résolution ----
    taille = (w, h)
    champ = np.stack([_agrandir(champ_petit[..., c], taille) for c in range(3)], axis=2)
    norm = rgb
    norm /= champ
    np.clip(norm, 0, 1, out=norm)
    del champ

    a = 1 - norm.min(axis=2)
    # le grain est plus fort à pleine résolution qu'en réduit : on le mesure sur place
    papier_plein = _agrandir(papier_petit.astype(np.float32), taille) > 0.99
    if papier_plein.any():
        echant = a[papier_plein]
        if echant.size > 200_000:
            echant = np.random.default_rng(0).choice(echant, 200_000, replace=False)
        plancher = float(np.clip(np.percentile(echant, 99.5), 0.02, 0.2))
    else:
        plancher = plancher_petit
    # au-delà du plafond, c'est opaque : une encre de Chine ne laisse pas voir le fond
    a = np.clip((a - plancher) / (r.plafond - plancher), 0, 1)

    lissage = max(0.6, 0.6 / echelle)
    garde_plein = _agrandir(ndimage.gaussian_filter(garde.astype(np.float32), 1.0), taille)
    a *= np.clip(garde_plein * 1.5, 0, 1)
    if r.interieur_opaque:
        int_plein = _agrandir(interieur.astype(np.float32), taille)
        int_plein = ndimage.gaussian_filter(int_plein, lissage)
        np.maximum(a, np.clip(int_plein * 1.2 - 0.1, 0, 1), out=a)

    # couleur du pigment : posée sur du blanc avec cet alpha, elle redonne le pixel normalisé
    couleur = norm
    couleur -= 1
    couleur /= np.maximum(a, 1e-4)[..., None]
    couleur += 1
    np.clip(couleur, 0, 1, out=couleur)

    rgba = np.empty((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = np.rint(couleur * 255)
    rgba[..., 3] = np.rint(a * 255)
    rgba[..., :3][rgba[..., 3] == 0] = 0
    sortie = Image.fromarray(rgba, "RGBA")
    if icc:
        sortie.info["icc_profile"] = icc
    if dpi:
        sortie.info["dpi"] = dpi
    return sortie


def _interieur(
    a_net: np.ndarray, dans_feuille: np.ndarray, r: Reglages, sujet: np.ndarray | None
) -> np.ndarray:
    """Zones rendues opaques : la peinture franche, les petites réserves qu'elle entoure et,
    avec l'IA, tout le sujet sauf le papier vierge relié au bord de la feuille."""
    peinture = _sans_poussieres((a_net > r.seuil_peinture) & dans_feuille, r.surface_min)
    trous = ndimage.binary_fill_holes(peinture) & ~peinture
    etiq, n = ndimage.label(trous)
    if n:
        tailles = ndimage.sum(np.ones_like(etiq), etiq, range(1, n + 1))
        petits = np.concatenate([[False], tailles <= r.reserve_max * trous.size])
        trous = petits[etiq]
    if sujet is None:
        return _resserrer(peinture | trous)

    proba = _agrandir(sujet, (a_net.shape[1], a_net.shape[0]))
    m = proba > r.seuil_ia
    # une réserve n'est gardée que si l'IA la voit dans le sujet (sinon : papier coincé) ;
    # être entourée de peinture est déjà un indice fort, on se contente d'un avis tiède
    if trous.any():
        etiq, n = ndimage.label(trous)
        moy = ndimage.mean(proba, etiq, range(1, n + 1))
        trous = np.concatenate([[False], moy > r.seuil_ia / 2])[etiq]
    # on reste en retrait du bord du masque, trop grossier pour décider du contour
    m = ndimage.binary_erosion(m, iterations=2) & dans_feuille
    bord = ~dans_feuille
    bord[0, :] = bord[-1, :] = bord[:, 0] = bord[:, -1] = True
    bord = ndimage.binary_dilation(bord, iterations=2)
    # papier vierge (lissé, pour ne pas se laisser piéger par le grain)
    vierge = m & (ndimage.gaussian_filter(a_net, 2) < 2 * r.seuil_trace)
    etiq, n = ndimage.label(vierge)
    if n:
        touche = np.unique(etiq[bord & vierge])
        m &= ~np.isin(etiq, touche[touche > 0])
    return _resserrer(peinture | trous) | m


def _resserrer(peinture: np.ndarray) -> np.ndarray:
    """La zone opaque reste en retrait du bord peint, sinon (agrandie et lissée) elle déborde
    sur le papier et dessine un liseré clair autour des traits fins ; ces bords sont rendus
    par l'alpha fin, calculé à pleine résolution."""
    return ndimage.binary_erosion(peinture, iterations=1)

