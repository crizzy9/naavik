"""gh — GitHub Project + Issue ops (native Python; plan 25 D.7).

Replaces the subprocess wrappers around `scripts/gh-project.sh` with native
Python that drives the GitHub Projects v2 GraphQL API + `gh` CLI for
repo-scoped ops (issue create / close / edit) via `lib/github_api.py`.

The single-writer contract is preserved: `.claude/naavik-ops gh` is still the
sole entry point to `.claude/github-issue-map.json` + GitHub Project state.
Only the implementation language flips from bash to Python; agents call the
dispatcher exactly as before.

# Subcommands

  init                                   Cache project IDs + auto-create
                                         Priority + Effort fields if missing.
  bootstrap [--apply] [--phase=X]        Parse ROADMAP.md → Milestones + Epics
                                         + Issues + Project items. Idempotent.
  sync [--apply]                         Diff ROADMAP vs Project; --apply
                                         pushes ROADMAP → Project. Backlog
                                         preserved (post-A.28 4-status).
  milestone-status [name]                JSON: items grouped by Status.
  add-item <issue-url>                   Add issue/PR to Project; print item id.
  add-subissue <parent-num> <child-num>  Link child issue under parent epic.
  create-issue <id> <title> [...]        Create issue + add to Project + set
                                         Status/Priority/Effort. Idempotent.
  create-epic <phase> [...]              Create `[Epic] <phase>` + add to
                                         Project. Idempotent.
  create-milestone <name> [--description]
                                         Idempotent milestone create. Stdout: #.
  item-id <issue-num>                    Resolve Issue # → Project item id.
  set-status <item-id> <status>          Project Status field write.
  set-priority <item-id> <pri>           Project Priority field write.
  set-effort <item-id> <effort>          Project Effort field write.
  add-status <name> [--color C]          Add option to Status single-select.
  next-unblocked                         Highest-priority unblocked Todo item.
  backlog-by-epic [--top N]              Backlog items grouped by parent epic.
  runs [count]                           Tail traces/runs.log.
  refresh-map                            Rebuild map cache from authoritative
                                         GitHub state.

  update-issue-title <issue-num> <new-title>      [NEW per D.7 — D.6 dep]
                                         Edit issue title + write to map cache.
                                         Atomic.
  close-issue <issue-num> [--reason completed|not_planned]
                                         [NEW per D.7 — D.6 dep + #76 cleanup]
                                         Close issue + write to map cache.

# State files

  .claude/github-project.json    — Project ID + field option IDs.
  .claude/github-issue-map.json  — Persistent map cache. Sole writer: this
                                   module (atomic tmp + os.replace via
                                   `lib/jsonl.write_json`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from naavik_ops.lib import NaavikOpsError, jsonl, roadmap
from naavik_ops.lib.github_api import gh_graphql

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = REPO_ROOT / ".claude" / "github-project.json"
ISSUE_MAP_PATH = REPO_ROOT / ".claude" / "github-issue-map.json"
RUNS_LOG_PATH = REPO_ROOT / "traces" / "runs.log"


# ---------------------------------------------------------------------------
# Cache loaders
# ---------------------------------------------------------------------------


def _require_gh() -> None:
    if shutil.which("gh") is None:
        raise NaavikOpsError("gh CLI not on PATH. nix develop or https://cli.github.com")


def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.is_file():
        raise NaavikOpsError(f"{CACHE_PATH} not found — run `naavik-ops gh init` first.")
    return jsonl.read_json(CACHE_PATH)


def _save_cache(data: dict[str, Any]) -> None:
    jsonl.write_json(CACHE_PATH, data)


# ---------------------------------------------------------------------------
# Issue-map cache (persistent {phase → epic#, task_id → issue#, phase → milestone#})
# ---------------------------------------------------------------------------


def _map_init() -> dict[str, Any]:
    """Read the map; return a fresh skeleton if missing."""
    if ISSUE_MAP_PATH.is_file():
        return jsonl.read_json(ISSUE_MAP_PATH)
    return _empty_map_skeleton()


def _empty_map_skeleton() -> dict[str, Any]:
    cache = _load_cache() if CACHE_PATH.is_file() else {}
    return {
        "_meta": {
            "owner": cache.get("owner", ""),
            "repo": cache.get("repo", ""),
            "project_number": cache.get("project_number", 0),
            "refreshed_at": _now_iso(),
            "note": (
                "Persistent cache of GitHub issue/milestone/epic associations. "
                "Sole writer: .claude/naavik-ops gh (native Python). Run "
                "`naavik-ops gh refresh-map` to rebuild from authoritative GitHub state."
            ),
        },
        "milestones": {},
        "epics": {},
        "issues": {},
    }


def _map_save(data: dict[str, Any]) -> None:
    jsonl.write_json(ISSUE_MAP_PATH, data)


def _map_lookup(category: str, key: str) -> int | None:
    """Return the cached int or None."""
    if not ISSUE_MAP_PATH.is_file():
        return None
    data = jsonl.read_json(ISSUE_MAP_PATH)
    val = (data.get(category) or {}).get(key)
    if isinstance(val, int):
        return val
    return None


def _map_set(category: str, key: str, value: int) -> None:
    """Set map[category][key] = value, atomic write."""
    data = _map_init()
    section = data.setdefault(category, {})
    section[key] = value
    _map_save(data)


# ---------------------------------------------------------------------------
# Time helper
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Low-level GraphQL helpers (single field writes)
# ---------------------------------------------------------------------------


_QUERY_SET_SELECT = """
mutation($p:ID!, $i:ID!, $f:ID!, $o:String!) {
  updateProjectV2ItemFieldValue(input:{
    projectId:$p, itemId:$i, fieldId:$f,
    value:{singleSelectOptionId:$o}
  }) { projectV2Item { id } }
}
""".strip()


def _set_select(project_id: str, item_id: str, field_id: str, option_id: str) -> None:
    if not field_id or not option_id:
        return  # field/option not configured — bash version was tolerant
    gh_graphql(
        _QUERY_SET_SELECT,
        variables={"p": project_id, "i": item_id, "f": field_id, "o": option_id},
    )


_QUERY_ISSUE_NODE_ID = """
query($owner:String!, $repo:String!, $num:Int!) {
  repository(owner:$owner, name:$repo) { issue(number:$num) { id } }
}
""".strip()


def _issue_node_id(owner: str, repo: str, num: int) -> str:
    data = gh_graphql(_QUERY_ISSUE_NODE_ID, variables={"owner": owner, "repo": repo, "num": num})
    return ((data.get("data") or {}).get("repository") or {}).get("issue", {}).get("id") or ""


_QUERY_ADD_ITEM = """
mutation($p:ID!, $c:ID!) {
  addProjectV2ItemById(input:{projectId:$p, contentId:$c}) { item { id } }
}
""".strip()


def _add_issue_to_project(project_id: str, content_id: str) -> str:
    data = gh_graphql(_QUERY_ADD_ITEM, variables={"p": project_id, "c": content_id})
    return (data.get("data") or {}).get("addProjectV2ItemById", {}).get("item", {}).get("id") or ""


_QUERY_ADD_SUBISSUE = """
mutation($parent:ID!, $child:ID!) {
  addSubIssue(input:{issueId:$parent, subIssueId:$child}) {
    subIssue { number }
  }
}
""".strip()


def _add_subissue_by_id(parent_id: str, child_id: str) -> None:
    try:
        gh_graphql(_QUERY_ADD_SUBISSUE, variables={"parent": parent_id, "child": child_id})
    except NaavikOpsError:
        # Bash tolerates failures here (`add_subissue_by_id ... || true`). Match.
        return


# ---------------------------------------------------------------------------
# gh CLI subprocess helpers (issues, milestones, labels — REST + commands)
# ---------------------------------------------------------------------------


def _gh(*args: str, check: bool = True, input_str: str | None = None) -> str:
    """Run `gh <args>`. Returns stdout. Captures stderr in NaavikOpsError."""
    _require_gh()
    cmd = ["gh", *args]
    try:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True, input=input_str)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"gh {' '.join(args)} failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    return result.stdout


def _gh_api(path: str, *flags: str, method: str | None = None) -> Any:
    """Call `gh api <path> [-X METHOD] [<flags>]`. Returns parsed JSON."""
    args = ["api", path]
    if method:
        args.extend(["-X", method])
    args.extend(flags)
    out = _gh(*args)
    return json.loads(out) if out.strip() else {}


def _gh_api_paginate(path: str) -> list[Any]:
    """Call `gh api <path> --paginate` (REST). Returns parsed JSON list."""
    out = _gh("api", path, "--paginate")
    return json.loads(out) if out.strip() else []


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def _ensure_milestone(name: str, description: str | None = None) -> int:
    """Idempotent milestone create. Returns the milestone number."""
    cached = _map_lookup("milestones", name)
    if cached:
        return cached

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]

    milestones = _gh_api_paginate(f"repos/{owner}/{repo}/milestones?state=all&per_page=100")
    if isinstance(milestones, list):
        for ms in milestones:
            if isinstance(ms, dict) and ms.get("title") == name:
                num = int(ms["number"])
                _map_set("milestones", name, num)
                return num

    # Create.
    desc = description or f"Mirrored from ROADMAP.md § {name}"
    new = _gh_api(
        f"repos/{owner}/{repo}/milestones",
        "-f",
        f"title={name}",
        "-f",
        f"description={desc}",
        method="POST",
    )
    num = int(new["number"])
    _map_set("milestones", name, num)
    return num


def _lookup_milestone(name: str) -> int | None:
    """Read-only milestone lookup — never creates. For bootstrap dry-run."""
    cached = _map_lookup("milestones", name)
    if cached:
        return cached
    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]
    milestones = _gh_api_paginate(f"repos/{owner}/{repo}/milestones?state=all&per_page=100")
    if isinstance(milestones, list):
        for ms in milestones:
            if isinstance(ms, dict) and ms.get("title") == name:
                num = int(ms["number"])
                _map_set("milestones", name, num)
                return num
    return None


# ---------------------------------------------------------------------------
# Issue existence (map-first, search-API fallback per single-writer rule)
# ---------------------------------------------------------------------------


def _find_issue_by_prefix(
    prefix: str, map_category: str | None = None, map_key: str | None = None
) -> int | None:
    """Map-first existence check. Backfill on cache-miss → live-hit."""
    if map_category and map_key:
        cached = _map_lookup(map_category, map_key)
        if cached:
            return cached

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]
    query = urllib.parse.quote_plus(f"repo:{owner}/{repo} in:title {prefix}")
    try:
        data = _gh_api(f"search/issues?q={query}")
    except NaavikOpsError:
        return None
    items = data.get("items") or []
    for item in items:
        title = item.get("title") or ""
        if title.startswith(prefix):
            num = int(item["number"])
            if map_category and map_key:
                _map_set(map_category, map_key, num)
            return num
    return None


def _ensure_label(name: str, color: str = "ededed", description: str = "Auto-created") -> None:
    """Idempotent label create. Bash version swallows errors — match."""
    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]
    try:
        _gh(
            "label",
            "create",
            name,
            "--repo",
            f"{owner}/{repo}",
            "--color",
            color,
            "--description",
            description,
        )
    except NaavikOpsError:
        return  # already exists


# ---------------------------------------------------------------------------
# Phase mapping helpers
# ---------------------------------------------------------------------------


def _phase_to_label(phase: str) -> str:
    if phase == "Phase A":
        return "phase:A"
    if phase == "Pre-Phase-2 paper cuts":
        return "phase:pre-2"
    if phase == "Phase 1 deferred items":
        return "phase:1.x"
    m = re.match(r"^Phase (\d+)$", phase)
    if m:
        return f"phase:{m.group(1)}"
    return ""


def _phase_to_category_labels(phase: str) -> str:
    if phase == "Phase A":
        return "agent-system"
    if phase == "Pre-Phase-2 paper cuts":
        return "paper-cut"
    if phase == "Phase 1 deferred items":
        return "phase-1-deferred"
    return ""


def _phase_to_default_effort(phase: str) -> str:
    if phase in ("Phase A", "Pre-Phase-2 paper cuts"):
        return "S"
    if phase == "Phase 1 deferred items":
        return "M"
    return "M"


# ---------------------------------------------------------------------------
# set-status / set-priority / set-effort
# ---------------------------------------------------------------------------


def _status_option_id(cache: dict[str, Any], status: str) -> str:
    opts = cache.get("status_options") or {}
    norm = status.strip().lower()
    if norm in ("todo", "to do"):
        return opts.get("todo") or ""
    if norm in ("in progress", "in_progress"):
        return opts.get("in_progress") or ""
    if norm == "done":
        return opts.get("done") or ""
    if norm == "backlog":
        opt = opts.get("backlog") or ""
        if not opt:
            raise NaavikOpsError(
                "Backlog status option not found in cache — run "
                "`naavik-ops gh add-status Backlog --color GRAY` then `init` to refresh"
            )
        return opt
    raise NaavikOpsError(f"unknown status '{status}' (expected: Todo, In Progress, Done, Backlog)")


def _priority_option_id(cache: dict[str, Any], priority: str) -> str:
    norm = priority.strip().upper()
    pri_opts = cache.get("priority_options") or {}
    mapping = {
        "CRITICAL": "critical",
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
    }
    if norm not in mapping:
        raise NaavikOpsError(
            f"unknown priority '{priority}' (expected: CRITICAL, HIGH, MEDIUM, LOW)"
        )
    return pri_opts.get(mapping[norm]) or ""


def _effort_option_id(cache: dict[str, Any], effort: str) -> str:
    norm = effort.strip().upper()
    eff_opts = cache.get("effort_options") or {}
    mapping = {"XS": "xs", "S": "s", "M": "m", "L": "l", "XL": "xl"}
    if norm not in mapping:
        raise NaavikOpsError(f"unknown effort '{effort}' (expected: XS, S, M, L, XL)")
    return eff_opts.get(mapping[norm]) or ""


def cmd_set_status(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops gh set-status <item-id> <status>\n")
        return 2
    cache = _load_cache()
    item_id, status = rest[0], " ".join(rest[1:])
    option_id = _status_option_id(cache, status)
    if not option_id:
        raise NaavikOpsError(f"status '{status}' has no cached option-id")
    _set_select(cache["project_id"], item_id, cache["status_field_id"], option_id)
    sys.stdout.write(f"status set: {status}\n")
    return 0


def cmd_set_priority(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops gh set-priority <item-id> <pri>\n")
        return 2
    cache = _load_cache()
    field_id = cache.get("priority_field_id") or ""
    if not field_id:
        sys.stderr.write("warning: Priority field not configured — skipping\n")
        return 0
    item_id, pri = rest[0], rest[1]
    option_id = _priority_option_id(cache, pri)
    _set_select(cache["project_id"], item_id, field_id, option_id)
    sys.stdout.write(f"priority set: {pri.upper()}\n")
    return 0


def cmd_set_effort(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops gh set-effort <item-id> <effort>\n")
        return 2
    cache = _load_cache()
    field_id = cache.get("effort_field_id") or ""
    if not field_id:
        sys.stderr.write("warning: Effort field not configured — skipping\n")
        return 0
    item_id, eff = rest[0], rest[1]
    option_id = _effort_option_id(cache, eff)
    _set_select(cache["project_id"], item_id, field_id, option_id)
    sys.stdout.write(f"effort set: {eff.upper()}\n")
    return 0


# Programmatic helpers used by task.py / release.py
def set_status(item_id: str, status: str) -> None:
    if not item_id or not status:
        raise NaavikOpsError("set_status requires non-empty item_id + status")
    cmd_set_status([item_id, status])


def set_priority(item_id: str, priority: str) -> None:
    cmd_set_priority([item_id, priority])


def set_effort(item_id: str, effort: str) -> None:
    cmd_set_effort([item_id, effort])


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


_QUERY_INIT = """
query($owner:String!, $number:Int!) {
  %s(login:$owner) {
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
}
""".strip()


_QUERY_CREATE_FIELD = """
mutation($p:ID!, $name:String!, $opts:[ProjectV2SingleSelectFieldOptionInput!]!) {
  createProjectV2Field(input:{
    projectId:$p, dataType:SINGLE_SELECT, name:$name,
    singleSelectOptions:$opts
  }) { projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
}
""".strip()


def cmd_init(rest: Sequence[str]) -> int:
    """Interactive prompt + project / field discovery + cache write."""
    _ = rest
    _require_gh()

    owner = input("GitHub owner (user or org, e.g. crizzy9): ").strip()
    repo = input("GitHub repo (e.g. naavik): ").strip()
    project_number = int(input("Project number (the integer in the project URL): ").strip())

    sys.stdout.write("→ resolving project + fields via GraphQL...\n")

    project_json: dict[str, Any] | None = None
    scope = "user"
    try:
        user_json = gh_graphql(
            _QUERY_INIT % "user", variables={"owner": owner, "number": project_number}
        )
        if ((user_json.get("data") or {}).get("user") or {}).get("projectV2"):
            project_json = user_json
    except NaavikOpsError:
        project_json = None

    if project_json is None:
        org_json = gh_graphql(
            _QUERY_INIT % "organization", variables={"owner": owner, "number": project_number}
        )
        if not ((org_json.get("data") or {}).get("organization") or {}).get("projectV2"):
            raise NaavikOpsError(f"project not found for {owner} #{project_number}")
        project_json = org_json
        scope = "organization"

    proj_data = ((project_json.get("data") or {}).get(scope) or {}).get("projectV2") or {}
    project_id = proj_data.get("id") or ""
    if not project_id:
        raise NaavikOpsError(f"project not found for {owner} #{project_number}")

    fields = proj_data.get("fields", {}).get("nodes") or []

    def _field_id(name: str) -> str:
        for f in fields:
            if f.get("name") == name:
                return f.get("id") or ""
        return ""

    def _option_id(field_name: str, option_name_match: list[str]) -> str:
        for f in fields:
            if f.get("name") == field_name:
                for opt in f.get("options") or []:
                    if opt.get("name") in option_name_match:
                        return opt.get("id") or ""
        return ""

    def _option_id_by_lower(field_name: str, lower: str) -> str:
        for f in fields:
            if f.get("name") == field_name:
                for opt in f.get("options") or []:
                    if (opt.get("name") or "").lower() == lower:
                        return opt.get("id") or ""
        return ""

    status_field_id = _field_id("Status")
    priority_field_id = _field_id("Priority")
    effort_field_id = _field_id("Effort")

    # Auto-create Priority field if missing.
    if not priority_field_id:
        sys.stdout.write("→ Priority field missing — creating CRITICAL/HIGH/MEDIUM/LOW...\n")
        new = gh_graphql(
            _QUERY_CREATE_FIELD,
            variables={
                "p": project_id,
                "name": "Priority",
                "opts": json.dumps(
                    [
                        {"name": "CRITICAL", "color": "RED", "description": "Drop everything"},
                        {"name": "HIGH", "color": "ORANGE", "description": "Next up"},
                        {"name": "MEDIUM", "color": "YELLOW", "description": "Normal"},
                        {"name": "LOW", "color": "GRAY", "description": "Backlog"},
                    ]
                ),
            },
        )
        priority_field_id = ((new.get("data") or {}).get("createProjectV2Field") or {}).get(
            "projectV2Field", {}
        ).get("id") or ""
        # Re-fetch.
        project_json = gh_graphql(
            _QUERY_INIT % scope, variables={"owner": owner, "number": project_number}
        )
        fields = (((project_json.get("data") or {}).get(scope) or {}).get("projectV2") or {}).get(
            "fields", {}
        ).get("nodes") or []

    # Auto-create Effort field if missing.
    if not effort_field_id:
        sys.stdout.write("→ Effort field missing — creating XS/S/M/L/XL...\n")
        new = gh_graphql(
            _QUERY_CREATE_FIELD,
            variables={
                "p": project_id,
                "name": "Effort",
                "opts": json.dumps(
                    [
                        {"name": "XS", "color": "GRAY", "description": "Less than 1 hour"},
                        {"name": "S", "color": "GREEN", "description": "1-4 hours"},
                        {"name": "M", "color": "BLUE", "description": "1 day"},
                        {"name": "L", "color": "PURPLE", "description": "2-3 days"},
                        {"name": "XL", "color": "RED", "description": "More than 1 week"},
                    ]
                ),
            },
        )
        effort_field_id = ((new.get("data") or {}).get("createProjectV2Field") or {}).get(
            "projectV2Field", {}
        ).get("id") or ""
        project_json = gh_graphql(
            _QUERY_INIT % scope, variables={"owner": owner, "number": project_number}
        )
        fields = (((project_json.get("data") or {}).get(scope) or {}).get("projectV2") or {}).get(
            "fields", {}
        ).get("nodes") or []

    status_todo = _option_id("Status", ["Todo", "To do"])
    status_inprog = _option_id("Status", ["In Progress", "In progress"])
    status_done = _option_id("Status", ["Done"])
    status_backlog = _option_id("Status", ["Backlog"])

    cache = {
        "owner": owner,
        "repo": repo,
        "scope": scope,
        "project_id": project_id,
        "project_number": project_number,
        "project_url": f"https://github.com/{scope}s/{owner}/projects/{project_number}",
        "status_field_id": status_field_id,
        "priority_field_id": priority_field_id,
        "effort_field_id": effort_field_id,
        "status_options": {
            "todo": status_todo,
            "in_progress": status_inprog,
            "done": status_done,
            "backlog": status_backlog,
        },
        "priority_options": {
            "critical": _option_id_by_lower("Priority", "critical"),
            "high": _option_id_by_lower("Priority", "high"),
            "medium": _option_id_by_lower("Priority", "medium"),
            "low": _option_id_by_lower("Priority", "low"),
        },
        "effort_options": {
            "xs": _option_id_by_lower("Effort", "xs"),
            "s": _option_id_by_lower("Effort", "s"),
            "m": _option_id_by_lower("Effort", "m"),
            "l": _option_id_by_lower("Effort", "l"),
            "xl": _option_id_by_lower("Effort", "xl"),
        },
    }
    _save_cache(cache)
    sys.stdout.write(f"→ cached at {CACHE_PATH}\n")
    sys.stdout.write(json.dumps(cache, indent=2) + "\n")
    return 0


# ---------------------------------------------------------------------------
# add-item / add-subissue / create-milestone / item-id
# ---------------------------------------------------------------------------


_QUERY_RESOLVE_URL = """
query($url:URI!) {
  resource(url:$url) {
    ... on Issue { id }
    ... on PullRequest { id }
  }
}
""".strip()


def cmd_add_item(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write("usage: naavik-ops gh add-item <issue-url>\n")
        return 2
    cache = _load_cache()
    issue_url = rest[0]
    data = gh_graphql(_QUERY_RESOLVE_URL, variables={"url": issue_url})
    content_id = ((data.get("data") or {}).get("resource") or {}).get("id") or ""
    if not content_id:
        raise NaavikOpsError(f"could not resolve {issue_url}")
    item_id = _add_issue_to_project(cache["project_id"], content_id)
    sys.stdout.write(item_id + "\n")
    return 0


def cmd_add_subissue(rest: Sequence[str]) -> int:
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops gh add-subissue <parent-num> <child-num>\n")
        return 2
    cache = _load_cache()
    parent_num, child_num = int(rest[0]), int(rest[1])
    parent_id = _issue_node_id(cache["owner"], cache["repo"], parent_num)
    child_id = _issue_node_id(cache["owner"], cache["repo"], child_num)
    if not parent_id or not child_id:
        raise NaavikOpsError("could not resolve parent or child issue id")
    _add_subissue_by_id(parent_id, child_id)
    sys.stdout.write(f"linked: #{child_num} → parent #{parent_num}\n")
    return 0


def cmd_create_milestone(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write('usage: naavik-ops gh create-milestone <name> [--description "..."]\n')
        return 2
    name = rest[0]
    description = f"Mirrored from ROADMAP.md § {name}"
    args = list(rest[1:])
    i = 0
    while i < len(args):
        if args[i] == "--description" and i + 1 < len(args):
            description = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{args[i]}'")
    num = _ensure_milestone(name, description)
    sys.stdout.write(f"{num}\n")
    return 0


_QUERY_ITEM_ID = """
query($owner:String!, $repo:String!, $num:Int!) {
  repository(owner:$owner, name:$repo) {
    issue(number:$num) {
      projectItems(first:10) {
        nodes { id project { id } }
      }
    }
  }
}
""".strip()


def cmd_item_id(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write("usage: naavik-ops gh item-id <issue-num>\n")
        return 2
    cache = _load_cache()
    issue_num = int(rest[0])
    data = gh_graphql(
        _QUERY_ITEM_ID,
        variables={"owner": cache["owner"], "repo": cache["repo"], "num": issue_num},
    )
    nodes = (data.get("data") or {}).get("repository", {}).get("issue", {}).get(
        "projectItems", {}
    ).get("nodes") or []
    for n in nodes:
        if (n.get("project") or {}).get("id") == cache["project_id"]:
            sys.stdout.write(f"{n['id']}\n")
            return 0
    raise NaavikOpsError(f"Issue #{issue_num} not in Project {cache.get('project_number')}")


def capture_item_id(issue_num: int | str) -> str:
    """Programmatic helper. Returns Project item id as string."""
    cache = _load_cache()
    data = gh_graphql(
        _QUERY_ITEM_ID,
        variables={"owner": cache["owner"], "repo": cache["repo"], "num": int(issue_num)},
    )
    nodes = (data.get("data") or {}).get("repository", {}).get("issue", {}).get(
        "projectItems", {}
    ).get("nodes") or []
    for n in nodes:
        if (n.get("project") or {}).get("id") == cache["project_id"]:
            return n.get("id") or ""
    raise NaavikOpsError(f"Issue #{issue_num} not in Project {cache.get('project_number')}")


# ---------------------------------------------------------------------------
# create-issue / create-epic
# ---------------------------------------------------------------------------


def cmd_create_issue(rest: Sequence[str]) -> int:
    """create-issue <id> <title> [--priority] [--effort] [--milestone] [--parent] [--body]"""
    if len(rest) < 2:
        sys.stderr.write(
            "usage: naavik-ops gh create-issue <id> <title> "
            '[--priority P] [--effort E] [--milestone M] [--parent NUM] [--body "..."]\n'
        )
        return 2
    task_id, title = rest[0], rest[1]
    args = list(rest[2:])

    pri, effort, milestone, parent, body = "MEDIUM", "M", "", "", ""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--priority":
            pri = args[i + 1].upper()
            i += 2
        elif a == "--effort":
            effort = args[i + 1].upper()
            i += 2
        elif a == "--milestone":
            milestone = args[i + 1]
            i += 2
        elif a == "--parent":
            parent = args[i + 1]
            i += 2
        elif a == "--body":
            body = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]

    prefix = f"[{task_id}]"
    existing = _find_issue_by_prefix(prefix, "issues", task_id)
    if existing:
        sys.stdout.write(f"exists: https://github.com/{owner}/{repo}/issues/{existing}\n")
        return 0

    if not body:
        body = (
            f"Created via `naavik-ops gh create-issue` (likely from `/plan`).\n\n"
            f"ROADMAP row: `{task_id}` — update `ROADMAP.md` § the relevant phase before "
            f"flipping status.\n\n"
            f"---\n"
            f"*Auto-managed by `.claude/naavik-ops gh`. `ROADMAP.md` is authoritative.*"
        )

    _ensure_label(f"priority:{pri.lower()}", "ededed", f"Priority {pri.upper()}")

    create_args = [
        "issue",
        "create",
        "--repo",
        f"{owner}/{repo}",
        "--title",
        f"[{task_id}] {title}",
        "--body",
        body,
        "--label",
        f"priority:{pri.lower()}",
    ]
    if milestone:
        _ensure_milestone(milestone)
        create_args.extend(["--milestone", milestone])

    url = _gh(*create_args).strip()
    num = int(url.rsplit("/", 1)[-1])

    node_id = _issue_node_id(owner, repo, num)
    item_id = _add_issue_to_project(cache["project_id"], node_id)

    # Set Status / Priority / Effort.
    _set_select(
        cache["project_id"], item_id, cache["status_field_id"], cache["status_options"]["todo"]
    )
    pri_id = _priority_option_id(cache, pri)
    if cache.get("priority_field_id"):
        _set_select(cache["project_id"], item_id, cache["priority_field_id"], pri_id)
    eff_id = _effort_option_id(cache, effort)
    if cache.get("effort_field_id"):
        _set_select(cache["project_id"], item_id, cache["effort_field_id"], eff_id)

    if parent:
        parent_id = _issue_node_id(owner, repo, int(parent))
        if parent_id:
            _add_subissue_by_id(parent_id, node_id)

    _map_set("issues", task_id, num)
    sys.stdout.write(url + "\n")
    return 0


def cmd_create_epic(rest: Sequence[str]) -> int:
    """create-epic <phase> [--priority P] [--effort E] [--body \"...\"]"""
    if not rest:
        sys.stderr.write(
            "usage: naavik-ops gh create-epic <phase-name> "
            '[--priority P] [--effort E] [--body "..."]\n'
        )
        return 2
    phase = rest[0]
    args = list(rest[1:])
    pri, effort, body = "HIGH", "L", ""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--priority":
            pri = args[i + 1].upper()
            i += 2
        elif a == "--effort":
            effort = args[i + 1].upper()
            i += 2
        elif a == "--body":
            body = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]

    existing = _find_issue_by_prefix(f"[Epic] {phase}", "epics", phase)
    if existing:
        sys.stdout.write(f"exists: https://github.com/{owner}/{repo}/issues/{existing}\n")
        return 0

    _ensure_milestone(phase)

    phase_label = _phase_to_label(phase)
    category_label = _phase_to_category_labels(phase)

    if not body:
        body = (
            f"**{phase} epic**\n\n"
            f"Sub-issues track the per-row tasks from `ROADMAP.md` § {phase}.\n\n"
            "Manager owns this epic's % complete via Sub-issues progress. Closing this epic "
            "happens after every sub-issue is closed AND the corresponding ROADMAP rows are "
            "marked `[x]`.\n\n"
            "---\n"
            "*Auto-managed by `.claude/naavik-ops gh`. `ROADMAP.md` is authoritative.*"
        )

    create_args = [
        "issue",
        "create",
        "--repo",
        f"{owner}/{repo}",
        "--title",
        f"[Epic] {phase}",
        "--body",
        body,
        "--milestone",
        phase,
        "--label",
        "epic",
        "--label",
        f"priority:{pri.lower()}",
    ]
    if phase_label:
        create_args.extend(["--label", phase_label])
    if category_label:
        create_args.extend(["--label", category_label])

    url = _gh(*create_args).strip()
    num = int(url.rsplit("/", 1)[-1])

    node_id = _issue_node_id(owner, repo, num)
    item_id = _add_issue_to_project(cache["project_id"], node_id)

    inprog_id = _status_option_id(cache, "In Progress")
    _set_select(cache["project_id"], item_id, cache["status_field_id"], inprog_id)
    pri_id = _priority_option_id(cache, pri)
    if cache.get("priority_field_id"):
        _set_select(cache["project_id"], item_id, cache["priority_field_id"], pri_id)
    eff_id = _effort_option_id(cache, effort)
    if cache.get("effort_field_id"):
        _set_select(cache["project_id"], item_id, cache["effort_field_id"], eff_id)

    _map_set("epics", phase, num)
    sys.stdout.write(url + "\n")
    return 0


# ---------------------------------------------------------------------------
# add-status (Status single-select option add — idempotent)
# ---------------------------------------------------------------------------


_QUERY_STATUS_FIELD = """
query($p:ID!) {
  node(id:$p) {
    ... on ProjectV2 {
      field(name:"Status") {
        ... on ProjectV2SingleSelectField {
          id options { id name color description }
        }
      }
    }
  }
}
""".strip()

_QUERY_UPDATE_FIELD_OPTIONS = """
mutation($f:ID!, $opts:[ProjectV2SingleSelectFieldOptionInput!]!) {
  updateProjectV2Field(input:{
    fieldId:$f,
    singleSelectOptions:$opts
  }) { projectV2Field { ... on ProjectV2SingleSelectField { id options { id name } } } }
}
""".strip()


def cmd_add_status(rest: Sequence[str]) -> int:
    if not rest:
        sys.stderr.write(
            "usage: naavik-ops gh add-status <option-name> [--color GRAY|RED|...] "
            '[--description "..."]\n'
        )
        return 2
    name = rest[0]
    args = list(rest[1:])
    color = "GRAY"
    description = "Deferred — not in current cycle"
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--color":
            color = args[i + 1].upper()
            i += 2
        elif a == "--description":
            description = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{a}'")

    valid_colors = {"GRAY", "RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE", "PINK"}
    if color not in valid_colors:
        raise NaavikOpsError(f"unknown color '{color}' (expected: {sorted(valid_colors)})")

    cache = _load_cache()
    project_id = cache["project_id"]
    status_field_id = cache["status_field_id"]

    status_data = gh_graphql(_QUERY_STATUS_FIELD, variables={"p": project_id})
    current_opts = (((status_data.get("data") or {}).get("node") or {}).get("field") or {}).get(
        "options"
    ) or []

    existing = next((o for o in current_opts if o.get("name") == name), None)
    if existing:
        sys.stdout.write(f"status option '{name}' already exists (id={existing['id']})\n")
    else:
        new_opts = [
            {
                "name": o["name"],
                "color": o.get("color") or "GRAY",
                "description": o.get("description") or "",
            }
            for o in current_opts
        ] + [{"name": name, "color": color, "description": description}]

        # gh CLI -F flag can't pass complex arrays; pipe via stdin.
        body = {
            "query": _QUERY_UPDATE_FIELD_OPTIONS,
            "variables": {"f": status_field_id, "opts": new_opts},
        }
        _gh("api", "graphql", "--input", "-", input_str=json.dumps(body))
        sys.stdout.write(f"added status option: {name} (color={color})\n")

    # Refresh cache option ids.
    status_data = gh_graphql(_QUERY_STATUS_FIELD, variables={"p": project_id})
    refreshed = (((status_data.get("data") or {}).get("node") or {}).get("field") or {}).get(
        "options"
    ) or []

    def _find_opt(*names: str) -> str:
        for o in refreshed:
            if o.get("name") in names:
                return o.get("id") or ""
        return ""

    cache["status_options"] = {
        "todo": _find_opt("Todo", "To do"),
        "in_progress": _find_opt("In Progress", "In progress"),
        "done": _find_opt("Done"),
        "backlog": _find_opt("Backlog"),
    }
    _save_cache(cache)
    sys.stdout.write(f"cache refreshed at {CACHE_PATH}\n")
    return 0


# ---------------------------------------------------------------------------
# milestone-status / next-unblocked / backlog-by-epic
# ---------------------------------------------------------------------------


_QUERY_ALL_ITEMS = """
query($owner:String!, $number:Int!) {
  %s(login:$owner) {
    projectV2(number:$number) {
      items(first:100) {
        nodes {
          id
          content {
            __typename
            ... on Issue {
              number title state url milestone { title }
              labels(first:10) { nodes { name } }
              parent { ... on Issue { number title } }
            }
            ... on PullRequest { number title state url milestone { title } }
          }
          fieldValues(first:20) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


def _scope_path(cache: dict[str, Any]) -> str:
    return "organization" if cache.get("scope") == "organization" else "user"


def _items_payload(cache: dict[str, Any]) -> list[dict[str, Any]]:
    scope = _scope_path(cache)
    data = gh_graphql(
        _QUERY_ALL_ITEMS % scope,
        variables={"owner": cache["owner"], "number": cache["project_number"]},
    )
    nodes = ((data.get("data") or {}).get(scope) or {}).get("projectV2", {}).get("items", {}).get(
        "nodes"
    ) or []
    return nodes


def _field_value(item: dict[str, Any], field_name: str) -> str | None:
    fv_nodes = (item.get("fieldValues") or {}).get("nodes") or []
    for fv in fv_nodes:
        field = (fv.get("field") or {}).get("name")
        if field == field_name:
            return fv.get("name")
    return None


def cmd_milestone_status(rest: Sequence[str]) -> int:
    cache = _load_cache()
    items = _items_payload(cache)

    milestone_name = rest[0] if rest else ""

    filtered = []
    for it in items:
        content = it.get("content") or {}
        if milestone_name:
            ms = (content.get("milestone") or {}).get("title")
            if ms != milestone_name:
                continue
        status = _field_value(it, "Status") or "Unset"
        filtered.append(
            {
                "status": status,
                "number": content.get("number"),
                "title": content.get("title"),
                "url": content.get("url"),
                "milestone": (content.get("milestone") or {}).get("title"),
            }
        )

    groups: dict[str, dict[str, Any]] = {}
    for f in filtered:
        s = f["status"]
        g = groups.setdefault(s, {"status": s, "count": 0, "items": []})
        g["count"] += 1
        if milestone_name:
            g["items"].append({"number": f["number"], "title": f["title"], "url": f["url"]})
        else:
            g["items"].append(
                {
                    "number": f["number"],
                    "title": f["title"],
                    "url": f["url"],
                    "milestone": f["milestone"],
                }
            )

    out = list(groups.values())
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


def cmd_next_unblocked(rest: Sequence[str]) -> int:
    """Highest-priority unblocked Todo item across the Project.

    Filters: state OPEN, status Todo, no `blocked` label, no `epic` label.
    Sort: Priority DESC (CRITICAL > HIGH > MEDIUM > LOW > unset).
    """
    _ = rest
    cache = _load_cache()
    items = _items_payload(cache)

    def labels(it: dict[str, Any]) -> list[str]:
        content = it.get("content") or {}
        lbls = (content.get("labels") or {}).get("nodes") or []
        return [(lbl.get("name") or "") for lbl in lbls]

    open_todos: list[dict[str, Any]] = []
    for it in items:
        content = it.get("content") or {}
        state = content.get("state") or "OPEN"
        if state != "OPEN":
            continue
        status = _field_value(it, "Status") or "Todo"
        if status != "Todo":
            continue
        lbl_set = labels(it)
        if "blocked" in lbl_set or "epic" in lbl_set:
            continue
        priority = _field_value(it, "Priority") or "MEDIUM"
        open_todos.append(
            {
                "number": content.get("number"),
                "title": content.get("title"),
                "url": content.get("url"),
                "priority": priority,
                "labels": lbl_set,
            }
        )

    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    open_todos.sort(key=lambda x: rank.get(x.get("priority") or "MEDIUM", 99))

    payload = open_todos[0] if open_todos else None
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def cmd_backlog_by_epic(rest: Sequence[str]) -> int:
    """Backlog items grouped by parent epic, epics ordered by Priority."""
    args = list(rest)
    top = 5
    i = 0
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top = int(args[i + 1])
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{args[i]}'")

    cache = _load_cache()
    items = _items_payload(cache)

    def labels(it: dict[str, Any]) -> list[str]:
        content = it.get("content") or {}
        lbls = (content.get("labels") or {}).get("nodes") or []
        return [(lbl.get("name") or "") for lbl in lbls]

    # Build epic_num → {priority, title} index.
    epic_index: dict[str, dict[str, Any]] = {}
    for it in items:
        content = it.get("content") or {}
        if (content.get("__typename") or "") != "Issue":
            continue
        if "epic" not in labels(it):
            continue
        pri = _field_value(it, "Priority")
        num = content.get("number")
        if num is not None:
            epic_index[str(num)] = {"priority": pri, "title": content.get("title")}

    backlog_items: list[dict[str, Any]] = []
    for it in items:
        content = it.get("content") or {}
        if (content.get("__typename") or "") != "Issue":
            continue
        state = content.get("state") or "OPEN"
        if state != "OPEN":
            continue
        status = _field_value(it, "Status") or "Todo"
        if status != "Backlog":
            continue
        if "epic" in labels(it):
            continue
        parent = content.get("parent") or {}
        backlog_items.append(
            {
                "issue": content.get("number"),
                "title": content.get("title"),
                "url": content.get("url"),
                "parent_issue": parent.get("number"),
                "parent_title": parent.get("title") or "_unparented",
            }
        )

    # Group by parent_issue.
    groups: dict[str | None, list[dict[str, Any]]] = {}
    for b in backlog_items:
        groups.setdefault(b["parent_issue"], []).append(b)

    rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    result: list[dict[str, Any]] = []
    for parent_num, items_list in groups.items():
        title = items_list[0]["parent_title"]
        if parent_num is None:
            epic_pri = None
        else:
            epic_pri = (epic_index.get(str(parent_num)) or {}).get("priority")
        items_list.sort(key=lambda x: x["issue"])
        result.append(
            {
                "epic_issue": parent_num,
                "epic_title": title,
                "epic_priority": epic_pri,
                "items": [
                    {"issue": x["issue"], "title": x["title"], "url": x["url"]}
                    for x in items_list[:top]
                ],
                "total_items": len(items_list),
            }
        )

    result.sort(key=lambda g: (-(rank.get(g.get("epic_priority") or "", 0)), g["epic_title"]))
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


def capture_next_unblocked() -> str:
    """Programmatic helper. Returns the JSON of the next unblocked item."""
    cache = _load_cache()
    items = _items_payload(cache)

    def labels(it: dict[str, Any]) -> list[str]:
        content = it.get("content") or {}
        lbls = (content.get("labels") or {}).get("nodes") or []
        return [(lbl.get("name") or "") for lbl in lbls]

    todos = []
    for it in items:
        content = it.get("content") or {}
        if content.get("state") != "OPEN":
            continue
        if (_field_value(it, "Status") or "Todo") != "Todo":
            continue
        lbl_set = labels(it)
        if "blocked" in lbl_set or "epic" in lbl_set:
            continue
        priority = _field_value(it, "Priority") or "MEDIUM"
        todos.append(
            {
                "number": content.get("number"),
                "title": content.get("title"),
                "url": content.get("url"),
                "priority": priority,
                "labels": lbl_set,
            }
        )
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    todos.sort(key=lambda x: rank.get(x.get("priority") or "MEDIUM", 99))
    return json.dumps(todos[0] if todos else None, indent=2)


# ---------------------------------------------------------------------------
# bootstrap — ROADMAP → Project mirror, idempotent
# ---------------------------------------------------------------------------


def cmd_bootstrap(rest: Sequence[str]) -> int:
    """bootstrap [--apply] [--phase=NAME]*"""
    cache = _load_cache()
    apply = False
    phases: list[str] = []
    for arg in rest:
        if arg == "--apply":
            apply = True
        elif arg.startswith("--phase="):
            phases.append(arg.split("=", 1)[1])
        else:
            raise NaavikOpsError(f"unknown arg '{arg}' (expected --apply or --phase=NAME)")

    if not phases:
        phases = ["Pre-Phase-2 paper cuts", "Phase A", "Phase 2", "Phase 1 deferred items"]

    sys.stdout.write(f"→ bootstrap (apply={apply}) phases: {' '.join(phases)}\n\n")

    created = 0
    skipped = 0

    for phase in phases:
        sys.stdout.write(f"=== {phase} ===\n")

        # 1. Milestone.
        existing_ms = _lookup_milestone(phase)
        if existing_ms is not None:
            sys.stdout.write(f"  milestone exists → #{existing_ms}\n")
        elif apply:
            num = _ensure_milestone(phase)
            sys.stdout.write(f"  milestone created → #{num}\n")
        else:
            sys.stdout.write(f'  milestone PLAN   would create "{phase}"\n')

        # 2. Epic.
        epic_num = None
        existing_epic = _find_issue_by_prefix(f"[Epic] {phase}", "epics", phase)
        if existing_epic:
            epic_num = existing_epic
            sys.stdout.write(f"  epic exists → #{epic_num}\n")
        elif apply:
            # Re-use cmd_create_epic (writes to stdout via its own URL print).
            # Capture by reading map after the call.
            cmd_create_epic([phase])
            epic_num = _map_lookup("epics", phase)
            sys.stdout.write(f"  epic created → #{epic_num}\n")
        else:
            sys.stdout.write(f"  epic PLAN   would create [Epic] {phase}\n")

        # 3. Iterate over the phase's tasks via lib/roadmap.
        for row in roadmap.parse([phase], open_only=True):
            task_id = row["id"]
            title = row["title"]
            status = row["status"]
            priority = row["priority"]
            notes = row["notes"]

            prefix = f"[{task_id}]"
            existing = _find_issue_by_prefix(prefix, "issues", task_id)
            if existing:
                sys.stdout.write(f"  SKIP   {prefix} exists → #{existing}\n")
                skipped += 1
                continue

            if not apply:
                sys.stdout.write(
                    f"  PLAN   {prefix} {title}  (priority={priority} status={status})\n"
                )
                created += 1
                continue

            default_effort = _phase_to_default_effort(phase)
            create_args = [
                task_id,
                title,
                "--priority",
                priority,
                "--effort",
                default_effort,
                "--milestone",
                phase,
            ]
            if epic_num:
                create_args.extend(["--parent", str(epic_num)])
            body = (
                f"Bootstrapped from `ROADMAP.md` § {phase} row {task_id}.\n\n"
                f"{notes}\n\n"
                f"---\n"
                f"*Auto-managed by `.claude/naavik-ops gh`. `ROADMAP.md` is authoritative. "
                f"Do not edit Status here directly; mark the ROADMAP row first, then "
                f"run `naavik-ops gh sync --apply`.*"
            )
            create_args.extend(["--body", body])
            cmd_create_issue(create_args)

            new_num = _map_lookup("issues", task_id)
            sys.stdout.write(f"  CREATE {prefix} → #{new_num}  ({priority}, parent #{epic_num})\n")

            # Status override for non-default-Todo rows (legacy parity).
            if status != " " and new_num is not None:
                item_id = capture_item_id(new_num)
                cache_now = _load_cache()
                if status == "~":
                    _set_select(
                        cache_now["project_id"],
                        item_id,
                        cache_now["status_field_id"],
                        cache_now["status_options"]["in_progress"],
                    )
                elif status == "x":
                    _set_select(
                        cache_now["project_id"],
                        item_id,
                        cache_now["status_field_id"],
                        cache_now["status_options"]["done"],
                    )
            created += 1
        sys.stdout.write("\n")
    _ = cache  # unused after iteration; kept for future field-id lookups

    if apply:
        sys.stdout.write(f"→ done. created={created} skipped={skipped}\n")
    else:
        sys.stdout.write(
            f"→ dry-run. would create={created} skipped={skipped}. re-run with --apply.\n"
        )
    return 0


# ---------------------------------------------------------------------------
# sync — diff ROADMAP vs Project; --apply pushes ROADMAP → Project
# ---------------------------------------------------------------------------


def cmd_sync(rest: Sequence[str]) -> int:
    apply = False
    for arg in rest:
        if arg == "--apply":
            apply = True
        else:
            raise NaavikOpsError(f"unknown arg '{arg}' (expected --apply)")

    cache = _load_cache()
    items = _items_payload(cache)
    sys.stdout.write(f"→ sync (apply={apply})\n")

    # Build map: task_id → project_item.
    item_by_task: dict[str, dict[str, Any]] = {}
    for it in items:
        title = (it.get("content") or {}).get("title") or ""
        m = re.match(r"^\[([^\]]+)\]\s+", title)
        if m:
            item_by_task[m.group(1)] = it

    diffs = 0
    applied = 0
    for row in roadmap.parse():
        task_id = row["id"]
        roadmap_status = row["status"]
        roadmap_priority = row["priority"]
        it = item_by_task.get(task_id)
        if it is None:
            continue

        item_id = it.get("id") or ""
        proj_status = _field_value(it, "Status") or "Todo"
        proj_priority = _field_value(it, "Priority") or "MEDIUM"

        expected_status = {" ": "Todo", "~": "In Progress", "x": "Done"}.get(roadmap_status)
        if expected_status is None:
            continue

        # Backlog → Todo is not a drift; preserve deferral.
        if proj_status == "Backlog" and expected_status == "Todo":
            pass
        elif proj_status != expected_status:
            diffs += 1
            sys.stdout.write(
                f"  [{task_id}] STATUS drift: project={proj_status} roadmap={expected_status}\n"
            )
            if apply:
                cmd_set_status([item_id, expected_status])
                applied += 1
        if proj_priority != roadmap_priority:
            diffs += 1
            sys.stdout.write(
                f"  [{task_id}] PRIORITY drift: project={proj_priority} roadmap={roadmap_priority}\n"
            )
            if apply:
                cmd_set_priority([item_id, roadmap_priority])
                applied += 1

    if apply:
        sys.stdout.write(f"→ sync done. drifts={diffs} applied={applied}\n")
    else:
        sys.stdout.write(f"→ sync dry-run. drifts={diffs}. re-run with --apply.\n")
    return 0


# ---------------------------------------------------------------------------
# runs / refresh-map
# ---------------------------------------------------------------------------


def cmd_runs(rest: Sequence[str]) -> int:
    count = int(rest[0]) if rest else 10
    if not RUNS_LOG_PATH.is_file():
        sys.stdout.write("no runs yet (traces/runs.log does not exist)\n")
        return 0
    lines = RUNS_LOG_PATH.read_text(encoding="utf-8").splitlines()
    for line in lines[-count:]:
        sys.stdout.write(line + "\n")
    return 0


def cmd_refresh_map(rest: Sequence[str]) -> int:
    """Rebuild map from authoritative GitHub state. On collisions, prefer open + lowest #."""
    _ = rest
    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]
    sys.stdout.write(f"→ refreshing {ISSUE_MAP_PATH} from authoritative GitHub state...\n")

    milestones = _gh_api_paginate(f"repos/{owner}/{repo}/milestones?state=all&per_page=100")
    ms_map: dict[str, int] = {}
    for ms in milestones or []:
        if isinstance(ms, dict):
            ms_map[ms.get("title") or ""] = int(ms.get("number") or 0)

    raw_issues = _gh_api_paginate(f"repos/{owner}/{repo}/issues?state=all&per_page=100")
    issues_filtered = [
        i for i in (raw_issues or []) if isinstance(i, dict) and i.get("pull_request") is None
    ]

    # Known phases (same defaults as cmd_bootstrap + the release-version epics).
    known_phases = [
        "Pre-Phase-2 paper cuts",
        "Phase A",
        "Phase 2",
        "Phase 2.5",
        "Phase 1 deferred items",
    ]

    def sort_open_lowest(items: list[dict]) -> dict | None:
        if not items:
            return None
        return sorted(
            items, key=lambda x: (0 if (x.get("state") == "open") else 1, int(x.get("number") or 0))
        )[0]

    epics_map: dict[str, int] = {}
    for phase in known_phases:
        matches = [
            i for i in issues_filtered if (i.get("title") or "").startswith(f"[Epic] {phase}")
        ]
        winner = sort_open_lowest(matches)
        if winner:
            epics_map[phase] = int(winner["number"])

    # Ad-hoc / release-version epics (titles starting with `[Epic] ` not covered above).
    for i in issues_filtered:
        title = i.get("title") or ""
        if not title.startswith("[Epic] "):
            continue
        suffix = title[len("[Epic] ") :].strip()
        if any(suffix.startswith(p) for p in known_phases):
            continue
        if suffix in epics_map:
            continue
        epics_map[suffix] = int(i.get("number") or 0)

    # Children — title matches `[<key>]` and not `[Epic] ...`.
    children_by_key: dict[str, list[dict]] = {}
    bracket_re = re.compile(r"^\[([^\]]+)\]\s+")
    for i in issues_filtered:
        title = i.get("title") or ""
        if title.startswith("[Epic] "):
            continue
        m = bracket_re.match(title)
        if not m:
            continue
        children_by_key.setdefault(m.group(1), []).append(i)

    children_map: dict[str, int] = {}
    for key, candidates in children_by_key.items():
        winner = sort_open_lowest(candidates)
        if winner:
            children_map[key] = int(winner["number"])

    new_map = {
        "_meta": {
            "owner": owner,
            "repo": repo,
            "project_number": cache.get("project_number"),
            "refreshed_at": _now_iso(),
            "note": (
                "Persistent cache of GitHub issue/milestone/epic associations. "
                "Sole writer: .claude/naavik-ops gh (native Python). "
                "Run `naavik-ops gh refresh-map` to rebuild from authoritative GitHub state."
            ),
        },
        "milestones": ms_map,
        "epics": epics_map,
        "issues": children_map,
    }

    # Preserve priorities / deps / statuses / redirects sub-dicts if the
    # existing map has them — refresh-map shouldn't drop unrelated subtrees.
    if ISSUE_MAP_PATH.is_file():
        old = jsonl.read_json(ISSUE_MAP_PATH)
        for k in ("priorities", "deps", "statuses", "redirects"):
            if k in old:
                new_map[k] = old[k]

    _map_save(new_map)
    sys.stdout.write(f"→ wrote {ISSUE_MAP_PATH}\n")
    sys.stdout.write(
        json.dumps(
            {
                "_meta": new_map["_meta"],
                "counts": {
                    "milestones": len(new_map["milestones"]),
                    "epics": len(new_map["epics"]),
                    "issues": len(new_map["issues"]),
                },
            },
            indent=2,
        )
        + "\n"
    )
    return 0


# ---------------------------------------------------------------------------
# update-issue-title — NEW per D.7 (D.6 dep)
# ---------------------------------------------------------------------------


def cmd_update_issue_title(rest: Sequence[str]) -> int:
    """update-issue-title <issue-num> <new-title>

    Atomically: gh issue edit <N> --title "<new>", then write to map cache.
    The mutating task subcommands (insert / defer / move / renumber) need to
    rewrite issue titles when positions shift; this is the helper they call.
    """
    if len(rest) < 2:
        sys.stderr.write("usage: naavik-ops gh update-issue-title <issue-num> <new-title>\n")
        return 2
    issue_num = int(rest[0])
    new_title = rest[1]

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]

    _gh("issue", "edit", str(issue_num), "--repo", f"{owner}/{repo}", "--title", new_title)

    # Re-key the map's `issues` sub-dict if the new title prefix differs from the
    # old one. We don't know the OLD task-id without consulting the map.
    m = re.match(r"^\[([^\]]+)\]\s+", new_title)
    if m:
        new_key = m.group(1)
        data = _map_init()
        issues = data.setdefault("issues", {})
        # Find any existing key currently pointing at this issue_num.
        old_keys = [k for k, v in issues.items() if v == issue_num]
        for k in old_keys:
            if k != new_key:
                issues.pop(k, None)
        issues[new_key] = issue_num
        _map_save(data)

    sys.stdout.write(f"updated: #{issue_num} → {new_title}\n")
    return 0


