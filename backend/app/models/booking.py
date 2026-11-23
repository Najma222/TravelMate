from sqlalchemy import CheckConstraint

from app.extensions import db
from app.models._base import created_at_col, updated_at_col

BOOKING_TYPES = ("hotel", "flight", "train", "bus")
BOOKING_STATUSES = ("Not Booked", "Pending", "Confirmed", "Cancelled")


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("booking_type IN ('hotel','flight','train','bus')", name="type_valid"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint(
            "status IN ('Not Booked','Pending','Confirmed','Cancelled')", name="status_valid"
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    booking_type = db.Column(db.String(10), nullable=False)
    provider = db.Column(db.String(100))
    booking_reference = db.Column(db.String(60))
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    booked_on = db.Column(db.Date)
    status = db.Column(db.String(12), nullable=False, default="Not Booked",
                       server_default="Not Booked")
    from_location = db.Column(db.String(100))
    to_location = db.Column(db.String(100))
    start_at = db.Column(db.DateTime(timezone=True))
    end_at = db.Column(db.DateTime(timezone=True))
    start_tz = db.Column(db.String(40))
    end_tz = db.Column(db.String(40))
    notes = db.Column(db.String(500))
    created_at = created_at_col()
    updated_at = updated_at_col()
