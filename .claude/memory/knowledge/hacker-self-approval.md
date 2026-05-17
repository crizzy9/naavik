---
Topic: hacker-self-approval
Aliases: self-approval blocked, own author PR review, hacker COMMENTED state, GitHub PR review API restriction, pr-review-write pivot
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---

# hacker-self-approval

## Context

PR #50 (PC.6) was authored under the user's GitHub identity. When hacker attempted `pull_request_review_write` with method=`submit_pending` and state=`CHANGES_REQUESTED`, GitHub's API rejected the call: an author cannot formally approve or request changes on their own PR. Hacker pivoted to submit the review with state=`COMMENTED`, carrying the `REQUEST_CHANGES` verdict in the body text. Same root cause hits any agent-dispatched review running under the PR author's token.

## Resolution / pattern

When the dispatched hacker (or any reviewer) is the PR's author, submit reviews as `state=COMMENTED` with the verdict (`APPROVE` / `APPROVE_WITH_NOTES` / `REQUEST_CHANGES` / `BLOCK`) explicit in the body. The verdict in body is what manager parses at PR_REVIEW_GATE; the API state is cosmetic. Manager still honors hacker `BLOCK` regardless of GitHub state — codified in `.claude/agents/manager.md § PR review gate` ("Hacker `BLOCK` overrides any user 'Merge'").

## Related

- traces/2026-05-17T03-16-16_75a522/hacker.log:21 — the pivot event
- .claude/agents/manager.md § PR review gate — `BLOCK` override semantics
- .claude/agents/hacker.md § Verdict — verdict-in-body format spec
- docs/AGENT_OPS.md § 7.2 — `PR_REVIEW_POSTED` event format
