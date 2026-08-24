"""中文：本模块负责实现“日志”相关功能。

English: Configure structured logging with request context and secret redaction.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# 中文：变量 `request_id_context` 用于保存“请求标识符上下文”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Context variables attach request identifiers without global mutable state.
request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
trace_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id",
    default=None,
)
# 中文：变量 `_SECRET_PATTERN` 用于保存“`secret``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Patterns cover common API key, bearer token, and password representations.
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|password|secret)([\"'=:\s]+)([^\s,;\"']+)"
)


class RedactionFilter(logging.Filter):
    """中文：该类用于表示或实现“`redaction`过滤（RedactionFilter）”的职责。

    English: Redact likely secrets from log messages and exception text.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """中文：该函数或方法负责“过滤目标数据”相关处理。

        English: Replace sensitive substrings before a formatter serializes the record.
        """

        # 中文：变量 `rendered_message` 用于保存“`rendered`消息”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Pre-rendered message includes any positional logging arguments.
        rendered_message = record.getMessage()
        record.msg = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", rendered_message)
        # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
        # English: Arguments are cleared because they have already been incorporated.
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """中文：该类用于表示或实现“JSON格式化器（JsonFormatter）”的职责。

    English: Serialize a log record as one compact JSON object.
    """

    def format(self, record: logging.LogRecord) -> str:
        """中文：该函数或方法负责“格式化目标数据”相关处理。

        English: Return a stable JSON line with safe request and trace context.
        """

        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: Base payload contains fields required by log aggregation and debugging.
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
            "trace_id": trace_id_context.get(),
        }
        if record.exc_info:
            # 中文：本步骤涉及异常，具体约束见下方英文说明。
            # English: Formatted exception is useful operationally but still passes
            #   through redaction.
            payload["exception"] = _SECRET_PATTERN.sub(
                r"\1\2[REDACTED]",
                self.formatException(record.exc_info),
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """中文：该函数或方法负责“配置日志”相关处理。

    English: Configure the root logger once for JSON or human-readable output.
    """

    # 中文：变量 `handler` 用于保存“`handler`”相关数据；其精确定义与约束见下方英文说明。
    # English: Root handler is intentionally replaced so repeated app-factory calls remain
    #   deterministic.
    handler = logging.StreamHandler()
    handler.addFilter(RedactionFilter())
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    # 中文：变量 `numeric_level` 用于保存“`numeric``level`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Named level is normalized before validation by the logging package.
    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, handlers=[handler], force=True)


def bind_log_context(request_id: str | None, trace_id: str | None = None) -> None:
    """中文：该函数或方法负责“绑定日志上下文”相关处理。

    English: Bind request and trace identifiers for the current asynchronous context.
    """

    request_id_context.set(request_id)
    trace_id_context.set(trace_id)


def get_logger(name: str) -> logging.Logger:
    """中文：该函数或方法负责“获取日志器”相关处理。

    English: Return a conventional named logger for the supplied module or component.
    """

    return logging.getLogger(name)
