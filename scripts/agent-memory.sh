#!/usr/bin/env bash
# scripts/agent-memory.sh — single writer for .claude/memory/ stores.
#
# Mirrors scripts/gh-project.sh conventions (set -euo pipefail, atomic mktemp+mv,
# subcommand dispatch, --help via no-args). Sole writer to:
#   .claude/memory/decisions.jsonl
#   .claude/memory/discussions.jsonl
#   .claude/memory/lessons.jsonl
#   .claude/memory/recurring-patterns.jsonl
#   .claude/memory/knowledge/<topic>.md
#   .claude/memory/runs-analysis/<run-id>.md
#
# Append-only invariant on JSONL — duplicate ids rejected unless --supersede.
# Knowledge files supported via record-knowledge (front-matter validated).
#
# Wave 1 subcommands: init record-decision record-discussion record-knowledge
#                     record-lesson list query seed.
# Wave 2 subcommands: analyze-run mine-patterns.
# Wave 3 subcommands: promote-lesson, mine-patterns --aliases.
#
# Companion: docs/design/AGENT_MEMORY.md, docs/AGENT_OPS.md § 14.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEMORY_DIR="$REPO_ROOT/.claude/memory"
DECISIONS="$MEMORY_DIR/decisions.jsonl"
DISCUSSIONS="$MEMORY_DIR/discussions.jsonl"
LESSONS="$MEMORY_DIR/lessons.jsonl"
PATTERNS="$MEMORY_DIR/recurring-patterns.jsonl"
KNOWLEDGE_DIR="$MEMORY_DIR/knowledge"
RUNS_DIR="$MEMORY_DIR/runs-analysis"

PROMOTION_THRESHOLD=5

require_jq() {
  command -v jq >/dev/null 2>&1 || { echo "error: jq not on PATH. nix develop." >&2; exit 1; }
}

now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

today_iso() {
  date -u +%Y-%m-%d
}

# Atomic JSONL append: lock-free; reader sees pre or post, never mid-line.
append_jsonl() {
  local FILE="$1" LINE="$2"
  mkdir -p "$(dirname "$FILE")"
  [[ -f "$FILE" ]] || : > "$FILE"
  local TMP="$FILE.tmp.$$"
  cat "$FILE" > "$TMP"
  printf '%s\n' "$LINE" >> "$TMP"
  mv "$TMP" "$FILE"
}

# Validate JSONL line via jq before append. Refuses malformed input.
validate_json() {
  local LINE="$1"
  echo "$LINE" | jq -e . >/dev/null 2>&1 || { echo "error: malformed JSON: $LINE" >&2; exit 1; }
}

# Find a JSONL row by id. Echoes the matching line; empty if absent.
find_by_id() {
  local FILE="$1" ID="$2"
  [[ -f "$FILE" ]] || return 0
  jq -c --arg id "$ID" 'select(.id == $id)' "$FILE" 2>/dev/null | head -n 1
}

# Mark an existing decision/lesson row as superseded by a new id.
# Rewrites file atomically; preserves all other rows.
mark_superseded() {
  local FILE="$1" OLD_ID="$2" NEW_ID="$3"
  [[ -f "$FILE" ]] || return 0
  local TMP="$FILE.tmp.$$"
  jq -c --arg old "$OLD_ID" --arg new "$NEW_ID" \
    'if .id == $old then .state = "superseded" | .superseded_by = $new else . end' \
    "$FILE" > "$TMP"
  mv "$TMP" "$FILE"
}

# ===========================================================================
# init — create dirs + empty stores. Idempotent.
# ===========================================================================

cmd_init() {
  mkdir -p "$MEMORY_DIR" "$KNOWLEDGE_DIR" "$RUNS_DIR"
  for f in "$DECISIONS" "$DISCUSSIONS" "$LESSONS" "$PATTERNS"; do
    [[ -f "$f" ]] || : > "$f"
  done
  [[ -f "$MEMORY_DIR/.keep" ]] || : > "$MEMORY_DIR/.keep"
  echo "init: $MEMORY_DIR (4 JSONL stores + knowledge/ + runs-analysis/)"
}

