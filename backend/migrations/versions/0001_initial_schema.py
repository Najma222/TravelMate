"""initial schema: 11 tables (AGENTS.md §4)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-23

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"),
                     nullable=False)


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(100), nullable=False),
        sa.Column("role", sa.String(10), server_default="user", nullable=False),
        sa.Column("avatar_url", sa.String(255)),
        sa.Column("notify_email", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notify_telegram", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("telegram_chat_id", sa.String(40)),
        sa.Column("session_nonce", sa.String(32), nullable=False),
        sa.Column("ui_prefs", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.CheckConstraint("role IN ('user','admin')", name="ck_users_role_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "trips",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("origin", sa.String(100), nullable=False),
        sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("traveller_count", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("budget", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), server_default="INR", nullable=False),
        sa.Column("preferences", sa.String(500)),
        sa.Column("transport_preference", sa.String(10), server_default="any", nullable=False),
        sa.Column("accommodation_preference", sa.String(10), server_default="any", nullable=False),
        sa.Column("status", sa.String(12), server_default="Draft", nullable=False),
        sa.Column("error_message", sa.String(500)),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("itinerary_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("weather", postgresql.JSONB()),
        sa.Column("weather_message", sa.String(200)),
        sa.Column("weather_updated_at", sa.DateTime(timezone=True)),
        sa.Column("cover_image_url", sa.String(255)),
        sa.Column("hero_quote", sa.String(200)),
        sa.Column("hero_quote_author", sa.String(80)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("end_date >= start_date", name="ck_trips_dates_ordered"),
        sa.CheckConstraint("traveller_count BETWEEN 1 AND 50", name="ck_trips_traveller_count_range"),
        sa.CheckConstraint("budget > 0", name="ck_trips_budget_positive"),
        sa.CheckConstraint("status IN ('Draft','Processing','Completed','Failed','Cancelled')",
                           name="ck_trips_status_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_trips_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_trips"),
    )
    op.create_index("ix_trips_user_id_start_date", "trips", ["user_id", "start_date"])
    op.create_index("ix_trips_status_processing_started_at", "trips",
                    ["status", "processing_started_at"])

    op.create_table(
        "trip_stops",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("source", sa.String(10), server_default="user", nullable=False),
        sa.CheckConstraint("source IN ('user','generated')", name="ck_trip_stops_source_valid"),
        sa.CheckConstraint("position >= 1", name="ck_trip_stops_position_positive"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_trip_stops_trip_id_trips"),
        sa.PrimaryKeyConstraint("id", name="pk_trip_stops"),
        sa.UniqueConstraint("trip_id", "position", name="uq_trip_stops_trip_id_position",
                            deferrable=True, initially="DEFERRED"),
    )

    op.create_table(
        "trip_days",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("day_number", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(300)),
        sa.Column("stop_id", sa.BigInteger()),
        sa.CheckConstraint("day_number >= 1", name="ck_trip_days_day_number_positive"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_trip_days_trip_id_trips"),
        sa.ForeignKeyConstraint(["stop_id"], ["trip_stops.id"], ondelete="SET NULL",
                                name="fk_trip_days_stop_id_trip_stops"),
        sa.PrimaryKeyConstraint("id", name="pk_trip_days"),
        sa.UniqueConstraint("trip_id", "day_number", name="uq_trip_days_trip_id_day_number"),
    )

    op.create_table(
        "itineraries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("day_number", sa.SmallInteger(), nullable=False),
        sa.Column("activity_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("location", sa.String(200)),
        sa.Column("start_time", sa.Time()),
        sa.Column("end_time", sa.Time()),
        sa.Column("estimated_cost", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("is_edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("day_number >= 1", name="ck_itineraries_day_number_positive"),
        sa.CheckConstraint("char_length(description) <= 2000",
                           name="ck_itineraries_description_length"),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_itineraries_estimated_cost_nonnegative"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_itineraries_trip_id_trips"),
        sa.PrimaryKeyConstraint("id", name="pk_itineraries"),
    )
    op.create_index("ix_itineraries_trip_id_day_number_sort_order", "itineraries",
                    ["trip_id", "day_number", "sort_order"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_type", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("booking_reference", sa.String(60)),
        sa.Column("amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("booked_on", sa.Date()),
        sa.Column("status", sa.String(12), server_default="Not Booked", nullable=False),
        sa.Column("from_location", sa.String(100)),
        sa.Column("to_location", sa.String(100)),
        sa.Column("start_at", sa.DateTime(timezone=True)),
        sa.Column("end_at", sa.DateTime(timezone=True)),
        sa.Column("start_tz", sa.String(40)),
        sa.Column("end_tz", sa.String(40)),
        sa.Column("notes", sa.String(500)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("booking_type IN ('hotel','flight','train','bus')",
                           name="ck_bookings_type_valid"),
        sa.CheckConstraint("amount >= 0", name="ck_bookings_amount_nonnegative"),
        sa.CheckConstraint("status IN ('Not Booked','Pending','Confirmed','Cancelled')",
                           name="ck_bookings_status_valid"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_bookings_trip_id_trips"),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
    )
    op.create_index("ix_bookings_trip_id", "bookings", ["trip_id"])

    op.create_table(
        "expenses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("booking_id", sa.BigInteger()),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("description", sa.String(200)),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("expense_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("source", sa.String(10), server_default="user", nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        sa.CheckConstraint("source IN ('user','n8n','booking')", name="ck_expenses_source_valid"),
        sa.CheckConstraint(
            "category IN ('transport','accommodation','food','activities','local_transport','misc')",
            name="ck_expenses_category_valid"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_expenses_trip_id_trips"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE",
                                name="fk_expenses_booking_id_bookings"),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
    )
    op.create_index("uq_expenses_booking_id", "expenses", ["booking_id"], unique=True,
                    postgresql_where=sa.text("booking_id IS NOT NULL"))
    op.create_index("ix_expenses_trip_id_category", "expenses", ["trip_id", "category"])

    op.create_table(
        "packing_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("is_packed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True)),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("source", sa.String(10), server_default="user", nullable=False),
        _ts("created_at"),
        sa.CheckConstraint("source IN ('user','default','auto')", name="ck_packing_items_source_valid"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_packing_items_trip_id_trips"),
        sa.PrimaryKeyConstraint("id", name="pk_packing_items"),
    )
    op.create_index("ix_packing_items_trip_id", "packing_items", ["trip_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("notification_type", sa.String(30), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("channels", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_status", sa.String(10), server_default="pending", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        sa.CheckConstraint("delivery_status IN ('sent','failed','pending')",
                           name="ck_notifications_delivery_status_valid"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE",
                                name="fk_notifications_trip_id_trips"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_notifications_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.UniqueConstraint("trip_id", "notification_type", "scheduled_for",
                            name="uq_notifications_trip_id_notification_type_scheduled_for"),
    )
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])

    op.create_table(
        "discover_destinations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country", sa.String(60), nullable=False),
        sa.Column("region", sa.String(60)),
        sa.Column("description", sa.String(500)),
        sa.Column("best_season", sa.String(60)),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("image_url", sa.String(255)),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_discover_destinations"),
        sa.UniqueConstraint("name", "country", name="uq_discover_destinations_name_country"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("trip_id", sa.BigInteger()),
        sa.Column("actor", sa.String(10), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("request_id", sa.String(36)),
        sa.Column("ip", postgresql.INET()),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_audit_logs_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_action_created_at", "audit_logs", ["action", "created_at"])


def downgrade():
    for table in ("audit_logs", "discover_destinations", "notifications", "packing_items",
                  "expenses", "bookings", "itineraries", "trip_days", "trip_stops", "trips",
                  "users"):
        op.drop_table(table)
