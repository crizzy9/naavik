#!/usr/bin/env bash
# scripts/gh-project.sh — idempotent helper for GitHub Projects v2.
#
# Subcommands:
#   init                            Prompt for repo + project number; cache IDs + option IDs.
#   bootstrap [--apply] [--phase=X] Parse ROADMAP.md, create Milestones + Epics + Issues + Project items.
#   sync [--apply]                  Diff ROADMAP vs Project; --apply pushes ROADMAP -> Project.
#   milestone-status [name]         JSON of items grouped by Status for a milestone.
#   add-item <issue-url>            Add an issue or PR to the Project. Returns project item id.
#   create-issue <id> <title> [--priority P] [--effort E] [--milestone M] [--parent N] [--body "..."]
#                                   Create one Issue + add to Project + set fields. For /plan.
#   create-epic <phase> [--priority P] [--effort E] [--body "..."]
#                                   Create the `[Epic] <phase>` issue + add to Project + set Status=In Progress.
#   add-subissue <parent-num> <child-num>
#                                   Link child issue under parent epic via GraphQL addSubIssue.
#   set-status <item-id> <status>   Move item. Status: Todo | In Progress | Done.
#   set-priority <item-id> <pri>    Set Priority. Values: CRITICAL | HIGH | MEDIUM | LOW.
#   set-effort <item-id> <effort>   Set Effort. Values: XS | S | M | L | XL.
#   next-unblocked                  Next open Todo item, sorted by Priority. Skips 'blocked' label.
#   runs [count]                    Show last N entries from traces/runs.log (default 10).
#   refresh-map                     Rebuild .claude/github-issue-map.json from authoritative GitHub state.
#                                   Run after any manual GitHub UI edit (rename, close, delete) so the
#                                   persistent association cache doesn't drift.
#
# State:
#   .claude/github-project.json   — Project ID + field option IDs. Run `init` once per fork.
#   .claude/github-issue-map.json — Persistent {phase→epic#, task_id→issue#, phase→milestone#}
#                                   association cache. **This script is the sole writer.** Existence
#                                   checks read from this cache before falling back to the GitHub
#                                   search API (which is eventually consistent — see commit 7b30797
#                                   for the duplicate-epic incident that motivated this). Run
#                                   `refresh-map` to rebuild from authoritative GitHub state.
# Companion: docs/AGENT_OPS.md, scripts/roadmap_parser.py.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$REPO_ROOT/.claude/github-project.json"
ISSUE_MAP="$REPO_ROOT/.claude/github-issue-map.json"
PARSER="$REPO_ROOT/scripts/roadmap_parser.py"

require_gh() {
  command -v gh >/dev/null 2>&1 || { echo "error: gh CLI not on PATH. nix develop or https://cli.github.com" >&2; exit 1; }
  command -v jq >/dev/null 2>&1 || { echo "error: jq not on PATH. nix develop." >&2; exit 1; }
}

require_python() {
  command -v python3 >/dev/null 2>&1 || { echo "error: python3 not on PATH. nix develop." >&2; exit 1; }
}

load_cache() {
  [[ -f "$CACHE" ]] || { echo "error: $CACHE not found — run \`$0 init\` first." >&2; exit 1; }
  PROJECT_ID="$(jq -r '.project_id' "$CACHE")"
  PROJECT_NUMBER="$(jq -r '.project_number' "$CACHE")"
  OWNER="$(jq -r '.owner' "$CACHE")"
  REPO="$(jq -r '.repo' "$CACHE")"
  SCOPE="$(jq -r '.scope' "$CACHE")"
  STATUS_FIELD_ID="$(jq -r '.status_field_id' "$CACHE")"
  PRIORITY_FIELD_ID="$(jq -r '.priority_field_id // empty' "$CACHE")"
  EFFORT_FIELD_ID="$(jq -r '.effort_field_id // empty' "$CACHE")"
  STATUS_TODO_ID="$(jq -r '.status_options.todo' "$CACHE")"
  STATUS_INPROG_ID="$(jq -r '.status_options.in_progress' "$CACHE")"
  STATUS_DONE_ID="$(jq -r '.status_options.done' "$CACHE")"
  PRIORITY_CRITICAL_ID="$(jq -r '.priority_options.critical // empty' "$CACHE")"
  PRIORITY_HIGH_ID="$(jq -r '.priority_options.high // empty' "$CACHE")"
  PRIORITY_MEDIUM_ID="$(jq -r '.priority_options.medium // empty' "$CACHE")"
  PRIORITY_LOW_ID="$(jq -r '.priority_options.low // empty' "$CACHE")"
  EFFORT_XS_ID="$(jq -r '.effort_options.xs // empty' "$CACHE")"
  EFFORT_S_ID="$(jq -r '.effort_options.s // empty' "$CACHE")"
  EFFORT_M_ID="$(jq -r '.effort_options.m // empty' "$CACHE")"
  EFFORT_L_ID="$(jq -r '.effort_options.l // empty' "$CACHE")"
  EFFORT_XL_ID="$(jq -r '.effort_options.xl // empty' "$CACHE")"
  OWNER_PATH="$SCOPE"
  [[ "$OWNER_PATH" == "organization" ]] || OWNER_PATH="user"
}

# ===========================================================================
# Issue-map cache — persistent {phase → epic#, task_id → issue#, phase → milestone#}
# associations. The GitHub search API is eventually consistent, so a re-run of
# bootstrap within ~2min of the first will miss freshly-created issues and create
# duplicates. The map gives us deterministic, instant idempotency: every successful
# create writes the new issue number here, and every existence check reads it
# before falling back to the live API. Sole writer is this script. If someone edits
# GitHub state manually, `refresh-map` reconciles.
# ===========================================================================

map_init() {
  if [[ ! -f "$ISSUE_MAP" ]]; then
    mkdir -p "$(dirname "$ISSUE_MAP")"
    local NOW
    NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    cat > "$ISSUE_MAP" <<EOF
{
  "_meta": {
    "owner": "${OWNER:-}",
    "repo": "${REPO:-}",
    "project_number": ${PROJECT_NUMBER:-0},
    "refreshed_at": "$NOW",
    "note": "Persistent cache of GitHub issue/milestone/epic associations. Sole writer: scripts/gh-project.sh. Run 'gh-project.sh refresh-map' to rebuild from authoritative GitHub state."
  },
  "milestones": {},
  "epics": {},
  "issues": {}
}
EOF
  fi
}

# Look up an entry. Args: category (milestones|epics|issues), key.
# Prints issue/milestone number on stdout; empty if missing.
map_lookup() {
  local CATEGORY="$1" KEY="$2"
  [[ -f "$ISSUE_MAP" ]] || return 0
  jq -r --arg c "$CATEGORY" --arg k "$KEY" '.[$c][$k] // empty' "$ISSUE_MAP" 2>/dev/null
}

