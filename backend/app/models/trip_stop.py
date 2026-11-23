from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db


class TripStop(db.Model):
    __tablename__ = "trip_stops"
    __table_args__ = (
        # DEFERRABLE INITIALLY DEFERRED so a reorder can swap positions in one transaction.
        UniqueConstraint("trip_id", "position", name="uq_trip_stops_trip_id_position",
                         deferrable=True, initially="DEFERRED"),
        CheckConstraint("source IN ('user','generated')", name="source_valid"),
        CheckConstraint("position >= 1", name="position_positive"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False)
    position = db.Column(db.SmallInteger, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    source = db.Column(db.String(10), nullable=False, default="user", server_default="user")
