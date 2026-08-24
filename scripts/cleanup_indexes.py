"""中文：本模块负责实现“清理索引”相关功能。

English: Preview or remove retired index snapshots outside the configured retention window.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from enterprise_rag.api.dependencies import build_container


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Keep ACTIVE plus the newest three historical snapshots and default to dry-run.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Explicit apply flag protects historical artifacts from accidental deletion.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--keep-history", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed scope identifies one tenant directory and retention count.
    arguments = parser.parse_args()
    container = build_container()
    tenant_root = (container.settings.storage.index_dir / arguments.tenant_id).resolve()
    tenant_root.relative_to(container.settings.storage.index_dir.resolve())
    # 中文：本步骤涉及数据库、列出、状态，具体约束见下方英文说明。
    # English: Database list is authoritative for status and creation order.
    from enterprise_rag.domain.models import UserContext

    user = UserContext(
        user_id="cleanup-indexes-script",
        tenant_id=arguments.tenant_id,
        roles=frozenset({"admin"}),
    )
    versions = container.knowledge.list_indexes(user)
    retained_history = 0
    removable: list[Path] = []
    for version in versions:
        if version["status"] == "active":
            continue
        if retained_history < max(0, arguments.keep_history):
            retained_history += 1
            continue
        path = (tenant_root / str(version["index_version_id"])).resolve()
        path.relative_to(tenant_root)
        if path.is_dir():
            removable.append(path)
    for path in removable:
        print(f"{'REMOVE' if arguments.apply else 'DRY-RUN'} {path.name}")
        if arguments.apply:
            # 中文：本步骤涉及快照、租户、数据库、元数据，具体约束见下方英文说明。
            # English: Exact resolved snapshot target was derived from tenant-scoped
            #   database metadata.
            shutil.rmtree(path)


if __name__ == "__main__":
    main()