# Write an entry. Args: category, key, value (numeric). Atomic via temp file.
map_set() {
  local CATEGORY="$1" KEY="$2" VALUE="$3"
  [[ -n "$CATEGORY" && -n "$KEY" && -n "$VALUE" ]] || return 0
  map_init
  local TMP="$ISSUE_MAP.tmp.$$"
  jq --arg c "$CATEGORY" --arg k "$KEY" --argjson v "$VALUE" \
    '.[$c][$k] = $v' "$ISSUE_MAP" > "$TMP"
  mv "$TMP" "$ISSUE_MAP"
}

# ===========================================================================
# init — also creates Priority + Effort single-select fields if missing
# ===========================================================================

cmd_init() {
  require_gh
  mkdir -p "$(dirname "$CACHE")"

  read -rp "GitHub owner (user or org, e.g. crizzy9): " OWNER
  read -rp "GitHub repo (e.g. naavik): " REPO
  read -rp "Project number (the integer in the project URL, e.g. 4): " PROJECT_NUMBER

  echo "→ resolving project + fields via GraphQL..."

  local QUERY='
    query($owner:String!, $number:Int!) {
      __TYPE__(login:$owner) {
        projectV2(number:$number) {
          id
          title
          fields(first:50) {
            nodes {
              ... on ProjectV2Field { id name dataType }
              ... on ProjectV2SingleSelectField {
                id name dataType
                options { id name }
              }
            }
          }
        }
      }
    }'

  local USER_JSON ORG_JSON SCOPE PROJECT_JSON
  USER_JSON="$(gh api graphql -f query="${QUERY//__TYPE__/user}" -F owner="$OWNER" -F number="$PROJECT_NUMBER" 2>/dev/null || true)"
  if [[ -n "$(echo "$USER_JSON" | jq -r '.data.user.projectV2.id // empty')" ]]; then
    SCOPE="user"
    PROJECT_JSON="$USER_JSON"
  else
    ORG_JSON="$(gh api graphql -f query="${QUERY//__TYPE__/organization}" -F owner="$OWNER" -F number="$PROJECT_NUMBER")"
    SCOPE="organization"
    PROJECT_JSON="$ORG_JSON"
  fi

  local PROJECT_ID
  PROJECT_ID="$(echo "$PROJECT_JSON" | jq -r ".data.${SCOPE}.projectV2.id // empty")"
  [[ -n "$PROJECT_ID" ]] || { echo "error: project not found for $OWNER #$PROJECT_NUMBER" >&2; exit 1; }

  local FIELDS_PATH=".data.${SCOPE}.projectV2.fields.nodes"

  local STATUS_FIELD_ID PRIORITY_FIELD_ID EFFORT_FIELD_ID
  STATUS_FIELD_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Status\") | .id")"
  PRIORITY_FIELD_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Priority\") | .id // empty")"
  EFFORT_FIELD_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .id // empty")"

  # Auto-create Priority field if missing.
  if [[ -z "$PRIORITY_FIELD_ID" ]]; then
    echo "→ Priority field missing — creating CRITICAL/HIGH/MEDIUM/LOW single-select..."
    local NEW=$(gh api graphql -f query='
      mutation($p:ID!) {
        createProjectV2Field(input:{
          projectId:$p, dataType:SINGLE_SELECT, name:"Priority",
          singleSelectOptions:[
            {name:"CRITICAL", color:RED, description:"Drop everything"}
            {name:"HIGH", color:ORANGE, description:"Next up"}
            {name:"MEDIUM", color:YELLOW, description:"Normal"}
            {name:"LOW", color:GRAY, description:"Backlog"}
          ]
        }) { projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
      }' -F p="$PROJECT_ID")
    PRIORITY_FIELD_ID="$(echo "$NEW" | jq -r '.data.createProjectV2Field.projectV2Field.id')"
    PROJECT_JSON="$(gh api graphql -f query="${QUERY//__TYPE__/$SCOPE}" -F owner="$OWNER" -F number="$PROJECT_NUMBER")"
  fi

  # Auto-create Effort field if missing.
  if [[ -z "$EFFORT_FIELD_ID" ]]; then
    echo "→ Effort field missing — creating XS/S/M/L/XL single-select..."
    local NEW=$(gh api graphql -f query='
      mutation($p:ID!) {
        createProjectV2Field(input:{
          projectId:$p, dataType:SINGLE_SELECT, name:"Effort",
          singleSelectOptions:[
            {name:"XS", color:GRAY, description:"Less than 1 hour"}
            {name:"S", color:GREEN, description:"1-4 hours"}
            {name:"M", color:BLUE, description:"1 day"}
            {name:"L", color:PURPLE, description:"2-3 days"}
            {name:"XL", color:RED, description:"More than 1 week"}
          ]
        }) { projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
      }' -F p="$PROJECT_ID")
    EFFORT_FIELD_ID="$(echo "$NEW" | jq -r '.data.createProjectV2Field.projectV2Field.id')"
    PROJECT_JSON="$(gh api graphql -f query="${QUERY//__TYPE__/$SCOPE}" -F owner="$OWNER" -F number="$PROJECT_NUMBER")"
  fi

  local STATUS_TODO_ID STATUS_INPROG_ID STATUS_DONE_ID
  STATUS_TODO_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Status\") | .options[]? | select(.name==\"Todo\" or .name==\"To do\") | .id" | head -n1)"
  STATUS_INPROG_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Status\") | .options[]? | select(.name==\"In Progress\" or .name==\"In progress\") | .id" | head -n1)"
  STATUS_DONE_ID="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Status\") | .options[]? | select(.name==\"Done\") | .id" | head -n1)"

  local PCRIT PHIGH PMED PLOW
  PCRIT="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Priority\") | .options[]? | select(.name|ascii_downcase==\"critical\") | .id" | head -n1)"
  PHIGH="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Priority\") | .options[]? | select(.name|ascii_downcase==\"high\") | .id" | head -n1)"
  PMED="$(echo "$PROJECT_JSON"  | jq -r "${FIELDS_PATH}[] | select(.name==\"Priority\") | .options[]? | select(.name|ascii_downcase==\"medium\") | .id" | head -n1)"
  PLOW="$(echo "$PROJECT_JSON"  | jq -r "${FIELDS_PATH}[] | select(.name==\"Priority\") | .options[]? | select(.name|ascii_downcase==\"low\") | .id" | head -n1)"

  local EXS ES EM EL EXL
  EXS="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .options[]? | select(.name|ascii_downcase==\"xs\") | .id" | head -n1)"
  ES="$(echo "$PROJECT_JSON"  | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .options[]? | select(.name|ascii_downcase==\"s\")  | .id" | head -n1)"
  EM="$(echo "$PROJECT_JSON"  | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .options[]? | select(.name|ascii_downcase==\"m\")  | .id" | head -n1)"
  EL="$(echo "$PROJECT_JSON"  | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .options[]? | select(.name|ascii_downcase==\"l\")  | .id" | head -n1)"
  EXL="$(echo "$PROJECT_JSON" | jq -r "${FIELDS_PATH}[] | select(.name==\"Effort\") | .options[]? | select(.name|ascii_downcase==\"xl\") | .id" | head -n1)"

  cat > "$CACHE" <<EOF
{
  "owner": "$OWNER",
  "repo": "$REPO",
  "scope": "$SCOPE",
  "project_id": "$PROJECT_ID",
  "project_number": $PROJECT_NUMBER,
  "project_url": "https://github.com/${SCOPE}s/$OWNER/projects/$PROJECT_NUMBER",
  "status_field_id": "$STATUS_FIELD_ID",
  "priority_field_id": "$PRIORITY_FIELD_ID",
  "effort_field_id": "$EFFORT_FIELD_ID",
  "status_options": { "todo": "$STATUS_TODO_ID", "in_progress": "$STATUS_INPROG_ID", "done": "$STATUS_DONE_ID" },
  "priority_options": { "critical": "$PCRIT", "high": "$PHIGH", "medium": "$PMED", "low": "$PLOW" },
  "effort_options": { "xs": "$EXS", "s": "$ES", "m": "$EM", "l": "$EL", "xl": "$EXL" }
}
EOF
  echo "→ cached at $CACHE"
  jq . "$CACHE"
}

