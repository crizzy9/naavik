"""auto_tag_bullets — Wave 6 wires this end-to-end.

Per BACKEND.md § M.3. Auto-generates 9-tag set per bullet during resume
parse + on each new bullet.
"""

from __future__ import annotations

from pydantic import BaseModel

PROMPT = """Tag this resume bullet with the relevant tags from the 9-tag vocabulary:
ai-ml, backend, frontend, devops, data-eng, genai, leadership, platform, product.

Bullet:
{text}

Return BulletTags with `tags` (1–4 tags). Pick only tags that are clearly
demonstrated by the bullet's content; don't pad.
"""


class BulletTags(BaseModel):
    tags: list[str]
