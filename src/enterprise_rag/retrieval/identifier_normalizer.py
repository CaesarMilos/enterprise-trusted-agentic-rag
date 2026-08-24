"""中文：本模块统一识别条款、章节、步骤、错误码和设备型号等精确检索锚点。

English: Normalize exact retrieval anchors such as clauses, chapters, steps, error codes,
and device model identifiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 中文：变量 `_CLAUSE_PATTERN` 同时接受中文数字和阿拉伯数字形式的编号条款。
# English: Clause pattern accepts both Chinese-numeral and Arabic-numeral identifiers.
_CLAUSE_PATTERN = re.compile(r"第\s*([零〇一二两三四五六七八九十百千万亿0-9]+)\s*条")
# 中文：变量 `_CHAPTER_PATTERN` 识别说明书、规范和法规常见的章节编号。
# English: Chapter pattern recognizes chapter identifiers used by manuals and references.
_CHAPTER_PATTERN = re.compile(r"第\s*([零〇一二两三四五六七八九十百千万亿0-9]+)\s*章")
# 中文：变量 `_STEP_PATTERN` 识别“步骤四”和“第4步”等稳定操作定位符。
# English: Step pattern recognizes stable operation anchors such as step four or step 4.
_STEP_PATTERN = re.compile(
    r"(?:步骤\s*([零〇一二两三四五六七八九十百千万亿0-9]+)|"
    r"第\s*([零〇一二两三四五六七八九十百千万亿0-9]+)\s*步)"
)
# 中文：错误码和型号必须包含数字，避免把普通英文单词误判为强锚点。
# English: Error and model identifiers require digits to avoid treating ordinary words as anchors.
_CODE_PATTERN = re.compile(r"\b(?=[A-Za-z0-9_.-]*\d)[A-Za-z][A-Za-z0-9_.-]{2,}\b")
# 中文：规范锚点正则使改写查询也能保留并重新识别原始精确定位符。
# English: Canonical-anchor syntax keeps original exact locators recognizable after rewriting.
_CANONICAL_ANCHOR_PATTERN = re.compile(
    r"\b(?:clause|chapter|step):\d+\b|\bcode:[a-z][a-z0-9_.-]{2,}\b",
    re.I,
)

_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SMALL_UNITS = {"十": 10, "百": 100, "千": 1000}
_LARGE_UNITS = {"万": 10_000, "亿": 100_000_000}


@dataclass(frozen=True, slots=True)
class IdentifierNormalization:
    """中文：保存规范化检索文本和从原查询中提取的精确锚点。

    English: Store normalized retrieval text and exact anchors extracted from the query.
    """

    # 中文：变量 `text` 保留原查询语义，并追加可由索引稳定匹配的规范Token。
    # English: Text preserves query meaning and appends canonical tokens for stable matching.
    text: str
    # 中文：变量 `exact_anchors` 保存去重且有序的强定位Token。
    # English: Exact anchors contain ordered, deduplicated strong locator tokens.
    exact_anchors: tuple[str, ...]


def chinese_number_to_int(value: str) -> int | None:
    """中文：把明确编号上下文中的中文数字安全转换为非负整数。

    English: Convert a Chinese numeral used in an identifier context to a non-negative integer.
    """

    compact = value.strip()
    if not compact:
        return None
    if compact.isdigit():
        return int(compact)
    if all(character in _DIGITS for character in compact):
        return int("".join(str(_DIGITS[character]) for character in compact))
    total = 0
    section = 0
    number = 0
    for character in compact:
        if character in _DIGITS:
            number = _DIGITS[character]
        elif character in _SMALL_UNITS:
            unit = _SMALL_UNITS[character]
            section += (number or 1) * unit
            number = 0
        elif character in _LARGE_UNITS:
            large_unit = _LARGE_UNITS[character]
            total += (section + number or 1) * large_unit
            section = 0
            number = 0
        else:
            return None
    return total + section + number


def extract_exact_anchors(text: str) -> tuple[str, ...]:
    """中文：从查询或文档中提取规范化条款、章节、步骤和代码锚点。

    English: Extract canonical clause, chapter, step, and code anchors from text.
    """

    anchors: list[str] = []
    for match in _CANONICAL_ANCHOR_PATTERN.finditer(text):
        anchor = match.group(0).lower()
        if anchor not in anchors:
            anchors.append(anchor)

    def append_numbered(prefix: str, raw_value: str) -> None:
        """中文：转换编号并按首次出现顺序追加唯一锚点。

        English: Convert one number and append a unique anchor in first-seen order.
        """

        number = chinese_number_to_int(raw_value)
        anchor = f"{prefix}:{number}" if number is not None else ""
        if anchor and anchor not in anchors:
            anchors.append(anchor)

    for match in _CLAUSE_PATTERN.finditer(text):
        append_numbered("clause", match.group(1))
    for match in _CHAPTER_PATTERN.finditer(text):
        append_numbered("chapter", match.group(1))
    for match in _STEP_PATTERN.finditer(text):
        append_numbered("step", match.group(1) or match.group(2))
    for match in _CODE_PATTERN.finditer(text):
        anchor = f"code:{match.group(0).lower()}"
        if anchor not in anchors:
            anchors.append(anchor)
    return tuple(anchors)


def normalize_identifiers(text: str) -> IdentifierNormalization:
    """中文：保留原文本并追加规范化锚点，供Dense、BM25和证据判断共享。

    English: Preserve original text and append canonical anchors shared by dense, BM25,
    and evidence grading.
    """

    anchors = extract_exact_anchors(text)
    suffix = " ".join(anchors)
    normalized = f"{text.strip()} {suffix}".strip() if suffix else text.strip()
    return IdentifierNormalization(normalized, anchors)
