from sqlalchemy import Index, text
from sqlalchemy.dialects.postgresql import INET, JSONB

from app.extensions import db
from app.models._base import created_at_col


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="SET NULL"))
    trip_id = db.Column(db.BigInteger)  # intentionally no FK: audit rows outlive trips
    actor = db.Column(db.String(10), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    outcome = db.Column(db.String(10), nullable=False)
    request_id = db.Column(db.String(36))
    ip = db.Column(INET)
    meta = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at = created_at_col()