# ===========================================================================
# Low-level helpers
# ===========================================================================

# Set a single-select field on a project item.
set_select() {
  local item="$1" field="$2" opt="$3"
  [[ -n "$field" && -n "$opt" ]] || return 0
  gh api graphql -f query='
    mutation($p:ID!, $i:ID!, $f:ID!, $o:String!) {
      updateProjectV2ItemFieldValue(input:{projectId:$p, itemId:$i, fieldId:$f, value:{singleSelectOptionId:$o}}) {
        projectV2Item { id }
      }
    }' -F p="$PROJECT_ID" -F i="$item" -F f="$field" -F o="$opt" >/dev/null
}

# Resolve issue number → GraphQL node id.
issue_node_id() {
  local NUM="$1"
  gh api graphql -f query='
    query($owner:String!, $repo:String!, $num:Int!) {
      repository(owner:$owner, name:$repo) { issue(number:$num) { id } }
    }' -F owner="$OWNER" -F repo="$REPO" -F num="$NUM" \
    | jq -r '.data.repository.issue.id // empty'
}

# Idempotent label create.
ensure_label() {
  local NAME="$1" COLOR="${2:-ededed}" DESC="${3:-Auto-created}"
  gh label create "$NAME" --repo "$OWNER/$REPO" --color "$COLOR" --description "$DESC" 2>/dev/null || true
}

# Idempotent milestone create. Returns the milestone number on stdout.
# Reads .claude/github-issue-map.json first; falls back to REST list; backfills map.
ensure_milestone() {
  local NAME="$1" DESC="${2:-Mirrored from ROADMAP.md § $1}"

  # Layer 1: persistent map (trusted; if drifted, user must run `refresh-map`).
  local CACHED
  CACHED="$(map_lookup "milestones" "$NAME")"
  if [[ -n "$CACHED" ]]; then
    echo "$CACHED"
    return 0
  fi

  # Layer 2: live REST query (no eventual-consistency problem on /milestones).
  local EXISTS
  EXISTS="$(gh api "repos/$OWNER/$REPO/milestones?state=all&per_page=100" --paginate 2>/dev/null \
            | jq -r --arg n "$NAME" 'map(select(.title == $n)) | .[0].number // empty')"
  if [[ -n "$EXISTS" ]]; then
    map_set "milestones" "$NAME" "$EXISTS"
    echo "$EXISTS"
    return 0
  fi

  # Layer 3: create.
  local NEW
  NEW="$(gh api "repos/$OWNER/$REPO/milestones" -X POST -f "title=$NAME" -f "description=$DESC" \
         | jq -r '.number')"
  map_set "milestones" "$NAME" "$NEW"
  echo "$NEW"
}

# Read-only milestone lookup (does NOT create). Used by bootstrap dry-run so we
# can report exists vs would-create without mutating state.
lookup_milestone() {
  local NAME="$1"
  local CACHED
  CACHED="$(map_lookup "milestones" "$NAME")"
  if [[ -n "$CACHED" ]]; then
    echo "$CACHED"
    return 0
  fi
  local EXISTS
  EXISTS="$(gh api "repos/$OWNER/$REPO/milestones?state=all&per_page=100" --paginate 2>/dev/null \
            | jq -r --arg n "$NAME" 'map(select(.title == $n)) | .[0].number // empty')"
  if [[ -n "$EXISTS" ]]; then
    map_set "milestones" "$NAME" "$EXISTS"
  fi
  echo "$EXISTS"
}

# Find an existing issue by title prefix (idempotency).
# Optional args 2+3 enable the persistent issue-map cache:
#   find_issue_by_prefix "$PREFIX" "epics"  "$PHASE"     # for [Epic] <phase>
#   find_issue_by_prefix "$PREFIX" "issues" "$TASK_ID"   # for [TASK_ID] <title>
# When provided, the cache is consulted first (no API call). On a cache miss, the
# live search API is used and the result is written back to the cache so subsequent
# runs short-circuit. Without these args, behavior is identical to the old function.
find_issue_by_prefix() {
  local PREFIX="$1"
  local MAP_CATEGORY="${2:-}"
  local MAP_KEY="${3:-}"

  # Layer 1: persistent map. Trust without verify (drift → user runs `refresh-map`).
  if [[ -n "$MAP_CATEGORY" && -n "$MAP_KEY" ]]; then
    local CACHED
    CACHED="$(map_lookup "$MAP_CATEGORY" "$MAP_KEY")"
    if [[ -n "$CACHED" ]]; then
      echo "$CACHED"
      return 0
    fi
  fi

  # Layer 2: live search (subject to GitHub indexing lag ~30s-2min; use as fallback only).
  local Q FOUND
  Q="$(printf 'repo:%s/%s in:title %s' "$OWNER" "$REPO" "$PREFIX" | jq -sRr @uri)"
  FOUND="$(gh api "search/issues?q=$Q" 2>/dev/null \
           | jq -r --arg p "$PREFIX" '.items // [] | map(select(.title | startswith($p))) | .[0].number // empty')"

  # Backfill the map on cache miss → live hit, so the next run skips the API.
  if [[ -n "$FOUND" && -n "$MAP_CATEGORY" && -n "$MAP_KEY" ]]; then
    map_set "$MAP_CATEGORY" "$MAP_KEY" "$FOUND"
  fi

  echo "$FOUND"
}

# Add an issue (node id) to the Project. Returns project item id on stdout.
add_issue_to_project() {
  local CONTENT_ID="$1"
  gh api graphql -f query='
    mutation($p:ID!, $c:ID!) {
      addProjectV2ItemById(input:{projectId:$p, contentId:$c}) { item { id } }
    }' -F p="$PROJECT_ID" -F c="$CONTENT_ID" \
    | jq -r '.data.addProjectV2ItemById.item.id'
}

