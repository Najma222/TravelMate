from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db


class TripDay(db.Model):
    """Per-day title/summary. The calendar date is computed (D7), never stored."""
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "day_number", name="uq_trip_days_trip_id_day_number"),
        CheckConstraint("day_number >= 1", name="day_number_positive"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False)
    day_number = db.Column(db.SmallInteger, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    summary = db.Column(db.String(300))
    stop_id = db.Column(db.BigInteger, db.ForeignKey("trip_stops.id", ondelete="SET NULL"))
