"""中文：把用户问题解析为通用的知识需求、展示要求和精确锚点。

English: Parse a user question into generic knowledge needs, presentation requirements,
and exact anchors without depending on a particular law, manual, vendor, or product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.core.enums import (
    AnchorType,
    AnswerFormat,
    InformationNeedIntent,
    NeedNecessity,
    NeedOrigin,
)
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.questions import (
    ExactAnchor,
    InformationNeed,
    QuestionPlan,
    ResponseContract,
    question_plan_fingerprint,
    validate_question_plan,
)
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors
from enterprise_rag.retrieval.query_features import plan_query_features

# 中文：这些短语只表达回答方式，不能降低知识覆盖率。
# English: These phrases specify response behavior and must not lower knowledge coverage.
_FORMAT_PHRASES = re.compile(
    r"(?:请|请问|请你)?(?:根据|依据)(?:本|上述)?(?:文档|资料|说明书|手册)"
    r"|请(?:回答|说明|列出|分别列出|给出)"
    r"|给出(?:原文)?引用|标注页码|附上依据"
    r"|according to (?:the )?(?:document|manual)|please (?:answer|explain|list|cite)",
    re.I,
)
_LIST_MARKER = re.compile(r"(?:^|[\n；;])\s*(?:\d+[.)、]|[（(]期?[0-9一-九]+[）)])\s*")
_EXPLICIT_SPLIT = re.compile(r"\s*(?:、|,|，|以及|和|与|and)\s*")
_ARABIC_COUNT = re.compile(r"(?<!\d)(\d{1,2})\s*(?:项|个|种|steps?|items?)", re.I)
_CHINESE_COUNT = re.compile(r"([一二两三四五六七八九十])\s*(?:项|个|种|步|条)")
_CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass(frozen=True, slots=True)
class QuestionPlanningPolicy:
    """中文：限制确定性问题规划的数量和指纹版本。

    English: Bound deterministic question planning and identify its algorithm version.
    """

    schema_version: str = "question-plan-v1"
    planner_version: str = "deterministic-generic-v1"
    max_total_needs: int = 16
    max_required_needs: int = 12
    max_anchors: int = 32
    max_dependency_depth: int = 4


class QuestionPlanner:
    """中文：使用可复现的通用规则生成最小且受限的问题计划。

    English: Build a minimal bounded question plan with reproducible document-agnostic rules.
    """

    def __init__(self, policy: QuestionPlanningPolicy | None = None) -> None:
        """中文：保存可测试的规划上限。

        English: Store testable planning limits.
        """

        self._policy = policy or QuestionPlanningPolicy()

    def plan(self, query: str) -> QuestionPlan:
        """中文：分离知识内容与格式指令，再生成 Need 和不可丢失锚点。

        English: Separate knowledge content from formatting, then create needs and immutable
        anchors.
        """

        original = " ".join(query.split()).strip()
        if not original:
            raise ValueError("question cannot be empty")
        response = self._response_contract(original)
        knowledge_query = self._knowledge_query(original)
        anchors = self._anchors(original)
        needs = self._needs(knowledge_query, response.requested_item_count, anchors)
        fingerprint = question_plan_fingerprint(
            original,
            knowledge_query,
            response,
            needs,
            anchors,
            self._policy.planner_version,
        )
        plan = QuestionPlan(
            schema_version=self._policy.schema_version,
            original_query=original,
            knowledge_query=knowledge_query,
            response_contract=response,
            needs=needs,
            anchors=anchors,
            planner_method="deterministic_rules",
            planner_version=self._policy.planner_version,
            fingerprint=fingerprint,
        )
        validate_question_plan(
            plan,
            max_total_needs=self._policy.max_total_needs,
            max_required_needs=self._policy.max_required_needs,
            max_anchors=self._policy.max_anchors,
            max_dependency_depth=self._policy.max_dependency_depth,
        )
        return plan

    @staticmethod
    def _knowledge_query(query: str) -> str:
        """中文：仅删除低风险格式短语，保留文档名、编号、条件和否定语义。

        English: Remove only low-risk format phrases while preserving names, identifiers,
        conditions, and negation.
        """

        return plan_query_features(query).core_query

    @staticmethod
    def _response_contract(query: str) -> ResponseContract:
        """中文：识别列表、表格、步骤、语言和引用要求。

        English: Detect list, table, steps, language, count, and citation requirements.
        """

        lowered = query.casefold()
        if any(token in lowered for token in ("表格", "table")):
            requested_format = AnswerFormat.TABLE
        elif any(token in lowered for token in ("步骤", "step")):
            requested_format = AnswerFormat.STEPS
        elif any(token in lowered for token in ("分别", "列出", "list")):
            requested_format = AnswerFormat.LIST
        else:
            requested_format = AnswerFormat.AUTO
        count = _requested_count(query)
        requested_language = None
        if "用英文" in query or "in english" in lowered:
            requested_language = "en"
        elif "用中文" in query or "in chinese" in lowered:
            requested_language = "zh-CN"
        return ResponseContract(
            citation_required=any(token in lowered for token in ("引用", "依据", "页码", "cite")),
            requested_format=requested_format,
            requested_language=requested_language,
            requested_item_count=count,
        )

    def _anchors(self, query: str) -> tuple[ExactAnchor, ...]:
        """中文：将条款、章节、步骤、错误码和型号转换为稳定锚点。

        English: Convert clauses, chapters, steps, error codes, and model identifiers into
        stable anchors.
        """

        anchors: list[ExactAnchor] = []
        for ordinal, normalized in enumerate(extract_exact_anchors(query)):
            if normalized.startswith(("clause:", "chapter:", "step:")):
                anchor_type = AnchorType.STRUCTURE_ID
            else:
                anchor_type = AnchorType.ERROR_CODE
            anchors.append(
                ExactAnchor(
                    id=f"anchor-{ordinal + 1}",
                    anchor_type=anchor_type,
                    raw_value=normalized,
                    normalized_value=normalized,
                )
            )
        return tuple(anchors[: self._policy.max_anchors])

    def _needs(
        self,
        knowledge_query: str,
        requested_count: int | None,
        anchors: tuple[ExactAnchor, ...],
    ) -> tuple[InformationNeed, ...]:
        """中文：优先拆分用户明示列举的并列项，未明示时保留单一必需 Need。

        English: Split explicitly enumerated parallel items; otherwise retain one required need.
        """

        parts = _explicit_need_parts(knowledge_query)
        # 中文：“六项原则是什么”只规定结果基数，并没有提供六个可命名子问题；
        # 因此不伪造六个语义 Need，而是把基数交给 Top-K 做覆盖扩展。
        # English: A requested count does not invent unnamed semantic needs; it becomes a
        # retrieval coverage target instead.
        if len(parts) <= 1:
            parts = (knowledge_query,)
        anchor_ids = tuple(anchor.id for anchor in anchors)
        intent = _infer_intent(knowledge_query)
        return tuple(
            InformationNeed(
                id=f"need-{index + 1}",
                description=part,
                retrieval_query=part,
                necessity=NeedNecessity.REQUIRED,
                origin=(
                    NeedOrigin.USER_EXPLICIT if len(parts) > 1 else NeedOrigin.QUERY_DECOMPOSED
                ),
                intent=intent,
                anchor_ids=anchor_ids if len(parts) == 1 else (),
                critical=bool(anchor_ids) and len(parts) == 1,
            )
            for index, part in enumerate(parts[: self._policy.max_required_needs])
        )


def _requested_count(query: str) -> int | None:
    """中文：读取明示结果项数，并限制异常大的请求。

    English: Read an explicit result cardinality and bound anomalously large requests.
    """

    if match := _ARABIC_COUNT.search(query):
        return min(int(match.group(1)), 50)
    if match := _CHINESE_COUNT.search(query):
        return _CHINESE_DIGITS[match.group(1)]
    return None


def _explicit_need_parts(query: str) -> tuple[str, ...]:
    """中文：只在明示列举或“分别”语境中拆分，避免破坏普通合取问题。

    English: Split only explicit enumerations or “respectively” constructions to avoid
    damaging ordinary conjunctive questions.
    """

    # 中文：成对时间边界是两个独立必答槽位，即使用户没有使用“分别”。
    # English: Paired temporal boundaries are independent required slots even without the word
    # “respectively”.
    temporal_match = re.search(
        r"(?P<subject>.+?)(?:从)?何时开始[、，,；;和与及]*(?:到)?何时终止",
        query,
    )
    if temporal_match is not None:
        subject = temporal_match.group("subject").strip(" ，,;；。？?")
        return (f"{subject}何时开始", f"{subject}何时终止")
    if _LIST_MARKER.search(query):
        parts = tuple(part.strip(" ，,;；。") for part in _LIST_MARKER.split(query))
        return tuple(part for part in parts if len(part) >= 2)
    if "分别" not in query and "respectively" not in query.casefold():
        return (query,)
    tail = re.split(r"分别|respectively", query, maxsplit=1, flags=re.I)[-1]
    parts = tuple(part.strip(" ，,;；。？?") for part in _EXPLICIT_SPLIT.split(tail))
    meaningful = tuple(part for part in parts if len(part) >= 2)
    return meaningful if len(meaningful) > 1 else (query,)


def _infer_intent(query: str) -> InformationNeedIntent:
    """中文：以跨领域触发词标注 Need 意图，仅用于检索配额而非法律裁决。

    English: Label need intent with cross-domain cues for retrieval, never legal adjudication.
    """

    lowered = query.casefold()
    if any(token in lowered for token in ("错误", "故障", "排查", "error", "fault")):
        return InformationNeedIntent.TROUBLESHOOTING
    if any(token in lowered for token in ("步骤", "操作", "如何", "how to", "procedure")):
        return InformationNeedIntent.PROCEDURE
    if any(token in lowered for token in ("例外", "除外", "exception")):
        return InformationNeedIntent.EXCEPTION
    if any(token in lowered for token in ("条件", "前提", "when", "condition")):
        return InformationNeedIntent.CONDITION
    if any(token in lowered for token in ("参数", "规格", "parameter", "specification")):
        return InformationNeedIntent.PARAMETER
    if any(token in lowered for token in ("原则", "应当", "不得", "必须", "rule", "must")):
        return InformationNeedIntent.RULE
    if any(token in lowered for token in ("是什么", "定义", "what is", "define")):
        return InformationNeedIntent.DEFINITION
    return InformationNeedIntent.FACT


def planning_cache_key(query: str, planner_version: str) -> str:
    """中文：为无隐私的问题计划缓存生成版本化键。

    English: Generate a versioned key for a privacy-appropriate question-plan cache.
    """

    return content_sha256(f"{planner_version}\0{query}")
