"""
Auto image generation for social posts.

Primary: OpenAI Images API (DALL·E)
Fallback: local Pillow poster so the app still works without an API key
"""

from __future__ import annotations

import base64
import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

from config import POSTS_DIR, config
from utils import get_logger, timestamp_slug

logger = get_logger("image_generator")

_api_lock = threading.Lock()
IMAGES_DIR = POSTS_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ImageResult:
    """Result of an image generation run."""

    path: Path
    provider: str
    prompt: str
    width: int
    height: int


class ImageGenerator:
    """Generate square social-ready images from text prompts."""

    def __init__(self) -> None:
        self.timeout = 120
        self.size = "1024x1024"

    def generate(
        self,
        prompt: str,
        *,
        topic: str = "",
        filename: str | None = None,
        force_local: bool = False,
    ) -> ImageResult:
        """
        Generate an image and save it under posts/images/.

        Uses OpenAI when a key is available; otherwise builds a local poster.
        """
        prompt = (prompt or "").strip()
        if not prompt and not topic:
            raise ValueError("Image prompt (or topic) is required.")
        if not prompt:
            prompt = (
                f"Ultra realistic editorial photo about {topic}, "
                "soft natural light, clean composition, no text, no logos"
            )

        filename = filename or f"post_image_{timestamp_slug()}.png"
        out_path = IMAGES_DIR / filename

        if not force_local and config.openai_api_key:
            try:
                return self._openai_image(prompt, out_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI image failed, using local poster: %s", exc)

        return self._local_poster(prompt=prompt, topic=topic, out_path=out_path)

    def _openai_image(self, prompt: str, out_path: Path) -> ImageResult:
        """Call OpenAI Images API (DALL·E)."""
        model = getattr(config, "image_model", None) or "dall-e-3"
        url = config.openai_base_url.rstrip("/") + "/images/generations"
        headers = {
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        }
        # Keep prompt within practical length for DALL·E
        safe_prompt = prompt[:3800]
        body: dict[str, Any] = {
            "model": model,
            "prompt": safe_prompt,
            "size": self.size,
            "n": 1,
        }
        # DALL·E 3 supports quality / response format options
        if model.startswith("dall-e-3"):
            body["quality"] = getattr(config, "image_quality", "standard") or "standard"
            body["response_format"] = "b64_json"

        with _api_lock:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")

        data = resp.json()
        item = data["data"][0]
        if "b64_json" in item:
            raw = base64.b64decode(item["b64_json"])
            out_path.write_bytes(raw)
        elif "url" in item:
            img_resp = requests.get(item["url"], timeout=self.timeout)
            img_resp.raise_for_status()
            out_path.write_bytes(img_resp.content)
        else:
            raise RuntimeError("Unexpected image API response shape.")

        with Image.open(out_path) as im:
            width, height = im.size

        logger.info("OpenAI image saved → %s", out_path)
        return ImageResult(
            path=out_path,
            provider="openai-dalle",
            prompt=prompt,
            width=width,
            height=height,
        )

    def _local_poster(self, *, prompt: str, topic: str, out_path: Path) -> ImageResult:
        """
        Create a clean social poster locally with Pillow.

        Useful for offline testing when no OpenAI image credits are set.
        """
        width = height = 1080
        img = Image.new("RGB", (width, height), "#12151e")
        draw = ImageDraw.Draw(img)

        # Soft gradient bands
        for y in range(height):
            t = y / height
            r = int(18 + 30 * t)
            g = int(22 + 40 * t)
            b = int(40 + 55 * (1 - t))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Accent card
        margin = 70
        card = [margin, margin + 80, width - margin, height - margin - 60]
        draw.rounded_rectangle(card, radius=36, fill="#1c2030")
        draw.rounded_rectangle(card, radius=36, outline="#5b8def", width=3)

        title = (topic or "Social Post").strip()
        if len(title) > 70:
            title = title[:67] + "…"

        font_title = self._font(52)
        font_body = self._font(28)
        font_small = self._font(22)

        # Wrap title
        title_lines = self._wrap(title, max_chars=22)
        y = card[1] + 70
        for line in title_lines[:4]:
            draw.text((card[0] + 50, y), line, fill="#e8eaef", font=font_title)
            y += 62

        y += 30
        draw.text(
            (card[0] + 50, y),
            "Auto-generated post image",
            fill="#9aa3b5",
            font=font_body,
        )
        y += 50

        snippet = (prompt or "")[:160].replace("\n", " ")
        for line in self._wrap(snippet, max_chars=36)[:4]:
            draw.text((card[0] + 50, y), line, fill="#9aa3b5", font=font_small)
            y += 34

        # Footer tip
        draw.text(
            (card[0] + 50, card[3] - 70),
            "Add OPENAI_API_KEY for DALL·E photos",
            fill="#5b8def",
            font=font_small,
        )

        img.save(out_path, format="PNG", optimize=True)
        logger.info("Local poster saved → %s", out_path)
        return ImageResult(
            path=out_path,
            provider="local-poster",
            prompt=prompt,
            width=width,
            height=height,
        )

    @staticmethod
    def _font(size: int) -> ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
        for path in candidates:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap(text: str, max_chars: int = 28) -> list[str]:
        words = (text or "").split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines


image_generator = ImageGenerator()
