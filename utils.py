"""
Shared utilities: logging, text helpers, quality checks, and export helpers.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOGS_DIR, POSTS_DIR

# Module-level lock for thread-safe logging setup
_log_lock = threading.Lock()
_logger: logging.Logger | None = None

# Common AI clichés to flag / strip
AI_CLICHES: tuple[str, ...] = (
    "in today's fast-paced world",
    "unlock your potential",
    "game-changing",
    "revolutionary",
    "as an ai",
    "delve into",
    "leverage synergies",
    "cutting-edge",
    "paradigm shift",
    "in conclusion",
)


def get_logger(name: str = "ai_social") -> logging.Logger:
    """Return a configured application logger (singleton-style)."""
    global _logger
    with _log_lock:
        if _logger is not None:
            return _logger.getChild(name) if name != "ai_social" else _logger

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("ai_social")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = logging.FileHandler(
            LOGS_DIR / "app.log", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        _logger = logger
        return logger if name == "ai_social" else logger.getChild(name)


def timestamp_slug() -> str:
    """Filesystem-safe timestamp string."""
    return datetime.now().strftime("%Y_%m_%d_%H%M%S")


def today_slug() -> str:
    """Date-only slug for filenames."""
    return datetime.now().strftime("%Y_%m_%d")


def word_count(text: str) -> int:
    """Count words in text."""
    return len(re.findall(r"\b\w+\b", text or ""))


def char_count(text: str) -> int:
    """Character count (includes spaces)."""
    return len(text or "")


def normalize_hashtag(tag: str) -> str:
    """Ensure hashtag starts with # and has no spaces."""
    tag = (tag or "").strip()
    if not tag:
        return ""
    tag = tag if tag.startswith("#") else f"#{tag}"
    return re.sub(r"\s+", "", tag)


def dedupe_hashtags(tags: list[str] | None) -> list[str]:
    """Remove duplicate hashtags (case-insensitive) while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags or []:
        tag = normalize_hashtag(str(raw))
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
    return result


def strip_ai_cliches(text: str) -> str:
    """Gently remove known AI cliché phrases (case-insensitive)."""
    cleaned = text or ""
    for phrase in AI_CLICHES:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        cleaned = pattern.sub("", cleaned)
    # Collapse leftover double spaces / blank lines
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def light_grammar_fix(text: str) -> str:
    """
    Lightweight grammar / spacing fixes without an external grammar API.

    Real grammar models can be plugged in later; this keeps content clean.
    """
    if not text:
        return ""
    fixed = text.replace(" ,", ",").replace(" .", ".")
    fixed = re.sub(r" +", " ", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    # Capitalize first letter of each paragraph
    paragraphs = []
    for para in fixed.split("\n"):
        if para.strip():
            s = para.strip()
            paragraphs.append(s[0].upper() + s[1:] if len(s) > 1 else s.upper())
        else:
            paragraphs.append("")
    return "\n".join(paragraphs)


def flesch_reading_ease(text: str) -> float:
    """
    Approximate Flesch Reading Ease score.
    Higher = easier to read (typical social posts: 60–80).
    """
    sentences = max(len(re.findall(r"[.!?]+", text)) or 1, 1)
    words = max(word_count(text), 1)
    syllables = 0
    for word in re.findall(r"\b[a-zA-Z]+\b", text.lower()):
        syllables += max(_count_syllables(word), 1)
    score = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    return round(max(0.0, min(100.0, score)), 1)


def _count_syllables(word: str) -> int:
    word = word.lower()
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def uniqueness_score(text: str) -> float:
    """
    Rough uniqueness heuristic based on token diversity (0–100).
    """
    tokens = re.findall(r"\b\w+\b", (text or "").lower())
    if not tokens:
        return 0.0
    unique = len(set(tokens))
    ratio = unique / len(tokens)
    # Penalize very short spammy repeats
    penalty = 0.0
    if len(tokens) > 20:
        # Bigram repetition penalty
        bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
        if bigrams:
            bigram_ratio = len(set(bigrams)) / len(bigrams)
            penalty = max(0.0, 0.25 * (1 - bigram_ratio))
    return round(max(0.0, min(100.0, (ratio - penalty) * 100)), 1)


def enforce_x_limit(content: str, hashtags: list[str], limit: int = 280) -> tuple[str, list[str]]:
    """
    Ensure X post (content + hashtags) stays within character limit.
    Truncates content first; drops hashtags as a last resort.
    """
    tags = dedupe_hashtags(hashtags)[:2]
    content = (content or "").strip()
    tag_str = (" " + " ".join(tags)) if tags else ""
    while tags and len(content) + len(tag_str) > limit:
        tags = tags[:-1]
        tag_str = (" " + " ".join(tags)) if tags else ""
    available = limit - len(tag_str)
    if len(content) > available:
        content = content[: max(0, available - 1)].rstrip() + "…"
    return content, tags


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize a generated social payload.
    Raises ValueError on hard failures.
    """
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")

    required = ["topic", "linkedin", "x", "facebook", "instagram", "image_prompt"]
    for key in required:
        if key not in payload:
            raise ValueError(f"Missing required key: {key}")

    # Normalize platform blocks
    for platform in ("linkedin", "x", "facebook", "instagram"):
        block = payload.get(platform) or {}
        if not isinstance(block, dict):
            raise ValueError(f"{platform} must be an object.")
        if "hashtags" in block:
            block["hashtags"] = dedupe_hashtags(block.get("hashtags") or [])
        for field in ("content", "caption", "title"):
            if field in block and isinstance(block[field], str):
                block[field] = light_grammar_fix(strip_ai_cliches(block[field]))
        payload[platform] = block

    # X limit
    x_block = payload["x"]
    x_content = x_block.get("content", "")
    x_tags = x_block.get("hashtags", [])
    x_content, x_tags = enforce_x_limit(x_content, x_tags)
    payload["x"]["content"] = x_content
    payload["x"]["hashtags"] = x_tags

    if "keywords" in payload:
        seen: set[str] = set()
        clean_kw: list[str] = []
        for kw in payload.get("keywords") or []:
            k = str(kw).strip()
            if k and k.lower() not in seen:
                seen.add(k.lower())
                clean_kw.append(k)
        payload["keywords"] = clean_kw

    payload["image_prompt"] = light_grammar_fix(
        strip_ai_cliches(str(payload.get("image_prompt", "")))
    )
    return payload


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from an LLM response."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model response.")

    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(text[start : end + 1])


