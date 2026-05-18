"""github_api — GraphQL helper wrapping `gh api graphql`.

Implements full hasNextPage pagination — fixes the 200-item cap in
`scripts/gh-project.sh` (Risk (e) in plan § Risk). A.30 (0.1.1) switches to
direct httpx GraphQL calls; A.29 wraps the `gh` CLI subprocess.

The Project items endpoint caps at first:100 per page; this helper concatenates
pages until hasNextPage is False. Safe for projects with hundreds of items.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from naavik_ops.lib import NaavikOpsError


def gh_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a one-shot GraphQL query via `gh api graphql`. Returns parsed JSON.

    Pass variables via `-F key=value` (gh CLI semantics: scalars only). For
    complex object/array variables, stream JSON to stdin.
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for key, value in variables.items():
            cmd.extend(["-F", f"{key}={value}"])
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise NaavikOpsError(
            f"gh api graphql failed (exit {e.returncode}): {e.stderr.strip()}"
        ) from e
    return json.loads(result.stdout)


def paginate(
    query: str,
    variables: dict[str, Any] | None,
    *,
    page_path: list[str],
) -> list[Any]:
    """Run a paginated query. Returns concatenated `nodes` across all pages.

    `query` MUST accept a `$cursor:String` variable and a `pageInfo`
    `{endCursor, hasNextPage}` selection alongside the `nodes` selection.

    `page_path` is the dotted JSON path from `.data` to the connection node
    that holds `nodes` + `pageInfo`. e.g. for projectV2.items, pass
    `["user", "projectV2", "items"]` or `["organization", "projectV2", "items"]`.

    Returns the concatenation of `.nodes` arrays across pages.
    """
    items: list[Any] = []
    cursor: str | None = None
    page_count = 0
    max_pages = 100  # 100 pages × ~100 items/page = 10k — sane upper bound

    while page_count < max_pages:
        page_vars = dict(variables or {})
        if cursor is not None:
            page_vars["cursor"] = cursor
        # gh CLI's -F passes empty string for None — pass empty for first page.
        page_vars.setdefault("cursor", "")

        data = gh_graphql(query, page_vars)
        node: Any = data.get("data", {})
        for key in page_path:
            if not isinstance(node, dict) or node is None:
                raise NaavikOpsError(f"paginate: page_path {page_path} did not resolve in response")
            node = node.get(key)
            if node is None:
                raise NaavikOpsError(f"paginate: page_path key '{key}' missing in response")

        nodes = node.get("nodes") or []
        items.extend(nodes)

        page_info = node.get("pageInfo") or {}
        has_next = bool(page_info.get("hasNextPage"))
        cursor = page_info.get("endCursor")
        if not has_next or not cursor:
            break
        page_count += 1
    else:
        raise NaavikOpsError(f"paginate: exceeded {max_pages} pages (suspected infinite loop)")

    return items
