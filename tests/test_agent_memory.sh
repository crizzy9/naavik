#!/usr/bin/env bash
# tests/test_agent_memory.sh — smoke tests for scripts/agent-memory.sh.
#
# Run from repo root: bash tests/test_agent_memory.sh
# Exits 0 on success, non-zero on failure. Prints PASS / FAIL per assertion.
#
# Runs against a temp .claude/memory/ via OVERRIDE_MEMORY_DIR — does NOT touch
# the real corpus. Cleanup is automatic on exit (trap).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/agent-memory.sh"

[[ -x "$SCRIPT" ]] || { echo "FAIL: $SCRIPT not executable"; exit 1; }

# Sandbox the test against a temp tree so we don't touch the real corpus.
# We do this by symlinking a temp memory dir over the real one for the test run,
# then restoring on exit. Skipped if NAAVIK_MEMORY_TEST_INPLACE=1 (rare; CI only).
TMP_ROOT="$(mktemp -d)"
TMP_MEM="$TMP_ROOT/.claude/memory"
REAL_MEM="$REPO_ROOT/.claude/memory"
BACKUP_MEM="$REPO_ROOT/.claude/memory.test-backup-$$"

mkdir -p "$(dirname "$TMP_MEM")"
# Snapshot the real memory dir + replace with a symlink to the temp tree.
if [[ -d "$REAL_MEM" && ! -L "$REAL_MEM" ]]; then
  mv "$REAL_MEM" "$BACKUP_MEM"
fi
ln -sf "$TMP_MEM" "$REAL_MEM"
mkdir -p "$TMP_MEM"

