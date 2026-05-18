#!/usr/bin/env bash
# scripts/A.28-board-restructure.sh — one-shot migration runbook for A.28.
#
# Purpose:
#   - Add the Backlog status option to the GitHub Project v2 Status field.
#   - Create the Phase 2.5 milestone + epic.
#   - Bulk-move relocated A-rows (A.9, A.10, A.18..A.27) to Phase 2.5 milestone + Backlog status,
#     re-parent under [Epic] Phase 2.5.
#   - Relocate PC.6a (#62) from Pre-Phase-2 paper cuts → Phase 2 milestone (status stays Todo —
#     it's a Tier-2 current-cycle item, not Backlog).
#   - Bulk-move Phase 2 sub-tasks 2.1–2.10 to Backlog status (only 2.12 + 2.11 stay in Todo).
#   - Bulk-move DEF-01..DEF-25 to Backlog status (Phase 1 deferred items).
#
# Idempotent: re-run is safe; each step checks current state before mutating.
# Reference: docs/plans/archive/20-A.28-board-restructure.md § E.
# Single-writer rule: all GitHub state mutations go through scripts/gh-project.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --apply) DRY_RUN=false ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--dry-run | --apply]

  --dry-run   Print what each step would do without executing.
  --apply     Actually execute the migration (default).

The migration is idempotent — re-running is safe. Each step checks current state
before mutating. Single-writer rule: writes go through scripts/gh-project.sh.

Reference: docs/plans/archive/20-A.28-board-restructure.md § E.
EOF
      exit 0
      ;;
  esac
done

GH_PROJECT="scripts/gh-project.sh"
ISSUE_MAP=".claude/github-issue-map.json"
CACHE=".claude/github-project.json"

run() {
  # In dry-run, print the command. In apply, run it.
  if $DRY_RUN; then
    echo "  DRY-RUN $*"
  else
    eval "$@"
  fi
}

echo "=== A.28 board restructure ==="
echo "mode: $([ "$DRY_RUN" = true ] && echo "dry-run" || echo "apply")"
echo

# -----------------------------------------------------------------------------
# Step 1 — Add Backlog status option (idempotent via cmd_add_status's check).
# -----------------------------------------------------------------------------
echo "Step 1: ensure Backlog status option exists..."
if jq -e '.status_options.backlog // empty' "$CACHE" >/dev/null 2>&1 && \
   [[ -n "$(jq -r '.status_options.backlog // empty' "$CACHE")" ]]; then
  echo "  Backlog status already in cache (id=$(jq -r '.status_options.backlog' "$CACHE"))"
else
  run "bash $GH_PROJECT add-status Backlog --color GRAY"
fi
echo

# -----------------------------------------------------------------------------
# Step 2 — Create Phase 2.5 milestone (idempotent via ensure_milestone).
# -----------------------------------------------------------------------------
echo "Step 2: ensure Phase 2.5 milestone..."
PP_MILESTONE_NUM=""
if [[ -n "$(jq -r '.milestones["Phase 2.5"] // empty' "$ISSUE_MAP" 2>/dev/null)" ]]; then
  PP_MILESTONE_NUM="$(jq -r '.milestones["Phase 2.5"]' "$ISSUE_MAP")"
  echo "  milestone exists → #$PP_MILESTONE_NUM"
else
  if $DRY_RUN; then
    echo "  DRY-RUN bash $GH_PROJECT create-milestone \"Phase 2.5\" --description \"QoL agent-system follow-ups deferred from Phase A until Phase 2 scrapers clear. Filed 2026-05-17 per A.28.\""
  else
    PP_MILESTONE_NUM="$(bash $GH_PROJECT create-milestone "Phase 2.5" \
      --description "QoL agent-system follow-ups deferred from Phase A until Phase 2 scrapers clear. Filed 2026-05-17 per A.28.")"
    echo "  milestone created → #$PP_MILESTONE_NUM"
  fi
fi
echo

# -----------------------------------------------------------------------------
# Step 3 — Create [Epic] Phase 2.5 (idempotent via find_issue_by_prefix).
# -----------------------------------------------------------------------------
echo "Step 3: ensure Phase 2.5 epic..."
PP_EPIC_NUM=""
if [[ -n "$(jq -r '.epics["Phase 2.5"] // empty' "$ISSUE_MAP" 2>/dev/null)" ]]; then
  PP_EPIC_NUM="$(jq -r '.epics["Phase 2.5"]' "$ISSUE_MAP")"
  echo "  epic exists → #$PP_EPIC_NUM"
