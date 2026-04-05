"""
core/face_db.py — Local SQLite mirror of CompreFace face recognition records.

Stores per-album face index data so the Face Search tab can query results
without hitting the network.  Thread-safe via a module-level lock.

Schema
──────
face_records
    id          INTEGER PK AUTOINCREMENT
    album_name  TEXT NOT NULL
    asset_id    TEXT NOT NULL   ← Immich asset UUID
    filename    TEXT NOT NULL
    subject     TEXT            ← CompreFace subject (person name / 'unknown_<hash>')
    similarity  REAL            ← match confidence 0..1 (NULL = unrecognised)
    thumb_path  TEXT            ← local cached thumbnail path (optional)
    s3_key      TEXT            ← RustFS object key  (<album>/<filename>)
    indexed_at  DATETIME
"""

import os
import sqlite3
import threading
from typing import Optional


_DDL = """
CREATE TABLE IF NOT EXISTS face_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album_name  TEXT    NOT NULL,
    asset_id    TEXT    NOT NULL,
    filename    TEXT    NOT NULL,
    subject     TEXT,
    similarity  REAL,
    thumb_path  TEXT,
    s3_key      TEXT,
    indexed_at  DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_album_subject
    ON face_records(album_name, subject);
CREATE INDEX IF NOT EXISTS idx_album_name
    ON face_records(album_name);
"""


class FaceDB:
    """Thread-safe SQLite wrapper for face recognition records."""

    def __init__(self, db_path: str):
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_DDL)

    # ── Write operations ──────────────────────────────────────────────────────

    def insert_record(
        self,
        album_name: str,
        asset_id: str,
        filename: str,
        subject: Optional[str],
        similarity: Optional[float],
        thumb_path: Optional[str] = None,
        s3_key: Optional[str] = None,
    ) -> int:
        """Insert a single face record. Returns the new row id."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO face_records
                   (album_name, asset_id, filename, subject, similarity, thumb_path, s3_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (album_name, asset_id, filename, subject, similarity, thumb_path, s3_key),
            )
            return cur.lastrowid

    def rename_subject(
        self, album_name: str, old_subject: str, new_subject: str
    ) -> int:
        """Rename all records with old_subject → new_subject in an album."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE face_records SET subject=? WHERE album_name=? AND subject=?",
                (new_subject, album_name, old_subject),
            )
            return cur.rowcount

    def delete_album(self, album_name: str) -> int:
        """Delete all face records for an album. Returns affected row count."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM face_records WHERE album_name=?", (album_name,)
            )
            return cur.rowcount

    # ── Read operations ───────────────────────────────────────────────────────

    def list_albums(self) -> list[str]:
        """Return all distinct album names that have face records."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT album_name FROM face_records ORDER BY album_name"
            ).fetchall()
            return [r["album_name"] for r in rows]

    def list_subjects(self, album_name: str) -> list[str]:
        """Return all distinct subjects indexed for an album (sorted)."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT subject FROM face_records
                   WHERE album_name=? AND subject IS NOT NULL
                   ORDER BY subject""",
                (album_name,),
            ).fetchall()
            return [r["subject"] for r in rows]

    def query_by_subject(self, album_name: str, subject: str) -> list[dict]:
        """Return all records matching album + subject, best similarity first."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM face_records
                   WHERE album_name=? AND subject=?
                   ORDER BY similarity DESC""",
                (album_name, subject),
            ).fetchall()
            return [dict(r) for r in rows]

    def query_by_album(self, album_name: str) -> list[dict]:
        """Return every face record for an album in reverse-indexed order."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM face_records WHERE album_name=? ORDER BY indexed_at DESC",
                (album_name,),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self, album_name: str) -> dict:
        """
        Quick aggregate stats for an album:
            total, identified, unknown, subjects (distinct count)
        """
        with self._lock, self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM face_records WHERE album_name=?", (album_name,)
            ).fetchone()[0]
            identified = conn.execute(
                """SELECT COUNT(*) FROM face_records
                   WHERE album_name=? AND subject IS NOT NULL
                     AND subject NOT LIKE 'unknown%'""",
                (album_name,),
            ).fetchone()[0]
            subjects_count = conn.execute(
                """SELECT COUNT(DISTINCT subject) FROM face_records
                   WHERE album_name=? AND subject IS NOT NULL""",
                (album_name,),
            ).fetchone()[0]
        return {
            "total": total,
            "identified": identified,
            "unknown": total - identified,
            "subjects": subjects_count,
        }
