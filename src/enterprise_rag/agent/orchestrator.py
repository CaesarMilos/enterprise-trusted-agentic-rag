"""中文：本模块负责实现“编排器”相关功能。

English: Run the explicit bounded Agentic RAG state machine without LangGraph.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from enterprise_rag.agent.answer_generator import AnswerGenerator
from enterprise_rag.agent.answer_protocol import build_verified_answer
from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.agent.intent_router import IntentRouter
from enterprise_rag.agent.query_rewriter import QueryRewriter
from enterprise_rag.agent.question_planner import QuestionPlanner
from enterprise_rag.agent.state import AgentState
from enterprise_rag.core.deadline import DeadlineBudget
from enterprise_rag.core.enums import (
    AgentStatus,
    AnswerStatus,
    EvidenceStatus,
    IntentType,
    RefusalReason,
)
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
        retrieve: Callable[..., EvidenceBundle],
        evidence_grader: EvidenceGrader,
        query_rewriter: QueryRewriter,
        answer_generator: AnswerGenerator,
        citation_verifier: CitationVerifier,
        max_retrieval_retries: int,
        max_model_calls: int,
        max_total_tokens: int,
        question_planner: QuestionPlanner | None = None,
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
        # 中文：确定性规划器不消耗模型预算，并且对文档类型无感知。
        # English: The deterministic planner consumes no model budget and is document-agnostic.
        self._question_planner = question_planner or QuestionPlanner()

    def run(
        self,
        state: AgentState,
        trace_step: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> AnswerResult | RefusalResult:
        """中文：该函数或方法负责“运行当前流程”相关处理。

        English: Execute until a verified answer, intentional refusal, or propagated system
        error.
        """

        initial_remaining = (state.deadline - datetime.now(UTC)).total_seconds()
        if initial_remaining <= 0:
            self._ensure_time(state, None, "workflow_start")
        deadline = DeadlineBudget.from_timeout(initial_remaining)
        self._ensure_time(state, deadline, "workflow_start")
        # 中文：本步骤涉及意图、模型、预算，具体约束见下方英文说明。
        # English: Intent classification is deterministic and consumes no model budget.
        state.intent = self._intent_router.classify(state.original_query)
        self._emit(trace_step, "intent_routed", {"intent": state.intent.value})
        if state.intent is not IntentType.KNOWLEDGE:
            return self._non_knowledge_result(state)
        state.question_plan = self._question_planner.plan(state.original_query)
        state.current_query = state.question_plan.knowledge_query
        self._emit(
            trace_step,
            "question_planned",
            {
                "fingerprint": state.question_plan.fingerprint,
                "required_need_ids": tuple(need.id for need in state.question_plan.needs),
                "anchor_values": tuple(
                    anchor.normalized_value for anchor in state.question_plan.anchors
                ),
                "requested_item_count": (
                    state.question_plan.response_contract.requested_item_count
                ),
            },
        )
        # 中文：变量 `max_rounds` 用于保存“`max``rounds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum total retrievals equals initial attempt plus configured rewrites.
        max_rounds = 1 + self._max_retrieval_retries
        # 中文：变量 `last_grade` 保存最终 Need 覆盖向量，供安全部分回答决策使用。
        # English: `last_grade` preserves the final need vector for safe partial-answer policy.
        last_grade = None
        while state.retrieval_rounds < max_rounds:
            self._ensure_time(state, deadline, "before_retrieval")
            state.status = AgentStatus.RETRIEVING
            # 中文：变量 `round_number` 用于保存“`round``number`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Next round number is fixed before calling the request-pinned
            #   retriever.
            round_number = state.retrieval_rounds + 1
            evidence = self._retrieve_with_deadline(
                state.current_query,
                round_number,
                deadline,
                state.question_plan,
            )
            # 中文：检索迟到结果在使用前丢弃，超时不得伪装成“无证据”。
            # English: Discard late retrieval before use; timeout is not "no evidence".
            self._ensure_time(state, deadline, "after_retrieval")
            state.retrieval_rounds = round_number
            state.evidence = evidence
            retrieval_trace = evidence.retrieval_trace
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
                    "dense_ranking": (
                        tuple(item.chunk_id for item in retrieval_trace.dense)
                        if retrieval_trace is not None
                        else ()
                    ),
                    "bm25_ranking": (
                        tuple(item.chunk_id for item in retrieval_trace.bm25)
                        if retrieval_trace is not None
                        else ()
                    ),
                    "rrf_ranking": (
                        tuple(item.chunk_id for item in retrieval_trace.fused)
                        if retrieval_trace is not None
                        else ()
                    ),
                    "reranker_ranking": (
                        tuple(item.chunk_id for item in retrieval_trace.reranked)
                        if retrieval_trace is not None
                        else ()
                    ),
                    "selected_child_ids": (
                        tuple(item.chunk_id for item in retrieval_trace.selected)
                        if retrieval_trace is not None
                        else ()
                    ),
                    "parent_context_by_child": (
                        retrieval_trace.parent_context_by_child
                        if retrieval_trace is not None
                        else ()
                    ),
                },
            )
            state.status = AgentStatus.GRADING
            grade = self._evidence_grader.grade(
                state.current_query,
                evidence,
                state.question_plan,
            )
            last_grade = grade
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
                return self._generate_and_verify(
                    state,
                    deadline,
                    grade,
                    AnswerStatus.ANSWERED,
                    trace_step,
                )
            if state.retrieval_rounds >= max_rounds:
                break
            # 中文：本步骤涉及查询、模型，具体约束见下方英文说明。
            # English: Query rewriting consumes one language-model call and must remain
            #   within budgets.
            self._ensure_model_budget(state)
            state.status = AgentStatus.REWRITING
            try:
                rewrite_decision, response = self._query_rewriter.decide(
                    original_query=state.original_query,
                    current_query=state.current_query,
                    grade=grade,
                    history=tuple(state.rewrite_history),
                    timeout_seconds=deadline.remaining_seconds(),
                )
            except ValueError:
                # 中文：变量 `break` 用于保存“`break`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Duplicate or empty rewrite cannot improve evidence and ends the
                #   loop safely.
                break
            self._ensure_time(state, deadline, "after_query_rewrite")
            self._record_usage(
                state,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            if not rewrite_decision.should_rewrite or rewrite_decision.rewritten_query is None:
                break
            state.current_query = rewrite_decision.rewritten_query
            state.rewrite_history.append(rewrite_decision.rewritten_query)
            self._emit(
                trace_step,
                "query_rewritten",
                {
                    "round": round_number,
                    "model_call_count": state.model_call_count,
                    "missing_need_ids": rewrite_decision.missing_need_ids,
                    "preserved_anchors": rewrite_decision.preserved_anchors,
                    "drift_score": round(rewrite_decision.drift_score, 4),
                    "reason": rewrite_decision.reason,
                },
            )
        # 中文：至少一个 required Need 完整支持且不存在真实冲突时，可返回受约束部分回答；
        # 仅有低覆盖“部分证据”仍然拒答，避免把不完整证据包装成结论。
        # English: A constrained partial answer requires at least one fully supported required
        # need and no true conflict; weak partial evidence alone remains a refusal.
        if (
            last_grade is not None
            and state.evidence is not None
            and state.question_plan is not None
            and not last_grade.conflicting
            and last_grade.missing_need_ids
            and any(item.status is EvidenceStatus.SUPPORTED for item in last_grade.need_grades)
        ):
            return self._generate_and_verify(
                state,
                deadline,
                last_grade,
                AnswerStatus.PARTIAL,
                trace_step,
            )
        state.status = AgentStatus.REFUSED
        return RefusalResult(
            trace_id=state.trace_id,
            reason=RefusalReason.INSUFFICIENT_EVIDENCE,
            message="The authorized documents do not contain enough evidence to answer safely.",
            index_version_id=state.index_version_id,
            retrieval_trace=(
                state.evidence.retrieval_trace if state.evidence is not None else None
            ),
        )

    def _retrieve_with_deadline(
        self,
        query: str,
        round_number: int,
        deadline: DeadlineBudget,
        plan: object,
    ) -> EvidenceBundle:
        """中文：向支持的检索回调传入全局预算，同时兼容 V4 两参数实现。

        English: Pass the global budget to capable retrievers while preserving V4 callbacks.
        """

        if len(inspect.signature(self._retrieve).parameters) >= 4:
            return self._retrieve(query, round_number, deadline, plan)
        if len(inspect.signature(self._retrieve).parameters) >= 3:
            return self._retrieve(query, round_number, deadline)
        return self._retrieve(query, round_number)

    def _generate_and_verify(
        self,
        state: AgentState,
        deadline: DeadlineBudget,
        grade: object,
        answer_status: AnswerStatus,
        trace_step: Callable[[str, Mapping[str, object]], None] | None = None,
    ) -> AnswerResult | RefusalResult:
        """中文：该内部函数负责“生成并且验证”相关处理。

        English: Generate one answer draft and enforce the final citation boundary.
        """

        if state.evidence is None or state.question_plan is None:
            raise ValueError("answer generation requires evidence and a question plan")
        # 中文：内部类型在循环中由 EvidenceGrader 固定返回；局部导入避免扩大公开接口。
        # English: EvidenceGrader fixes the runtime type; local validation keeps the public
        # method surface compact.
        from enterprise_rag.agent.evidence_grader import EvidenceGrade

        if not isinstance(grade, EvidenceGrade):
            raise TypeError("answer generation requires an EvidenceGrade")
        need_by_id = {need.id: need for need in state.question_plan.needs}
        supported_need_ids = tuple(
            item.need_id for item in grade.need_grades if item.status is EvidenceStatus.SUPPORTED
        )
        supported_needs = tuple(
            need_by_id[need_id].description
            for need_id in supported_need_ids
            if need_id in need_by_id
        )
        unresolved_needs = tuple(
            need_by_id[need_id].description
            for need_id in grade.missing_need_ids
            if need_id in need_by_id
        )
        self._ensure_model_budget(state)
        self._ensure_time(state, deadline, "before_answer_generation")
        state.status = AgentStatus.GENERATING
        response = self._answer_generator.generate(
            state.original_query,
            state.evidence,
            timeout_seconds=deadline.remaining_seconds(),
            supported_needs=supported_needs,
            unresolved_needs=(unresolved_needs if answer_status is AnswerStatus.PARTIAL else ()),
        )
        # 中文：模型在截止后返回的文本永远不会进入用量、答案或引用处理。
        # English: Model text returned after expiry never reaches usage, answer, or citations.
        self._ensure_time(state, deadline, "after_answer_generation")
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
                retrieval_trace=state.evidence.retrieval_trace,
            )
        state.status = AgentStatus.VERIFYING
        self._ensure_time(state, deadline, "before_citation_verification")
        verification = self._citation_verifier.verify(
            state.answer_draft,
            state.evidence,
            state.retrieval_scope,
        )
        self._ensure_time(state, deadline, "after_citation_verification")
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
                retrieval_trace=state.evidence.retrieval_trace,
            )
        try:
            protocol = build_verified_answer(
                answer_text=state.answer_draft,
                citations=verification.citations,
                evidence=state.evidence,
                plan=state.question_plan,
                grade=grade,
                scope=state.retrieval_scope,
                trace_id=state.trace_id,
                retrieval_rounds=state.retrieval_rounds,
                status=answer_status,
            )
        except ValueError as exc:
            # 中文：Claim 无法确定性绑定 Need 时拒答，不允许退化成无映射的自然语言结果。
            # English: If a claim cannot be deterministically bound to a need, refuse rather
            # than returning unstructured natural language.
            state.status = AgentStatus.REFUSED
            self._emit(
                trace_step,
                "answer_protocol_rejected",
                {"reason": str(exc)},
            )
            return RefusalResult(
                trace_id=state.trace_id,
                reason=RefusalReason.INSUFFICIENT_EVIDENCE,
                message="The generated answer could not be bound to verified evidence claims.",
                index_version_id=state.index_version_id,
                retrieval_trace=state.evidence.retrieval_trace,
            )
        state.verified_answer = state.answer_draft
        state.citations = verification.citations
        state.status = (
            AgentStatus.PARTIAL if answer_status is AnswerStatus.PARTIAL else AgentStatus.ANSWERED
        )
        return AnswerResult(
            trace_id=state.trace_id,
            answer=state.verified_answer,
            citations=state.citations,
            index_version_id=state.index_version_id,
            retrieval_rounds=state.retrieval_rounds,
            retrieval_trace=state.evidence.retrieval_trace,
            status=answer_status,
            verified_protocol=protocol,
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
            message="V5 answers questions grounded in authorized enterprise documents.",
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
    def _ensure_time(
        state: AgentState,
        deadline: DeadlineBudget | None,
        stage: str,
    ) -> None:
        """中文：同时检查 UTC 与单调时钟截止点，并记录发生超时的阶段。

        English: Check UTC and monotonic deadlines and record the stage at which time expired.
        """

        if datetime.now(UTC) >= state.deadline or (
            deadline is not None and deadline.remaining_seconds() <= 0
        ):
            state.status = AgentStatus.TIMEOUT
            raise OperationTimeoutError(
                # 中文：此处调用 `_timeout_detail` 以执行“`timeout``detail`”相关步骤；
                # 具体约束见下方英文说明。
                # English: Imported lazily avoids duplicating error construction at other
                #   state transitions.
                _timeout_detail(stage)
            )


def _timeout_detail(stage: str) -> ErrorDetail:
    """中文：该内部函数负责“超时详情”相关处理。

    English: Create the structured timeout detail required by OperationTimeoutError.
    """

    from enterprise_rag.core.enums import ErrorCategory
    from enterprise_rag.core.exceptions import error_detail

    return error_detail(
        "AGENT_DEADLINE_EXCEEDED",
        ErrorCategory.TIMEOUT,
        "The question-answering workflow exceeded its hard deadline.",
        stage=stage,
    )
