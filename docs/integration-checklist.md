# Integration Checklist

## Backend (verified in this repository)
- [x] `docker compose up --build` starts db, backend, web and n8n; `n8n-init` imports the workflow with `--activeState=fromJson`.
- [x] Backend waits for PostgreSQL, runs `flask db upgrade`, seeds destinations (idempotent), starts Gunicorn `--workers 1 --threads 4`.
- [x] Backend reaches n8n at `http://n8n:5678` over `travelmate-net`.
- [x] Data persists across container restarts (named volumes `pgdata`, `uploads`, `n8n_data`).
- [x] Full pytest suite against PostgreSQL 16.

## Frontend (implemented in `frontend/assets/js/api.js` + nginx `web`)
- [x] Send `credentials: "include"` on every API call.
- [x] Always send `Content-Type: application/json` on `POST/PUT/DELETE` (even bodyless).
- [x] Pages and API share one origin (`http://localhost:8080`); nginx proxies `/api` and `/media` to Flask.
- [x] `ALLOWED_ORIGINS` contains the browser origin(s); `TRUSTED_PROXIES=1` makes Flask see the real client IP.
- [x] Money is translated for the existing INR display; the adapter also maps envelopes and field names.
- [x] Poll `GET /trips/{id}/status` while `Processing`; stop on `Completed`/`Failed`.
- [x] Error envelope (`error.code`, `error.details.fields`) becomes a readable toast.
- [x] `SESSION_COOKIE_SECURE=false` for plain-HTTP local runs.
- [ ] Use `ETag`/`If-None-Match` for `GET /trips/{id}/overview` (not used by the current pages).
- [ ] Booking-linked expenses (`locked: true`) are not disabled in the UI; the API returns `409`.

## n8n
- [x] Trip-generation workflow shipped at `n8n/workflows/travelmate-trip-generate.json`, imported with `--activeState=fromJson` by `n8n-init`.
- [x] Workflow verifies `X-Webhook-Secret` on the trigger and sends it on every callback.
- [x] Callback echoes `generation_id`; itinerary/expense row caps respected.
- [x] Uses Geoapify (places/coordinates), Open-Meteo (weather, no key) and Gemini (itinerary).
- [ ] Weather-refresh cron using `PUT /api/v1/internal/trips/{id}/weather` (generation already stores weather).
- [ ] Reminder workflows using `GET /internal/upcoming-trips` / `booking-gaps` + `POST /internal/notifications` (no resend on `409`).
- [ ] Optional cron for `POST /api/v1/internal/sweep-stuck`.

## Deployment
- [x] `.env` created from `.env.example` with strong random secrets (never committed).
- [x] `FLASK_SECRET_KEY` ≥ 32 chars (enforced in production).
- [x] nginx is the only browser-facing origin; Flask uses `ProxyFix` with `TRUSTED_PROXIES=1` (rate limits key on client IP). Set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- [x] PostgreSQL port is not published (default compose config keeps it internal).
- [ ] Backups for `pgdata` and `uploads` volumes.
