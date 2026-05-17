#!/usr/bin/env bash
# .claude/hooks/cold-start.sh
# Fires on SessionStart (matchers: startup, resume — not compact: ROADMAP already gets
# re-attached via skill content lifecycle). Injects a pinned "required reading" block +
# current state snapshot so every fresh session lands oriented.
#
# Subagent dispatches DO NOT receive SessionStart (per Claude Code hook spec, 2026-05).
# The `naavik-cold-start` skill is the subagent equivalent — each agent prompt requires
# it as the first action. Belt + suspenders.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 0  # fail open — never block session startup

# Read the SessionStart event payload (we only use source to skip compact).
INPUT="$(cat || true)"
SOURCE="$(echo "$INPUT" | jq -r '.source // "startup"' 2>/dev/null || echo "startup")"

# On compact, skip — the skill content lifecycle re-attaches invoked skills automatically.
if [[ "$SOURCE" == "compact" ]]; then
  exit 0
fi

# Surface the current ROADMAP "Last updated" line for "what's fresh".
LAST_UPDATED="$(grep -m1 '^> Last updated:' ROADMAP.md 2>/dev/null | sed 's/^> //' || echo 'unknown')"

# Tail recent agent activity.
RUNS_TAIL=""
if [[ -f traces/runs.log ]]; then
  RUNS_TAIL="$(tail -n 5 traces/runs.log 2>/dev/null || true)"
fi

# Budget snapshot (gitignored; may not exist on fresh clone).
BUDGET=""
if [[ -f .claude/budget-ledger.json ]]; then
  BUDGET="$(jq -r '"today=\(.current_day) total=\(.total_today)"' .claude/budget-ledger.json 2>/dev/null || true)"
fi

cat <<EOF
Naavik cold-start reminder. Your first action MUST be: Skill: naavik-cold-start

That skill will load the canonical context (AGENTS.md, ROADMAP_OVERVIEW.md, AGENT_OPS.md, etc.) in the right order for your role. Until it has run, do not read individual files directly.

Current state snapshot (use this to decide whether the skill needs to re-fetch state):
- ROADMAP $LAST_UPDATED
- Recent runs:
$(echo "$RUNS_TAIL" | sed 's/^/    /')
- Budget: $BUDGET

If you are a subagent dispatched via Task, this hook did NOT fire for you (SessionStart only fires on parent sessions). Invoke Skill: naavik-cold-start regardless — your agent prompt's "Required reading on cold start" section enforces this.
EOF

exit 0
