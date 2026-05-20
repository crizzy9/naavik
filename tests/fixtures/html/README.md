# tests/fixtures/html/

HTML fixtures for `job_extractor` unit tests (plan 30 / 0.2.0.08).

Naming: `<source>-<scenario>.html`. Five top-level scenarios cover the cases
the extraction service must handle:

| File | Purpose |
|---|---|
| `linkedin-senior-engineer.html` | Realistic LinkedIn JD with nav / footer / script noise. Exercises `_strip_boilerplate` reduction. |
| `greenhouse-sponsorship.html` | Greenhouse JD with explicit "we sponsor H1B" body. Exercises `visa_restrictions=sponsorship_available`. |
| `workday-citizen-only.html` | Workday JD with "must be US citizen" body. Exercises `visa_restrictions=us_citizen_only`. |
| `empty-body.html` | Just `<script>` tags + footer (no JD body). Exercises the empty-strip-output schema-invalid path. |
| `minimal-valid.html` | Smallest JD that still has a body. Exercises the happy path. |

The site-specific fixtures under `tests/fixtures/html/sites/` belong to
`0.2.0.07` per-site scraper tests; they are not reused here because the
extractor tests want representative noise patterns to validate the
boilerplate strip in isolation.