def safe_json_dumps(data: Any, indent: int = 2) -> str:
    """Pretty-print JSON with UTF-8 characters preserved."""
    return json.dumps(data, ensure_ascii=False, indent=indent)


def export_json(payload: dict[str, Any], filename: str | None = None) -> Path:
    """Save payload as JSON under posts/."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTS_DIR / (filename or f"social_post_{timestamp_slug()}.json")
    path.write_text(safe_json_dumps(payload) + "\n", encoding="utf-8")
    return path


def export_markdown(payload: dict[str, Any], filename: str | None = None) -> Path:
    """Save payload as Markdown under posts/."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTS_DIR / (filename or f"social_post_{timestamp_slug()}.md")
    md = payload_to_markdown(payload)
    path.write_text(md, encoding="utf-8")
    return path


def export_txt(payload: dict[str, Any], filename: str | None = None) -> Path:
    """Save payload as plain text under posts/."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    path = POSTS_DIR / (filename or f"social_post_{timestamp_slug()}.txt")
    path.write_text(payload_to_txt(payload), encoding="utf-8")
    return path


def payload_to_markdown(payload: dict[str, Any]) -> str:
    """Convert a post payload into readable Markdown."""
    lines = [
        f"# {payload.get('title') or payload.get('topic') or 'Social Post'}",
        "",
        f"**Topic:** {payload.get('topic', '')}",
        "",
        f"**Summary:** {payload.get('summary', '')}",
        "",
        "## LinkedIn",
        "",
        payload.get("linkedin", {}).get("title", ""),
        "",
        payload.get("linkedin", {}).get("content", ""),
        "",
        " ".join(payload.get("linkedin", {}).get("hashtags", [])),
        "",
        "## X (Twitter)",
        "",
        payload.get("x", {}).get("content", ""),
        "",
        " ".join(payload.get("x", {}).get("hashtags", [])),
        "",
        "## Facebook",
        "",
        payload.get("facebook", {}).get("content", ""),
        "",
        " ".join(payload.get("facebook", {}).get("hashtags", [])),
        "",
        "## Instagram",
        "",
        payload.get("instagram", {}).get("caption", ""),
        "",
        " ".join(payload.get("instagram", {}).get("hashtags", [])),
        "",
        "## Image Prompt",
        "",
        payload.get("image_prompt", ""),
        "",
        "## Keywords",
        "",
        ", ".join(payload.get("keywords", [])),
        "",
        f"**CTA:** {payload.get('cta', '')}",
        "",
    ]
    return "\n".join(lines)


def payload_to_txt(payload: dict[str, Any]) -> str:
    """Convert a post payload into plain text."""
    md = payload_to_markdown(payload)
    # Simple markdown stripping
    txt = re.sub(r"^#+\s*", "", md, flags=re.MULTILINE)
    txt = re.sub(r"\*\*(.*?)\*\*", r"\1", txt)
    return txt


def readability_label(score: float) -> str:
    """Human label for Flesch score."""
    if score >= 80:
        return "Very easy"
    if score >= 60:
        return "Easy"
    if score >= 50:
        return "Fairly easy"
    if score >= 30:
        return "Difficult"
    return "Very difficult"


def quality_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a quality report for UI display."""
    combined = " ".join(
        [
            payload.get("linkedin", {}).get("content", ""),
            payload.get("x", {}).get("content", ""),
            payload.get("facebook", {}).get("content", ""),
            payload.get("instagram", {}).get("caption", ""),
        ]
    )
    x_full = payload.get("x", {}).get("content", "")
    tags = payload.get("x", {}).get("hashtags", [])
    if tags:
        x_full = f"{x_full} {' '.join(tags)}"
    flesch = flesch_reading_ease(combined)
    return {
        "x_chars": char_count(x_full),
        "x_ok": char_count(x_full) <= 280,
        "readability": flesch,
        "readability_label": readability_label(flesch),
        "uniqueness": uniqueness_score(combined),
        "word_count": word_count(combined),
    }
