# TravelMate API Contract (v1)

Implementation: `backend/app`. Machine-readable spec: `docs/openapi.yaml`.
Architecture rules and decisions D1–D14: `AGENTS.md`. Integration notes: `docs/integration-decisions.md`.

## Conventions

| Topic | Rule |
|---|---|
| Base path | Everything under `/api/v1`, except `GET /health` and `GET /media/<path>` (D1). |
| Auth | Signed cookie `tm_session` (HttpOnly, SameSite=Lax, Secure in production, 7 days). Holds `uid` + `nonce`; the nonce must match `users.session_nonce`. |
| CSRF (D12) | `POST`/`PUT`/`DELETE` on `/api/v1/**` (not `/api/v1/internal/**`) need an `Origin` (or `Referer`) in `ALLOWED_ORIGINS` **and** `Content-Type: application/json` — also for bodyless requests such as `POST /trips/{id}/generate` or `DELETE /stops/{id}`. Only `POST /auth/avatar` and `POST /trips/{id}/cover` accept `multipart/form-data`. Violations → `403 forbidden` with `details.reason` ∈ `origin_missing`, `origin_not_allowed`, `referer_not_allowed`, `content_type_not_allowed`. |
| Internal auth | `/api/v1/internal/**` require header `X-Webhook-Secret` (compared with `hmac.compare_digest`) → `401 unauthorized` + audit row on failure. |
| Money | Strings with exactly 2 decimals (`"12345.50"`). Requests may send JSON numbers or strings; they are parsed as `Decimal` (never float). More than 2 decimals → `400`. |
| Percentages / coordinates / temperatures | JSON numbers. |
| Dates | `YYYY-MM-DD`. Timestamps: ISO-8601 with offset. Business dates (phase, scopes, `scheduled_for`, "today") use `APP_TIMEZONE=Asia/Kolkata`. |
| Ownership | Another user's trip or child record → `404 not_found` (never 403). |
| Pagination | `?page=1&per_page=20` (max 100) → `{"items": [...], "pagination": {"page","per_page","total","pages"}}`. |
| Request id | Every response carries `X-Request-ID` (echoes a safe client value or generates a UUID). |

### Error envelope

```json
{"error": {"code": "validation_error", "message": "Request validation failed",
           "details": {"fields": {"budget": "must be greater than 0"}}}}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `validation_error` | Invalid body/query, malformed JSON. `details.fields` maps field → message. |
| 401 | `unauthorized` / `invalid_credentials` | No/expired session, bad webhook secret / wrong login. |
| 403 | `forbidden` | D12 origin / content-type rejection. |
| 404 | `not_found` | Missing or not owned. |
| 405 | `method_not_allowed` | |
| 409 | `conflict` / `duplicate_submission` | State conflicts (see each route). |
| 413 | `payload_too_large` | Upload > 2 MB. |
| 415 | `unsupported_media_type` | Upload not JPEG/PNG/WebP or not decodable. |
| 429 | `rate_limited` | Rate limits; includes `Retry-After`. |
| 500 | `internal_error` | Unexpected error (no stack traces or SQL are returned). |
| 502 | `upstream_error` | n8n could not be reached / rejected the request. |
| 503 | — | `GET /health` when the database is unavailable (`{"status":"degraded"}`). |

## Trip status lifecycle

```
            POST /generate (atomic claim)            callback Completed
 Draft ───────────────────────────────▶ Processing ───────────────────▶ Completed
   ▲  Failed/Completed ── /generate ──▶     │  callback Failed / invalid payload /
   │                                        │  0 valid activities / n8n unreachable /
   │                                        └─ sweeper (>10 min) ─────▶ Failed
 any non-Cancelled ── POST /cancel ──▶ Cancelled (terminal; callbacks ignored)
