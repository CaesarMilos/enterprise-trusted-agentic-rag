"""中文：从证据原文中确定性抽取可追溯命题和语义槽位。

English: Deterministically extract traceable propositions and semantic slots from evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.core.enums import ClaimModality
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.evidence import EvidenceProposition

# 中文：句子边界保留原始字符偏移，确保命题可以回指原文。
# English: Sentence boundaries retain original offsets so every proposition can cite its span.
_SENTENCE_PATTERN = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?", re.MULTILINE)
# 中文：实体词表只承担保守的一致性检查，不尝试完成开放域实体识别。
# English: Entity terms support conservative consistency checks, not open-domain NER.
_ENTITY_TERMS = (
    "自然人",
    "法人",
    "非法人组织",
    "民事主体",
    "成年人",
    "未成年人",
    "被监护人",
    "监护人",
    "胎儿",
)
# 中文：时间角色使用互斥标签，避免“开始”证据错误支撑“终止”结论。
# English: Temporal roles are distinct so start evidence cannot support an end claim.
_TEMPORAL_ROLES: dict[str, tuple[str, ...]] = {
    "start": ("出生时", "开始", "起算", "生效", "自成立时", "自登记时", "之日起"),
    "end": ("死亡时", "终止", "届满", "失效", "注销时", "清算结束", "时止"),
}
# 中文：规范模态词用于识别义务、禁止、许可和例外，避免模态错配。
# English: Normative cues identify duties, prohibitions, permissions, and exceptions.
_MODALITY_CUES: dict[ClaimModality, tuple[str, ...]] = {
    ClaimModality.PROHIBITED: ("不得", "禁止", "严禁", "不应"),
    ClaimModality.REQUIRED: ("应当", "必须", "须", "有义务"),
    ClaimModality.PERMITTED: ("可以", "有权", "允许"),
    ClaimModality.EXCEPTION: ("但是", "除外", "除非", "例外"),
    ClaimModality.CONDITIONAL: ("如果", "若", "在下列情形", "符合条件"),
}


@dataclass(frozen=True, slots=True)
class SemanticSignals:
    """中文：保存断言或证据中的关键实体、时间角色、模态和数值。

    English: Store key entities, temporal roles, modalities, and numeric values.
    """

    # 中文：`entities` 是需要保持一致的明确主体类别。
    # English: `entities` contains explicit subject categories that must remain consistent.
    entities: frozenset[str]
    # 中文：`temporal_roles` 区分开始与终止等时间语义。
    # English: `temporal_roles` distinguishes beginning and ending semantics.
    temporal_roles: frozenset[str]
    # 中文：`modalities` 保存明确出现的规范强度。
    # English: `modalities` stores explicitly expressed normative force.
    modalities: frozenset[ClaimModality]
    # 中文：`numbers` 保存不可由相似词替代的阿拉伯数字值。
    # English: `numbers` stores Arabic numeric values that similarity cannot substitute.
    numbers: frozenset[str]


class PropositionExtractor:
    """中文：用确定性规则抽取证据命题，不让模型创造证据字段。

    English: Extract evidence propositions with deterministic rules without model invention.
    """

    def extract(self, chunk_id: str, text: str) -> tuple[EvidenceProposition, ...]:
        """中文：逐句抽取带原文偏移、主体、谓词、模态和时间范围的命题。

        English: Extract sentence propositions with source offsets, subject, predicate,
        modality, and temporal scope.
        """

        propositions: list[EvidenceProposition] = []
        for match in _SENTENCE_PATTERN.finditer(text):
            sentence = match.group(0).strip()
            if not sentence:
                continue
            signals = semantic_signals(sentence)
            subject = next((item for item in _ENTITY_TERMS if item in sentence), None)
            modality = _primary_modality(signals.modalities)
            predicate = _predicate_cue(sentence, signals)
            propositions.append(
                EvidenceProposition(
                    id=f"prop_{content_sha256(f'{chunk_id}:{match.start()}:{sentence}')[:24]}",
                    subject=subject,
                    predicate=predicate,
                    object=None,
                    modality=modality,
                    conditions=(),
                    exceptions=(sentence,) if modality is ClaimModality.EXCEPTION else (),
                    temporal_scope=",".join(sorted(signals.temporal_roles)) or None,
                    authority_scope=None,
                    source_chunk_id=chunk_id,
                    source_span_start=match.start(),
                    source_span_end=match.end(),
                    extraction_method="deterministic-proposition-v5.1",
                )
            )
        return tuple(propositions)


def semantic_signals(text: str) -> SemanticSignals:
    """中文：从文本中读取后续一致性校验所需的保守语义信号。

    English: Read conservative semantic signals used by downstream consistency checks.
    """

    entities = frozenset(entity for entity in _ENTITY_TERMS if entity in text)
    temporal_roles = frozenset(
        role
        for role, cues in _TEMPORAL_ROLES.items()
        if any(cue in text for cue in cues)
    )
    modalities = frozenset(
        modality
        for modality, cues in _MODALITY_CUES.items()
        if any(cue in text for cue in cues)
    )
    numbers = frozenset(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text))
    return SemanticSignals(entities, temporal_roles, modalities, numbers)


def required_temporal_roles(text: str) -> frozenset[str]:
    """中文：把问题中的“何时开始/终止”转换为不可缺失的时间槽位。

    English: Convert start/end questions into mandatory temporal evidence slots.
    """

    roles: set[str] = set()
    if any(cue in text for cue in ("何时开始", "什么时候开始", "起始时间", "从何时")):
        roles.add("start")
    if any(cue in text for cue in ("何时终止", "什么时候终止", "终止时间", "到何时")):
        roles.add("end")
    return frozenset(roles)


def _primary_modality(modalities: frozenset[ClaimModality]) -> ClaimModality:
    """中文：按安全优先级选择一句话的主要规范模态。

    English: Select one sentence's primary modality in safety-first order.
    """

    for modality in (
        ClaimModality.PROHIBITED,
        ClaimModality.REQUIRED,
        ClaimModality.EXCEPTION,
        ClaimModality.CONDITIONAL,
        ClaimModality.PERMITTED,
    ):
        if modality in modalities:
            return modality
    return ClaimModality.FACT


def _predicate_cue(sentence: str, signals: SemanticSignals) -> str | None:
    """中文：返回最具判别力的谓词提示，未知时保持为空。

    English: Return the most discriminative predicate cue, leaving unknown predicates empty.
    """

    for role in ("start", "end"):
        if role in signals.temporal_roles:
            return role
    for modality, cues in _MODALITY_CUES.items():
        if modality in signals.modalities:
            return next((cue for cue in cues if cue in sentence), modality.value)
    return None
