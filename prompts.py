"""
System and user prompt templates for social content generation.
"""

from __future__ import annotations

SYSTEM_PROMPT = """
You are an expert Social Media Content Strategist, Copywriter, and Marketing Writer.

Write content that sounds like a real experienced human wrote it.
Never sound robotic. Never sound like an AI assistant.

Rules:
- Use simple English and short sentences.
- Friendly, clear, trustworthy tone.
- Professional when needed.
- Include a personal insight, observation, or lesson when it fits.
- Educate, inspire, or provide practical value.
- Encourage discussion with a natural question or CTA.
- Never use AI clichés such as:
  "In today's fast-paced world", "Unlock your potential", "Game-changing",
  "Revolutionary", "As an AI", "Delve into", "Leverage synergies",
  "Cutting-edge", "Paradigm shift".
- Do not overuse emojis. Only include emojis if explicitly allowed.
- Never keyword-stuff. Place keywords naturally.
- Original content only. Never copy existing posts.

Platform guidance:
- LinkedIn: 150–300 words. Hook → insight/story → practical takeaway → question.
  Professional tone. Title + content + 2–5 hashtags.
- X (Twitter): max 280 characters TOTAL including hashtags. One clear idea.
  Strong hook. Optional CTA. 1–2 hashtags max.
- Facebook: 100–220 words. Conversational. Encourage comments. 3–5 hashtags.
- Instagram: 80–180 words caption. First line grabs attention. Use short lines and spacing.
  End with CTA. 5–10 hashtags.

Also produce:
- One professional image_prompt (scene, lighting, composition, lens, mood,
  color palette, camera angle, ultra realistic). No text/logos in the image.
- SEO keywords (array)
- One CTA string
- A short title
- A short summary (1–2 sentences)

Return ONLY valid JSON with this exact shape:
{
  "topic": "",
  "title": "",
  "summary": "",
  "cta": "",
  "linkedin": {"title": "", "content": "", "hashtags": []},
  "x": {"content": "", "hashtags": []},
  "facebook": {"content": "", "hashtags": []},
  "instagram": {"caption": "", "hashtags": []},
  "image_prompt": "",
  "keywords": []
}
""".strip()


def build_generation_prompt(
    topic: str,
    *,
    industry: str = "General / Lifestyle",
    tone: str = "Professional",
    language: str = "English",
    platforms: list[str] | None = None,
    word_count_target: int = 180,
    emoji_enabled: bool = False,
    tone_mode: str = "Professional",
) -> str:
    """Build the user prompt for full multi-platform generation."""
    selected = platforms or ["LinkedIn", "X", "Facebook", "Instagram"]
    emoji_rule = (
        "You may use 1–2 subtle emojis where natural."
        if emoji_enabled
        else "Do not use emojis."
    )
    mode_rule = (
        "Lean professional: polished, credible, workplace-appropriate."
        if tone_mode.lower().startswith("pro")
        else "Lean casual: relaxed, conversational, still clear and human."
    )
    return f"""
Create original social media content for this request.

Topic: {topic}
Industry: {industry}
Tone: {tone}
Tone mode: {tone_mode} — {mode_rule}
Language: {language}
Platforms to optimize for: {", ".join(selected)}
Approx word budget for long-form posts (LinkedIn / Facebook / Instagram): ~{word_count_target} words
Emoji policy: {emoji_rule}

Requirements:
- Sound human and trustworthy.
- Platform-optimized lengths and structure.
- Include actionable advice where it fits.
- Distinct CTAs across platforms when possible.
- Generate hashtags that are relevant (industry + topic + community). No spam tags.
- Image prompt must be ultra realistic photography style (unless the topic clearly suggests otherwise).

Return ONLY the JSON object. No markdown. No commentary.
""".strip()


def build_rewrite_prompt(
    payload_json: str,
    *,
    instruction: str = "Rewrite to sound more natural and human.",
    platforms: list[str] | None = None,
) -> str:
    """Build a rewrite prompt around an existing payload."""
    selected = platforms or ["LinkedIn", "X", "Facebook", "Instagram"]
    return f"""
Rewrite the following social content.

Instruction: {instruction}
Focus platforms: {", ".join(selected)}

Keep the same JSON schema.
Improve clarity, remove robotic wording, preserve meaning.
Ensure X stays within 280 characters including hashtags.

Existing content JSON:
{payload_json}

Return ONLY the JSON object.
""".strip()


def build_hashtag_prompt(topic: str, industry: str, platform: str) -> str:
    """Prompt for standalone hashtag generation."""
    counts = {
        "LinkedIn": "2-5",
        "X": "1-2",
        "Facebook": "3-5",
        "Instagram": "5-10",
    }
    count = counts.get(platform, "3-5")
    return f"""
Generate {count} relevant hashtags for:
Topic: {topic}
Industry: {industry}
Platform: {platform}

Rules: no spam, mix industry/community/topic tags, return JSON:
{{"hashtags": ["#Example"]}}
""".strip()
