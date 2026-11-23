# Integration Checklist

## Backend (verified in this repository)
- [x] `docker compose up --build` starts db, backend, n8n; backend and n8n report healthy.
- [x] Backend waits for PostgreSQL, runs `flask db upgrade`, seeds destinations (idempotent), starts Gunicorn `--workers 1 --threads 4`.
- [x] Backend reaches n8n at `http://n8n:5678` over `travelmate-net` (verified: n8n answered; with no workflow imported the trip correctly became `Failed` / `502`).
- [x] Data persists across container restarts (named volumes `pgdata`, `uploads`, `n8n_data`).
- [x] Full pytest suite against PostgreSQL 16.

## Frontend
- [ ] Send `credentials: "include"` on every API call.
- [ ] Always send `Content-Type: application/json` on `POST/PUT/DELETE` (even bodyless) — uploads use `multipart/form-data` with field `file`.
- [ ] Frontend origin is listed in `ALLOWED_ORIGINS` (comma-separated, scheme + host + port).
- [ ] Treat money fields as strings (format with `Intl.NumberFormat` using `trip.currency`).
- [ ] Poll `GET /trips/{id}/status` while `Processing` (e.g. every 3 s); stop on `Completed`/`Failed`.
- [ ] Use `ETag`/`If-None-Match` for `GET /trips/{id}/overview`.
- [ ] Booking-linked expenses (`locked: true`) are read-only; edit the booking instead.
- [ ] Handle the error envelope (`error.code`, `error.details.fields`).
- [ ] Production is HTTPS (cookie is `Secure`); for plain-HTTP local runs set `SESSION_COOKIE_SECURE=false` or use `APP_ENV=development`.

## n8n
- [ ] Import/build the trip-generation workflow at `/webhook/trip-generate`.
- [ ] Workflow verifies `X-Webhook-Secret` on the trigger and sends it on every callback.
- [ ] Callback echoes `generation_id`; ≤ 200 itinerary rows, ≤ 50 expense rows.
- [ ] Weather refresh workflow uses `PUT /api/v1/internal/trips/{id}/weather`.
- [ ] Reminder workflows record deliveries via `POST /api/v1/internal/notifications` and do not resend on `409`.
- [ ] Optional cron for `POST /api/v1/internal/sweep-stuck`.

## Deployment
- [ ] `.env` created from `.env.example` with strong random secrets (never committed).
- [ ] `FLASK_SECRET_KEY` ≥ 32 chars (enforced in production).
- [ ] TLS terminated in front of the backend; `ProxyFix` / trusted proxy configuration reviewed if a proxy is added (rate limits key on client IP).
- [ ] PostgreSQL port is not published (default compose config keeps it internal).
- [ ] Backups for `pgdata` and `uploads` volumes.
