# scripts/

This directory is reserved for **project-wide user-runnable scripts** — build
wrappers, deploy helpers, test orchestrators that the maintainer invokes
directly. It is NOT for agent-system tooling.

## Agent-system tooling lives at `.claude/naavik_ops/`

Agent dispatcher: `.claude/naavik-ops` (executable Python entry point).
See `docs/AGENT_OPS.md § 2.7a` for the operator surface.

## During A.29 transition (until A.30 ships as 0.1.1)

The following bash scripts temporarily live here as subprocess targets for the
Python dispatcher:

- `gh-project.sh` (1469 LOC bash) — `.claude/naavik-ops gh` wraps it.
- `agent-memory.sh` (843 LOC bash) — `.claude/naavik-ops memory` wraps it.
- `roadmap_parser.py` (304 LOC Python) — `.claude/naavik_ops/lib/roadmap.py`
  will absorb it in A.30 (0.1.1).

The historic one-shot migration `A.28-board-restructure.sh` has already moved
to `.claude/migrations/`. The new A.29 migration runbook
`A.29-phase-renumber.py` lives there as well — both are agent-system internal
historical artifacts.

After A.30 ships (single-task patch release 0.1.1 themed "Python rewrite of
legacy bash"), this directory should be empty until a real project-wide script
lands.

## Convention summary (per design doc § 9 + plan § D.21)

| Path | Audience | Invoker |
|---|---|---|
| `.claude/naavik-ops` | Agent system | Manager / architect / engineer / etc. |
| `.claude/naavik_ops/**` | Agent system | Dispatched via `naavik-ops <group> <cmd>` |
| `.claude/migrations/**` | Maintainer | One-shot historical migrations |
| `scripts/**` | Maintainer | Project-wide build/deploy/test wrappers |

Per the single-writer rule (`AGENTS.md § GitHub state — single writer rule`),
all GitHub Project + Issue + agent-memory state mutations route through
`.claude/naavik-ops`. The bash scripts above remain the underlying
implementation during A.29 transition; subprocess wrappers preserve the
single-writer invariant.
