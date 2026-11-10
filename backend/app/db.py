"""SQLite storage for reports, tags, and settings. No external DB, no accounts."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import config

_lock = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    media_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    confidence_band TEXT NOT NULL,
    report_json TEXT NOT NULL,
    evidence_dir TEXT
);
CREATE TABLE IF NOT EXISTS tags (
    report_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (report_id, tag),
    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    with _lock:
        conn.executescript(SCHEMA)
        for k, v in config.DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()


def save_report(
    conn: sqlite3.Connection,
    *,
    report_id: str,
    created_at: str,
    media_type: str,
    original_name: str,
    sha256: str,
    size_bytes: int,
    verdict: str,
    confidence_band: str,
    report: dict[str, Any],
    evidence_dir: str | None,
    tags: list[str] | None = None,
) -> None:
    with _lock:
        conn.execute(
            """INSERT INTO reports
               (id, created_at, media_type, original_name, sha256, size_bytes,
                verdict, confidence_band, report_json, evidence_dir)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                report_id, created_at, media_type, original_name, sha256, size_bytes,
                verdict, confidence_band, json.dumps(report), evidence_dir,
            ),
        )
        for tag in tags or []:
            conn.execute(
                "INSERT OR IGNORE INTO tags (report_id, tag) VALUES (?, ?)",
                (report_id, tag.strip().lower()),
            )
        conn.commit()


def get_report(conn: sqlite3.Connection, report_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["report"] = json.loads(d.pop("report_json"))
    d["tags"] = [
        r["tag"] for r in conn.execute(
            "SELECT tag FROM tags WHERE report_id = ?", (report_id,)
        ).fetchall()
    ]
    return d


def list_reports(
    conn: sqlite3.Connection,
    *,
    query: str | None = None,
    tag: str | None = None,
    media_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    sql = "SELECT DISTINCT r.* FROM reports r"
    where = []
    params: list[Any] = []
    if tag:
        sql += " JOIN tags t ON t.report_id = r.id"
        where.append("t.tag = ?")
        params.append(tag.strip().lower())
    if query:
        where.append("(r.original_name LIKE ? OR r.verdict LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if media_type:
        where.append("r.media_type = ?")
        params.append(media_type)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["report"] = json.loads(d.pop("report_json"))
        d["tags"] = [
            r["tag"] for r in conn.execute(
                "SELECT tag FROM tags WHERE report_id = ?", (d["id"],)
            ).fetchall()
        ]
        out.append(d)
    return out


def delete_report(conn: sqlite3.Connection, report_id: str) -> bool:
    with _lock:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        conn.execute("DELETE FROM tags WHERE report_id = ?", (report_id,))
        conn.commit()
        return cur.rowcount > 0


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    with _lock:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()
