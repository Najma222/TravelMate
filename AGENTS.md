# AGENTS.md — TravelMate Backend Engineering Specification (v1.1)

## 1. Role & Architecture Overview

You are building the **TravelMate** backend (`Flask` + `PostgreSQL 16` + `SQLAlchemy` + `Docker Compose` + `n8n` integration).

- **Strict Layering:** `Blueprints (thin HTTP controllers)` → `Services (business logic & DB transactions)` → `Models / Repositories` + `Schemas (pure validation & serialization)`.
- **Blueprints must NEVER touch `db.session` directly.** Services own `db.session.commit()` and `db.session.rollback()`.
- **Models must NOT contain `to_dict()` methods.** All serialization lives in `app/schemas/`.
- Keep modules cohesive, avoid duplicated business logic, and follow existing patterns where they comply with this specification.

## 2. Non-Negotiable Architectural Decisions (D1–D14)

### D1 — API Versioning
- All API routes live under `/api/v1/...`.
- Only `GET /health` and `GET /media/<path:filename>` are unversioned.

### D2 — Environment & Entrypoint
Required environment variables:
- `FLASK_SECRET_KEY`
- `INTERNAL_WEBHOOK_SECRET`
- `N8N_TRIP_WEBHOOK_URL`
- `DATABASE_URL`
- `APP_TIMEZONE=Asia/Kolkata`
- `ALLOWED_ORIGINS`
- `UPLOAD_DIR`

Gunicorn entrypoint is `wsgi:app`, using `--workers 1 --threads 4`.

### D3 — Budget Math
- Use **`Decimal` arithmetic ONLY** for money. Never use `float` for calculations.
- Database money columns use `NUMERIC(12,2)`.
- JSON output amounts are rounded to 2 decimals.
- `confirmed_total` = sum of expenses where `is_confirmed == True`.
- `estimated_total` = sum of expenses where `is_confirmed == False`.
- For each category (`transport`, `accommodation`, `food`, `activities`, `local_transport`, `misc`): `effective = confirmed if confirmed > 0 else estimated`.
- Category `basis` is `confirmed` if `confirmed > 0`, otherwise `estimated`.
- `forecast_total` = sum of `effective` across categories.
- `remaining = budget - forecast_total`; `exceeded = remaining < 0`; `exceeded_by = max(Decimal('0.00'), -remaining)`.
- `spent_percent = round(confirmed_total / budget * 100, 1)`.
- `remaining_percent = max(0.0, round(100 - spent_percent, 1))`.
- `forecast_percent = round(forecast_total / budget * 100, 1)`.

### D4 — Expense Categories
Fixed categories: `transport`, `accommodation`, `food`, `activities`, `local_transport`, `misc`.\nCallback normalization:
- `Transportation` → `transport`
- `Miscellaneous` → `misc`
- Case-fold other category names.

### D5 — Generation ID
- Every `/generate` call creates a new UUID `generation_id`.
- Send it to n8n; callback must echo it.
- A callback with mismatched `generation_id` returns HTTP `200` and `{"ignored": true, "reason": "stale_generation"}`.

### D6 — Weather Storage
- Store weather in `trips.weather` (JSONB) with `location_name`, `current` (`temperature_c`, `weather_code`, `observed_at`), and a `daily` list.
- Map WMO codes to labels in `services/weather.py`.
- Guarantee `high_c >= low_c`.
- Never fabricate weather. If weather is empty/unavailable, return `available: false` and a `weather_message`.
- Support `PUT /api/v1/internal/trips/{id}/weather`.

### D7 — Stops & Days
- `trip_stops` have ordered `position` and a `DEFERRABLE INITIALLY DEFERRED` unique constraint on `(trip_id, position)`.
- `trip_days` stores a title per day, defaulting to `Day N`.
- Calendar dates are computed from `start_date + (day_number - 1)` and are never stored.

### D8 — Currency
- `trips.currency` is ISO 4217, restricted to `INR`, `USD`, `EUR`, `GBP`, `NPR`, `BDT`, `AED`; default `INR`.
- Currency is display-only in v1; do not implement currency conversion.

### D9 — Notifications
- Track `channels` (JSONB), `read_at`, `delivery_status` (`sent`, `failed`, `pending`), and `scheduled_for` (DATE in `APP_TIMEZONE`).
- Unique constraint: `(trip_id, notification_type, scheduled_for)`.
- Re-posting a `failed` notification updates it and returns `200`.
- Re-posting a `sent` notification returns `409 conflict`.

