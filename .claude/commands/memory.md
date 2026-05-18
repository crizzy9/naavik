---
description: Read-only inspection of `.claude/memory/` stores. List or query JSONL stores; read a knowledge entry by topic slug. Writes go through `.claude/naavik-ops memory` (single writer rule; subprocess-wraps `scripts/agent-memory.sh` during A.29).
argument-hint: <list|query|knowledge> [args]
---

Args: $ARGUMENTS

Procedure — strict dispatch on first verb:

### Verb: `list <store>`

Run `.claude/naavik-ops memory list <store>` where `<store>` is one of: `decisions`, `discussions`, `lessons`, `patterns`, `knowledge`, `runs`. Pretty-print result in chat.

Examples:
- `/memory list knowledge` → tabular list of all `.claude/memory/knowledge/*.md` files.
- `/memory list decisions` → tabular list of `decisions.jsonl` rows.

### Verb: `query <store> '<jq-expr>'`

Run `.claude/naavik-ops memory query <store> '<jq-expr>'` where `<store>` is one of: `decisions`, `discussions`, `lessons`, `patterns`. Expression runs through `jq -c "select(<expr>)"`.

Examples:
- `/memory query decisions '.id == "storage-backend"'`
- `/memory query lessons '.state == "active"'`
- `/memory query discussions '.priority == "HIGH" and .filed_as == null'`

### Verb: `knowledge <slug>`

Run `Read .claude/memory/knowledge/<slug>.md` + surface full file content.

Example:
- `/memory knowledge linkedin-scraping` → reads `.claude/memory/knowledge/linkedin-scraping.md`.

Slug doesn't exist → surface `not found: .claude/memory/knowledge/<slug>.md — run /memory list knowledge for index`.

### Forbidden

- Do NOT write to `.claude/memory/` from this command. Writes go through `.claude/naavik-ops memory` subcommands (`record-decision`, `record-discussion`, `record-knowledge`, `record-lesson`).
- Do NOT shell-out to `gh` / `gh api graphql` from this command. Read-only inspection surface for memory stores; GitHub state queries go through `.claude/naavik-ops gh`.
- Do NOT modify `~/.claude/projects/.../memory/MEMORY.md` from this command. That file is auto-managed by Claude Code; we are read-only on it.

### Canonical references

- `.claude/naavik-ops memory --help` — full writer surface.
- `docs/design/AGENT_MEMORY.md` — architecture + store schemas.
- `docs/AGENT_OPS.md § 14` — daily workflow integration.
- `.claude/skills/naavik-memory-lookup/SKILL.md` — programmatic lookup pattern for agents.
