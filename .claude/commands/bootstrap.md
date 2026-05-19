---
description: First-time setup for the agent system. Caches GitHub Project IDs + creates Milestones + opens Issues from ROADMAP.md. Run once per fork.
argument-hint: [--apply]
---

Bootstrap Naavik agent system. Per `docs/AGENT_OPS.md` § 2 + CLAUDE.md § "GitHub state — single writer rule".

**Pre-flight checks** (do these first, report failures):
1. `gh auth status` — confirm `gh` is authenticated. Not authenticated → instruct user to run `gh auth login` (suggest they paste `! gh auth login` so it runs in this session).
2. Confirm `.claude/naavik-ops` + `.claude/naavik_ops/gh.py` + `.claude/naavik_ops/lib/roadmap.py` exist + executable (dispatcher subprocess-wraps the legacy scripts during A.29).
3. Check `.claude/github-project.json` — exists → ask user whether to re-init or skip.
4. Check `.claude/github-issue-map.json` — exists → note when last refreshed (`jq '._meta.refreshed_at' .claude/github-issue-map.json`); older than ~7 days OR missing → plan to run `.claude/naavik-ops gh refresh-map` before dry-run so existence checks use fresh cache instead of eventually-consistent search API.
5. Check `.claude/budget.json` exists.

**Step 1 — Init (only if cache missing or user requested re-init):**

Tell user: "Before running init, confirm you've created GitHub Project v2 in web UI w/ Status field (Todo / In Progress / Done / Backlog — Backlog added 2026-05-17 per A.28) + Priority field (CRITICAL / HIGH / MEDIUM / LOW). See `docs/AGENT_OPS.md` § 2.2 for walkthrough. Your Project was set up before A.28 w/ only 3 status options → run `.claude/naavik-ops gh add-status Backlog --color GRAY` after init to add fourth option."

Then run:
```
.claude/naavik-ops gh init
```

(`init` is interactive — prompts for owner / repo / project number. Can't run for them in non-interactive mode; print command + let them paste `! .claude/naavik-ops gh init`.)

**Step 1b — Refresh map (always before dry-run, unless cache is < ~1h old):**

```
.claude/naavik-ops gh refresh-map
```

Rebuilds `.claude/github-issue-map.json` from authoritative GitHub state. **Critical** — dry-run consults map first; if map is stale or missing, dry-run falls back to eventually-consistent search API (~30s–2min indexing lag) + may report `PLAN` for issues that already exist, tricking apply into creating duplicates. Skipping refresh-map is how original `#46`/`#47` duplicates were created. Always run unless you just refreshed it earlier in same session.

**Step 2 — Bootstrap dry-run:**

```
.claude/naavik-ops gh bootstrap
```

Prints what milestones + epics + issues would be created without mutating anything. Output distinguishes `exists` (already in GitHub) from `PLAN` (would be created) for milestones AND epics AND child issues — older versions of script only reported epics/milestones as "would create if missing" regardless of state. See `PLAN` rows you didn't expect → sanity-check via `gh issue list --search "[task-id] in:title"` before apply; script's existence check is now map-cached, so `PLAN` row almost always means issue truly doesn't exist (unless someone closed it manually + forgot to delete map entry — re-run `refresh-map` to be safe).

Present dry-run output to user via AskUserQuestion: Approve all / Limit to specific phases (via `--phase=NAME`) / Cancel.

**Step 3 — Bootstrap apply (only with user approval):**

Args contained `--apply` OR user approves in step 2 → run:
```
.claude/naavik-ops gh bootstrap --apply
```

(Append any `--phase=X` flags user specified.)

**Step 4 — Verify:**

```
.claude/naavik-ops gh milestone-status
.claude/naavik-ops gh next-unblocked
```

Print output. Confirm at least one issue landed + `next-unblocked` returns non-null item.

**Step 5 — Wrap-up:**

Print:
- Number of Milestones created / already-existed.
- Number of Issues created / skipped.
- "Next steps" recommendation: `claude /standup` to see state, `claude /build "next"` to deliver.
- Pointer to `docs/AGENT_OPS.md` for full reference.

**Anything fails:** print failing command + error verbatim, refer user to `docs/AGENT_OPS.md` § 9 Troubleshooting.
