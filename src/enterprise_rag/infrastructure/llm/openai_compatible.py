"""中文：本模块负责实现“`openai`兼容”相关功能。

English: Call OpenAI-compatible chat completions without coupling callers to a vendor SDK.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping

from enterprise_rag.domain.protocols.models import ModelResponse, ModelUsage
from enterprise_rag.infrastructure.llm.base import safe_metadata


class OpenAICompatibleLLM:
    """中文：该类用于表示或实现“打开AI兼容大语言模型（OpenAICompatibleLLM）”的职责。

    English: Implement provider-neutral text completion through the standard chat endpoint.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key_env: str,
        timeout_seconds: int,
        temperature: float = 0.0,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store endpoint and model configuration without storing secret key values.
        """

        # 中文：变量 `_model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
        # English: Provider model identifier.
        self._model = model
        # 中文：变量 `_base_url` 用于保存“基础`url`”相关数据；其精确定义与约束见下方英文说明。
        # English: Service root normalized for path construction.
        self._base_url = base_url.rstrip("/")
        # 中文：变量 `_api_key_env` 用于保存“接口`key``env`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Environment variable name containing the key.
        self._api_key_env = api_key_env
        # 中文：变量 `_timeout_seconds` 用于保存“`timeout``seconds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Per-call HTTP deadline.
        self._timeout_seconds = timeout_seconds
        # 中文：变量 `_temperature` 用于保存“`temperature`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Sampling temperature for deterministic grounded answers by default.
        self._temperature = temperature

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint without endpoint credentials.
        """

        return f"openai-compatible-chat:{self._model}"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        metadata: Mapping[str, str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> ModelResponse:
        """中文：该函数或方法负责“完成一次模型调用”相关处理。

        English: Return generated text and normalized token usage.
        """

        # 中文：变量 `api_key` 用于保存“接口`key`”相关数据；其精确定义与约束见下方英文说明。
        # English: Secret is read only for the outbound request.
        api_key = os.getenv(self._api_key_env, "")
        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: Standard chat-completions body is compatible with OpenAI, BaiLian,
        #   Zhipu, and Ollama.
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "metadata": safe_metadata(metadata),
        }
        # 中文：本步骤涉及元数据，具体约束见下方英文说明。
        # English: Empty metadata is removed for providers that reject the optional field.
        if not payload["metadata"]:
            payload.pop("metadata")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            # 中文：单次 HTTP 超时不得超过 Agent 剩余硬预算。
            # English: Per-call HTTP timeout never exceeds the agent's remaining hard budget.
            request_timeout = (
                self._timeout_seconds
                if timeout_seconds is None
                else max(0.05, min(float(self._timeout_seconds), timeout_seconds))
            )
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("chat completion request failed") from exc
        # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
        # English: Response shape follows the OpenAI-compatible choices convention.
        text = str(result["choices"][0]["message"]["content"])
        # 中文：变量 `usage` 用于保存“`usage`”相关数据；其精确定义与约束见下方英文说明。
        # English: Missing usage is common for local providers and safely defaults to zero.
        usage = result.get("usage", {})
        return ModelResponse(
            text=text,
            usage=ModelUsage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
            ),
            model=str(result.get("model", self._model)),
        )
