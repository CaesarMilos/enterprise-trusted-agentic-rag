"""中文：本模块把知识问题、来源提示和回答格式指令分离。

English: Separate knowledge questions, source hints, and answer-format instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors

# 中文：命名来源回答短语只在句尾移除，避免误删正文中的“依据”等实体语义。
# English: Named-source answer phrases are removed only at the end to avoid deleting semantic
# occurrences of words such as “basis” inside the actual question.
_NAMED_SOURCE_INSTRUCTION = re.compile(
    r"(?:请|请问|请你)?(?:根据|依据)"
    r"(?P<source>[\u3400-\u9fffA-Za-z0-9_.-]{2,40})"
    r"(?:回答|作答|说明)(?:并)?(?:给出|附上|标注)?(?:原文)?(?:引用|依据|页码)?[。.!！]?$",
    re.I,
)
_GENERIC_FORMAT_INSTRUCTION = re.compile(
    r"(?:请|请问|请你)?(?:根据|依据)(?:本|上述)?(?:文档|资料|说明书|手册)"
    r"|请(?:回答|说明|列出|分别列出|给出)"
    r"|给出(?:原文)?引用|标注页码|附上依据"
    r"|according to (?:the )?(?:document|manual)|please (?:answer|explain|list|cite)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class RetrievalQueryPlan:
    """中文：保存检索核心问题、来源提示、锚点和被剥离指令。

    English: Store the retrieval core, source hint, anchors, and removed instructions.
    """

    core_query: str
    source_hint: str | None
    exact_anchors: tuple[str, ...]
    ignored_instruction_terms: tuple[str, ...]


def plan_query_features(query: str) -> RetrievalQueryPlan:
    """中文：确定性提取来源提示并剥离不会改变知识语义的呈现指令。

    English: Deterministically extract source hints and remove presentation-only instructions.
    """

    normalized = " ".join(query.split()).strip()
    if not normalized:
        raise ValueError("query cannot be empty")
    removed: list[str] = []
    source_hint: str | None = None
    named_match = _NAMED_SOURCE_INSTRUCTION.search(normalized)
    if named_match is not None:
        source_hint = named_match.group("source")
        removed.append(named_match.group(0))
        normalized = normalized[: named_match.start()]
    generic_matches = tuple(_GENERIC_FORMAT_INSTRUCTION.finditer(normalized))
    removed.extend(match.group(0) for match in generic_matches)
    core_query = _GENERIC_FORMAT_INSTRUCTION.sub(" ", normalized)
    core_query = re.sub(r"\s+", " ", core_query).strip(" ，,;；。") or query.strip()
    return RetrievalQueryPlan(
        core_query=core_query,
        source_hint=source_hint,
        exact_anchors=extract_exact_anchors(query),
        ignored_instruction_terms=tuple(dict.fromkeys(removed)),
    )
