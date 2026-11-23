"""add general vehicle expenses

Revision ID: 7d3e9a1b2c4f
Revises: c41f64a0d7c2
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "7d3e9a1b2c4f"
down_revision = "c41f64a0d7c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("vendor", sa.String(length=120), nullable=True),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["car_id"], ["car.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expense_car_id", "expense", ["car_id"])
    op.create_index("ix_expense_date", "expense", ["date"])
    op.create_index("ix_expense_category", "expense", ["category"])


def downgrade():
    op.drop_index("ix_expense_category", table_name="expense")
    op.drop_index("ix_expense_date", table_name="expense")
    op.drop_index("ix_expense_car_id", table_name="expense")
    op.drop_table("expense")
