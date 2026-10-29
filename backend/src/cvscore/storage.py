"""File storage by id. CVs are saved once and referenced by `cv_id` everywhere else.

Layout: <storage_dir>/cv/<cv_id>/original.<pdf|docx>
Low-level module: it may be imported by the API and by the services.
"""

import re
import shutil
import time
import uuid
from pathlib import Path

from cvscore.config import get_service_settings

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# First bytes of each format: the extension alone is not trusted.
_MAGIC = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}
_CV_ID_RE = re.compile(r"[0-9a-f]{32}")


class StorageError(Exception):
    """Invalid upload, invalid id, or file not found."""


def _cv_root(storage_dir: Path | None) -> Path:
    return (storage_dir or get_service_settings().storage_dir) / "cv"


def _cv_folder(cv_id: str, storage_dir: Path | None) -> Path:
    # The id becomes part of a path: accept only what we generate ourselves.
    if not _CV_ID_RE.fullmatch(cv_id):
        raise StorageError("invalid cv_id")
    return _cv_root(storage_dir) / cv_id


def save_cv(data: bytes, filename: str, storage_dir: Path | None = None) -> str:
    """Validate and store an uploaded CV. Returns its new cv_id."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"unsupported file type: {ext or 'none'}")
    if not data:
        raise StorageError("empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise StorageError("file too large")
    if not data.startswith(_MAGIC[ext]):
        raise StorageError("file content does not match its extension")

    cv_id = uuid.uuid4().hex
    folder = _cv_folder(cv_id, storage_dir)
    folder.mkdir(parents=True)
    (folder / f"original{ext}").write_bytes(data)
    return cv_id


def get_cv_path(cv_id: str, storage_dir: Path | None = None) -> Path:
    folder = _cv_folder(cv_id, storage_dir)
    matches = list(folder.glob("original.*")) if folder.is_dir() else []
    if not matches:
        raise StorageError("cv not found")
    return matches[0]


def delete_cv(cv_id: str, storage_dir: Path | None = None) -> None:
    shutil.rmtree(_cv_folder(cv_id, storage_dir), ignore_errors=True)


def purge_expired(
    ttl_seconds: int, storage_dir: Path | None = None, now: float | None = None
) -> int:
    """Delete CVs older than the TTL. Returns how many were removed."""
    root = _cv_root(storage_dir)
    if not root.is_dir():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for folder in root.iterdir():
        if folder.is_dir() and now - folder.stat().st_mtime > ttl_seconds:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