# ===========================================================================
# record-decision <id> <verdict> <rationale> [--supersedes <old-id>]
# ===========================================================================
#
# Schema:
#   { id, verdict, rationale, captured_at, state: "active"|"superseded",
#     superseded_by?: <new-id>, run_id?: <run-id> }

cmd_record_decision() {
  require_jq; cmd_init >/dev/null
  local ID="${1:?usage: record-decision <id> <verdict> <rationale> [--supersedes <old-id>] [--run-id <run-id>]}"
  local VERDICT="${2:?usage: record-decision <id> <verdict> <rationale>}"
  local RATIONALE="${3:?usage: record-decision <id> <verdict> <rationale>}"
  shift 3
  local SUPERSEDES="" RUN_ID=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --supersedes) SUPERSEDES="$2"; shift 2 ;;
      --run-id) RUN_ID="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  local EXISTING
  EXISTING="$(find_by_id "$DECISIONS" "$ID")"
  if [[ -n "$EXISTING" && -z "$SUPERSEDES" ]]; then
    echo "error: decision '$ID' exists. Use --supersedes <old-id> to upgrade." >&2
    exit 1
  fi

  local LINE
  LINE="$(jq -nc \
    --arg id "$ID" --arg v "$VERDICT" --arg r "$RATIONALE" \
    --arg ts "$(now_iso)" --arg sup "$SUPERSEDES" --arg run "$RUN_ID" \
    '{id: $id, verdict: $v, rationale: $r, captured_at: $ts, state: "active"}
     | if $sup != "" then . + {supersedes: $sup} else . end
     | if $run != "" then . + {run_id: $run} else . end')"

  validate_json "$LINE"

  if [[ -n "$SUPERSEDES" ]]; then
    mark_superseded "$DECISIONS" "$SUPERSEDES" "$ID"
  fi

  append_jsonl "$DECISIONS" "$LINE"
  echo "decision: $ID"
}

# ===========================================================================
# record-discussion <topic> <surface> [--phase <phase>] [--priority <P>] [--filed-as <#N>] [--run-id <run-id>]
# ===========================================================================
#
# Schema:
#   { id (auto), topic, surface, phase?, priority?, filed_as?, captured_at, run_id? }
# Auto-id: <YYYYMMDD>-<random-6hex>. Append-only; no supersede semantics.

cmd_record_discussion() {
  require_jq; cmd_init >/dev/null
  local TOPIC="${1:?usage: record-discussion <topic> <surface> [--phase X] [--priority P] [--filed-as #N] [--run-id ID]}"
  local SURFACE="${2:?usage: record-discussion <topic> <surface>}"
  shift 2
  local PHASE="" PRIORITY="MEDIUM" FILED="" RUN_ID=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --phase) PHASE="$2"; shift 2 ;;
      --priority) PRIORITY="${2^^}"; shift 2 ;;
      --filed-as) FILED="$2"; shift 2 ;;
      --run-id) RUN_ID="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  local ID
  ID="$(today_iso | tr -d -)-$(head -c 3 /dev/urandom | od -An -tx1 | tr -d ' \n')"

  local LINE
  LINE="$(jq -nc \
    --arg id "$ID" --arg t "$TOPIC" --arg s "$SURFACE" \
    --arg ph "$PHASE" --arg pr "$PRIORITY" --arg f "$FILED" \
    --arg ts "$(now_iso)" --arg run "$RUN_ID" \
    '{id: $id, topic: $t, surface: $s, priority: $pr, captured_at: $ts}
     | if $ph != "" then . + {phase: $ph} else . end
     | if $f != "" then . + {filed_as: $f} else . end
     | if $run != "" then . + {run_id: $run} else . end')"

  validate_json "$LINE"
  append_jsonl "$DISCUSSIONS" "$LINE"
  echo "discussion: $ID"
}

# ===========================================================================
# record-knowledge <topic-slug> <body-source> [--aliases "a, b, c"]
#                  [--confidence H|M|L] [--supersedes <slug>] [--overwrite]
# ===========================================================================
#
# Writes .claude/memory/knowledge/<slug>.md with validated front-matter.
# body-source: path to file OR "-" for stdin.
# Refuses overwrite unless --overwrite (preserves the append-only spirit;
# updates produce a new file via --supersedes for traceability).

