from sqlalchemy import CheckConstraint, Index, text

from app.extensions import db
from app.models._base import created_at_col, updated_at_col


class Itinerary(db.Model):
    __tablename__ = "itineraries"
    __table_args__ = (
        CheckConstraint("day_number >= 1", name="day_number_positive"),
        CheckConstraint("char_length(description) <= 2000", name="description_length"),
        CheckConstraint("estimated_cost >= 0", name="estimated_cost_nonnegative"),
        Index("ix_itineraries_trip_id_day_number_sort_order", "trip_id", "day_number",
              "sort_order"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False)
    day_number = db.Column(db.SmallInteger, nullable=False)
    activity_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    estimated_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    is_edited = db.Column(db.Boolean, nullable=False, default=False, server_default=text("false"))
    sort_order = db.Column(db.SmallInteger, nullable=False, default=0, server_default="0")
    created_at = created_at_col()
    updated_at = updated_at_col()
