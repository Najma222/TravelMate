# Backend Progress Tracker

Status values: NOT_STARTED · IN_PROGRESS · IMPLEMENTED · TESTED · BLOCKED.
Last updated: 2026-11-23. Test suite: `cd backend && python -m pytest` (PostgreSQL 16 on :55432).

| Feature | Files | Status | Tests | Issues / next action |
|---|---|---|---|---|
| Config, fail-fast env validation | `config.py` | TESTED | all suites (testing config) | — |
| App factory, wsgi, extensions | `app/__init__.py`, `wsgi.py`, `app/extensions.py` | TESTED | all | — |
| Error envelope + handlers | `app/utils/errors.py` | TESTED | `test_middleware.py`, many | — |
| Request id, JSON access log | `app/middleware/request_id.py`, `request_logging.py` | TESTED | `test_middleware.py` | — |
| D12 origin/referer/content-type guard | `app/middleware/origin_check.py` | TESTED | `test_middleware.py` | Bodyless POST/DELETE also need JSON content type (I7) |
| Health | `blueprints/health.py`, `services/health_service.py` | TESTED | `test_middleware.py`, Docker | — |
| 11 models + constraints + indexes | `app/models/*` | TESTED | all; `flask db check` = no drift | — |
| Migration `0001_initial_schema` | `migrations/versions/0001_initial_schema.py` | TESTED | test session builds schema via upgrade; downgrade/upgrade round-trip; Docker boot | — |
| Auth: register/login/logout/me/profile/password/delete | `blueprints/auth.py`, `services/auth_service.py`, `schemas/auth.py`, `schemas/user.py` | TESTED | `test_auth.py` | — |
| Session nonce rotation | `utils/auth.py`, `services/auth_service.py` | TESTED | `test_auth.py` | Logout ends all sessions (I4) |
| Rate limits (10/min IP; 5 failures/15 min/email) | `blueprints/auth.py`, `services/auth_service.py` | TESTED | `test_auth.py` | In-memory IP limiter assumes 1 worker (I6) |
| Route audit (login_required / internal_only / public) | `utils/auth.py`, `utils/internal_auth.py` | TESTED | `test_architecture.py` | — |
| Audit log | `services/audit.py` | TESTED | auth, callback, csrf tests | — |
| Trips CRUD, scopes, pagination, phase, ring, dedupe | `blueprints/trips.py`, `services/trip_service.py`, `services/trip_rules.py`, `schemas/trip.py` | TESTED | `test_trips.py` | — |
| Stops + deferred reorder | `services/trip_service.py`, `schemas/trip_stop.py` | TESTED | `test_itinerary_stops.py` | — |
| Itinerary + days (D7) | `blueprints/itinerary.py`, `services/itinerary_service.py`, `schemas/itinerary.py`, `schemas/trip_day.py` | TESTED | `test_itinerary_stops.py` | — |
| Atomic generation + n8n client | `services/generation_service.py`, `services/n8n_client.py` | TESTED | `test_generation.py` (incl. 5-thread race, retry/timeout rules, commit-before-call) | — |
| Callback (idempotent, stale, replace/preserve) | `services/callback_service.py`, `schemas/callback.py` | TESTED | `test_callback.py` | — |
| Stuck sweeper | `services/trip_service.py` | TESTED | `test_generation.py` | — |
| Overview (≤8 queries, ETag/304) | `blueprints/overview.py`, `services/overview_service.py` | TESTED | `test_discover_overview.py` | — |
| Dashboard | `blueprints/dashboard.py`, `services/overview_service.py`, `schemas/dashboard.py` | TESTED | `test_discover_overview.py` | — |
| Expenses + D3 budget | `blueprints/expenses.py`, `services/expense_service.py`, `services/budget.py`, `schemas/expense.py` | TESTED | `test_budget_expenses.py` | — |
| Bookings + atomic expense sync (D10) | `blueprints/bookings.py`, `services/booking_service.py`, `services/booking_sync.py`, `schemas/booking.py` | TESTED | `test_bookings.py` | — |
| Booking links | `services/booking_links.py` | TESTED | `test_bookings.py` | — |
| Weather (D6) | `services/weather.py`, `schemas/weather.py` | TESTED | `test_packing_weather.py`, `test_callback.py` | — |
| Packing + seed + reminders + auto-jacket (D11) | `services/packing_service.py`, `services/packing_seed.py`, `schemas/packing.py` | TESTED | `test_packing_weather.py`, `test_callback.py` | — |
| Discover + seed | `blueprints/discover.py`, `services/discover_service.py`, `seed/discover_destinations.json` | TESTED | `test_discover_overview.py`, `test_cli.py` | 32 destinations |
| Places | `blueprints/trips.py`, `services/trip_service.py` | TESTED | `test_discover_overview.py` | — |
| Notifications + prefs + dedupe (D9) | `blueprints/notifications.py`, `services/notification_service.py`, `schemas/notification.py` | TESTED | `test_notifications.py` | — |
| Internal endpoints + reminder queries | `blueprints/internal.py`, `services/reminder_queries.py` | TESTED | `test_notifications.py`, `test_generation.py`, `test_callback.py` | — |
| Media uploads (D14) | `services/upload_service.py`, `blueprints/media.py` | TESTED | `test_uploads.py` | — |
| CLI: seed-discover / seed-demo / simulate-callback | `app/cli.py` | TESTED | `test_cli.py` | — |
| Docker Compose (db, backend, web, n8n, n8n-init) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `backend/entrypoint.sh` | TESTED | Manual: `up --build`, all healthy, smoke test, restart persistence | nginx `web` serves pages and proxies `/api` + `/media` |
| API docs (contract, OpenAPI, Postman) | `docs/*`, `backend/scripts/gen_api_docs.py` | TESTED | `test_docs.py` (route parity + OpenAPI validation) | — |
| n8n trip-generation workflow | `n8n/workflows/travelmate-trip-generate.json`, compose `n8n-init` | IMPLEMENTED | Imported + published + webhook executed in n8n 2.48.6 (dummy keys → Failed callback path) | Live itinerary output needs `GEMINI_API_KEY` + `GEOAPIFY_API_KEY` |
| Frontend integration | `frontend/assets/js/api.js`, `frontend/nginx.conf`, `frontend/Dockerfile` | IMPLEMENTED | Request/response adapter checked against every page; same-origin proxy tested | Browser E2E pending user API keys |
| n8n weather-refresh / reminder / booking-gap cron workflows | — | NOT_STARTED | — | Optional; generation already stores weather in its callback |
