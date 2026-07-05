"""Utils package — domain-free helpers shared across services.

Plan 93 Part 1: `crypto` (SECRET_KEY-derived Fernet), `geo` (US-city
lookup), `html_text` (HTML → text), `rate_limit` (in-memory per-user
limiter + FastAPI deps; module-level buckets stay single-instance via the
single import path), `first_run` (first-run diagnostic probe).

Module-tier seams: import the submodule (`from services.utils import geo`)
and patch `services.utils.<mod>.X`.
"""
