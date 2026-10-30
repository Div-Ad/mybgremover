"""Masque du sujet par BiRefNet (ONNX, processeur) : dit *où* est le sujet, pas *comment*
découper ses bords — ça, c'est le travail de papier.py."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

COTE = 1024
DEPOT = "onnx-community/BiRefNet-ONNX"
FICHIER = "onnx/model.onnx"
DOSSIER = Path(__file__).resolve().parent.parent / "modeles" / "birefnet"
MOYENNE = np.array([0.485, 0.456, 0.406], dtype=np.float32)
ECART = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def chemin_modele() -> Path:
    chemin = DOSSIER / FICHIER
    if not chemin.exists():
        from huggingface_hub import hf_hub_download

        hf_hub_download(DEPOT, FICHIER, local_dir=DOSSIER)
    return chemin


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = os.cpu_count() or 4
    return ort.InferenceSession(
        str(chemin_modele()), options, providers=["CPUExecutionProvider"]
    )


def masque_sujet(rgb: Image.Image) -> np.ndarray:
    """Probabilité d'appartenir au sujet, en flottants [0, 1], format (COTE, COTE)."""
    im = rgb.convert("RGB").resize((COTE, COTE), Image.BILINEAR)
    x = (np.asarray(im, dtype=np.float32) / 255.0 - MOYENNE) / ECART
    x = x.transpose(2, 0, 1)[None]
    sortie = _session().run(None, {_session().get_inputs()[0].name: x})[0][0, 0]
    if sortie.min() < 0 or sortie.max() > 1:
        sortie = 1 / (1 + np.exp(-sortie))
    return sortie.astype(np.float32)
