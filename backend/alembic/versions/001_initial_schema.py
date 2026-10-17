"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-09-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("customer", "staff", name="user_role"), nullable=False, server_default="customer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.Enum("car", "suv", "van", "truck", "bike", name="vehicle_type"), nullable=False),
        sa.Column("make", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("registration_no", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("price_per_day", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.Enum("available", "maintenance", "retired", name="vehicle_status"), nullable=False, server_default="available"),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "rental_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", "active", "completed", "cancelled", name="rental_status"), nullable=False, server_default="pending"),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("rejection_reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Original (incorrect) R1 attempt; replaced by a partial unique index in 002.
        sa.UniqueConstraint("customer_id", "status", name="uq_one_outstanding_per_customer"),
    )

    op.create_table(
        "proof_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("rental_requests.id"), nullable=False),
        sa.Column("kind", sa.Enum("aadhaar", "licence", name="proof_kind"), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("rental_requests.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.Enum("submitted", "approved", "rejected", "activated", "completed", "cancelled", name="audit_action"), nullable=False),
        sa.Column("from_status", sa.String(50), nullable=False),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("proof_documents")
    op.drop_table("rental_requests")
    op.drop_table("vehicles")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS audit_action")
    op.execute("DROP TYPE IF EXISTS proof_kind")
    op.execute("DROP TYPE IF EXISTS rental_status")
    op.execute("DROP TYPE IF EXISTS vehicle_status")
    op.execute("DROP TYPE IF EXISTS vehicle_type")
    op.execute("DROP TYPE IF EXISTS user_role")
