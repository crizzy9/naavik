# scripts/

This directory is reserved for **project-wide user-runnable scripts** — build
wrappers, deploy helpers, test orchestrators that the maintainer or end-users
invoke directly. It is NOT for agent-system tooling.

After `0.1.1` shipped (plan 25), the agent-system tooling that previously lived
here (`gh-project.sh`, `agent-memory.sh`, `roadmap_parser.py`) was ported to
native Python under `.claude/naavik_ops/`.

## Current maintainer scripts

| Script | Purpose |
|---|---|
| `eval_generation.py` | Standalone generation-quality eval over generated applications. |
| `linkedin_login.py` | Seed/refresh the LinkedIn session profile for the authenticated apply-target resolver (`docs/design/LINKEDIN_APPLY_RESOLUTION.md`). |

Agent-system tooling is invoked through the dispatcher instead:

```bash
.claude/naavik-ops gh next-unblocked
.claude/naavik-ops memory list discussions
.claude/naavik-ops task list 0.2.0
```

## Agent-system tooling lives at `.claude/naavik_ops/`

Entry point: `.claude/naavik-ops` (executable Python).
See `docs/AGENT_OPS.md § 2.7a` for the operator surface.

Historic one-shot migrations live at `.claude/migrations/`.

## Convention summary (per design doc § 9 + plan § D.21)

| Path | Audience | Invoker |
|---|---|---|
| `.claude/naavik-ops` | Agent system | Manager / architect / engineer / etc. |
| `.claude/naavik_ops/**` | Agent system | Dispatched via `naavik-ops <group> <cmd>` |
| `.claude/migrations/**` | Maintainer | One-shot historical migrations |
| `scripts/**` | Maintainer | Project-wide build/deploy/test wrappers |

Per the single-writer rule (`AGENTS.md § GitHub state — single writer rule`),
all GitHub Project + Issue + agent-memory state mutations route through
`.claude/naavik-ops`. The dispatcher writes natively in Python; there are no
remaining bash wrappers.