else
  if $DRY_RUN; then
    echo "  DRY-RUN bash $GH_PROJECT create-epic \"Phase 2.5\" --priority MEDIUM --effort XL"
  else
    bash $GH_PROJECT create-epic "Phase 2.5" --priority MEDIUM --effort XL >/dev/null
    PP_EPIC_NUM="$(jq -r '.epics["Phase 2.5"]' "$ISSUE_MAP")"
    echo "  epic created → #$PP_EPIC_NUM"
  fi
fi
echo

# -----------------------------------------------------------------------------
# Step 4 — Move relocated A-rows to Phase 2.5 milestone + Backlog status.
# -----------------------------------------------------------------------------
echo "Step 4: relocate A-rows (A.9, A.10, A.18-A.27) → Phase 2.5 milestone + Backlog..."
RELOCATED_A=("A.9" "A.10" "A.18" "A.19" "A.20" "A.21" "A.22" "A.23" "A.24" "A.25" "A.26" "A.27")
for TASK_ID in "${RELOCATED_A[@]}"; do
  ISSUE_NUM="$(jq -r --arg id "$TASK_ID" '.issues[$id] // empty' "$ISSUE_MAP")"
  if [[ -z "$ISSUE_NUM" ]]; then
    echo "  WARN: $TASK_ID not in issue map — skipping (Issue not yet created)"
    continue
  fi
  # Update milestone (gh issue edit doesn't cascade to Project Status — both calls required).
  CURRENT_MS="$(gh issue view "$ISSUE_NUM" --json milestone -q '.milestone.title' 2>/dev/null || echo "")"
  if [[ "$CURRENT_MS" != "Phase 2.5" ]]; then
    run "gh issue edit $ISSUE_NUM --milestone \"Phase 2.5\""
  fi
  # Update Project Status field to Backlog.
  ITEM_ID="$(bash $GH_PROJECT item-id "$ISSUE_NUM" 2>/dev/null || echo "")"
  if [[ -n "$ITEM_ID" ]]; then
    CURRENT_STATUS="$(gh api graphql -f query="
      query(\$item:ID!) { node(id:\$item) { ... on ProjectV2Item {
        fieldValues(first:20) { nodes { ... on ProjectV2ItemFieldSingleSelectValue {
          name field { ... on ProjectV2SingleSelectField { name } } } } }
      }}}" -F item="$ITEM_ID" 2>/dev/null \
      | jq -r '.data.node.fieldValues.nodes[]? | select(.field.name == "Status") | .name // ""' \
      | head -n1)"
    if [[ "$CURRENT_STATUS" != "Backlog" ]]; then
      run "bash $GH_PROJECT set-status $ITEM_ID Backlog"
      echo "  MIRROR action=set-status item=$ISSUE_NUM from=$CURRENT_STATUS to=Backlog"
    else
      echo "  $TASK_ID (#$ISSUE_NUM) already Backlog — skipping"
    fi
  fi
  # Re-parent under [Epic] Phase 2.5 (idempotent — addSubIssue is a no-op if already linked).
  if [[ -n "$PP_EPIC_NUM" ]]; then
    run "bash $GH_PROJECT add-subissue $PP_EPIC_NUM $ISSUE_NUM 2>/dev/null || true"
  fi
  echo "  $TASK_ID (#$ISSUE_NUM) → Phase 2.5 / Backlog"
done
echo

# -----------------------------------------------------------------------------
# Step 5 — Relocate PC.6a (#62) from Pre-Phase-2 paper cuts → Phase 2 milestone.
#           Status STAYS Todo (PC.6a is Tier-2 current-cycle, not Backlog).
# -----------------------------------------------------------------------------
echo "Step 5: relocate PC.6a (#62) → Phase 2 milestone (Status stays Todo)..."
PC6A_ISSUE_NUM="$(jq -r '.issues["PC.6a"] // empty' "$ISSUE_MAP")"
if [[ -n "$PC6A_ISSUE_NUM" ]]; then
  CURRENT_MS="$(gh issue view "$PC6A_ISSUE_NUM" --json milestone -q '.milestone.title' 2>/dev/null || echo "")"
  if [[ "$CURRENT_MS" != "Phase 2" ]]; then
    run "gh issue edit $PC6A_ISSUE_NUM --milestone \"Phase 2\""
    echo "  PC.6a (#$PC6A_ISSUE_NUM) milestone: $CURRENT_MS → Phase 2"
  else
    echo "  PC.6a (#$PC6A_ISSUE_NUM) already in Phase 2 — skipping"
  fi
else
  echo "  WARN: PC.6a not in issue map — skipping"
fi
echo

