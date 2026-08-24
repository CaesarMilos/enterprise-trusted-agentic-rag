"""中文：本模块负责实现“追踪记录器”相关功能。

English: Append redacted trace events to tenant-isolated JSON Lines files without blocking
workflows.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Any

from enterprise_rag.domain.models import TraceRecord
from enterprise_rag.observability.trace_models import TraceStep


class JSONLTraceRecorder:
    """中文：该类用于表示或实现“JSONL追踪记录器（JSONLTraceRecorder）”的职责。

    English: Persist safe append-only trace events and never expose raw prompts or document
    bodies.
    """

    def __init__(self, root: Path) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store and create the trace root.
        """

        # 中文：变量 `_root` 用于保存“`root`”相关数据；其精确定义与约束见下方英文说明。
        # English: Canonical root contains one file per safe trace ID.
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        # 中文：变量 `_lock` 用于保存“`lock`”相关数据；其精确定义与约束见下方英文说明。
        # English: Process-local lock protects sequence assignment and line appends.
        self._lock = Lock()
        # 中文：变量 `_sequences` 用于保存“`sequences`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Per-trace sequence numbers preserve event order.
        self._sequences: dict[str, int] = {}

    def start(self, trace: TraceRecord) -> None:
        """中文：该函数或方法负责“开始”相关处理。

        English: Create the first redacted trace event.
        """

        self._append(
            trace.id,
            {
                "event": "trace_started",
                "trace": _json_safe(asdict(trace)),
            },
        )

    def append_step(
        self,
        trace_id: str,
        name: str,
        attributes: Mapping[str, Any],
    ) -> None:
        """中文：该函数或方法负责“追加步骤”相关处理。

        English: Append one redacted step while preserving event order.
        """

        with self._lock:
            # 中文：变量 `sequence` 用于保存“`sequence`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Current sequence defaults to zero for traces not started in this
            #   process.
            sequence = self._sequences.get(trace_id, 0)
            self._sequences[trace_id] = sequence + 1
        # 中文：变量 `step` 用于保存“`step`”相关数据；其精确定义与约束见下方英文说明。
        # English: Attribute values are recursively constrained to JSON-safe bounded
        #   representations.
        step = TraceStep(
            trace_id=trace_id,
            sequence=sequence,
            name=name[:128],
            attributes=_safe_attributes(attributes),
        )
        self._append(trace_id, {"event": "step", "step": _json_safe(asdict(step))})

    def finish(
        self,
        trace_id: str,
        status: str,
        attributes: Mapping[str, Any],
    ) -> None:
        """中文：该函数或方法负责“结束”相关处理。

        English: Append a terminal trace event with safe aggregate attributes.
        """

        self._append(
            trace_id,
            {
                "event": "trace_finished",
                "status": status[:64],
                "attributes": _safe_attributes(attributes),
            },
        )

    def _append(self, trace_id: str, payload: Mapping[str, Any]) -> None:
        """中文：该内部函数负责“追加”相关处理。

        English: Append one compact JSON line and swallow observability-only filesystem errors.
        """

        # 中文：本步骤涉及追踪，具体约束见下方英文说明。
        # English: Strict trace IDs prevent path traversal and broad writes.
        if not trace_id or any(character in trace_id for character in ("/", "\\", "\x00")):
            return
        # 中文：变量 `target` 用于保存“`target`”相关数据；其精确定义与约束见下方英文说明。
        # English: Exact file target stays beneath the configured trace root.
        target = (self._root / f"{trace_id}.jsonl").resolve()
        try:
            target.relative_to(self._root)
            # 中文：本步骤涉及追踪、用户，具体约束见下方英文说明。
            # English: Trace failure must never fail the user workflow.
            with self._lock, target.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            return


def _safe_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """中文：该内部函数负责“安全属性”相关处理。

    English: Filter likely secrets and bound keys and scalar values.
    """

    # 中文：变量 `blocked_fragments` 用于保存“`blocked``fragments`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Keys containing secret-bearing labels are dropped rather than redacted
    #   ambiguously.
    blocked_fragments = ("key", "token", "authorization", "password", "prompt", "chunk_text")
    return {
        str(key)[:128]: _json_safe(value)
        for key, value in attributes.items()
        if not any(fragment in str(key).lower() for fragment in blocked_fragments)
    }


def _json_safe(value: Any) -> Any:
    """中文：该内部函数负责“JSON安全”相关处理。

    English: Convert arbitrary safe metadata into bounded JSON-compatible values.
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, Mapping):
        return {str(key)[:128]: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in list(value)[:100]]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:500]
