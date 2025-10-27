from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20241010_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    asset_status_enum = sa.Enum("queued", "ready", "processing", "failed", name="assetstatus")
    job_status_enum = sa.Enum("queued", "running", "succeeded", "failed", name="jobstatus")
    job_type_enum = sa.Enum("thumbnails", "sidecar", name="jobtype")

    op.create_table(
        "organizations",
        sa.Column("org_id", sa.String(length=64), primary_key=True),
        sa.Column("plan", sa.String(length=32), nullable=True),
        sa.Column("limits_jsonb", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=255), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_uri", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("hash", sa.String(length=128), nullable=True),
        sa.Column("hash_quality", sa.String(length=16), nullable=True),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", asset_status_enum, nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sidecars",
        sa.Column("asset_id", sa.String(length=255), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=2048), nullable=False),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "thumbnails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(length=255), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("ts_ms", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.String(length=2048), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_id", "idx", name="uq_thumbnails_asset_idx"),
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("job_type", job_type_enum, nullable=False),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(length=255), sa.ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", job_status_enum, nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_jobs_org_id_asset_id", "jobs", ["org_id", "asset_id"])
    op.create_unique_constraint("uq_jobs_org_idempotency", "jobs", ["org_id", "idempotency_key"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(length=64), sa.ForeignKey("organizations.org_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("meta_jsonb", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_constraint("uq_jobs_org_idempotency", "jobs", type_="unique")
    op.drop_index("ix_jobs_org_id_asset_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("thumbnails")
    op.drop_table("sidecars")
    op.drop_table("assets")
    op.drop_table("organizations")

    sa.Enum(name="jobtype").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="jobstatus").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="assetstatus").drop(op.get_bind(), checkfirst=False)

