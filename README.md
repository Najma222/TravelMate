# TravelMate

TravelMate is an AI-assisted trip planner. You enter where you're going, your dates and
your budget; TravelMate generates a day-by-day itinerary (via an n8n workflow), tracks
expenses against your budget, keeps bookings and a packing list, shows the weather forecast
and sends trip reminders.

| Part | Tech | Folder |
|---|---|---|
| Frontend | HTML, CSS, vanilla JavaScript, served by nginx | `frontend/` |
| Backend API | Python 3.12, Flask, SQLAlchemy, Alembic, Gunicorn | `backend/` |
| Database | PostgreSQL 16 | Docker service `db` |
| Automation | n8n (itinerary generation, weather, reminders) | Docker service `n8n` |

Everything runs on **one address**: <http://localhost:8080>. The nginx `web` container serves
the pages and proxies `/api` and `/media` to Flask, so the browser never makes a cross-origin
request and the login cookie just works.

```
browser ──► http://localhost:8080 (nginx: web)
              ├── /                static pages (frontend/)
              ├── /api/v1/...      proxy ──► backend:5000 (Flask)
              └── /media/...       proxy ──► backend:5000 (uploads)
backend ──► n8n:5678/webhook/trip-generate
n8n ──► backend:5000/api/v1/internal/... (callback + weather)
```

---

## Installation guide

