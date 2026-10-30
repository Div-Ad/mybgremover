import numpy as np
from PIL import Image

from moteur.papier import Reglages, detourer

H, W = 600, 800
PAPIER = np.array([0.95, 0.92, 0.82])  # Canson crème


def aquarelle(sujet_ia: bool = False):
    """Papier crème éclairé de travers, un disque peint cerné d'encre avec une réserve
    blanche au centre, une poussière isolée."""
    y, x = np.mgrid[0:H, 0:W]
    eclairage = 1 - 0.12 * x / W - 0.05 * y / H
    rng = np.random.default_rng(1)
    img = PAPIER * eclairage[..., None] + rng.normal(0, 0.006, (H, W, 3))
    d = np.hypot(x - 400, y - 300)
    disque = d < 150
    img[disque] *= np.array([0.45, 0.6, 0.85])  # lavis bleu
    img[(d >= 150) & (d < 156)] = 0.08  # trait d'encre
    reserve = d < 30
    img[reserve] = PAPIER * eclairage[reserve][..., None]
    img[50:53, 60:63] = 0.3  # poussière
    rgb = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    proba = (d < 156).astype(np.float32) if sujet_ia else None
    return rgb, proba, d


def test_papier_transparent_sujet_opaque():
    rgb, proba, d = aquarelle()
    a = np.asarray(detourer(rgb, sujet=proba))[..., 3]
    assert (a[d > 170] == 0).mean() > 0.995  # le papier a disparu, malgré l'éclairage
    assert a[d < 140].min() == 255  # le lavis est opaque…
    assert a[d < 25].min() == 255  # … et la réserve blanche entourée aussi
    assert a[(d >= 151) & (d < 155)].min() > 240  # le trait d'encre est entier
    assert a[48:56, 58:66].max() == 0  # la poussière est partie


def test_reserve_rendue_blanche_et_bord_sans_liseré():
    rgb, proba, d = aquarelle(sujet_ia=True)
    out = np.asarray(detourer(rgb, sujet=proba)).astype(int)
    # le crème du papier est retiré : la réserve devient blanche
    assert out[d < 25][:, :3].min() > 240
    # posé sur du noir, l'extérieur du trait ne laisse pas de halo clair
    bord = (d > 157) & (d < 162)
    sur_noir = out[bord][:, :3] * out[bord][:, 3:4] / 255
    assert sur_noir.max() < 60


def test_transparence_integrale_sans_interieur_opaque():
    rgb, _, d = aquarelle()
    a = np.asarray(detourer(rgb, Reglages(interieur_opaque=False)))[..., 3]
    assert a[d < 25].max() < 30  # la réserve redevient transparente
    assert 100 < np.median(a[(d > 60) & (d < 140)]) < 230  # le lavis est translucide


def test_conserve_taille_profil_et_dpi():
    rgb, proba, _ = aquarelle()
    rgb.info["dpi"] = (300, 300)
    rgb.info["icc_profile"] = b"profil"
    out = detourer(rgb, sujet=proba)
    assert out.size == (W, H) and out.mode == "RGBA"
    assert out.info["dpi"] == (300, 300)
    assert out.info["icc_profile"] == b"profil"