cmd_record_knowledge() {
  require_jq; cmd_init >/dev/null
  local SLUG="${1:?usage: record-knowledge <topic-slug> <body-source|-> [--aliases ...] [--confidence H|M|L] [--supersedes <slug>] [--overwrite] [--run-id ID]}"
  local SRC="${2:?usage: record-knowledge <topic-slug> <body-source|->}"
  shift 2
  local ALIASES="" CONFIDENCE="medium" SUPERSEDES="none" OVERWRITE=false RUN_ID=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --aliases) ALIASES="$2"; shift 2 ;;
      --confidence) CONFIDENCE="$(echo "${2,,}" | sed 's/^h$/high/; s/^m$/medium/; s/^l$/low/')"; shift 2 ;;
      --supersedes) SUPERSEDES="$2"; shift 2 ;;
      --overwrite) OVERWRITE=true; shift ;;
      --run-id) RUN_ID="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  case "$CONFIDENCE" in high|medium|low) ;; *) echo "error: confidence must be high|medium|low" >&2; exit 1 ;; esac
  [[ "$SLUG" =~ ^[a-z0-9-]+$ ]] || { echo "error: slug must be kebab-case [a-z0-9-]" >&2; exit 1; }

  local OUT="$KNOWLEDGE_DIR/$SLUG.md"
  if [[ -f "$OUT" && "$OVERWRITE" == false ]]; then
    echo "error: $OUT exists. Use --overwrite or --supersedes <slug>." >&2
    exit 1
  fi

  local BODY
  if [[ "$SRC" == "-" ]]; then
    BODY="$(cat)"
  else
    [[ -f "$SRC" ]] || { echo "error: body-source '$SRC' not found" >&2; exit 1; }
    BODY="$(cat "$SRC")"
  fi

  local TODAY RUN_LINE=""
  TODAY="$(today_iso)"
  [[ -n "$RUN_ID" ]] && RUN_LINE=" (run $RUN_ID)"

  local TMP="$OUT.tmp.$$"
  cat > "$TMP" <<EOF
---
Topic: $SLUG
Aliases: $ALIASES
First captured: $TODAY$RUN_LINE
Last referenced: $TODAY
Supersedes: $SUPERSEDES
Confidence: $CONFIDENCE
---

$BODY
EOF
  mv "$TMP" "$OUT"
  echo "knowledge: $OUT"
}

# ===========================================================================
# record-lesson <id> <pattern> <evidence-runs> [--supersedes <id>] [--proposed-action "..."]
# ===========================================================================
#
# Schema:
#   { id, pattern, evidence_runs[], proposed_action?, captured_at, state, run_id? }

cmd_record_lesson() {
  require_jq; cmd_init >/dev/null
  local ID="${1:?usage: record-lesson <id> <pattern> <evidence-runs-csv> [--proposed-action ...] [--supersedes <id>] [--run-id ID]}"
  local PATTERN="${2:?usage: record-lesson <id> <pattern> <evidence-runs-csv>}"
  local EVIDENCE="${3:?usage: record-lesson <id> <pattern> <evidence-runs-csv>}"
  shift 3
  local SUPERSEDES="" ACTION="" RUN_ID=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --supersedes) SUPERSEDES="$2"; shift 2 ;;
      --proposed-action) ACTION="$2"; shift 2 ;;
      --run-id) RUN_ID="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  local EXISTING
  EXISTING="$(find_by_id "$LESSONS" "$ID")"
  if [[ -n "$EXISTING" && -z "$SUPERSEDES" ]]; then
    echo "error: lesson '$ID' exists. Use --supersedes <old-id> to upgrade." >&2
    exit 1
  fi

  local EVIDENCE_JSON
  EVIDENCE_JSON="$(echo "$EVIDENCE" | jq -Rc 'split(",") | map(gsub("^\\s+|\\s+$"; ""))')"

  local LINE
  LINE="$(jq -nc \
    --arg id "$ID" --arg p "$PATTERN" --argjson e "$EVIDENCE_JSON" \
    --arg a "$ACTION" --arg ts "$(now_iso)" --arg sup "$SUPERSEDES" --arg run "$RUN_ID" \
    '{id: $id, pattern: $p, evidence_runs: $e, captured_at: $ts, state: "active"}
     | if $a != "" then . + {proposed_action: $a} else . end
     | if $sup != "" then . + {supersedes: $sup} else . end
     | if $run != "" then . + {run_id: $run} else . end')"

  validate_json "$LINE"

  if [[ -n "$SUPERSEDES" ]]; then
    mark_superseded "$LESSONS" "$SUPERSEDES" "$ID"
  fi

  append_jsonl "$LESSONS" "$LINE"
  echo "lesson: $ID"
}

