import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import serveur
from tests.test_papier import aquarelle


@pytest.fixture
def client(monkeypatch):
    # pas de vrai modèle : le masque IA est simulé
    monkeypatch.setattr(serveur, "_preparer_modele", lambda: serveur._etat.update(modele="pret"))
    monkeypatch.setattr(
        serveur.ia, "masque_sujet", lambda im: np.asarray(aquarelle(True)[1], dtype=np.float32)
    )
    with TestClient(serveur.app) as c:
        serveur._etat["modele"] = "pret"
        yield c


def _jpeg() -> bytes:
    tampon = io.BytesIO()
    aquarelle()[0].save(tampon, "JPEG", quality=92, dpi=(300, 300))
    return tampon.getvalue()


def _charger(client, contenu: bytes, nom="aquarelle.jpg") -> dict:
    r = client.post("/api/charger", files={"fichier": (nom, contenu, "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()


def _png(image: Image.Image) -> bytes:
    tampon = io.BytesIO()
    image.save(tampon, "PNG", dpi=(1200, 1200))
    return tampon.getvalue()


def _lancer(client, ident: str, **taille) -> dict:
    r = client.post(f"/api/detourer/{ident}", data={k: str(v) for k, v in taille.items()})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("ext", ["png", "webp", "avif"])
def test_charger_lancer_telecharger(client, ext):
    depot = _charger(client, _jpeg())
    assert (depot["largeur"], depot["hauteur"], depot["dpi"]) == (800, 600, 300)
    corps = _lancer(client, depot["id"])
    assert (corps["largeur"], corps["hauteur"]) == (800, 600)

    for cote in ("avant", "apres"):
        assert client.get(f"/api/apercu/{corps['id']}/{cote}").status_code == 200

    fichier = client.get(f"/api/resultat/{corps['id']}.{ext}")
    assert fichier.status_code == 200
    im = Image.open(io.BytesIO(fichier.content))
    assert im.format == ext.upper() and im.size == (800, 600)
    alpha = np.asarray(im.convert("RGBA"))[..., 3]
    assert alpha[0, 0] == 0 and alpha[300, 400] == 255
    if ext == "png":
        assert round(im.info["dpi"][0]) == 300
    # le dépôt est consommé
    assert client.post(f"/api/detourer/{depot['id']}").status_code == 404


def test_fichier_illisible(client):
    r = client.post("/api/charger", files={"fichier": ("x.jpg", b"pas une image", "image/jpeg")})
    assert r.status_code == 415


def test_resultat_inconnu(client):
    assert client.get("/api/resultat/inconnu.png").status_code == 404
    assert client.get("/api/resultat/inconnu.gif").status_code == 404
    assert client.post("/api/detourer/inconnu").status_code == 404


def test_retirer_un_depot(client):
    depot = _charger(client, _jpeg())
    assert client.delete(f"/api/charger/{depot['id']}").status_code == 200
    assert client.post(f"/api/detourer/{depot['id']}").status_code == 404


@pytest.mark.parametrize(
    "transposer, attendu",
    [(False, (300, 225)), (True, (225, 300))],  # paysage : hauteur ; portrait : largeur
)
def test_reduction_petit_cote_en_px(client, transposer, attendu):
    image = aquarelle()[0]  # 800 × 600, paysage
    if transposer:
        image = image.transpose(Image.Transpose.TRANSPOSE)
    depot = _charger(client, _png(image), "scan.png")
    assert (depot["largeur"], depot["hauteur"], depot["dpi"]) == (*image.size, 1200)
    corps = _lancer(client, depot["id"], dpi=300, cote=225, unite="px")
    assert (corps["largeur"], corps["hauteur"]) == attendu
    png = Image.open(io.BytesIO(client.get(f"/api/resultat/{corps['id']}.png").content))
    assert png.size == attendu and round(png.info["dpi"][0]) == 300


@pytest.mark.parametrize("contenu", [_png, lambda im: _jpeg()], ids=["png", "jpeg"])
def test_reduction_en_cm(client, contenu):
    # 4 cm à 100 dpi = 157 px sur le petit côté (le JPEG passe par le décodage réduit)
    corps = _lancer(client, _charger(client, contenu(aquarelle()[0]))["id"], dpi=100, cote=4, unite="cm")
    assert (corps["largeur"], corps["hauteur"]) == (209, 157)
    png = Image.open(io.BytesIO(client.get(f"/api/resultat/{corps['id']}.png").content))
    assert round(png.info["dpi"][0]) == 100


def test_orientation_exif_annoncee(client):
    exif = Image.Exif()
    exif[0x0112] = 6  # photo prise de côté
    tampon = io.BytesIO()
    aquarelle()[0].save(tampon, "JPEG", exif=exif)
    depot = _charger(client, tampon.getvalue())
    assert (depot["largeur"], depot["hauteur"]) == (600, 800)
    corps = _lancer(client, depot["id"], dpi=300, cote=300, unite="px")
    assert (corps["largeur"], corps["hauteur"]) == (300, 400)


def test_pas_d_agrandissement(client):
    # 21 cm à 300 dpi = 2480 px > 600 : l'image reste telle quelle, dpi d'origine
    corps = _lancer(client, _charger(client, _png(aquarelle()[0]), "s.png")["id"], dpi=300, cote=21, unite="cm")
    assert (corps["largeur"], corps["hauteur"]) == (800, 600)
    png = Image.open(io.BytesIO(client.get(f"/api/resultat/{corps['id']}.png").content))
    assert round(png.info["dpi"][0]) == 1200


def test_reglage_invalide(client):
    depot = _charger(client, _jpeg())
    r = client.post(f"/api/detourer/{depot['id']}", data={"dpi": "300", "cote": "21", "unite": "pouces"})
    assert r.status_code == 422


@pytest.mark.parametrize("fmt", ["TIFF", "JPEG"])
def test_apercu_de_l_original_avant_lancement(client, fmt):
    grande = aquarelle()[0].resize((3200, 2400))
    tampon = io.BytesIO()
    grande.save(tampon, fmt)
    depot = _charger(client, tampon.getvalue(), f"scan.{fmt.lower()}")
    r = client.get(f"/api/apercu/{depot['id']}/avant")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(r.content)).size) == serveur.APERCU
    assert client.get(f"/api/apercu/{depot['id']}/apres").status_code == 404  # pas encore détourée
    corps = _lancer(client, depot["id"])
    assert client.get(f"/api/apercu/{corps['id']}/apres").status_code == 200
