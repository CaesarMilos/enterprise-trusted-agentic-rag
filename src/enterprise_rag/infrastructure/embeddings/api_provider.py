"""中文：本模块负责实现“接口提供方”相关功能。

English: Call an OpenAI-compatible embeddings endpoint with bounded JSON requests.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence


class APIEmbeddingProvider:
    """中文：该类用于表示或实现“接口向量嵌入提供方（APIEmbeddingProvider）”的职责。

    English: Implement the embedding port through an OpenAI-compatible HTTP API.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key_env: str,
        timeout_seconds: int = 45,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store endpoint configuration while reading credentials only at call time.
        """

        # 中文：变量 `_model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
        # English: Model identifier appears in every request and fingerprint.
        self._model = model
        # 中文：变量 `_base_url` 用于保存“基础`url`”相关数据；其精确定义与约束见下方英文说明。
        # English: Normalized service root supports endpoints with or without a trailing
        #   slash.
        self._base_url = base_url.rstrip("/")
        # 中文：变量 `_api_key_env` 用于保存“接口`key``env`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Environment variable name avoids storing secret material in Settings.
        self._api_key_env = api_key_env
        # 中文：变量 `_timeout_seconds` 用于保存“`timeout``seconds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: HTTP deadline bounds provider latency.
        self._timeout_seconds = timeout_seconds

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint without exposing the endpoint or
        key.
        """

        return f"openai-compatible-embedding:{self._model}"

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """中文：该函数或方法负责“向量化”相关处理。

        English: Return vectors reordered by the response index field.
        """

        # 中文：变量 `api_key` 用于保存“接口`key`”相关数据；其精确定义与约束见下方英文说明。
        # English: API key is resolved at the last possible moment and never logged.
        api_key = os.getenv(self._api_key_env, "")
        # 中文：变量 `body` 用于保存“`body`”相关数据；其精确定义与约束见下方英文说明。
        # English: Request body preserves caller text ordering.
        body = json.dumps({"model": self._model, "input": list(texts)}).encode("utf-8")
        # 中文：变量 `headers` 用于保存“`headers`”相关数据；其精确定义与约束见下方英文说明。
        # English: Authorization header is omitted for explicitly keyless local endpoints.
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(
            f"{self._base_url}/embeddings",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("embedding API request failed") from exc
        # 中文：变量 `ordered` 用于保存“`ordered`”相关数据；其精确定义与约束见下方英文说明。
        # English: OpenAI response entries contain explicit input indices.
        ordered = sorted(payload["data"], key=lambda item: int(item["index"]))
        return tuple(tuple(float(value) for value in item["embedding"]) for item in ordered)
