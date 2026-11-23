"""add service items, tires, document links and modifications

Revision ID: a82f1c9d4e77
Revises: 7d3e9a1b2c4f
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "a82f1c9d4e77"
down_revision = "7d3e9a1b2c4f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "modification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_date", sa.Date(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["car_id"], ["car.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_modification_car_id", "modification", ["car_id"])
    op.create_index("ix_modification_status", "modification", ["status"])

    op.create_table(
        "tire_set",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("season", sa.String(length=16), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("aspect_ratio", sa.Integer(), nullable=True),
        sa.Column("diameter", sa.Integer(), nullable=True),
        sa.Column("dot", sa.String(length=16), nullable=True),
        sa.Column("rim", sa.String(length=120), nullable=True),
        sa.Column("recommended_pressure", sa.String(length=64), nullable=True),
        sa.Column("storage_location", sa.String(length=160), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["car_id"], ["car.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tire_set_car_id", "tire_set", ["car_id"])

    op.create_table(
        "service_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("part_number", sa.String(length=120), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["service_id"], ["service_entry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_item_service_id", "service_item", ["service_id"])
    op.create_index("ix_service_item_part_number", "service_item", ["part_number"])

    op.create_table(
        "modification_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("modification_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["modification_id"], ["modification.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_modification_task_modification_id", "modification_task", ["modification_id"]
    )

    op.create_table(
        "tire_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tire_set_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("km", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("tread_fl", sa.Numeric(4, 1), nullable=True),
        sa.Column("tread_fr", sa.Numeric(4, 1), nullable=True),
        sa.Column("tread_rl", sa.Numeric(4, 1), nullable=True),
        sa.Column("tread_rr", sa.Numeric(4, 1), nullable=True),
        sa.Column("pressure", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["tire_set_id"], ["tire_set.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tire_event_tire_set_id", "tire_event", ["tire_set_id"])
    op.create_index("ix_tire_event_date", "tire_event", ["date"])

    op.create_table(
        "document_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "target_type", "target_id", name="uq_document_link_target"
        ),
    )
    op.create_index("ix_document_link_document_id", "document_link", ["document_id"])
    op.create_index("ix_document_link_target_type", "document_link", ["target_type"])
    op.create_index("ix_document_link_target_id", "document_link", ["target_id"])


def downgrade():
    op.drop_table("document_link")
    op.drop_table("tire_event")
    op.drop_table("modification_task")
    op.drop_table("service_item")
    op.drop_table("tire_set")
    op.drop_table("modification")
