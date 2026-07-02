# Bundled datasets

## us_cities.json

US city + state pairs used by the job-search-preferences city autocomplete
(`GET /api/v1/geo/cities`, see `docs/design/JOB_SEARCH_PREFERENCES.md`).

Format: compact JSON array of `{"c": city, "s": state_code, "p": population}`
sorted by population DESC (0 = population unknown), then city name.

Sources (merged 2026-07-02):

- Base list (~29.8k cities): [kelvins/US-Cities-Database](https://github.com/kelvins/US-Cities-Database) — MIT license.
- Population ranking (top 1k cities): [plotly/datasets `us-cities-top-1k.csv`](https://github.com/plotly/datasets) — MIT license (2014 census estimates; used only as an autocomplete ranking signal, not displayed).
