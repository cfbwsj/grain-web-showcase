from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except OSError:
        return False


def _resolve_data_dir() -> Path:
    configured = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
    fallback = (BASE_DIR / "data").resolve()
    if _is_writable_directory(configured):
        return configured
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass(frozen=True)
class Settings:
    app_name: str = "GRAIN Retrieval Showcase"
    base_dir: Path = BASE_DIR
    data_dir: Path = _resolve_data_dir()
    secret_key: str = os.getenv(
        "SECRET_KEY",
        "dev-secret-change-me-please-use-env-in-production-2026",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "72"))
    cookie_secure: bool = _bool_env("COOKIE_SECURE", bool(os.getenv("RENDER")))
    super_admin_email: str = os.getenv("SUPER_ADMIN_EMAIL", "admin@grain.local")
    super_admin_password: str = os.getenv(
        "SUPER_ADMIN_PASSWORD", "ChangeMe-Grain-Admin-2026!"
    )
    invite_bootstrap_codes: tuple[str, ...] = tuple(_list_env("INVITE_BOOTSTRAP_CODES"))
    retriever_backend: str = os.getenv("RETRIEVER_BACKEND", "feature").strip().lower()
    clip_model_name: str = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")
    person_retriever_backend: str = os.getenv(
        "PERSON_RETRIEVER_BACKEND",
        os.getenv("RETRIEVER_BACKEND", "grain"),
    ).strip().lower()
    general_retriever_backend: str = os.getenv(
        "GENERAL_RETRIEVER_BACKEND",
        "openclip",
    ).strip().lower()
    grain_config_file: str = os.getenv("GRAIN_CONFIG_FILE", "").strip()
    grain_checkpoint: str = os.getenv("GRAIN_CHECKPOINT", "").strip()
    general_openclip_model: str = os.getenv(
        "GENERAL_OPENCLIP_MODEL",
        "ViT-B-16",
    ).strip()
    general_openclip_pretrained: str = os.getenv(
        "GENERAL_OPENCLIP_PRETRAINED",
        "laion2b_s34b_b88k",
    ).strip()
    allow_retriever_fallback: bool = _bool_env("ALLOW_RETRIEVER_FALLBACK", True)
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    search_default_top_k: int = int(os.getenv("SEARCH_DEFAULT_TOP_K", "24"))
    search_max_top_k: int = int(os.getenv("SEARCH_MAX_TOP_K", "100"))

    @property
    def database_path(self) -> Path:
        return self.data_dir / "grain_web.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def video_dir(self) -> Path:
        return self.data_dir / "videos"


settings = Settings()
