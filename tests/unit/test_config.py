"""中文：本模块负责实现“测试配置”相关功能。

English: Verify precedence, path resolution, and safety validation in application settings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_rag.core.config import load_settings
from enterprise_rag.core.exceptions import ValidationError

# 中文：变量 `_DEFAULT_CONFIG` 用于保存“默认配置”相关数据；其精确定义与约束见下方英文说明。
# English: Repository default configuration used by every test in this module.
_DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"
# 中文：变量 `_DEVELOPMENT_CONFIG` 用于保存“开发配置”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Repository development override used to verify layered configuration.
_DEVELOPMENT_CONFIG = Path(__file__).parents[2] / "configs" / "development.yaml"


def test_environment_values_have_highest_precedence() -> None:
    """中文：该测试用于验证“环境值具有最高优先级”相关行为。

    English: Ensure nested environment variables override both YAML layers.
    """

    # 中文：变量 `environ` 用于保存“`environ`”相关数据；其精确定义与约束见下方英文说明。
    # English: Explicit mapping avoids dependence on the test runner's process environment.
    environ = {
        "ENTERPRISE_RAG__RETRIEVAL__MAX_K": "8",
        "ENTERPRISE_RAG__AGENT__TIMEOUT_SECONDS": "15",
    }
    # 中文：变量 `settings` 用于保存“设置”相关数据；其精确定义与约束见下方英文说明。
    # English: Loaded settings should be fully validated and immutable.
    settings = load_settings(_DEFAULT_CONFIG, _DEVELOPMENT_CONFIG, environ=environ)

    assert settings.application.environment == "development"
    assert settings.config_version == "5.0"
    assert settings.retrieval.max_k == 8
    assert settings.agent.timeout_seconds == 15
    assert settings.storage.upload_dir.is_absolute()


def test_production_rejects_demo_authentication() -> None:
    """中文：该测试用于验证“生产拒绝演示认证”相关行为。

    English: Ensure the header-based development identity cannot run in production.
    """

    # 中文：变量 `environ` 用于保存“`environ`”相关数据；其精确定义与约束见下方英文说明。
    # English: Environment override deliberately attempts to enable the unsafe production
    #   setting.
    environ = {"ENTERPRISE_RAG__SECURITY__DEMO_AUTH_ENABLED": "true"}

    with pytest.raises(ValidationError):
        load_settings(_DEFAULT_CONFIG, environ=environ)


def test_invalid_top_k_bounds_are_rejected() -> None:
    """中文：该测试用于验证“无效的TopK 值边界为被拒绝的”相关行为。

    English: Ensure dynamic Top-K limits cannot be configured in descending order.
    """

    # 中文：变量 `environ` 用于保存“`environ`”相关数据；其精确定义与约束见下方英文说明。
    # English: Maximum below the default creates an invalid cross-field relationship.
    environ = {"ENTERPRISE_RAG__RETRIEVAL__MAX_K": "4"}

    with pytest.raises(ValidationError):
        load_settings(_DEFAULT_CONFIG, environ=environ)


def test_request_body_limit_must_reserve_multipart_overhead() -> None:
    """中文：确认完整请求体上限必须大于原文件上限。

    English: Ensure the whole-body limit exceeds the original-file limit for multipart overhead.
    """

    environ = {
        "ENTERPRISE_RAG__INGESTION__MAX_FILE_SIZE_MB": "50",
        "ENTERPRISE_RAG__INGESTION__MAX_REQUEST_BODY_SIZE_MB": "50",
    }

    with pytest.raises(ValidationError):
        load_settings(_DEFAULT_CONFIG, environ=environ)
