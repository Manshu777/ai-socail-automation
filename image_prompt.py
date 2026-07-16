"""
Image prompt helpers — enhance and structure visual prompts for AI image tools.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImagePromptSpec:
    """Structured description for a social-media-ready image prompt."""

    scene: str
    lighting: str = "soft natural window light"
    composition: str = "clean balanced composition with negative space"
    lens: str = "50mm lens, shallow depth of field"
    mood: str = "calm, premium, trustworthy"
    color_palette: str = "muted blues, warm neutrals, soft contrast"
    camera_angle: str = "slight three-quarter eye-level angle"
    style: str = "ultra realistic editorial photography, high quality, sharp detail"
    extras: str = "no text, no logos, no watermarks, no UI overlays"

    def to_prompt(self) -> str:
        """Render a single-line professional image prompt."""
        parts = [
            self.scene,
            self.lighting,
            self.composition,
            self.lens,
            f"mood: {self.mood}",
            f"color palette: {self.color_palette}",
            self.camera_angle,
            self.style,
            self.extras,
        ]
        return ", ".join(p.strip().rstrip(",") for p in parts if p and p.strip())


def enhance_image_prompt(raw: str, *, topic: str = "", industry: str = "") -> str:
    """
    Ensure a model-produced image prompt covers key visual controls.

    If the raw prompt already looks detailed, we lightly append missing cues.
    """
    text = (raw or "").strip()
    lower = text.lower()

    if not text:
        spec = ImagePromptSpec(
            scene=(
                f"A professional workspace scene inspired by {topic or 'modern work'} "
                f"in the {industry or 'business'} field"
            )
        )
        return spec.to_prompt()

    additions: list[str] = []
    if "light" not in lower and "lighting" not in lower:
        additions.append("soft natural lighting")
    if "composition" not in lower and "framed" not in lower:
        additions.append("clean balanced composition")
    if "lens" not in lower and "mm" not in lower:
        additions.append("50mm lens, shallow depth of field")
    if "mood" not in lower:
        additions.append("calm premium mood")
    if "angle" not in lower and "perspective" not in lower:
        additions.append("eye-level three-quarter camera angle")
    if "realistic" not in lower and "photo" not in lower:
        additions.append("ultra realistic photography, high quality")
    if "no text" not in lower and "without text" not in lower:
        additions.append("no text, no logos, no watermarks")

    if additions:
        text = text.rstrip("., ") + ", " + ", ".join(additions)
    return text


def fallback_image_prompt(topic: str, industry: str = "General") -> str:
    """Deterministic fallback when the LLM omits an image prompt."""
    return ImagePromptSpec(
        scene=(
            f"Cinematic still of a thoughtful professional moment related to "
            f"'{topic}', set in a {industry.lower()} context — desk, soft props, "
            f"and subtle environmental storytelling"
        ),
        lighting="golden-hour side light with gentle shadows",
        composition="subject slightly off-center, breathing room on one side",
        lens="35mm and 50mm hybrid look, soft bokeh",
        mood="hopeful, grounded, human",
        color_palette="warm wood, soft charcoal, muted teal accents",
        camera_angle="slightly elevated three-quarter view",
    ).to_prompt()
