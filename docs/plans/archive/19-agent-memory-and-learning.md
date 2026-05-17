---
Status: EXECUTED
Type: design
Authored: 2026-05-17
Last updated: 2026-05-17
Approved: 2026-05-17 — all 7 Q decisions locked per architect recommendation; 12-item approval checklist accepted; ROADMAP A.15 filed
Shipped: 2026-05-17 — PR #53 squash a63b774; closes #52; ROADMAP § Phase A row A.15 marked [x]. Run: 2026-05-17T08-40-13_4abef2.
Depends on: 16-agent-system-v2 (archived 2026-05-17 — EXECUTED) — provides the skill + hook + trace substrate this plan builds on top of
GitHub: A.15 → Issue #52 (CLOSED on merge). Follow-ups filed pre-merge: A.17 (#54), DEF-24 (#55), DEF-25 (#56); A.11 (#48) drift reconciled inline.
---

## Approval decisions (locked 2026-05-17)

| Q | Decision | Rationale |
|---|---|---|
| Q1 | JSONL + markdown only | no SQLite / no pgvector / no Mem0; self-host minimal |
| Q2 | surface-then-ask at PR_REVIEW_GATE + MILESTONE_GATE | mid-strength automation; manager prompts user with discovered items |
| Q3 | manual `/learn` slash command + skill mirror | no cron; milestone gate suggests running it |
| Q4 | 5-occurrence threshold for knowledge promotion | revisit in Wave 3 with real data |
| Q5 | full Wave 1 (10 ships) | not skinny-MVP; ship complete substrate |
| Q6 | `~/.claude/projects/.../memory/MEMORY.md` integration = read-only | never writes; suggest user-copy when promotion warranted |
| Q7 | ROADMAP row identity = new A.15 under Phase A, HIGH priority | already filed 2026-05-17 |

**Deviation from architect's recommendation**: ship all 3 Waves in **one PR** (not 3 phased PRs with HALTs between). Per user directive 2026-05-17. Engineer scopes accordingly; reviewers handle the larger diff at PR_REVIEW_GATE.

**Companion follow-up**: ROADMAP § Phase A row **A.16** (Machine-readable wording rewrite of `.claude/agents/*`, `.claude/skills/*`, `.claude/commands/*`, `.claude/hooks/*`) — separate plan; user-asked principle "wording everywhere other than docs is machine readable... minimizes tokens while conveying the same information." Engineer working on A.15 should adopt this style for **all new agent-system files** (new skills, new commands, new scripts) but is NOT scoped to retrofit existing files in this PR.

# 19 · Agent memory + learning system — persistent stores, indexed knowledge base, discussion capture, periodic learning loop

## Goal

Ship the agent system's missing memory layer — six append-only or markdown stores under `.claude/memory/`, a discovery surface stitched onto the existing skills + grep stack, a `/learn` slash command (plus skill mirror) that analyzes recent runs for failure patterns + drift + token hotspots, and a `discussion-capture` skill that fires at every PR-merge and milestone gate to surface deferred items the user said-out-loud-but-the-system-didn't-file. The stores are markdown + JSONL (no new DB), follow the existing single-writer pattern (`scripts/gh-project.sh` is the model — one script per store), and complement Claude's built-in primitives (`CLAUDE.md` for invariants, `~/.claude/projects/.../memory/MEMORY.md` for personal preferences, Skills for procedural memory) rather than duplicate them. Type: design — the plan produces a permanent design doc at `docs/design/AGENT_MEMORY.md` after approval, plus the engineer-shipped substrate in Wave 1.

## Why

Three drifts the current agent system shows, all surfaced by the **2026-05-17 run** (`traces/2026-05-17T03-16-16_75a522/`) that just shipped PC.6 + A.11:

1. **Cross-run amnesia.** The architect-LinkedIn dispatch produced `docs/design/research/LINKEDIN_SCRAPING.md` (94k tokens of option matrix) — the next dispatch that touches LinkedIn won't know it exists unless someone reads the trace. The engineer's path-C re-loop landed a `prepare-commit-msg` case-sensitivity gotcha — the next engineer dispatch will rediscover it. The hacker's self-approval-on-own-author PR pivot (forced posting as `COMMENTED` instead of `CHANGES_REQUESTED`) is now a recurring pattern but isn't memorialized anywhere queryable.
2. **Discussion-to-ROADMAP drift.** The session surfaced PC.6a (broader `require_password_complete` gate), JWT-denylist-on-rotation, and an "uppercase-task-id case sensitivity" note. The first two got ROADMAP rows; the third got an AGENT_OPS § 2.8 paragraph but no tracking row — silently absorbed. The user's question — "are we doing this?" — is the right question, and today the answer is "sometimes, when the manager remembers." Should be deterministic.
3. **No retrospective.** Five `errors_encountered` entries in this run's `MANIFEST.json`. Two of them (sandbox denial after direct push, destructive-rm guard tripping the live-orchestrator surrogate) recur across multiple runs. Without an `analyze last N runs` pass, the system never learns from itself; the user has to spot patterns by eye.

