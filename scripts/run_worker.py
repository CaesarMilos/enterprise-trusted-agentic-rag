"""中文：本模块负责实现“运行工作进程”相关功能。

English: Poll and process durable ingestion jobs in a long-running worker process.
"""

from __future__ import annotations

import argparse
import time

from enterprise_rag.api.dependencies import build_container


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Run the durable worker continuously or until the current queue is empty.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Once mode is useful for local demos and deterministic tests.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed polling interval is clamped to avoid a busy loop.
    arguments = parser.parse_args()
    container = build_container()
    while True:
        processed = container.worker.run_once()
        if arguments.once:
            break
        if not processed:
            time.sleep(max(0.2, arguments.poll_seconds))


if __name__ == "__main__":
    main()
