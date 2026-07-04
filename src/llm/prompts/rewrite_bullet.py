"""rewrite_bullet — style-directed bullet rewrites for the profile editor.

The bullet editor modal's "Rewrite with AI" (2026-07): the user picks a
style, the model returns 2-3 alternative phrasings plus a one-line note on
what it changed. Variants render as clickable cards; nothing persists until
the user picks one and Saves. Replaces the old trim_bullet@160 wiring that
returned already-short bullets unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel

# Style key → instruction fragment interpolated into PROMPT. Keys double as
# the `rewrite_style` form values submitted by the modal's radio chips.
STYLES: dict[str, str] = {
    "punchier": (
        "Lead with a forceful verb, cut hedging and filler, and make the "
        "impact land in the first few words."
    ),
    "tighter": (
        "Say the same thing in noticeably fewer words. Drop redundant "
        "context and qualifiers; keep every fact."
    ),
    "more-technical": (
        "Foreground the concrete technologies, systems, and methods already "
        "mentioned or clearly implied; drop marketing gloss."
    ),
    "metric-forward": (
        "Restructure so the quantified result leads the line. Keep every "
        "number exactly as written; never invent or extrapolate metrics."
    ),
}

DEFAULT_STYLE = "punchier"

PROMPT = """Rewrite this resume bullet. Style: {style} — {style_guidance}

Original:
{text}

Rules:
- Never invent facts, numbers, technologies, or scope that the original does not state.
- Each version must read as ONE resume line (at most {target_chars} characters).
- Give 2-3 versions that differ in structure or emphasis, not just synonyms.
- `note` is one short line telling the user what you changed and why.

Return BulletRewrite with `variants` (2-3 strings) and `note`.
"""


# OpenAI strict mode (`llm/openai.py:_to_strict_schema`): all fields
# required, no defaults.
class BulletRewrite(BaseModel):
    variants: list[str]
    note: str
