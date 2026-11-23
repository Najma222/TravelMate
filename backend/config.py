"""Environment-based configuration for the TravelMate backend.

All secrets come from environment variables. ``ProductionConfig.validate`` fails
fast when a required value is missing so the container never boots half-configured.
"""
from __future__ import annotations

import os
from datetime import timedelta


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _split_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


class BaseConfig:
    ENV_NAME = "base"
    DEBUG = False
    TESTING = False

    SECRET_KEY = _env("FLASK_SECRET_KEY")
    INTERNAL_WEBHOOK_SECRET = _env("INTERNAL_WEBHOOK_SECRET")
    N8N_TRIP_WEBHOOK_URL = _env("N8N_TRIP_WEBHOOK_URL")
    N8N_TIMEOUT_SECONDS = float(_env("N8N_TIMEOUT_SECONDS", "10"))
    # Base URL n8n uses to call back into Flask (Docker service name by default).
    BACKEND_INTERNAL_URL = _env("BACKEND_INTERNAL_URL", "http://backend:5000")
    GENERATION_TIMEOUT_MINUTES = int(_env("GENERATION_TIMEOUT_MINUTES", "10"))

    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 10,
        "connect_args": {
            "connect_timeout": 5,
            # Guard against runaway queries holding a worker thread / row locks.
            "options": "-c statement_timeout=15000 -c lock_timeout=10000",
        },
    }

    APP_TIMEZONE = _env("APP_TIMEZONE", "Asia/Kolkata")
    ALLOWED_ORIGINS = _split_origins(_env("ALLOWED_ORIGINS", ""))
    UPLOAD_DIR = _env("UPLOAD_DIR", "/app/uploads")
    MAX_UPLOAD_BYTES = 2 * 1024 * 1024
    # Request-level cap: 2 MB file + multipart framing overhead.
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 64 * 1024

    SESSION_COOKIE_NAME = "tm_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = _env("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    AUTH_RATE_LIMIT = "10/minute"
    LOGIN_FAILURE_LIMIT = 5
    LOGIN_FAILURE_WINDOW_MINUTES = 15

    LOG_LEVEL = _env("LOG_LEVEL", "INFO")
    BCRYPT_LOG_ROUNDS = 12
    ALLOW_DEMO_SEED = False

    REQUIRED = (
        "SECRET_KEY",
        "INTERNAL_WEBHOOK_SECRET",
        "N8N_TRIP_WEBHOOK_URL",
        "SQLALCHEMY_DATABASE_URI",
        "ALLOWED_ORIGINS",
    )

    @classmethod
    def validate(cls) -> None:
        missing = [k for k in cls.REQUIRED if not getattr(cls, k)]
        if missing:
            raise RuntimeError(
                "Missing required configuration: " + ", ".join(sorted(missing))
            )
        if cls.SECRET_KEY and len(cls.SECRET_KEY) < 32 and cls.ENV_NAME == "production":
            raise RuntimeError("FLASK_SECRET_KEY must be at least 32 characters")


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    ALLOW_DEMO_SEED = True
    SECRET_KEY = BaseConfig.SECRET_KEY or "dev-only-insecure-secret-key-change-me-0000"
    ALLOWED_ORIGINS = BaseConfig.ALLOWED_ORIGINS or ["http://localhost:5173"]
    REQUIRED = ("SQLALCHEMY_DATABASE_URI",)


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "test-secret-key-test-secret-key-0000"
    INTERNAL_WEBHOOK_SECRET = "test-internal-secret"
    N8N_TRIP_WEBHOOK_URL = "http://n8n.test/webhook/trip"
    BACKEND_INTERNAL_URL = "http://backend.test"
    SQLALCHEMY_DATABASE_URI = _env(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://travelmate:travelmate@localhost:55432/travelmate_test",
    )
    ALLOWED_ORIGINS = ["http://localhost:5173"]
    BCRYPT_LOG_ROUNDS = 4
    RATELIMIT_STORAGE_URI = "memory://"
    ALLOW_DEMO_SEED = True
    LOG_LEVEL = "WARNING"
    REQUIRED = ()


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    SESSION_COOKIE_SECURE = _env("SESSION_COOKIE_SECURE", "true").lower() != "false"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    name = (name or _env("APP_ENV") or _env("FLASK_ENV") or "production").lower()
    if name not in CONFIGS:
        raise RuntimeError(f"Unknown APP_ENV '{name}'")
    return CONFIGS[name]
