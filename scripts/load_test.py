#!/usr/bin/env python3
"""Issue #37 hardening pass — a simple, self-contained local load-test
script for the API.

This is deliberately modest: it hits a handful of representative
endpoints against a *locally running* `uvicorn` instance and records
requests/sec and latency percentiles, so future scaling decisions have a
real (if small) number to compare against instead of a guess. It is NOT a
production capacity plan — see docs/infra/load-test-baseline.md for the
methodology caveats and the numbers actually recorded on a local dev
machine.

Usage
-----
Start the API separately first (a second terminal):

    DATABASE_URL=postgresql://localhost:5432/raindeer_test_issue37 \\
        uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

Then, from repo root, with the same DATABASE_URL exported so this script's
setup/teardown DB writes land in the same database the server is reading:

    DATABASE_URL=postgresql://localhost:5432/raindeer_test_issue37 \\
        python scripts/load_test.py

Optional flags: --base-url, --requests, --concurrency (see --help).

What it measures
-----------------
Three endpoints, each run as its own phase:
  1. GET  /health                        — unauthenticated, no DB query.
  2. GET  /brands                        — authenticated read, one query.
  3. POST /brands/{id}/calendar-events   — authenticated write (the
     lightest real write endpoint in the API — creating a Post via the
     full pipeline trigger is a Celery job, not a synchronous request, so
     isn't representative of *request* throughput the way this is).

/brands and calendar-events sit behind RateLimitMiddleware's per-org limit
(100 requests/60s by default — apps/api/middleware/rate_limit.py). A
single token would get rate-limited well before this script's default
request count, which would measure the rate limiter, not the endpoint. To
measure actual request-handling throughput instead, this script creates
several distinct organizations up front and round-robins requests across
their tokens, matching how the limiter is actually scoped in production
(per org, not globally) — see docs/infra/load-test-baseline.md for a note
on rate-limit behavior observed at higher request counts.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Repo root (this file is repo_root/scripts/load_test.py) — needed on
# sys.path so `apps.api...` imports resolve when this script is run
# directly (`python scripts/load_test.py`) rather than as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps.api.auth.jwt import create_access_token, hash_password  # noqa: E402
from apps.api.config.database import SessionLocal  # noqa: E402
from apps.api.models import Brand, Organization, User, UserRole  # noqa: E402

DEFAULT_ORG_COUNT = 5


@dataclass
class PhaseResult:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    status_counts: dict[int, int] = field(default_factory=dict)
    wall_seconds: float = 0.0

    def record(self, status_code: int, elapsed_ms: float) -> None:
        self.latencies_ms.append(elapsed_ms)
        self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1

    @property
    def total(self) -> int:
        return len(self.latencies_ms)

    @property
    def requests_per_sec(self) -> float:
        return self.total / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        idx = min(int(len(ordered) * p), len(ordered) - 1)
        return ordered[idx]

    def report(self) -> str:
        codes = ", ".join(f"{code}={count}" for code, count in sorted(self.status_counts.items()))
        return (
            f"{self.name}\n"
            f"  requests:      {self.total}\n"
            f"  wall time:     {self.wall_seconds:.3f}s\n"
            f"  requests/sec:  {self.requests_per_sec:.1f}\n"
            f"  latency mean:  {statistics.mean(self.latencies_ms):.1f}ms\n"
            f"  latency p50:   {self.percentile(0.50):.1f}ms\n"
            f"  latency p95:   {self.percentile(0.95):.1f}ms\n"
            f"  latency p99:   {self.percentile(0.99):.1f}ms\n"
            f"  status codes:  {codes}"
        )


@dataclass
class SeededOrg:
    org_id: uuid.UUID
    user_id: uuid.UUID
    brand_id: uuid.UUID
    token: str


def seed_orgs(count: int) -> list[SeededOrg]:
    """Creates `count` real Organization/User/Brand rows directly via the
    ORM (same DB the target uvicorn process is reading, via DATABASE_URL)
    so requests round-robin across distinct rate-limit keys."""
    db = SessionLocal()
    seeded: list[SeededOrg] = []
    try:
        run_tag = uuid.uuid4().hex[:8]
        for i in range(count):
            org = Organization(name=f"load-test-{run_tag}-{i}")
            db.add(org)
            db.flush()

            user = User(
                organization_id=org.id,
                email=f"load-test-{run_tag}-{i}@raindeer.test",
                password_hash=hash_password("load-test-password"),
                role=UserRole.EDITOR,
            )
            brand = Brand(organization_id=org.id, name=f"Load Test Brand {i}")
            db.add_all([user, brand])
            db.flush()

            token = create_access_token(
                user_id=str(user.id), org_id=str(org.id), role=UserRole.EDITOR.value
            )
            seeded.append(
                SeededOrg(org_id=org.id, user_id=user.id, brand_id=brand.id, token=token)
            )
        db.commit()
        return seeded
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cleanup_orgs(seeded: list[SeededOrg]) -> None:
    db = SessionLocal()
    try:
        org_ids = [s.org_id for s in seeded]
        db.query(Brand).filter(Brand.organization_id.in_(org_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.organization_id.in_(org_ids)).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id.in_(org_ids)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_phase(
    name: str,
    base_url: str,
    total_requests: int,
    concurrency: int,
    make_request: "callable[[httpx.Client, int], httpx.Response]",
) -> PhaseResult:
    result = PhaseResult(name=name)

    # One shared, connection-pooled client per phase (httpx.Client is
    # thread-safe for concurrent requests) rather than a fresh client —
    # and fresh TCP connection — per request: the latter measures
    # connection-setup overhead, not the endpoint's actual handling time,
    # and would badly understate real throughput (a real client/browser/
    # service reuses connections too).
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    with httpx.Client(base_url=base_url, timeout=30.0, limits=limits) as client:

        def _one(i: int) -> tuple[int, float]:
            started = time.perf_counter()
            response = make_request(client, i)
            elapsed_ms = (time.perf_counter() - started) * 1000
            return response.status_code, elapsed_ms

        wall_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for status_code, elapsed_ms in pool.map(_one, range(total_requests)):
                result.record(status_code, elapsed_ms)
        result.wall_seconds = time.perf_counter() - wall_start
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=150, help="requests per phase")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--orgs", type=int, default=DEFAULT_ORG_COUNT, help="distinct orgs to round-robin across")
    parser.add_argument("--keep-seed-data", action="store_true", help="skip teardown of seeded orgs/users/brands")
    args = parser.parse_args()

    print(f"Seeding {args.orgs} organizations for round-robin auth...")
    seeded = seed_orgs(args.orgs)
    print(f"Seeded. Target: {args.base_url}\n")

    results: list[PhaseResult] = []
    try:
        # Phase 1: unauthenticated health check — no DB, no auth, no rate limit.
        results.append(
            run_phase(
                "GET /health",
                args.base_url,
                args.requests,
                args.concurrency,
                lambda client, i: client.get("/health"),
            )
        )

        # Phase 2: authenticated read, round-robin across seeded orgs.
        results.append(
            run_phase(
                "GET /brands",
                args.base_url,
                args.requests,
                args.concurrency,
                lambda client, i: client.get(
                    "/brands", headers={"Authorization": f"Bearer {seeded[i % len(seeded)].token}"}
                ),
            )
        )

        # Phase 3: authenticated write, round-robin across seeded orgs.
        event_payload = {
            "title": "Load test event",
            "description": "Created by scripts/load_test.py",
            "target_platforms": ["linkedin"],
            "desired_format": "single-image",
            "target_datetime": "2026-12-01T12:00:00Z",
        }
        results.append(
            run_phase(
                "POST /brands/{id}/calendar-events",
                args.base_url,
                args.requests,
                args.concurrency,
                lambda client, i: client.post(
                    f"/brands/{seeded[i % len(seeded)].brand_id}/calendar-events",
                    json=event_payload,
                    headers={"Authorization": f"Bearer {seeded[i % len(seeded)].token}"},
                ),
            )
        )
    finally:
        if not args.keep_seed_data:
            print("Cleaning up seeded orgs/users/brands (calendar events cascade)...")
            db = SessionLocal()
            try:
                from apps.api.models import ContentCalendarEvent

                brand_ids = [s.brand_id for s in seeded]
                db.query(ContentCalendarEvent).filter(
                    ContentCalendarEvent.brand_id.in_(brand_ids)
                ).delete(synchronize_session=False)
                db.commit()
            finally:
                db.close()
            cleanup_orgs(seeded)

    print("\n" + "=" * 60)
    print("Load test results")
    print("=" * 60)
    for result in results:
        print()
        print(result.report())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
