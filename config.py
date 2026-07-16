"""
Application configuration and environment loading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Project root (directory containing this file)
ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
DATABASE_DIR = ROOT_DIR / "database"
POSTS_DIR = ROOT_DIR / "posts"
IMAGES_DIR = POSTS_DIR / "images"
LOGS_DIR = ROOT_DIR / "logs"
ASSETS_DIR = ROOT_DIR / "assets"
DB_PATH = DATABASE_DIR / "social_automation.db"

# Ensure critical folders exist
for _dir in (DATABASE_DIR, POSTS_DIR, IMAGES_DIR, LOGS_DIR, ASSETS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_PATH)

# Supported industries, tones, and languages for UI dropdowns
INDUSTRIES: list[str] = [
    "Technology",
    "Marketing",
    "Finance",
    "Healthcare",
    "Education",
    "E-commerce",
    "SaaS",
    "Real Estate",
    "Fitness",
    "Food & Hospitality",
    "Design",
    "Consulting",
    "General / Lifestyle",
]

TONES: list[str] = [
    "Professional",
    "Casual",
    "Friendly",
    "Inspirational",
    "Educational",
    "Conversational",
    "Authoritative",
]

LANGUAGES: list[str] = [
    "English",
    "Spanish",
    "French",
    "German",
    "Portuguese",
    "Hindi",
    "Arabic",
]

PLATFORMS: list[str] = ["LinkedIn", "X", "Facebook", "Instagram"]

# Visual theme
COLORS: dict[str, str] = {
    "bg": "#0f1115",
    "sidebar": "#151821",
    "card": "#1c2030",
    "card_hover": "#242938",
    "border": "#2a3144",
    "accent": "#5b8def",
    "accent_hover": "#4a7de0",
    "text": "#e8eaef",
    "text_muted": "#9aa3b5",
    "success": "#3ecf8e",
    "warning": "#f5a524",
    "danger": "#f06565",
    "input": "#12151e",
}


@dataclass
class AppConfig:
    """Runtime configuration loaded from environment variables."""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.1-70b-instruct"
    linkedin_token: str = ""
    facebook_token: str = ""
    instagram_token: str = ""
    x_token: str = ""
    use_nvidia_fallback: bool = True
    default_word_count: int = 180
    dark_mode: bool = True
    auto_save: bool = True
    emoji_enabled: bool = False
    tone_mode: str = "Professional"  # Professional | Casual
    auto_generate_image: bool = True
    image_model: str = "dall-e-3"
    image_quality: str = "standard"  # standard | hd
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create config from current environment / .env file."""
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            openai_base_url=os.getenv(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).strip(),
            nvidia_api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
            nvidia_base_url=os.getenv(
                "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ).strip(),
            nvidia_model=os.getenv(
                "NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"
            ).strip(),
            linkedin_token=os.getenv("LINKEDIN_TOKEN", "").strip(),
            facebook_token=os.getenv("FACEBOOK_TOKEN", "").strip(),
            instagram_token=os.getenv("INSTAGRAM_TOKEN", "").strip(),
            x_token=os.getenv("X_TOKEN", "").strip(),
            use_nvidia_fallback=os.getenv("USE_NVIDIA_FALLBACK", "true").lower()
            in {"1", "true", "yes"},
            default_word_count=int(os.getenv("DEFAULT_WORD_COUNT", "180")),
            dark_mode=os.getenv("DARK_MODE", "true").lower() in {"1", "true", "yes"},
            auto_save=os.getenv("AUTO_SAVE", "true").lower() in {"1", "true", "yes"},
            emoji_enabled=os.getenv("EMOJI_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            tone_mode=os.getenv("TONE_MODE", "Professional").strip() or "Professional",
            auto_generate_image=os.getenv("AUTO_GENERATE_IMAGE", "true").lower()
            in {"1", "true", "yes"},
            image_model=os.getenv("IMAGE_MODEL", "dall-e-3").strip() or "dall-e-3",
            image_quality=os.getenv("IMAGE_QUALITY", "standard").strip() or "standard",
        )

    def reload(self) -> None:
        """Reload values from disk after .env updates."""
        load_dotenv(ENV_PATH, override=True)
        refreshed = AppConfig.from_env()
        for key, value in refreshed.__dict__.items():
            setattr(self, key, value)


def save_env(values: dict[str, str]) -> None:
    """
    Persist key/value pairs into the project .env file.

    Existing keys are updated; unknown keys are appended.
    """
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, val = stripped.partition("=")
            existing[key.strip()] = val.strip().strip('"').strip("'")

    existing.update({k: str(v) for k, v in values.items() if v is not None})

    lines = [
        "# AI Social Media Automation — environment configuration",
        "# Generated/updated by the Settings screen. Do not commit secrets.",
        "",
    ]
    preferred_order = [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "NVIDIA_API_KEY",
        "NVIDIA_BASE_URL",
        "NVIDIA_MODEL",
        "USE_NVIDIA_FALLBACK",
        "LINKEDIN_TOKEN",
        "FACEBOOK_TOKEN",
        "INSTAGRAM_TOKEN",
        "X_TOKEN",
        "DEFAULT_WORD_COUNT",
        "DARK_MODE",
        "AUTO_SAVE",
        "EMOJI_ENABLED",
        "TONE_MODE",
        "AUTO_GENERATE_IMAGE",
        "IMAGE_MODEL",
        "IMAGE_QUALITY",
    ]
    written: set[str] = set()
    for key in preferred_order:
        if key in existing:
            lines.append(f"{key}={existing[key]}")
            written.add(key)
    for key, val in existing.items():
        if key not in written:
            lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)


# Singleton used across modules
config = AppConfig.from_env()
