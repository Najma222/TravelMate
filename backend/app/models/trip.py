from sqlalchemy import CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models._base import created_at_col, updated_at_col

TRIP_STATUSES = ("Draft", "Processing", "Completed", "Failed", "Cancelled")
CURRENCIES = ("INR", "USD", "EUR", "GBP", "NPR", "BDT", "AED")
TRANSPORT_PREFERENCES = ("any", "flight", "train", "bus", "car")
ACCOMMODATION_PREFERENCES = ("any", "hotel", "hostel", "homestay", "resort")


class Trip(db.Model):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        CheckConstraint("traveller_count BETWEEN 1 AND 50", name="traveller_count_range"),
        CheckConstraint("budget > 0", name="budget_positive"),
        CheckConstraint(
            "status IN ('Draft','Processing','Completed','Failed','Cancelled')",
            name="status_valid",
        ),
        Index("ix_trips_user_id_start_date", "user_id", "start_date"),
        Index("ix_trips_status_processing_started_at", "status", "processing_started_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False)
    origin = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    traveller_count = db.Column(db.SmallInteger, nullable=False, default=1, server_default="1")
    budget = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.CHAR(3), nullable=False, default="INR", server_default="INR")
    preferences = db.Column(db.String(500))
    transport_preference = db.Column(db.String(10), nullable=False, default="any",
                                     server_default="any")
    accommodation_preference = db.Column(db.String(10), nullable=False, default="any",
                                         server_default="any")
    status = db.Column(db.String(12), nullable=False, default="Draft", server_default="Draft")
    error_message = db.Column(db.String(500))
    generation_id = db.Column(UUID(as_uuid=True))
    processing_started_at = db.Column(db.DateTime(timezone=True))
    itinerary_stale = db.Column(db.Boolean, nullable=False, default=False,
                                server_default=text("false"))
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    weather = db.Column(JSONB)
    weather_message = db.Column(db.String(200))
    weather_updated_at = db.Column(db.DateTime(timezone=True))
    cover_image_url = db.Column(db.String(255))
    hero_quote = db.Column(db.String(200))
    hero_quote_author = db.Column(db.String(80))
    created_at = created_at_col()
    updated_at = updated_at_col()
