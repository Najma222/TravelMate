from sqlalchemy import CheckConstraint, text

from app.extensions import db
from app.models._base import created_at_col


class PackingItem(db.Model):
    __tablename__ = "packing_items"
    __table_args__ = (
        CheckConstraint("source IN ('user','default','auto')", name="source_valid"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(300))
    is_packed = db.Column(db.Boolean, nullable=False, default=False, server_default=text("false"))
    remind_at = db.Column(db.DateTime(timezone=True))
    sort_order = db.Column(db.SmallInteger, nullable=False, default=0, server_default="0")
    source = db.Column(db.String(10), nullable=False, default="user", server_default="user")
    created_at = created_at_col()
