"""中文：验证 JWT 模式只接受签名、时效、签发者和受众均可信的租户身份。

English: Verify JWT mode accepts only tenant identities with valid signature and claims.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from enterprise_rag.security.jwt_auth import decode_hs256_user_context


def _segment(payload: object) -> str:
    """中文：把测试声明编码为无填充 Base64URL 段。

    English: Encode a test claim object as an unpadded Base64URL segment.
    """

    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _token(secret: str, *, expiration: int = 2_000) -> str:
    """中文：用固定声明生成确定性的 HS256 测试令牌。

    English: Generate a deterministic HS256 test token with fixed claims.
    """

    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment(
        {
            "sub": "user-a",
            "tenant_id": "tenant-a",
            "roles": ["reader", "admin"],
            "source_ids": "source-a,source-b",
            "group_ids": ["operations"],
            "iss": "enterprise-rag",
            "aud": "enterprise-rag-api",
            "exp": expiration,
        }
    )
    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{signing_input}.{encoded_signature}"


def test_valid_jwt_builds_scoped_user_context() -> None:
    """中文：可信声明必须被收窄为不可变角色、资料源和用户组集合。

    English: Trusted claims must narrow into immutable role, source, and group sets.
    """

    context = decode_hs256_user_context(
        _token("correct-secret"),
        "correct-secret",
        "enterprise-rag",
        "enterprise-rag-api",
        now=1_000,
    )

    assert context.user_id == "user-a"
    assert context.tenant_id == "tenant-a"
    assert context.roles == frozenset({"reader", "admin"})
    assert context.allowed_source_ids == frozenset({"source-a", "source-b"})
    assert context.group_ids == frozenset({"operations"})


@pytest.mark.parametrize(
    ("secret", "issuer", "audience", "now"),
    [
        ("wrong-secret", "enterprise-rag", "enterprise-rag-api", 1_000),
        ("correct-secret", "other-issuer", "enterprise-rag-api", 1_000),
        ("correct-secret", "enterprise-rag", "other-audience", 1_000),
        ("correct-secret", "enterprise-rag", "enterprise-rag-api", 2_000),
    ],
)
def test_invalid_signature_scope_or_expiry_is_rejected(
    secret: str,
    issuer: str,
    audience: str,
    now: int,
) -> None:
    """中文：伪造签名、跨系统令牌和到期令牌都不能产生用户上下文。

    English: Forged, cross-system, and expired tokens must never produce a user context.
    """

    with pytest.raises(ValueError):
        decode_hs256_user_context(
            _token("correct-secret"),
            secret,
            issuer,
            audience,
            now=now,
        )
