"""
Background scheduler for delayed social posts.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

import schedule

from database import Database, db
from social_api import SocialPublisher, publisher
from utils import get_logger

logger = get_logger("scheduler")


class PostScheduler:
    """
    In-process scheduler that polls SQLite for due jobs.

    Uses the `schedule` library for a lightweight tick every minute,
    plus a worker thread so the UI stays responsive.
    """

    def __init__(
        self,
        database: Database | None = None,
        social: SocialPublisher | None = None,
    ) -> None:
        self.db = database or db
        self.social = social or publisher
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.on_status: Callable[[str], None] | None = None

    def start(self) -> None:
        """Start the background loop (idempotent)."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            schedule.clear("social-tick")
            schedule.every(30).seconds.do(self._tick).tag("social-tick")
            self._thread = threading.Thread(
                target=self._run_loop, name="PostScheduler", daemon=True
            )
            self._thread.start()
            logger.info("Scheduler started.")
            self._emit("Scheduler running")

    def stop(self) -> None:
        self._stop.set()
        schedule.clear("social-tick")
        logger.info("Scheduler stop requested.")
        self._emit("Scheduler stopped")

    def schedule_post(
        self,
        post_id: int,
        platform: str,
        when: datetime,
        notes: str = "",
    ) -> int:
        """Persist a schedule entry and ensure the worker is running."""
        if when <= datetime.now():
            # Allow near-term schedules (within a minute) but warn on past dates
            if (datetime.now() - when).total_seconds() > 60:
                raise ValueError("Scheduled time must be in the future.")
        iso = when.strftime("%Y-%m-%dT%H:%M:%S")
        schedule_id = self.db.add_schedule(post_id, platform, iso, notes=notes)
        self.start()
        self._emit(f"Scheduled {platform} post #{post_id} for {iso}")
        return schedule_id

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                schedule.run_pending()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scheduler tick error: %s", exc)
            time.sleep(1)

    def _tick(self) -> None:
        due = self.db.due_schedules()
        if not due:
            return
        for item in due:
            self._process(item.id, item.post_id, item.platform)

    def _process(self, schedule_id: int, post_id: int, platform: str) -> None:
        post = self.db.get_post(post_id)
        if not post:
            self.db.update_schedule_status(
                schedule_id, "failed", notes="Post not found"
            )
            self._emit(f"Schedule #{schedule_id} failed: post missing")
            return

        payload = post.payload
        content = self._content_for_platform(payload, platform)
        if not content:
            self.db.update_schedule_status(
                schedule_id, "failed", notes="Empty content for platform"
            )
            return

        # Mark processing to avoid double-sends under concurrent ticks
        self.db.update_schedule_status(schedule_id, "processing")
        result = self.social.publish(platform, content)
        if result.ok:
            self.db.update_schedule_status(
                schedule_id, "published", notes=result.message
            )
            self._emit(f"Published to {platform}: {result.message}")
            logger.info("Published schedule #%s to %s", schedule_id, platform)
        else:
            self.db.update_schedule_status(
                schedule_id, "failed", notes=result.message
            )
            self._emit(f"Publish failed ({platform}): {result.message}")
            logger.error("Publish failed (#%s): %s", schedule_id, result.message)

    @staticmethod
    def _content_for_platform(payload: dict, platform: str) -> str:
        key = platform.strip().lower()
        if key == "linkedin":
            block = payload.get("linkedin", {})
            title = block.get("title", "")
            body = block.get("content", "")
            tags = " ".join(block.get("hashtags", []))
            parts = [p for p in (title, body, tags) if p]
            return "\n\n".join(parts)
        if key in {"x", "twitter"}:
            block = payload.get("x", {})
            tags = " ".join(block.get("hashtags", []))
            content = block.get("content", "")
            return f"{content} {tags}".strip()
        if key == "facebook":
            block = payload.get("facebook", {})
            tags = " ".join(block.get("hashtags", []))
            return f"{block.get('content', '')}\n\n{tags}".strip()
        if key == "instagram":
            block = payload.get("instagram", {})
            tags = " ".join(block.get("hashtags", []))
            return f"{block.get('caption', '')}\n\n{tags}".strip()
        return ""

    def _emit(self, message: str) -> None:
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:  # noqa: BLE001
                pass


# Shared scheduler instance
post_scheduler = PostScheduler()
