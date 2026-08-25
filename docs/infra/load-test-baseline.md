# Load-Test Baseline

Issue #37 — final hardening pass. Date: 2026-08-25.

## Scope and honesty note

**This is a local dev-machine baseline, not a production capacity plan.**
It was run on a single laptop, against a single `uvicorn` worker process,
with Postgres and Redis also running locally on the same machine — the
numbers below say nothing about what a real deployment (managed Postgres,
a Redis cluster, multiple API replicas behind a load balancer, real
network latency) could sustain. Its purpose, per issue #37, is to
establish *some* real, actually-measured number to compare future changes
against, rather than continuing to operate on a guess. No cloud
infrastructure was provisioned for this — see
`docs/security/secrets-management.md` for the same honesty note applied
to the secrets-manager migration piece of this issue.

Machine: local development machine (Apple Silicon Mac), not representative
of production hardware.

## 1. Rate limiting under genuine concurrent load

`apps/api/middleware/rate_limit.py` (Issue #12) already had single-request
tests (`apps/api/tests/test_rate_limit.py`). This issue adds
`test_concurrent_requests_hold_exactly_at_the_limit`, which fires 60
genuinely concurrent requests (real OS threads, real sockets, a real
`uvicorn` server — not `TestClient`, whose single-event-loop dispatch
would serialize the middleware's blocking Redis call and prove nothing;
see the test's docstring for why) at an endpoint capped at 20
requests/window, aligned to start together via a `threading.Barrier`.

**Result: exactly 20 requests succeeded (200) and exactly 40 were rejected
(429) — every run, no flakiness observed across repeated local runs.**
No double-counting (more than the limit let through) and no
over-blocking (fewer than the limit let through). This is expected: the
limiter's core operation is Redis's `INCR`, which is atomic server-side
regardless of how many clients race it concurrently — the test exists as
a regression net (e.g. against someone "simplifying" the middleware to a
non-atomic get/compare/set), not because a race was suspected.

A second real-world confirmation came from the load test below itself: a
run against a single organization's token pushed 300 total requests
(2 phases × 150) through `/brands`-prefixed routes inside one 60-second
window, well past the default limit of 100. The limiter enforced the cap
exactly as documented — see run 3 below.

## 2. Load-test script and methodology

`scripts/load_test.py` is a small, self-contained script (stdlib +
`httpx`, both already dependencies) that:

1. Seeds N real `Organization`/`User`/`Brand` rows directly via the ORM
   (so requests round-robin across distinct rate-limit keys, matching how
   the limiter is actually scoped in production — per org, not globally).
2. Fires `--requests` HTTP requests at `--concurrency` concurrent workers
   (a `ThreadPoolExecutor` + one shared, connection-pooled `httpx.Client`
   per phase) against each of three phases:
   - `GET /health` — unauthenticated, no DB query, no rate limit
     (health isn't under a rate-limited path prefix).
   - `GET /brands` — authenticated read, one DB query, rate-limited.
   - `POST /brands/{id}/calendar-events` — authenticated write (the
     lightest real synchronous write endpoint in the API; the actual
     content pipeline runs as a Celery job, not inline in a request, so
     isn't representative of *request* throughput the way this is).
3. Records per-request latency and status code, then reports
   requests/sec (total requests ÷ phase wall-clock time) and p50/p95/p99
   latency per phase.
4. Tears down the seeded rows afterward (`--keep-seed-data` to skip).

Run it against a locally running `uvicorn` instance:

```bash
# terminal 1
DATABASE_URL=postgresql://localhost:5432/raindeer_test_issue37 \
    uvicorn apps.api.main:app --host 127.0.0.1 --port 8123

# terminal 2
DATABASE_URL=postgresql://localhost:5432/raindeer_test_issue37 \
    python scripts/load_test.py --base-url http://127.0.0.1:8123 \
    --requests 400 --concurrency 25 --orgs 8
```

## 3. Recorded results (2026-08-25, local dev machine)

### Run 1 — 400 requests/phase, concurrency 25, 8 organizations

All requests succeeded (no rate limiting — spread across 8 orgs, 50
requests/org, under the 100/60s per-org cap).

| Phase | Requests | Wall time | Req/sec | p50 | p95 | p99 | Status codes |
|---|---:|---:|---:|---:|---:|---:|---|
| `GET /health` | 400 | 0.411s | 972.5 | 24.1ms | 32.5ms | 39.4ms | 200×400 |
| `GET /brands` | 400 | 0.486s | 822.7 | 29.2ms | 38.2ms | 43.2ms | 200×400 |
| `POST /brands/{id}/calendar-events` | 400 | 1.089s | 367.4 | 58.2ms | 138.0ms | 189.7ms | 201×400 |

### Run 2 — 150 requests/phase, concurrency 10, 5 organizations (lighter load, for comparison)

| Phase | Requests | Wall time | Req/sec | p50 | p95 | p99 | Status codes |
|---|---:|---:|---:|---:|---:|---:|---|
| `GET /health` | 150 | 0.087s | 1714.8 | 5.2ms | 9.9ms | 12.3ms | 200×150 |
| `GET /brands` | 150 | 0.167s | 898.5 | 10.4ms | 15.6ms | 25.8ms | 200×150 |
| `POST /brands/{id}/calendar-events` | 150 | 0.286s | 524.9 | 17.9ms | 28.7ms | 30.9ms | 201×150 |

### Run 3 — rate limiter under real sustained load: 150 requests/phase, concurrency 15, **1 organization** (deliberately, to push past the per-org cap)

| Phase | Requests | Req/sec | Status codes |
|---|---:|---:|---|
| `GET /health` | 150 | 741.0 | 200×150 (not rate-limited — not under a limited path prefix) |
| `GET /brands` | 150 | 1051.9 | 200×100, **429×50** |
| `POST /brands/{id}/calendar-events` | 150 | 1371.9 | **429×150** |

This run's single organization hit exactly 100 successes on `/brands`
before the limiter started returning 429 for the remainder of that phase,
and — having already exhausted its 60-second window — got 429 on every
request of the following write phase too. This is the limiter working
exactly as designed (`DEFAULT_LIMIT = 100`,
`DEFAULT_WINDOW_SECONDS = 60`), observed under genuine request volume
rather than only asserted by a single-request unit test.

## 4. Interpretation

- Read/write throughput (Run 1: ~370–970 req/sec depending on endpoint,
  single `uvicorn` worker) is dominated by Postgres round-trips per
  request, not framework/middleware overhead — the write endpoint
  (an INSERT plus surrounding validation) is consistently the slowest of
  the three, as expected.
- These numbers scale with worker count in production (`uvicorn
  --workers N` or multiple replicas behind a load balancer) far more than
  they'd scale with raw hardware on this one process — a real capacity
  plan needs that dimension, which this baseline deliberately doesn't
  attempt.
- The rate limiter holds under both synthetic concurrent-thread pressure
  (§1) and real sustained multi-phase load (Run 3) — no gap found here.