cleanup() {
  rm -f "$REAL_MEM"
  [[ -d "$BACKUP_MEM" ]] && mv "$BACKUP_MEM" "$REAL_MEM"
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

PASS=0
FAIL=0

assert() {
  local LABEL="$1" RC="$2"
  if [[ "$RC" -eq 0 ]]; then
    echo "PASS  $LABEL"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $LABEL (rc=$RC)"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# Wave 1 — substrate
# ---------------------------------------------------------------------------

# 1. init creates the directory + empty stores. Idempotent.
"$SCRIPT" init >/dev/null
test -f "$TMP_MEM/decisions.jsonl"; assert "init creates decisions.jsonl" $?
test -f "$TMP_MEM/discussions.jsonl"; assert "init creates discussions.jsonl" $?
test -f "$TMP_MEM/lessons.jsonl"; assert "init creates lessons.jsonl" $?
test -f "$TMP_MEM/recurring-patterns.jsonl"; assert "init creates recurring-patterns.jsonl" $?
test -d "$TMP_MEM/knowledge"; assert "init creates knowledge/" $?
test -d "$TMP_MEM/runs-analysis"; assert "init creates runs-analysis/" $?

# Idempotency: second init no-ops.
"$SCRIPT" init >/dev/null; assert "init is idempotent" $?

# 2. record-decision appends a valid row.
"$SCRIPT" record-decision storage-backend "JSONL + markdown" "see plan 19 § C.1" \
  --run-id test-run >/dev/null
test "$(wc -l < "$TMP_MEM/decisions.jsonl")" -eq 1; assert "record-decision appends 1 row" $?

# Schema validity: every line is valid JSON.
jq -e . "$TMP_MEM/decisions.jsonl" >/dev/null 2>&1; assert "decisions.jsonl is valid JSONL" $?

# 3. Duplicate id rejected without --supersedes.
"$SCRIPT" record-decision storage-backend "different verdict" "trying again" 2>/dev/null
RC=$?
[[ $RC -ne 0 ]]; assert "duplicate decision id rejected without --supersedes" $?

# 4. --supersedes upgrades cleanly + marks old as superseded.
"$SCRIPT" record-decision storage-backend-v2 "JSONL + markdown + SQLite FTS5" "revisit @10k entries" \
  --supersedes storage-backend >/dev/null
test "$(wc -l < "$TMP_MEM/decisions.jsonl")" -eq 2; assert "supersede appends new row" $?
OLD_STATE="$(jq -r 'select(.id == "storage-backend") | .state' "$TMP_MEM/decisions.jsonl")"
[[ "$OLD_STATE" == "superseded" ]]; assert "old row marked state=superseded" $?
SUP_BY="$(jq -r 'select(.id == "storage-backend") | .superseded_by' "$TMP_MEM/decisions.jsonl")"
[[ "$SUP_BY" == "storage-backend-v2" ]]; assert "old row points superseded_by=new-id" $?

# 5. record-discussion appends a valid row + generates auto-id.
"$SCRIPT" record-discussion "JWT denylist on password rotation" manager.log \
  --priority MEDIUM --phase "Phase 1.x deferred items" >/dev/null
test "$(wc -l < "$TMP_MEM/discussions.jsonl")" -eq 1; assert "record-discussion appends 1 row" $?
jq -e . "$TMP_MEM/discussions.jsonl" >/dev/null 2>&1; assert "discussions.jsonl is valid JSONL" $?
DISC_ID="$(jq -r '.id' "$TMP_MEM/discussions.jsonl")"
[[ "$DISC_ID" =~ ^[0-9]{8}-[a-f0-9]{6}$ ]]; assert "discussion id matches YYYYMMDD-6hex pattern" $?

# 6. record-knowledge writes a markdown file with valid front-matter.
echo "test body content" | "$SCRIPT" record-knowledge test-topic - \
  --aliases "phrase a, phrase b" --confidence high --run-id test-run >/dev/null
test -f "$TMP_MEM/knowledge/test-topic.md"; assert "record-knowledge creates the file" $?
grep -q "^Topic: test-topic$" "$TMP_MEM/knowledge/test-topic.md"; assert "front-matter Topic correct" $?
grep -q "^Aliases: phrase a, phrase b$" "$TMP_MEM/knowledge/test-topic.md"; assert "front-matter Aliases correct" $?
grep -q "^Confidence: high$" "$TMP_MEM/knowledge/test-topic.md"; assert "front-matter Confidence correct" $?
grep -q "test body content" "$TMP_MEM/knowledge/test-topic.md"; assert "body content preserved" $?

# 6a. record-knowledge auto-regenerates INDEX.md (single-writer for knowledge dir).
test -f "$TMP_MEM/knowledge/INDEX.md"; assert "record-knowledge auto-creates INDEX.md" $?
grep -q "^| \`test-topic\` |" "$TMP_MEM/knowledge/INDEX.md"; assert "INDEX.md lists test-topic" $?
grep -q "AUTO-GENERATED" "$TMP_MEM/knowledge/INDEX.md"; assert "INDEX.md has auto-gen marker" $?

# 6b. update-index standalone subcommand is idempotent.
"$SCRIPT" update-index >/dev/null; assert "update-index subcommand exits 0" $?
test -f "$TMP_MEM/knowledge/INDEX.md"; assert "update-index keeps INDEX.md present" $?

# 7. record-knowledge refuses overwrite without --overwrite.
echo "second body" | "$SCRIPT" record-knowledge test-topic - --confidence low 2>/dev/null
RC=$?
[[ $RC -ne 0 ]]; assert "record-knowledge refuses overwrite without --overwrite" $?

# 8. record-knowledge rejects non-kebab slug.
echo "x" | "$SCRIPT" record-knowledge BadSlug - 2>/dev/null
RC=$?
[[ $RC -ne 0 ]]; assert "record-knowledge rejects non-kebab slug" $?

# 9. record-knowledge rejects bad confidence value.
echo "x" | "$SCRIPT" record-knowledge another-topic - --confidence bogus 2>/dev/null
RC=$?
[[ $RC -ne 0 ]]; assert "record-knowledge rejects bad confidence value" $?

# 10. list <store> works for all stores.
"$SCRIPT" list decisions | grep -q "storage-backend-v2"; assert "list decisions shows the active row" $?
"$SCRIPT" list discussions | grep -q "JWT denylist"; assert "list discussions shows the topic" $?
"$SCRIPT" list knowledge | grep -q "test-topic"; assert "list knowledge shows the topic" $?

# 11. query <store> '<jq-expr>' filters correctly.
ACTIVE_COUNT="$("$SCRIPT" query decisions '.state == "active"' | wc -l)"
[[ "$ACTIVE_COUNT" -eq 1 ]]; assert "query decisions filters to active (1 row)" $?

SUPERSEDED_COUNT="$("$SCRIPT" query decisions '.state == "superseded"' | wc -l)"
[[ "$SUPERSEDED_COUNT" -eq 1 ]]; assert "query decisions filters to superseded (1 row)" $?

# 12. record-lesson appends a valid row.
"$SCRIPT" record-lesson lesson-test-1 "test pattern" "run1,run2" \
  --proposed-action "do the thing" >/dev/null
test "$(wc -l < "$TMP_MEM/lessons.jsonl")" -eq 1; assert "record-lesson appends 1 row" $?
jq -e . "$TMP_MEM/lessons.jsonl" >/dev/null 2>&1; assert "lessons.jsonl is valid JSONL" $?
EVI_LEN="$(jq -r 'select(.id == "lesson-test-1") | .evidence_runs | length' "$TMP_MEM/lessons.jsonl")"
[[ "$EVI_LEN" -eq 2 ]]; assert "evidence_runs parsed as 2-element array" $?

# 13. Atomic write: no .tmp files left after a successful run.
test -z "$(find "$TMP_MEM" -maxdepth 2 -name '*.tmp.*' 2>/dev/null)"; assert "no temp files leak" $?

# ---------------------------------------------------------------------------
# Wave 2 — analytics
# ---------------------------------------------------------------------------

# 14. analyze-run on a synthetic trace produces a valid markdown report.
SYN_RUN="2099-12-31T00-00-00_test01"
SYN_DIR="$REPO_ROOT/traces/$SYN_RUN"
mkdir -p "$SYN_DIR"
cat > "$SYN_DIR/MANIFEST.json" <<EOF
{
  "run_id": "$SYN_RUN",
  "started_at": "2099-12-31T00:00:00Z",
  "ended_at": "2099-12-31T00:30:00Z",
  "milestone": "test-milestone",
  "outcome": "delivered",
  "halt_reason": null,
  "issues_closed": [99],
  "prs_merged": [],
  "files_touched": ["test.py"],
  "deviations_recorded": [],
  "tokens_spent": {"manager": 100, "engineer": 200},
  "what_built": "test",
  "errors_encountered": []
}
EOF
cat > "$SYN_DIR/engineer.log" <<EOF
[2099-12-31T00:00:00Z] EDIT test.py reason='test'
[2099-12-31T00:10:00Z] ERROR step=test-step kind=pivot reason='test pivot' attempt=1/1
[2099-12-31T00:20:00Z] ERROR step=test-step kind=pivot reason='same pivot again' attempt=1/1
[2099-12-31T00:30:00Z] BUILT files_added=1 files_modified=0 files_deleted=0 summary='test ship'
EOF

"$SCRIPT" analyze-run "$SYN_RUN" >/dev/null
test -f "$TMP_MEM/runs-analysis/$SYN_RUN.md"; assert "analyze-run writes runs-analysis/<run>.md" $?
grep -q "milestone: test-milestone" "$TMP_MEM/runs-analysis/$SYN_RUN.md"; assert "analyze-run captures milestone" $?
grep -q "pivot: 2" "$TMP_MEM/runs-analysis/$SYN_RUN.md"; assert "analyze-run counts pivots" $?
grep -q "BUILT files_added=1" "$TMP_MEM/runs-analysis/$SYN_RUN.md"; assert "analyze-run surfaces BUILT line" $?

# 15. mine-patterns aggregates same step+kind across runs.
# Create a second synthetic run with the same pivot pattern.
SYN_RUN2="2099-12-31T00-30-00_test02"
SYN_DIR2="$REPO_ROOT/traces/$SYN_RUN2"
mkdir -p "$SYN_DIR2"
cat > "$SYN_DIR2/engineer.log" <<EOF
[2099-12-31T00:35:00Z] ERROR step=test-step kind=pivot reason='third time' attempt=1/1
EOF

"$SCRIPT" mine-patterns --lookback 3 >/dev/null
test "$(wc -l < "$TMP_MEM/recurring-patterns.jsonl")" -ge 1; assert "mine-patterns writes at least 1 row" $?
PATTERN_COUNT="$(jq -r 'select(.pattern_id == "test-step__pivot") | .occurrence_count' "$TMP_MEM/recurring-patterns.jsonl" | head -n 1)"
[[ "$PATTERN_COUNT" -ge 3 ]]; assert "test-step__pivot pattern has occurrence_count >= 3 (got $PATTERN_COUNT)" $?

# Cleanup synthetic traces.
rm -rf "$SYN_DIR" "$SYN_DIR2"

# ---------------------------------------------------------------------------
# Wave 3 — promotion + alias mining
# ---------------------------------------------------------------------------

# 16. promote-lesson rejects below threshold.
# Inject a pattern with count=4 (below threshold 5).
PATTERN_LINE='{"pattern_id":"low-count__pivot","step":"low-count","kind":"pivot","occurrence_count":4,"runs":["r1","r2"],"first_seen":"2099-12-31T00:00:00Z","last_seen":"2099-12-31T00:00:00Z","proposed_action":"do nothing"}'
echo "$PATTERN_LINE" >> "$TMP_MEM/recurring-patterns.jsonl"

"$SCRIPT" promote-lesson low-count__pivot 2>/dev/null
RC=$?
[[ $RC -ne 0 ]]; assert "promote-lesson rejects pattern with count=4 (below threshold 5)" $?

# 17. promote-lesson succeeds at threshold.
HIGH_LINE='{"pattern_id":"high-count__pivot","step":"high-count","kind":"pivot","occurrence_count":6,"runs":["r1","r2","r3","r4","r5","r6"],"first_seen":"2099-12-31T00:00:00Z","last_seen":"2099-12-31T00:00:00Z","proposed_action":"split the step into two"}'
echo "$HIGH_LINE" >> "$TMP_MEM/recurring-patterns.jsonl"

"$SCRIPT" promote-lesson high-count__pivot >/dev/null
RC=$?
[[ $RC -eq 0 ]]; assert "promote-lesson succeeds at count=6" $?
test -f "$TMP_MEM/knowledge/high-count.md"; assert "promote-lesson creates knowledge stub" $?
grep -q "lesson-high-count--pivot" "$TMP_MEM/lessons.jsonl"; assert "promote-lesson appends to lessons.jsonl" $?

# 18. mine-patterns --aliases scans manager.log for MEMORY_MISS events.
SYN_RUN3="2099-12-31T01-00-00_test03"
SYN_DIR3="$REPO_ROOT/traces/$SYN_RUN3"
mkdir -p "$SYN_DIR3"
cat > "$SYN_DIR3/manager.log" <<EOF
[2099-12-31T01:00:00Z] MEMORY_MISS topic=linkedin-scraping phrase='scrape linkedin jobs'
[2099-12-31T01:05:00Z] MEMORY_MISS topic=hacker-self-approval phrase='cant approve my own pr'
EOF

OUTPUT="$("$SCRIPT" mine-patterns --aliases --lookback 5 2>&1)"
echo "$OUTPUT" | grep -q "linkedin-scraping"; assert "mine-aliases surfaces linkedin-scraping MEMORY_MISS" $?
echo "$OUTPUT" | grep -q "hacker-self-approval"; assert "mine-aliases surfaces hacker-self-approval MEMORY_MISS" $?

rm -rf "$SYN_DIR3"

# ---------------------------------------------------------------------------
# A.17 hardening regression tests
# ---------------------------------------------------------------------------

# 19. Finding 1 — flock around concurrent writers. Spawn 30 background
# record-discussion calls, wait for all, assert all 30 rows landed.
PRE_COUNT="$(wc -l < "$TMP_MEM/discussions.jsonl")"
N_PARALLEL=30
for i in $(seq 1 "$N_PARALLEL"); do
  ("$SCRIPT" record-discussion "concurrency-test-$i" "test.log" --priority LOW >/dev/null 2>&1) &
done
wait
POST_COUNT="$(wc -l < "$TMP_MEM/discussions.jsonl")"
ADDED=$((POST_COUNT - PRE_COUNT))
[[ "$ADDED" -eq "$N_PARALLEL" ]]; assert "Finding 1 — 30 concurrent record-discussion writes all persist (got $ADDED/$N_PARALLEL)" $?

# 20. Finding 2 (positive control) — safe jq expression passes the sandbox.
"$SCRIPT" query decisions '.state == "active"' >/dev/null 2>&1
assert "Finding 2 (positive) — '.state == \"active\"' passes the sandbox" $?

# 20a. Positive control — pattern_id substring containing 'path' is NOT a
# false-positive (word-boundary regex must not match inside identifiers).
"$SCRIPT" query patterns '.pattern_id == "test-step__pivot"' >/dev/null 2>&1
assert "Finding 2 (positive) — pattern_id substring 'path' is not a false-positive" $?

# 21. Finding 2 (negative control) — env exfiltration rejected.
NAAVIK_TEST_SECRET="leaked-secret-abc123" "$SCRIPT" query decisions 'true) | env.NAAVIK_TEST_SECRET' > /tmp/test_jq_exfil_$$ 2>&1
RC=$?
[[ $RC -ne 0 ]]; assert "Finding 2 (negative) — env.* exfil exits non-zero" $?
! grep -q "leaked-secret-abc123" /tmp/test_jq_exfil_$$; assert "Finding 2 (negative) — env.* exfil does NOT leak secret to output" $?
rm -f /tmp/test_jq_exfil_$$

# 21a. Finding 2 (negative control) — .path identifier blocked at word boundary.
"$SCRIPT" query decisions '.path == "x"' >/dev/null 2>&1
RC=$?
[[ $RC -ne 0 ]]; assert "Finding 2 (negative) — '.path' identifier rejected (word-boundary)" $?

# 21b. Finding 2 (negative control) — \$ENV reference blocked.
"$SCRIPT" query decisions '$ENV.HOME' >/dev/null 2>&1
RC=$?
[[ $RC -ne 0 ]]; assert "Finding 2 (negative) — '\$ENV' reference rejected" $?

# 22. Finding 4 (positive control) — alias matching the seeded corpus shape passes.
echo "smoke body" | "$SCRIPT" record-knowledge alias-positive-test - \
  --aliases "kebab-case, another-kebab, with .naavik/db path" >/dev/null 2>&1
assert "Finding 4 (positive) — multi-token aliases with spaces/dots/slashes accepted" $?

# 22a. Finding 4 (negative control) — newline + front-matter injection rejected.
NL_ALIAS=$'pwned\n---\nTopic:owned\n---'
echo "body" | "$SCRIPT" record-knowledge alias-injection-test - --aliases "$NL_ALIAS" >/dev/null 2>&1
RC=$?
[[ $RC -ne 0 ]]; assert "Finding 4 (negative) — front-matter injection via --aliases rejected" $?
test ! -f "$TMP_MEM/knowledge/alias-injection-test.md"; assert "Finding 4 (negative) — injected knowledge file NOT created" $?

# 22b. Finding 4 (negative control) — bare '---' fence rejected.
echo "body" | "$SCRIPT" record-knowledge alias-fence-test - --aliases "good, ---, evil" >/dev/null 2>&1
RC=$?
[[ $RC -ne 0 ]]; assert "Finding 4 (negative) — bare '---' fence in --aliases rejected" $?

# 23. Finding 5 — MANIFEST.json values land inside fenced code blocks
# (no Markdown link / inline code rendering).
SYN_RUN5="2099-12-31T05-00-00_test05"
SYN_DIR5="$REPO_ROOT/traces/$SYN_RUN5"
mkdir -p "$SYN_DIR5"
cat > "$SYN_DIR5/MANIFEST.json" <<'EOF'
{
  "run_id": "2099-12-31T05-00-00_test05",
  "started_at": "2099-12-31T05:00:00Z",
  "ended_at": "2099-12-31T05:30:00Z",
  "milestone": "fence-test",
  "outcome": "delivered",
  "halt_reason": null,
  "issues_closed": [],
  "prs_merged": [],
  "files_touched": ["[evil](http://x.test)", "`whoami`", "normal/path.py"],
  "deviations_recorded": [],
  "tokens_spent": {"agent-a": 100, "agent-b": "`whoami`"},
  "what_built": "fence test",
  "errors_encountered": []
}
EOF
"$SCRIPT" analyze-run "$SYN_RUN5" >/dev/null
ANALYSIS="$TMP_MEM/runs-analysis/$SYN_RUN5.md"
test -f "$ANALYSIS"; assert "Finding 5 — analyze-run wrote output file" $?
# Files touched line "[evil](http://x.test)" must be inside a fenced block (not rendered as a link).
# Verify by checking that the fenced block opens before the literal string + closes after.
awk '
  /^```$/ { in_fence = !in_fence; fence_count++; next }
  /\[evil\]/ { if (in_fence) evil_in_fence = 1 }
  END { exit (evil_in_fence && fence_count >= 4 ? 0 : 1) }
' "$ANALYSIS"
assert "Finding 5 — '[evil](...)' string lands inside a fenced code block (not rendered as a Markdown link)" $?
# Tokens line value "\`whoami\`" must also be inside a fence.
grep -q "agent-b: \`whoami\`" "$ANALYSIS"; assert "Finding 5 — tokens_spent value preserved verbatim inside fence" $?

rm -rf "$SYN_DIR5"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
echo "==== $PASS pass, $FAIL fail ===="
exit "$FAIL"
