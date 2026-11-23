"""Generate docs/openapi.yaml and docs/postman/travelmate.postman_collection.json.

    python scripts/gen_api_docs.py

Both files are derived from the ROUTES table below; tests/test_docs.py asserts that
every route registered in the Flask app appears in both outputs.
"""
from __future__ import annotations

import json
import os
import re

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCS = os.path.join(ROOT, "docs")

S = lambda name: {"$ref": f"#/components/schemas/{name}"}  # noqa: E731
OBJ = lambda props, required=(): {"type": "object", "properties": props, **({"required": list(required)} if required else {})}  # noqa: E731
STR = {"type": "string"}
MONEY = {"type": "string", "pattern": r"^-?\d+\.\d{2}$", "example": "12500.00"}
MONEY_IN = {"oneOf": [{"type": "string"}, {"type": "number"}], "description": "Decimal, max 2 dp"}
DATE = {"type": "string", "format": "date"}
DT = {"type": "string", "format": "date-time"}
INT = {"type": "integer"}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}
NULLSTR = {"type": "string", "nullable": True}

SCHEMAS = {
    "Error": OBJ({"error": OBJ({"code": STR, "message": STR, "details": {"type": "object"}},
                              ["code", "message", "details"])}, ["error"]),
    "Pagination": OBJ({"page": INT, "per_page": INT, "total": INT, "pages": INT}),
    "User": OBJ({"id": INT, "name": STR, "email": STR, "role": STR, "avatar_url": NULLSTR,
                 "notify_email": BOOL, "notify_telegram": BOOL, "telegram_chat_id": NULLSTR,
                 "ui_prefs": {"type": "object"}, "created_at": DT, "updated_at": DT}),
    "Trip": OBJ({"id": INT, "origin": STR, "destination": STR, "start_date": DATE, "end_date": DATE,
                 "duration_days": INT, "traveller_count": INT, "budget": MONEY, "currency": STR,
                 "preferences": NULLSTR, "transport_preference": STR, "accommodation_preference": STR,
                 "status": {"type": "string", "enum": ["Draft", "Processing", "Completed", "Failed", "Cancelled"]},
                 "error_message": NULLSTR, "itinerary_stale": BOOL, "latitude": NUM, "longitude": NUM,
                 "cover_image_url": NULLSTR, "hero_quote": NULLSTR, "hero_quote_author": NULLSTR,
                 "phase": {"type": "string", "enum": ["upcoming", "ongoing", "past"]},
                 "ring_percent": NUM, "days_until_start": INT, "created_at": DT, "updated_at": DT}),
    "TripStatus": OBJ({"id": INT, "status": STR, "error_message": NULLSTR, "generation_id": NULLSTR,
                       "processing_started_at": DT, "itinerary_stale": BOOL, "updated_at": DT}),
    "TripCreate": OBJ({"origin": STR, "destination": STR, "start_date": DATE, "end_date": DATE,
                       "traveller_count": INT, "budget": MONEY_IN,
                       "currency": {"type": "string", "enum": ["INR", "USD", "EUR", "GBP", "NPR", "BDT", "AED"]},
                       "preferences": STR,
                       "transport_preference": {"type": "string", "enum": ["any", "flight", "train", "bus", "car"]},
                       "accommodation_preference": {"type": "string", "enum": ["any", "hotel", "hostel", "homestay", "resort"]},
                       "latitude": NUM, "longitude": NUM, "hero_quote": STR, "hero_quote_author": STR},
                      ["origin", "destination", "start_date", "end_date", "budget"]),
    "Stop": OBJ({"id": INT, "trip_id": INT, "position": INT, "name": STR, "latitude": NUM,
                 "longitude": NUM, "source": {"type": "string", "enum": ["user", "generated"]}}),
    "StopInput": OBJ({"name": STR, "latitude": NUM, "longitude": NUM}, ["name"]),
    "ItineraryItem": OBJ({"id": INT, "trip_id": INT, "day_number": INT, "activity_name": STR,
                          "description": NULLSTR, "location": NULLSTR, "start_time": NULLSTR,
                          "end_time": NULLSTR, "estimated_cost": MONEY, "latitude": NUM, "longitude": NUM,
                          "is_edited": BOOL, "sort_order": INT, "created_at": DT, "updated_at": DT}),
    "ItineraryInput": OBJ({"day_number": INT, "activity_name": STR, "description": STR, "location": STR,
                           "start_time": {"type": "string", "example": "09:00"}, "end_time": STR,
                           "estimated_cost": MONEY_IN, "latitude": NUM, "longitude": NUM, "sort_order": INT},
                          ["day_number", "activity_name"]),
    "Day": OBJ({"day_number": INT, "date": DATE, "title": STR, "summary": NULLSTR,
                "stop": {"type": "object", "nullable": True},
                "items": {"type": "array", "items": S("ItineraryItem")}}),
    "Expense": OBJ({"id": INT, "trip_id": INT, "booking_id": {"type": "integer", "nullable": True},
                    "category": STR, "description": NULLSTR, "amount": MONEY, "is_confirmed": BOOL,
                    "expense_date": DATE, "source": STR, "locked": BOOL, "created_at": DT, "updated_at": DT}),
    "ExpenseInput": OBJ({"category": {"type": "string", "enum": ["transport", "accommodation", "food", "activities", "local_transport", "misc"]},
                         "amount": MONEY_IN, "description": STR, "is_confirmed": BOOL, "expense_date": DATE},
                        ["category", "amount"]),
    "Budget": OBJ({"currency": STR, "budget": MONEY, "confirmed_total": MONEY, "estimated_total": MONEY,
                   "forecast_total": MONEY, "remaining": MONEY, "exceeded": BOOL, "exceeded_by": MONEY,
                   "spent_percent": NUM, "remaining_percent": NUM, "forecast_percent": NUM,
                   "categories": {"type": "array", "items": OBJ({"category": STR, "confirmed": MONEY,
                                                                 "estimated": MONEY, "effective": MONEY,
                                                                 "basis": {"type": "string", "enum": ["confirmed", "estimated"]}})}}),
    "Booking": OBJ({"id": INT, "trip_id": INT, "booking_type": STR, "provider": NULLSTR,
                    "booking_reference": NULLSTR, "amount": MONEY, "booked_on": DATE, "status": STR,
                    "from_location": NULLSTR, "to_location": NULLSTR, "start_at": DT, "end_at": DT,
                    "start_tz": NULLSTR, "end_tz": NULLSTR, "notes": NULLSTR,
                    "linked_expense_id": {"type": "integer", "nullable": True}, "created_at": DT, "updated_at": DT}),
    "BookingInput": OBJ({"booking_type": {"type": "string", "enum": ["hotel", "flight", "train", "bus"]},
                         "status": {"type": "string", "enum": ["Not Booked", "Pending", "Confirmed", "Cancelled"]},
                         "amount": MONEY_IN, "provider": STR, "booking_reference": STR, "booked_on": DATE,
                         "from_location": STR, "to_location": STR, "start_at": DT, "end_at": DT,
                         "start_tz": STR, "end_tz": STR, "notes": STR}, ["booking_type"]),
    "PackingItem": OBJ({"id": INT, "trip_id": INT, "name": STR, "note": NULLSTR, "is_packed": BOOL,
                        "remind_at": DT, "sort_order": INT,
                        "source": {"type": "string", "enum": ["user", "default", "auto"]}, "created_at": DT}),
    "PackingInput": OBJ({"name": STR, "note": STR, "is_packed": BOOL, "remind_at": DT, "sort_order": INT}, ["name"]),
    "Notification": OBJ({"id": INT, "trip_id": INT, "notification_type": STR, "message": STR,
                         "channels": {"type": "array", "items": STR}, "scheduled_for": DATE, "sent_at": DT,
                         "delivery_status": {"type": "string", "enum": ["sent", "failed", "pending"]},
                         "read_at": DT, "is_read": BOOL, "created_at": DT}),
    "Preferences": OBJ({"notify_email": BOOL, "notify_telegram": BOOL, "telegram_chat_id": NULLSTR}),
    "Weather": OBJ({"available": BOOL, "location_name": NULLSTR, "current": {"type": "object", "nullable": True},
                    "daily": {"type": "array", "items": OBJ({"date": DATE, "high_c": NUM, "low_c": NUM,
                                                             "precip_prob_max": NUM, "weather_code": INT, "condition": STR})},
                    "message": NULLSTR, "updated_at": DT}),
    "WeatherInput": OBJ({"location_name": STR,
                         "current": OBJ({"temperature_c": NUM, "weather_code": INT, "observed_at": DT}),
                         "daily": {"type": "array", "maxItems": 16, "items": OBJ({"date": DATE, "temp_max_c": NUM, "temp_min_c": NUM, "precip_prob_max": NUM, "weather_code": INT})},
                         "weather_message": STR}),
    "Destination": OBJ({"id": INT, "name": STR, "country": STR, "region": NULLSTR, "description": NULLSTR,
                        "best_season": NULLSTR, "latitude": NUM, "longitude": NUM, "image_url": NULLSTR,
                        "tags": {"type": "array", "items": STR}}),
    "CallbackPayload": OBJ({"generation_id": {"type": "string", "format": "uuid"},
                            "status": {"type": "string", "enum": ["Completed", "Failed"]},
                            "error_message": STR,
                            "itinerary": {"type": "array", "maxItems": 200, "items": S("ItineraryInput")},
                            "days": {"type": "array", "items": OBJ({"day_number": INT, "title": STR, "summary": STR, "stop_name": STR})},
                            "expenses": {"type": "array", "maxItems": 50, "items": OBJ({"category": STR, "description": STR, "amount": MONEY_IN})},
                            "stops": {"type": "array", "maxItems": 50, "items": S("StopInput")},
                            "weather": S("WeatherInput"), "latitude": NUM, "longitude": NUM,
                            "hero_quote": STR, "hero_quote_author": STR}, ["generation_id", "status"]),
    "InternalNotification": OBJ({"trip_id": INT, "notification_type": STR, "message": STR,
                                 "channels": {"type": "array", "items": {"type": "string", "enum": ["email", "telegram", "in_app"]}},
                                 "scheduled_for": DATE,
                                 "delivery_status": {"type": "string", "enum": ["sent", "failed", "pending"]},
                                 "sent_at": DT}, ["trip_id", "notification_type", "message"]),
}

