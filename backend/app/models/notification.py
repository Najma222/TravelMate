from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.models._base import created_at_col

DELIVERY_STATUSES = ("sent", "failed", "pending")
NOTIFICATION_CHANNELS = ("email", "telegram", "in_app")


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("trip_id", "notification_type", "scheduled_for",
                         name="uq_notifications_trip_id_notification_type_scheduled_for"),
        CheckConstraint("delivery_status IN ('sent','failed','pending')",
                        name="delivery_status_valid"),
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False)
    notification_type = db.Column(db.String(30), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    channels = db.Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    # D9: calendar date in APP_TIMEZONE (dedupe key), not a timestamp.
    scheduled_for = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True))
    delivery_status = db.Column(db.String(10), nullable=False, default="pending",
                                server_default="pending")
    read_at = db.Column(db.DateTime(timezone=True))
    created_at = created_at_col()
