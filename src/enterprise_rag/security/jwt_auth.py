"""中文：仅使用标准库验证 HS256 JWT，并从已验证声明构建租户用户上下文。

English: Verify HS256 JWTs with the standard library and build tenant context from trusted claims.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping

from enterprise_rag.domain.models import UserContext


def _decode_segment(segment: str) -> bytes:
    """中文：解码无填充 Base64URL 段并拒绝非法编码。

    English: Decode an unpadded Base64URL segment and reject malformed encoding.
    """

    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def _string_set(value: object, claim: str) -> frozenset[str]:
    """中文：把数组或逗号字符串声明收窄为非空字符串集合。

    English: Narrow an array or comma-separated claim to a set of non-empty strings.
    """

    if isinstance(value, str):
        return frozenset(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(item for item in value if item)
    if value is None:
        return frozenset()
    raise ValueError(f"JWT claim {claim} must be a string or string array")


def decode_hs256_user_context(
    token: str,
    secret: str,
    issuer: str,
    audience: str,
    *,
    now: int | None = None,
) -> UserContext:
    """中文：验证签名、算法、时效、签发者和受众后返回可信身份。

    English: Return trusted identity after signature, algorithm, time, issuer, and audience checks.
    """

    if not secret:
        raise ValueError("JWT secret is not configured")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("JWT must contain exactly three segments")
    encoded_header, encoded_payload, encoded_signature = parts
    try:
        header = json.loads(_decode_segment(encoded_header))
        payload = json.loads(_decode_segment(encoded_payload))
        supplied_signature = _decode_segment(encoded_signature)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("JWT encoding is invalid") from exc
    if not isinstance(header, Mapping) or header.get("alg") != "HS256":
        raise ValueError("JWT algorithm must be HS256")
    if not isinstance(payload, Mapping):
        raise ValueError("JWT payload must be an object")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("JWT signature is invalid")
    current_time = int(time.time()) if now is None else now
    expiration = payload.get("exp")
    if not isinstance(expiration, (int, float)) or current_time >= int(expiration):
        raise ValueError("JWT is expired or has no valid expiration")
    not_before = payload.get("nbf")
    if isinstance(not_before, (int, float)) and current_time < int(not_before):
        raise ValueError("JWT is not active yet")
    if payload.get("iss") != issuer:
        raise ValueError("JWT issuer is invalid")
    raw_audience = payload.get("aud")
    audiences = {raw_audience} if isinstance(raw_audience, str) else set(raw_audience or [])
    if audience not in audiences:
        raise ValueError("JWT audience is invalid")
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(tenant_id, str)
        or not tenant_id
    ):
        raise ValueError("JWT requires non-empty sub and tenant_id claims")
    return UserContext(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=_string_set(payload.get("roles"), "roles"),
        allowed_source_ids=_string_set(payload.get("source_ids"), "source_ids"),
        group_ids=_string_set(payload.get("group_ids"), "group_ids"),
    )
