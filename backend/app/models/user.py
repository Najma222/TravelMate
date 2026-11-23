from sqlalchemy import CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.models._base import created_at_col, updated_at_col


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("role IN ('user','admin')", name="role_valid"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="user", server_default="user")
    avatar_url = db.Column(db.String(255))
    notify_email = db.Column(db.Boolean, nullable=False, default=True, server_default=text("true"))
    notify_telegram = db.Column(db.Boolean, nullable=False, default=False,
                                server_default=text("false"))
    telegram_chat_id = db.Column(db.String(40))
    session_nonce = db.Column(db.String(32), nullable=False)
    ui_prefs = db.Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at = created_at_col()
    updated_at = updated_at_col()