W = lambda key, schema: OBJ({key: schema})  # noqa: E731
ARR = lambda schema: {"type": "array", "items": schema}  # noqa: E731
PAGED = lambda schema: OBJ({"items": ARR(schema), "pagination": S("Pagination")})  # noqa: E731
DELETED = OBJ({"deleted": BOOL, "id": INT})

# (method, path, tag, auth, summary, request(schema|None|"multipart"), status, response, sample_body, query)
ROUTES = [
    ("get", "/health", "Public", "public", "Liveness + DB readiness", None, 200, OBJ({"status": STR, "database": STR}), None, []),
    ("get", "/media/{filename}", "Public", "public", "Serve avatars/covers ({kind}/{uuid}.webp)", None, 200, {"type": "string", "format": "binary"}, None, []),
    ("get", "/api/v1/discover/destinations", "Public", "public", "Search destinations", None, 200, PAGED(S("Destination")), None, ["q", "country", "region", "tag", "page", "per_page"]),
    ("post", "/api/v1/auth/register", "Auth", "public", "Register (10/min/IP)", OBJ({"name": STR, "email": STR, "password": STR}, ["name", "email", "password"]), 201, W("user", S("User")), {"name": "Asha", "email": "asha@example.com", "password": "Passw0rd!"}, []),
    ("post", "/api/v1/auth/login", "Auth", "public", "Login (10/min/IP, 5 failures/15min/email)", OBJ({"email": STR, "password": STR}, ["email", "password"]), 200, W("user", S("User")), {"email": "asha@example.com", "password": "Passw0rd!"}, []),
    ("post", "/api/v1/auth/logout", "Auth", "session", "Logout (rotates nonce)", None, 200, OBJ({"logged_out": BOOL}), {}, []),
    ("get", "/api/v1/auth/me", "Auth", "session", "Current user", None, 200, W("user", S("User")), None, []),
    ("put", "/api/v1/auth/profile", "Auth", "session", "Update profile", OBJ({"name": STR, "ui_prefs": {"type": "object"}}), 200, W("user", S("User")), {"name": "Asha K"}, []),
    ("post", "/api/v1/auth/avatar", "Auth", "session", "Upload avatar (multipart `file`)", "multipart", 200, OBJ({"user": S("User"), "upload": OBJ({"kind": STR, "url": STR, "content_type": STR})}), None, []),
    ("post", "/api/v1/auth/change-password", "Auth", "session", "Change password (rotates nonce)", OBJ({"current_password": STR, "new_password": STR}, ["current_password", "new_password"]), 200, OBJ({"password_changed": BOOL}), {"current_password": "Passw0rd!", "new_password": "N3wPassw0rd!"}, []),
    ("delete", "/api/v1/auth/me", "Auth", "session", "Delete account", OBJ({"password": STR}, ["password"]), 200, OBJ({"deleted": BOOL}), {"password": "Passw0rd!"}, []),
    ("post", "/api/v1/trips", "Trips", "session", "Create trip", S("TripCreate"), 201, W("trip", S("Trip")), {"origin": "Mumbai", "destination": "Goa", "start_date": "2026-12-20", "end_date": "2026-12-23", "traveller_count": 2, "budget": "30000.00", "currency": "INR"}, []),
    ("get", "/api/v1/trips", "Trips", "session", "List trips", None, 200, PAGED(S("Trip")), None, ["scope", "page", "per_page"]),
    ("get", "/api/v1/trips/{trip_id}", "Trips", "session", "Get trip", None, 200, W("trip", S("Trip")), None, []),
    ("put", "/api/v1/trips/{trip_id}", "Trips", "session", "Update trip (partial)", S("TripCreate"), 200, W("trip", S("Trip")), {"traveller_count": 3}, []),
    ("delete", "/api/v1/trips/{trip_id}", "Trips", "session", "Delete trip", None, 200, DELETED, None, []),
    ("post", "/api/v1/trips/{trip_id}/generate", "Trips", "session", "Start itinerary generation", None, 202, W("trip", S("TripStatus")), {}, []),
    ("post", "/api/v1/trips/{trip_id}/cancel", "Trips", "session", "Cancel trip", None, 200, W("trip", S("Trip")), {}, []),
    ("get", "/api/v1/trips/{trip_id}/status", "Trips", "session", "Generation status (+ stuck sweep)", None, 200, W("trip", S("TripStatus")), None, []),
    ("post", "/api/v1/trips/{trip_id}/cover", "Trips", "session", "Upload cover (multipart `file`)", "multipart", 200, OBJ({"trip": S("Trip"), "upload": {"type": "object"}}), None, []),
    ("get", "/api/v1/trips/{trip_id}/weather", "Trips", "session", "Weather (never fabricated)", None, 200, OBJ({"trip_id": INT, "weather": S("Weather")}), None, []),
    ("get", "/api/v1/trips/{trip_id}/places", "Trips", "session", "Stored places and stops", None, 200, {"type": "object"}, None, []),
    ("post", "/api/v1/trips/{trip_id}/stops", "Stops", "session", "Add stop", S("StopInput"), 201, W("stop", S("Stop")), {"name": "Panaji", "latitude": 15.49, "longitude": 73.82}, []),
    ("put", "/api/v1/stops/{stop_id}", "Stops", "session", "Update stop", S("StopInput"), 200, W("stop", S("Stop")), {"name": "Old Goa"}, []),
    ("delete", "/api/v1/stops/{stop_id}", "Stops", "session", "Delete stop", None, 200, DELETED, None, []),
    ("put", "/api/v1/trips/{trip_id}/stops/order", "Stops", "session", "Reorder stops", OBJ({"stop_ids": ARR(INT)}, ["stop_ids"]), 200, W("stops", ARR(S("Stop"))), {"stop_ids": [2, 1]}, []),
    ("get", "/api/v1/trips/{trip_id}/overview", "Overview", "session", "Trip overview (ETag/304, ≤8 queries)", None, 200, {"type": "object"}, None, []),
    ("get", "/api/v1/dashboard", "Overview", "session", "Dashboard", None, 200, {"type": "object"}, None, []),
    ("get", "/api/v1/trips/{trip_id}/itinerary", "Itinerary", "session", "Itinerary by day", None, 200, OBJ({"trip_id": INT, "status": STR, "itinerary_stale": BOOL, "days": ARR(S("Day"))}), None, []),
    ("post", "/api/v1/trips/{trip_id}/itinerary", "Itinerary", "session", "Add itinerary item", S("ItineraryInput"), 201, W("item", S("ItineraryItem")), {"day_number": 1, "activity_name": "Fort Aguada", "start_time": "09:00", "end_time": "11:00"}, []),
    ("put", "/api/v1/itinerary/{item_id}", "Itinerary", "session", "Update item", S("ItineraryInput"), 200, W("item", S("ItineraryItem")), {"activity_name": "Fort Aguada Lighthouse"}, []),
    ("delete", "/api/v1/itinerary/{item_id}", "Itinerary", "session", "Delete item", None, 200, DELETED, None, []),
    ("put", "/api/v1/trips/{trip_id}/days/{day_number}", "Itinerary", "session", "Update day title/summary/stop", OBJ({"title": STR, "summary": STR, "stop_id": INT}), 200, W("day", S("Day")), {"title": "North Goa beaches"}, []),
    ("get", "/api/v1/trips/{trip_id}/expenses", "Expenses", "session", "List expenses", None, 200, OBJ({"trip_id": INT, "currency": STR, "items": ARR(S("Expense"))}), None, ["category"]),
    ("post", "/api/v1/trips/{trip_id}/expenses", "Expenses", "session", "Add expense", S("ExpenseInput"), 201, W("expense", S("Expense")), {"category": "food", "amount": "450.00", "description": "Dinner", "is_confirmed": True}, []),
    ("put", "/api/v1/expenses/{expense_id}", "Expenses", "session", "Update expense (409 if booking-linked)", S("ExpenseInput"), 200, W("expense", S("Expense")), {"amount": "500.00"}, []),
    ("delete", "/api/v1/expenses/{expense_id}", "Expenses", "session", "Delete expense (409 if booking-linked)", None, 200, DELETED, None, []),
    ("get", "/api/v1/trips/{trip_id}/budget", "Expenses", "session", "Budget summary (D3)", None, 200, OBJ({"trip_id": INT, "budget": S("Budget")}), None, []),
    ("get", "/api/v1/trips/{trip_id}/bookings", "Bookings", "session", "List bookings", None, 200, OBJ({"trip_id": INT, "currency": STR, "items": ARR(S("Booking"))}), None, []),
    ("post", "/api/v1/trips/{trip_id}/bookings", "Bookings", "session", "Add booking (+expense sync)", S("BookingInput"), 201, W("booking", S("Booking")), {"booking_type": "hotel", "provider": "Taj", "amount": "12000.00", "status": "Confirmed", "start_at": "2026-12-20T14:00:00+05:30", "start_tz": "Asia/Kolkata"}, []),
    ("put", "/api/v1/bookings/{booking_id}", "Bookings", "session", "Update booking (+expense sync)", S("BookingInput"), 200, W("booking", S("Booking")), {"status": "Cancelled"}, []),
    ("delete", "/api/v1/bookings/{booking_id}", "Bookings", "session", "Delete booking", None, 200, DELETED, None, []),
    ("get", "/api/v1/trips/{trip_id}/booking-links", "Bookings", "session", "External search links", None, 200, {"type": "object"}, None, []),
    ("get", "/api/v1/trips/{trip_id}/packing", "Packing", "session", "List packing items", None, 200, OBJ({"trip_id": INT, "total": INT, "packed": INT, "items": ARR(S("PackingItem"))}), None, []),
    ("post", "/api/v1/trips/{trip_id}/packing", "Packing", "session", "Add packing item", S("PackingInput"), 201, W("item", S("PackingItem")), {"name": "Snorkel"}, []),
    ("put", "/api/v1/packing/{item_id}", "Packing", "session", "Update packing item", S("PackingInput"), 200, W("item", S("PackingItem")), {"is_packed": True}, []),
    ("delete", "/api/v1/packing/{item_id}", "Packing", "session", "Delete packing item", None, 200, DELETED, None, []),
    ("get", "/api/v1/notifications", "Notifications", "session", "List notifications", None, 200, PAGED(S("Notification")), None, ["unread", "page", "per_page"]),
    ("put", "/api/v1/notifications/{notification_id}/read", "Notifications", "session", "Mark read", None, 200, W("notification", S("Notification")), {}, []),
    ("post", "/api/v1/notifications/read-all", "Notifications", "session", "Mark all read", None, 200, OBJ({"marked_read": INT}), {}, []),
    ("get", "/api/v1/notifications/preferences", "Notifications", "session", "Get preferences", None, 200, W("preferences", S("Preferences")), None, []),
    ("put", "/api/v1/notifications/preferences", "Notifications", "session", "Update preferences", S("Preferences"), 200, W("preferences", S("Preferences")), {"notify_email": True}, []),
    ("post", "/api/v1/internal/trips/{trip_id}/result", "Internal", "internal", "n8n generation callback", S("CallbackPayload"), 200, {"type": "object"}, {"generation_id": "00000000-0000-0000-0000-000000000000", "status": "Completed", "itinerary": [{"day_number": 1, "activity_name": "Fort Aguada"}]}, []),
    ("put", "/api/v1/internal/trips/{trip_id}/weather", "Internal", "internal", "Store weather", S("WeatherInput"), 200, OBJ({"trip_id": INT, "weather": S("Weather")}), {"location_name": "Goa", "daily": [{"date": "2026-12-20", "temp_max_c": 31, "temp_min_c": 22, "precip_prob_max": 10, "weather_code": 1}]}, []),
    ("get", "/api/v1/internal/upcoming-trips", "Internal", "internal", "Trips starting soon", None, 200, {"type": "object"}, None, ["days"]),
    ("get", "/api/v1/internal/active-trips", "Internal", "internal", "Ongoing trips", None, 200, {"type": "object"}, None, []),
    ("get", "/api/v1/internal/booking-gaps", "Internal", "internal", "Upcoming trips missing bookings", None, 200, {"type": "object"}, None, ["days"]),
    ("post", "/api/v1/internal/notifications", "Internal", "internal", "Record notification delivery (201/200/409)", S("InternalNotification"), 201, OBJ({"notification": S("Notification"), "created": BOOL}), {"trip_id": 1, "notification_type": "trip_reminder", "message": "Your trip starts in 3 days", "channels": ["email"], "delivery_status": "sent"}, []),
    ("post", "/api/v1/internal/sweep-stuck", "Internal", "internal", "Fail Processing trips older than 10 min", None, 200, OBJ({"swept": INT, "trip_ids": ARR(INT)}), {}, []),
]

