import hmac
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg2
from flask import Flask, jsonify, request


app = Flask(__name__)
REMINDER_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _connect_db():
    """Connect using Render's DATABASE_URL or the local Compose Postgres vars."""
    database_url = os.getenv("DATABASE_URL")
    if database_url and not os.getenv("POSTGRES_HOST"):
        return psycopg2.connect(database_url, connect_timeout=5)

    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    if not all(os.getenv(key) for key in required):
        raise RuntimeError("Database connection is not configured")

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "db"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5,
    )


def _require_internal_secret():
    expected_secret = os.getenv("INTERNAL_WEBHOOK_SECRET", "")
    supplied_secret = request.headers.get("X-Webhook-Secret", "")
    return bool(expected_secret) and hmac.compare_digest(supplied_secret, expected_secret)


def _ensure_reminder_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_trips (
            trip_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            destination TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            user_email TEXT,
            notify_email BOOLEAN NOT NULL DEFAULT FALSE,
            notify_telegram BOOLEAN NOT NULL DEFAULT FALSE,
            telegram_chat_id TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION
        )
        """
    )
    cursor.execute("ALTER TABLE reminder_trips ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION")
    cursor.execute("ALTER TABLE reminder_trips ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_notifications (
            id BIGSERIAL PRIMARY KEY,
            trip_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            notification_type TEXT NOT NULL CHECK (notification_type IN ('7_day', '2_day', 'weather_alert')),
            message TEXT NOT NULL,
            scheduled_at TIMESTAMPTZ NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL,
            delivery_status TEXT NOT NULL CHECK (delivery_status IN ('sent', 'failed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_trip_reminder_occurrence UNIQUE (trip_id, notification_type, scheduled_at)
        )
        """
    )
    cursor.execute("ALTER TABLE trip_notifications DROP CONSTRAINT IF EXISTS trip_notifications_notification_type_check")
    cursor.execute(
        """ALTER TABLE trip_notifications ADD CONSTRAINT trip_notifications_notification_type_check
           CHECK (notification_type IN ('7_day', '2_day', 'weather_alert'))"""
    )


def _parse_timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


@app.get("/health")
def health():
    return "ok", 200