# Link a child issue under a parent epic via GraphQL addSubIssue.
add_subissue_by_id() {
  local PARENT_ID="$1" CHILD_ID="$2"
  gh api graphql -f query='
    mutation($parent:ID!, $child:ID!) {
      addSubIssue(input:{issueId:$parent, subIssueId:$child}) {
        subIssue { number }
      }
    }' -F parent="$PARENT_ID" -F child="$CHILD_ID" >/dev/null
}

# ===========================================================================
# set-status / set-priority / set-effort (item-level field writes)
# ===========================================================================

cmd_set_status() {
  require_gh; load_cache
  local ITEM_ID="${1:?usage: set-status <item-id> <status>}"
  local STATUS="${2:?usage: set-status <item-id> <status>}"
  local OPT_ID
  case "$STATUS" in
    Todo|todo|"To do") OPT_ID="$STATUS_TODO_ID" ;;
    "In Progress"|in_progress|"in progress") OPT_ID="$STATUS_INPROG_ID" ;;
    Done|done) OPT_ID="$STATUS_DONE_ID" ;;
    *) echo "error: unknown status '$STATUS' (expected: Todo, In Progress, Done)" >&2; exit 1 ;;
  esac
  set_select "$ITEM_ID" "$STATUS_FIELD_ID" "$OPT_ID"
  echo "status set: $STATUS"
}

cmd_set_priority() {
  require_gh; load_cache
  local ITEM_ID="${1:?usage: set-priority <item-id> <pri>}"
  local PRI="${2:?usage: set-priority <item-id> <pri>}"
  local OPT_ID
  case "${PRI^^}" in
    CRITICAL) OPT_ID="$PRIORITY_CRITICAL_ID" ;;
    HIGH) OPT_ID="$PRIORITY_HIGH_ID" ;;
    MEDIUM) OPT_ID="$PRIORITY_MEDIUM_ID" ;;
    LOW) OPT_ID="$PRIORITY_LOW_ID" ;;
    *) echo "error: unknown priority '$PRI' (expected: CRITICAL, HIGH, MEDIUM, LOW)" >&2; exit 1 ;;
  esac
  [[ -n "$PRIORITY_FIELD_ID" ]] || { echo "warning: Priority field not configured — skipping" >&2; return 0; }
  set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$OPT_ID"
  echo "priority set: ${PRI^^}"
}

cmd_set_effort() {
  require_gh; load_cache
  local ITEM_ID="${1:?usage: set-effort <item-id> <effort>}"
  local EFF="${2:?usage: set-effort <item-id> <effort>}"
  local OPT_ID
  case "${EFF^^}" in
    XS) OPT_ID="$EFFORT_XS_ID" ;;
    S) OPT_ID="$EFFORT_S_ID" ;;
    M) OPT_ID="$EFFORT_M_ID" ;;
    L) OPT_ID="$EFFORT_L_ID" ;;
    XL) OPT_ID="$EFFORT_XL_ID" ;;
    *) echo "error: unknown effort '$EFF' (expected: XS, S, M, L, XL)" >&2; exit 1 ;;
  esac
  [[ -n "$EFFORT_FIELD_ID" ]] || { echo "warning: Effort field not configured — skipping" >&2; return 0; }
  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$OPT_ID"
  echo "effort set: ${EFF^^}"
}

# ===========================================================================
# Phase → labels + epic info
# ===========================================================================

# Map a phase name to a sanitized phase label.
phase_to_label() {
  case "$1" in
    "Phase A") echo "phase:A" ;;
    "Pre-Phase-2 paper cuts") echo "phase:pre-2" ;;
    "Phase 1 deferred items") echo "phase:1.x" ;;
    "Phase "[0-9]) echo "phase:${1#Phase }" ;;
    *) echo "" ;;
  esac
}

# Map a phase name to additional category labels (paper-cut, agent-system, etc.).
phase_to_category_labels() {
  case "$1" in
    "Phase A") echo "agent-system" ;;
    "Pre-Phase-2 paper cuts") echo "paper-cut" ;;
    "Phase 1 deferred items") echo "phase-1-deferred" ;;
    *) echo "" ;;
  esac
}

# Default Effort per phase.
phase_to_default_effort() {
  case "$1" in
    "Phase A"|"Pre-Phase-2 paper cuts") echo "S" ;;
    "Phase 1 deferred items") echo "M" ;;
    *) echo "M" ;;
  esac
}

# ===========================================================================
# create-epic — `[Epic] <phase>` parent issue
# ===========================================================================

cmd_create_epic() {
  require_gh; load_cache
  local PHASE="${1:?usage: create-epic <phase-name> [--priority P] [--effort E] [--body \"...\"]}"
  shift
  local PRI="HIGH" EFFORT="L" BODY=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --priority) PRI="${2^^}"; shift 2 ;;
      --effort) EFFORT="${2^^}"; shift 2 ;;
      --body) BODY="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  local TITLE="[Epic] $PHASE"
  local EXISTING
  EXISTING="$(find_issue_by_prefix "[Epic] $PHASE" "epics" "$PHASE" 2>/dev/null || echo "")"
  if [[ -n "$EXISTING" ]]; then
    echo "exists: https://github.com/$OWNER/$REPO/issues/$EXISTING"
    return 0
  fi

  ensure_milestone "$PHASE" >/dev/null

  local PHASE_LABEL CATEGORY_LABEL
  PHASE_LABEL="$(phase_to_label "$PHASE")"
  CATEGORY_LABEL="$(phase_to_category_labels "$PHASE")"

  local LABEL_ARGS=("--label" "epic" "--label" "priority:${PRI,,}")
  [[ -n "$PHASE_LABEL" ]] && LABEL_ARGS+=("--label" "$PHASE_LABEL")
  [[ -n "$CATEGORY_LABEL" ]] && LABEL_ARGS+=("--label" "$CATEGORY_LABEL")

  if [[ -z "$BODY" ]]; then
    BODY="**$PHASE epic**