ERR = {"description": "Error", "content": {"application/json": {"schema": S("Error")}}}


def build_openapi() -> dict:
    paths: dict = {}
    for method, path, tag, auth, summary, req, status, resp, _sample, query in ROUTES:
        op = {"tags": [tag], "summary": summary, "responses": {str(status): {
            "description": "Success", "content": {"application/json": {"schema": resp}}}}}
        params = [{"name": p, "in": "path", "required": True,
                   "schema": {"type": "string" if p == "filename" else "integer"}}
                  for p in re.findall(r"{(\w+)}", path)]
        params += [{"name": q, "in": "query", "required": False, "schema": {"type": "string"}} for q in query]
        if params:
            op["parameters"] = params
        if req == "multipart":
            op["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": OBJ(
                {"file": {"type": "string", "format": "binary"}}, ["file"])}}}
        elif req is not None:
            op["requestBody"] = {"required": True, "content": {"application/json": {"schema": req}}}
        if auth == "session":
            op["security"] = [{"sessionCookie": []}]
            op["responses"]["401"] = ERR
            if path.count("{") and "notifications" not in path:
                op["responses"]["404"] = ERR
        elif auth == "internal":
            op["security"] = [{"webhookSecret": []}]
            op["responses"]["401"] = ERR
        else:
            op["security"] = []
        if method in ("post", "put", "delete"):
            op["responses"]["400"] = ERR
            if not path.startswith("/api/v1/internal"):
                op["responses"]["403"] = ERR
        if path.endswith("/generate"):
            op["responses"]["409"] = ERR
            op["responses"]["502"] = ERR
        if req == "multipart":
            op["responses"]["413"] = ERR
            op["responses"]["415"] = ERR
        if path.endswith(("/login", "/register")):
            op["responses"]["429"] = ERR
        if path in ("/api/v1/expenses/{expense_id}", "/api/v1/internal/notifications"):
            op["responses"]["409"] = ERR
        if path.endswith("/overview"):
            op["responses"]["304"] = {"description": "Not modified (If-None-Match matched)"}
        paths.setdefault(path, {})[method] = op
    return {
        "openapi": "3.0.3",
        "info": {"title": "TravelMate API", "version": "1.0.0",
                 "description": "See docs/api-contract.md. Unsafe user requests need Origin/Referer in "
                                "ALLOWED_ORIGINS and Content-Type: application/json (D12). Money is a 2-dp string."},
        "servers": [{"url": "http://localhost:5000"}],
        "components": {
            "securitySchemes": {
                "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "tm_session"},
                "webhookSecret": {"type": "apiKey", "in": "header", "name": "X-Webhook-Secret"},
            },
            "schemas": SCHEMAS,
        },
        "paths": paths,
    }


