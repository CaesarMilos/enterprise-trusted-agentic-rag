"""中文：本模块负责实现“编排器”相关功能。

English: Run the explicit bounded Agentic RAG state machine without LangGraph.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from enterprise_rag.agent.answer_generator import AnswerGenerator
from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.agent.intent_router import IntentRouter
from enterprise_rag.agent.query_rewriter import QueryRewriter
from enterprise_rag.agent.state import AgentState
from enterprise_rag.core.enums import AgentStatus, IntentType, RefusalReason
from enterprise_rag.core.exceptions import ErrorDetail, OperationTimeoutError
from enterprise_rag.domain.results import AnswerResult, RefusalResult
from enterprise_rag.retrieval.models import EvidenceBundle


class AgentOrchestrator:
    """中文：该类用于表示或实现“智能体编排器（AgentOrchestrator）”的职责。

    English: Coordinate bounded retrieval, grading, rewriting, answering, and verification.
    """

    def __init__(
        self,
        intent_router: IntentRouter,
        retrieve: Callable[[str, int], EvidenceBundle],
        evidence_grader: EvidenceGrader,
        query_rewriter: QueryRewriter,
        answer_generator: AnswerGenerator,
        citation_verifier: CitationVerifier,
        max_retrieval_retries: int,
        max_model_calls: int,
        max_total_tokens: int,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store state-machine components and hard execution budgets.
        """

        # 中文：变量 `_intent_router` 用于保存“意图路由器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Deterministic pre-retrieval request classifier.
        self._intent_router = intent_router
        # 中文：变量 `_retrieve` 用于保存“检索”相关数据；其精确定义与约束见下方英文说明。
        # English: Request-pinned retrieval callback.
        self._retrieve = retrieve
        # 中文：变量 `_evidence_grader` 用于保存“证据评估器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Deterministic evidence sufficiency policy.
        self._evidence_grader = evidence_grader
        # 中文：变量 `_query_rewriter` 用于保存“查询改写器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Provider-backed evidence-gap query rewriter.
        self._query_rewriter = query_rewriter
        # 中文：变量 `_answer_generator` 用于保存“答案生成器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Provider-backed evidence-only answer generator.
        self._answer_generator = answer_generator
        # 中文：变量 `_citation_verifier` 用于保存“引用验证器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Deterministic final citation boundary.
        self._citation_verifier = citation_verifier
        # 中文：变量 `_max_retrieval_retries` 用于保存“`max`检索`retries`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum rewrite count after the initial retrieval.
        self._max_retrieval_retries = max_retrieval_retries
        # 中文：变量 `_max_model_calls` 用于保存“`max`模型`calls`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum language-model calls across the workflow.
        self._max_model_calls = max_model_calls
        # 中文：变量 `_max_total_tokens` 用于保存“`max``total`词元”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum provider-reported aggregate tokens.
        self._max_total_tokens = max_total_tokens

    def run(
        self,
        state: AgentState,
        trace_step: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> AnswerResult | RefusalResult:
        """中文：该函数或方法负责“运行当前流程”相关处理。

        English: Execute until a verified answer, intentional refusal, or propagated system
        error.
        """

        self._ensure_time(state)
        # 中文：本步骤涉及意图、模型、预算，具体约束见下方英文说明。
        # English: Intent classification is deterministic and consumes no model budget.
        state.intent = self._intent_router.classify(state.original_query)
        self._emit(trace_step, "intent_routed", {"intent": state.intent.value})
        if state.intent is not IntentType.KNOWLEDGE:
            return self._non_knowledge_result(state)
        # 中文：变量 `max_rounds` 用于保存“`max``rounds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum total retrievals equals initial attempt plus configured rewrites.
        max_rounds = 1 + self._max_retrieval_retries
        while state.retrieval_rounds < max_rounds:
            self._ensure_time(state)
            state.status = AgentStatus.RETRIEVING
            # 中文：变量 `round_number` 用于保存“`round``number`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Next round number is fixed before calling the request-pinned
            #   retriever.
            round_number = state.retrieval_rounds + 1
            evidence = self._retrieve(state.current_query, round_number)
            state.retrieval_rounds = round_number
            state.evidence = evidence
            self._emit(
                trace_step,
                "retrieval_completed",
                {
                    "round": round_number,
                    "routing_mode": evidence.routing.mode,
                    "source_count": len(evidence.routing.source_ids),
                    "evidence_count": len(evidence.items),
                    "selected_k": evidence.top_k.selected_k,
                    "degradations": evidence.degradations,
                },
            )
            state.status = AgentStatus.GRADING
            grade = self._evidence_grader.grade(state.current_query, evidence)
            self._emit(
                trace_step,
                "evidence_graded",
                {
                    "round": round_number,
                    "sufficient": grade.sufficient,
                    "coverage": round(grade.coverage, 4),
                    "conflicting": grade.conflicting,
                    "reason": grade.reason,
                },
            )
            state.evidence_grade_reasons.append(grade.reason)
            if grade.sufficient:
                return self._generate_and_verify(state, trace_step)
            if state.retrieval_rounds >= max_rounds:
                break
            # 中文：本步骤涉及查询、模型，具体约束见下方英文说明。
            # English: Query rewriting consumes one language-model call and must remain
            #   within budgets.
            self._ensure_model_budget(state)
            state.status = AgentStatus.REWRITING
            try:
                rewritten, response = self._query_rewriter.rewrite(
                    original_query=state.original_query,
                    current_query=state.current_query,
                    grade=grade,
                    history=tuple(state.rewrite_history),
                )
            except ValueError:
                # 中文：变量 `break` 用于保存“`break`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Duplicate or empty rewrite cannot improve evidence and ends the
                #   loop safely.
                break
            self._record_usage(
                state,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            state.current_query = rewritten
            state.rewrite_history.append(rewritten)
            self._emit(
                trace_step,
                "query_rewritten",
                {"round": round_number, "model_call_count": state.model_call_count},
            )
        state.status = AgentStatus.REFUSED
        return RefusalResult(
            trace_id=state.trace_id,
            reason=RefusalReason.INSUFFICIENT_EVIDENCE,
            message="The authorized documents do not contain enough evidence to answer safely.",
            index_version_id=state.index_version_id,
        )

    def _generate_and_verify(
        self,
        state: AgentState,
        trace_step: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> AnswerResult | RefusalResult:
        """中文：该内部函数负责“生成并且验证”相关处理。

        English: Generate one answer draft and enforce the final citation boundary.
        """

        if state.evidence is None:
            raise ValueError("answer generation requires evidence")
        self._ensure_model_budget(state)
        self._ensure_time(state)
        state.status = AgentStatus.GENERATING
        response = self._answer_generator.generate(state.original_query, state.evidence)
        self._record_usage(
            state,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        state.answer_draft = response.text.strip()
        self._emit(
            trace_step,
            "answer_generated",
            {
                "model_call_count": state.model_call_count,
                "reported_tokens": state.token_count,
                "declared_insufficient": state.answer_draft == "INSUFFICIENT_EVIDENCE",
            },
        )
        if state.answer_draft == "INSUFFICIENT_EVIDENCE":
            state.status = AgentStatus.REFUSED
            return RefusalResult(
                trace_id=state.trace_id,
                reason=RefusalReason.INSUFFICIENT_EVIDENCE,
                message="The answer model determined that the evidence is insufficient.",
                index_version_id=state.index_version_id,
            )
        state.status = AgentStatus.VERIFYING
        verification = self._citation_verifier.verify(
            state.answer_draft,
            state.evidence,
            state.retrieval_scope,
        )
        self._emit(
            trace_step,
            "citations_verified",
            {
                "valid": verification.valid,
                "citation_count": len(verification.citations),
                "reason": verification.reason,
            },
        )
        if not verification.valid:
            state.status = AgentStatus.REFUSED
            return RefusalResult(
                trace_id=state.trace_id,
                reason=RefusalReason.INSUFFICIENT_EVIDENCE,
                message=(
                    "The generated answer could not pass citation verification: "
                    f"{verification.reason}"
                ),
                index_version_id=state.index_version_id,
            )
        state.verified_answer = state.answer_draft
        state.citations = verification.citations
        state.status = AgentStatus.ANSWERED
        return AnswerResult(
            trace_id=state.trace_id,
            answer=state.verified_answer,
            citations=state.citations,
            index_version_id=state.index_version_id,
            retrieval_rounds=state.retrieval_rounds,
        )

    @staticmethod
    def _emit(
        trace_step: Callable[[str, Mapping[str, object]], None] | None,
        name: str,
        attributes: Mapping[str, object],
    ) -> None:
        """中文：在不耦合具体记录器的前提下发送一条已脱敏状态机步骤。

        English: Emit one redacted state-machine step without coupling to a concrete recorder.
        """

        if trace_step is not None:
            trace_step(name, attributes)

    @staticmethod
    def _non_knowledge_result(state: AgentState) -> RefusalResult:
        """中文：该内部函数负责“非知识结果”相关处理。

        English: Map non-knowledge intents to explicit unsupported or unsafe outcomes.
        """

        if state.intent is IntentType.UNSAFE:
            state.status = AgentStatus.REFUSED
            return RefusalResult(
                trace_id=state.trace_id,
                reason=RefusalReason.UNSAFE_REQUEST,
                message="This request cannot be completed safely.",
                index_version_id=None,
            )
        state.status = AgentStatus.UNSUPPORTED
        return RefusalResult(
            trace_id=state.trace_id,
            reason=RefusalReason.UNSUPPORTED_REQUEST,
            message="V0.3 answers questions grounded in authorized enterprise documents.",
            index_version_id=None,
        )

    def _ensure_model_budget(self, state: AgentState) -> None:
        """中文：该内部函数负责“确保模型预算”相关处理。

        English: Raise before a model call would exceed configured call or token budgets.
        """

        if state.model_call_count >= self._max_model_calls:
            raise RuntimeError("agent model-call budget exhausted")
        if state.token_count >= self._max_total_tokens:
            raise RuntimeError("agent token budget exhausted")

    def _record_usage(self, state: AgentState, input_tokens: int, output_tokens: int) -> None:
        """中文：该内部函数负责“记录用量”相关处理。

        English: Add one provider call's usage and enforce the aggregate token limit.
        """

        state.model_call_count += 1
        state.token_count += max(0, input_tokens) + max(0, output_tokens)
        if state.token_count > self._max_total_tokens:
            raise RuntimeError("agent token budget exceeded")

    @staticmethod
    def _ensure_time(state: AgentState) -> None:
        """中文：该内部函数负责“确保时间”相关处理。

        English: Raise a typed timeout when the workflow reaches its absolute deadline.
        """

        if datetime.now(UTC) >= state.deadline:
            state.status = AgentStatus.TIMEOUT
            raise OperationTimeoutError(
                # 中文：此处调用 `_timeout_detail` 以执行“`timeout``detail`”相关步骤；
                # 具体约束见下方英文说明。
                # English: Imported lazily avoids duplicating error construction at other
                #   state transitions.
                _timeout_detail()
            )


def _timeout_detail() -> ErrorDetail:
    """中文：该内部函数负责“超时详情”相关处理。

    English: Create the structured timeout detail required by OperationTimeoutError.
    """

    from enterprise_rag.core.enums import ErrorCategory
    from enterprise_rag.core.exceptions import error_detail

    return error_detail(
        "AGENT_TIMEOUT",
        ErrorCategory.TIMEOUT,
        "The question-answering workflow exceeded its deadline.",
    )