# ===========================================================================
# list <store>
# ===========================================================================

cmd_list() {
  require_jq
  local STORE="${1:?usage: list <decisions|discussions|lessons|patterns|knowledge|runs>}"
  case "$STORE" in
    decisions)
      [[ -f "$DECISIONS" ]] || { echo "(no decisions yet)"; return 0; }
      jq -r '"\(.id)\t\(.verdict)\t\(.state)\t\(.captured_at)"' "$DECISIONS" \
        | awk -F'\t' 'BEGIN{printf "%-40s %-20s %-12s %s\n","ID","VERDICT","STATE","CAPTURED"} {printf "%-40s %-20s %-12s %s\n",$1,$2,$3,$4}'
      ;;
    discussions)
      [[ -f "$DISCUSSIONS" ]] || { echo "(no discussions yet)"; return 0; }
      jq -r '"\(.id)\t\(.topic)\t\(.priority)\t\(.filed_as // "-")"' "$DISCUSSIONS" \
        | awk -F'\t' 'BEGIN{printf "%-22s %-50s %-10s %s\n","ID","TOPIC","PRIORITY","FILED-AS"} {printf "%-22s %-50s %-10s %s\n",$1,$2,$3,$4}'
      ;;
    lessons)
      [[ -f "$LESSONS" ]] || { echo "(no lessons yet)"; return 0; }
      jq -r '"\(.id)\t\(.pattern)\t\(.state)\t\((.evidence_runs|length))"' "$LESSONS" \
        | awk -F'\t' 'BEGIN{printf "%-30s %-60s %-12s %s\n","ID","PATTERN","STATE","RUNS"} {printf "%-30s %-60s %-12s %s\n",$1,$2,$3,$4}'
      ;;
    patterns)
      [[ -f "$PATTERNS" ]] || { echo "(no patterns yet)"; return 0; }
      jq -r '"\(.pattern_id)\t\(.occurrence_count)\t\(.first_seen)\t\(.last_seen)"' "$PATTERNS" \
        | awk -F'\t' 'BEGIN{printf "%-40s %-6s %-22s %s\n","PATTERN-ID","N","FIRST-SEEN","LAST-SEEN"} {printf "%-40s %-6s %-22s %s\n",$1,$2,$3,$4}'
      ;;
    knowledge)
      [[ -d "$KNOWLEDGE_DIR" ]] || { echo "(no knowledge yet)"; return 0; }
      printf "%-40s %-12s %s\n" "TOPIC" "CONFIDENCE" "ALIASES"
      for f in "$KNOWLEDGE_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        local slug aliases conf
        slug="$(basename "$f" .md)"
        aliases="$(awk -F': ' '/^Aliases:/{print $2; exit}' "$f")"
        conf="$(awk -F': ' '/^Confidence:/{print $2; exit}' "$f")"
        printf "%-40s %-12s %s\n" "$slug" "$conf" "$aliases"
      done
      ;;
    runs|runs-analysis)
      [[ -d "$RUNS_DIR" ]] || { echo "(no runs analyzed yet)"; return 0; }
      printf "%-40s %s\n" "RUN-ID" "SIZE"
      for f in "$RUNS_DIR"/*.md; do
        [[ -f "$f" ]] || continue
        printf "%-40s %s\n" "$(basename "$f" .md)" "$(wc -c < "$f")"
      done
      ;;
    *)
      echo "error: unknown store '$STORE' (decisions|discussions|lessons|patterns|knowledge|runs)" >&2
      exit 1
      ;;
  esac
}

# ===========================================================================
# query <store> <jq-expression>
# ===========================================================================

cmd_query() {
  require_jq
  local STORE="${1:?usage: query <decisions|discussions|lessons|patterns> '<jq-expr>'}"
  local EXPR="${2:?usage: query <store> '<jq-expr>'}"
  local FILE
  case "$STORE" in
    decisions) FILE="$DECISIONS" ;;
    discussions) FILE="$DISCUSSIONS" ;;
    lessons) FILE="$LESSONS" ;;
    patterns) FILE="$PATTERNS" ;;
    *) echo "error: query not supported for '$STORE' (use list)" >&2; exit 1 ;;
  esac
  [[ -f "$FILE" ]] || { echo "(empty store: $FILE)"; return 0; }
  jq -c "select($EXPR)" "$FILE"
}

# ===========================================================================
# seed — bootstrap the 5 initial knowledge entries committed with this PR.
# Idempotent: skips any slug already present.
# ===========================================================================

cmd_seed() {
  cmd_init >/dev/null
  echo "seed: 5 initial knowledge entries shipped with A.15. Files live in .claude/memory/knowledge/."
  echo "seed: this subcommand is informational — seeds are tracked in git via the gitignore negation"
  echo "      '!.claude/memory/knowledge/' (PR diff carries the .md files; this script is the writer"
  echo "      for new entries going forward)."
  ls -1 "$KNOWLEDGE_DIR" 2>/dev/null | sed 's/^/  /'
}

# ===========================================================================
# analyze-run <run-id> — Wave 2. Produce runs-analysis/<run-id>.md.
# ===========================================================================

cmd_analyze_run() {
  require_jq; cmd_init >/dev/null
  local RUN_ID="${1:?usage: analyze-run <run-id>}"
  local TRACE_DIR="$REPO_ROOT/traces/$RUN_ID"
  [[ -d "$TRACE_DIR" ]] || { echo "error: $TRACE_DIR not found" >&2; exit 1; }

  local OUT="$RUNS_DIR/$RUN_ID.md"
  local TMP="$OUT.tmp.$$"

  local STARTED ENDED MILESTONE OUTCOME HALT
  if [[ -f "$TRACE_DIR/MANIFEST.json" ]]; then
    STARTED="$(jq -r '.started_at // "unknown"' "$TRACE_DIR/MANIFEST.json")"
    ENDED="$(jq -r '.ended_at // "unknown"' "$TRACE_DIR/MANIFEST.json")"
    MILESTONE="$(jq -r '.milestone // "unknown"' "$TRACE_DIR/MANIFEST.json")"
    OUTCOME="$(jq -r '.outcome // "unknown"' "$TRACE_DIR/MANIFEST.json")"
    HALT="$(jq -r '.halt_reason // "null"' "$TRACE_DIR/MANIFEST.json")"
  else
    STARTED="(no manifest)"; ENDED="(no manifest)"; MILESTONE="unknown"; OUTCOME="unknown"; HALT="null"
  fi

  {
    echo "# Run analysis — $RUN_ID"
    echo
    echo "- started: $STARTED"
    echo "- ended: $ENDED"
    echo "- milestone: $MILESTONE"
    echo "- outcome: $OUTCOME"
    echo "- halt_reason: $HALT"
    echo
    echo "## Per-agent token spend"
    echo
    if [[ -f "$TRACE_DIR/MANIFEST.json" ]]; then
      jq -r '.tokens_spent | to_entries[] | "- \(.key): \(.value)"' "$TRACE_DIR/MANIFEST.json"
    else
      echo "(no manifest)"
    fi
    echo
    echo "## ERROR events grouped by kind"
    echo
    local ERR_TOTAL=0
    for kind in retry skip halt pivot; do
      local count
      count="$( { grep -hE "kind=$kind" "$TRACE_DIR"/*.log 2>/dev/null || true; } | wc -l | tr -d ' ')"
      ERR_TOTAL=$((ERR_TOTAL + count))
      echo "- $kind: $count"
    done
    echo "- TOTAL: $ERR_TOTAL"
    echo
    echo "## BUILT / REVIEWED summaries"
    echo
    for log in "$TRACE_DIR"/*.log; do
      [[ -f "$log" ]] || continue
      local agent
      agent="$(basename "$log" .log)"
      local last
      last="$( { grep -E "^\[.*\] (BUILT|REVIEWED) " "$log" 2>/dev/null || true; } | tail -n 1)"
      [[ -n "$last" ]] && echo "- **$agent** — $last"
    done
    echo
    echo "## Files touched"
    echo
    if [[ -f "$TRACE_DIR/MANIFEST.json" ]]; then
      jq -r '.files_touched[]? | "- \(.)"' "$TRACE_DIR/MANIFEST.json"
    fi
    echo
    echo "## Deviations recorded"
    echo
    if [[ -f "$TRACE_DIR/engineer-deviations.log" ]]; then
      sed 's/^/- /' "$TRACE_DIR/engineer-deviations.log"
    else
      echo "(none)"
    fi
  } > "$TMP"

  mv "$TMP" "$OUT"
  echo "analyze-run: $OUT"
}

# ===========================================================================
# mine-patterns [--lookback N] [--aliases]
# ===========================================================================

cmd_mine_patterns() {
  require_jq; cmd_init >/dev/null
  local LOOKBACK=10 ALIAS_MODE=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --lookback) LOOKBACK="$2"; shift 2 ;;
      --aliases) ALIAS_MODE=true; shift ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  if [[ "$ALIAS_MODE" == true ]]; then
    cmd_mine_aliases "$LOOKBACK"
    return
  fi

  local TRACES_ROOT="$REPO_ROOT/traces"
  [[ -d "$TRACES_ROOT" ]] || { echo "(no traces/)"; return 0; }

  # Recent runs by mtime, capped at LOOKBACK.
  local RUNS
  RUNS=$(find "$TRACES_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -printf '%T@\t%f\n' 2>/dev/null \
         | sort -rn | head -n "$LOOKBACK" | cut -f2)

  # Collect every ERROR step across the recent runs, keyed by step+kind.
  local TMP_AGG
  TMP_AGG="$(mktemp)"
  for run in $RUNS; do
    for log in "$TRACES_ROOT/$run"/*.log; do
      [[ -f "$log" ]] || continue
      { grep -hE "^\[.*\] ERROR step=" "$log" 2>/dev/null || true; } | while IFS= read -r line; do
        local step kind
        step="$(echo "$line" | sed -nE 's/.*step=([^ ]+).*/\1/p')"
        kind="$(echo "$line" | sed -nE 's/.*kind=([^ ]+).*/\1/p')"
        echo -e "$step\t$kind\t$run"
      done
    done
  done >> "$TMP_AGG"

  # Group, emit one recurring-patterns row per (step,kind) with count >= 2.
  local NEW=0
  while IFS=$'\t' read -r STEP KIND RUNS_CSV COUNT; do
    [[ "$COUNT" -lt 2 ]] && continue
    local PATTERN_ID="${STEP}__${KIND}"
    local EXISTING
    EXISTING="$(jq -c --arg p "$PATTERN_ID" 'select(.pattern_id == $p)' "$PATTERNS" 2>/dev/null | head -n 1)"
    local FIRST LAST
    FIRST="$(now_iso)"; LAST="$(now_iso)"
    if [[ -n "$EXISTING" ]]; then
      FIRST="$(echo "$EXISTING" | jq -r '.first_seen')"
    fi
    local RUNS_JSON
    RUNS_JSON="$(echo "$RUNS_CSV" | jq -Rc 'split(",")')"
    local LINE
    LINE="$(jq -nc \
      --arg pid "$PATTERN_ID" --arg step "$STEP" --arg kind "$KIND" \
      --argjson c "$COUNT" --argjson runs "$RUNS_JSON" \
      --arg first "$FIRST" --arg last "$LAST" \
      '{pattern_id: $pid, step: $step, kind: $kind, occurrence_count: $c,
        runs: $runs, first_seen: $first, last_seen: $last,
        proposed_action: ""}')"
    # Remove any prior row for this pattern_id (simple supersede).
    if [[ -n "$EXISTING" ]]; then
      local TMP="$PATTERNS.tmp.$$"
      jq -c --arg p "$PATTERN_ID" 'select(.pattern_id != $p)' "$PATTERNS" > "$TMP"
      mv "$TMP" "$PATTERNS"
    fi
    append_jsonl "$PATTERNS" "$LINE"
    NEW=$((NEW + 1))
  done < <(awk -F'\t' '{
    key=$1"\t"$2
    runs[key] = (runs[key] ? runs[key]","$3 : $3)
    count[key]++
  } END {
    for (k in count) {
      split(k, kk, "\t")
      print kk[1]"\t"kk[2]"\t"runs[k]"\t"count[k]
    }
  }' "$TMP_AGG")
  rm -f "$TMP_AGG"
  echo "mine-patterns: $NEW pattern row(s) written/updated to $PATTERNS"
}

