"""US-city autocomplete — `GET /api/v1/geo/cities?q=`.

Serves the job-search-preferences city input (profile page). Backed by the
bundled dataset in `src/data/us_cities.json` via `services/geo.py`; no
network calls. See docs/design/JOB_SEARCH_PREFERENCES.md § C.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from models import User
from services.auth import require_authed_session
from services.utils.geo import search_cities

router = APIRouter(prefix="/api/v1/geo")


class CityMatch(BaseModel):
    label: str
    city: str
    state: str


class CityMatches(BaseModel):
    items: list[CityMatch]


@router.get("/cities", response_model=CityMatches)
async def get_cities(
    q: str = Query(default="", max_length=80),
    _user: User = Depends(require_authed_session),
) -> CityMatches:
    return CityMatches(items=[CityMatch(**m) for m in search_cities(q)])
