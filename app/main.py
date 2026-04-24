from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from .attributes import compose_attribute_prompt
from .config import settings
from .db import connect, init_db, row_to_dict, utc_now
from .retrievers import (
    cosine_similarity,
    decode_json,
    encode_json,
    get_retriever,
    metadata_similarity,
)
from .schemas import AttributeSearchIn, ImageIdSearchIn, InviteCreateIn, LoginIn, RegisterIn, TextSearchIn
from .security import create_access_token, decode_access_token, hash_password, verify_password
from .translation import normalize_for_retrieval


WEB_DIR = settings.base_dir / "web"
MEDIA_DIR = settings.upload_dir
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
VIDEO_MIME_PREFIXES = ("video/",)
SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
PERSON_TARGET = "person"
GENERAL_TARGET = "general"
FAST_UPLOAD_MAX_SIDE = 1920
THUMBNAIL_MAX_SIDE = 480

settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.video_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


def clean_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name or "upload"
    return SAFE_NAME_RE.sub("_", name).strip("._") or "upload"


def clean_label(value: str | None, fallback: str = "") -> str:
    if value is None:
        return fallback
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value[:160] if value else fallback


def media_url(stored_path: str) -> str:
    normalized = stored_path.replace("\\", "/")
    return f"/media/{normalized}"


def image_payload(
    row: dict[str, Any],
    score: float | None = None,
    rank: int | None = None,
    *,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "rank": rank,
        "score": score,
        "similarity_pct": None if score is None else round(max(0.0, min(1.0, score)) * 100, 1),
        "original_filename": row["original_filename"],
        "url": media_url(row["stored_path"]),
        "thumbnail_url": media_url(row["thumbnail_path"]),
        "width": row["width"],
        "height": row["height"],
        "dataset": row["dataset"],
        "person_key": row["person_key"],
        "title": row["title"],
        "tags": row["tags"],
        "created_at": row["created_at"],
        "can_delete": False if user is None else can_manage_image(user, row),
    }
    return payload


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row_to_dict(row)


def set_auth_cookie(response: Response, user: dict[str, Any]) -> None:
    token = create_access_token(user)
    response.set_cookie(
        "grain_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
    )


def auth_token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return request.cookies.get("grain_session")


async def require_user(request: Request) -> dict[str, Any]:
    token = auth_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    user = get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def ensure_super_admin() -> None:
    now = utc_now()
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM users WHERE email = ?", (settings.super_admin_email,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO users (email, password_hash, role, display_name, created_at)
                VALUES (?, ?, 'admin', 'Super Admin', ?)
                """,
                (settings.super_admin_email, hash_password(settings.super_admin_password), now),
            )
        elif existing["role"] != "admin":
            conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (existing["id"],))

        admin_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", (settings.super_admin_email,)
        ).fetchone()["id"]
        for code in settings.invite_bootstrap_codes:
            conn.execute(
                """
                INSERT OR IGNORE INTO invites (code, label, max_uses, used_count, created_by, created_at)
                VALUES (?, 'Bootstrap invite', 100, 0, ?, ?)
                """,
                (code, admin_id, now),
            )


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_super_admin()
    get_retriever(PERSON_TARGET)
    get_retriever(GENERAL_TARGET)


@app.get("/api/health")
def health() -> dict[str, Any]:
    person_retriever = get_retriever(PERSON_TARGET)
    general_retriever = get_retriever(GENERAL_TARGET)
    with connect() as conn:
        image_count = conn.execute("SELECT COUNT(*) AS count FROM images").fetchone()["count"]
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    return {
        "ok": True,
        "app": settings.app_name,
        "backend": person_retriever.name,
        "person_backend": person_retriever.name,
        "general_backend": general_retriever.name,
        "semantic_text": person_retriever.semantic_text or general_retriever.semantic_text,
        "data_dir": str(settings.data_dir),
        "image_count": image_count,
        "user_count": user_count,
    }


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response) -> dict[str, Any]:
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    with connect() as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user["id"]))
    set_auth_cookie(response, user)
    return {"user": public_user(user)}


@app.post("/api/auth/register")
def register(payload: RegisterIn, response: Response) -> dict[str, Any]:
    now = utc_now()
    code = payload.invite_code.strip()
    with connect() as conn:
        invite = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
        if invite is None:
            raise HTTPException(status_code=400, detail="Invitation code is invalid")
        if invite["used_count"] >= invite["max_uses"]:
            raise HTTPException(status_code=400, detail="Invitation code has been used up")
        if invite["expires_at"]:
            expires_at = datetime.fromisoformat(invite["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Invitation code has expired")
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, role, display_name, created_at)
                VALUES (?, ?, 'user', ?, ?)
                """,
                (
                    payload.email,
                    hash_password(payload.password),
                    clean_label(payload.display_name, ""),
                    now,
                ),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Email is already registered") from exc
        conn.execute(
            "UPDATE invites SET used_count = used_count + 1 WHERE id = ?", (invite["id"],)
        )
        user = row_to_dict(conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone())
    assert user is not None
    set_auth_cookie(response, user)
    return {"user": public_user(user)}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("grain_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return {"user": public_user(user)}


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "display_name": user["display_name"],
        "created_at": user["created_at"],
    }


