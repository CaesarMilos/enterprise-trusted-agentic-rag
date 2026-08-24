"""中文：本模块负责实现“重建索引”相关功能。

English: Build, reload-validate, and atomically activate a fresh tenant index snapshot.
"""

from __future__ import annotations

import argparse

from enterprise_rag.api.dependencies import build_container


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Run the formal active-index rebuild use case.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Tenant is required to prevent accidental broad rebuilds.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed tenant scope selects exactly one immutable snapshot build.
    arguments = parser.parse_args()
    result = build_container().indexes.rebuild_active(arguments.tenant_id)
    print(
        f"Activated index={result.index_version_id} chunks={result.chunk_count} "
        f"previous={result.previous_index_version_id}"
    )


if __name__ == "__main__":
    main()