# Wave 3: alias mining — scan manager.log for MEMORY_MISS events.
cmd_mine_aliases() {
  require_jq
  local LOOKBACK="${1:-10}"
  local TRACES_ROOT="$REPO_ROOT/traces"
  [[ -d "$TRACES_ROOT" ]] || { echo "(no traces/)"; return 0; }
  local RUNS
  RUNS=$(find "$TRACES_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -printf '%T@\t%f\n' 2>/dev/null \
         | sort -rn | head -n "$LOOKBACK" | cut -f2)
  echo "mine-patterns --aliases: scanning last $LOOKBACK runs for MEMORY_MISS events..."
  local FOUND=0
  for run in $RUNS; do
    [[ -f "$TRACES_ROOT/$run/manager.log" ]] || continue
    while IFS= read -r line; do
      local topic phrase
      topic="$(echo "$line" | sed -nE 's/.*topic=([^ ]+).*/\1/p')"
      phrase="$(echo "$line" | sed -nE "s/.*phrase='([^']+)'.*/\1/p")"
      [[ -n "$topic" && -n "$phrase" ]] || continue
      echo "  $run: topic=$topic phrase='$phrase' → suggest adding to .claude/memory/knowledge/$topic.md Aliases"
      FOUND=$((FOUND + 1))
    done < <(grep -hE "^\[.*\] MEMORY_MISS " "$TRACES_ROOT/$run/manager.log" 2>/dev/null || true)
  done
  echo "mine-aliases: $FOUND candidate(s). Manager surfaces each via AskUserQuestion before mutating."
}

