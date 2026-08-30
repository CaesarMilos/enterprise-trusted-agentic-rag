"""中文：在创建数据库和网络服务前验证生产认证配置是否完整。

English: Validate production authentication before creating database or network services.
"""

from __future__ import annotations

import os

from enterprise_rag.core.config import Settings
from enterprise_rag.core.enums import AuthenticationMode


def validate_security_startup(settings: Settings) -> None:
    """中文：生产环境缺少 JWT/代理密钥或启用 Demo 时拒绝启动。

    English: Refuse production startup for demo mode or missing JWT/proxy secrets.
    """

    if settings.application.environment != "production":
        return
    mode = settings.security.authentication_mode
    if mode is AuthenticationMode.DEMO:
        raise RuntimeError("demo authentication is forbidden in production")
    secret_env = (
        settings.security.jwt_secret_env
        if mode is AuthenticationMode.JWT
        else settings.security.trusted_proxy_secret_env
    )
    if not os.getenv(secret_env, ""):
        raise RuntimeError(f"production authentication requires environment variable {secret_env}")