### D10 — Bookings & Sync
- Booking types: `hotel`, `flight`, `train`, `bus`.
- Statuses: `Not Booked`, `Pending`, `Confirmed`, `Cancelled`.
- Store `start_at` / `end_at` (`TIMESTAMPTZ`) and `start_tz` / `end_tz` (IANA timezone).
- In the same transaction, if `status == 'Confirmed'` and `amount > 0`, upsert a linked `Expense` (`booking_id=booking.id`, `is_confirmed=True`, `source='booking'`, category `accommodation` for hotel, otherwise `transport`). Otherwise delete any linked expense.
- Editing or deleting booking-linked expenses directly via `/expenses` returns `409 conflict`.

### D11 — Packing Items
- Seed default items from `seed/default_packing.json` when a trip is created.
- `remind_at` must be in the future and `<= trip.end_date`.
- After a successful n8n callback, if minimum forecast temperature is `<= 15°C` and no `jacket` item exists, auto-add one (`source='auto'`).

### D12 — CSRF & Security
- Unsafe user-route methods (`POST`, `PUT`, `DELETE`) require `Origin` or `Referer` matching `ALLOWED_ORIGINS` and `Content-Type: application/json` (or `multipart/form-data` on upload routes). Otherwise return `403 forbidden`.

### D13 — Trip Phases & Scopes
Computed dynamically in `APP_TIMEZONE` (`Asia/Kolkata`), never stored:
- `phase`: `upcoming` (`today < start_date`), `ongoing` (`start_date <= today <= end_date`), `past` (`today > end_date`).
- `scope=upcoming`: `status != 'Cancelled'` AND `end_date >= today`.
- `scope=archive`: `status == 'Cancelled'` OR `end_date < today`.

### D14 — Media Uploads
- Avatars and trip covers validated via Pillow; accept JPEG, PNG, WebP only; max 2 MB.
- Re-encode to `.webp`, stripping EXIF.
- Save to `UPLOAD_DIR/{avatars|covers}/{uuid}.webp`.
- Serve using `GET /media/<path:filename>`.

## 3. Critical Concurrency, State Machine & Security Rules

### Route protection
- Every route must use `@login_required` or `@internal_only`, unless explicitly public:
  - `GET /health`
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `GET /api/v1/discover/destinations`
- **No enumeration:** accessing another user's trip or child resource returns `404 not_found`, never `403`.
- Unknown-email login must still execute a dummy `bcrypt` check before returning `401`.
- Store `user_id` and `session_nonce` in Flask signed `HttpOnly`, `SameSite=Lax` cookie.
- Rotate `session_nonce` on password change to invalidate other sessions.

### Atomic generation claim (F5)
1. Execute atomic SQL update:
   ```sql
   UPDATE trips
   SET status='Processing', generation_id=:gid,
       processing_started_at=now(), error_message=NULL,
       itinerary_stale=false
   WHERE id=:id AND user_id=:uid
     AND status IN ('Draft','Completed','Failed')
   RETURNING id;
   ```
2. If zero rows updated: return `404` if not owned; return `409 conflict` if `Processing` or `Cancelled`.
3. Commit **before** calling `n8n_client.trigger()`.
4. POST to `N8N_TRIP_WEBHOOK_URL` with `X-Webhook-Secret`, 10-second timeout, and one retry on connection error only. **Never retry on timeout.**
5. On trigger failure, use a new transaction to mark `status='Failed'`, then return `502 upstream_error`.

### Idempotent callback (F6)
1. Verify `X-Webhook-Secret` using `hmac.compare_digest`; return `401` on failure and audit-log it.
2. Lock trip row using `SELECT ... FOR UPDATE`.
3. If `Cancelled`, status is not `Processing`, or `generation_id` mismatches, return `200` with `{"ignored": true, "reason": "..."}`.
4. On successful callback, validate itinerary rows (drop invalid activities; fail if zero valid remain). In **one transaction**, replace itineraries, `trip_days`, unconfirmed non-booking expenses, and `source='generated'` trip stops, while preserving confirmed/booking expenses and user-created stops.

### Stuck sweeper (F7 & F18)
- Any trip in `Processing` with `processing_started_at < now() - interval '10 minutes'` transitions to `Failed` with error message `Generation timed out. Please retry.`
- Run this on `GET /trips/{id}/status` and `POST /internal/sweep-stuck`.

### Error envelope
All errors use:
```json
{
  "error": {
    "code": "<snake_case_code>",
    "message": "<human_message>",
    "details": {}
  }
}
```

## 4. Required Directory Structure
Create/maintain this layout under `travelmate/`:

