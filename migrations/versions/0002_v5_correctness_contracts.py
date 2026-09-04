"""中文：增加 V5 正确性、内容契约、快照撤销和可追溯字段。

English: Add V5 correctness, content-contract, snapshot-revocation, and provenance schema.

Revision ID: 0002_v5_correctness_contracts
Revises: 0001_v4_baseline
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_v5_correctness_contracts"
down_revision = "0001_v4_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """中文：以可空扩展、数据回填、约束收紧的顺序升级 V4 数据。

    English: Upgrade V4 data in nullable-expand, backfill, and constraint-tightening order.
    """

    for column in (
        sa.Column("contract_json", sa.JSON(), nullable=True),
        sa.Column("contract_schema_version", sa.String(64), nullable=True),
        sa.Column("contract_fingerprint", sa.String(64), nullable=True),
    ):
        op.add_column("sources", column)

    op.add_column(
        "documents",
        sa.Column("lifecycle_status", sa.String(32), nullable=True, server_default="active"),
    )
    op.add_column("documents", sa.Column("next_version_number", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE documents SET next_version_number = COALESCE("
            "(SELECT MAX(document_versions.version_number) + 1 FROM document_versions "
            "WHERE document_versions.document_id = documents.id), 2)"
        )
    )

    for column in (
        sa.Column("publication_status", sa.String(32), nullable=True, server_default="candidate"),
        sa.Column("resolved_contract_json", sa.JSON(), nullable=True),
        sa.Column("profile_decision_json", sa.JSON(), nullable=True),
        sa.Column("quality_report_id", sa.String(80), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
    ):
        op.add_column("document_versions", column)

    for column in (
        sa.Column("original_locator_json", sa.JSON(), nullable=True),
        sa.Column("display_locator_json", sa.JSON(), nullable=True),
        sa.Column("normalized_start", sa.Integer(), nullable=True),
        sa.Column("normalized_end", sa.Integer(), nullable=True),
        sa.Column("locator_mapping_quality", sa.String(32), nullable=True),
        sa.Column("structure_node_id", sa.String(80), nullable=True),
        sa.Column("structure_type", sa.String(64), nullable=True),
        sa.Column("hard_boundary_key", sa.String(256), nullable=True),
    ):
        op.add_column("chunks", column)

    for column in (
        sa.Column("execution_status", sa.String(32), nullable=True, server_default="queued"),
        sa.Column("job_type", sa.String(32), nullable=False, server_default="ingestion"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("ingestion_jobs", column)
    op.execute(
        sa.text(
            "UPDATE ingestion_jobs SET execution_status = CASE status "
            "WHEN 'pending' THEN 'queued' WHEN 'running' THEN 'running' "
            "WHEN 'succeeded' THEN 'succeeded' WHEN 'cancelled' THEN 'cancelled' "
            "WHEN 'stale' THEN 'stale' ELSE 'failed' END"
        )
    )
    op.create_index(
        "uq_job_tenant_type_idempotency",
        "ingestion_jobs",
        ["tenant_id", "job_type", "idempotency_key"],
        unique=True,
    )

    op.add_column("index_versions", sa.Column("manifest_schema_version", sa.String(64)))
    op.add_column("index_versions", sa.Column("manifest_fingerprint", sa.String(64)))
    op.add_column(
        "traces",
        sa.Column("trace_level", sa.String(32), nullable=False, server_default="summary"),
    )
    op.add_column("traces", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "traces",
        sa.Column(
            "redaction_version",
            sa.String(64),
            nullable=False,
            server_default="trace-redaction-v1",
        ),
    )
    op.add_column("traces", sa.Column("snapshot_id", sa.String(80)))

    op.create_table(
        "quality_reports",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.String(80), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column(
            "document_version_id",
            sa.String(80),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("degradation_codes", sa.JSON(), nullable=False),
        sa.Column("validator_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_version_id", name="uq_quality_report_version"),
    )
    for name in ("tenant_id", "document_id", "document_version_id"):
        op.create_index(f"ix_quality_reports_{name}", "quality_reports", [name])
    op.create_table(
        "tenant_knowledge_state",
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("revocation_epoch", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "query_snapshots",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("index_version_id", sa.String(80), nullable=False),
        sa.Column("index_manifest_fingerprint", sa.String(64), nullable=False),
        sa.Column("authorization_fingerprint", sa.String(64), nullable=False),
        sa.Column("captured_revocation_epoch", sa.Integer(), nullable=False),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_query_snapshots_tenant_id", "query_snapshots", ["tenant_id"])
    op.create_index("ix_query_snapshots_user_id", "query_snapshots", ["user_id"])
    op.create_index("ix_snapshot_expiry", "query_snapshots", ["tenant_id", "status", "expires_at"])
    op.create_index(
        "ix_snapshot_index",
        "query_snapshots",
        ["tenant_id", "index_version_id", "status"],
    )
    op.create_table(
        "query_snapshot_document_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_id",
            sa.String(80),
            sa.ForeignKey("query_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.String(80),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id"), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "document_version_id",
            name="uq_snapshot_document_version",
        ),
    )
    for name in ("snapshot_id", "document_version_id", "source_id"):
        op.create_index(
            f"ix_query_snapshot_document_versions_{name}",
            "query_snapshot_document_versions",
            [name],
        )
    op.create_table(
        "revocations",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(80), nullable=False),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "epoch", name="uq_revocation_tenant_epoch"),
    )
    op.create_index("ix_revocations_tenant_id", "revocations", ["tenant_id"])
    op.create_index("ix_revocation_scope", "revocations", ["tenant_id", "scope_type", "scope_id"])
    op.create_table(
        "operational_events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("tenant_id", sa.String(80), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("from_state", sa.String(32)),
        sa.Column("to_state", sa.String(32)),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operational_events_tenant_id", "operational_events", ["tenant_id"])
    op.create_index(
        "ix_operational_events_tenant_time",
        "operational_events",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    """中文：按依赖逆序移除 V5 扩展，恢复 V4 基线。

    English: Remove V5 extensions in dependency order and restore the V4 baseline.
    """

    for table_name in (
        "operational_events",
        "revocations",
        "query_snapshot_document_versions",
        "query_snapshots",
        "tenant_knowledge_state",
        "quality_reports",
    ):
        op.drop_table(table_name)
    op.drop_column("traces", "snapshot_id")
    op.drop_column("traces", "redaction_version")
    op.drop_column("traces", "expires_at")
    op.drop_column("traces", "trace_level")
    op.drop_column("index_versions", "manifest_fingerprint")
    op.drop_column("index_versions", "manifest_schema_version")
    op.drop_index("uq_job_tenant_type_idempotency", table_name="ingestion_jobs")
    for name in (
        "dead_lettered_at",
        "max_attempts",
        "idempotency_key",
        "job_type",
        "execution_status",
    ):
        op.drop_column("ingestion_jobs", name)
    for name in (
        "hard_boundary_key",
        "structure_type",
        "structure_node_id",
        "locator_mapping_quality",
        "normalized_end",
        "normalized_start",
        "display_locator_json",
        "original_locator_json",
    ):
        op.drop_column("chunks", name)
    for name in (
        "provenance_json",
        "quality_report_id",
        "profile_decision_json",
        "resolved_contract_json",
        "publication_status",
    ):
        op.drop_column("document_versions", name)
    op.drop_column("documents", "next_version_number")
    op.drop_column("documents", "lifecycle_status")
    for name in ("contract_fingerprint", "contract_schema_version", "contract_json"):
        op.drop_column("sources", name)