def build_postman() -> dict:
    folders: dict[str, list] = {}
    for method, path, tag, auth, summary, req, _status, _resp, sample, query in ROUTES:
        url_path = re.sub(r"{(\w+)}", r"{{\1}}", path)
        headers = []
        if auth == "internal":
            headers.append({"key": "X-Webhook-Secret", "value": "{{webhook_secret}}"})
        elif method in ("post", "put", "delete"):
            headers.append({"key": "Origin", "value": "{{origin}}"})
        item = {"name": f"{method.upper()} {path}", "request": {
            "method": method.upper(), "header": headers,
            "url": {"raw": "{{base_url}}" + url_path + ("?" + "&".join(f"{q}=" for q in query) if query else ""),
                    "host": ["{{base_url}}"], "path": [p for p in url_path.split("/") if p],
                    **({"query": [{"key": q, "value": "", "disabled": True} for q in query]} if query else {})},
            "description": summary}}
        if req == "multipart":
            item["request"]["body"] = {"mode": "formdata", "formdata": [{"key": "file", "type": "file", "src": ""}]}
        elif method in ("post", "put", "delete") and (sample is not None or req is not None):
            headers.append({"key": "Content-Type", "value": "application/json"})
            item["request"]["body"] = {"mode": "raw", "raw": json.dumps(sample if sample is not None else {}, indent=2),
                                       "options": {"raw": {"language": "json"}}}
        elif method in ("post", "put", "delete") and auth != "internal":
            headers.append({"key": "Content-Type", "value": "application/json"})
        folders.setdefault(tag, []).append(item)
    return {
        "info": {"name": "TravelMate API v1", "_postman_id": "8c1f4b8e-6c3c-4c1e-9d55-2f6a7b8c9d01",
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                 "description": "Run Auth > register/login first; Postman keeps the tm_session cookie. "
                                "Set trip_id etc. in collection variables."},
        "variable": [{"key": k, "value": v} for k, v in {
            "base_url": "http://localhost:5000", "origin": "http://localhost:5173",
            "webhook_secret": "replace-me", "trip_id": "1", "stop_id": "1", "item_id": "1",
            "expense_id": "1", "booking_id": "1", "notification_id": "1", "day_number": "1",
            "filename": "avatars/00000000-0000-0000-0000-000000000000.webp"}.items()],
        "item": [{"name": tag, "item": items} for tag, items in folders.items()],
    }


def main() -> None:
    os.makedirs(os.path.join(DOCS, "postman"), exist_ok=True)
    with open(os.path.join(DOCS, "openapi.yaml"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Generated by backend/scripts/gen_api_docs.py — do not edit by hand.\n")
        yaml.safe_dump(build_openapi(), fh, sort_keys=False, allow_unicode=True, width=120)
    with open(os.path.join(DOCS, "postman", "travelmate.postman_collection.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(build_postman(), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote docs/openapi.yaml and docs/postman/travelmate.postman_collection.json")


if __name__ == "__main__":
    main()
