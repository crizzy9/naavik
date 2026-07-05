"""Ethics pre-flight check — plan 66 (0.3.1) § B.6.

Scans the generated resume bullets for claims not grounded in the
candidate's profile. Any bullet whose `source_bullet_id` does not match
a real `Bullet.id` in the candidate's profile gets DROPPED.

The check is best-effort: when in doubt, drop the bullet (favor honesty
over coverage). The audit trail records every dropped bullet so the
user can review what the LLM tried to fabricate.

This is the CORE honesty constraint per plan § A: "Every bullet you
emit must trace to a corpus bullet — if you cannot, drop the bullet."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(slots=True)
class EthicsReport:
    """Pre-flight verdict for a generation bundle.

    `passed=True` iff zero bullets were dropped. `dropped_bullets`
    carries the rationale per dropped bullet so the audit trail can
    surface what fabrication was caught.

    `surface_to_user=True` when `len(dropped) > 2` — the orchestrator
    rejects the bundle and asks the user to review their profile
    (covers the "LLM emitted N fabricated bullets" red-flag case).
    """

    passed: bool
    dropped_bullets: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    surface_to_user: bool = False


def preflight_check(
    selected_bullet_ids: list[int],
    trimmed_lines: dict[int, str],
    available_bullet_ids: set[int],
) -> EthicsReport:
    """Drop any selected bullet whose ID isn't in the candidate's profile.

    Bullet IDs that don't appear in `available_bullet_ids` (the profile's
    actual `Bullet.id` set) are presumed LLM-fabricated and removed from
    `selected_bullet_ids` + `trimmed_lines`. The caller continues with
    the surviving bullets.

    `flags` may add additional heuristics in future iterations (e.g.
    sentence patterns that look like over-claiming); v1 ships the
    minimum honest signal.
    """
    dropped: list[dict] = []
    surviving: list[int] = []
    for bid in selected_bullet_ids:
        if bid in available_bullet_ids:
            surviving.append(bid)
        else:
            dropped.append(
                {
                    "bullet_id": bid,
                    "trimmed_line": trimmed_lines.get(bid, ""),
                    "reason": "bullet_id not in candidate profile",
                }
            )

    selected_bullet_ids[:] = surviving
    for d in dropped:
        trimmed_lines.pop(d["bullet_id"], None)

    return EthicsReport(
        passed=len(dropped) == 0,
        dropped_bullets=dropped,
        flags=[],
        surface_to_user=len(dropped) > 2,
    )
