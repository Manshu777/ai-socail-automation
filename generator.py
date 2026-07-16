"""
LLM-backed content generation (OpenAI primary, NVIDIA NIM optional fallback).
"""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass, field
from typing import Any

import requests

from config import config
from image_prompt import enhance_image_prompt, fallback_image_prompt
from prompts import SYSTEM_PROMPT, build_generation_prompt, build_rewrite_prompt
from utils import (
    dedupe_hashtags,
    extract_json_object,
    get_logger,
    quality_report,
    validate_payload,
)

logger = get_logger("generator")

# Serialize outbound API calls to avoid overwhelming rate limits
_api_lock = threading.Lock()


@dataclass
class GenerationRequest:
    """Inputs for a generation run."""

    topic: str
    industry: str = "General / Lifestyle"
    tone: str = "Professional"
    language: str = "English"
    platforms: list[str] = field(
        default_factory=lambda: ["LinkedIn", "X", "Facebook", "Instagram"]
    )
    word_count: int = 180
    emoji_enabled: bool = False
    tone_mode: str = "Professional"


@dataclass
class GenerationResult:
    """Normalized generation output plus quality metadata."""

    payload: dict[str, Any]
    provider: str
    quality: dict[str, Any]
    raw_text: str = ""


class ContentGenerator:
    """Generate and rewrite multi-platform social content."""

    def __init__(self) -> None:
        self.timeout = 90

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate a full multi-platform payload."""
        topic = (request.topic or "").strip()
        if not topic:
            raise ValueError("Topic is required.")

        user_prompt = build_generation_prompt(
            topic,
            industry=request.industry,
            tone=request.tone,
            language=request.language,
            platforms=request.platforms,
            word_count_target=request.word_count,
            emoji_enabled=request.emoji_enabled,
            tone_mode=request.tone_mode,
        )
        raw, provider = self._chat(SYSTEM_PROMPT, user_prompt)
        payload = self._parse_and_enrich(raw, request)
        quality = quality_report(payload)
        return GenerationResult(
            payload=payload, provider=provider, quality=quality, raw_text=raw
        )

    def rewrite(
        self,
        payload: dict[str, Any],
        *,
        instruction: str = "Rewrite to sound more natural and human.",
        platforms: list[str] | None = None,
    ) -> GenerationResult:
        """Rewrite an existing payload."""
        if not payload:
            raise ValueError("Nothing to rewrite.")
        user_prompt = build_rewrite_prompt(
            json.dumps(payload, ensure_ascii=False),
            instruction=instruction,
            platforms=platforms,
        )
        raw, provider = self._chat(SYSTEM_PROMPT, user_prompt)
        # Reuse industry/tone placeholders for image enrichment
        request = GenerationRequest(
            topic=str(payload.get("topic", "")),
            platforms=platforms or ["LinkedIn", "X", "Facebook", "Instagram"],
        )
        parsed = self._parse_and_enrich(raw, request)
        quality = quality_report(parsed)
        return GenerationResult(
            payload=parsed, provider=provider, quality=quality, raw_text=raw
        )

    def regenerate(self, request: GenerationRequest) -> GenerationResult:
        """Alias for generate — used by UI regenerate button."""
        return self.generate(request)

    def _parse_and_enrich(
        self, raw: str, request: GenerationRequest
    ) -> dict[str, Any]:
        data = extract_json_object(raw)
        data = validate_payload(data)

        # Ensure topic and metadata fields exist
        data["topic"] = data.get("topic") or request.topic
        data.setdefault("title", data["topic"])
        data.setdefault("summary", "")
        data.setdefault("cta", "What do you think?")
        data.setdefault("keywords", [])

        # Image prompt enhancement
        image = data.get("image_prompt") or ""
        if not image.strip():
            image = fallback_image_prompt(request.topic, request.industry)
        data["image_prompt"] = enhance_image_prompt(
            image, topic=request.topic, industry=request.industry
        )

        # Platform pruning if user deselected some
        selected = {p.lower() for p in request.platforms}
        # Always keep keys, but mark unused lightly if needed — UI filters display
        for platform_key in ("linkedin", "x", "facebook", "instagram"):
            block = data.get(platform_key, {})
            if "hashtags" in block:
                block["hashtags"] = dedupe_hashtags(block.get("hashtags") or [])
            data[platform_key] = block

        data["_meta"] = {
            "industry": request.industry,
            "tone": request.tone,
            "language": request.language,
            "platforms": request.platforms,
            "selected": list(selected),
        }
        return data

    def _chat(self, system: str, user: str) -> tuple[str, str]:
        """
        Call OpenAI first; optionally fall back to NVIDIA NIM.
        Returns (content, provider_name).
        """
        errors: list[str] = []

        if config.openai_api_key:
            try:
                text = self._openai_chat(system, user)
                return text, "openai"
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenAI call failed: %s", exc)
                errors.append(f"OpenAI: {exc}")
        else:
            errors.append("OpenAI API key missing.")

        if config.use_nvidia_fallback and config.nvidia_api_key:
            try:
                text = self._nvidia_chat(system, user)
                return text, "nvidia"
            except Exception as exc:  # noqa: BLE001
                logger.warning("NVIDIA NIM call failed: %s", exc)
                errors.append(f"NVIDIA: {exc}")
        else:
            errors.append("NVIDIA NIM unavailable or disabled.")

        # Offline demo fallback so the UI still works without keys
        logger.error("All LLM providers failed: %s", "; ".join(errors))
        return self._offline_demo(user), "offline-demo"

    def _openai_chat(self, system: str, user: str) -> str:
        url = config.openai_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": config.openai_model,
            "temperature": 0.75,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        with _api_lock:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _nvidia_chat(self, system: str, user: str) -> str:
        """NVIDIA NIM OpenAI-compatible chat completions endpoint."""
        url = config.nvidia_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.nvidia_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": config.nvidia_model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with _api_lock:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _offline_demo(self, user_prompt: str) -> str:
        """
        Deterministic demo JSON used when no API keys / providers are available.
        Keeps the app runnable for UI development and demos.
        """
        # Pull a rough topic from the prompt line
        topic = "Working with fewer tools"
        for line in user_prompt.splitlines():
            if line.lower().startswith("topic:"):
                topic = line.split(":", 1)[1].strip() or topic
                break

        payload = {
            "topic": topic,
            "title": f"A practical take on {topic}",
            "summary": f"A human, clear post series about {topic} with simple advice.",
            "cta": "Have you experienced this?",
            "linkedin": {
                "title": f"What {topic} actually looks like at work",
                "content": (
                    f"I used to overcomplicate {topic}.\n\n"
                    "More checklists. More tools. More noise.\n\n"
                    "Then a quieter week taught me something simple: "
                    "focus beats activity. I picked one priority, cut two "
                    "unnecessary meetings, and wrote the next step before "
                    "opening my inbox.\n\n"
                    "If your week feels busy but empty, try this:\n"
                    "• Choose one outcome that matters today\n"
                    "• Protect a deep-work block\n"
                    "• End the day by noting what moved forward\n\n"
                    "Progress rarely needs more dashboards. It needs clearer "
                    "attention.\n\n"
                    "What is one thing you will cut this week?"
                ),
                "hashtags": ["#Productivity", "#WorkLife", "#Focus", "#Leadership"],
            },
            "x": {
                "content": (
                    f"{topic} gets easier when you remove options. "
                    "Pick one goal. Protect one hour. Ship one next step."
                ),
                "hashtags": ["#Productivity", "#Focus"],
            },
            "facebook": {
                "content": (
                    f"Can we talk about {topic} for a moment?\n\n"
                    "I caught myself doing the busy version of progress — "
                    "lots of tabs, little movement. So I tried a smaller "
                    "plan: one outcome, one block of focus, one honest "
                    "check-in at the end of the day.\n\n"
                    "It felt slower at first. Then it felt lighter.\n\n"
                    "Would this work for you, or do you need a different approach?"
                ),
                "hashtags": ["#ProductivityTips", "#WorkLife", "#Focus", "#Mindset"],
            },
            "instagram": {
                "caption": (
                    f"If {topic} feels heavy, shrink the plan.\n\n"
                    "One outcome.\n"
                    "One quiet hour.\n"
                    "One next step you can finish today.\n\n"
                    "Busy weeks feel productive. Clear weeks actually are.\n\n"
                    "Save this for the next overloaded morning."
                ),
                "hashtags": [
                    "#ProductivityTips",
                    "#FocusTime",
                    "#WorkSmarter",
                    "#DailyHabits",
                    "#MindsetShift",
                    "#CareerGrowth",
                    "#DeepWork",
                    "#SimpleLiving",
                ],
            },
            "image_prompt": fallback_image_prompt(topic, "Technology"),
            "keywords": [
                topic.lower(),
                "productivity",
                "focus",
                "deep work",
                "work tips",
            ],
        }
        return json.dumps(payload, ensure_ascii=False)


# Shared generator instance
generator = ContentGenerator()


def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a payload for safe editing."""
    return copy.deepcopy(payload)
