"""中文：本模块负责实现“状态”相关功能。

English: Define the serializable state used by the explicit bounded Python agent state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from enterprise_rag.core.enums import AgentStatus, IntentType
from enterprise_rag.domain.models import Citation, RetrievalScope
from enterprise_rag.domain.questions import QuestionPlan
from enterprise_rag.retrieval.models import EvidenceBundle


@dataclass(slots=True)
class AgentState:
    """中文：该类用于表示或实现“智能体状态（AgentState）”的职责。

    English: Track every bounded decision and budget for one question-answering workflow.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier shared by public output and observability.
    trace_id: str
    # 中文：变量 `original_query` 用于保存“原始查询”相关数据；其精确定义与约束见下方英文说明。
    # English: Original unmodified user question.
    original_query: str
    # 中文：变量 `current_query` 用于保存“当前查询”相关数据；其精确定义与约束见下方英文说明。
    # English: Current initial or rewritten retrieval query.
    current_query: str
    # 中文：变量 `retrieval_scope` 用于保存“检索范围”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Exact ACL and immutable index version pinned before execution.
    retrieval_scope: RetrievalScope
    # 中文：变量 `deadline` 用于保存“`deadline`”相关数据；其精确定义与约束见下方英文说明。
    # English: Absolute UTC deadline for the complete workflow.
    deadline: datetime
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Current state-machine status.
    status: AgentStatus = AgentStatus.CREATED
    # 中文：变量 `intent` 用于保存“意图”相关数据；其精确定义与约束见下方英文说明。
    # English: Classified request intent.
    intent: IntentType | None = None
    # 中文：问题计划分离知识 Need、格式指令和不可丢失锚点。
    # English: The question plan separates knowledge needs, format instructions, and anchors.
    question_plan: QuestionPlan | None = None
    # 中文：变量 `retrieval_rounds` 用于保存“检索`rounds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of completed retrieval rounds.
    retrieval_rounds: int = 0
    # 中文：变量 `rewrite_history` 用于保存“改写`history`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Ordered rewritten queries, excluding the original query.
    rewrite_history: list[str] = field(default_factory=list)
    # 中文：变量 `evidence_grade_reasons` 用于保存“证据`grade``reasons`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Safe reasons returned by each evidence grade.
    evidence_grade_reasons: list[str] = field(default_factory=list)
    # 中文：变量 `evidence` 用于保存“证据”相关数据；其精确定义与约束见下方英文说明。
    # English: Most recent selected evidence bundle.
    evidence: EvidenceBundle | None = None
    # 中文：变量 `model_call_count` 用于保存“模型`call``count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Total language-model provider calls.
    model_call_count: int = 0
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Aggregate provider-reported input and output tokens.
    token_count: int = 0
    # 中文：变量 `answer_draft` 用于保存“答案`draft`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Unverified generated answer text.
    answer_draft: str | None = None
    # 中文：变量 `verified_answer` 用于保存“`verified`答案”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified answer text safe to return.
    verified_answer: str | None = None
    # 中文：变量 `citations` 用于保存“引用”相关数据；其精确定义与约束见下方英文说明。
    # English: Verified citations safe to return.
    citations: tuple[Citation, ...] = ()
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable terminal error code, when execution fails.
    error_code: str | None = None

    @property
    def index_version_id(self) -> str:
        """中文：该函数或方法负责“索引版本标识符”相关处理。

        English: Return the required immutable index version from the pinned scope.
        """

        if self.retrieval_scope.index_version_id is None:
            raise ValueError("agent state requires a pinned index version")
        return self.retrieval_scope.index_version_id
