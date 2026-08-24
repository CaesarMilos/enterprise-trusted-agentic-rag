"""中文：本模块负责实现“接入目录”相关功能。

English: Submit a directory through the formal ingestion service and process durable jobs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from enterprise_rag.api.dependencies import build_container
from enterprise_rag.domain.models import UserContext
from enterprise_rag.domain.requests import CreateDocumentCommand


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Enqueue supported files and run the durable worker until its queue is empty.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Command-line arguments identify exact local input, tenant, and source scope.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--source-id", required=True)
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed values are validated by the formal service and upload validator.
    arguments = parser.parse_args()
    container = build_container()
    user = UserContext(
        user_id="ingest-directory-script",
        tenant_id=arguments.tenant_id,
        roles=frozenset({"admin"}),
    )
    # 中文：变量 `allowed` 用于保存“`allowed`”相关数据；其精确定义与约束见下方英文说明。
    # English: Allowed extensions come from the same immutable application settings.
    allowed = set(container.settings.ingestion.allowed_extensions)
    files = tuple(
        path
        for path in sorted(arguments.directory.expanduser().resolve().iterdir())
        if path.is_file() and path.suffix.lower().lstrip(".") in allowed
    )
    for path in files:
        result = container.ingestion.create_document(
            CreateDocumentCommand(
                user=user,
                source_id=arguments.source_id,
                filename=path.name,
                temporary_path=path,
            )
        )
        print(f"Queued {path.name}: job={result.job_id}")
    # 中文：变量 `processed` 用于保存“`processed`”相关数据；其精确定义与约束见下方英文说明。
    # English: Worker iteration leases and processes each durable job.
    processed = 0
    while container.worker.run_once():
        processed += 1
    print(f"Submitted {len(files)} file(s); processed {processed} job(s).")


if __name__ == "__main__":
    main()
