---
Topic: sandbox-post-direct-push
Aliases: sandbox denial gh issue create, post-direct-push gh subcommand blocked, BOOKKEEPING push, follow-up issue deferred, .claude/naavik-ops gh create-issue halt
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---

# sandbox-post-direct-push

## Context

After PR #50 merged, manager ran the BOOKKEEPING direct push of `c158320` to `main` (ROADMAP row flip + new PC.6a + JWT-denylist follow-up rows). Immediately after, manager attempted `.claude/naavik-ops gh create-issue PC.6a ...` to mirror the new ROADMAP rows onto the GitHub Project board. The sandbox denied the `gh issue create` subcommand — auto-mode treats the post-direct-push state as elevated and blocks subsequent destructive (in the API sense) calls until the next user turn. Manager halted and deferred the Project board sync to the next session.

## Resolution / pattern

After a direct push to `main` (BOOKKEEPING), pause before invoking any `.claude/naavik-ops gh create-issue` / `create-epic` / `set-status` operation. If the sandbox denies, file the follow-up sync as a one-line note in `manager.log` (`BLOCKED action=... reason='sandbox denial post-direct-push'`) and complete the sync in the next session. Manager's `ERROR step=gh-project.sh-create-issue kind=halt reason='sandbox denial after direct-push'` event captures the deferral. This is operational — the persistent issue-map cache and ROADMAP are still authoritative; only the Project mirror is briefly stale.

## Related

- traces/2026-05-17T03-16-16_75a522/MANIFEST.json:errors_encountered[4]
- traces/2026-05-17T03-16-16_75a522/manager.log — BLOCKED event
- AGENTS.md § GitHub state — single writer rule
- docs/AGENT_OPS.md § 6.6 — single-writer + refresh-map reconciler
