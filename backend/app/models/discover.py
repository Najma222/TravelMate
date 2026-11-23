from sqlalchemy import UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


class DiscoverDestination(db.Model):
    __tablename__ = "discover_destinations"
    __table_args__ = (
        UniqueConstraint("name", "country", name="uq_discover_destinations_name_country"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(60), nullable=False)
    region = db.Column(db.String(60))
    description = db.Column(db.String(500))
    best_season = db.Column(db.String(60))
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    image_url = db.Column(db.String(255))
    tags = db.Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=text("true"))
