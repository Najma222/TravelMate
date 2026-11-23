#!/bin/sh
# TravelMate backend entrypoint: wait for PostgreSQL, migrate, seed (idempotent), serve.
set -eu

echo "[entrypoint] waiting for database..."
python - <<'PY'
import os, sys, time
import psycopg2
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
for attempt in range(60):
    try:
        psycopg2.connect(host=url.host, port=url.port or 5432, user=url.username,
                         password=url.password, dbname=url.database, connect_timeout=3).close()
        print("[entrypoint] database is ready")
        sys.exit(0)
    except psycopg2.OperationalError:
        time.sleep(2)
print("[entrypoint] database not reachable after 120s", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] applying migrations..."
flask db upgrade

if [ "${SEED_DISCOVER_ON_START:-true}" = "true" ]; then
    flask seed-discover
fi

exec gunicorn -b 0.0.0.0:5000 --workers 1 --threads 4 \
    --timeout 60 --graceful-timeout 30 \
    --access-logfile - --error-logfile - \
    wsgi:app
