"""中文：在不破坏编号、URL、小数和成对符号的前提下切分中英文混排句子。

English: Split mixed Chinese/English sentences without breaking identifiers, URLs, or decimals.
"""

from __future__ import annotations

import re

# 中文：URL、邮箱、版本号和小数点中的句点不是句末边界。
# English: Periods inside URLs, emails, versions, and decimals are not sentence boundaries.
_PROTECTED_PERIOD = re.compile(
    r"(?:https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.\w+|\d+(?:\.\d+)+)", re.I
)
_CLOSING_QUOTES = frozenset("”’」』】）》\"'")
_OPENING = {"（": "）", "(": ")", "[": "]", "【": "】", "《": "》", "「": "」", "『": "』"}


class ChineseSentenceSplitter:
    """中文：使用线性扫描生成稳定句界，并保留原始标点和字符顺序。

    English: Use a linear scan to produce stable boundaries while preserving punctuation/order.
    """

    def split(self, text: str) -> tuple[str, ...]:
        """中文：返回非空完整句；括号内部和受保护范围内不切分。

        English: Return non-empty complete sentences without splitting inside protected spans.
        """

        stripped = text.strip()
        if not stripped:
            return ()
        protected = self._protected_offsets(stripped)
        stack: list[str] = []
        boundaries: list[int] = []
        index = 0
        while index < len(stripped):
            char = stripped[index]
            if char in _OPENING:
                stack.append(_OPENING[char])
            elif stack and char == stack[-1]:
                stack.pop()
            is_terminal = char in "。！？!?；;" or self._latin_period_boundary(stripped, index)
            if is_terminal and not stack and index not in protected:
                end = index + 1
                while end < len(stripped) and stripped[end] in _CLOSING_QUOTES:
                    end += 1
                boundaries.append(end)
                index = end
                continue
            index += 1
        if not boundaries or boundaries[-1] < len(stripped):
            boundaries.append(len(stripped))
        parts: list[str] = []
        start = 0
        for end in boundaries:
            part = stripped[start:end].strip()
            if part:
                parts.append(part)
            start = end
        return tuple(parts)

    @staticmethod
    def _protected_offsets(text: str) -> frozenset[int]:
        """中文：收集受保护模式占用的字符位置，用于 O(1) 边界排除。

        English: Collect protected character offsets for constant-time boundary exclusion.
        """

        return frozenset(
            position
            for match in _PROTECTED_PERIOD.finditer(text)
            for position in range(match.start(), match.end())
        )

    @staticmethod
    def _latin_period_boundary(text: str, index: int) -> bool:
        """中文：仅把后接空白和新句开头的英文句点视为句界。

        English: Treat a Latin period as terminal only before whitespace and a new sentence.
        """

        if text[index] != "." or index + 1 >= len(text):
            return text[index] == "." and index + 1 == len(text)
        if not text[index + 1].isspace():
            return False
        cursor = index + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        return cursor >= len(text) or text[cursor].isupper() or text[cursor].isdigit()
