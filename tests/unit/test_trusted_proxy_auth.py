"""中文：验证生产可信代理身份适配器的密钥和完整性边界。

English: Verify secret and identity-completeness boundaries for trusted proxy authentication.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from enterprise_rag.api.dependencies import AppContainer, get_user_context
from enterprise_rag.core.config import SecuritySettings, Settings


def _trusted_proxy_container() -> AppContainer:
    """中文：构造仅供身份依赖测试使用的生产设置容器。

    English: Build a production settings container used only by the identity dependency tests.
    """

    settings = Settings(
        security=SecuritySettings(
            trusted_proxy_auth_enabled=True,
            trusted_proxy_secret_env="TEST_ENTERPRISE_RAG_PROXY_SECRET",
        )
    )
    return cast(AppContainer, SimpleNamespace(settings=settings))


def test_trusted_proxy_accepts_only_verified_complete_identity(monkeypatch: Any) -> None:
    """中文：确认密钥匹配且用户/租户头完整时才构造授权上下文。

    English: Ensure only a matching secret plus complete user and tenant headers create identity.
    """

    monkeypatch.setenv("TEST_ENTERPRISE_RAG_PROXY_SECRET", "expected-secret")
    identity = get_user_context(
        _trusted_proxy_container(),
        user_id="employee-a",
        tenant_id="tenant-a",
        roles="reader,auditor",
        source_ids="source-a",
        group_ids="group-a",
        proxy_secret="expected-secret",
    )

    assert identity.user_id == "employee-a"
    assert identity.tenant_id == "tenant-a"
    assert identity.roles == frozenset({"reader", "auditor"})
    assert identity.allowed_source_ids == frozenset({"source-a"})


def test_trusted_proxy_rejects_a_forged_secret(monkeypatch: Any) -> None:
    """中文：确认外部客户端无法伪造代理注入的身份头。

    English: Ensure an external client cannot forge proxy-injected identity headers.
    """

    monkeypatch.setenv("TEST_ENTERPRISE_RAG_PROXY_SECRET", "expected-secret")
    with pytest.raises(HTTPException) as captured:
        get_user_context(
            _trusted_proxy_container(),
            user_id="admin-a",
            tenant_id="tenant-a",
            roles="admin",
            source_ids=None,
            group_ids=None,
            proxy_secret="forged-secret",
        )

    assert captured.value.status_code == 401
