# Integration Decisions

Decisions taken while implementing the backend, where `AGENTS.md` was silent or needed
interpretation. None of them override a D1–D14 rule.

| # | Topic | Decision | Why |
|---|---|---|---|
| I1 | Repository layout | The repository root is the "travelmate/" project root. | The repo already had `backend/`, `docs/`, `docker-compose.yml`. |
| I2 | Validation library | Small in-house validator (`app/utils/validators.py`) used by `app/schemas/*`; no marshmallow/pydantic. | Not in the approved stack (§1); keeps schemas pure. |
| I3 | Money on the wire | Responses: 2-dp strings. Requests: JSON numbers or strings, parsed with `parse_float=Decimal`. | "never float" (§1). |
| I4 | Logout | Rotates `session_nonce` → logs out **all** of the user's sessions. | Signed-cookie sessions cannot be revoked individually; the master prompt requires logout to invalidate the nonce. |
| I5 | Failed-login limit storage | Counted from `audit_logs` (`login_failed` rows keyed by SHA-256 of the normalised email), not in memory. | Survives restarts; no raw email stored in audit meta. |
| I6 | IP rate limit storage | Flask-Limiter `memory://` (one Gunicorn worker per D2). Set `RATELIMIT_STORAGE_URI` (e.g. Redis) if workers are ever increased. | |
| I7 | D12 on bodyless requests | `Content-Type: application/json` is required on **every** user `POST/PUT/DELETE`, even without a body (strict reading of D12). | The frontend fetch wrapper must always set it. |
| I8 | Audit writes | Written on a separate connection (autonomous transaction). | Audit rows persist when business transactions roll back, and never commit caller work. |
| I9 | Callback `generation_id` missing/invalid | `400` without changing trip state. | Cannot be attributed to the current generation. A *mismatched* id is `200 ignored stale_generation` (D5). |
| I10 | Callback row handling | Invalid activity/expense/day/stop rows are dropped, never repaired; over-long text is truncated to column limits. | "Never invent places". |
| I11 | Callback replacement of expenses | All `is_confirmed=false AND booking_id IS NULL` expenses are replaced, including user-entered estimates. | Literal §3 rule. |
| I12 | Generated stops | Appended after user stops (positions renumbered 1..n). Editing a generated stop converts it to `source:"user"`. | User edits must survive regeneration. |
| I13 | `trip_days` on callback | A row is written for every day 1..N; missing titles default to `Day N`. | D7. |
| I14 | Auto-jacket | Evaluated in the same transaction as the callback, from stored forecast lows; item name `Warm jacket`. Existing items matching `%jacket%` (case-insensitive) suppress it. | D11. |
| I15 | Weather PUT | Replaces the forecast; a payload without `current`/`daily` clears it (so stale data is not shown). | D6 "never fabricate". |
| I16 | Notification retry | Existing `failed` **or `pending`** row → updated (`200`); `sent` → `409`. | D9 covers failed/sent; pending must be updatable for claim-then-send flows. Exactly-once *delivery* is not guaranteed (n8n may send then crash before recording). |
| I17 | Trip length | Max 60 days. | Keeps itinerary within the 200-row callback cap. |
| I18 | Duplicate trip submission | Same user + origin + destination + dates within 10 s → `409 duplicate_submission`; serialised with a per-user advisory lock. | Double-click protection. |
| I19 | Preferences enums | `transport_preference`: any/flight/train/bus/car; `accommodation_preference`: any/hotel/hostel/homestay/resort (schema-validated; no DB CHECK). | Spec gives only the column and default. |
| I20 | Account deletion | `DELETE /auth/me` requires the password. | Destructive action. |
| I21 | Booking links | Booking.com and Google Flights links are pre-filled; IRCTC and redBus link to their search pages (`prefilled:false`). | No stable public deep-link format for those two. |
| I22 | Booking-sync category | Recomputed on every sync (changing `booking_type` hotel ↔ flight moves the expense category). | D10. |
| I23 | Stuck sweeper | Single conditional `UPDATE … WHERE status='Processing' AND processing_started_at < now()-10min RETURNING`. | Concurrency-safe without locks. |

## n8n workflow contract (to implement in n8n)

1. **Trigger** — Webhook node at `POST /webhook/trip-generate` (matches `N8N_TRIP_WEBHOOK_URL`). Verify `X-Webhook-Secret` equals `INTERNAL_WEBHOOK_SECRET`; respond `2xx` quickly (Respond immediately), then work asynchronously. Received fields: `trip_id, generation_id, callback_url, weather_url, origin, destination, start_date, end_date, duration_days, traveller_count, budget (string), currency, preferences, transport_preference, accommodation_preference, latitude, longitude, user_stops[]`.
2. **Callback** — `POST {callback_url}` with header `X-Webhook-Secret` and the payload in `docs/api-contract.md` (echo `generation_id`). Use only real data from providers; never invent prices, weather or places.
3. **Weather refresh** — `PUT {weather_url}` (e.g. daily cron over `GET /internal/active-trips`).
4. **Reminders** — cron: `GET /internal/upcoming-trips` / `booking-gaps`, send via email/Telegram according to user prefs, then `POST /internal/notifications` with `delivery_status` `sent` or `failed`. On `409` do not resend.
5. **Sweeper** — optional cron `POST /internal/sweep-stuck` every 5 minutes.
