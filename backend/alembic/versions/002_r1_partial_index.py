"""enforce R1 via partial unique index; add proof/audit constraints

The `submitted` audit action lives in 001 rather than being added here: introducing
it would force a downgrade to rebuild the enum, which cannot cast rows that already
carry the value. Keeping it in the initial schema keeps the migration reversible
against a database that contains data.

Replaces the original UNIQUE (customer_id, status) constraint, which was wrong:
it would forbid a customer from ever holding two rejected/completed rows, while
still permitting two pending ones. The partial unique index scoped to the
outstanding statuses expresses R1 exactly and closes the check-then-insert race.

Revision ID: 002
Revises: 001
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENTAL_STATUSES = ("pending", "approved", "rejected", "active", "completed", "cancelled")


def upgrade() -> None:
    # 1. Drop the incorrect constraint from 001.
    op.drop_constraint("uq_one_outstanding_per_customer", "rental_requests", type_="unique")

    # 2. R1: at most one pending/approved/active rental per customer.
    op.create_index(
        "uq_rentals_one_outstanding_per_customer",
        "rental_requests",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'approved', 'active')"),
    )

    # 3. R4: one artifact per kind per request.
    op.create_unique_constraint(
        "uq_proof_one_per_kind_per_request", "proof_documents", ["request_id", "kind"]
    )

    # 4. Support the overlap scan and the approval queue ordering.
    op.create_index("ix_rentals_vehicle_window", "rental_requests", ["vehicle_id", "start_date", "end_date"])
    op.create_index("ix_rentals_status", "rental_requests", ["status"])

    # 6. Cascade proof/audit deletes with their request.
    op.drop_constraint("proof_documents_request_id_fkey", "proof_documents", type_="foreignkey")
    op.create_foreign_key(
        "proof_documents_request_id_fkey",
        "proof_documents",
        "rental_requests",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("audit_events_request_id_fkey", "audit_events", type_="foreignkey")
    op.create_foreign_key(
        "audit_events_request_id_fkey",
        "audit_events",
        "rental_requests",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_proof_documents_request_id", "proof_documents", ["request_id"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_proof_documents_request_id", table_name="proof_documents")
    op.drop_constraint("audit_events_request_id_fkey", "audit_events", type_="foreignkey")
    op.create_foreign_key(
        "audit_events_request_id_fkey", "audit_events", "rental_requests", ["request_id"], ["id"]
    )
    op.drop_constraint("proof_documents_request_id_fkey", "proof_documents", type_="foreignkey")
    op.create_foreign_key(
        "proof_documents_request_id_fkey", "proof_documents", "rental_requests", ["request_id"], ["id"]
    )
    op.drop_index("ix_rentals_status", table_name="rental_requests")
    op.drop_index("ix_rentals_vehicle_window", table_name="rental_requests")
    op.drop_constraint("uq_proof_one_per_kind_per_request", "proof_documents", type_="unique")
    op.drop_index("uq_rentals_one_outstanding_per_customer", table_name="rental_requests")

    op.create_unique_constraint(
        "uq_one_outstanding_per_customer", "rental_requests", ["customer_id", "status"]
    )