# ===========================================================================
# promote-lesson <pattern_id> — Wave 3. Threshold 5.
# ===========================================================================

cmd_promote_lesson() {
  require_jq; cmd_init >/dev/null
  local PID="${1:?usage: promote-lesson <pattern_id>}"
  local PATTERN
  PATTERN="$(jq -c --arg p "$PID" 'select(.pattern_id == $p)' "$PATTERNS" 2>/dev/null | head -n 1)"
  [[ -n "$PATTERN" ]] || { echo "error: pattern '$PID' not in $PATTERNS" >&2; exit 1; }

  local COUNT
  COUNT="$(echo "$PATTERN" | jq -r '.occurrence_count')"
  if (( COUNT < PROMOTION_THRESHOLD )); then
    echo "error: pattern '$PID' has count=$COUNT (threshold=$PROMOTION_THRESHOLD). Not promoting." >&2
    exit 1
  fi

  local LESSON_ID="lesson-$(echo "$PID" | tr '_' '-')"
  local PATTERN_TEXT ACTION RUNS_JSON
  PATTERN_TEXT="$(echo "$PATTERN" | jq -r '"\(.step) / \(.kind)"')"
  ACTION="$(echo "$PATTERN" | jq -r '.proposed_action // ""')"
  RUNS_JSON="$(echo "$PATTERN" | jq -r '.runs | join(",")')"

  cmd_record_lesson "$LESSON_ID" "$PATTERN_TEXT" "$RUNS_JSON" \
    ${ACTION:+--proposed-action "$ACTION"}

  local SLUG
  SLUG="$(echo "$PID" | sed 's/__.*//' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/--*/-/g; s/^-//; s/-$//')"
  local STUB_FILE="$KNOWLEDGE_DIR/$SLUG.md"
  if [[ ! -f "$STUB_FILE" ]]; then
    local BODY="
# $SLUG

## Context

Promoted from recurring pattern \`$PID\` after $COUNT occurrences across runs.

## Pattern

$PATTERN_TEXT

## Proposed action

${ACTION:-(none captured — update via record-knowledge --overwrite)}

## Related

- pattern: $PID
- lesson: $LESSON_ID
- runs: $RUNS_JSON
"
    echo "$BODY" | cmd_record_knowledge "$SLUG" - --confidence medium --aliases "" >/dev/null
    echo "promote-lesson: lesson $LESSON_ID + knowledge stub $STUB_FILE"
  else
    echo "promote-lesson: lesson $LESSON_ID (knowledge stub $STUB_FILE already exists; left as-is)"
  fi
}

# ===========================================================================
# dispatch
# ===========================================================================

case "${1:-}" in
  init) shift; cmd_init "$@" ;;
  record-decision) shift; cmd_record_decision "$@" ;;
  record-discussion) shift; cmd_record_discussion "$@" ;;
  record-knowledge) shift; cmd_record_knowledge "$@" ;;
  record-lesson) shift; cmd_record_lesson "$@" ;;
  list) shift; cmd_list "$@" ;;
  query) shift; cmd_query "$@" ;;
  seed) shift; cmd_seed "$@" ;;
  analyze-run) shift; cmd_analyze_run "$@" ;;
  mine-patterns) shift; cmd_mine_patterns "$@" ;;
  promote-lesson) shift; cmd_promote_lesson "$@" ;;
  ""|-h|--help|help)
    cat <<'EOF'
agent-memory.sh — single writer for .claude/memory/ stores (Naavik A.15).

Wave 1 — substrate:
  init                                  Create dirs + empty stores. Idempotent.
  record-decision <id> <verdict> <rationale> [--supersedes <id>] [--run-id ID]
  record-discussion <topic> <surface> [--phase X] [--priority P] [--filed-as #N] [--run-id ID]
  record-knowledge <slug> <body-source|-> [--aliases "a, b"] [--confidence H|M|L] [--supersedes <slug>] [--overwrite] [--run-id ID]
  record-lesson <id> <pattern> <evidence-runs-csv> [--proposed-action "..."] [--supersedes <id>]
  list <decisions|discussions|lessons|patterns|knowledge|runs>
  query <decisions|discussions|lessons|patterns> '<jq-expr>'
  seed                                  Inventory the 5 committed knowledge seeds.

Wave 2 — analytics:
  analyze-run <run-id>                  Produce .claude/memory/runs-analysis/<run-id>.md.
  mine-patterns [--lookback N]          Aggregate recurring ERROR steps from last N runs.

Wave 3 — promotion + alias mining:
  promote-lesson <pattern_id>           Threshold 5. Creates lessons.jsonl row + knowledge stub.
  mine-patterns --aliases [--lookback N]
                                        Scan manager.log for MEMORY_MISS topic=... phrase=... events.

Invariants:
  - Single writer. No Edit/Write against .claude/memory/ outside this script.
  - JSONL stores are append-only. Duplicate ids rejected; --supersedes is the upgrade path.
  - Atomic writes via mktemp + mv. Partial files never visible.
  - .claude/memory/ is gitignored EXCEPT the knowledge/ subdir + .keep (carried in PR diff).

Guide: docs/AGENT_OPS.md § 14, docs/design/AGENT_MEMORY.md.
EOF
    ;;
  *)
    echo "error: unknown subcommand '$1' (run with no args for help)" >&2
    exit 1 ;;
esac
