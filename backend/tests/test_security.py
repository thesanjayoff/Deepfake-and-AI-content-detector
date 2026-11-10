from pathlib import Path

import pytest

from app.security import FileValidationError, new_storage_path, sanitize_display_name, sniff_and_validate


def test_sanitize_strips_path_traversal():
    assert sanitize_display_name("../../etc/passwd") == "passwd"
    assert sanitize_display_name("..\\..\\windows\\system32\\evil.exe") == "evil.exe"


def test_sanitize_strips_null_bytes_and_script_chars():
    name = sanitize_display_name('evil<script>"; DROP TABLE;.jpg')
    assert "<" not in name and ">" not in name and '"' not in name and ";" not in name


def test_new_storage_path_never_uses_original_name_for_path(tmp_path):
    path, display = new_storage_path("../../../etc/passwd.jpg", tmp_path)
    assert tmp_path.resolve() in path.parents
    assert "etc" not in str(path)
    assert display == "passwd.jpg"


def test_sniff_rejects_empty_file():
    with pytest.raises(FileValidationError):
        sniff_and_validate(b"", "a.jpg")


def test_sniff_rejects_oversized_file(monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(FileValidationError):
        sniff_and_validate(b"x" * 100, "a.txt")


def test_sniff_detects_real_jpeg_by_content():
    fixtures = Path(__file__).resolve().parent / "fixtures"
    data = (fixtures / "plain_photo.jpg").read_bytes()
    result = sniff_and_validate(data, "plain_photo.jpg")
    assert result.kind == "image"
    assert result.mime == "image/jpeg"


def test_sniff_rejects_mislabeled_file():
    # A text file renamed to .jpg should NOT be sniffed as an image --
    # content sniffing must win over the extension.
    with pytest.raises(FileValidationError):
        sniff_and_validate(b"just plain text content here", "fake.jpg")


def test_sniff_accepts_plain_text():
    result = sniff_and_validate(b"hello world, this is plain text.", "note.txt")
    assert result.kind == "text"


def test_sniff_rejects_binary_claiming_to_be_text():
    with pytest.raises(FileValidationError):
        sniff_and_validate(b"\x00\x01\x02binary garbage\xff\xfe", "note.txt")
