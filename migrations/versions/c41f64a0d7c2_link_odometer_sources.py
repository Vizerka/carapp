"""link odometer entries to fuel and service sources

Revision ID: c41f64a0d7c2
Revises: 838b36e7ff82
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "c41f64a0d7c2"
down_revision = "838b36e7ff82"
branch_labels = None
depends_on = None


def _backfill_unambiguous_sources() -> None:
    """Łączy tylko stare wpisy, dla których istnieje jeden pewny kandydat."""
    bind = op.get_bind()

    fuels = bind.execute(sa.text(
        "SELECT id, car_id, date, km FROM fuel_entry ORDER BY id"
    )).mappings()
    for fuel in fuels:
        candidates = bind.execute(sa.text(
            "SELECT id FROM odometer_entry "
            "WHERE car_id = :car_id AND date = :date AND km = :km "
            "AND source_type IS NULL AND source_id IS NULL "
            "AND note LIKE 'Tankowanie%'"
        ), fuel).scalars().all()
        if len(candidates) == 1:
            bind.execute(sa.text(
                "UPDATE odometer_entry SET source_type = 'fuel', source_id = :source_id "
                "WHERE id = :odo_id"
            ), {"source_id": fuel["id"], "odo_id": candidates[0]})

    services = bind.execute(sa.text(
        "SELECT id, car_id, date, km FROM service_entry "
        "WHERE km IS NOT NULL ORDER BY id"
    )).mappings()
    for service in services:
        candidates = bind.execute(sa.text(
            "SELECT id FROM odometer_entry "
            "WHERE car_id = :car_id AND date = :date AND km = :km "
            "AND source_type IS NULL AND source_id IS NULL "
            "AND note LIKE 'Serwis:%'"
        ), service).scalars().all()
        if len(candidates) == 1:
            bind.execute(sa.text(
                "UPDATE odometer_entry SET source_type = 'service', source_id = :source_id "
                "WHERE id = :odo_id"
            ), {"source_id": service["id"], "odo_id": candidates[0]})


def upgrade():
    with op.batch_alter_table("odometer_entry") as batch_op:
        batch_op.add_column(sa.Column("source_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))

    _backfill_unambiguous_sources()

    with op.batch_alter_table("odometer_entry") as batch_op:
        batch_op.create_index("ix_odometer_entry_source_type", ["source_type"])
        batch_op.create_index("ix_odometer_entry_source_id", ["source_id"])
        batch_op.create_unique_constraint(
            "uq_odometer_source", ["source_type", "source_id"]
        )
        batch_op.create_check_constraint(
            "ck_odometer_source_pair",
            "(source_type IS NULL AND source_id IS NULL) OR "
            "(source_type IS NOT NULL AND source_id IS NOT NULL)",
        )


def downgrade():
    with op.batch_alter_table("odometer_entry") as batch_op:
        batch_op.drop_constraint("ck_odometer_source_pair", type_="check")
        batch_op.drop_constraint("uq_odometer_source", type_="unique")
        batch_op.drop_index("ix_odometer_entry_source_id")
        batch_op.drop_index("ix_odometer_entry_source_type")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_type")
