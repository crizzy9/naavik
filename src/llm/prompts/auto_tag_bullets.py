"""auto_tag_bullets — Wave 6 wires this end-to-end.

Per BACKEND.md § M.3. Auto-generates 9-tag set per bullet during resume
parse + on each new bullet.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm.base import LLMProvider

PROMPT = """Tag this resume bullet with the relevant tags from the 9-tag vocabulary:
ai-ml, backend, frontend, devops, data-eng, genai, leadership, platform, product.

Bullet:
{text}

Return BulletTags with `tags` (1–4 tags). Pick only tags that are clearly
demonstrated by the bullet's content; don't pad.
"""


class BulletTags(BaseModel):
    tags: list[str]


async def auto_tag_bullets(provider: LLMProvider, *, text: str) -> BulletTags:
    rendered = PROMPT.format(text=text)
    result = await provider.structured(rendered, BulletTags, max_tokens=256)
    return BulletTags.model_validate(result.value)
