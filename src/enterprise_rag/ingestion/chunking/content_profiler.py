"""中文：以确定性结构信号识别内容画像，并为低置信度输入提供保守回退。

English: Detect content profiles from deterministic structure signals with conservative fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.core.enums import ContentProfile

_SIGNALS: dict[ContentProfile, tuple[re.Pattern[str], ...]] = {
    ContentProfile.REGULATION: (
        re.compile(r"第[一二三四五六七八九十百千万0-9]+[编章节条款]"),
        re.compile(r"(?:本法|条例|规定|合同|责任|义务)"),
    ),
    ContentProfile.MANUAL: (
        re.compile(r"(?:警告|注意|步骤|故障|安装|操作|维护)"),
        re.compile(r"(?:WARNING|CAUTION|STEP|TROUBLESHOOT)", re.I),
    ),
    ContentProfile.ACADEMIC: (
        re.compile(r"(?:摘要|关键词|研究方法|实验结果|参考文献|结论)"),
        re.compile(r"(?:abstract|methodology|references|conclusion)", re.I),
    ),
    ContentProfile.TECHNICAL_DOC: (
        re.compile(r"(?:GET|POST|PUT|PATCH|DELETE)\s+/", re.I),
        re.compile(r"(?:API|配置|参数|错误码|代码示例)"),
    ),
    ContentProfile.NARRATIVE: (
        re.compile(r"第[一二三四五六七八九十百千万0-9]+章"),
        re.compile(r"(?:他说|她说|场景|人物|故事)"),
    ),
}


@dataclass(frozen=True, slots=True)
class ContentProfileAssessment:
    """中文：保存画像、置信度、证据标签和是否使用通用回退。

    English: Store profile, confidence, evidence labels, and whether fallback was used.
    """

    profile: ContentProfile
    confidence: float
    signals: tuple[str, ...]
    used_fallback: bool


class ContentProfiler:
    """中文：统计固定规则命中，不调用 LLM，因此结果可复现且可审计。

    English: Count fixed rule hits without an LLM, making results reproducible and auditable.
    """

    def assess(self, text: str, minimum_confidence: float = 0.55) -> ContentProfileAssessment:
        """中文：选择得分最高画像；分数不足或并列时返回 GENERAL_PROSE。

        English: Select the strongest profile; low or tied scores return GENERAL_PROSE.
        """

        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be within zero and one")
        sample = text[:100_000]
        scores = {
            profile: sum(min(3, len(pattern.findall(sample))) for pattern in patterns)
            for profile, patterns in _SIGNALS.items()
        }
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
        best_profile, best_score = ordered[0]
        second_score = ordered[1][1]
        total = sum(scores.values())
        confidence = best_score / max(1, total)
        ambiguous = best_score == 0 or best_score == second_score
        if ambiguous or confidence < minimum_confidence:
            return ContentProfileAssessment(
                profile=ContentProfile.GENERAL_PROSE,
                confidence=confidence,
                signals=("general_fallback",),
                used_fallback=True,
            )
        return ContentProfileAssessment(
            profile=best_profile,
            confidence=confidence,
            signals=tuple(
                f"{best_profile.value}:{index}"
                for index, pattern in enumerate(_SIGNALS[best_profile])
                if pattern.search(sample)
            ),
            used_fallback=False,
        )