Sub-issues track the per-row tasks from \`ROADMAP.md\` § $PHASE.

Manager owns this epic's % complete via Sub-issues progress. Closing this epic happens after every sub-issue is closed AND the corresponding ROADMAP rows are marked \`[x]\`.

---
*Auto-managed by \`scripts/gh-project.sh\`. \`ROADMAP.md\` is authoritative.*"
  fi

  local URL
  URL="$(gh issue create --repo "$OWNER/$REPO" \
    --title "$TITLE" \
    --body "$BODY" \
    --milestone "$PHASE" \
    "${LABEL_ARGS[@]}")"

  local NUM="${URL##*/}"
  local NODE_ID ITEM_ID
  NODE_ID="$(issue_node_id "$NUM")"
  ITEM_ID="$(add_issue_to_project "$NODE_ID")"
  cmd_set_status "$ITEM_ID" "In Progress" >/dev/null
  set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$(case "$PRI" in CRITICAL) echo "$PRIORITY_CRITICAL_ID";; HIGH) echo "$PRIORITY_HIGH_ID";; MEDIUM) echo "$PRIORITY_MEDIUM_ID";; LOW) echo "$PRIORITY_LOW_ID";; esac)"
  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$(case "$EFFORT" in XS) echo "$EFFORT_XS_ID";; S) echo "$EFFORT_S_ID";; M) echo "$EFFORT_M_ID";; L) echo "$EFFORT_L_ID";; XL) echo "$EFFORT_XL_ID";; esac)"

  map_set "epics" "$PHASE" "$NUM"

  echo "$URL"
}

# ===========================================================================
# create-issue (for /plan) — supports --parent for sub-issue linkage
# ===========================================================================

cmd_create_issue() {
  require_gh; load_cache
  local TASK_ID="${1:?usage: create-issue <task-id> <title> [--priority P] [--effort E] [--milestone M] [--parent NUM] [--body \"...\"]}"
  local TITLE="${2:?usage: create-issue <task-id> <title>}"
  shift 2

  local PRI="MEDIUM" EFFORT="M" MILESTONE="" PARENT="" BODY=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --priority) PRI="${2^^}"; shift 2 ;;
      --effort) EFFORT="${2^^}"; shift 2 ;;
      --milestone) MILESTONE="$2"; shift 2 ;;
      --parent) PARENT="$2"; shift 2 ;;
      --body) BODY="$2"; shift 2 ;;
      *) echo "error: unknown arg '$1'" >&2; exit 1 ;;
    esac
  done

  local ISSUE_PREFIX="[$TASK_ID]"
  local EXISTING
  EXISTING="$(find_issue_by_prefix "$ISSUE_PREFIX" "issues" "$TASK_ID" 2>/dev/null || echo "")"
  if [[ -n "$EXISTING" ]]; then
    echo "exists: https://github.com/$OWNER/$REPO/issues/$EXISTING"
    return 0
  fi

  if [[ -z "$BODY" ]]; then
    BODY="Created via \`scripts/gh-project.sh create-issue\` (likely from \`/plan\`).

ROADMAP row: \`$TASK_ID\` — update \`ROADMAP.md\` § the relevant phase before flipping status.

---
*Auto-managed by \`scripts/gh-project.sh\`. \`ROADMAP.md\` is authoritative.*"
  fi

  ensure_label "priority:${PRI,,}" "ededed" "Priority ${PRI^^}"

  local CREATE_ARGS=(--repo "$OWNER/$REPO" --title "[$TASK_ID] $TITLE" --body "$BODY" --label "priority:${PRI,,}")
  [[ -n "$MILESTONE" ]] && { ensure_milestone "$MILESTONE" >/dev/null; CREATE_ARGS+=(--milestone "$MILESTONE"); }

  local URL
  URL="$(gh issue create "${CREATE_ARGS[@]}")"

  local NUM="${URL##*/}"
  local NODE_ID ITEM_ID
  NODE_ID="$(issue_node_id "$NUM")"
  ITEM_ID="$(add_issue_to_project "$NODE_ID")"

  set_select "$ITEM_ID" "$STATUS_FIELD_ID" "$STATUS_TODO_ID"
  case "${PRI^^}" in
    CRITICAL) set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_CRITICAL_ID" ;;
    HIGH)     set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_HIGH_ID" ;;
    MEDIUM)   set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_MEDIUM_ID" ;;
    LOW)      set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_LOW_ID" ;;
  esac
  case "${EFFORT^^}" in
    XS) set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_XS_ID" ;;
    S)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_S_ID" ;;
    M)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_M_ID" ;;
    L)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_L_ID" ;;
    XL) set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_XL_ID" ;;
  esac

  if [[ -n "$PARENT" ]]; then
    local PARENT_ID
    PARENT_ID="$(issue_node_id "$PARENT")"
    [[ -n "$PARENT_ID" ]] && add_subissue_by_id "$PARENT_ID" "$NODE_ID"
  fi

  map_set "issues" "$TASK_ID" "$NUM"

  echo "$URL"
}

# ===========================================================================
# add-item / add-subissue
# ===========================================================================

cmd_add_item() {
  require_gh; load_cache
  local ISSUE_URL="${1:?usage: add-item <issue-url>}"
  local CONTENT_ID
  CONTENT_ID="$(gh api graphql -f query='
    query($url:URI!) { resource(url:$url) { ... on Issue { id } ... on PullRequest { id } } }
  ' -F url="$ISSUE_URL" | jq -r '.data.resource.id')"
  [[ -n "$CONTENT_ID" && "$CONTENT_ID" != "null" ]] || { echo "error: could not resolve $ISSUE_URL" >&2; exit 1; }
  add_issue_to_project "$CONTENT_ID"
}

cmd_add_subissue() {
  require_gh; load_cache
  local PARENT_NUM="${1:?usage: add-subissue <parent-num> <child-num>}"
  local CHILD_NUM="${2:?usage: add-subissue <parent-num> <child-num>}"
  local PARENT_ID CHILD_ID
  PARENT_ID="$(issue_node_id "$PARENT_NUM")"
  CHILD_ID="$(issue_node_id "$CHILD_NUM")"
  [[ -n "$PARENT_ID" && -n "$CHILD_ID" ]] || { echo "error: could not resolve parent or child issue id" >&2; exit 1; }
  add_subissue_by_id "$PARENT_ID" "$CHILD_ID"
  echo "linked: #$CHILD_NUM → parent #$PARENT_NUM"
}

# ===========================================================================
# milestone-status
# ===========================================================================

cmd_milestone_status() {
  require_gh; load_cache
  local MILESTONE_NAME="${1:-}"
  local ITEMS_JSON
  ITEMS_JSON="$(gh api graphql -f query="
    query(\$owner:String!, \$number:Int!) {
      ${OWNER_PATH}(login:\$owner) {
        projectV2(number:\$number) {
          items(first:100) {
            nodes {
              id
              content {
                __typename
                ... on Issue { number title state url milestone { title } }
                ... on PullRequest { number title state url milestone { title } }
              }
              fieldValues(first:20) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } }
                }
              }
            }
          }
        }
      }
    }" -F owner="$OWNER" -F number="$PROJECT_NUMBER")"

  if [[ -n "$MILESTONE_NAME" ]]; then
    echo "$ITEMS_JSON" | jq --arg ms "$MILESTONE_NAME" '
      .data | (.organization // .user) | .projectV2.items.nodes
      | map(select(.content.milestone.title == $ms))
      | group_by(.fieldValues.nodes[]? | select(.field.name == "Status") | .name)
      | map({status: (.[0].fieldValues.nodes[]? | select(.field.name == "Status") | .name // "Unset"),
             count: length,
             items: map({number: .content.number, title: .content.title, url: .content.url})})'
  else
    echo "$ITEMS_JSON" | jq '
      .data | (.organization // .user) | .projectV2.items.nodes
      | group_by(.fieldValues.nodes[]? | select(.field.name == "Status") | .name)
      | map({status: (.[0].fieldValues.nodes[]? | select(.field.name == "Status") | .name // "Unset"),
             count: length,
             items: map({number: .content.number, title: .content.title, url: .content.url, milestone: .content.milestone.title})})'
  fi
}

# ===========================================================================
# next-unblocked
# ===========================================================================

cmd_next_unblocked() {
  require_gh; load_cache
  gh api graphql -f query="
    query(\$owner:String!, \$number:Int!) {
      ${OWNER_PATH}(login:\$owner) {
        projectV2(number:\$number) {
          items(first:100) {
            nodes {
              id
              content {
                __typename
                ... on Issue { number title state url labels(first:10) { nodes { name } } }
                ... on PullRequest { number title state url }
              }
              fieldValues(first:20) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } }
                }
              }
            }
          }
        }
      }
    }" -F owner="$OWNER" -F number="$PROJECT_NUMBER" \
  | jq '
      def status_of: [.fieldValues.nodes[]? | select(.field.name? == "Status") | .name?] | .[0] // "Todo";
      def priority_of: [.fieldValues.nodes[]? | select(.field.name? == "Priority") | .name?] | .[0] // "MEDIUM";
      def labels_of: [.content.labels.nodes[]?.name?];

      .data | (.organization // .user) | .projectV2.items.nodes
      | map(select(
          (.content.state // "OPEN") == "OPEN"
          and (status_of == "Todo")
          and ((labels_of | index("blocked")) == null)
          and ((labels_of | index("epic")) == null)
        ))
      | map({
          number: .content.number,
          title: .content.title,
          url: .content.url,
          priority: priority_of,
          labels: labels_of
        })
      | sort_by(.priority as $p | ["CRITICAL","HIGH","MEDIUM","LOW"] | index($p) // 99)
      | (.[0] // null)'
}

# ===========================================================================
# bootstrap — parse ROADMAP, create milestones + epics + sub-issues
# ===========================================================================

cmd_bootstrap() {
  require_gh; require_python; load_cache

  local APPLY=false
  local PHASES=()
  for arg in "$@"; do
    case "$arg" in
      --apply) APPLY=true ;;
      --phase=*) PHASES+=("${arg#--phase=}") ;;
      *) echo "error: unknown arg '$arg' (expected --apply or --phase=NAME)" >&2; exit 1 ;;
    esac
  done

  if [[ ${#PHASES[@]} -eq 0 ]]; then
    PHASES=("Pre-Phase-2 paper cuts" "Phase A" "Phase 2" "Phase 1 deferred items")
  fi

  echo "→ bootstrap (apply=$APPLY) phases: ${PHASES[*]}"
  echo

  local PHASE_ARGS=()
  for p in "${PHASES[@]}"; do PHASE_ARGS+=("--phase=$p"); done

  local CREATED=0 SKIPPED=0

  for PHASE in "${PHASES[@]}"; do
    echo "=== $PHASE ==="

    # 1. Milestone — read-only lookup in both dry-run and apply (apply also creates if missing).
    local EXISTING_MS
    EXISTING_MS="$(lookup_milestone "$PHASE")"
    if [[ -n "$EXISTING_MS" ]]; then
      echo "  milestone exists → #$EXISTING_MS"
    elif $APPLY; then
      local MS_NUM
      MS_NUM="$(ensure_milestone "$PHASE")"
      echo "  milestone created → #$MS_NUM"
    else
      echo "  milestone PLAN   would create \"$PHASE\""
    fi

    # 2. Epic — read-only lookup in both dry-run and apply (apply also creates if missing).
    local EPIC_NUM=""
    local EXISTING_EPIC
    EXISTING_EPIC="$(find_issue_by_prefix "[Epic] $PHASE" "epics" "$PHASE" 2>/dev/null || echo "")"
    if [[ -n "$EXISTING_EPIC" ]]; then
      EPIC_NUM="$EXISTING_EPIC"
      echo "  epic exists → #$EPIC_NUM"
    elif $APPLY; then
      local EPIC_OUT
      EPIC_OUT="$(cmd_create_epic "$PHASE")"
      EPIC_NUM="${EPIC_OUT##*/}"
      echo "  epic created → #$EPIC_NUM ($EPIC_OUT)"
    else
      echo "  epic PLAN   would create [Epic] $PHASE"
    fi

    # 3. Iterate over the phase's tasks.
    while IFS= read -r row; do
      [[ -z "$row" ]] && continue

      local TASK_ID TITLE STATUS PRIORITY NOTES
      TASK_ID="$(echo "$row" | jq -r .id)"
      TITLE="$(echo "$row" | jq -r .title)"
      STATUS="$(echo "$row" | jq -r .status)"
      PRIORITY="$(echo "$row" | jq -r .priority)"
      NOTES="$(echo "$row" | jq -r .notes)"

      local ISSUE_PREFIX="[$TASK_ID]"
      local EXISTING
      EXISTING="$(find_issue_by_prefix "$ISSUE_PREFIX" "issues" "$TASK_ID" 2>/dev/null || echo "")"

      if [[ -n "$EXISTING" ]]; then
        echo "  SKIP   $ISSUE_PREFIX exists → #$EXISTING"
        SKIPPED=$((SKIPPED+1))
        continue
      fi

      if ! $APPLY; then
        echo "  PLAN   $ISSUE_PREFIX $TITLE  (priority=$PRIORITY status=$STATUS)"
        CREATED=$((CREATED+1))
        continue
      fi

      local DEFAULT_EFFORT
      DEFAULT_EFFORT="$(phase_to_default_effort "$PHASE")"

      local PHASE_LABEL CATEGORY_LABEL
      PHASE_LABEL="$(phase_to_label "$PHASE")"
      CATEGORY_LABEL="$(phase_to_category_labels "$PHASE")"

      local BODY
      BODY="Bootstrapped from \`ROADMAP.md\` § $PHASE row $TASK_ID.

$NOTES

---
*Auto-managed by \`scripts/gh-project.sh\`. \`ROADMAP.md\` is authoritative. Do not edit Status here directly; mark the ROADMAP row first, then run \`scripts/gh-project.sh sync --apply\`.*"

      local LABEL_ARGS=(--label "priority:${PRIORITY,,}")
      [[ -n "$PHASE_LABEL" ]] && LABEL_ARGS+=(--label "$PHASE_LABEL")
      [[ -n "$CATEGORY_LABEL" ]] && LABEL_ARGS+=(--label "$CATEGORY_LABEL")

      local URL
      URL="$(gh issue create --repo "$OWNER/$REPO" \
        --title "$ISSUE_PREFIX $TITLE" \
        --body "$BODY" \
        --milestone "$PHASE" \
        "${LABEL_ARGS[@]}")"

      local NUM="${URL##*/}"
      local NODE_ID ITEM_ID
      NODE_ID="$(issue_node_id "$NUM")"
      ITEM_ID="$(add_issue_to_project "$NODE_ID")"

      case "$STATUS" in
        " ") set_select "$ITEM_ID" "$STATUS_FIELD_ID" "$STATUS_TODO_ID" ;;
        "~") set_select "$ITEM_ID" "$STATUS_FIELD_ID" "$STATUS_INPROG_ID" ;;
        "x") set_select "$ITEM_ID" "$STATUS_FIELD_ID" "$STATUS_DONE_ID" ;;
      esac

      case "${PRIORITY^^}" in
        CRITICAL) set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_CRITICAL_ID" ;;
        HIGH)     set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_HIGH_ID" ;;
        MEDIUM)   set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_MEDIUM_ID" ;;
        LOW)      set_select "$ITEM_ID" "$PRIORITY_FIELD_ID" "$PRIORITY_LOW_ID" ;;
      esac

      case "${DEFAULT_EFFORT^^}" in
        XS) set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_XS_ID" ;;
        S)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_S_ID" ;;
        M)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_M_ID" ;;
        L)  set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_L_ID" ;;
        XL) set_select "$ITEM_ID" "$EFFORT_FIELD_ID" "$EFFORT_XL_ID" ;;
      esac

      # Link to epic via Parent issue.
      if [[ -n "$EPIC_NUM" ]]; then
        local EPIC_ID
        EPIC_ID="$(issue_node_id "$EPIC_NUM")"
        [[ -n "$EPIC_ID" ]] && add_subissue_by_id "$EPIC_ID" "$NODE_ID" 2>/dev/null || true
      fi

      map_set "issues" "$TASK_ID" "$NUM"

      echo "  CREATE $ISSUE_PREFIX → #$NUM  ($PRIORITY, parent #$EPIC_NUM)"
      CREATED=$((CREATED+1))
    done < <(python3 "$PARSER" --phase="$PHASE" --open-only)

    echo
  done

  if $APPLY; then
    echo "→ done. created=$CREATED skipped=$SKIPPED"
  else
    echo "→ dry-run. would create=$CREATED skipped=$SKIPPED. re-run with --apply."
  fi
}

# ===========================================================================
# sync — diff ROADMAP vs Project; --apply pushes ROADMAP → Project
# ===========================================================================

cmd_sync() {
  require_gh; require_python; load_cache

  local APPLY=false
  for arg in "$@"; do
    case "$arg" in
      --apply) APPLY=true ;;
      *) echo "error: unknown arg '$arg' (expected --apply)" >&2; exit 1 ;;
    esac
  done

  echo "→ sync (apply=$APPLY)"

  local ITEMS_JSON
  ITEMS_JSON="$(gh api graphql -f query="
    query(\$owner:String!, \$number:Int!) {
      ${OWNER_PATH}(login:\$owner) {
        projectV2(number:\$number) {
          items(first:200) {
            nodes {
              id
              content { __typename ... on Issue { number title state url } }
              fieldValues(first:20) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2SingleSelectField { name } } }
                }
              }
            }
          }
        }
      }
    }" -F owner="$OWNER" -F number="$PROJECT_NUMBER")"

  local DIFFS=0 APPLIED=0
  while IFS= read -r row; do
    [[ -z "$row" ]] && continue
    local TASK_ID STATUS PRIORITY
    TASK_ID="$(echo "$row" | jq -r .id)"
    STATUS="$(echo "$row" | jq -r .status)"
    PRIORITY="$(echo "$row" | jq -r .priority)"

    local PROJ_ITEM
    PROJ_ITEM="$(echo "$ITEMS_JSON" | jq --arg p "[$TASK_ID]" '.data | (.organization // .user) | .projectV2.items.nodes | map(select(.content.title | startswith($p))) | .[0] // null')"
    [[ "$PROJ_ITEM" == "null" ]] && continue

    local ITEM_ID PROJ_STATUS PROJ_PRIORITY
    ITEM_ID="$(echo "$PROJ_ITEM" | jq -r .id)"
    PROJ_STATUS="$(echo "$PROJ_ITEM" | jq -r '.fieldValues.nodes[]? | select(.field.name == "Status") | .name // "Todo"' | head -n1)"
    PROJ_PRIORITY="$(echo "$PROJ_ITEM" | jq -r '.fieldValues.nodes[]? | select(.field.name == "Priority") | .name // "MEDIUM"' | head -n1)"

    local EXPECTED_STATUS
    case "$STATUS" in
      " ") EXPECTED_STATUS="Todo" ;;
      "~") EXPECTED_STATUS="In Progress" ;;
      "x") EXPECTED_STATUS="Done" ;;
    esac

    if [[ "$PROJ_STATUS" != "$EXPECTED_STATUS" ]]; then
      DIFFS=$((DIFFS+1))
      echo "  [$TASK_ID] STATUS drift: project=$PROJ_STATUS roadmap=$EXPECTED_STATUS"
      if $APPLY; then
        cmd_set_status "$ITEM_ID" "$EXPECTED_STATUS" >/dev/null
        APPLIED=$((APPLIED+1))
      fi
    fi
    if [[ "$PROJ_PRIORITY" != "$PRIORITY" ]]; then
      DIFFS=$((DIFFS+1))
      echo "  [$TASK_ID] PRIORITY drift: project=$PROJ_PRIORITY roadmap=$PRIORITY"
      if $APPLY; then
        cmd_set_priority "$ITEM_ID" "$PRIORITY" >/dev/null
        APPLIED=$((APPLIED+1))
      fi
    fi
  done < <(python3 "$PARSER")

  if $APPLY; then
    echo "→ sync done. drifts=$DIFFS applied=$APPLIED"
  else
    echo "→ sync dry-run. drifts=$DIFFS. re-run with --apply."
  fi
}

# ===========================================================================
# runs
# ===========================================================================

cmd_runs() {
  local COUNT="${1:-10}"
  local LOG="$REPO_ROOT/traces/runs.log"
  if [[ ! -f "$LOG" ]]; then
    echo "no runs yet (traces/runs.log does not exist)"
    return 0
  fi
  tail -n "$COUNT" "$LOG"
}

# ===========================================================================
# refresh-map — rebuild .claude/github-issue-map.json from authoritative state
# ===========================================================================
#
# When to run:
#   - After any manual GitHub UI edit (issue closed/renamed/deleted, milestone renamed).
#   - After bulk operations that bypass this script (e.g. `gh issue close <N>` outside helpers).
#   - First time setting up the map cache on a fork that already has open issues.
#
# Semantics:
#   - Open issues win over closed ones with the same prefix (handles dedup like #6 vs #46).
#   - PRs are excluded (the GitHub Issues endpoint returns PRs too — we filter `pull_request==null`).
#   - Milestones are read from /milestones (state=all so renamed-then-closed milestones still map).
#   - Atomic write via temp file; never partial-overwrites the cache.

cmd_refresh_map() {
  require_gh; load_cache
  echo "→ refreshing $ISSUE_MAP from authoritative GitHub state..."

  # 1. Milestones (REST, state=all).
  local MILESTONES_JSON
  MILESTONES_JSON="$(gh api "repos/$OWNER/$REPO/milestones?state=all&per_page=100" --paginate \
                     | jq '[.[] | {(.title): .number}] | add // {}')"

  # 2. Issues — fetch open and closed in one canonical list with state attached.
  local ALL_ISSUES
  ALL_ISSUES="$(gh api "repos/$OWNER/$REPO/issues?state=all&per_page=100" --paginate \
                | jq '[.[] | select(.pull_request == null) | {number, title, state}]')"

  # 3. Epics: match against the known phase list (same defaults as cmd_bootstrap),
  #    so the keys we cache are exactly what bootstrap looks up. On collisions,
  #    prefer open over closed, then lowest issue number (the original/canonical).
  #    Falls back to ltrimstr-derived key for any [Epic] not in the known list
  #    (e.g. ad-hoc phases someone added manually).
  local KNOWN_PHASES_JSON
  KNOWN_PHASES_JSON='["Pre-Phase-2 paper cuts","Phase A","Phase 2","Phase 1 deferred items"]'

  local EPICS_JSON
  EPICS_JSON="$(echo "$ALL_ISSUES" | jq --argjson known "$KNOWN_PHASES_JSON" '
    . as $issues
    | (
        # First pass: each known phase → best matching epic by (open, lowest-#).
        ($known | map(. as $phase | ({
            key: $phase,
            value: ($issues
              | map(select(.title | startswith("[Epic] " + $phase)))
              | sort_by(if .state == "open" then 0 else 1 end, .number)
              | (.[0].number // null))
          }))
          | map(select(.value != null))
          | from_entries) as $known_map
        # Second pass: any [Epic] not covered by a known phase prefix gets an
        # ltrimstr-derived key (covers ad-hoc / future phases added manually).
        | reduce ($issues[]
                  | select(.title | startswith("[Epic] "))
                  | select(.title as $t | ($known | any(. as $p | $t | startswith("[Epic] " + $p))) | not)
                 ) as $i ($known_map;
            ($i.title | ltrimstr("[Epic] ")) as $k
            | if has($k) then . else . + {($k): $i.number} end
          )
      )
  ')"

  # 4. Child issues: title matches "[<task-id>] ..." (excluding [Epic] titles).
  #    On collisions, prefer open over closed, then lowest issue number.
  local CHILDREN_JSON
  CHILDREN_JSON="$(echo "$ALL_ISSUES" | jq '
    [.[]
     | select(.title | test("^\\[[^\\]]+\\] "))
     | select(.title | startswith("[Epic] ") | not)
     | . + {key: (.title | capture("^\\[(?<id>[^\\]]+)\\]").id)}
    ]
    | group_by(.key)
    | map({(.[0].key): (sort_by(if .state == "open" then 0 else 1 end, .number) | .[0].number)})
    | add // {}
  ')"

  # 6. Compose.
  local NOW
  NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  mkdir -p "$(dirname "$ISSUE_MAP")"
  local TMP="$ISSUE_MAP.tmp.$$"
  jq -n \
    --arg owner "$OWNER" --arg repo "$REPO" --argjson pn "$PROJECT_NUMBER" --arg ts "$NOW" \
    --argjson ms "$MILESTONES_JSON" --argjson ep "$EPICS_JSON" --argjson is "$CHILDREN_JSON" \
    '{
      _meta: {
        owner: $owner,
        repo: $repo,
        project_number: $pn,
        refreshed_at: $ts,
        note: "Persistent cache of GitHub issue/milestone/epic associations. Sole writer: scripts/gh-project.sh. Run gh-project.sh refresh-map to rebuild from authoritative GitHub state."
      },
      milestones: $ms,
      epics: $ep,
      issues: $is
    }' > "$TMP"

  mv "$TMP" "$ISSUE_MAP"
  echo "→ wrote $ISSUE_MAP"
  jq '{_meta, counts: {milestones: (.milestones | length), epics: (.epics | length), issues: (.issues | length)}}' "$ISSUE_MAP"
}

# ===========================================================================
# dispatch
# ===========================================================================

case "${1:-}" in
  init) shift; cmd_init "$@" ;;
  bootstrap) shift; cmd_bootstrap "$@" ;;
  sync) shift; cmd_sync "$@" ;;
  milestone-status) shift; cmd_milestone_status "$@" ;;
  add-item) shift; cmd_add_item "$@" ;;
  add-subissue) shift; cmd_add_subissue "$@" ;;
  create-issue) shift; cmd_create_issue "$@" ;;
  create-epic) shift; cmd_create_epic "$@" ;;
  set-status) shift; cmd_set_status "$@" ;;
  set-priority) shift; cmd_set_priority "$@" ;;
  set-effort) shift; cmd_set_effort "$@" ;;
  next-unblocked) shift; cmd_next_unblocked "$@" ;;
  runs) shift; cmd_runs "$@" ;;
  refresh-map) shift; cmd_refresh_map "$@" ;;
  ""|-h|--help|help)
    cat <<EOF
gh-project.sh — GitHub Projects v2 helper (Naavik)

Subcommands:
  init                                Cache project IDs + auto-create Priority + Effort fields if missing.
  bootstrap [--apply] [--phase=X]     Parse ROADMAP.md → create Milestones + Epics + Issues + Project items.
                                      Default phases: Pre-Phase-2 paper cuts, Phase A, Phase 2, Phase 1.x deferred.
                                      Idempotent: consults .claude/github-issue-map.json first (no API
                                      round-trip) before falling back to GitHub search. Dry-run reports
                                      exists/PLAN for milestones + epics, not "would create if missing".
  refresh-map                         Rebuild .claude/github-issue-map.json from authoritative GitHub state.
                                      Run after any manual UI edit (rename/close/delete) that bypasses
                                      this script. Open issues win over closed ones on prefix collisions.
  sync [--apply]                      Diff ROADMAP vs Project; --apply pushes ROADMAP → Project.
  milestone-status [name]             JSON of items grouped by Status.
  add-item <issue-url>                Add issue/PR to Project. Returns item id.
  add-subissue <parent-num> <child>   Link child under parent epic via GraphQL addSubIssue.
  create-issue <id> <title> [...]     Create issue + add to Project + set Status/Priority/Effort (+ --parent N).
  create-epic <phase> [...]           Create [Epic] <phase> + add to Project (Status=In Progress, default HIGH/L).
  set-status <item-id> <Todo|In Progress|Done>
  set-priority <item-id> <CRITICAL|HIGH|MEDIUM|LOW>
  set-effort <item-id> <XS|S|M|L|XL>
  next-unblocked                      Next open Todo item (skips 'blocked' + 'epic' labels), sorted by Priority.
  runs [count]                        Tail last N entries from traces/runs.log (default 10).

State:
  .claude/github-project.json    Project ID + field option IDs (init once per fork).
  .claude/github-issue-map.json  Persistent {phase→epic#, task_id→issue#, phase→milestone#} cache.
                                 **This script is the sole writer.** Rebuild with \`refresh-map\`.

Guide: docs/AGENT_OPS.md.
EOF
    ;;
  *)
    echo "error: unknown subcommand '$1' (run with no args for help)" >&2
    exit 1 ;;
esac
