"""trim_bullet — Wave 6 wires this end-to-end (apply-time trim).

Per BACKEND.md § K.4. Trims a long-form bullet to one resume line while
preserving numbers + verbs.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Trim this bullet to one resume line of at most {target_chars} characters.

Original:
{text}

Preserve: every number, every verb, the most concrete result. Drop:
filler adjectives, redundant context. Return TrimmedBullet with `trimmed`
(the one-line version) and `dropped_phrases` (what you removed).
"""


class TrimmedBullet(BaseModel):
    trimmed: str
    dropped_phrases: list[str] = []


async def trim_bullet(
    provider: LLMProvider,
    *,
    text: str,
    target_chars: int = 120,
) -> TrimmedBullet:
    rendered = PROMPT.format(text=text, target_chars=target_chars)
    result = await provider.structured(rendered, TrimmedBullet, max_tokens=512)
    return TrimmedBullet.model_validate(result.value)