def is_admin(user: dict[str, Any]) -> bool:
    return user.get("role") == "admin"


def normalize_target_type(target_type: str | None, default: str = PERSON_TARGET) -> str:
    value = (target_type or default).strip().lower()
    if value in {"general", "object", "objects", "non-person", "non_person", "scene"}:
        return GENERAL_TARGET
    return PERSON_TARGET


def should_group_by_person(target_type: str | None, requested: bool) -> bool:
    return normalize_target_type(target_type) == PERSON_TARGET and requested


def visibility_filters(user: dict[str, Any], alias: str = "") -> tuple[list[str], list[Any]]:
    if is_admin(user):
        return [], []
    prefix = f"{alias}." if alias else ""
    return [f"{prefix}uploaded_by = ?"], [user["id"]]


def can_manage_image(user: dict[str, Any], row: dict[str, Any]) -> bool:
    return is_admin(user) or row.get("uploaded_by") == user["id"]


@app.get("/api/admin/invites")
def list_invites(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM invites ORDER BY created_at DESC, id DESC").fetchall()
    return {"invites": [row_to_dict(row) for row in rows]}


@app.post("/api/admin/invites")
def create_invite(payload: InviteCreateIn, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    code = payload.code.strip() if payload.code else f"GRAIN-{secrets.token_urlsafe(8).upper()}"
    code = re.sub(r"[^A-Z0-9_-]+", "-", code.upper()).strip("-")
    expires_at = None
    if payload.expires_days:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=payload.expires_days)
        ).isoformat(timespec="seconds")
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO invites (code, label, max_uses, expires_at, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, clean_label(payload.label, ""), payload.max_uses, expires_at, admin["id"], utc_now()),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invitation code already exists") from exc
        row = conn.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()
    return {"invite": row_to_dict(row)}


def infer_person_key(filename: str, explicit: str | None) -> str:
    explicit = clean_label(explicit, "")
    if explicit:
        return explicit
    normalized = filename.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) > 1:
        return clean_label(parts[-2], "")
    stem = Path(parts[-1] if parts else filename).stem
    token = re.split(r"[_\-\s.]+", stem)[0]
    return clean_label(token, "")


def open_image_from_upload(upload: UploadFile, data: bytes) -> Image.Image:
    if upload.content_type and upload.content_type not in IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"{upload.filename}: unsupported image type")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail=f"{upload.filename}: invalid image") from exc
    return image


def prepare_uploaded_image(image: Image.Image) -> Image.Image:
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    if max(prepared.size) > FAST_UPLOAD_MAX_SIDE:
        prepared.thumbnail((FAST_UPLOAD_MAX_SIDE, FAST_UPLOAD_MAX_SIDE))
    return prepared


