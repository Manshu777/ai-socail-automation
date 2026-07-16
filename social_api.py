"""
Social platform publishing stubs (tokens loaded from Settings / .env).

These adapters validate credentials and provide a consistent publish interface.
Wire real Graph / LinkedIn / X APIs when production credentials are ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from config import config
from utils import get_logger

logger = get_logger("social_api")


@dataclass
class PublishResult:
    """Result of a publish attempt."""

    ok: bool
    platform: str
    message: str
    response: dict[str, Any] | None = None


class SocialPublisher:
    """Unified publisher for LinkedIn, X, Facebook, and Instagram."""

    def __init__(self) -> None:
        self.timeout = 30

    def publish(
        self, platform: str, content: str, *, extra: dict[str, Any] | None = None
    ) -> PublishResult:
        platform_key = platform.strip().lower()
        handlers = {
            "linkedin": self.publish_linkedin,
            "x": self.publish_x,
            "twitter": self.publish_x,
            "facebook": self.publish_facebook,
            "instagram": self.publish_instagram,
        }
        handler = handlers.get(platform_key)
        if not handler:
            return PublishResult(False, platform, f"Unsupported platform: {platform}")
        return handler(content, extra=extra or {})

    def publish_linkedin(
        self, content: str, *, extra: dict[str, Any] | None = None
    ) -> PublishResult:
        token = config.linkedin_token
        if not token:
            return PublishResult(
                False,
                "LinkedIn",
                "LinkedIn token missing. Add it in Settings.",
            )
        # Stub: simulate success and log intent. Replace with LinkedIn UGC Posts API.
        logger.info("LinkedIn publish queued (%d chars).", len(content))
        return PublishResult(
            True,
            "LinkedIn",
            "Queued / simulated publish (connect LinkedIn UGC API for live posting).",
            {"preview": content[:160], "extra": extra or {}},
        )

    def publish_x(
        self, content: str, *, extra: dict[str, Any] | None = None
    ) -> PublishResult:
        token = config.x_token
        if not token:
            return PublishResult(False, "X", "X token missing. Add it in Settings.")
        if len(content) > 280:
            return PublishResult(False, "X", "Content exceeds 280 characters.")
        logger.info("X publish queued (%d chars).", len(content))
        return PublishResult(
            True,
            "X",
            "Queued / simulated publish (connect X API v2 for live posting).",
            {"preview": content, "extra": extra or {}},
        )

    def publish_facebook(
        self, content: str, *, extra: dict[str, Any] | None = None
    ) -> PublishResult:
        token = config.facebook_token
        if not token:
            return PublishResult(
                False, "Facebook", "Facebook token missing. Add it in Settings."
            )
        logger.info("Facebook publish queued (%d chars).", len(content))
        return PublishResult(
            True,
            "Facebook",
            "Queued / simulated publish (connect Graph API for live posting).",
            {"preview": content[:160], "extra": extra or {}},
        )

    def publish_instagram(
        self, content: str, *, extra: dict[str, Any] | None = None
    ) -> PublishResult:
        token = config.instagram_token
        if not token:
            return PublishResult(
                False, "Instagram", "Instagram token missing. Add it in Settings."
            )
        logger.info("Instagram publish queued (%d chars).", len(content))
        return PublishResult(
            True,
            "Instagram",
            "Queued / simulated publish (connect Instagram Graph API for live posting).",
            {"preview": content[:160], "extra": extra or {}},
        )

    def health_check(self) -> dict[str, bool]:
        """Report which platform tokens are configured."""
        return {
            "LinkedIn": bool(config.linkedin_token),
            "X": bool(config.x_token),
            "Facebook": bool(config.facebook_token),
            "Instagram": bool(config.instagram_token),
            "OpenAI": bool(config.openai_api_key),
            "NVIDIA": bool(config.nvidia_api_key),
        }

    def ping_openai(self) -> bool:
        """Lightweight connectivity probe (models list)."""
        if not config.openai_api_key:
            return False
        try:
            url = config.openai_base_url.rstrip("/") + "/models"
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {config.openai_api_key}"},
                timeout=15,
            )
            return resp.status_code < 500
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI ping failed: %s", exc)
            return False


publisher = SocialPublisher()