### 1. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| [Git](https://git-scm.com/downloads) | any recent | cloning the repo |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose v2) | Compose v2.20+ | running the database, backend, web server and n8n |
| [Python](https://www.python.org/downloads/) | 3.12 | running the backend tests (not needed to use the app) |

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
| `ALLOWED_ORIGINS` | the address you open the site from, e.g. `http://localhost:8080` (comma-separate several) |
| `SESSION_COOKIE_SECURE` | `false` for local `http://` use (the default in `.env.example`); `true` in production behind HTTPS |
| `GEMINI_API_KEY` | **required for itinerary generation** — free key from <https://aistudio.google.com/apikey> |
| `GEOAPIFY_API_KEY` | **required for place names/coordinates** — free key from <https://myprojects.geoapify.com> |
| `GEMINI_MODEL` | optional, defaults to `gemini-2.5-flash` |

Weather comes from Open-Meteo and needs no key.

> `.env` holds secrets and is git-ignored. Never commit it.

### 4. Start the whole stack

```bash
docker compose up --build -d
```

The first run downloads images and builds the backend and web containers (a few minutes). On
every start the backend waits for PostgreSQL, applies migrations, loads the destination
catalogue and starts Gunicorn. The `n8n-init` one-shot container imports the shipped itinerary
workflow with its JSON active state before n8n starts.

Check that everything is up:

```bash
docker compose ps                       # db, backend, web and n8n should be "healthy"; n8n-init "exited (0)"
curl http://localhost:8080/health       # {"status":"ok","database":"ok"} (through nginx)
curl http://localhost:5000/health       # same, direct to Flask
```

| Service | URL |
|---|---|
| **Frontend** | **http://localhost:8080** |
| Backend API (direct, for debugging) | http://localhost:5000 |
| n8n editor | http://localhost:5678 |
| PostgreSQL | internal to Docker only (not published) |

Optional — create a demo account with two sample trips (development only):

```bash
docker compose exec -e APP_ENV=development backend flask seed-demo
# login: demo@travelmate.local / DemoPass123
```

### 5. Use the app

Open <http://localhost:8080>, create an account, then create a trip. The page code calls
`/api/v1/...` on the same origin; nginx forwards it to Flask. Do not point the frontend at
`http://localhost:5000/api/v1` — that is a different origin and the browser will block it.

**Mock mode.** To click through the pages without a backend, run this once in the browser
console and reload:

```js
localStorage.tm_mock = '1';
```

Switch back with `localStorage.removeItem('tm_mock')`. Mock data lives in `localStorage`;
`localStorage.clear()` resets it.

**How the pages talk to the API.** The pages were written against the sample-data shapes.
`frontend/assets/js/api.js` contains one translation layer that maps the Flask envelopes and
field names (`{"items": [...]}`, `traveller_count`, `booking_type`, `latitude`, …) to the
shapes the pages already use, and turns API error envelopes into readable messages. Page code
is unchanged.

### 6. Itinerary generation (n8n)

The workflow is in `n8n/workflows/travelmate-trip-generate.json` and is imported automatically
with its checked-in active state on `docker compose up` (workflow id `tmTripGenerate`). It:

1. receives `POST /webhook/trip-generate` and verifies `X-Webhook-Secret`;
2. geocodes the destination and fetches attractions with **Geoapify**;
3. fetches a 16-day forecast from **Open-Meteo** (free, no key);
4. asks **Gemini** for a strict-JSON itinerary using those real places;
5. posts the result to the backend callback with the same secret.

Add `GEMINI_API_KEY` and `GEOAPIFY_API_KEY` to `.env`, then restart:

```bash
docker compose up -d
```

Open <http://localhost:5678> and create the n8n owner account (first visit only). The
workflow is already there and active. If generation fails, the trip is marked *Failed* with a
retry button; check `docker compose logs -f n8n` and `docker compose logs n8n-init`.

> `n8n-init` re-imports the file on every stack start, so changes made only in the n8n editor
> are overwritten. Make persistent changes in the JSON file (or stop using `n8n-init` once you
> are editing the workflow by hand).

### 7. Stopping, logs and resetting

```bash
docker compose logs -f backend      # follow backend logs
docker compose logs -f web          # nginx access/error logs
docker compose logs -f n8n          # workflow executions
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
| `403 forbidden` from the API | The page's origin isn't in `ALLOWED_ORIGINS`. Open the site at the exact URL listed there (usually `http://localhost:8080`). |
| Logged in, but the next request is `401` | Use `SESSION_COOKIE_SECURE=false` for plain-HTTP local runs. |
| Login fails or the page returns to login | Inspect the backend and nginx logs while retrying: `docker compose logs --tail=100 backend` and `docker compose logs --tail=100 web`. Check for `401`, `403`, origin/CSRF messages, database errors, or a missing session cookie. Confirm the browser URL matches `ALLOWED_ORIGINS` exactly and that `.env` has `SESSION_COOKIE_SECURE=false` for local HTTP. |
| Need to watch a login failure live | Run `docker compose logs -f backend web`, retry the login once, then stop with `Ctrl+C`. The backend log contains the request id and authentication result; nginx shows the HTTP status returned to the browser. |
| The browser blocks API calls / CORS errors | Open the app at <http://localhost:8080>, not by opening the HTML files directly and not by pointing `api.js` at port 5000. |
| Port 8080, 5000 or 5678 already in use | Set `WEB_PORT` / `BACKEND_PORT` / `N8N_PORT` in `.env` (then update `ALLOWED_ORIGINS` if you changed `WEB_PORT`). |
| "Generate itinerary" fails immediately | Add `GEMINI_API_KEY` and `GEOAPIFY_API_KEY` to `.env` and run `docker compose up -d`. Check `docker compose logs n8n`. |
| n8n workflow is missing or inactive | `docker compose logs n8n-init`; re-run it with `docker compose run --rm n8n-init`. |
| Backend container keeps restarting | `docker compose logs backend` — usually a missing env value or the database not ready. |

## Project structure

```
TravelMate/
├── frontend/              HTML pages, assets/css, assets/js (api.js = API + translation layer)
│   ├── Dockerfile         nginx image that serves the pages
│   └── nginx.conf         proxies /api and /media to Flask
├── backend/
│   ├── app/               Flask app: blueprints, services, schemas, models, middleware
│   ├── migrations/        Alembic database migrations
│   ├── seed/              destination catalogue + default packing list
│   ├── tests/             pytest suite
│   ├── Dockerfile, entrypoint.sh, requirements*.txt
├── n8n/
│   └── workflows/         importable n8n workflows (Gemini + Geoapify + Open-Meteo)
├── docs/                  API contract, OpenAPI spec, Postman collection, integration notes
├── docker-compose.yml     db + backend + web + n8n (+ one-shot n8n-init)
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
