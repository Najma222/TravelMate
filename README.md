# TravelMate

TravelMate is an AI-assisted trip planner. You enter where you're going, your dates and
your budget; TravelMate generates a day-by-day itinerary (via an n8n workflow), tracks
expenses against your budget, keeps bookings and a packing list, shows the weather forecast
and sends trip reminders.

| Part | Tech | Folder |
|---|---|---|
| Frontend | HTML, CSS, vanilla JavaScript | `frontend/` |
| Backend API | Python 3.12, Flask, SQLAlchemy, Alembic, Gunicorn | `backend/` |
| Database | PostgreSQL 16 | Docker service `db` |
| Automation | n8n (itinerary generation, weather, reminders) | Docker service `n8n` |

---

## Installation guide

### 1. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| [Git](https://git-scm.com/downloads) | any recent | cloning the repo |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose v2) | Compose v2.20+ | running database, backend and n8n |
| [Python](https://www.python.org/downloads/) | 3.12 | serving the frontend locally, running backend tests |

Check them:

```bash
git --version
docker --version && docker compose version
python --version
```

### 2. Clone the repository

```bash
git clone https://github.com/Najma222/TravelMate.git
cd TravelMate
```

### 3. Create your `.env` file

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and replace **every** placeholder. Generate strong random values with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

| Variable | What to put |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | database credentials (any values; the password should be strong) |
| `FLASK_SECRET_KEY` | random string, at least 32 characters |
| `INTERNAL_WEBHOOK_SECRET` | random string shared by the backend and n8n |
| `N8N_ENCRYPTION_KEY` | random string |
| `ALLOWED_ORIGINS` | the address you serve the frontend from, e.g. `http://localhost:8080` (comma-separate several) |
| `SESSION_COOKIE_SECURE` | `false` for local `http://` use; `true` in production behind HTTPS |
| `GEOAPIFY_API_KEY`, `GEMINI_API_KEY`, `ORS_API_KEY` | API keys used by the n8n workflows (optional until you build them) |

> `.env` holds secrets and is git-ignored. Never commit it.

### 4. Start the backend stack

```bash
docker compose up --build -d
```

The first run downloads images and builds the backend (a few minutes). On every start the
backend waits for PostgreSQL, applies database migrations, loads the destination catalogue
and starts Gunicorn.

Check that everything is up:

```bash
docker compose ps                       # db, backend and n8n should be "healthy"
curl http://localhost:5000/health       # {"status":"ok","database":"ok"}
```

| Service | URL |
|---|---|
| Backend API | http://localhost:5000 |
| n8n editor | http://localhost:5678 |
| PostgreSQL | internal to Docker only (not published) |

Optional — create a demo account with two sample trips (development only):

```bash
docker compose exec -e APP_ENV=development backend flask seed-demo
# login: demo@travelmate.local / DemoPass123
```

### 5. Run the frontend

The frontend is static files; serve them with any HTTP server (don't open them with `file://`):

```bash
cd frontend
python -m http.server 8080
```

Open http://localhost:8080/login.html.

**Mock mode vs. real backend.** Out of the box the frontend runs on built-in sample data
(`MOCK:true` in `frontend/assets/js/api.js`), so you can click through every page without
the backend. To use the real API, edit the first lines of `frontend/assets/js/api.js`:

```js
const API={MOCK:false,BASE:'http://localhost:5000/api/v1'};
```

and make sure that:

* `ALLOWED_ORIGINS` in `.env` contains `http://localhost:8080` (restart with `docker compose up -d` after editing `.env`);
* `SESSION_COOKIE_SECURE=false` for local `http://` testing, otherwise the browser won't keep the login cookie.

The backend's endpoints, request bodies and responses are documented in
`docs/api-contract.md`. Pages that still use mock-only data shapes may need small
adjustments to match that contract.

### 6. Set up n8n (itinerary generation)

Until an n8n workflow exists, pressing **Generate itinerary** returns an "Itinerary service
is unavailable" error and the trip is marked *Failed* — that is expected.

1. Open http://localhost:5678 and create the n8n owner account.
2. Build or import a workflow with a **Webhook** trigger at `POST /webhook/trip-generate`.
3. Have it check the `X-Webhook-Secret` header against `INTERNAL_WEBHOOK_SECRET`, generate
   the itinerary, then `POST` the result to the `callback_url` it received, with the same header.

The full payload contract is in `docs/integration-decisions.md`.

### 7. Stopping, logs and resetting

```bash
docker compose logs -f backend      # follow backend logs
docker compose down                 # stop (data is kept)
docker compose down -v              # stop AND delete all data (database, uploads, n8n)
```

---

## Running the backend tests

Tests use a real PostgreSQL 16 in a throwaway container:

```bash
docker run -d --name travelmate-test-db -e POSTGRES_USER=travelmate -e POSTGRES_PASSWORD=travelmate \
  -e POSTGRES_DB=travelmate_test -p 55432:5432 postgres:16

cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

Remove the test database afterwards with `docker rm -f travelmate-test-db`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `set FLASK_SECRET_KEY in .env` (or similar) on `docker compose up` | `.env` is missing or a required value is empty — see step 3. |
| `403 forbidden` from the API | The page's origin isn't in `ALLOWED_ORIGINS`, or the request lacks `Content-Type: application/json`. |
| Logged in, but the next request is `401` | Use `SESSION_COOKIE_SECURE=false` for plain-HTTP local runs. |
| Port 5000 or 5678 already in use | Set `BACKEND_PORT` / `N8N_PORT` in `.env` (e.g. `BACKEND_PORT=5050`). |
| Backend container keeps restarting | `docker compose logs backend` — usually a missing env value or the database not ready. |

## Project structure

```
TravelMate/
├── frontend/              HTML pages, assets/css, assets/js (api.js = API helper)
├── backend/
│   ├── app/               Flask app: blueprints, services, schemas, models, middleware
│   ├── migrations/        Alembic database migrations
│   ├── seed/              destination catalogue + default packing list
│   ├── tests/             pytest suite
│   ├── Dockerfile, entrypoint.sh, requirements*.txt
├── docs/                  API contract, OpenAPI spec, Postman collection, integration notes
├── docker-compose.yml     db + backend + n8n
├── .env.example           configuration template
└── AGENTS.md              backend engineering rules
```

## Documentation

* `docs/api-contract.md` — every endpoint, request and response
* `docs/openapi.yaml` — OpenAPI 3.0 spec
* `docs/postman/travelmate.postman_collection.json` — Postman collection
* `docs/integration-decisions.md` — design decisions and the n8n contract
* `docs/integration-checklist.md` — frontend / n8n / deployment checklist

## Credits

* **Frontend** — pages and UI initially developed by [@nezza983](https://github.com/nezza983);
  reorganised and integrated by [@Najma222](https://github.com/Najma222).
* **Backend, infrastructure and documentation** — [@Najma222](https://github.com/Najma222).