ROADMAP row this plan implements: a new **`A.15`** under Phase A (Agent System), HIGH priority — *agent memory + learning loop*. This row needs to be filed against `ROADMAP.md § Phase A` as part of plan approval (manager edits ROADMAP first per single-doc-tracking; architect's `MIRROR_ISSUE_OPENED` event creates the GitHub Issue mirror after).

The plan is `Type: design` because it introduces a new contract — store schemas, store-writer rule, knowledge-entry shape, learning-loop interface, skill conventions for memory-aware skills. On approval the proposal content graduates into `docs/design/AGENT_MEMORY.md` as the permanent reference; the plan file at `docs/plans/19-agent-memory-and-learning.md` archives with the deviations section.

## Proposal

### A · Why not just use what already exists?

Before designing anything new, the plan should defend why the current stack can't cover the surface. Side-by-side:

| Surface | What Claude already provides | Gap |
| --- | --- | --- |
| **Project conventions** | `CLAUDE.md`, `AGENTS.md` — read on every cold start via `naavik-cold-start` skill | Static; can't accumulate session-derived facts |
| **User preferences** | `~/.claude/projects/-home-nightwatcher-.../memory/MEMORY.md` — auto-managed by Claude Code | Per-user, per-machine; not shared with other contributors; not queryable from agents (Claude reads it but agents can't search it) |
| **Procedural memory** | `.claude/skills/<name>/SKILL.md` — auto-triggers on phrase match; 29 skills today | Procedural-only; doesn't hold situational state ("last time we tried X, it failed because Y") |
| **State caches** | `.claude/budget-ledger.json` (manager-managed), `.claude/github-issue-map.json` (gh-project.sh single writer) | Single-purpose; not a general-purpose KB |
| **Trace logs** | `traces/<run-id>/*.log` + `MANIFEST.json` — append-only per run | Per-run; the question "across last 20 runs, which agent retries most?" needs aggregation that doesn't exist |
| **Anthropic Memory tool** | API-level `memory_20250818` tool — Claude reads/writes `/memories/*` | **Not exposed in Claude Code.** Agent SDK / API only. Out of scope for this plan (would require switching off Claude Code for the agent loop, which we're not doing). Flag for revisit if Claude Code adds the tool. |
| **Mem0 / MCP memory servers** | mem0.ai cloud + `mcp-memory-keeper` self-hosted + `shaneholloman/mcp-knowledge-graph` local | Adds a third-party always-on service or paid SaaS — violates "self-host first, no third-party always-on" (`AGENTS.md`). Flag for revisit if a future plan needs semantic search at scale. |

**Conclusion:** the gap is real and Claude's primitives don't fill it. But the gap is small enough to fill with **flat files + jq + grep + the existing skills surface** — no new infrastructure.

### B · Architecture sketch

Six stores under `.claude/memory/`, owned by a single writer script (`scripts/agent-memory.sh`), discovered via 3 new memory-aware skills + 2 new slash commands. All stores are markdown or JSONL; readable with `Read` / `Grep` / `jq`; gitignored per-fork (committed only at the writer's level — design doc + script, not the stores themselves).

```
.claude/memory/                       ← all stores (gitignored, per-fork)
├── decisions.jsonl                   ← W1 · architectural decisions w/ rationale + supersedes-by
├── discussions.jsonl                 ← W1 · deferred items captured at gate boundaries
├── lessons.jsonl                     ← W2 · mined patterns from session analysis
├── knowledge/                        ← W1 · long-form markdown KB, one file per topic
│   ├── linkedin-scraping.md          ←   (e.g.) extracted from architect-linkedin trace
│   ├── prepare-commit-msg-case.md    ←   gotcha extracted from plan-18 deviations
│   └── hacker-self-approval.md       ←   pattern from PR #50 hacker.log
├── recurring-patterns.jsonl          ← W2 · auto-aggregated patterns (5+ occurrences)
└── runs-analysis/                    ← W2 · per-run summaries (one .md per run-id)
    └── 2026-05-17T03-16-16_75a522.md

scripts/agent-memory.sh               ← W1 · single writer for all stores
                                         (mirrors scripts/gh-project.sh pattern)

.claude/skills/                       ← 3 new skills + 1 new shared
├── naavik-memory-lookup/SKILL.md     ← W1 · "before answering X, check the KB"
├── naavik-discussion-capture/SKILL.md ← W1 · fires at gate boundaries
├── naavik-learn/SKILL.md             ← W2 · skill mirror for /learn command
└── manager-promote-lesson/SKILL.md   ← W3 · promotes a recurring-pattern to a lesson

.claude/commands/                     ← 2 new slash commands
├── learn.md                          ← W2 · /learn N — analyze last N runs
└── memory.md                         ← W1 · /memory <verb> <args> — inspect or record
                                         (read-only — never writes; writes go via scripts/agent-memory.sh)
```

**Reading model:** any agent can `Read` / `Grep` any store. The skills are the auto-discovery surface (skill description = trigger phrases that pull the right knowledge file into context).

**Writing model:** all writes go through `scripts/agent-memory.sh` (`record-decision`, `record-discussion`, `record-knowledge`, `record-lesson`, `analyze-run`, `mine-patterns`). Single-writer rule mirrors `scripts/gh-project.sh`. Agents invoke via Bash; the script enforces schema + dedupe + append-only invariants.

### C · Decisions (option matrices)

#### C.1 — Storage backend (file vs SQLite vs Postgres+pgvector vs MCP memory server)

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **JSONL + markdown files** (one file per topic; jq/grep search) | Plenty for the corpus size (~2k entries over 1 year); zero infra; matches existing `.claude/*.json` cache pattern; works with `Read`/`Grep`/`Glob` out of the box; survives `nix-collect-garbage`; readable with `cat` | Storage: a few hundred KB even after a year; CPU: jq + grep are O(file size) but the corpus is small (each store under 1 MB at steady state) | Schema drift if multiple writers diverge — mitigated by single-writer rule (`scripts/agent-memory.sh`) | Add one line to `.gitignore`; the script does dedupe + validation | None — switch to anything later by piping JSONL through `jq` |
| SQLite + FTS5 (per `.claude/memory.sqlite3`) | BM25 ranking; sub-100ms queries on 100k+ entries; clean schema | New Python dep (or shell out to `sqlite3` CLI); migration story when schema changes; binary file in `.claude/` complicates `git diff`; FTS5 needs index rebuild on every insert | Brittle — corruption isn't recoverable by `Edit`; agents can't easily inspect mid-flight | Migration scripts as schema evolves; explicit `VACUUM` over time | Medium — exit costs are write-a-converter |
| Postgres + pgvector (reuse product DB) | Hybrid BM25 + vector + recency scoring; same DB the product uses | Couples agent-system feature to product DB lifecycle (runs only when `nix run .#dev` is up — most operator sessions are read-only on closed orchestrator); needs Alembic migration; needs DB session in shell scripts (not standard); ~2k entries doesn't need vectors | Drift between agent-system schema and product schema; semantic search blast radius (embeddings cost LLM tokens) | New migration every time the schema changes; vector index tuning; embedding job for new rows | High — agent system becomes Postgres-dependent |
| MCP memory server (mem0 cloud / mcp-memory-keeper / mcp-knowledge-graph) | Drop-in, battle-tested; semantic search out of the box | Cloud option breaks "self-host first" rule; self-hosted requires a separate always-on Node/Python service; per-fork bootstrap step; agent prompt has to know how to invoke the MCP tool | New service to monitor + restart + auth | Read the upstream docs + their breaking changes | High — switching memory provider rewires the whole system |

**Recommendation: JSONL + markdown.** Naavik's memory corpus is genuinely tiny (~10–50 entries per active session, ~500–2000 per year at the current pace). Every existing operational cache in `.claude/` is already file-based (`budget-ledger.json`, `github-issue-map.json`, `github-project.json`); this plan follows the same pattern. Trade-off accepted: no semantic search. Mitigation: the **skills layer** is the semantic surface — a well-described skill (`naavik-memory-lookup` with rich trigger phrases) effectively does what semantic search would do, by surfacing the right knowledge file when the right phrase appears. If we ever cross 10k entries, we revisit SQLite FTS5 (one-shot migration: `jq` the JSONL into `INSERT` statements). pgvector + MCP options are forbidden by other invariants ("self-host first," "no new always-on services," "decouple agent system from product DB"); listed only to make the rejection explicit.

#### C.2 — Search + progressive discovery mechanism

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Skill auto-trigger + Grep fallback** | Skill descriptions encode "when to read which file"; `Grep` covers anything not covered by a skill | Skill descriptions need pushy trigger phrases (per `architect-option-matrix` skill body) — well-trodden territory | Skill underTriggering on novel phrases — mitigated by adding trigger phrases as the skill matures via `/learn` recommendations | Skill body updates (rare; description tuning at most every few weeks) | None — skills are just markdown |
| Vector embeddings (per-entry; semantic similarity at query time) | Best recall on unfamiliar phrasing | Need an embedding model running (OpenAI / local Ollama / Anthropic Haiku); $$$ on cloud or RAM on Ollama; per-write embedding cost; index file maintenance | Cold-cache miss → first query is slow + expensive; embedding drift if the model changes | Per-write embedding refresh + index update | Medium — switching backends rewrites the entry-to-vector map |
| Pure `Grep`-over-`.claude/memory/` (no skills) | Trivial | Agent has to know to grep; doesn't auto-fire | High — same underTriggering as if we had no skills | None | None |

**Recommendation: skill auto-trigger + Grep fallback.** The skills layer is **the discovery mechanism Claude Code is shipping for exactly this purpose** — auto-trigger on phrase match, body points at the right file. The 29 existing skills already prove the pattern works for procedural memory; extending it to situational memory is one new skill per topic-family. Trade-off accepted: agent has to look up topics by phrase, not by semantic similarity. Mitigation: each knowledge file gets a `## Aliases` section listing alternate phrases the skill description should trigger on — `/learn` Wave 2 mines failed grep attempts to identify aliases that should be added.

#### C.3 — Discussion → ROADMAP capture automation level

This is the user's direct question — "we discuss things … we must add them to the roadmap if it's not being addressed immediately. are we doing that?"

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Surface-then-ask (semi-automatic)**: at every PR_REVIEW_GATE + MILESTONE_GATE, the manager runs `Skill: naavik-discussion-capture`, which scans `manager.log` for `SIDE_TASK`, `BLOCKED`, `ROADMAP_EDIT row=<new>`, and `OPEN_QUESTION` events in the current run; presents a single `AskUserQuestion` with one row per candidate deferred item (each with "file as ROADMAP row" / "skip" / "merge with existing row #N") | Captures deferred items at the natural break point of the workflow; explicit user consent per item; surfaces what the system noticed | One AskUserQuestion per gate (already exists); the skill body adds ~3k tokens of scanning logic | User decision fatigue if too many candidates surface (e.g. 8 items at a milestone gate) — mitigated by a hard cap (top-5 by significance, with "see more" for the rest) | Skill description tuning over time | None |
| Auto-file every deferred item without asking | Zero decision overhead | False positives — every `BLOCKED` event becomes a ROADMAP row including transient sandbox denials; ROADMAP becomes noisy; user loses trust in the ledger | High — drift from "ROADMAP is authoritative" to "ROADMAP is also a bug log" | Higher than option 1 (the user starts cleaning up after the system) | None |
| Manual only (status quo) | No false positives | Status quo: the user has to remember, the system silently drops items; this is the drift the user just called out | The exact problem this plan fixes | None | None |
| Hybrid: auto-file CRITICAL/HIGH-shape deferred items; ask for MEDIUM/LOW | Best signal-to-noise | Classifier needs heuristics (who decides what's CRITICAL?); user has to debug misclassifications | Higher than option 1 | Higher | None |

**Recommendation: option 1, surface-then-ask.** Directly answers the user's "are we doing this?" with "yes, at every PR_REVIEW_GATE and MILESTONE_GATE, the system surfaces what it noticed and you say yes/no per item." Trade-off accepted: one extra AskUserQuestion per gate (which the user already responds to at those gates anyway — the gate halt is the cost, not the additional question). The skill is required reading for the manager prompt's `# Operating loop` step 10 / step 15.

#### C.4 — Periodic learning trigger (cron vs `/build` post-hook vs manual `/learn` command)

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Manual `/learn [N]` slash command** (default N=10, scans last N runs) | User controls when learning fires; deterministic; no surprise sub-agent spawns | Requires the user to remember `/learn` — but `/standup` and `/groom` already exist as periodic-by-user-volition commands, this matches the pattern | User might forget — mitigated by adding "run /learn weekly" to AGENT_OPS § 3 daily workflow | The skill description nudges manager to suggest `/learn` after every milestone gate | None |
| `/build` post-hook: every `/build` run that ships >=1 PR fires `Skill: naavik-learn` automatically | Catches every milestone | Token cost: ~50k–150k per analysis run (we'll budget it); spawns sub-agent at the end of every milestone, which doubles `/build`'s tail latency | Surprises the user with a long-running analysis they didn't ask for | Hook config in manager.md + budget ceiling | None |
| Cron / scheduled trigger (apscheduler in dev orchestrator, or a manual `traces/.cron.sh`) | Truly periodic | Requires a process to be running (the dev orchestrator isn't always up); separate scheduling story; "schedule a remote agent" exists as a built-in skill but ties to a third-party service | Out-of-band runs the user doesn't see; budget accounting headache | New cron config | High — separate scheduling subsystem |
| Hybrid: auto-fire after every milestone gate (cheap, scoped to the milestone's runs); separate `/learn` command for ad-hoc broader analysis | Best of both | Doubles the trigger surface | More implementation than C.1 | Both | None |

**Recommendation: option 1, manual `/learn [N]` command with skill mirror, plus a one-line `traces/runs.log` parse at every milestone gate that surfaces "you've shipped N runs since last `/learn` — run it?"** — the milestone-gate prompt fires the question but doesn't auto-run. Trade-off accepted: the user has to say yes. Justification: an unsupervised cron analysis with no consent gate accumulates a backlog of "the system thinks X" that nobody reads. Better to opt-in. After a few months of running `/learn` per milestone, if the user wants automation, we can promote it to hybrid (option 4) in a Wave 3 follow-up.

#### C.5 — Knowledge entry shape (markdown vs JSON vs YAML)

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Markdown** with `## Front-matter` keys (`Topic:`, `Aliases:`, `First captured:`, `Last referenced:`, `Supersedes:`) | Reads like the rest of `docs/`; skill bodies can `Read` directly; humans can grep + scroll | No machine-strict schema — mitigated by single-writer script enforcing front-matter shape | Schema drift if writer script bypassed — mitigated by single-writer rule | One `record-knowledge` subcommand validates shape | None — flat markdown |
| Pure JSON (one file per topic, `topic.json`) | Machine-strict | Worst reading experience; can't grep the body usefully; renders badly in `Read` | Lossy for long-form prose | Same as markdown | Low |
| Structured YAML (front-matter only) + body separately | Compromise | Two-file pattern; no clear win | Two files to keep in sync | Higher | Low |
| Single JSONL file with one entry per row | Best for queries | Bad for long-form bodies (escaped multi-line strings); same problem as JSON | Worst readability | Single-file growth | None |

**Recommendation: markdown with front-matter.** The knowledge files **are** documentation — they should read like the rest of `docs/`. Each file has:

```markdown
---
Topic: <kebab-case slug; matches filename>
Aliases: <comma-separated phrases the topic also surfaces under>
First captured: <YYYY-MM-DD, plus run-id>
Last referenced: <YYYY-MM-DD>
Supersedes: <other-topic.md or "none">
Confidence: <high | medium | low>
---

# <Topic>

## Context

<one paragraph — what surface, what symptom, what motivated the capture>

## Resolution / pattern

<the thing learned, the option matrix outcome, the workaround>

## Related

- traces/<run-id>/<agent>.log:<line>
- docs/plans/archive/<NN>-<name>.md § <section>
```

Trade-off accepted: no strict machine schema for the body. Mitigation: front-matter is machine-parseable (the writer script extracts it via `awk '/^---$/{n++} n==1' file`); the body is free-form.

#### C.6 — Integration boundary with Claude's native primitives

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Read-only of `~/.claude/projects/.../memory/MEMORY.md`** — the new system never writes there; if a lesson from `lessons.jsonl` graduates to "Claude should remember this across all sessions," we surface a `Suggest: add to MEMORY.md` notification but the user decides | Respects Claude's auto-managed personal memory; new system stays in repo scope | One more surface for the system to read on `naavik-memory-lookup` invocations — mitigated by reading `MEMORY.md` only when the corpus has a stale entry on the topic | Per-user-per-machine drift between contributors — mitigated by `decisions.jsonl` being the cross-contributor canonical store | None | None |
| Programmatic write to `~/.claude/projects/.../memory/MEMORY.md` | Auto-promotes important lessons | Stomps on Claude's own management of that file; per-user-per-machine writes break the multi-contributor story; risks corruption (Claude reformats it on its own schedule) | High — Claude's own writes can clobber ours | Need to know when Claude's about to write and back off | Medium |
| Ignore `MEMORY.md` entirely | Simplest | The user's existing "always shut down long-running processes" memory is exactly the kind of pattern we want to mine — ignoring it means we duplicate it in `lessons.jsonl` | Low | None | None |
| Use Anthropic Memory tool (`memory_20250818`) | Native | Not exposed in Claude Code — out of scope until Anthropic ships it | n/a | n/a | High once we depend on it |

**Recommendation: read-only of `MEMORY.md` + read-only of `CLAUDE.md`.** The new memory system **owns** `.claude/memory/` and READS `MEMORY.md` + `CLAUDE.md` + the relevant `docs/` files when assembling context. Never writes to either. If a lesson graduates to "this should be in `MEMORY.md`," the system surfaces a one-line suggestion at the next milestone gate; user copies it manually. If we ever switch to Agent SDK (post-Claude-Code), revisit; for now Claude Code is the only harness.

#### C.7 — Phasing: one big plan vs waves

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
| --- | --- | --- | --- | --- | --- |
| **Three Waves**: W1 = stores + writer script + 2 skills + `/memory` read-only command + discussion-capture gate; W2 = `/learn` command + analytics + per-run summary + skill mirror; W3 = retrospective UI + lesson promotion gate + alias-mining | Smallest first-shippable slice fits in 1 engineer session; each Wave halts at user-visible value | Three plan-archive cycles + three engineer dispatches | Each Wave produces something usable on its own; the next can be deferred without orphaning value | None per-Wave | None |
| Single big-bang plan | One archive cycle | Engineer dispatches over multiple sessions; high risk that mid-plan the spec drifts; long delay before the user sees value | High — plan 10 was the closest example, took ~2 weeks of sessions | One bigger archive | None |
| Two phases (substrate + everything else) | Middle ground | Phase 2 is still too large (analytics + retrospective + alias-mining + promotion = 4 independent surfaces) | Medium | Two archives | None |

**Recommendation: three Waves with HALTs in between.** Mirrors plan 16's four-phase shape which worked well. W1 is the minimum to answer the user's "are we doing this?" question (discussion-capture lands in W1). W2 adds retrospective. W3 adds machine-learning-from-itself. Each Wave is independently archivable.

### D · Build sequence (three Waves)

#### Wave 1 — Substrate + discussion capture (~1 engineer day)

**Deliverable:** stores exist, write script exists, manager auto-captures deferred items at every gate, user has `/memory` to inspect.

Engineer ships:

1. **`.gitignore` update** — add `.claude/memory/` to gitignore (per-fork, like `budget-ledger.json` + `github-issue-map.json`). Single line.

2. **`scripts/agent-memory.sh`** (new, ~250 lines bash, follows `scripts/gh-project.sh` pattern):
   - `init` — create `.claude/memory/` + subdirs, write empty stores with schema headers
   - `record-decision <id> <verdict> <rationale> [--supersedes <id>]` — append to `decisions.jsonl`
   - `record-discussion <topic> <surface> [--phase <phase>] [--priority <P>]` — append to `discussions.jsonl`
   - `record-knowledge <topic> <body-file> [--aliases "..."] [--confidence H|M|L]` — write to `knowledge/<topic>.md` with validated front-matter
   - `record-lesson <pattern> <evidence-runs>` — append to `lessons.jsonl` (W2 will be the auto-writer; W1 ships the command surface)
   - `list <store>` — pretty-print contents
   - `query <store> <jq-expression>` — pass-through to `jq` for power users
   - Schema validation on every write (rejects malformed entries with a clear error)
   - Append-only invariant on JSONL stores (refuses `--replace`; `--supersede` is the upgrade path)

3. **`.claude/skills/naavik-memory-lookup/SKILL.md`** (new, ~120 lines):
   - Description: "Before answering questions about LinkedIn scraping, hacker self-approval, prepare-commit-msg case sensitivity, or any topic with a captured knowledge entry, check `.claude/memory/knowledge/<topic>.md` first. Triggers on phrases matching `Aliases:` front-matter across all knowledge files."
   - Body: documents the lookup pattern (glob `.claude/memory/knowledge/*.md`, grep aliases, read matches), points at `scripts/agent-memory.sh query knowledge` for advanced queries.

4. **`.claude/skills/naavik-discussion-capture/SKILL.md`** (new, ~150 lines):
   - Description: "Surface deferred items from the current run's `manager.log` to the user before closing a PR_REVIEW_GATE or MILESTONE_GATE. Triggers on phrases like 'gate approved', 'about to merge', 'milestone done', 'wrapping up'. Manager invokes at step 10 + step 15 of the operating loop."
   - Body: documents the scan (parse `SIDE_TASK`, `BLOCKED`, `OPEN_QUESTION`, `ROADMAP_EDIT row=<new>` events from `traces/<run-id>/manager.log`); the AskUserQuestion format (one row per candidate, max 5 candidates, "see more" fallback); on user-accept fires `scripts/agent-memory.sh record-discussion` AND (if user wants ROADMAP filing) `scripts/gh-project.sh create-issue` per the single-writer rule.

5. **`.claude/commands/memory.md`** (new, ~80 lines):
   - Slash command surface: `/memory list <store>`, `/memory query <store> '<jq-expr>'`, `/memory knowledge <topic>`. **Read-only** (writes go through `scripts/agent-memory.sh`).
   - Argument-hint: `<list|query|knowledge> [args]`.

6. **`docs/design/AGENT_MEMORY.md`** (the design-doc graduation target) — content lands here on plan approval. Sections:
   - § 1 — Architecture (Wave 1's `.claude/memory/` shape, single-writer rule)
   - § 2 — Stores (one section per store: decisions, discussions, lessons, knowledge, recurring-patterns, runs-analysis)
   - § 3 — Skills + commands
   - § 4 — Discussion-capture gate procedure
   - § 5 — Integration with `MEMORY.md` / `CLAUDE.md` / Skills (read-only)
   - § 6 — How to extend (add a new store, add a new lookup skill, mine a new pattern)

7. **Manager prompt update** (`.claude/agents/manager.md`) — operating loop steps 10 + 15 add:
   - Step 10 (PR_REVIEW_GATE follow-up): "Before closing the gate, invoke `Skill: naavik-discussion-capture`."
   - Step 15 (MILESTONE_GATE): "Before printing the milestone summary, invoke `Skill: naavik-discussion-capture`."

8. **`docs/AGENT_OPS.md § 14 — Memory + learning system`** (new section, ~80 lines):
   - The map: stores + writer + skills + commands.
   - The invariants: single-writer rule mirrors `gh-project.sh`; append-only; gitignored per-fork; markdown knowledge entries.
   - The daily workflow integration: `/memory` for inspection, discussion-capture for capture, `/learn` (W2) for retrospective.
   - The relationship to `MEMORY.md` + `CLAUDE.md` (read-only).

9. **Initial knowledge seeds** (engineer manually backfills from the 2026-05-17 trace):
   - `knowledge/linkedin-scraping.md` — extracted from `docs/design/research/LINKEDIN_SCRAPING.md` (one-paragraph summary + pointer to the full doc)
   - `knowledge/prepare-commit-msg-case.md` — engineer-deviations.log line 2 from this run
   - `knowledge/hacker-self-approval.md` — hacker.log line 21 pattern, also surfaced via engineer-deviations.log
   - `knowledge/destructive-rm-guard.md` — devops pivot in this run's `errors_encountered[3]`
   - `knowledge/sandbox-post-direct-push.md` — manager halt in this run's `errors_encountered[4]`

10. **Tests** — minimal smoke for `scripts/agent-memory.sh`:
    - `init` creates the directory + empty stores
    - `record-decision` rejects malformed input + appends valid input
    - `query` is a jq pass-through (no test beyond exit-code)
    - Append-only invariant: a second `record-decision <id=X>` with `X` already in the file is rejected unless `--supersede`

Wave 1 halt point: user runs `/memory list knowledge`, sees the 5 seeded entries; merges Wave 1; runs the next milestone, gets the discussion-capture prompt at the gate. **HALT for user review.** Move to Wave 2 only on user OK.

#### Wave 2 — Periodic learning loop + retrospective (~2 engineer days)

**Deliverable:** `/learn` produces an actionable report; the system has a memory of its own behavior.

Engineer ships:

1. **`scripts/agent-memory.sh` extensions:**
   - `analyze-run <run-id>` — produces `runs-analysis/<run-id>.md` containing: tokens-per-agent, ERROR events grouped by kind, BUILT/REVIEWED summaries, deviations count, files touched, PRs merged. Idempotent — re-runs overwrite.
   - `mine-patterns [--lookback N]` — scans last N `runs-analysis/*.md` for recurring patterns; appends to `recurring-patterns.jsonl` (auto-aggregated entries that surface 3+ times across runs). Schema: `{pattern_id, first_seen, last_seen, occurrence_count, runs[], proposed_action}`.

2. **`.claude/commands/learn.md`** (new, ~100 lines) — slash command. Arg: `[N]` (default 10).
   - Procedure: invoke `analyze-run` for the N most recent runs; invoke `mine-patterns --lookback N`; produce a markdown report with the headers:
     - **Failure patterns** — top 5 ERROR kinds grouped (pivot / retry / halt / skip), with example run-ids
     - **Drift signals** — plans whose deviation count > 4 (suggests architect under-research before authoring)
     - **Token-spend hotspots** — agents over their cap on N runs out of last 10
     - **Skill activation stats** — for each skill, count of invocations across the N runs (via `traces/<run-id>/manager.log` SIDE_TASK / DISPATCH patterns); flag skills with 0 invocations
     - **Knowledge promotion candidates** — patterns in `recurring-patterns.jsonl` with count >= 5 and no `knowledge/` entry yet; offer user to promote each
     - **ROADMAP candidates** — discussions in `discussions.jsonl` without a `filed_as: #N` link
   - The report is interactive: each section ends with an `AskUserQuestion` ("promote pattern X to knowledge entry?" / "file discussion Y as ROADMAP row?" / etc.).

3. **`.claude/skills/naavik-learn/SKILL.md`** (new, ~120 lines) — skill mirror of `/learn` per the dual-surface convention (`AGENT_OPS § 10.2`).

4. **Manager prompt update** — milestone-gate step 15 adds a one-liner suggestion: "if `runs since last /learn` >= 5, suggest running `/learn`."
   - Computed from `mtime` of the most recent `runs-analysis/*.md` vs `traces/runs.log` length.

5. **`docs/AGENT_OPS.md § 14` extended** — Wave 2's analytics surfaces documented.

6. **Tests:**
   - `analyze-run` over a synthetic minimal trace dir produces a valid markdown report
   - `mine-patterns` with two synthetic runs containing the same ERROR pattern produces a `recurring-patterns.jsonl` entry with `occurrence_count: 2`

Wave 2 halt point: user runs `/learn 5` after Wave 1 + a few real `/build` runs; sees a real report with real signal; merges Wave 2. **HALT for user review.** Move to Wave 3 only on user OK.

#### Wave 3 — Lesson promotion + alias mining + retrospective UI hooks (~1 engineer day)

**Deliverable:** the system starts tightening itself — promoting recurring patterns to lessons, suggesting skill description updates from failed grep attempts, surfacing decision supersession.

Engineer ships:

1. **`scripts/agent-memory.sh promote-lesson <pattern_id>`** — moves a recurring-pattern (count >= 5) into `lessons.jsonl` AND creates a `knowledge/<auto-slug>.md` stub from the pattern's `proposed_action` field. Manager invokes after user approves a `/learn` "promote pattern" prompt.

2. **`.claude/skills/manager-promote-lesson/SKILL.md`** (new, ~100 lines) — the lesson-promotion wrapper. Documents the consent flow + the auto-slugging rule + the knowledge-stub template.

3. **Alias mining** — `mine-patterns` extended with a `--aliases` subcommand that scans `manager.log` for "user said X, we didn't find a knowledge entry" patterns (the system can log "memory miss" events when `naavik-memory-lookup` returns empty). Surfaces aliases the topic should have been queryable under; opens a one-row `AskUserQuestion` to add aliases to the relevant knowledge file's front-matter.

4. **Decision supersession surface** — when `record-decision` is invoked with `--supersedes`, the old decision is marked `superseded_by: <new-id>` (not deleted); `/memory query decisions` defaults to `state == "active"` filter. The skill body for `naavik-memory-lookup` documents the supersede semantics.

5. **`docs/AGENT_OPS.md § 14` finalized** — full Wave 3 surface documented.

6. **Tests:**
   - `promote-lesson` over a pattern with count=4 is rejected (threshold 5)
   - `promote-lesson` over count=6 creates the lesson + knowledge stub
   - alias-mine on a synthetic memory-miss event surfaces the alias proposal

Wave 3 halt point: 1 month of `/learn` usage produces the first real promote-lesson event; user approves; the system starts to compound. **DONE.**

### E · File-by-file edits — Wave 1 (engineer reads this and writes the diff)

| File | New / modify | Purpose |
| --- | --- | --- |
| `.gitignore` | modify | Add `.claude/memory/` |
| `scripts/agent-memory.sh` | new | Single-writer for all stores (Wave 1 subcommands: `init`, `record-decision`, `record-discussion`, `record-knowledge`, `record-lesson`, `list`, `query`) |
| `.claude/memory/.keep` | new | Track the dir in repo (otherwise `init` is awkward) — note: the dir is gitignored but `.keep` is excluded from the gitignore rule via `!.claude/memory/.keep` |
| `.claude/skills/naavik-memory-lookup/SKILL.md` | new | Memory-lookup skill |
| `.claude/skills/naavik-discussion-capture/SKILL.md` | new | Gate-firing discussion capture |
| `.claude/commands/memory.md` | new | Read-only inspection command |
| `docs/design/AGENT_MEMORY.md` | new | The graduated design doc (post-approval; copies §§ B–D of this plan) |
| `docs/AGENT_OPS.md` | modify | Add § 14 — Memory + learning system; § 4 commands ref table adds `/memory` (skill mirror auto); § 5 agent ref no change |
| `.claude/agents/manager.md` | modify | Operating loop step 10 + step 15 add "invoke `Skill: naavik-discussion-capture`" lines; "Skill" tool already in the tools list |
| `ROADMAP.md § Phase A` | modify | Add row A.15 — "Agent memory + learning system" HIGH; mark `[~]` on Wave 1 start |
| `ROADMAP.md "Last updated"` | modify | Bump to plan-19-approval date |
| `tests/test_agent_memory.sh` | new | Minimal smoke tests (bash, runs in CI's `nix develop` shell) |
| `traces/<run-id>/engineer-deviations.log` | append | Per-Wave deviation entries |

Wave 2 + Wave 3 file lists are committed in their respective implementation prompts (authored by architect after each Wave's PLAN_GATE pass), not in this plan.

### F · Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| **Discussion-capture noise** — too many false-positive deferred items at each gate, decision fatigue | Medium | Medium | Hard cap on candidates surfaced per gate (top-5 by significance — recency + `SIDE_TASK` shape over `BLOCKED`); "see more" expandable; `/memory query discussions '.severity == "low"'` lets user inspect rejected candidates later. |
| **Schema drift in JSONL stores** | Low (single-writer rule) | High (corrupt entries break `jq` queries) | `scripts/agent-memory.sh` validates schema on every write; CI lint job runs `jq '.' .claude/memory/*.jsonl` on every PR that touches `.claude/memory/`. |
| **Stores grow without bound** | Low (corpus is small) | Medium (1+ MB files slow `Read` calls) | Wave 3 adds a `prune` subcommand (decisions/lessons older than 1 year + superseded_by != null get archived to `.claude/memory/archive/`). Defer until needed. |
| **Skill underTriggering** — `naavik-memory-lookup` doesn't fire on novel phrasings | Medium | Medium | Wave 3's alias-mining auto-proposes alias additions; until then, manual updates via `scripts/agent-memory.sh record-knowledge --aliases "..."`. |
| **`MEMORY.md` clobbering** — Claude Code re-writes its personal memory file on its own schedule | Low (we're read-only) | n/a | Read-only; never write. If a lesson should land there, system surfaces a suggestion + user copies manually. |
| **Sandbox denial mid-write** | Low | Low (writes are atomic via `mv tmp final` pattern) | Writer script uses `mktemp` + `mv` atomic rename; partial files never visible. If sandbox denies `mv`, the temp file lingers but no store corruption. |
| **Single-writer rule violated by an agent calling `Edit` directly on a store** | Medium | High | Hacker's `hacker-secrets-audit` skill gains a "no direct edits to `.claude/memory/` outside `agent-memory.sh`" check; CI grep blocks it; engineer prompt forbids it. |
| **`/learn` budget overrun** | Medium | Medium | `/learn` runs as a manager-coordinated dispatch (not architect — analysis is mechanical, not synthesis-heavy); ~50k–150k tokens / run; budget ledger flags it; user pays one user-visible AskUserQuestion if estimated spend > 200k. |
| **Discussion-capture conflicts with manager's existing operating loop steps** | Low | Low | Plan 16 already added the skill-invocation pattern at step 10. The new skill invocation slots in cleanly. |
| **The plan creates a "second source of truth"** alongside ROADMAP | Low (per § Single-doc-tracking) | High if violated | `.claude/memory/decisions.jsonl` is NOT a task ledger — it's a decision log (one row per locked architectural decision with rationale). `discussions.jsonl` is NOT a tracking list — it's a record of items surfaced at gates AND their disposition (filed to ROADMAP / skipped / merged with existing). ROADMAP stays authoritative; memory stores capture rationale + context that ROADMAP can't hold. |

### G · Test plan

**Wave 1:**

1. `nix develop` → `scripts/agent-memory.sh init` creates `.claude/memory/` + 4 empty stores + `knowledge/` subdir.
2. `scripts/agent-memory.sh record-decision storage-backend "JSONL + markdown" "see plan 19 § C.1"` appends one row; second invocation with same `id` is rejected.
3. `scripts/agent-memory.sh record-knowledge linkedin-scraping body.md --aliases "linkedin, scrapers"` writes `knowledge/linkedin-scraping.md` with valid front-matter; second invocation requires `--overwrite`.
4. `scripts/agent-memory.sh query decisions '.id == "storage-backend"'` returns the JSONL row via `jq`.
5. Manager-style dispatch in a synthetic trace dir invokes `Skill: naavik-discussion-capture`; the skill returns a candidate list with 0 candidates (empty `manager.log`) and 3 candidates (synthetic `manager.log` with `SIDE_TASK`, `BLOCKED`, `OPEN_QUESTION` events).
6. `/memory list knowledge` produces a table of the 5 seeded knowledge entries.
7. CI lint: `jq '.' .claude/memory/decisions.jsonl >/dev/null` (passes on a clean file).

**Wave 2:**

1. `scripts/agent-memory.sh analyze-run <run-id>` on the 2026-05-17 trace produces a valid markdown report with the right ERROR counts (5).
2. `scripts/agent-memory.sh mine-patterns --lookback 3` on synthetic runs containing the same pivot pattern in 3 runs produces a `recurring-patterns.jsonl` row with `occurrence_count: 3`.
3. `/learn 3` produces an interactive report; AskUserQuestion mock responses test the promote-pattern / file-discussion paths.

**Wave 3:**

1. `promote-lesson <pattern-id>` with count=4 is rejected; with count=6 succeeds + creates `lessons.jsonl` row + `knowledge/<slug>.md` stub.
2. Alias-mining on a synthetic `manager.log` containing `MEMORY_MISS topic=<X> phrase=<Y>` events proposes adding `Y` as an alias to `knowledge/<X>.md`.

### H · Doc cross-walk on Wave 1 ship

When Wave 1 archives:

- `README.md § Configuration` — no change (gitignored, no env vars).
- `README.md § Operations` — add one bullet to "Daily workflow" pointing at `/memory` + `/learn`.
- `CLAUDE.md § Claude Code Specific Notes` — add one-line pointer to the new memory system.
- `AGENTS.md § Agent System` — add `.claude/memory/` + `scripts/agent-memory.sh` to the infrastructure table; add `naavik-memory-lookup` + `naavik-discussion-capture` to skill list.
- `docs/AGENT_OPS.md § 14` — full system documentation (Wave 1 writes the section; Waves 2 + 3 extend it).
- `docs/design/AGENT_MEMORY.md` — the graduated design doc.
- `ROADMAP.md § Phase A` — A.15 row added at plan approval (`[ ]`); flipped `[~]` at Wave 1 start; `[x]` at Wave 3 ship with deliverable note.

### I · Relationship to other in-flight work

- **Plan 16 (A.11, archived 2026-05-17):** this plan builds on plan 16's skill system + trace contract. No conflict; pure extension.
- **PC.6a (deferred):** unrelated.
- **JWT denylist (Phase 1.x):** unrelated.
- **Phase 2 (scrapers):** the LinkedIn knowledge entry seeded in Wave 1 will be consumed by plan 11 (Phase 2 scrapers) — keeps the option matrix discoverable when that plan lands.
- **`docs/PLAYBOOK.md` (A.14, PR #51 in-flight):** the playbook codifies CONTRACT_CHANGE vs BOOKKEEPING. This plan respects the rule — `.claude/memory/` content is gitignored (per-fork), so writes are not CONTRACT_CHANGE; the writer script + skill bodies + design doc ARE CONTRACT_CHANGE and go through PR.

## Open questions

- [ ] **Q1 — Storage scope: JSONL + markdown only, OR add SQLite FTS5 as a second-pass index?** Plan recommends JSONL + markdown (§ C.1). The trade-off accepted: no semantic search, ~2k-entry ceiling before performance matters. User signs off OR asks for SQLite FTS5 from day one (additional ~1 engineer day on top of Wave 1).
- [ ] **Q2 — Discussion-capture automation level: surface-then-ask (recommended), or hybrid auto-file-HIGH + ask-MEDIUM (option 4 in § C.3)?** Surface-then-ask matches the user's explicit "are we doing this?" check. Hybrid is more aggressive — would close the loop faster on high-confidence items but introduces a classifier that needs tuning.
- [ ] **Q3 — `/learn` trigger: manual (recommended) vs auto-fire-post-milestone (`/build` hook) vs cron?** Manual matches `/standup` and `/groom`. Auto-fire adds latency to every `/build` (~50–150k tokens). Cron is rejected here; revisit if usage shows the user always forgets.
- [ ] **Q4 — Knowledge promotion threshold: 5 occurrences (recommended) vs 3 vs 10?** Lower threshold → more lessons promoted faster, more noise. Higher → slower compounding. 5 is a guess based on the current 1 paper-cut-per-day pace; revisit in Wave 3 after live data.
- [ ] **Q5 — Wave 1 first-deliverable shape: full Wave 1 as spec'd (10 ships), or skinnier "just `agent-memory.sh init` + `record-decision` + `naavik-memory-lookup` skill + 1 seeded knowledge entry"?** Full Wave 1 is ~1 engineer day. Skinnier "MVP of the substrate" is ~3 hours but ships nothing the user can interact with at a gate (no `discussion-capture`). Recommend full Wave 1 — discussion-capture is what answers the user's question.
- [ ] **Q6 — Integration with `MEMORY.md`: read-only (recommended) vs ignore vs programmatic write?** Read-only respects Claude's management of that file. Programmatic write risks corruption + per-user-per-machine drift. Ignore loses the existing user-managed pattern.
- [ ] **Q7 — ROADMAP row identity: new A.15 under Phase A (recommended), or fold into existing A.9 / A.10 (which are "cap retention" + "visual dashboard" — adjacent but not the same)?** A.15 is the cleanest — neither A.9 nor A.10 capture memory + learning. User confirms before architect creates the GitHub Issue mirror.

## Approval checklist

- [ ] Plan goal + why are coherent for a future reader who lacks this session's context.
- [ ] Q1: storage backend = JSONL + markdown.
- [ ] Q2: discussion-capture = surface-then-ask at every PR_REVIEW_GATE + MILESTONE_GATE.
- [ ] Q3: `/learn` trigger = manual slash command + skill mirror; milestone gate suggests running it.
- [ ] Q4: knowledge promotion threshold = 5 occurrences (revisit in Wave 3).
- [ ] Q5: Wave 1 ships the full 10-item slice (substrate + 2 skills + 1 command + 5 seeded knowledge entries + AGENT_OPS § 14 + AGENT_MEMORY.md design doc).
- [ ] Q6: MEMORY.md integration = read-only.
- [ ] Q7: ROADMAP row = new A.15 under Phase A, HIGH priority.
- [ ] Type: design — content graduates to `docs/design/AGENT_MEMORY.md` on Wave 1 ship.
- [ ] Three Waves with HALTs in between (Wave 1 = substrate + discussion-capture; Wave 2 = `/learn` + analytics; Wave 3 = lesson promotion + alias mining).
- [ ] Single-writer rule: `scripts/agent-memory.sh` is the sole writer to `.claude/memory/`; the `hacker-secrets-audit` skill gains a check.
- [ ] Skill bodies stay under 1,536 chars in the description field (per spec); use rich trigger phrases.
- [ ] No CLI extension to `src/cli/` and no vault extension. Memory + learning lives entirely in `.claude/memory/` + `scripts/agent-memory.sh`.
- [ ] On Wave 1 ship, README + CLAUDE + AGENTS + AGENT_OPS § 14 + ROADMAP all propagate the new operational surface (`.claude/memory/`, `/memory`, `naavik-memory-lookup`, `naavik-discussion-capture`).

## Deviations from plan

Captured at archive per AGENTS.md § Workflow step 7. Promoted from PR #53 body + `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md`.

### Architectural / scope deviations

- **3-Wave-in-one-PR instead of 3 phased PRs with HALTs between.** Plan § D recommended HALT between Waves 1/2/3 to keep PR diffs small. User locked the override 2026-05-17 ("ship all 3 Waves in one PR"). **Impact:** PR #53 carried Wave 1 (substrate) + Wave 2 (analytics: `/learn` + `analyze-run` + `mine-patterns`) + Wave 3 (promotion: `promote-lesson` + alias mining) together. Reviewers (hacker + devops) handled the larger diff in one gate. No follow-up plan needed; all 3 Waves are EXECUTED via this single PR.
- **Gitignore narrow-exempt approach.** Plan § E left a choice between (a) broad `.claude/memory/` ignore + `git add -f` for seeds vs (b) narrower ignore tracking `knowledge/*.md` + `.keep`. Shipped (b): `.claude/memory/*` ignored EXCEPT `!.claude/memory/.keep` + `!.claude/memory/knowledge/` + `!.claude/memory/knowledge/*.md`. **Impact:** seed knowledge entries + future committed knowledge files ship in git for cross-contributor reference without per-fork `add -f` ceremony.
- **`scripts/agent-memory.sh seed` subcommand added beyond plan.** Inventory helper that lists the 5 committed knowledge seeds. Read-only; doesn't write to any store. **Impact:** discoverability — operators run `bash scripts/agent-memory.sh seed` to see what's bundled.
- **`scripts/agent-memory.sh update-index` subcommand + auto-call from `record-knowledge` added post-review-gate.** Filed by user during PR_REVIEW_GATE ("i see we didn't index our knowledge base properly"). Maintains `.claude/memory/knowledge/INDEX.md` (topic / confidence / aliases / first / last captured) automatically on every `record-knowledge` invocation; standalone subcommand for forced refresh. Single-writer rule preserved. 5 new test assertions cover it (smoke total 45→50 PASS). **Impact:** static index file shippable in PR diff (vs only dynamic `list knowledge` output); navigable on GitHub web UI.
- **Follow-up Issues filed pre-merge, not post-merge.** Plan implicitly assumed follow-ups would be filed after merge. User directive 2026-05-17 at PR_REVIEW_GATE wrapped them into the same PR cycle: `A.17` #54 (hacker findings — `agent-memory.sh` hardening), `DEF-24` #55 (pre-existing ruff cleanup), `DEF-25` #56 (DB-test gating gap). `A.11` (#48) Project board drift reconciled inline via `gh issue close` (workflow rule auto-moved Todo→Done; no new ROADMAP row).

### Quality-gate deviations

- **Pre-existing failures NOT blocking.** PR #53's `bash tests/test_agent_memory.sh` shipped 50/50 PASS on the A.15-introduced surface, but `uv run ruff check .` showed 10 errors (in `migrations/versions/0001_initial.py`, `migrations/versions/0002_settings_multi_users.py`, `scripts/roadmap_parser.py`) + `uv run pytest -x` halted on `tests/test_application_qs_form.py::test_app_questions_render_as_selects` (asyncpg auth on `localhost:5432`). Devops verified BOTH are pre-existing on `origin/main` via the stash technique. Filed as `DEF-24` + `DEF-25`. **Impact:** none on A.15 — confirms A.15 didn't introduce regressions.
- **PR body initially understated pytest pre-existing scope.** Body cited "1 pre-existing failure" via `pytest -x` halt-first behavior. Devops scope-correction: actual is **65 failures across 11 test files** (test_application_qs_form, test_discover_redesign, test_settings_llm_form, test_stub_endpoints, test_swipe_handler, test_draft_lifecycle, test_inplace_expand, test_mobile_layouts, test_mobile_sidebar, test_pages, test_persistence_swap, test_sample_data, test_scroll_spy). PR body addendum + DEF-25 carry the corrected scope. **Impact:** when DEF-25 ships, the canonical fix pattern is `_skip_if_no_db()` at `tests/test_settings_llm_form.py:17-25` — propagate to remaining 11 files.

### Security-review deviations

- **Hacker verdict APPROVE_WITH_NOTES (medium) — 5 findings deferred to A.17.** None block per hacker gating logic (0 critical/high). 2 medium worth pre-merge fix in theory, but user merged with follow-up:
  1. `append_jsonl:49-57` lost-update race (medium) — 30 parallel writes drop ~17; needs `flock` around read-modify-write.
  2. `query:376` jq env() exfil (medium) — user expr unescaped to `jq`; env.* filter reads process secrets to stdout; needs allowlist regex.
  3. `for run in $RUNS:506,573` unquoted word-split (low) — defense-in-depth.
  4. `--aliases` front-matter newline injection (low) — needs kebab regex validation.
  5. `MANIFEST.json` verbatim echo into markdown (low) — needs `printf %q`.
  **Impact:** A.17 (#54, HIGH, ~2h) carries all 5 hardening fixes. Race + jq exfil are real but small-blast-radius (single-operator local tool, no untrusted network input).

### Workflow / process deviations

- **Engineer dispatch bypassed; manager absorbed commit + push + PR role.** Plan assumed normal flow: manager → architect plan → user approval → engineer implements. Reality: when manager ran `/build A.15`, the work was already complete on the `feat/A.15-agent-memory` branch (user implemented directly during the same session window). Manager dispatch of engineer rejected; manager pivoted to verify + commit + push + PR + dispatch reviewers. Logged as `ERROR step=engineer-dispatch kind=skip` in `traces/2026-05-17T08-40-13_4abef2/manager.log`. **Impact:** future plans may see similar shapes when the user is also actively coding — manager should pivot gracefully (don't redo work, verify + ship).
- **Hacker self-approval pivot.** GitHub blocked the hacker (same identity as PR author `crizzy9`) from APPROVE-ing the PR. Hacker posted review as `event=COMMENT` with the verdict line at the top of the body. Pattern captured in `.claude/memory/knowledge/hacker-self-approval.md`. **Impact:** future PR review flows on operator-author PRs hit the same pattern; the captured knowledge entry is the canonical workaround.
- **PR review gate report archived to `traces/<run-id>/pr-review-gate.md`.** New convention introduced this run per user directive ("store this report in an archive"). Future runs should write the gate report to the same path; canonical template lives at `traces/2026-05-17T08-40-13_4abef2/pr-review-gate.md` § 9 convention note. **Impact:** establishes a tracing-system pattern; consider promoting to `docs/AGENT_OPS.md § 7` in a follow-up doc PR.

### New operational surface (propagated per AGENTS.md § Workflow step 7)

All cross-walks landed in PR #53 diff:

- `.claude/memory/` — agent memory stores (gitignored per-fork EXCEPT `.keep` + `knowledge/*.md` + `knowledge/INDEX.md`). Documented in `README.md § Operations`, `CLAUDE.md "Last updated"`, `AGENTS.md § Agent System` infrastructure table, `docs/AGENT_OPS.md § 14`.
- `scripts/agent-memory.sh` — single writer for `.claude/memory/`. Hacker `secrets-audit` skill enforces (`hacker-secrets-audit/SKILL.md` updated).
- `/memory list <store>` + `/memory query <store> '<jq>'` + `/memory knowledge <topic>` — read-only slash commands.
- `/learn [N]` — manual retrospective.
- `.claude/memory/knowledge/INDEX.md` — static auto-generated knowledge index.
- Read-only integration with `~/.claude/projects/.../memory/MEMORY.md` — no programmatic write per locked Q6.

### Test count delta

- Plan § G Wave 1 tests: 7 assertions specified.
- Plan § G Wave 2 tests: 3 assertions specified.
- Plan § G Wave 3 tests: 2 assertions specified.
- Plan § G total spec'd: 12.
- **Shipped: 50** (additive — includes substrate edge cases, idempotency, supersede semantics, list/query coverage, INDEX maintenance). All PASS at merge. **Impact:** confidence is higher than spec; future regressions surface fast.
