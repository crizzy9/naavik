---
description: Apply the architect's option-matrix template — for every non-trivial decision, surface 2+ options across {capability, cost, risk, maintenance, lock-in} and recommend one with rationale. Use whenever a plan needs to lock a design decision, when the user asks "which approach should we use", or when you catch yourself proposing one option without naming alternatives. Triggers on phrases like "option matrix", "trade-off table", "weigh the options", "which approach", "compare alternatives", "design decision", "recommend with rationale".
---

# architect-option-matrix

Plan contract requires ≥ 2 viable options for any non-trivial decision, w/ trade-off matrix + recommendation. Single-option plans bury rejection rationale + force user to re-derive at review. Template + worked example from plan 16 § C.1 (skill naming).

## When to invoke

- Authoring new plan, hitting "we'll use X" sentence — stop, surface alternatives.
- User asks "which approach should we use" / "compare alternatives" / "trade-offs".
- Reviewing someone's plan recommending without comparing — flag for matrix.
- Self-review: plan reads like "obvious choice is X" w/ no rejected alternatives.

## Template

For each decision, markdown table w/ ≥ 2 options across 5 dimensions:

| Dimension | Question to answer |
|---|---|
| **Capability** | What does option get us? What does it NOT get us? |
| **Cost** | Implementation effort + ongoing maintenance + token cost if AI-relevant. |
| **Risk** | What could go wrong? Probability + impact. |
| **Maintenance** | Who owns it 6 months from now? What expertise to evolve it? |
| **Lock-in** | How hard is reversal if we change our mind? What does exit look like? |

Then **Recommendation** line: name option, state why, name trade-off accepted.

```markdown
#### <Decision number> — <Decision name>

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| <Option A> | <what it gives> | <impl effort> | <what can go wrong> | <ownership / expertise> | <reversal cost> |
| <Option B> | ... | ... | ... | ... | ... |
| **<Recommended option>** | ... | ... | ... | ... | ... |

**Recommendation: <option>.** <one-paragraph rationale: why this option, trade-off accepted, evidence (research / context7 / nixos / ROADMAP precedent).>
```

## Worked example — plan 16 § C.1 (skill naming)

| Option | Clarity | Collision risk | Discoverability | Tree readability |
| --- | --- | --- | --- | --- |
| Flat (`pick-next`, `stack-invariants`) | Lowest — "pick-next from where?" | High — collides w/ built-in `pick-next` if Anthropic ships one | Worst — alphabetical sort mixes agents | Worst — 28 dirs in flat list |
| `naavik-<agent>-<verb>` (`naavik-manager-pick-next`) | High | Lowest — fully namespaced | Good but verbose | Good but verbose |
| **`<agent>-<verb>` agent-specific + `naavik-<verb>` shared** | High | Low — agent prefix dedupes | Good — `manager-*` groups visually | Good — 6 agent prefixes + 4 `naavik-*` |

**Recommendation: hybrid.** `<agent>-<verb>` for agent-scoped, `naavik-<verb>` for shared cross-agent. Trade-off: slight name redundancy when listed alphabetically. Evidence: same hybrid pattern works in `.claude/commands/` (e.g. `bootstrap`, `groom`, `standup`) where context disambiguates.

Dimensions flex per decision. Naming had no maintenance/lock-in axis worth comparing — clarity / collision / discoverability / readability were the load-bearing differentiators. Pick 4-5 dimensions that matter for THIS decision; don't force canonical 5 if uninformative.

## Other worked patterns from archive

| Plan | Decision | Options | Recommendation pattern |
|---|---|---|---|
| 10a | Process-compose vs systemd-user vs raw shell for dev orchestrator | 3 | Picked process-compose + setsid-w wrapper; locked-in trade-off was Linux-only |
| 10b | NullPool vs default pool for AsyncSession under lifespan | 2 | Picked NullPool; trade-off was 1-2ms latency for safer shutdown |
| 10c | `~/.naavik/dev-credentials` env-gated vs unconditional vs CLI command | 3 | Picked env-gated + on-disk file; trade-off was operator must read file (not CLI prompt) |

Archive examples = templates — read corresponding archived plan if decision shape is similar.

## Canonical references

- `.claude/agents/architect.md` § "Reasoning depth" + § "Operating loop" § "Option matrix".
- `.claude/agents/architect.md` § "Anti-patterns" — "Skip option matrix on non-trivial decisions".
- Plan 16 § C.1–C.6 — six worked examples in one plan.
- `docs/plans/archive/` — every executed plan has a worked option matrix or two.

## When NOT to invoke

- Trivial choices (variable name, comment phrasing, kebab-vs-snake) — overhead drowns decision.
- Forced choices ("library only supports option B" — no matrix to draw).
- Compaction events.

## Forbidden during invocation

- Do NOT ship single-option section labeled "we'll use X". Anti-pattern this skill prevents.
- Do NOT pad matrix w/ options you don't take seriously. Two real candidates beat five strawmen.
- Do NOT skip Recommendation line — naming trade-off you ACCEPT is half the value.
