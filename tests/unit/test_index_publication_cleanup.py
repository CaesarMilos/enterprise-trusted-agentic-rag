"""中文：验证候选索引在数据库激活失败后不会留下 Staging 或孤儿发布目录。

English: Verify failed database activation leaves neither staging nor orphan publication dirs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_rag.core.exceptions import IndexBuildError
from enterprise_rag.indexing.index_coordinator import IndexCoordinator
from enterprise_rag.indexing.models import IndexBuildPlan


class _FakeEmbeddingService:
    """中文：为目录状态测试提供不依赖数值库的占位向量结果。

    English: Provide a placeholder vector result without numerical runtime dependencies.
    """

    def embed(self, texts: tuple[str, ...]) -> object:
        """中文：保持调用协议并返回仅供假构建器接收的对象。

        English: Preserve the call protocol and return an object consumed only by fake builders.
        """

        del texts
        return object()


class _FakeBuilder:
    """中文：写入一个唯一制品，使真实 Manifest 创建逻辑仍被执行。

    English: Write one unique artifact so real manifest creation still executes.
    """

    def __init__(self, name: str) -> None:
        """中文：保存当前组件的唯一文件名。

        English: Store the unique filename for this component.
        """

        self._name = name

    def build(self, plan: object, *arguments: object) -> tuple[Path, ...]:
        """中文：兼容向量和非向量构建签名，并写入确定性测试制品。

        English: Accept vector/non-vector signatures and write a deterministic test artifact.
        """

        del plan
        directory = next(item for item in reversed(arguments) if isinstance(item, Path))
        artifact = directory / self._name
        artifact.write_text(self._name, encoding="utf-8")
        return (artifact,)


def test_activation_failure_removes_published_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中文：目录原子替换后若 CAS 失败，必须删除精确候选并保留旧索引职责。

    English: After directory publication, a failed CAS must remove the exact candidate.
    """

    coordinator = IndexCoordinator(
        tmp_path,
        _FakeEmbeddingService(),  # type: ignore[arg-type]
        _FakeBuilder("dense.bin"),  # type: ignore[arg-type]
        _FakeBuilder("bm25.json"),  # type: ignore[arg-type]
        _FakeBuilder("catalog.json"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(IndexCoordinator, "_validate_reloaded", staticmethod(lambda *_: None))
    plan = IndexBuildPlan(
        index_version_id="index-new",
        tenant_id="tenant-a",
        entries=(),
        source_profiles=(),
        chunker_version="v4-test",
        embedding_fingerprint="embedding-test",
        config_fingerprint="config-test",
    )

    def reject_activation(_: str) -> None:
        """中文：模拟数据库 CAS 或生命周期检查失败。

        English: Simulate a failed database CAS or lifecycle check.
        """

        raise RuntimeError("activation rejected")

    with pytest.raises(IndexBuildError):
        coordinator.build_and_publish(plan, reject_activation)

    assert not (tmp_path / "tenant-a" / "index-new").exists()
    assert not (tmp_path / "tenant-a" / "index-new.staging").exists()
