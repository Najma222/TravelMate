"""Shared column helpers for models."""
from sqlalchemy import func

from app.extensions import db


def created_at_col():
    return db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_col():
    return db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now(),
                     onupdate=func.now())
