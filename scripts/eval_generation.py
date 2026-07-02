"""Standalone generation-quality eval — item 9 (2026-07).

Runs `services.generation_eval.evaluate_bundle` over already-generated
applications and prints per-bundle scorecards, so prompt changes can be
compared before/after:

    NAAVIK_DEBUG=1 DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik \
        uv run python scripts/eval_generation.py --apps 7,14

Read-only against application rows except for the ApiUsage rows the
tracked judge call writes. `--no-judge` skips the LLM entirely (free,
deterministic checks only).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def _run(app_ids: list[int], run_judge: bool) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from config import settings as app_settings
    from models import Application
    from services import generation_eval, settings_service

    engine = create_async_engine(app_settings.database_url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    failures = 0
    async with maker() as session:
        for app_id in app_ids:
            application = (
                await session.exec(select(Application).where(Application.id == app_id))
            ).one_or_none()
            if application is None:
                print(f"[app {app_id}] NOT FOUND")
                failures += 1
                continue
            user_settings = await settings_service.get_or_create(
                session, user_id=application.user_id
            )
            scorecard = await generation_eval.evaluate_bundle(
                session, application, settings=user_settings, run_judge=run_judge
            )
            await session.commit()  # persist the judge's ApiUsage row
            if scorecard is None:
                print(f"[app {app_id}] no generated bundle to evaluate")
                failures += 1
                continue
            det = scorecard["deterministic"]
            print(
                f"\n[app {app_id}] deterministic "
                f"{scorecard['deterministic_passed']}/{scorecard['deterministic_total']}"
            )
            for name, check in det.items():
                mark = "·" if check["passed"] is None else ("✓" if check["passed"] else "✗")
                extra = f"  {check['value']}" if check["passed"] is False else ""
                print(f"  {mark} {name}{extra}")
            ts = scorecard["trace_scores"]
            print(
                f"  parse_fidelity={ts['parse_fidelity']} keyword_coverage={ts['keyword_coverage']}"
            )
            judge = scorecard["judge"]
            if judge:
                print(
                    "  judge: "
                    f"ats={judge['ats_friendliness']:.2f} "
                    f"jd={judge['jd_keyword_usage']:.2f} "
                    f"honesty={judge['honesty_vs_profile']:.2f} "
                    f"tone={judge['tone']:.2f}"
                )
                if judge.get("violations"):
                    print(f"  flagged: {judge['violations']}")
                if judge.get("notes"):
                    print(f"  notes: {judge['notes']}")
            else:
                print("  judge: skipped (no provider)")
            print(json.dumps(scorecard, default=str)[:200] + "…")
    await engine.dispose()
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps", required=True, help="comma-separated application ids")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM judge call")
    args = parser.parse_args()
    app_ids = [int(x) for x in args.apps.split(",") if x.strip()]
    failures = asyncio.run(_run(app_ids, run_judge=not args.no_judge))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
