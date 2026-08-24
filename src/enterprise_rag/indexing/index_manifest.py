"""中文：本模块负责实现“索引清单”相关功能。

English: Create, persist, and verify immutable index manifests and artifact checksums.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.models import IndexManifest
from enterprise_rag.indexing.models import IndexBuildPlan


def create_manifest(plan: IndexBuildPlan, artifacts: tuple[Path, ...]) -> IndexManifest:
    """中文：该函数或方法负责“创建清单”相关处理。

    English: Create a manifest from staged artifacts after every component has been written.
    """

    if not artifacts:
        raise ValueError("an index manifest requires at least one artifact")
    # 中文：变量 `common_parent` 用于保存“`common``parent`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Common parent defines portable relative artifact paths.
    common_parent = Path(artifacts[0]).parent
    # 中文：变量 `checksums` 用于保存“`checksums`”相关数据；其精确定义与约束见下方英文说明。
    # English: Checksum mapping detects partial writes and corruption before publication
    #   or recovery.
    checksums = {
        str(path.relative_to(common_parent)): content_sha256(path.read_bytes())
        for path in sorted(artifacts)
    }
    return IndexManifest(
        index_version_id=plan.index_version_id,
        tenant_id=plan.tenant_id,
        chunk_ids=tuple(entry.chunk_id for entry in plan.entries),
        embedding_fingerprint=plan.embedding_fingerprint,
        chunker_version=plan.chunker_version,
        config_fingerprint=plan.config_fingerprint,
        artifact_checksums=checksums,
    )


def save_manifest(manifest: IndexManifest, directory: Path) -> Path:
    """中文：该函数或方法负责“保存清单”相关处理。

    English: Serialize a manifest deterministically after component checksums are final.
    """

    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Datetime is normalized to ISO 8601 for portable JSON.
    payload = asdict(manifest)
    payload["created_at"] = manifest.created_at.isoformat()
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest_path


def load_manifest(directory: Path) -> IndexManifest:
    """中文：该函数或方法负责“加载清单”相关处理。

    English: Load a manifest and restore immutable tuple fields.
    """

    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Manifest is required for every staging reload and process recovery.
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return IndexManifest(
        index_version_id=str(payload["index_version_id"]),
        tenant_id=str(payload["tenant_id"]),
        chunk_ids=tuple(payload["chunk_ids"]),
        embedding_fingerprint=str(payload["embedding_fingerprint"]),
        chunker_version=str(payload["chunker_version"]),
        config_fingerprint=str(payload["config_fingerprint"]),
        artifact_checksums={
            str(path): str(checksum) for path, checksum in payload["artifact_checksums"].items()
        },
        created_at=datetime.fromisoformat(payload["created_at"]),
    )


def verify_manifest(directory: Path, manifest: IndexManifest) -> None:
    """中文：该函数或方法负责“验证清单”相关处理。

    English: Raise when a required artifact is absent or differs from its recorded checksum.
    """

    for relative_path, expected_checksum in manifest.artifact_checksums.items():
        # 中文：变量 `artifact_path` 用于保存“制品`path`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Relative path is resolved under the exact snapshot directory.
        artifact_path = (directory / relative_path).resolve()
        try:
            artifact_path.relative_to(directory.resolve())
        except ValueError as exc:
            raise ValueError("manifest artifact path escapes snapshot directory") from exc
        if not artifact_path.is_file():
            raise ValueError(f"manifest artifact is missing: {relative_path}")
        # 中文：变量 `actual_checksum` 用于保存“`actual`校验和”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Actual checksum validates bytes rather than trusting file size or
        #   modification time.
        actual_checksum = content_sha256(artifact_path.read_bytes())
        if actual_checksum != expected_checksum:
            raise ValueError(f"manifest checksum mismatch: {relative_path}")
