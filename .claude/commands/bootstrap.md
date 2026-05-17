---
description: First-time setup for the agent system. Caches GitHub Project IDs + creates Milestones + opens Issues from ROADMAP.md. Run once per fork.
argument-hint: [--apply]
---

Bootstrap the Naavik agent system. Per `docs/AGENT_OPS.md` § 2 and CLAUDE.md § "GitHub state — single writer rule".

**Pre-flight checks** (do these first, report any failures):
1. `gh auth status` — confirm `gh` is authenticated. If not, instruct the user to run `gh auth login` (suggest they paste `! gh auth login` so it runs in this session).
2. Confirm `scripts/gh-project.sh` and `scripts/roadmap_parser.py` exist + executable.
3. Check `.claude/github-project.json` — if it exists, ask the user whether to re-init or skip.
4. Check `.claude/github-issue-map.json` — if it exists, note when it was last refreshed (`jq '._meta.refreshed_at' .claude/github-issue-map.json`); if older than ~7 days OR missing, plan to run `scripts/gh-project.sh refresh-map` before the dry-run so existence checks use a fresh cache instead of the eventually-consistent search API.
5. Check `.claude/budget.json` exists.

**Step 1 — Init (only if cache missing or user requested re-init):**

Tell the user: "Before running init, confirm you've created the GitHub Project v2 in the web UI with a Status field (Todo / In Progress / Done / Backlog — Backlog added 2026-05-17 per A.28) and a Priority field (CRITICAL / HIGH / MEDIUM / LOW). See `docs/AGENT_OPS.md` § 2.2 for the walkthrough. If your Project was set up before A.28 with only 3 status options, run `scripts/gh-project.sh add-status Backlog --color GRAY` after init to add the fourth option."

Then run:
```
scripts/gh-project.sh init
```

(`init` is interactive — prompts for owner / repo / project number. You can't run this for them in non-interactive mode; print the command and let them paste `! scripts/gh-project.sh init`.)

**Step 1b — Refresh map (always before dry-run, unless cache is < ~1h old):**

```
scripts/gh-project.sh refresh-map
```

This rebuilds `.claude/github-issue-map.json` from authoritative GitHub state. **This is critical** — the dry-run consults the map first; if the map is stale or missing, the dry-run falls back to the eventually-consistent search API (~30s–2min indexing lag) and may report `PLAN` for issues that already exist, tricking apply into creating duplicates. Skipping refresh-map is how the original `#46`/`#47` duplicates were created. Always run unless you just refreshed it earlier in the same session.

**Step 2 — Bootstrap dry-run:**

```
scripts/gh-project.sh bootstrap
```

This prints what milestones + epics + issues would be created without mutating anything. The output now distinguishes `exists` (already in GitHub) from `PLAN` (would be created) for milestones AND epics AND child issues — older versions of the script only reported epics/milestones as "would create if missing" regardless of state. If you see `PLAN` rows you didn't expect, sanity-check via `gh issue list --search "[task-id] in:title"` before apply; the script's existence check is now map-cached, so a `PLAN` row almost always means the issue truly doesn't exist (unless someone closed it manually and forgot to delete the map entry — re-run `refresh-map` to be safe).

Present the dry-run output to the user via AskUserQuestion: Approve all / Limit to specific phases (via `--phase=NAME`) / Cancel.

**Step 3 — Bootstrap apply (only with user approval):**

If args contained `--apply` OR user approves in step 2, run:
```
scripts/gh-project.sh bootstrap --apply
```

(Append any `--phase=X` flags the user specified.)

**Step 4 — Verify:**

```
scripts/gh-project.sh milestone-status
scripts/gh-project.sh next-unblocked
```

Print the output. Confirm at least one issue landed and `next-unblocked` returns a non-null item.

**Step 5 — Wrap-up:**

Print:
- Number of Milestones created / already-existed.
- Number of Issues created / skipped.
- The "next steps" recommendation: `claude /standup` to see state, `claude /build "next"` to deliver.
- Pointer to `docs/AGENT_OPS.md` for the full reference.

**If anything fails:** print the failing command + error verbatim, and refer the user to `docs/AGENT_OPS.md` § 9 Troubleshooting.
