"""Shared foundations for the generation package (plan 91 Phase 4.3).

`svc()` resolves the `services.generation` package surface at call time so
internal calls to patched seams (get_provider, typst_compile, llm_tracker,
is_cost_capped, _today_spend, _app_documents_dir, load_profile_snapshot,
_latest_error_free_doc) keep honoring `patch("services.generation.X")`
and `monkeypatch.setattr(dg, ...)` exactly as they did pre-split.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import settings as app_settings


def svc():
    """The `services.generation` package surface, resolved at call time —
    keeps `patch("services.generation.X")` seams intercepting internal
    calls (plan 91 Phase 4.3 / plan 92 teardown)."""
    from services import generation

    return generation


# Documents directory — relative to DATA_DIR; per-app subdir.
def _documents_dir() -> Path:
    raw = app_settings.data_dir
    base = Path(raw).expanduser() if raw.startswith("~") else Path(raw)
    if not base.is_absolute():
        base = base.resolve()
    return base / "data" / "documents"


def _app_documents_dir(application_id: int) -> Path:
    d = _documents_dir() / str(application_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Template selection (shared by resume / snapshot / maintenance) ──────

from models import Application, Settings  # noqa: E402
from models.enums import ApplicationBoard  # noqa: E402
from typst.compiler import template_path  # noqa: E402

# Plan 66 (0.3.1) § T6 — auto-select the ATS-friendly template variant for
# ATS-known boards; manual + company-direct stays on creative onepage.typ.
_ATS_BOARDS: frozenset[ApplicationBoard] = frozenset(
    {
        ApplicationBoard.WORKDAY,
        ApplicationBoard.GREENHOUSE,
        ApplicationBoard.LEVER,
        ApplicationBoard.ASHBY,
        ApplicationBoard.LINKEDIN,
    }
)


def _template_version(template_name: str) -> str:
    """Content hash of the packaged template source.

    Stamped into `bullet_selection` at generation time and required to match
    in `can_reuse_existing_resume`, so shipping a template change invalidates
    previously generated documents instead of reusing stale layouts.
    """
    cached = _template_version_cache.get(template_name)
    if cached is None:
        cached = hashlib.sha256(template_path(template_name).read_bytes()).hexdigest()[:12]
        _template_version_cache[template_name] = cached
    return cached


_template_version_cache: dict[str, str] = {}


def _select_template(application: Application, settings: Settings | None) -> tuple[str, str | None]:
    """One template (`onepage.typ`) for every board — it is both the dense
    recruiter-standard layout AND ATS-safe (single column, ligatures off,
    plain bullets). Returns ``(template_name, pdf_standard)``; ATS-known
    boards keep PDF/A-1b output for maximum parser compatibility.
    """
    del settings  # `resume_template_preference` is vestigial post-consolidation
    board = getattr(application, "board", None)
    if board is not None and board in _ATS_BOARDS:
        return "onepage", "a-1b"
    return "onepage", None
