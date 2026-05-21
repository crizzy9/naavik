"""Burstiness validator — plan 66 (0.3.1) § T5.

Computes word-count std-dev across a batch of bullets. Below threshold
(default 6), the batch reads like AI: too-uniform sentence lengths.
Returns the most-uniform offender so the orchestrator can regenerate
one bullet with explicit length-variance instructions.

Cap at one regenerate per bundle — the marginal-cost-vs-benefit sweet
spot. Multi-retry blows the cost budget without proportional gain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean, pstdev

_WORD_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z'-]+")

# Threshold from research § T1-C — std-dev ≥ 6 reads as human (variance);
# below reads as AI (uniformity).
BURSTINESS_THRESHOLD = 6.0


@dataclass(slots=True)
class BurstinessReport:
    """Per-batch burstiness signal.

    `passed=True` iff std-dev ≥ BURSTINESS_THRESHOLD. `worst_offender_idx`
    is the index of the bullet closest to the mean (lowest variance
    contribution); regenerate THAT one to widen the distribution.
    """

    passed: bool
    std_dev: float
    mean_words: float
    word_counts: list[int]
    worst_offender_idx: int | None = None
    suggested_target: str = ""  # "short" or "long" or "" if passed
    suggested_target_words: int | None = None


def _word_count(text: str) -> int:
    return len(_WORD_TOKEN.findall(text or ""))


def check_and_score(bullets: list[str]) -> BurstinessReport:
    """Compute burstiness over `bullets`. Identify worst offender if below.

    Returns a passing report when there's <2 bullets (no variance signal).
    """
    word_counts = [_word_count(b) for b in bullets]
    n = len(word_counts)
    if n < 2:
        return BurstinessReport(
            passed=True,
            std_dev=0.0,
            mean_words=float(word_counts[0]) if word_counts else 0.0,
            word_counts=word_counts,
        )
    mu = mean(word_counts)
    std = pstdev(word_counts)
    if std >= BURSTINESS_THRESHOLD:
        return BurstinessReport(
            passed=True,
            std_dev=round(std, 2),
            mean_words=round(mu, 2),
            word_counts=word_counts,
        )

    # Find the bullet closest to the mean — that's the most-uniform offender.
    deviations = [abs(wc - mu) for wc in word_counts]
    worst_idx = deviations.index(min(deviations))

    # Suggest a target: pull AWAY from the mean. If mean is small, suggest
    # longer; if mean is large, suggest shorter.
    if mu <= 14:
        suggested_target = "long"
        suggested_target_words = max(int(mu + std + 8), 22)
    else:
        suggested_target = "short"
        suggested_target_words = max(int(mu - std - 4), 6)

    return BurstinessReport(
        passed=False,
        std_dev=round(std, 2),
        mean_words=round(mu, 2),
        word_counts=word_counts,
        worst_offender_idx=worst_idx,
        suggested_target=suggested_target,
        suggested_target_words=suggested_target_words,
    )
