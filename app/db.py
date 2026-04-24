from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.video_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                display_name TEXT,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                label TEXT,
                max_uses INTEGER NOT NULL DEFAULT 1,
                used_count INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                thumbnail_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                dataset TEXT,
                person_key TEXT,
                title TEXT,
                tags TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                embedding_json TEXT,
                embedding_backend TEXT,
                uploaded_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_images_dataset ON images(dataset);
            CREATE INDEX IF NOT EXISTS idx_images_person_key ON images(person_key);
            CREATE INDEX IF NOT EXISTS idx_images_created_at ON images(created_at);

            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                query_text TEXT,
                translated_text TEXT,
                latency_ms INTEGER NOT NULL,
                backend TEXT NOT NULL,
                result_count INTEGER NOT NULL,
                results_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_user_created
                ON search_history(user_id, created_at);

            CREATE TABLE IF NOT EXISTS image_embeddings (
                image_id INTEGER NOT NULL,
                backend TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (image_id, backend),
                FOREIGN KEY(image_id) REFERENCES images(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                dataset TEXT,
                status TEXT NOT NULL,
                message TEXT,
                uploaded_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );
            """
        )


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
