from app import db


def test_save_and_get_report(tmp_path):
    with db.connect(tmp_path / "test.db") as conn:
        db.save_report(
            conn, report_id="r1", created_at="2026-01-01T00:00:00", media_type="image",
            original_name="a.jpg", sha256="abc", size_bytes=100, verdict="inconclusive",
            confidence_band="low", report={"x": 1}, evidence_dir=None, tags=["Family", "test"],
        )
        got = db.get_report(conn, "r1")
        assert got is not None
        assert got["report"] == {"x": 1}
        assert set(got["tags"]) == {"family", "test"}


def test_list_reports_filters_by_tag(tmp_path):
    with db.connect(tmp_path / "test.db") as conn:
        db.save_report(
            conn, report_id="r1", created_at="2026-01-01T00:00:00", media_type="image",
            original_name="a.jpg", sha256="a", size_bytes=1, verdict="inconclusive",
            confidence_band="low", report={}, evidence_dir=None, tags=["work"],
        )
        db.save_report(
            conn, report_id="r2", created_at="2026-01-02T00:00:00", media_type="audio",
            original_name="b.wav", sha256="b", size_bytes=1, verdict="inconclusive",
            confidence_band="low", report={}, evidence_dir=None, tags=["family"],
        )
        work = db.list_reports(conn, tag="work")
        assert len(work) == 1
        assert work[0]["id"] == "r1"


def test_delete_report(tmp_path):
    with db.connect(tmp_path / "test.db") as conn:
        db.save_report(
            conn, report_id="r1", created_at="2026-01-01T00:00:00", media_type="image",
            original_name="a.jpg", sha256="a", size_bytes=1, verdict="inconclusive",
            confidence_band="low", report={}, evidence_dir=None,
        )
        assert db.delete_report(conn, "r1") is True
        assert db.get_report(conn, "r1") is None
        assert db.delete_report(conn, "r1") is False


def test_settings_roundtrip(tmp_path):
    with db.connect(tmp_path / "test.db") as conn:
        settings = db.get_settings(conn)
        assert settings["fully_local_mode"] == "true"
        db.set_setting(conn, "fully_local_mode", "false")
        assert db.get_settings(conn)["fully_local_mode"] == "false"
