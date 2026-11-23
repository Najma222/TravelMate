from sqlalchemy import CheckConstraint, Index, func, text

from app.extensions import db
from app.models._base import created_at_col, updated_at_col

EXPENSE_CATEGORIES = ("transport", "accommodation", "food", "activities", "local_transport", "misc")


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("source IN ('user','n8n','booking')", name="source_valid"),
        CheckConstraint(
            "category IN ('transport','accommodation','food','activities','local_transport','misc')",
            name="category_valid",
        ),
        # At most one linked expense per booking (D10).
        Index("uq_expenses_booking_id", "booking_id", unique=True,
              postgresql_where=text("booking_id IS NOT NULL")),
        Index("ix_expenses_trip_id_category", "trip_id", "category"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("trips.id", ondelete="CASCADE"),
                        nullable=False)
    booking_id = db.Column(db.BigInteger, db.ForeignKey("bookings.id", ondelete="CASCADE"))
    category = db.Column(db.String(16), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    is_confirmed = db.Column(db.Boolean, nullable=False, default=False,
                             server_default=text("false"))
    expense_date = db.Column(db.Date, nullable=False, server_default=func.current_date())
    source = db.Column(db.String(10), nullable=False, default="user", server_default="user")
    created_at = created_at_col()
    updated_at = updated_at_col()