# -----------------------------------------------------------------------------
# Step 6 — Move Phase 2 sub-tasks 2.1–2.10 to Backlog (2.12 + 2.11 stay in Todo).
# -----------------------------------------------------------------------------
echo "Step 6: relocate Phase 2 sub-tasks 2.1-2.10 → Backlog status..."
PHASE2_BACKLOG=("2.1" "2.2" "2.3" "2.4" "2.5" "2.6" "2.7" "2.8" "2.9" "2.10")
for TASK_ID in "${PHASE2_BACKLOG[@]}"; do
  ISSUE_NUM="$(jq -r --arg id "$TASK_ID" '.issues[$id] // empty' "$ISSUE_MAP")"
  [[ -z "$ISSUE_NUM" ]] && { echo "  WARN: $TASK_ID not in issue map — skipping"; continue; }
  ITEM_ID="$(bash $GH_PROJECT item-id "$ISSUE_NUM" 2>/dev/null || echo "")"
  if [[ -n "$ITEM_ID" ]]; then
    CURRENT_STATUS="$(gh api graphql -f query="
      query(\$item:ID!) { node(id:\$item) { ... on ProjectV2Item {
        fieldValues(first:20) { nodes { ... on ProjectV2ItemFieldSingleSelectValue {
          name field { ... on ProjectV2SingleSelectField { name } } } } }
      }}}" -F item="$ITEM_ID" 2>/dev/null \
      | jq -r '.data.node.fieldValues.nodes[]? | select(.field.name == "Status") | .name // ""' \
      | head -n1)"
    if [[ "$CURRENT_STATUS" != "Backlog" ]]; then
      run "bash $GH_PROJECT set-status $ITEM_ID Backlog"
      echo "  MIRROR action=set-status item=$ISSUE_NUM from=$CURRENT_STATUS to=Backlog"
    else
      echo "  $TASK_ID (#$ISSUE_NUM) already Backlog — skipping"
    fi
  fi
done
echo

# -----------------------------------------------------------------------------
# Step 7 — Move DEF-01..DEF-25 (Phase 1 deferred items) to Backlog status.
# -----------------------------------------------------------------------------
echo "Step 7: relocate DEF-01..DEF-25 → Backlog status..."
DEFERRED_BACKLOG=(
  DEF-01 DEF-02 DEF-03 DEF-04 DEF-05 DEF-06 DEF-07 DEF-08 DEF-09 DEF-10
  DEF-11 DEF-12 DEF-13 DEF-14 DEF-15 DEF-16 DEF-17 DEF-18 DEF-19 DEF-20
  DEF-21 DEF-22 DEF-23 DEF-24 DEF-25
)
for TASK_ID in "${DEFERRED_BACKLOG[@]}"; do
  ISSUE_NUM="$(jq -r --arg id "$TASK_ID" '.issues[$id] // empty' "$ISSUE_MAP")"
  [[ -z "$ISSUE_NUM" ]] && continue
  ITEM_ID="$(bash $GH_PROJECT item-id "$ISSUE_NUM" 2>/dev/null || echo "")"
  if [[ -n "$ITEM_ID" ]]; then
    CURRENT_STATUS="$(gh api graphql -f query="
      query(\$item:ID!) { node(id:\$item) { ... on ProjectV2Item {
        fieldValues(first:20) { nodes { ... on ProjectV2ItemFieldSingleSelectValue {
          name field { ... on ProjectV2SingleSelectField { name } } } } }
      }}}" -F item="$ITEM_ID" 2>/dev/null \
      | jq -r '.data.node.fieldValues.nodes[]? | select(.field.name == "Status") | .name // ""' \
      | head -n1)"
    if [[ "$CURRENT_STATUS" != "Backlog" ]]; then
      run "bash $GH_PROJECT set-status $ITEM_ID Backlog"
      echo "  MIRROR action=set-status item=$ISSUE_NUM from=$CURRENT_STATUS to=Backlog"
    fi
  fi
done
echo

# -----------------------------------------------------------------------------
# Summary.
# -----------------------------------------------------------------------------
echo "=== done ==="
if $DRY_RUN; then
  echo "Mode: DRY-RUN — no mutations executed. Re-run with --apply to perform the migration."
else
  echo "Mode: APPLY — migration complete."
  echo
  echo "Verification:"
  echo "  bash $GH_PROJECT milestone-status \"Phase 2.5\""
  echo "  bash $GH_PROJECT milestone-status \"Phase 2\""
  echo "  bash $GH_PROJECT next-unblocked"
  echo "  bash $GH_PROJECT backlog-by-epic --top 3"
  echo "  jq '.status_options' $CACHE  # expect 4 keys: todo, in_progress, done, backlog"
fi
