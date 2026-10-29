import os

import pytest

from cvscore import storage
from cvscore.storage import StorageError

PDF = b"%PDF-1.4 fake pdf body"
DOCX = b"PK\x03\x04 fake docx body"


def test_save_and_get_path_round_trip(tmp_path):
    cv_id = storage.save_cv(PDF, "My CV.PDF", storage_dir=tmp_path)

    path = storage.get_cv_path(cv_id, storage_dir=tmp_path)

    assert path.name == "original.pdf"
    assert path.read_bytes() == PDF


def test_docx_is_accepted(tmp_path):
    cv_id = storage.save_cv(DOCX, "cv.docx", storage_dir=tmp_path)
    assert storage.get_cv_path(cv_id, storage_dir=tmp_path).suffix == ".docx"


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (PDF, "cv.exe"),  # extension not allowed
        (PDF, "cv"),  # no extension
        (b"", "cv.pdf"),  # empty
        (b"just text", "cv.pdf"),  # content does not match the extension
        (DOCX, "cv.pdf"),  # a docx renamed to pdf
        (PDF + b"x" * storage.MAX_UPLOAD_BYTES, "cv.pdf"),  # too large
    ],
)
def test_invalid_uploads_are_rejected(tmp_path, data, filename):
    with pytest.raises(StorageError):
        storage.save_cv(data, filename, storage_dir=tmp_path)


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "abc", "", "g" * 32, "A" * 32])
def test_path_traversal_and_malformed_ids_are_rejected(tmp_path, bad_id):
    with pytest.raises(StorageError):
        storage.get_cv_path(bad_id, storage_dir=tmp_path)


def test_unknown_but_well_formed_id_is_not_found(tmp_path):
    with pytest.raises(StorageError):
        storage.get_cv_path("0" * 32, storage_dir=tmp_path)


def test_delete_removes_the_cv(tmp_path):
    cv_id = storage.save_cv(PDF, "cv.pdf", storage_dir=tmp_path)

    storage.delete_cv(cv_id, storage_dir=tmp_path)

    with pytest.raises(StorageError):
        storage.get_cv_path(cv_id, storage_dir=tmp_path)


def test_purge_expired_removes_only_old_cvs(tmp_path):
    old_id = storage.save_cv(PDF, "old.pdf", storage_dir=tmp_path)
    new_id = storage.save_cv(PDF, "new.pdf", storage_dir=tmp_path)
    now = 1_000_000.0
    # The old CV was stored 2 hours before "now", the new one 1 minute before.
    for cv_id, age in ((old_id, 7200), (new_id, 60)):
        folder = storage.get_cv_path(cv_id, storage_dir=tmp_path).parent
        os.utime(folder, (now - age, now - age))

    removed = storage.purge_expired(3600, storage_dir=tmp_path, now=now)

    assert removed == 1
    with pytest.raises(StorageError):
        storage.get_cv_path(old_id, storage_dir=tmp_path)
    assert storage.get_cv_path(new_id, storage_dir=tmp_path).exists()
