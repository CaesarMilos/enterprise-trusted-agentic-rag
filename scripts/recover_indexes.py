"""中文：本模块负责实现“恢复索引”相关功能。

English: Verify published manifests and report recoverable tenant index snapshots.
"""

from __future__ import annotations

import argparse

from enterprise_rag.api.dependencies import build_container
from enterprise_rag.indexing.index_manifest import load_manifest, verify_manifest


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Inspect exact tenant snapshot directories without mutating active database state.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Tenant scope is required to avoid scanning unrelated customer artifacts.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed scope selects one contained tenant directory.
    arguments = parser.parse_args()
    container = build_container()
    tenant_root = (container.settings.storage.index_dir / arguments.tenant_id).resolve()
    tenant_root.relative_to(container.settings.storage.index_dir.resolve())
    for directory in sorted(path for path in tenant_root.iterdir() if path.is_dir()):
        try:
            manifest = load_manifest(directory)
            verify_manifest(directory, manifest)
            print(f"VALID {directory.name} chunks={len(manifest.chunk_ids)}")
        except Exception as exc:
            print(f"INVALID {directory.name}: {exc}")


if __name__ == "__main__":
    main()