```

`phase` (`upcoming`/`ongoing`/`past`), `ring_percent` and `days_until_start` are computed on every read (D13), never stored.

---

## Public

### `GET /health`
`200 {"status":"ok","database":"ok"}` · `503 {"status":"degraded","database":"unavailable"}`

### `GET /media/<path:filename>`
Serves `avatars/{uuid}.webp` or `covers/{uuid}.webp` only (anything else, including traversal attempts → `404`). `Content-Type: image/webp`, `X-Content-Type-Options: nosniff`, cached 1 day.

### `GET /api/v1/discover/destinations`
Query: `q` (name/description/region contains), `country`, `region` (case-insensitive exact), `tag`, `page`, `per_page`.
`200` paginated items: `{id, name, country, region, description, best_season, latitude, longitude, image_url, tags[]}`.

## Auth — `/api/v1/auth`

| Route | Body | Success | Errors |
|---|---|---|---|
| `POST /register` *(public, 10/min/IP)* | `{name (1–80), email, password}` | `201 {"user"}` + session cookie | 400, 409 (email taken), 429 |
| `POST /login` *(public, 10/min/IP + 5 failures/15 min per email)* | `{email, password}` | `200 {"user"}` + cookie | 401 `invalid_credentials`, 429 + `Retry-After` |
| `POST /logout` | — | `200 {"logged_out":true}`; rotates nonce → **all** sessions of the user end | 401 |
| `GET /me` | — | `200 {"user"}` | 401 |
| `PUT /profile` | `{name?, ui_prefs? (object ≤ 4 KB)}` | `200 {"user"}` | 400 |
| `POST /avatar` *(multipart, field `file`)* | image | `200 {"user","upload":{"kind","url","content_type"}}` | 400, 413, 415 |
| `POST /change-password` | `{current_password, new_password}` | `200`; rotates nonce (other sessions end, this one is re-issued) | 400 |
| `DELETE /me` | `{password}` | `200 {"deleted":true}`; cascades all data | 400 |

Password: 8+ chars, ≤ 72 bytes, at least one letter and one digit, no leading/trailing whitespace. Emails are trimmed and lower-cased. Unknown emails run a dummy bcrypt check (no enumeration).

`user` = `{id, name, email, role, avatar_url, notify_email, notify_telegram, telegram_chat_id, ui_prefs, created_at, updated_at}`.

## Trips — `/api/v1`

### `POST /trips`
Body:

| Field | Rule |
|---|---|
| `origin`, `destination` | required, 1–100 chars |
| `start_date`, `end_date` | required; `start_date ≥ today`; `end_date ≥ start_date`; ≤ 60 days |
| `traveller_count` | 1–50, default 1 |
| `budget` | required, > 0, 2 dp |
| `currency` | `INR` (default), `USD`, `EUR`, `GBP`, `NPR`, `BDT`, `AED` (display only) |
| `preferences` | ≤ 500 |
| `transport_preference` | `any` (default), `flight`, `train`, `bus`, `car` |
| `accommodation_preference` | `any` (default), `hotel`, `hostel`, `homestay`, `resort` |
| `latitude`/`longitude`, `hero_quote` (≤200), `hero_quote_author` (≤80) | optional |

`201 {"trip"}`. Default packing items are seeded (D11). Same origin/destination/dates by the same user within 10 s → `409 duplicate_submission` (`details.existing_trip_id`).

`trip` = `{id, origin, destination, start_date, end_date, duration_days, traveller_count, budget, currency, preferences, transport_preference, accommodation_preference, status, error_message, itinerary_stale, latitude, longitude, cover_image_url, hero_quote, hero_quote_author, phase, ring_percent, days_until_start, created_at, updated_at}`.

### `GET /trips?scope=upcoming|archive|all&page&per_page`
`upcoming`: `status ≠ Cancelled AND end_date ≥ today` (ordered by start date). `archive`: `Cancelled OR end_date < today` (latest first). `all` (default): newest first. Response adds `"scope"`.

### `GET /trips/{id}` → `200 {"trip"}`
### `PUT /trips/{id}`
Partial update, same rules (start date may not move into the past). `409` while `Processing` or when `Cancelled`. Changing a generation input on a `Completed` trip sets `itinerary_stale=true`.
### `DELETE /trips/{id}` → `200 {"deleted":true,"id"}` (cascades; cover file deleted)
### `POST /trips/{id}/cancel` → `200 {"trip"}`; `409` if already cancelled.

### `POST /trips/{id}/generate`
`202 {"trip": {id, status:"Processing", error_message, generation_id, processing_started_at, itinerary_stale, updated_at}}`.
`404` not owned · `409` when `Processing` or `Cancelled` (`details.status`) · `502 upstream_error` when n8n fails (trip becomes `Failed`).

### `GET /trips/{id}/status`
Same `trip` status shape. If the trip has been `Processing` > `GENERATION_TIMEOUT_MINUTES` (10) it is atomically moved to `Failed` with `"Generation timed out. Please retry."` first.

### `POST /trips/{id}/cover` *(multipart `file`)* → `200 {"trip","upload"}`
### `GET /trips/{id}/weather` → `200 {"trip_id","weather"}`
Available: `{available:true, location_name, current:{temperature_c, weather_code, condition, observed_at}|null, daily:[{date, high_c, low_c, precip_prob_max, weather_code, condition}], message, updated_at}` (`high_c ≥ low_c` guaranteed).
Unavailable: `{available:false, daily:[], message: weather_message || "Forecast not available yet"}`. Weather is never fabricated.

### `GET /trips/{id}/places`
`{trip_id, destination:{name,latitude,longitude}, stops:[stop], places:[{itinerary_id, day_number, name, location, latitude, longitude}]}` — only stored stops/itinerary rows with a location or coordinates.

### Stops
| Route | Body | Success |
|---|---|---|
| `POST /trips/{id}/stops` | `{name, latitude?, longitude?}` | `201 {"stop"}` appended at the end (max 50) |
| `PUT /stops/{id}` | partial | `200 {"stop"}`; an edited stop becomes `source:"user"` (survives regeneration) |
| `DELETE /stops/{id}` | — | `200`; remaining positions compacted |
| `PUT /trips/{id}/stops/order` | `{stop_ids:[...]}` exact permutation | `200 {"stops"}` |

`stop` = `{id, trip_id, position, name, latitude, longitude, source}`.

## Overview & dashboard
### `GET /trips/{id}/overview`
≤ 8 SQL queries (including the session lookup). Returns `{trip, weather, budget, stops, itinerary:{total_activities, focus_day, focus_items, days:[day + activity_count]}, bookings:{items, status_counts}, packing:{total, packed, percent}}`.
Sends a weak `ETag`; `If-None-Match` with the same tag → `304` (empty body).

### `GET /dashboard`
`{user:{id,name,avatar_url}, counts:{upcoming, ongoing, past, cancelled, total}, next_trip, upcoming_trips[≤5], recent_trips[≤5], notifications:{unread_count, recent[≤5]}, pending_bookings}`; trip cards include `budget_summary:{forecast_total, confirmed_total, remaining, exceeded, spent_percent}`.

## Itinerary
| Route | Body | Success / errors |
|---|---|---|
| `GET /trips/{id}/itinerary` | — | `{trip_id, status, itinerary_stale, days:[{day_number, date, title, summary, stop, items:[item]}]}` — one entry per trip day; title defaults to `Day N`; `date` computed (D7) |
| `POST /trips/{id}/itinerary` | `{day_number, activity_name, description?, location?, start_time? "HH:MM", end_time?, estimated_cost?, latitude?, longitude?, sort_order?}` | `201 {"item"}`; `400` day outside trip / end before start; `409` while Processing |
| `PUT /itinerary/{id}` | partial | `200 {"item"}`, sets `is_edited` |
| `DELETE /itinerary/{id}` | — | `200` |
| `PUT /trips/{id}/days/{day_number}` | `{title?, summary?, stop_id?}` | `200 {"day"}` |

`item` = `{id, trip_id, day_number, activity_name, description, location, start_time, end_time, estimated_cost, latitude, longitude, is_edited, sort_order, created_at, updated_at}`.

## Expenses & budget
| Route | Body | Success / errors |
|---|---|---|
| `GET /trips/{id}/expenses?category=` | — | `{trip_id, currency, items:[expense]}` |
| `POST /trips/{id}/expenses` | `{category, amount > 0, description?, is_confirmed? (false), expense_date? (today)}` | `201 {"expense"}` |
| `PUT /expenses/{id}` | partial | `200`; `409` if booking-linked |
| `DELETE /expenses/{id}` | — | `200`; `409` if booking-linked |
| `GET /trips/{id}/budget` | — | `{trip_id, budget:{currency, budget, confirmed_total, estimated_total, forecast_total, remaining, exceeded, exceeded_by, spent_percent, remaining_percent, forecast_percent, categories:[{category, confirmed, estimated, effective, basis}]}}` (D3) |

Categories: `transport, accommodation, food, activities, local_transport, misc` (user input is matched case-insensitively; unknown → 400).
`expense` = `{id, trip_id, booking_id, category, description, amount, is_confirmed, expense_date, source (user|n8n|booking), locked, created_at, updated_at}`.

## Bookings
| Route | Body | Success |
|---|---|---|
| `GET /trips/{id}/bookings` | — | `{trip_id, currency, items:[booking]}` |
| `POST /trips/{id}/bookings` | `{booking_type (hotel/flight/train/bus), status? ("Not Booked"/"Pending"/"Confirmed"/"Cancelled"), amount? ≥ 0, provider?, booking_reference?, booked_on?, from_location?, to_location?, start_at?, end_at?, start_tz?, end_tz?, notes?}` | `201 {"booking"}` |
| `PUT /bookings/{id}` | partial | `200 {"booking"}` |
| `DELETE /bookings/{id}` | — | `200` (linked expense cascades) |
| `GET /trips/{id}/booking-links` | — | `{trip_id, links:[{booking_type, provider, url, prefilled}], disclaimer}` — search links only; no availability, reservation or payment |

`start_at`/`end_at`: ISO-8601 with offset, or naive + `start_tz`/`end_tz` (IANA) to localise. `end_at ≥ start_at`.
Sync (same transaction): `Confirmed` and `amount > 0` → exactly one linked expense (`is_confirmed`, `source:"booking"`, `accommodation` for hotels else `transport`); otherwise the linked expense is deleted.
`booking` = all columns + `linked_expense_id`.

## Packing
| Route | Body | Success |
|---|---|---|
| `GET /trips/{id}/packing` | — | `{trip_id, total, packed, items:[item]}` |
| `POST /trips/{id}/packing` | `{name (1–100), note?, is_packed?, remind_at?, sort_order?}` | `201 {"item"}` |
| `PUT /packing/{id}` | partial | `200 {"item"}` |
| `DELETE /packing/{id}` | — | `200` |

`remind_at` must include an offset, be in the future and be on/before the trip `end_date` (end of that day in `APP_TIMEZONE`).
`source`: `default` (seeded), `user`, `auto` (jacket rule).

## Notifications
| Route | Body | Success |
|---|---|---|
| `GET /notifications?unread=true|false&page&per_page` | — | paginated `notification` items + `unread_count` |
| `PUT /notifications/{id}/read` | `{}` | `200 {"notification"}` (idempotent) |
| `POST /notifications/read-all` | `{}` | `200 {"marked_read": n}` |
| `GET /notifications/preferences` | — | `{"preferences":{notify_email, notify_telegram, telegram_chat_id}}` |
| `PUT /notifications/preferences` | partial; `telegram_chat_id` numeric or `@username`; enabling Telegram needs a chat id | `200` |

`notification` = `{id, trip_id, notification_type, message, channels[], scheduled_for, sent_at, delivery_status, read_at, is_read, created_at}`.

## Internal (n8n) — `/api/v1/internal`, header `X-Webhook-Secret`

| Route | Purpose |
|---|---|
| `POST /trips/{id}/result` | Generation callback (payload below) |
| `PUT /trips/{id}/weather` | `{location_name?, current?, daily?[≤16], weather_message?}` replaces stored weather; empty payload clears it |
| `GET /upcoming-trips?days=3` | Non-cancelled trips starting in `[today, today+days]` with `user` contact/prefs and `unpacked_items` |
| `GET /active-trips` | Ongoing trips (`day_number`, coordinates, `weather_updated_at`, `user`) |
| `GET /booking-gaps?days=14` | Upcoming trips missing a Confirmed hotel and/or transport (`missing:["hotel","transport"]`) |
| `POST /notifications` | `{trip_id, notification_type (snake_case ≤30), message, channels? [email, telegram, in_app], scheduled_for? (today), delivery_status? (pending), sent_at?}` → `201` new · `200` updated failed/pending row · `409` already `sent` |
| `POST /sweep-stuck` | `{"swept": n, "trip_ids": [...]}` |

### Generation callback payload

```json
{
  "generation_id": "uuid from the trigger",
  "status": "Completed",                        
  "error_message": "only for Failed",
  "itinerary": [{"day_number": 1, "activity_name": "Fort Aguada", "description": "...",
                 "location": "Candolim", "start_time": "09:00", "end_time": "11:00",
                 "estimated_cost": "200.00", "latitude": 15.49, "longitude": 73.77, "sort_order": 0}],
  "days": [{"day_number": 1, "title": "North Goa", "summary": "...", "stop_name": "North Goa"}],
  "expenses": [{"category": "Transportation", "description": "Flights", "amount": "8000.00"}],
  "stops": [{"name": "North Goa", "latitude": 15.6, "longitude": 73.75}],
  "weather": {"location_name": "Goa", "current": {...}, "daily": [...]},
  "latitude": 15.29, "longitude": 74.12, "hero_quote": "...", "hero_quote_author": "..."
}
```

Responses: `200 {"status":"Completed", activities_saved, activities_dropped, expenses_saved, stops_saved, jacket_added}` · `200 {"status":"Failed"}` · `200 {"ignored":true,"reason":"cancelled"|"stale_generation"|"not_processing"}` · `400` invalid envelope (> 200 itinerary rows, > 50 expenses, wrong types → trip `Failed`; missing/invalid `generation_id` → no state change) · `401` · `404`.
