# TravelMate API and n8n Contracts

**Status:** Draft for review. Person 1 and Person 2 must approve this contract before workflow implementation begins.

## Shared rules

- Exchange JSON using `Content-Type: application/json`.
- The Flask-to-n8n trip webhook and all n8n-to-Flask internal endpoints use the `X-Webhook-Secret` header with the shared `INTERNAL_WEBHOOK_SECRET` value. Never put the secret in a request body or URL.
- Use Docker service names for service-to-service calls: n8n calls `http://backend:5000`; Flask calls the URL in `N8N_TRIP_WEBHOOK_URL` (normally `http://n8n:5678/webhook/trip-generate`). Do not use `localhost` between containers.
- Trip generation statuses are exactly `Processing`, `Completed`, and `Failed`.
- Dates use `YYYY-MM-DD`; itinerary times use 24-hour `HH:MM` in `Asia/Kolkata`. Currency amounts are INR numbers. Latitude and longitude are decimal degrees.
- A callback's path trip ID must match its body `trip_id`.

## Trip generation

### Frontend to Flask

`POST /api/trips/{id}/generate` starts generation for an existing trip. Flask sets its status to `Processing`, calls the configured n8n webhook, and returns promptly so the frontend can poll the status endpoint. A repeated request while generation is already processing must not start a second run; Person 1 should confirm the exact response code and body for that case.

### Flask to n8n

`POST ${N8N_TRIP_WEBHOOK_URL}`

Header: `X-Webhook-Secret: <shared secret>`

Example body:

```json
{
  "trip_id": 12,
  "origin": "Pune",
  "destination": "Goa",
  "start_date": "2026-12-20",
  "end_date": "2026-12-22",
  "traveller_count": 2,
  "budget": 15000,
  "preferences": "beaches, food, budget",
  "transport": "train",
  "accommodation": "hostel"
}
```

n8n should acknowledge the webhook immediately and continue processing asynchronously. The request uses the active webhook URL; use the `webhook-test` URL only during manual workflow testing.

## n8n result callback

`POST /api/internal/trips/{id}/result`

Header: `X-Webhook-Secret: <shared secret>`

On success, Flask saves the itinerary and expenses, clears `error_message`, and changes the trip status to `Completed`.

```json
{
  "trip_id": 12,
  "status": "Completed",
  "error_message": null,
  "itinerary": [
    {
      "day_number": 1,
      "activity_name": "Fort Aguada",
      "description": "Morning visit to the fort",
      "location": "Candolim, Goa",
      "start_time": "09:00",
      "end_time": "11:00",
      "estimated_cost": 0,
      "latitude": 15.49,
      "longitude": 73.77
    }
  ],
  "expenses": [
    {
      "category": "Food",
      "description": "Estimate",
      "amount": 3000,
      "is_confirmed": false
    }
  ]
}
```

On failure, n8n calls the same callback with `status` set to `Failed` and a useful, non-empty `error_message`. Flask stores the error and exposes it through the status endpoint. No itinerary or expense rows should be saved from a failed result.

```json
{
  "trip_id": 12,
  "status": "Failed",
  "error_message": "No valid places found",
  "itinerary": [],
  "expenses": []
}
```

## Frontend polling

`GET /api/trips/{id}/status` returns the current status and error, if any. Suggested response shape:

```json
{
  "trip_id": 12,
  "status": "Processing",
  "error_message": null
}
```

When status is `Completed`, the frontend can load `GET /api/trips/{id}/itinerary` and `GET /api/trips/{id}/expenses`. When status is `Failed`, show `error_message` and offer retry.

## Internal endpoints for n8n

All of these routes require the same `X-Webhook-Secret` header. Missing or invalid secrets must be rejected. Requests and responses use JSON.

| Method and path | Purpose and contract |
| --- | --- |
| `POST /api/internal/trips/{id}/result` | Save a completed or failed generation result as specified above. |
| `GET /api/internal/upcoming-trips?days=7,2` | Return trips due for reminders only, including the trip/user identifiers, destination and dates, user email and notification preferences, and reminder type (`7_day` or `2_day`). Exclude reminders already recorded. |
| `POST /api/internal/notifications` | Record an attempted notification, including trip/user IDs, type, message, scheduled time, sent time, and delivery status (`sent` or `failed`). |

### Notification duplicate protection

Flask owns de-duplication. Add a database unique constraint on `(trip_id, notification_type, scheduled_at)`, where `scheduled_at` identifies the reminder occurrence (stored in a consistent timezone, preferably UTC). On a duplicate insert, return HTTP `409 Conflict`; n8n treats that response as “already recorded” and does not send a second notification. `sent_at` records the actual delivery attempt time and is not the idempotency key.

To avoid a send/log race, the workflow should check the upcoming-trips response before sending, then record the notification. Person 1 must confirm whether the notification row is written before or after external delivery and how a failed delivery is retried without duplicating a successful send.

## Related API surface from the PRD

These routes are part of the wider Flask API contract. User-facing routes require the user's normal authentication and ownership checks; the internal routes above use the shared secret.

| Area | Method and path |
| --- | --- |
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout` |
| Trips | `POST /api/trips`, `GET /api/trips`, `GET /api/trips/{id}`, `PUT /api/trips/{id}`, `DELETE /api/trips/{id}` |
| Generation | `POST /api/trips/{id}/generate`, `GET /api/trips/{id}/status` |
| Itinerary | `GET /api/trips/{id}/itinerary`, `PUT /api/itinerary/{id}` |
| Places and weather | `GET /api/trips/{id}/places`, `GET /api/trips/{id}/weather` |
| Bookings | `POST /api/trips/{id}/bookings`, `GET /api/trips/{id}/bookings`, `PUT /api/bookings/{id}` |
| Expenses | `POST /api/trips/{id}/expenses`, `GET /api/trips/{id}/expenses` |
| Notifications | `GET /api/notifications`, `PUT /api/notifications/preferences` |

## Approval checklist

- [ ] Person 1 approves the Flask routes, request/response fields, status values, and database behavior.
- [ ] Person 2 approves the polling/status and result fields needed by the frontend.
- [ ] Person 3 has reviewed the webhook URL, authentication header, notification contract, and retry/de-duplication behavior.

Resolve the notification delivery/retry question above with Person 1 before building reminder workflows. Update this document if the team agrees on any different field, route, status, or response code.
