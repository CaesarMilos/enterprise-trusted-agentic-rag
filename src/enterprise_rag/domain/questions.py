"""中文：定义问题内容、格式要求、精确锚点和信息需要的稳定契约。

English: Define stable contracts for question content, format, exact anchors, and needs.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from enterprise_rag.core.enums import (
    AnchorType,
    AnswerFormat,
    InformationNeedIntent,
    NeedNecessity,
    NeedOrigin,
)
from enterprise_rag.core.ids import content_sha256


@dataclass(frozen=True, slots=True)
class ExactAnchor:
    """中文：保存检索和改写过程中不可丢失的精确用户锚点。

    English: Store an exact user anchor that retrieval and rewriting may not lose.
    """

    id: str
    anchor_type: AnchorType
    raw_value: str
    normalized_value: str
    source_span_start: int | None = None
    source_span_end: int | None = None

    def __post_init__(self) -> None:
        """中文：校验锚点文本、长度和原问题字符范围。

        English: Validate anchor text, length, and source-query character range.
        """

        if not self.id or not self.raw_value.strip() or not self.normalized_value.strip():
            raise ValueError("exact anchor requires non-empty identity and values")
        if len(self.raw_value) > 256 or len(self.normalized_value) > 256:
            raise ValueError("exact anchor values cannot exceed 256 characters")
        if (self.source_span_start is None) != (self.source_span_end is None):
            raise ValueError("anchor source span must provide both start and end")
        if self.source_span_start is not None and self.source_span_end is not None:
            if self.source_span_start < 0 or self.source_span_end <= self.source_span_start:
                raise ValueError("anchor source span must satisfy 0 <= start < end")


@dataclass(frozen=True, slots=True)
class ResponseContract:
    """中文：保存展示格式和引用要求，不参与知识证据覆盖评分。

    English: Store presentation and citation requirements excluded from evidence grading.
    """

    citation_required: bool = True
    requested_format: AnswerFormat = AnswerFormat.AUTO
    requested_language: str | None = None
    requested_item_count: int | None = None
    include_missing_information: bool = True

    def __post_init__(self) -> None:
        """中文：限制请求语言标签和列表数量。

        English: Bound the requested language label and item count.
        """

        if self.requested_language is not None and not 1 <= len(self.requested_language) <= 32:
            raise ValueError("requested language must contain 1-32 characters")
        if self.requested_item_count is not None and not 1 <= self.requested_item_count <= 50:
            raise ValueError("requested item count must be within [1, 50]")


@dataclass(frozen=True, slots=True)
class InformationNeed:
    """中文：表示一个必须或可选的待证明信息需要。

    English: Represent one required or optional information need to be evidenced.
    """

    id: str
    description: str
    retrieval_query: str
    necessity: NeedNecessity
    origin: NeedOrigin
    intent: InformationNeedIntent
    anchor_ids: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    source_span_start: int | None = None
    source_span_end: int | None = None
    critical: bool = False

    def __post_init__(self) -> None:
        """中文：防止证据发现项影响完整性或关键项被错误标成可选。

        English: Prevent discovered evidence from determining completeness or optional criticality.
        """

        if not self.id or not self.description.strip() or not self.retrieval_query.strip():
            raise ValueError("information need requires identity, description, and query")
        if self.origin is NeedOrigin.EVIDENCE_DISCOVERED:
            if self.necessity is not NeedNecessity.OPTIONAL:
                raise ValueError("evidence-discovered needs must be optional")
        if self.critical and self.necessity is not NeedNecessity.REQUIRED:
            raise ValueError("only required needs may be critical")
        if self.id in self.depends_on:
            raise ValueError("information need cannot depend on itself")
        if (self.source_span_start is None) != (self.source_span_end is None):
            raise ValueError("need source span must provide both start and end")


@dataclass(frozen=True, slots=True)
class QuestionPlan:
    """中文：冻结知识问题、回答格式、信息需要和精确锚点。

    English: Freeze knowledge content, response format, information needs, and exact anchors.
    """

    schema_version: str
    original_query: str
    knowledge_query: str
    response_contract: ResponseContract
    needs: tuple[InformationNeed, ...]
    anchors: tuple[ExactAnchor, ...]
    planner_method: str
    planner_version: str
    fingerprint: str


def topological_need_order(needs: Sequence[InformationNeed]) -> tuple[InformationNeed, ...]:
    """中文：稳定拓扑排序信息需要，并拒绝循环依赖。

    English: Stably topologically order information needs and reject dependency cycles.
    """

    by_id = {need.id: need for need in needs}
    if len(by_id) != len(needs):
        raise ValueError("information need IDs must be unique")
    indegree = {need.id: 0 for need in needs}
    children: dict[str, list[str]] = {need.id: [] for need in needs}
    for need in needs:
        for dependency in need.depends_on:
            if dependency not in by_id:
                raise ValueError("information need depends on an unknown need")
            indegree[need.id] += 1
            children[dependency].append(need.id)
    # 中文：初始队列保持输入顺序，使相同计划生成确定性执行次序。
    # English: Initial queue preserves input order for deterministic plan execution.
    ready = deque(need.id for need in needs if indegree[need.id] == 0)
    ordered: list[InformationNeed] = []
    while ready:
        current = ready.popleft()
        ordered.append(by_id[current])
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(ordered) != len(needs):
        raise ValueError("information need dependencies contain a cycle")
    return tuple(ordered)


def question_plan_fingerprint(
    original_query: str,
    knowledge_query: str,
    response_contract: ResponseContract,
    needs: Sequence[InformationNeed],
    anchors: Sequence[ExactAnchor],
    planner_version: str,
) -> str:
    """中文：为相同的语义计划生成可复现指纹。

    English: Generate a reproducible fingerprint for the same semantic question plan.
    """

    payload = {
        "anchors": [
            {
                "id": anchor.id,
                "normalized_value": anchor.normalized_value,
                "raw_value": anchor.raw_value,
                "source_span_end": anchor.source_span_end,
                "source_span_start": anchor.source_span_start,
                "type": anchor.anchor_type.value,
            }
            for anchor in anchors
        ],
        "knowledge_query": knowledge_query,
        "needs": [
            {
                "anchor_ids": list(need.anchor_ids),
                "critical": need.critical,
                "depends_on": list(need.depends_on),
                "description": need.description,
                "id": need.id,
                "intent": need.intent.value,
                "necessity": need.necessity.value,
                "origin": need.origin.value,
                "retrieval_query": need.retrieval_query,
            }
            for need in needs
        ],
        "original_query": original_query,
        "planner_version": planner_version,
        "response_contract": {
            "citation_required": response_contract.citation_required,
            "include_missing_information": response_contract.include_missing_information,
            "requested_format": response_contract.requested_format.value,
            "requested_item_count": response_contract.requested_item_count,
            "requested_language": response_contract.requested_language,
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return content_sha256(canonical)


def validate_question_plan(
    plan: QuestionPlan,
    *,
    max_total_needs: int,
    max_required_needs: int,
    max_anchors: int,
    max_dependency_depth: int,
) -> None:
    """中文：验证问题计划上限、引用关系、来源位置和确定性指纹。

    English: Validate plan limits, references, source spans, dependencies, and fingerprint.
    """

    if (
        not plan.schema_version
        or not plan.original_query.strip()
        or not plan.knowledge_query.strip()
    ):
        raise ValueError("question plan requires schema and non-empty queries")
    if not 1 <= len(plan.needs) <= max_total_needs:
        raise ValueError("question plan has an invalid number of needs")
    required_count = sum(need.necessity is NeedNecessity.REQUIRED for need in plan.needs)
    if not 1 <= required_count <= max_required_needs:
        raise ValueError("question plan requires a bounded number of required needs")
    if len(plan.anchors) > max_anchors:
        raise ValueError("question plan contains too many exact anchors")
    anchor_ids = {anchor.id for anchor in plan.anchors}
    if len(anchor_ids) != len(plan.anchors):
        raise ValueError("question anchor IDs must be unique")
    if any(anchor_id not in anchor_ids for need in plan.needs for anchor_id in need.anchor_ids):
        raise ValueError("information need references an unknown anchor")
    query_length = len(plan.original_query)
    for anchor in plan.anchors:
        if anchor.source_span_end is not None and anchor.source_span_end > query_length:
            raise ValueError("anchor source span exceeds original query")
    for need in plan.needs:
        if need.source_span_end is not None and need.source_span_end > query_length:
            raise ValueError("need source span exceeds original query")
    ordered = topological_need_order(plan.needs)
    depths: dict[str, int] = {}
    for need in ordered:
        depths[need.id] = 1 + max((depths[item] for item in need.depends_on), default=-1)
        if depths[need.id] > max_dependency_depth:
            raise ValueError("question plan dependency depth exceeds the configured limit")
    expected = question_plan_fingerprint(
        plan.original_query,
        plan.knowledge_query,
        plan.response_contract,
        plan.needs,
        plan.anchors,
        plan.planner_version,
    )
    if plan.fingerprint != expected:
        raise ValueError("question plan fingerprint does not match its content")
