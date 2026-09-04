"""中文：本模块负责实现“问答”相关功能。

English: Expose the trusted chat use case without direct index or model access.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from enterprise_rag.api.dependencies import AppContainer, get_container, get_user_context
from enterprise_rag.api.schemas import (
    AnswerClaimSchema,
    AnswerItemSchema,
    ChatRequest,
    ChatResponse,
    CitationSchema,
    MissingInformationSchema,
)
from enterprise_rag.domain.models import UserContext
from enterprise_rag.domain.requests import ChatCommand
from enterprise_rag.domain.results import AnswerResult

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Router prefix is combined with the application API prefix.
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> ChatResponse:
    """中文：该函数或方法负责“问答”相关处理。

    English: Return a verified cited answer or an explicit refusal.
    """

    # 中文：变量 `result` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
    # English: Service command is framework-independent and contains trusted user context.
    result = container.chat.chat(
        ChatCommand(
            user=user,
            query=payload.query,
            conversation_id=payload.conversation_id,
            requested_source_ids=frozenset(payload.requested_source_ids),
        )
    )
    if isinstance(result, AnswerResult):
        # 中文：V5 客户端可消费结构化协议；V4 客户端继续读取 answer/citations。
        # English: V5 clients consume the structured protocol while V4 clients continue to
        # read answer and citations.
        protocol = result.verified_protocol
        return ChatResponse(
            trace_id=result.trace_id,
            status=result.status.value,
            answer=result.answer,
            citations=[CitationSchema(**asdict(citation)) for citation in result.citations],
            items=(
                [
                    AnswerItemSchema(
                        id=item.id,
                        need_ids=list(item.need_ids),
                        text=item.text,
                        claim_ids=list(item.claim_ids),
                    )
                    for item in protocol.items
                ]
                if protocol is not None
                else []
            ),
            claims=(
                [
                    AnswerClaimSchema(
                        id=claim.id,
                        text=claim.text,
                        need_ids=list(claim.need_ids),
                        evidence_ids=list(claim.evidence_ids),
                        citation_ids=list(claim.citation_ids),
                        verification_status=claim.verification_status.value,
                    )
                    for claim in protocol.claims
                ]
                if protocol is not None
                else []
            ),
            missing_information=(
                [
                    MissingInformationSchema(
                        need_id=item.need_id,
                        description=item.description,
                        reason=item.reason.value,
                    )
                    for item in protocol.missing_information
                ]
                if protocol is not None
                else []
            ),
            index_version_id=result.index_version_id,
            retrieval_rounds=result.retrieval_rounds,
        )
    return ChatResponse(
        trace_id=result.trace_id,
        status="refused",
        refusal_reason=result.reason.value,
        message=result.message,
        index_version_id=result.index_version_id,
    )
