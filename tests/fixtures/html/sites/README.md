# Site scraper HTML / JSON fixtures

Hand-crafted, structurally accurate. Modeled on real DOM observations but
NEVER contain real PII / company names — fictional companies + fictional
URL hosts (`fictional.example.com`, `acme-fake.example.com`, etc.).

Per plan 33 § OQ.3: hand-crafted beats live-scrubbed because (a) no PII
audit step, (b) versionable, (c) clearly fictional under reviewer eye.

## Naming

`{source}_listing.{html,json}` — listing-page response.
`{source}_detail.html` — detail-page response.

## Source DOM dates

| File | Source DOM date observed |
|---|---|
| greenhouse_listing.json | 2026-05-19 (boards.greenhouse.io/embed/job_board) |
| greenhouse_detail.html | 2026-05-19 (boards.greenhouse.io/<co>/jobs/<id>) |
| lever_listing.json | 2026-05-19 (api.lever.co/v0/postings) |
| lever_detail.html | 2026-05-19 (jobs.lever.co/<co>/<id>) |
| ashby_listing.json | 2026-05-19 (api.ashbyhq.com/posting-api) |
| ashby_detail.html | 2026-05-19 (jobs.ashbyhq.com/<co>/<id>) |
| linkedin_listing.html | 2026-05-19 (linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings) |
| linkedin_detail.html | 2026-05-19 (linkedin.com/jobs-guest/jobs/api/jobPosting/<id>) |
| workday_listing.html | 2026-05-19 (<tenant>.wd1.myworkdayjobs.com) |
| workday_detail.html | 2026-05-19 (<tenant>.wd1.myworkdayjobs.com/job/...) |
| indeed_listing.html | 2026-05-19 (indeed.com/jobs?q=...) |
| indeed_detail.html | 2026-05-19 (indeed.com/viewjob?jk=...) |

## Regenerating

When DOM shape drifts (a parse test starts failing because the real site
moved selectors), hand-edit the fixture to match new structure. Do not
paste real responses without scrubbing PII; if scrubbing seems hard, the
fixture is already too close to a live capture.
