"""US-city lookup for the job-search-preferences autocomplete.

Backed by the bundled `src/data/us_cities.json` (see `src/data/README.md`
for provenance) — ~29.8k `{"c": city, "s": state_code, "p": population}`
records sorted by population DESC. Loaded lazily once per process.

Search is typo-tolerant: normalized prefix matches rank first, then
substring matches, then close fuzzy matches (difflib) — all stable within
rank by population. `normalize_city` maps free-text (e.g. a parsed resume
location like "Boston, Massachusetts, USA") onto the canonical
"City, ST" form when it names a known US city.
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "us_cities.json"

_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}  # fmt: skip


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


@lru_cache(maxsize=1)
def _cities() -> list[dict]:
    with _DATA_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    for r in records:
        r["n"] = _norm(r["c"])
        r["label"] = f"{r['c']}, {r['s']}"
    return records


def search_cities(query: str, *, limit: int = 10) -> list[dict]:
    """Top matches as [{"label", "city", "state"}], typo-tolerant."""
    q = _norm(query)
    if not q:
        return []

    prefix: list[dict] = []
    substring: list[dict] = []
    for r in _cities():  # population-sorted, so ranks are stable by pop
        if r["n"].startswith(q):
            prefix.append(r)
            if len(prefix) >= limit:
                break
        elif q in r["n"]:
            substring.append(r)

    out = prefix + substring[: max(0, limit - len(prefix))]
    if len(out) < limit and len(q) >= 4:
        # Fuzzy fallback for typos ("bostn"). Match against unique city
        # names, then re-expand to records (population order preserved).
        seen = {r["n"] for r in out}
        names = [r["n"] for r in _cities() if r["n"] not in seen]
        close = set(difflib.get_close_matches(q, names, n=limit - len(out), cutoff=0.8))
        out += [r for r in _cities() if r["n"] in close][: limit - len(out)]

    return [{"label": r["label"], "city": r["c"], "state": r["s"]} for r in out[:limit]]


def normalize_city(free_text: str) -> str | None:
    """Map free-text location to canonical "City, ST" (or None).

    Handles "Boston", "Boston, MA", "Boston, Massachusetts",
    "Boston, MA, USA" — first (most-populous) match wins for bare names.
    """
    if not free_text:
        return None
    parts = [
        p
        for p in (_norm(p) for p in free_text.split(","))
        if p and p not in {"usa", "us", "united states"}
    ]
    if not parts:
        return None
    city_q = parts[0]
    state_q: str | None = None
    if len(parts) > 1:
        cand = parts[1]
        if cand.upper() in set(_STATE_NAMES.values()) or len(cand) == 2:
            state_q = cand.upper()
        else:
            state_q = _STATE_NAMES.get(cand)

    for r in _cities():
        if r["n"] == city_q and (state_q is None or r["s"] == state_q):
            return r["label"]
    return None
