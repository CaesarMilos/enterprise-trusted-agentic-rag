"""中文：本模块负责实现“资料源目录”相关功能。

English: Build and query source profiles derived from the same immutable index build plan.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from enterprise_rag.domain.models import RetrievalScope
from enterprise_rag.indexing.models import IndexBuildPlan, SourceProfile


class SourceCatalogBuilder:
    """中文：该类用于表示或实现“资料源目录构建器（SourceCatalogBuilder）”的职责。

    English: Serialize deterministic source profiles into a staging directory.
    """

    def build(self, plan: IndexBuildPlan, directory: Path) -> tuple[Path, ...]:
        """中文：该函数或方法负责“构建目标对象”相关处理。

        English: Write source profiles aligned with the plan's active source content.
        """

        directory.mkdir(parents=True, exist_ok=True)
        # 中文：变量 `artifact` 用于保存“制品”相关数据；其精确定义与约束见下方英文说明。
        # English: Catalog contains no chunk bodies and remains cheap to load for every
        #   request.
        artifact = {
            "index_version_id": plan.index_version_id,
            "profiles": [asdict(profile) for profile in plan.source_profiles],
        }
        artifact_path = directory / "source_catalog.json"
        artifact_path.write_text(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return (artifact_path,)


class PersistentSourceCatalog:
    """中文：该类用于表示或实现“持久化资料源目录（PersistentSourceCatalog）”的职责。

    English: Expose only profiles authorized by an exact retrieval scope.
    """

    def __init__(self, version_id: str, profiles: tuple[SourceProfile, ...]) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store one immutable catalog snapshot.
        """

        # 中文：变量 `_version_id` 用于保存“版本标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Snapshot identifier prevents routing against a different content version.
        self._version_id = version_id
        # 中文：变量 `_profiles` 用于保存“资料源画像”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Profiles are sorted and frozen by the build plan.
        self._profiles = profiles

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable snapshot identifier.
        """

        return self._version_id

    @classmethod
    def load(cls, directory: Path) -> PersistentSourceCatalog:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Reload a source catalog and validate duplicate source identifiers.
        """

        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: JSON artifact is safe, compact, and independently reloadable.
        payload = json.loads((directory / "source_catalog.json").read_text(encoding="utf-8"))
        # 中文：变量 `profiles` 用于保存“资料源画像”相关数据；其精确定义与约束见下方英文说明。
        # English: JSON arrays are normalized to immutable tuples expected by domain models.
        profiles = tuple(
            SourceProfile(
                source_id=item["source_id"],
                tenant_id=item["tenant_id"],
                name=item["name"],
                description=item["description"],
                profile_terms=tuple(item["profile_terms"]),
                chunk_count=int(item["chunk_count"]),
            )
            for item in payload["profiles"]
        )
        # 中文：本步骤涉及资料源画像、路由，具体约束见下方英文说明。
        # English: Duplicate profiles would make routing explanations ambiguous.
        if len({profile.source_id for profile in profiles}) != len(profiles):
            raise ValueError("source catalog contains duplicate source IDs")
        return cls(str(payload["index_version_id"]), profiles)

    def profiles(self, scope: RetrievalScope) -> tuple[dict[str, object], ...]:
        """中文：该函数或方法负责“资料源画像”相关处理。

        English: Return authorized profile mappings suitable for source routing.
        """

        if scope.index_version_id and scope.index_version_id != self._version_id:
            raise ValueError("retrieval scope and source catalog versions differ")
        return tuple(
            {
                "source_id": profile.source_id,
                "name": profile.name,
                "description": profile.description,
                "profile_terms": profile.profile_terms,
                "chunk_count": profile.chunk_count,
            }
            for profile in self._profiles
            if profile.tenant_id == scope.tenant_id and profile.source_id in scope.source_ids
        )
