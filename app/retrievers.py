from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image

from .config import settings


COLOR_PROTOTYPES: list[tuple[str, tuple[int, int, int]]] = [
    ("black", (18, 18, 18)),
    ("white", (238, 238, 232)),
    ("gray", (128, 128, 128)),
    ("red", (206, 42, 42)),
    ("blue", (45, 98, 210)),
    ("green", (52, 148, 84)),
    ("yellow", (231, 199, 53)),
    ("brown", (134, 83, 45)),
    ("orange", (223, 119, 45)),
    ("pink", (220, 108, 156)),
    ("purple", (129, 78, 182)),
]

COLOR_WORDS = {name for name, _ in COLOR_PROTOTYPES}
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = vector.astype("float32")
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-8 or math.isnan(norm):
        return vector
    return vector / norm


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 1e-8 or right_norm <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def encode_json(vector: np.ndarray) -> str:
    return "[" + ",".join(f"{float(item):.7f}" for item in vector.tolist()) + "]"


def decode_json(value: str | None) -> np.ndarray | None:
    if not value:
        return None
    import json

    try:
        return np.asarray(json.loads(value), dtype="float32")
    except (TypeError, ValueError):
        return None


class BaseRetriever:
    name = "base"
    semantic_text = False

    def encode_image(self, image: Image.Image) -> np.ndarray:
        raise NotImplementedError

    def encode_text(self, text: str) -> np.ndarray:
        raise NotImplementedError


class FeatureRetriever(BaseRetriever):
    """Small dependency-free retriever for demos and constrained Render instances."""

    name = "feature"
    semantic_text = False

    def __init__(self) -> None:
        self._colors = np.asarray([rgb for _, rgb in COLOR_PROTOTYPES], dtype="float32") / 255.0

    def encode_image(self, image: Image.Image) -> np.ndarray:
        rgb = image.convert("RGB")
        rgb.thumbnail((128, 128))
        pixels = np.asarray(rgb, dtype="float32").reshape(-1, 3) / 255.0
        if pixels.size == 0:
            return np.zeros(len(COLOR_PROTOTYPES), dtype="float32")
        distances = ((pixels[:, None, :] - self._colors[None, :, :]) ** 2).sum(axis=2)
        nearest = distances.argmin(axis=1)
        hist = np.bincount(nearest, minlength=len(COLOR_PROTOTYPES)).astype("float32")
        hist = hist / max(float(hist.sum()), 1.0)
        return normalize_vector(hist)

    def encode_text(self, text: str) -> np.ndarray:
        tokens = set(token.lower() for token in TOKEN_RE.findall(text or ""))
        vector = np.zeros(len(COLOR_PROTOTYPES), dtype="float32")
        for index, (name, _) in enumerate(COLOR_PROTOTYPES):
            if name in tokens or (name == "gray" and "grey" in tokens):
                vector[index] = 1.0
        return normalize_vector(vector)


class ClipRetriever(BaseRetriever):
    name = "clip"
    semantic_text = True

    def __init__(self) -> None:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(settings.clip_model_name).to(self.device)
        self.model.eval()
        self.processor = CLIPProcessor.from_pretrained(settings.clip_model_name)

    def _finalize(self, tensor: Any) -> np.ndarray:
        vector = tensor.detach().cpu().float().numpy()[0]
        return normalize_vector(vector)

    def encode_image(self, image: Image.Image) -> np.ndarray:
        inputs = self.processor(images=image.convert("RGB"), return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self.torch.no_grad():
            features = self.model.get_image_features(**inputs)
        return self._finalize(features)

    def encode_text(self, text: str) -> np.ndarray:
        inputs = self.processor(text=[text], padding=True, truncation=True, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self.torch.no_grad():
            features = self.model.get_text_features(**inputs)
        return self._finalize(features)


def token_set(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "")}


def metadata_similarity(query: str, image_record: dict[str, Any]) -> float:
    query_tokens = token_set(query)
    if not query_tokens:
        return 0.0
    haystack = " ".join(
        str(image_record.get(key) or "")
        for key in ("original_filename", "dataset", "person_key", "title", "tags")
    )
    target_tokens = token_set(haystack)
    if not target_tokens:
        return 0.0
    overlap = len(query_tokens & target_tokens)
    return min(1.0, overlap / max(len(query_tokens), 1))


@lru_cache(maxsize=1)
def get_retriever() -> BaseRetriever:
    backend = settings.retriever_backend
    if backend in {"clip", "auto"}:
        try:
            return ClipRetriever()
        except Exception:
            if backend == "clip":
                raise
    return FeatureRetriever()

