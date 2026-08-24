"""中文：本模块负责实现“意图路由器”相关功能。

English: Classify supported knowledge requests before any expensive retrieval begins.
"""

from __future__ import annotations

import re

from enterprise_rag.core.enums import IntentType

# 中文：变量 `_CAPABILITY_PATTERN` 用于保存“`capability``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Capability phrases request product explanation rather than document evidence.
_CAPABILITY_PATTERN = re.compile(
    r"(?i)\b(what can you do|your capabilities|how do you work)\b|你(能做什么|有什么功能)"
)
# 中文：变量 `_SMALL_TALK_PATTERN` 用于保存“`small``talk``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Small-talk phrases are intentionally narrow to avoid stealing real knowledge
#   questions.
_SMALL_TALK_PATTERN = re.compile(r"(?i)^(hi|hello|hey|thanks|thank you|你好|谢谢)[!,.，。！\s]*$")
# 中文：变量 `_UNSUPPORTED_PATTERN` 用于保存“`unsupported``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Unsupported real-time requests are outside the frozen V0.3 data-source boundary.
_UNSUPPORTED_PATTERN = re.compile(
    r"(?i)\b(latest news|stock price|weather|browse the web|internet search)\b|"
    r"(最新新闻|股价|天气|搜索互联网|联网搜索)"
)
# 中文：变量 `_UNSAFE_PATTERN` 用于保存“`unsafe``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: High-level unsafe action indicators are routed away from knowledge retrieval.
_UNSAFE_PATTERN = re.compile(
    r"(?i)\b(steal|exfiltrate|bypass access|reveal api key|ignore permissions)\b|"
    r"(窃取|绕过权限|泄露密钥|忽略权限)"
)


class IntentRouter:
    """中文：该类用于表示或实现“意图路由器（IntentRouter）”的职责。

    English: Apply conservative deterministic request classification.
    """

    def classify(self, query: str) -> IntentType:
        """中文：该函数或方法负责“分类”相关处理。

        English: Return the first matching safe intent category.
        """

        # 中文：变量 `normalized` 用于保存“`normalized`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Stripped text avoids whitespace-only classification artifacts.
        normalized = query.strip()
        if _UNSAFE_PATTERN.search(normalized):
            return IntentType.UNSAFE
        if _UNSUPPORTED_PATTERN.search(normalized):
            return IntentType.UNSUPPORTED
        if _CAPABILITY_PATTERN.search(normalized):
            return IntentType.CAPABILITY
        if _SMALL_TALK_PATTERN.fullmatch(normalized):
            return IntentType.SMALL_TALK
        return IntentType.KNOWLEDGE
