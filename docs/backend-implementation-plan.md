# TravelMate Backend — Implementation Plan

Source of truth: `AGENTS.md` (v1.1). No `docs/api-contract.md`, `docs/openapi.yaml`,
`docs/integration-*.md` existed at audit time; they are produced by this work and
must stay consistent with `AGENTS.md`.

## Phase 0 — Audit (2026-11-23)

Existing repository state:

| Item | State |
|---|---|
| `backend/app.py` | Flask hello-world with `GET /health` only (replaced by app factory + `wsgi.py`) |
| `backend/Dockerfile` | Runs `gunicorn app:app` with default workers (does not satisfy D2) |
| `backend/requirements.txt` | Unpinned Flask / gunicorn / psycopg2 |
| `docker-compose.yml` | `db` (postgres:16), `backend`, `n8n` services, named volumes, shared network |
| Tests, models, migrations, docs | Absent |

Repository layout note: the master prompt describes a `travelmate/` project root; the
existing repository root *is* that root (it already contains `backend/`,
`docker-compose.yml`, `docs/`), so files are placed relative to the repository root.

## Phases and dependencies

| Phase | Scope | Depends on |
|---|---|---|
| 1 Foundation | config, extensions, app factory, wsgi, errors, request-id/logging/origin middleware, health, Docker | — |
| 2 Auth + models | 11 models, migration `0001_initial_schema`, auth service/routes, session nonce, decorators, rate limits | 1 |
| 3 Trips/core | trip CRUD, scopes, phase, ring, pagination, overview (≤8 queries, ETag), dashboard | 2 |
| 4 Itinerary/generation | itinerary, days, stops, atomic generate, n8n client, callback, sweeper | 3 |
| 5 Money | expenses, D3 budget, bookings, booking sync, booking links | 3 |
| 6 Weather/places/packing | discover + seed, places, weather (D6), packing seed + CRUD, auto-jacket | 4 |
| 7 Notifications/internal | notifications, prefs, dedupe (D9), reminder queries, internal routes | 3 |
| 8 Media | Pillow validation, WebP re-encode, avatar/cover, `/media` serving | 2 |
| 9 Finalisation | api-contract, OpenAPI, Postman, README, checklist, full verification | all |

## Risks

* **PostgreSQL-only features** (JSONB, `FOR UPDATE`, deferrable constraints, partial
  unique index, `INET`) — tests must run against real PostgreSQL 16, not SQLite.
  Tests use a disposable `postgres:16` container (see README).
* **Signed-cookie sessions** cannot be revoked individually; revocation uses the
  per-user `session_nonce` (logout and password change rotate it).
* **n8n workflow** is not part of this repository; the backend contract is documented
  in `docs/integration-decisions.md` and must be mirrored in the n8n workflow.

Progress is tracked in `docs/backend-progress.md`.