@app.post("/api/internal/trips/<int:path_trip_id>/result")
def save_trip_result(path_trip_id):
    if not _require_internal_secret():
        return jsonify(error="Unauthorized"), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Request body must be a JSON object"), 400

    trip_id = body.get("trip_id")
    if type(trip_id) is not int or trip_id != path_trip_id:
        return jsonify(error="Path trip ID must match body trip_id"), 400

    status = body.get("status")
    if status not in ("Completed", "Failed"):
        return jsonify(error="status must be Completed or Failed"), 400

    error_message = body.get("error_message")
    if status == "Failed" and (not isinstance(error_message, str) or not error_message.strip()):
        return jsonify(error="Failed results require a non-empty error_message"), 400
    if status == "Completed" and error_message is not None:
        return jsonify(error="Completed results must have error_message set to null"), 400

    for field in ("itinerary", "expenses"):
        if not isinstance(body.get(field), list):
            return jsonify(error=f"{field} must be a JSON array"), 400

    try:
        with _connect_db() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trip_generation_results (
                        trip_id BIGINT PRIMARY KEY,
                        status TEXT NOT NULL CHECK (status IN ('Completed', 'Failed')),
                        error_message TEXT,
                        result JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO trip_generation_results
                        (trip_id, status, error_message, result, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (trip_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        error_message = EXCLUDED.error_message,
                        result = EXCLUDED.result,
                        updated_at = NOW()
                    """,
                    (trip_id, status, error_message, json.dumps(body)),
                )
    except (psycopg2.Error, RuntimeError, ValueError):
        app.logger.exception("Could not persist trip generation result")
        return jsonify(error="Result storage is temporarily unavailable"), 503

    return jsonify(trip_id=trip_id, status=status, stored=True), 200


@app.post("/api/internal/reminder-trips")
def save_reminder_trip():
    """Bridge endpoint for the main Flask trip API to register reminder fields."""
    if not _require_internal_secret():
        return jsonify(error="Unauthorized"), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Request body must be a JSON object"), 400

    trip_id = body.get("trip_id")
    user_id = body.get("user_id")
    destination = body.get("destination")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    if type(trip_id) is not int or trip_id < 1 or type(user_id) is not int or user_id < 1:
        return jsonify(error="trip_id and user_id must be positive integers"), 400
    if not isinstance(destination, str) or not destination.strip():
        return jsonify(error="destination is required"), 400
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (TypeError, ValueError):
        return jsonify(error="start_date and end_date must use YYYY-MM-DD"), 400
    if end < start:
        return jsonify(error="end_date must not be before start_date"), 400
    email = body.get("email")
    chat_id = body.get("telegram_chat_id")
    if email is not None and not isinstance(email, str):
        return jsonify(error="email must be a string or null"), 400
    if chat_id is not None and not isinstance(chat_id, str):
        return jsonify(error="telegram_chat_id must be a string or null"), 400
    if type(body.get("notify_email", False)) is not bool or type(body.get("notify_telegram", False)) is not bool:
        return jsonify(error="notification preferences must be booleans"), 400
    latitude = body.get("latitude")
    longitude = body.get("longitude")
    if latitude is not None and (type(latitude) not in (int, float) or not -90 <= latitude <= 90):
        return jsonify(error="latitude must be between -90 and 90"), 400
    if longitude is not None and (type(longitude) not in (int, float) or not -180 <= longitude <= 180):
        return jsonify(error="longitude must be between -180 and 180"), 400
    if (latitude is None) != (longitude is None):
        return jsonify(error="latitude and longitude must be provided together"), 400

    try:
        with _connect_db() as connection:
            with connection.cursor() as cursor:
                _ensure_reminder_schema(cursor)
                cursor.execute(
                    """
                    INSERT INTO reminder_trips
                        (trip_id, user_id, destination, start_date, end_date, user_email,
                         notify_email, notify_telegram, telegram_chat_id, latitude, longitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trip_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        destination = EXCLUDED.destination,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        user_email = EXCLUDED.user_email,
                        notify_email = EXCLUDED.notify_email,
                        notify_telegram = EXCLUDED.notify_telegram,
                        telegram_chat_id = EXCLUDED.telegram_chat_id,
                        latitude = COALESCE(EXCLUDED.latitude, reminder_trips.latitude),
                        longitude = COALESCE(EXCLUDED.longitude, reminder_trips.longitude)
                    """,
                    (
                        trip_id,
                        user_id,
                        destination.strip(),
                        start,
                        end,
                        email,
                        body.get("notify_email", False),
                        body.get("notify_telegram", False),
                        chat_id,
                        latitude,
                        longitude,
                    ),
                )
    except (psycopg2.Error, RuntimeError, ValueError):
        app.logger.exception("Could not save reminder trip data")
        return jsonify(error="Reminder data storage is temporarily unavailable"), 503

    return jsonify(trip_id=trip_id, stored=True), 200


@app.get("/api/internal/upcoming-trips")
def upcoming_trips():
    if not _require_internal_secret():
        return jsonify(error="Unauthorized"), 401

    raw_days = request.args.get("days", "7,2")
    try:
        reminder_days = {int(value) for value in raw_days.split(",") if value.strip()}
    except ValueError:
        return jsonify(error="days must be comma-separated positive integers"), 400
    if not reminder_days or not reminder_days.issubset({7, 2}):
        return jsonify(error="days must contain 7, 2, or both"), 400

    today = datetime.now(REMINDER_TIMEZONE).date()
    scheduled_at = datetime.combine(today, time(hour=8), REMINDER_TIMEZONE).astimezone(timezone.utc)
    try:
        with _connect_db() as connection:
            with connection.cursor() as cursor:
                _ensure_reminder_schema(cursor)
                cursor.execute(
                    """
                    SELECT trip_id, user_id, destination, start_date, end_date,
                           user_email, notify_email, notify_telegram, telegram_chat_id
                    FROM reminder_trips
                    WHERE start_date - %s = ANY(%s)
                      AND (notify_email OR notify_telegram)
                    ORDER BY trip_id
                    """,
                    (today, list(reminder_days)),
                )
                trips = cursor.fetchall()
                due = []
                for row in trips:
                    (trip_id, user_id, destination, start, end, email,
                     notify_email, notify_telegram, telegram_chat_id) = row
                    days_before = (start - today).days
                    reminder_type = "7_day" if days_before == 7 else "2_day" if days_before == 2 else f"{days_before}_day"
                    cursor.execute(
                        """
                        SELECT 1 FROM trip_notifications
                        WHERE trip_id = %s AND notification_type = %s AND scheduled_at = %s
                        """,
                        (trip_id, reminder_type, scheduled_at),
                    )
                    if cursor.fetchone():
                        continue
                    due.append(
                        {
                            "trip_id": trip_id,
                            "user_id": user_id,
                            "destination": destination,
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                            "email": email,
                            "notify_email": notify_email,
                            "notify_telegram": notify_telegram,
                            "telegram_chat_id": telegram_chat_id,
                            "reminder_type": reminder_type,
                            "scheduled_at": scheduled_at.isoformat(),
                        }
                    )
    except (psycopg2.Error, RuntimeError, ValueError):
        app.logger.exception("Could not load upcoming reminder trips")
        return jsonify(error="Reminder data is temporarily unavailable"), 503

    return jsonify(trips=due), 200


@app.get("/api/internal/weather-trips")
def weather_trips():
    if not _require_internal_secret():
        return jsonify(error="Unauthorized"), 401

    try:
        days = int(request.args.get("days", "5"))
    except ValueError:
        return jsonify(error="days must be an integer from 1 to 5"), 400
    if not 1 <= days <= 5:
        return jsonify(error="days must be an integer from 1 to 5"), 400

    today = datetime.now(REMINDER_TIMEZONE).date()
    scheduled_at = datetime.combine(today, time(hour=8), REMINDER_TIMEZONE).astimezone(timezone.utc)
    try:
        with _connect_db() as connection:
            with connection.cursor() as cursor:
                _ensure_reminder_schema(cursor)
                cursor.execute(
                    """
                    SELECT r.trip_id, r.user_id, r.destination, r.start_date, r.end_date,
                           r.user_email, r.notify_email, r.notify_telegram, r.telegram_chat_id,
                           COALESCE(r.latitude, p.latitude), COALESCE(r.longitude, p.longitude)
                    FROM reminder_trips r
                    LEFT JOIN trip_generation_results g ON g.trip_id = r.trip_id
                    LEFT JOIN LATERAL (
                        SELECT (item->>'latitude')::double precision AS latitude,
                               (item->>'longitude')::double precision AS longitude
                        FROM jsonb_array_elements(
                            CASE WHEN jsonb_typeof(g.result->'itinerary') = 'array'
                                 THEN g.result->'itinerary' ELSE '[]'::jsonb END
                        ) WITH ORDINALITY AS activity(item, position)
                        WHERE jsonb_typeof(item->'latitude') = 'number'
                          AND jsonb_typeof(item->'longitude') = 'number'
                          AND (item->>'latitude')::double precision BETWEEN -90 AND 90
                          AND (item->>'longitude')::double precision BETWEEN -180 AND 180
                        ORDER BY position
                        LIMIT 1
                    ) p ON TRUE
                    WHERE r.start_date BETWEEN %s AND %s
                      AND (r.notify_email OR r.notify_telegram)
                      AND COALESCE(r.latitude, p.latitude) IS NOT NULL
                      AND COALESCE(r.longitude, p.longitude) IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM trip_notifications n
                          WHERE n.trip_id = r.trip_id
                            AND n.notification_type = 'weather_alert'
                            AND n.scheduled_at = %s
                      )
                    ORDER BY r.start_date, r.trip_id
                    """,
                    (today, today + timedelta(days=days), scheduled_at),
                )
                trips = cursor.fetchall()
    except (psycopg2.Error, RuntimeError, ValueError):
        app.logger.exception("Could not load trips for weather alerts")
        return jsonify(error="Weather alert data is temporarily unavailable"), 503

    due = [
        {
            "trip_id": row[0], "user_id": row[1], "destination": row[2],
            "start_date": row[3].isoformat(), "end_date": row[4].isoformat(),
            "email": row[5], "notify_email": row[6], "notify_telegram": row[7],
            "telegram_chat_id": row[8], "latitude": row[9], "longitude": row[10],
            "scheduled_at": scheduled_at.isoformat(),
        }
        for row in trips
    ]
    return jsonify(trips=due), 200


@app.post("/api/internal/notifications")
def record_notification():
    if not _require_internal_secret():
        return jsonify(error="Unauthorized"), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Request body must be a JSON object"), 400
    trip_id = body.get("trip_id")
    user_id = body.get("user_id")
    notification_type = body.get("notification_type")
    message = body.get("message")
    delivery_status = body.get("delivery_status")
    if type(trip_id) is not int or trip_id < 1 or type(user_id) is not int or user_id < 1:
        return jsonify(error="trip_id and user_id must be positive integers"), 400
    if notification_type not in ("7_day", "2_day", "weather_alert"):
        return jsonify(error="notification_type must be 7_day, 2_day, or weather_alert"), 400
    if not isinstance(message, str) or not message.strip():
        return jsonify(error="message is required"), 400
    if delivery_status not in ("sent", "failed"):
        return jsonify(error="delivery_status must be sent or failed"), 400
    try:
        scheduled_at = _parse_timestamp(body.get("scheduled_at"), "scheduled_at")
        sent_at = _parse_timestamp(body.get("sent_at"), "sent_at")
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    try:
        with _connect_db() as connection:
            with connection.cursor() as cursor:
                _ensure_reminder_schema(cursor)
                cursor.execute(
                    """
                    INSERT INTO trip_notifications
                        (trip_id, user_id, notification_type, message, scheduled_at, sent_at, delivery_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trip_id, notification_type, scheduled_at) DO NOTHING
                    """,
                    (trip_id, user_id, notification_type, message.strip(), scheduled_at, sent_at, delivery_status),
                )
                inserted = cursor.rowcount == 1
    except (psycopg2.Error, RuntimeError, ValueError):
        app.logger.exception("Could not record reminder notification")
        return jsonify(error="Notification record is temporarily unavailable"), 503
    if not inserted:
        return jsonify(error="Reminder occurrence already recorded"), 409
    return jsonify(trip_id=trip_id, notification_type=notification_type, recorded=True), 201
