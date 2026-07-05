"""Jobs package — job CRUD/queries, scrape-run bookkeeping, JD enrichment,
raw-listing extraction, and dedup.

Plan 92 Phase B2 grouped the former flat modules `job_service` /
`jd_enrichment` / `job_extractor` / `dedup` into this package.

Seam tiers:

- Package surface (this `__init__`): the job service API — the conftest
  shims land here and callers read `job_service.get_job(...)` through a
  `from services import jobs as job_service` alias, so
  `patch("services.jobs.X")` intercepts.
- Module tier: `jd_enrichment`, `extractor`, `dedup` — import the
  submodule; patch as `services.jobs.<mod>.X`.
"""

from __future__ import annotations

from services.jobs.service import (
    archive_job,
    auto_apply_queue,
    count_jobs_by_source,
    count_jobs_in_queue_state,
    create_manual_job,
    get_job,
    get_scrape_run,
    list_external_ids,
    list_jobs,
    list_jobs_by_queue_state,
    list_new_jobs_from_run,
    list_recent_scrape_runs,
    list_recent_scrape_runs_by_source,
    record_scrape_run,
    restore_job,
    set_queue_state,
    sum_listings_scanned_since,
    upsert_job,
)

__all__ = [
    "archive_job",
    "auto_apply_queue",
    "count_jobs_by_source",
    "count_jobs_in_queue_state",
    "create_manual_job",
    "get_job",
    "get_scrape_run",
    "list_external_ids",
    "list_jobs",
    "list_jobs_by_queue_state",
    "list_new_jobs_from_run",
    "list_recent_scrape_runs",
    "list_recent_scrape_runs_by_source",
    "record_scrape_run",
    "restore_job",
    "set_queue_state",
    "sum_listings_scanned_since",
    "upsert_job",
]
