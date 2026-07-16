"""
SQLite persistence for generated posts and scheduled jobs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Iterable

from config import DB_PATH
from utils import get_logger

logger = get_logger("database")


@dataclass
class PostRecord:
    """A stored social post."""

    id: int
    topic: str
    industry: str
    tone: str
    language: str
    platforms: str
    payload_json: str
    title: str
    summary: str
    created_at: str
    updated_at: str

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)


@dataclass
class ScheduleRecord:
    """A scheduled publish entry."""

    id: int
    post_id: int
    platform: str
    scheduled_at: str
    status: str
    notes: str
    created_at: str
    updated_at: str


class Database:
    """Thread-safe thin wrapper around SQLite."""

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    industry TEXT DEFAULT '',
                    tone TEXT DEFAULT '',
                    language TEXT DEFAULT 'English',
                    platforms TEXT DEFAULT '',
                    payload_json TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_posts_topic ON posts(topic);
                CREATE INDEX IF NOT EXISTS idx_schedules_at ON schedules(scheduled_at);
                """
            )
        logger.info("Database ready at %s", self.db_path)

    def save_post(
        self,
        payload: dict[str, Any],
        *,
        industry: str = "",
        tone: str = "",
        language: str = "English",
        platforms: Iterable[str] | None = None,
        post_id: int | None = None,
    ) -> int:
        """Insert or update a post. Returns the post id."""
        now = datetime.now().isoformat(timespec="seconds")
        topic = str(payload.get("topic", "")).strip()
        title = str(payload.get("title", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        platform_str = ", ".join(platforms or [])
        body = json.dumps(payload, ensure_ascii=False)

        with self._connect() as conn:
            if post_id:
                conn.execute(
                    """
                    UPDATE posts
                    SET topic=?, industry=?, tone=?, language=?, platforms=?,
                        payload_json=?, title=?, summary=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        topic,
                        industry,
                        tone,
                        language,
                        platform_str,
                        body,
                        title,
                        summary,
                        now,
                        post_id,
                    ),
                )
                return post_id

            cur = conn.execute(
                """
                INSERT INTO posts (
                    topic, industry, tone, language, platforms,
                    payload_json, title, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    topic,
                    industry,
                    tone,
                    language,
                    platform_str,
                    body,
                    title,
                    summary,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def get_post(self, post_id: int) -> PostRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM posts WHERE id = ?", (post_id,)
            ).fetchone()
        return self._row_to_post(row) if row else None

    def list_posts(self, query: str = "", limit: int = 200) -> list[PostRecord]:
        q = f"%{(query or '').strip()}%"
        with self._connect() as conn:
            if query.strip():
                rows = conn.execute(
                    """
                    SELECT * FROM posts
                    WHERE topic LIKE ? OR title LIKE ? OR summary LIKE ?
                          OR payload_json LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (q, q, q, q, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def delete_post(self, post_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM schedules WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    def add_schedule(
        self,
        post_id: int,
        platform: str,
        scheduled_at: str,
        notes: str = "",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO schedules (
                    post_id, platform, scheduled_at, status, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                """,
                (post_id, platform, scheduled_at, notes, now, now),
            )
            return int(cur.lastrowid)

    def list_schedules(self, status: str | None = None) -> list[ScheduleRecord]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM schedules
                    WHERE status = ?
                    ORDER BY scheduled_at ASC
                    """,
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM schedules ORDER BY scheduled_at ASC"
                ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def due_schedules(self, now_iso: str | None = None) -> list[ScheduleRecord]:
        now = now_iso or datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM schedules
                WHERE status = 'pending' AND scheduled_at <= ?
                ORDER BY scheduled_at ASC
                """,
                (now,),
            ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def update_schedule_status(
        self, schedule_id: int, status: str, notes: str | None = None
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            if notes is None:
                conn.execute(
                    """
                    UPDATE schedules SET status=?, updated_at=? WHERE id=?
                    """,
                    (status, now, schedule_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE schedules
                    SET status=?, notes=?, updated_at=?
                    WHERE id=?
                    """,
                    (status, notes, now, schedule_id),
                )

    def delete_schedule(self, schedule_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM schedules WHERE status='pending'"
            ).fetchone()[0]
            done = conn.execute(
                "SELECT COUNT(*) FROM schedules WHERE status='published'"
            ).fetchone()[0]
        return {
            "posts": int(posts),
            "pending_schedules": int(pending),
            "published_schedules": int(done),
        }

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> PostRecord:
        return PostRecord(
            id=row["id"],
            topic=row["topic"],
            industry=row["industry"],
            tone=row["tone"],
            language=row["language"],
            platforms=row["platforms"],
            payload_json=row["payload_json"],
            title=row["title"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> ScheduleRecord:
        return ScheduleRecord(
            id=row["id"],
            post_id=row["post_id"],
            platform=row["platform"],
            scheduled_at=row["scheduled_at"],
            status=row["status"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# Default shared instance
db = Database()
