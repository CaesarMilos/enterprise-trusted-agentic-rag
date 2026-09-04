"""中文：本模块负责实现“答案生成器”相关功能。

English: Generate an answer solely from the final bounded evidence bundle.
"""

from __future__ import annotations

from enterprise_rag.agent.model_invocation import complete_with_timeout
from enterprise_rag.agent.prompts import ANSWER_SYSTEM_PROMPT
from enterprise_rag.domain.protocols.models import LLMProvider, ModelResponse
from enterprise_rag.retrieval.models import EvidenceBundle


class AnswerGenerator:
    """中文：该类用于表示或实现“答案生成器（AnswerGenerator）”的职责。

    English: Invoke a provider-neutral model with injection-resistant evidence formatting.
    """

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the configured language-model provider.
        """

        # 中文：变量 `_provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
        # English: One provider instance is reused by application dependency wiring.
        self._provider = provider

    def generate(
        self,
        query: str,
        evidence: EvidenceBundle,
        timeout_seconds: float | None = None,
        *,
        supported_needs: tuple[str, ...] = (),
        unresolved_needs: tuple[str, ...] = (),
    ) -> ModelResponse:
        """中文：该函数或方法负责“生成”相关处理。

        English: Return an unverified answer draft and provider usage.
        """

        # 中文：变量 `user_prompt` 用于保存“用户提示词”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Evidence context explicitly marks document text as untrusted data.
        # 中文：部分回答只允许覆盖已支持 Need，并把未解决 Need 明示为禁止推断范围。
        # English: Partial generation may address supported needs only and treats unresolved
        # needs as an explicit no-inference boundary.
        coverage_instruction = ""
        if unresolved_needs:
            supported = "\n".join(f"- {item}" for item in supported_needs)
            unresolved = "\n".join(f"- {item}" for item in unresolved_needs)
            coverage_instruction = (
                "\n\nThis is a PARTIAL answer. Answer only these supported needs:\n"
                f"{supported}\n"
                "Do not answer, infer, or mention facts for these unresolved needs:\n"
                f"{unresolved}\n"
                "Do not claim that the response is complete."
            )
        user_prompt = (
            f"Question:\n{query}\n\n"
            f"Authorized evidence from index {evidence.index_version_id}:\n"
            f"{evidence.context_text}{coverage_instruction}"
        )
        return complete_with_timeout(
            self._provider,
            ANSWER_SYSTEM_PROMPT,
            user_prompt,
            {"operation": "answer_generation"},
            timeout_seconds,
        )
