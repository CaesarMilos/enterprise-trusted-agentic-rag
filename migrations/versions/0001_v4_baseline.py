"""中文：冻结可被 V5 安全接管的 V4 数据库基线。

English: Freeze the V4 database baseline that V5 may safely adopt.

Revision ID: 0001_v4_baseline
Revises: None
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_v4_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """中文：创建 V4 的八张正式业务表和索引。

    English: Create the eight V4 business tables and their indexes.
    """

    op.create_table(
        "tenants",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content_profile", sa.String(32), nullable=False),
        sa.Column("chunk_strategy_override", sa.String(128)),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("allowed_group_ids", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"])
    op.create_index("ix_sources_tenant_active", "sources", ["tenant_id", "is_active"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("active_version_id", sa.String(80)),
        sa.Column("lifecycle_generation", sa.Integer(), nullable=False),
        sa.Column("delete_requested_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_tenant_status", "documents", ["tenant_id", "status"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.String(80), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("media_type", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("ingestion_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )
    for name in ("tenant_id", "document_id", "source_id", "content_hash"):
        op.create_index(f"ix_document_versions_{name}", "document_versions", [name])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("document_id", sa.String(80), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column(
            "document_version_id",
            sa.String(80),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("previous_chunk_id", sa.String(80)),
        sa.Column("next_chunk_id", sa.String(80)),
        sa.Column("boundary_reason", sa.String(64), nullable=False),
        sa.Column("chunker_version", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("document_version_id", "ordinal", name="uq_chunk_version_ordinal"),
    )
    for name in ("tenant_id", "source_id", "document_id", "document_version_id"):
        op.create_index(f"ix_chunks_{name}", "chunks", [name])
    op.create_index("ix_chunks_scope", "chunks", ["tenant_id", "source_id", "document_id"])
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.String(80), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column(
            "document_version_id",
            sa.String(80),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("document_generation_snapshot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(255)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_nonnegative"),
    )
    for name in ("tenant_id", "document_id", "document_version_id"):
        op.create_index(f"ix_ingestion_jobs_{name}", "ingestion_jobs", [name])
    op.create_index("ix_jobs_claim", "ingestion_jobs", ["status", "lease_expires_at", "created_at"])
    op.create_table(
        "index_versions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("config_fingerprint", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_index_versions_tenant_id", "index_versions", ["tenant_id"])
    op.create_index(
        "ix_index_tenant_status_created",
        "index_versions",
        ["tenant_id", "status", "created_at"],
    )
    op.create_table(
        "traces",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("index_version_id", sa.String(80)),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_traces_tenant_id", "traces", ["tenant_id"])
    op.create_index("ix_traces_user_id", "traces", ["user_id"])
    op.create_index("ix_traces_tenant_user", "traces", ["tenant_id", "user_id", "created_at"])


def downgrade() -> None:
    """中文：按外键依赖逆序删除 V4 基线表。

    English: Drop V4 baseline tables in reverse foreign-key order.
    """

    for table_name in (
        "traces",
        "index_versions",
        "ingestion_jobs",
        "chunks",
        "document_versions",
        "documents",
        "sources",
        "tenants",
    ):
        op.drop_table(table_name)