```text
travelmate/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
├── README.md
├── docs/
│   ├── api-contract.md
│   ├── openapi.yaml
│   └── postman/travelmate.postman_collection.json
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh
    ├── requirements.txt
    ├── pytest.ini
    ├── wsgi.py
    ├── config.py
    ├── migrations/
    │   └── 0001_initial_schema.py
    ├── seed/
    │   ├── discover_destinations.json
    │   └── default_packing.json
    └── app/
        ├── __init__.py
        ├── extensions.py
        ├── cli.py
        ├── models/
        │   ├── user.py
        │   ├── trip.py
        │   ├── trip_stop.py
        │   ├── trip_day.py
        │   ├── itinerary.py
        │   ├── booking.py
        │   ├── expense.py
        │   ├── packing.py
        │   ├── notification.py
        │   ├── discover.py
        │   ├── audit.py
        │   └── __init__.py
        ├── schemas/
        │   └── domain-specific validators and serializers
        ├── blueprints/
        │   ├── auth.py
        │   ├── trips.py
        │   ├── overview.py
        │   ├── itinerary.py
        │   ├── expenses.py
        │   ├── bookings.py
        │   ├── packing.py
        │   ├── notifications.py
        │   ├── dashboard.py
        │   ├── discover.py
        │   ├── internal.py
        │   ├── media.py
        │   └── health.py
        ├── services/
        │   ├── auth_service.py
        │   ├── trip_service.py
        │   ├── generation_service.py
        │   ├── callback_service.py
        │   ├── n8n_client.py
        │   ├── budget.py
        │   ├── overview_service.py
        │   ├── booking_sync.py
        │   ├── booking_links.py
        │   ├── weather.py
        │   ├── notification_service.py
        │   ├── reminder_queries.py
        │   ├── upload_service.py
        │   ├── packing_seed.py
        │   └── audit.py
        ├── middleware/
        │   ├── request_id.py
        │   ├── origin_check.py
        │   └── request_logging.py
        ├── utils/
        │   ├── errors.py
        │   ├── auth.py
        │   ├── internal_auth.py
        │   ├── validators.py
        │   ├── money.py
        │   ├── dates.py
        │   └── pagination.py
        └── tests/
            ├── conftest.py
            ├── factories.py
            └── comprehensive test_*.py files covering every feature and rule
```


## 5. Implementation & Quality Rules
- Inspect the repository and current state before changing files. Do not restart, overwrite, or scaffold over existing work without verifying it is needed.
- Follow the exact architecture and directory structure above; explain deviations before introducing them.
- Use database migrations for schema changes; avoid silently relying on `create_all()` for production schema.
- Services own business logic, transaction boundaries, commit, and rollback. Blueprints only parse request data, invoke services, and shape HTTP responses.
- Schemas validate inputs and serialize outputs; model classes are persistence-focused.
- Use parameterized SQL/ORM operations. Never interpolate untrusted values into SQL.
- Protect ownership at query level; child-resource queries must scope through the owning user/trip.
- Keep external API/network calls outside DB transactions whenever practical.
- Add tests for success, validation, authorization, conflicts, concurrency/idempotency, and failure paths.
- Do not mark a task complete merely because code was written. Run relevant tests, report commands/results, and clearly disclose unverified items.
- Avoid unnecessary dependencies; update `requirements.txt` intentionally.
- Keep secrets out of source, logs, fixtures, and committed files. `.env` must not be committed.

## 6. Continuation Protocol for Coding Agents

At the start of each session:
1. Read this `AGENTS.md` fully.
2. Inspect git status, repository tree, existing files, recent commits (if available), and test setup.
3. Determine what is already implemented and what is incomplete; do not assume the repo is empty.
4. Identify the next highest-priority incomplete requirement and its dependencies.
5. Make a small, coherent implementation batch that fits existing conventions.
6. Run tests (at minimum the focused tests; run the full suite when practical), lint/type checks if configured, and inspect the diff.
7. Update docs/checklists if implementation status changes.
8. Summarize: what was already there, what you changed, files touched, tests/commands and results, remaining blockers, and the exact next step.

## 7. Definition of Done
A feature is done only when:
- It matches this specification and the API contract.
- Validation, authorization, error handling, and transaction behavior are implemented.
- Tests cover normal and important edge/error cases.
- Tests have actually been run and results recorded.
- Documentation is updated where appropriate.
- No unrelated or accidental changes remain in the diff.

## 8. Agent Continuation Prompt
Use the following prompt to continue implementation in an existing repository:


> You are the TravelMate backend engineering agent. Treat `AGENTS.md` as the source of truth and follow all D1–D14 decisions, architecture rules, security requirements, concurrency/idempotency behavior, and directory structure. **Do not restart or rewrite the project.** First inspect the current repository, git status, files, recent history, and tests. Build an evidence-based checklist of completed, partial, missing, and broken requirements. Then select the highest-priority incomplete task whose dependencies are satisfied and implement it in a focused batch. Keep Blueprints thin; Services own business logic and transaction boundaries; Models contain no serializers; Schemas handle validation/serialization. Add or update tests and run them. Inspect your final diff for regressions and unrelated changes. Continue working—not just planning—until a meaningful batch is complete or you hit a concrete blocker. In your final response, report existing state, implementation performed, files changed, tests and exact results, blockers, and the next recommended task. Never claim tests passed unless you ran them.

