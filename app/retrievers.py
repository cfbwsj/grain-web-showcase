from __future__ import annotations

import math
import re
import sys
from functools import lru_cache
from pathlib import Path
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

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
PERSON_TARGET = "person"
GENERAL_TARGET = "general"
OPENCLIP_PROMPT_PREFIXES = (
    "a photo of ",
    "an image of ",
    "a close-up photo of ",
    "a detailed photo of ",
    "a full body photo of ",
)
METADATA_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "photo",
    "image",
    "full",
    "body",
    "close",
    "up",
    "detailed",
}


def normalize_target_type(target_type: str | None) -> str:
    value = (target_type or PERSON_TARGET).strip().lower()
    if value in {"general", "object", "objects", "non-person", "non_person", "scene"}:
        return GENERAL_TARGET
    return PERSON_TARGET


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
    semantic_text = False

    def __init__(self, backend_name: str = "feature") -> None:
        self.name = backend_name
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


class OpenClipRetriever(BaseRetriever):
    name = "openclip"
    semantic_text = True

    def __init__(self) -> None:
        import open_clip
        import torch

        self.open_clip = open_clip
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            settings.general_openclip_model,
            pretrained=settings.general_openclip_pretrained,
            device=self.device,
        )
        self.tokenizer = open_clip.get_tokenizer(settings.general_openclip_model)
        self.model.eval()

    def _finalize(self, tensor: Any) -> np.ndarray:
        vector = tensor.detach().cpu().float().numpy()[0]
        return normalize_vector(vector)

    def _prompt_variants(self, text: str) -> list[str]:
        base = re.sub(r"\s+", " ", (text or "").strip()).strip(" ,.;:")
        if not base:
            return [""]
        lowered = base.lower()
        if lowered.startswith(OPENCLIP_PROMPT_PREFIXES):
            return [base]
        variants = [
            base,
            f"a photo of {base}",
            f"an image of {base}",
            f"a close-up photo of {base}",
            f"a detailed photo of {base}",
        ]
        return list(dict.fromkeys(variants))

    def encode_image(self, image: Image.Image) -> np.ndarray:
        tensor = self.preprocess(image.convert("RGB")).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            features = self.model.encode_image(tensor)
        return self._finalize(features)

    def encode_text(self, text: str) -> np.ndarray:
        prompts = self._prompt_variants(text)
        tokens = self.tokenizer(prompts).to(self.device)
        with self.torch.no_grad():
            features = self.model.encode_text(tokens)
        vectors = features.detach().cpu().float().numpy()
        if vectors.ndim == 1:
            return normalize_vector(vectors)
        normalized = np.asarray([normalize_vector(vector) for vector in vectors], dtype="float32")
        return normalize_vector(normalized.mean(axis=0))


class GrainRetriever(BaseRetriever):
    name = "grain"
    semantic_text = True

    def __init__(self) -> None:
        import torch

        config_path = Path(settings.grain_config_file).expanduser()
        checkpoint_path = Path(settings.grain_checkpoint).expanduser()
        if not config_path.is_file():
            raise FileNotFoundError(f"GRAIN_CONFIG_FILE not found: {config_path}")
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"GRAIN_CHECKPOINT not found: {checkpoint_path}")

        repo_root = settings.base_dir.parent.resolve()
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from datasets.bases import tokenize
        from datasets.build import build_transforms
        from model import build_model
        from utils.checkpoint import Checkpointer
        from utils.iotools import load_train_configs
        from utils.simple_tokenizer import SimpleTokenizer

        self.torch = torch
        self.tokenize = tokenize
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.args = load_train_configs(str(config_path))
        self.args.training = False
        self.model = build_model(self.args)
        checkpointer = Checkpointer(self.model)
        checkpointer.load(str(checkpoint_path))
        self.model.to(self.device)
        self.model.eval()
        self.transform = build_transforms(img_size=tuple(self.args.img_size), is_train=False)
        self.tokenizer = SimpleTokenizer()
        self.text_length = getattr(self.args, "text_length", 77)

    def _finalize(self, tensor: Any) -> np.ndarray:
        vector = tensor.detach().cpu().float().numpy()[0]
        return normalize_vector(vector)

    def encode_image(self, image: Image.Image) -> np.ndarray:
        tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            features = self.model.encode_image(tensor)
        return self._finalize(features)

    def encode_text(self, text: str) -> np.ndarray:
        tokens = self.tokenize(
            text,
            tokenizer=self.tokenizer,
            text_length=self.text_length,
            truncate=True,
        ).unsqueeze(0).to(self.device)
        with self.torch.no_grad():
            features = self.model.encode_text(tokens)
        return self._finalize(features)


def token_set(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "")}


def metadata_similarity(query: str, image_record: dict[str, Any]) -> float:
    query_tokens = {token for token in token_set(query) if token not in METADATA_STOPWORDS}
    if not query_tokens:
        return 0.0
    haystack = " ".join(
        str(image_record.get(key) or "")
        for key in ("original_filename", "dataset", "person_key", "title", "tags")
    )
    target_tokens = {token for token in token_set(haystack) if token not in METADATA_STOPWORDS}
    if not target_tokens:
        return 0.0
    overlap = len(query_tokens & target_tokens)
    return min(1.0, overlap / max(len(query_tokens), 1))


def _build_backend(backend: str, target_type: str) -> BaseRetriever:
    backend = (backend or "feature").strip().lower()
    if backend == "grain":
        return GrainRetriever()
    if backend in {"openclip", "open_clip", "clip"}:
        return OpenClipRetriever()
    return FeatureRetriever(backend_name=f"feature-{target_type}")


def _fallback_name(target_type: str) -> str:
    return f"feature-{target_type}-fallback"


@lru_cache(maxsize=4)
def get_retriever(target_type: str = PERSON_TARGET) -> BaseRetriever:
    target_type = normalize_target_type(target_type)
    backend = (
        settings.general_retriever_backend
        if target_type == GENERAL_TARGET
        else settings.person_retriever_backend
    )
    try:
        return _build_backend(backend, target_type)
    except Exception:
        if not settings.allow_retriever_fallback:
            raise
        return FeatureRetriever(backend_name=_fallback_name(target_type))