def update_issue_title(issue_num: int, new_title: str) -> None:
    """Programmatic helper for the mutating task subcommands."""
    cmd_update_issue_title([str(issue_num), new_title])


# ---------------------------------------------------------------------------
# close-issue — NEW per D.7 (gap from PR #75; #76 cleanup)
# ---------------------------------------------------------------------------


def cmd_close_issue(rest: Sequence[str]) -> int:
    """close-issue <issue-num> [--reason completed|not_planned]

    Closes an issue + updates the map cache (removes the key for that
    issue-number; the issue stays closed on GitHub). The map cache only
    stores open or recently-closed issue numbers; closed ones can stay in
    the map for a few cycles (refresh-map's "open + lowest #" preference
    handles eventual cleanup).
    """
    if not rest:
        sys.stderr.write(
            "usage: naavik-ops gh close-issue <issue-num> [--reason completed|not_planned]\n"
        )
        return 2

    # argv parse safety: issue-num must parse to int.
    try:
        issue_num = int(rest[0])
    except ValueError as e:
        raise NaavikOpsError(
            f"close-issue: <issue-num> must be an integer (got '{rest[0]}')"
        ) from e

    reason = "completed"
    args = list(rest[1:])
    i = 0
    while i < len(args):
        if args[i] == "--reason" and i + 1 < len(args):
            reason = args[i + 1]
            i += 2
        else:
            raise NaavikOpsError(f"unknown arg '{args[i]}'")
    if reason not in ("completed", "not_planned"):
        raise NaavikOpsError(f"reason must be 'completed' or 'not_planned' (got '{reason}')")

    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]

    close_args = ["issue", "close", str(issue_num), "--repo", f"{owner}/{repo}"]
    if reason == "not_planned":
        close_args.extend(["--reason", "not planned"])
    _gh(*close_args)

    sys.stdout.write(f"closed: #{issue_num} (reason={reason})\n")
    return 0


def close_issue(issue_num: int, reason: str = "completed") -> None:
    """Programmatic helper for the W6 release-ceremony post-merge ops."""
    cmd_close_issue([str(issue_num), "--reason", reason])


# ---------------------------------------------------------------------------
# get-issue — NEW helper for parity tests / programmatic reads
# ---------------------------------------------------------------------------


def get_issue(issue_num: int) -> dict[str, Any]:
    """Read-only: return the GitHub issue JSON via REST."""
    cache = _load_cache()
    owner, repo = cache["owner"], cache["repo"]
    return _gh_api(f"repos/{owner}/{repo}/issues/{issue_num}")


# ---------------------------------------------------------------------------
# Direct invocation (debug aid)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(0)
