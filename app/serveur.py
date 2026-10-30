"""Serveur local : une page, une API de détourage.

Lancement : python -m uvicorn app.serveur:app --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from moteur import ia
from moteur.papier import detourer

Image.MAX_IMAGE_PIXELS = 300_000_000  # grands scans à 600 dpi

STATIQUE = Path(__file__).resolve().parent / "statique"
APERCU = 1600
GARDES = 40  # résultats gardés en mémoire (pleine résolution)

FORMATS = {
    "png": ("PNG", "image/png", {"compress_level": 6}),
    "webp": ("WEBP", "image/webp", {"lossless": True, "method": 4, "exact": False}),
    "avif": ("AVIF", "image/avif", {"quality": 92, "subsampling": "4:4:4", "speed": 6}),
}

_resultats: OrderedDict[str, dict] = OrderedDict()
_calcul = threading.Lock()  # un seul détourage à la fois : il occupe déjà tout le processeur
_etat = {"modele": "absent", "erreur": None}
_depots: dict[str, Path] = {}  # images déposées, en attente de « Lancer »
_vignettes: dict[str, bytes] = {}  # aperçus de ces images
_verrou_vignettes = threading.Lock()
_temporaire: list[tempfile.TemporaryDirectory] = []


def _dossier_depots() -> Path:
    if not _temporaire:
        _temporaire.append(tempfile.TemporaryDirectory(prefix="detourage-"))
    return Path(_temporaire[0].name)


def _preparer_modele() -> None:
    try:
        _etat["modele"] = "chargement"
        ia._session()
        _etat["modele"] = "pret"
    except Exception as e:  # pas de réseau au premier lancement, fichier corrompu…
        _etat["modele"] = "erreur"
        _etat["erreur"] = str(e)


@asynccontextmanager
async def _cycle(_app: FastAPI):
    # le modèle se charge en tâche de fond : la page s'affiche tout de suite
    asyncio.get_running_loop().run_in_executor(None, lambda: _preparer_modele())
    yield
    _depots.clear()
    _vignettes.clear()
    while _temporaire:
        _temporaire.pop().cleanup()


app = FastAPI(title="Détourage d'aquarelles", lifespan=_cycle)


def _apercu(im: Image.Image) -> bytes:
    im = im.copy()
    im.thumbnail((APERCU, APERCU))
    tampon = io.BytesIO()
    im.save(tampon, "WEBP", quality=88)
    return tampon.getvalue()


def _arrondi(x: float) -> int:
    return int(x + 0.5)  # comme Math.round, pour que la page annonce la taille exacte


def _taille_reduite(
    taille: tuple[int, int], dpi: float, cote: float, unite: str
) -> tuple[int, int] | None:
    """Petit côté ramené à `cote` (cm à `dpi`, ou px). None : pas de réduction (jamais
    d'agrandissement)."""
    cible = _arrondi(cote / 2.54 * dpi) if unite == "cm" else _arrondi(cote)
    petit = min(taille)
    if cible >= petit:
        return None
    f = cible / petit
    return max(1, _arrondi(taille[0] * f)), max(1, _arrondi(taille[1] * f))


def _ouvrir(chemin: Path) -> Image.Image:
    try:
        return Image.open(chemin)  # n'est décodée qu'au besoin : l'en-tête suffit ici
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(415, "Ce fichier n'est pas une image lisible.") from e


def _dimensions(im: Image.Image) -> tuple[int, int]:
    """Taille une fois l'orientation EXIF appliquée."""
    tourne = im.getexif().get(0x0112) in (5, 6, 7, 8)
    return (im.height, im.width) if tourne else im.size


def _traiter(chemin: Path, reduction: tuple[float, float, str] | None = None) -> dict:
    source = _ouvrir(chemin)
    finale = _taille_reduite(_dimensions(source), *reduction) if reduction else None
    if finale and source.format == "JPEG":
        # le JPEG se décode directement à 1/2, 1/4 ou 1/8 : bien plus rapide sur les grands scans
        echelle = finale[0] / _dimensions(source)[0]
        source.draft("RGB", (source.width * echelle, source.height * echelle))
    try:
        source.load()
    except OSError as e:
        raise HTTPException(415, "Ce fichier n'est pas une image lisible.") from e
    source = ImageOps.exif_transpose(source)
    info = {k: source.info[k] for k in ("icc_profile", "dpi") if k in source.info}
    rgb = source.convert("RGB")
    del source
    if finale:
        if rgb.size != finale:
            rgb = rgb.resize(finale, Image.Resampling.LANCZOS, reducing_gap=3.0)
        info["dpi"] = (reduction[0], reduction[0])
    rgb.info.update(info)
    with _calcul:
        debut = time.perf_counter()
        resultat = detourer(rgb, sujet=ia.masque_sujet(rgb))
        duree = time.perf_counter() - debut
    return {
        "image": resultat,
        "avant": _apercu(rgb),
        "apres": _apercu(resultat),
        "duree": duree,
    }


@app.get("/")
def accueil() -> FileResponse:
    return FileResponse(STATIQUE / "index.html")


@app.get("/api/etat")
def etat() -> dict:
    return _etat


@app.post("/api/charger")
async def charger(fichier: UploadFile = File(...)) -> dict:
    """Dépôt d'une image sur le disque ; rien n'est calculé avant « Lancer »."""
    ident = uuid.uuid4().hex
    chemin = _dossier_depots() / ident
    with chemin.open("wb") as f:
        while bloc := await fichier.read(1 << 22):
            f.write(bloc)
    try:
        im = _ouvrir(chemin)
        largeur, hauteur = _dimensions(im)
        dpi = im.info.get("dpi")
        im.close()
    except HTTPException:
        chemin.unlink(missing_ok=True)
        raise
    _depots[ident] = chemin
    return {
        "id": ident,
        "largeur": largeur,
        "hauteur": hauteur,
        "dpi": round(float(dpi[0])) if dpi else None,
    }


@app.delete("/api/charger/{ident}")
def oublier(ident: str) -> dict:
    chemin = _depots.pop(ident, None)
    _vignettes.pop(ident, None)
    if chemin:
        try:
            chemin.unlink(missing_ok=True)
        except PermissionError:  # encore ouvert : le dossier est vidé à l'arrêt
            pass
    return {}


@app.post("/api/detourer/{ident}")
async def detourer_depot(
    ident: str,
    dpi: float | None = Form(None),
    cote: float | None = Form(None),
    unite: str = Form("cm"),
) -> JSONResponse:
    if _etat["modele"] != "pret":
        raise HTTPException(503, "Le modèle n'est pas encore prêt.")
    if ident not in _depots:
        raise HTTPException(404, "Image introuvable : dépose-la à nouveau.")
    reduction = None
    if dpi is not None and cote is not None:
        if unite not in ("cm", "px") or not (0 < dpi <= 4800 and 0 < cote <= 100_000):
            raise HTTPException(422, "Dimensions de sortie invalides.")
        reduction = (dpi, cote, unite)
    r = await run_in_threadpool(_traiter, _depots[ident], reduction)
    oublier(ident)
    _resultats[ident] = r
    while len(_resultats) > GARDES:
        _resultats.popitem(last=False)
    largeur, hauteur = r["image"].size
    return JSONResponse(
        {"id": ident, "duree": round(r["duree"], 1), "largeur": largeur, "hauteur": hauteur}
    )


def _resultat(ident: str) -> dict:
    if ident not in _resultats:
        raise HTTPException(404, "Résultat expiré : relance le détourage.")
    return _resultats[ident]


def _vignette(ident: str) -> bytes:
    """Aperçu de l'original déposé, fabriqué à la première demande."""
    with _verrou_vignettes:
        if ident not in _vignettes:
            if ident not in _depots:  # retirée ou détourée entre-temps
                raise HTTPException(404, "Aperçu introuvable.")
            im = _ouvrir(_depots[ident])
            im.draft("RGB", (APERCU, APERCU))  # JPEG : décodage directement réduit
            try:
                im.load()
            except OSError as e:
                raise HTTPException(415, "Ce fichier n'est pas une image lisible.") from e
            _vignettes[ident] = _apercu(ImageOps.exif_transpose(im).convert("RGB"))
        return _vignettes[ident]


@app.get("/api/apercu/{ident}/{cote}")
def apercu(ident: str, cote: str) -> Response:
    if cote not in ("avant", "apres"):
        raise HTTPException(404)
    if ident in _resultats:
        return Response(_resultats[ident][cote], media_type="image/webp")
    if cote == "avant" and ident in _depots:
        return Response(_vignette(ident), media_type="image/webp")
    raise HTTPException(404, "Aperçu introuvable.")


@app.get("/api/resultat/{ident}.{ext}")
async def telecharger(ident: str, ext: str) -> Response:
    if ext not in FORMATS:
        raise HTTPException(404, "Format inconnu.")
    image = _resultat(ident)["image"]
    nom, mime, options = FORMATS[ext]

    def encoder() -> bytes:
        tampon = io.BytesIO()
        extra = {k: image.info[k] for k in ("icc_profile", "dpi") if k in image.info}
        if nom == "WEBP":
            extra.pop("dpi", None)  # non géré par WebP
        image.save(tampon, nom, **options, **extra)
        return tampon.getvalue()

    return Response(await run_in_threadpool(encoder), media_type=mime)
