---
description: Apply the architect's option-matrix template — for every non-trivial decision, surface 2+ options across {capability, cost, risk, maintenance, lock-in} and recommend one with rationale. Use whenever a plan needs to lock a design decision, when the user asks "which approach should we use", or when you catch yourself proposing one option without naming alternatives. Triggers on phrases like "option matrix", "trade-off table", "weigh the options", "which approach", "compare alternatives", "design decision", "recommend with rationale".
---

# architect-option-matrix

Architect's plan contract requires at least 2 viable options for any non-trivial decision, with a trade-off matrix and a recommendation. Single-option plans bury the rejection rationale and force the user to re-derive it at review time. This skill is the template + a worked example pulled from plan 16 § C.1 (skill naming).

## When to invoke

- Authoring a new plan, hitting a "we'll use X" sentence — stop and surface alternatives.
- User asks "which approach should we use" / "compare alternatives" / "what are the trade-offs".
- Reviewing someone else's plan that recommends without comparing — flag for matrix addition.
- Self-review: any time the plan reads like "the obvious choice is X" with no rejected alternatives.

## What this skill does

For each decision, render a markdown table with at least 2 options across these 5 dimensions:

| Dimension | Question to answer |
|---|---|
| **Capability** | What does this option get us? What does it NOT get us? |
| **Cost** | Implementation effort + ongoing maintenance cost + token cost if AI-relevant. |
| **Risk** | What could go wrong? Probability + impact. |
| **Maintenance** | Who owns it 6 months from now? What expertise is required to evolve it? |
| **Lock-in** | How hard is reversal if we change our mind? What does the exit look like? |

Then a **Recommendation** line: name the option, state why, name the trade-off you're accepting.

### Template

```markdown
#### <Decision number> — <Decision name>

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| <Option A> | <what it gives> | <impl effort> | <what can go wrong> | <ownership / expertise> | <reversal cost> |
| <Option B> | ... | ... | ... | ... | ... |
| **<Recommended option>** | ... | ... | ... | ... | ... |

**Recommendation: <option>.** <one-paragraph rationale: why this option, what trade-off accepted, what evidence supports the call (research / context7 / nixos / a recent ROADMAP precedent).>
```

### Worked example — plan 16 § C.1 (skill naming)

| Option | Clarity | Collision risk | Discoverability | Tree readability |
| --- | --- | --- | --- | --- |
| Flat (`pick-next`, `stack-invariants`) | Lowest — "pick-next from where?" | High — collides with built-in `pick-next` if Anthropic ships one | Worst — alphabetical sort mixes agents | Worst — 28 dirs in a flat list |
| `naavik-<agent>-<verb>` (`naavik-manager-pick-next`) | High | Lowest — fully namespaced | Good but verbose | Good but verbose |
| **`<agent>-<verb>` agent-specific + `naavik-<verb>` shared** | High | Low — agent prefix dedupes | Good — `manager-*` groups visually | Good — 6 agent prefixes + 4 `naavik-*` |

**Recommendation: hybrid.** `<agent>-<verb>` for agent-scoped, `naavik-<verb>` for shared cross-agent. Trade-off accepted: slight name redundancy when listed alphabetically. Evidence: the same hybrid pattern works in `.claude/commands/` (e.g. `bootstrap`, `groom`, `standup`) where context disambiguates.

Note: dimensions can flex per decision. Naming had no maintenance/lock-in axis worth comparing — clarity / collision / discoverability / readability were the load-bearing differentiators. Pick the 4-5 dimensions that matter for THIS decision; don't force the canonical 5 if some are uninformative.

### Other worked patterns from the archive

| Plan | Decision | Options compared | Recommendation pattern |
|---|---|---|---|
| 10a | Process-compose vs systemd-user vs raw shell for dev orchestrator | 3 | Picked process-compose + setsid-w wrapper; locked-in trade-off was Linux-only |
| 10b | NullPool vs default pool for AsyncSession under lifespan | 2 | Picked NullPool; trade-off was 1-2ms latency for safer shutdown |
| 10c | `~/.naavik/dev-credentials` env-gated vs unconditional vs CLI command | 3 | Picked env-gated + on-disk file; trade-off was operator must read the file (not a CLI prompt) |

These archive examples are templates — read the corresponding archived plan if your decision shape is similar.

## Canonical references

- `.claude/agents/architect.md` § "Reasoning depth" + § "Operating loop" § "Option matrix".
- `.claude/agents/architect.md` § "Anti-patterns" — "Skip the option matrix on non-trivial decisions".
- Plan 16 § C.1–C.6 — six worked examples in one plan.
- `docs/plans/archive/` — every executed plan has a worked option matrix or two.

## When NOT to invoke

- Trivial choices (variable name, comment phrasing, kebab-vs-snake) — option-matrix overhead drowns the decision.
- Forced choices ("the library only supports option B" — there's no matrix to draw).
- Compaction events.

## Forbidden during invocation

- Do NOT ship a single-option section labeled "we'll use X". That's the anti-pattern this skill exists to prevent.
- Do NOT pad the matrix with options you don't take seriously. Two real candidates beat five strawmen.
- Do NOT skip the Recommendation line — naming the trade-off you ACCEPT is half the value.