def save_image_record(
    upload: UploadFile,
    image: Image.Image,
    dataset: str,
    person_key: str,
    title: str,
    tags: str,
    user_id: int,
) -> dict[str, Any]:
    now = utc_now()
    safe_name = clean_filename(upload.filename or "image.jpg")
    uid = uuid4().hex
    original_rel = Path("images") / now[:7] / f"{uid}.jpg"
    thumb_rel = Path("thumbs") / now[:7] / f"{uid}.jpg"
    original_path = settings.upload_dir / original_rel
    thumb_path = settings.upload_dir / thumb_rel
    original_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    rgb = prepare_uploaded_image(image)
    rgb.save(original_path, "JPEG", quality=88)
    thumb = rgb.copy()
    thumb.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
    thumb.save(thumb_path, "JPEG", quality=80)

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO images (
                original_filename, stored_path, thumbnail_path, mime_type, width, height,
                dataset, person_key, title, tags, metadata_json, embedding_json,
                embedding_backend, uploaded_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe_name,
                original_rel.as_posix(),
                thumb_rel.as_posix(),
                "image/jpeg",
                rgb.width,
                rgb.height,
                clean_label(dataset, "default"),
                clean_label(person_key, ""),
                clean_label(title, ""),
                clean_label(tags, ""),
                json.dumps({"source_filename": upload.filename}, ensure_ascii=False),
                None,
                None,
                user_id,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM images WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_dict(row) or {}


@app.post("/api/images/upload")
async def upload_images(
    files: list[UploadFile] = File(...),
    dataset: str = Form("default"),
    person_key: str = Form(""),
    title: str = Form(""),
    tags: str = Form(""),
    infer_person: bool = Form(True),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    uploaded: list[dict[str, Any]] = []
    errors: list[str] = []
    max_bytes = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            errors.append(f"{upload.filename}: exceeds {settings.max_upload_mb} MB")
            continue
        try:
            image = open_image_from_upload(upload, data)
            resolved_person = infer_person_key(upload.filename or "", person_key) if infer_person else person_key
            row = save_image_record(upload, image, dataset, resolved_person, title, tags, user["id"])
            uploaded.append(image_payload(row, user=user))
        except HTTPException as exc:
            errors.append(str(exc.detail))
    return {"uploaded": uploaded, "errors": errors, "count": len(uploaded)}


@app.get("/api/images")
def list_images(
    q: str = "",
    dataset: str = "",
    person_key: str = "",
    page: int = 1,
    page_size: int = 48,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    clauses: list[str] = []
    params: list[Any] = []
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(original_filename LIKE ? OR title LIKE ? OR tags LIKE ? OR dataset LIKE ? OR person_key LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    if dataset.strip():
        clauses.append("dataset = ?")
        params.append(dataset.strip())
    if person_key.strip():
        clauses.append("person_key = ?")
        params.append(person_key.strip())
    scope_clauses, scope_params = visibility_filters(user)
    clauses.extend(scope_clauses)
    params.extend(scope_params)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM images {where}", params).fetchone()["count"]
        rows = conn.execute(
            f"SELECT * FROM images {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        dataset_where = "WHERE " + " AND ".join(scope_clauses) if scope_clauses else ""
        datasets = [
            row["dataset"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT dataset FROM images
                {dataset_where}
                {('AND' if dataset_where else 'WHERE')} dataset IS NOT NULL AND dataset != ''
                ORDER BY dataset
                """,
                scope_params,
            ).fetchall()
        ]
    return {
        "images": [image_payload(row_to_dict(row) or {}, user=user) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "datasets": datasets,
        "visibility_scope": "all" if is_admin(user) else "own",
    }


@app.get("/api/images/{image_id}")
def get_image(image_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = fetch_image(image_id, user)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"image": image_payload(row, user=user)}


def fetch_image(image_id: int, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
    clauses = ["id = ?"]
    params: list[Any] = [image_id]
    if user is not None:
        scope_clauses, scope_params = visibility_filters(user)
        clauses.extend(scope_clauses)
        params.extend(scope_params)
    where = " AND ".join(clauses)
    with connect() as conn:
        row = conn.execute(f"SELECT * FROM images WHERE {where}", params).fetchone()
    return row_to_dict(row)


def all_image_rows(user: dict[str, Any]) -> list[dict[str, Any]]:
    clauses, params = visibility_filters(user)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM images {where} ORDER BY id ASC", params).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def update_embedding(image_id: int, vector: np.ndarray, backend: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO image_embeddings (image_id, backend, embedding_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(image_id, backend) DO UPDATE SET
                embedding_json = excluded.embedding_json,
                updated_at = excluded.updated_at
            """,
            (image_id, backend, encode_json(vector), utc_now()),
        )


def load_cached_embedding(image_id: int, backend: str) -> np.ndarray | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT embedding_json FROM image_embeddings WHERE image_id = ? AND backend = ?",
            (image_id, backend),
        ).fetchone()
    if row is not None:
        return decode_json(row["embedding_json"])
    return None


def embedding_for_row(row: dict[str, Any], target_type: str) -> np.ndarray:
    retriever = get_retriever(target_type)
    vector = load_cached_embedding(row["id"], retriever.name)
    if vector is None:
        legacy_vector = decode_json(row.get("embedding_json"))
        if legacy_vector is not None and row.get("embedding_backend") == retriever.name:
            vector = legacy_vector
    if vector is not None:
        return vector
    image_path = settings.upload_dir / row["stored_path"]
    with Image.open(image_path) as image:
        image.load()
        vector = retriever.encode_image(image)
    update_embedding(row["id"], vector, retriever.name)
    return vector


def score_rows(
    query_vector: np.ndarray,
    *,
    rows: list[dict[str, Any]],
    query_text: str = "",
    top_k: int,
    target_type: str,
    group_by_person: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    retriever = get_retriever(target_type)
    scored: list[tuple[float, dict[str, Any]]] = []
    target_type = normalize_target_type(target_type)
    group_by_person = should_group_by_person(target_type, group_by_person)
    for row in rows:
        image_vector = embedding_for_row(row, target_type)
        visual = cosine_similarity(query_vector, image_vector)
        if retriever.name == "clip":
            visual = (visual + 1.0) / 2.0
        meta = metadata_similarity(query_text, row) if query_text else 0.0
        if query_text and np.linalg.norm(query_vector) <= 1e-8:
            score = meta
        elif target_type == GENERAL_TARGET:
            score = (0.62 * visual) + (0.38 * meta if query_text else 0.0)
        else:
            score = (0.88 * visual) + (0.12 * meta if query_text else 0.0)
        scored.append((float(max(0.0, min(1.0, score))), row))
    scored.sort(key=lambda item: item[0], reverse=True)

    matched_person = None
    selected = scored[:top_k]
    if group_by_person:
        matched = next((row for score, row in scored if row.get("person_key")), None)
        if matched and matched.get("person_key"):
            matched_person = matched["person_key"]
            selected = [(score, row) for score, row in scored if row.get("person_key") == matched_person]
            selected = selected[: max(top_k, len(selected))]

    return [row_to_dict_result(row, score, index) for index, (score, row) in enumerate(selected)], matched_person


def row_to_dict_result(row: dict[str, Any], score: float, index: int) -> dict[str, Any]:
    return image_payload(row, score=score, rank=index + 1)


def materialize_search_results(
    raw_results: list[dict[str, Any]],
    user: dict[str, Any],
) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    for item in raw_results:
        row = fetch_image(item["id"], user)
        if row is None:
            continue
        materialized.append(
            image_payload(row, score=item["score"], rank=item["rank"], user=user)
        )
    return materialized


def record_history(
    user_id: int,
    mode: str,
    query_text: str | None,
    translated_text: str | None,
    latency_ms: int,
    backend: str,
    results: list[dict[str, Any]],
) -> None:
    compact = [
        {
            "id": item["id"],
            "rank": item["rank"],
            "score": item["score"],
            "person_key": item["person_key"],
            "thumbnail_url": item["thumbnail_url"],
        }
        for item in results[:20]
    ]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO search_history (
                user_id, mode, query_text, translated_text, latency_ms, backend,
                result_count, results_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                mode,
                query_text,
                translated_text,
                latency_ms,
                backend,
                len(results),
                json.dumps(compact, ensure_ascii=False),
                utc_now(),
            ),
        )


def run_text_search(
    user: dict[str, Any],
    mode: str,
    query: str,
    top_k: int,
    group_by_person: bool,
    target_type: str,
) -> dict[str, Any]:
    start = time.perf_counter()
    target_type = normalize_target_type(target_type)
    normalized, provider = normalize_for_retrieval(query)
    retriever = get_retriever(target_type)
    query_vector = retriever.encode_text(normalized)
    rows = all_image_rows(user)
    results, matched_person = score_rows(
        query_vector,
        rows=rows,
        query_text=f"{query} {normalized}",
        top_k=min(top_k, settings.search_max_top_k),
        target_type=target_type,
        group_by_person=group_by_person,
    )
    results = materialize_search_results(results, user)
    latency_ms = int((time.perf_counter() - start) * 1000)
    record_history(user["id"], mode, query, normalized, latency_ms, retriever.name, results)
    return {
        "mode": mode,
        "query": query,
        "translated_query": normalized,
        "translation_provider": provider,
        "backend": retriever.name,
        "semantic_text": retriever.semantic_text,
        "latency_ms": latency_ms,
        "matched_person_key": matched_person,
        "target_type": target_type,
        "grouped_by_person": should_group_by_person(target_type, group_by_person),
        "results": results,
    }


@app.post("/api/search/text")
def search_text(payload: TextSearchIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return run_text_search(
        user,
        "text",
        payload.text,
        payload.top_k,
        payload.group_by_person,
        payload.target_type,
    )


@app.post("/api/search/attributes")
def search_attributes(
    payload: AttributeSearchIn, user: dict[str, Any] = Depends(require_user)
) -> dict[str, Any]:
    prompt = compose_attribute_prompt(payload.attributes)
    result = run_text_search(user, "attributes", prompt, payload.top_k, payload.group_by_person, PERSON_TARGET)
    result["attributes"] = payload.attributes
    return result


def run_image_search(
    user: dict[str, Any],
    image: Image.Image,
    label: str,
    top_k: int,
    group_by_person: bool,
    target_type: str,
) -> dict[str, Any]:
    start = time.perf_counter()
    target_type = normalize_target_type(target_type)
    retriever = get_retriever(target_type)
    query_vector = retriever.encode_image(image)
    rows = all_image_rows(user)
    results, matched_person = score_rows(
        query_vector,
        rows=rows,
        top_k=min(top_k, settings.search_max_top_k),
        target_type=target_type,
        group_by_person=group_by_person,
    )
    results = materialize_search_results(results, user)
    latency_ms = int((time.perf_counter() - start) * 1000)
    record_history(user["id"], "image", label, None, latency_ms, retriever.name, results)
    return {
        "mode": "image",
        "query": label,
        "backend": retriever.name,
        "latency_ms": latency_ms,
        "matched_person_key": matched_person,
        "target_type": target_type,
        "grouped_by_person": should_group_by_person(target_type, group_by_person),
        "results": results,
    }


@app.post("/api/search/image")
async def search_image_upload(
    file: UploadFile = File(...),
    top_k: int = Form(24),
    group_by_person: bool = Form(True),
    target_type: str = Form(PERSON_TARGET),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    image = open_image_from_upload(file, data)
    return run_image_search(
        user,
        prepare_uploaded_image(image),
        file.filename or "query image",
        top_k,
        group_by_person,
        target_type,
    )


@app.post("/api/search/image-id")
def search_image_id(payload: ImageIdSearchIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = fetch_image(payload.image_id, user)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    with Image.open(settings.upload_dir / row["stored_path"]) as image:
        image.load()
        return run_image_search(
            user,
            prepare_uploaded_image(image),
            row["original_filename"],
            payload.top_k,
            payload.group_by_person,
            payload.target_type,
        )


@app.delete("/api/images/{image_id}")
def delete_image(image_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    row = fetch_image(image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if not can_manage_image(user, row):
        raise HTTPException(status_code=403, detail="You can only delete your own uploads")
    with connect() as conn:
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
    for relative_path in (row["stored_path"], row["thumbnail_path"]):
        file_path = settings.upload_dir / relative_path
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "deleted_image_id": image_id}


@app.get("/api/search/history")
def search_history(
    limit: int = 40, user: dict[str, Any] = Depends(require_user)
) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM search_history
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user["id"], limit),
        ).fetchall()
    history = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            item["results"] = json.loads(item.pop("results_json") or "[]")
        except json.JSONDecodeError:
            item["results"] = []
        history.append(item)
    return {"history": history}


@app.post("/api/admin/reindex")
def reindex(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    retrievers = {
        retriever.name: retriever
        for retriever in (get_retriever(PERSON_TARGET), get_retriever(GENERAL_TARGET))
    }
    start = time.perf_counter()
    count = 0
    for row in all_image_rows({"role": "admin", "id": -1}):
        image_path = settings.upload_dir / row["stored_path"]
        with Image.open(image_path) as image:
            image.load()
            for retriever in retrievers.values():
                vector = retriever.encode_image(image)
                update_embedding(row["id"], vector, retriever.name)
        count += 1
    return {
        "ok": True,
        "backend": ", ".join(retrievers.keys()),
        "count": count,
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


@app.post("/api/videos/upload")
async def upload_video_placeholder(
    file: UploadFile = File(...),
    dataset: str = Form("default"),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    if file.content_type and not file.content_type.startswith(VIDEO_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail="Unsupported video type")
    safe_name = clean_filename(file.filename or "video")
    uid = uuid4().hex
    stored_rel = Path(f"{utc_now()[:7]}") / f"{uid}_{safe_name}"
    stored_path = settings.video_dir / stored_rel
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    with stored_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO videos (original_filename, stored_path, mime_type, dataset, status, message, uploaded_by, created_at)
            VALUES (?, ?, ?, ?, 'queued_pending_backend', ?, ?, ?)
            """,
            (
                safe_name,
                stored_rel.as_posix(),
                file.content_type or "video/*",
                clean_label(dataset, "default"),
                "Video retrieval API is reserved; frame indexing will be implemented after image retrieval is online.",
                user["id"],
                utc_now(),
            ),
        )
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return {"video": row_to_dict(row)}


@app.get("/api/videos")
def list_videos(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    clauses, params = visibility_filters(user)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM videos {where} ORDER BY created_at DESC, id DESC", params).fetchall()
    return {"videos": [row_to_dict(row) for row in rows]}


@app.post("/api/search/video")
def search_video_placeholder(_: dict[str, Any] = Depends(require_user)) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "detail": "Video retrieval interface is reserved. The current release indexes images only.",
        },
    )


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
